/* Redaktions-Eintraege und ihre Text-Operationen auf dem Geraet (Spec 5.1).
 * Gegenstueck zu tools/redaktion/ops.py: dieselben Regeln, dieselben Testvektoren
 * (tools/redaktion/testvektoren.json); test_redaktion_js.py prueft die Paritaet.
 * Reine Funktionen, keine Fremdbibliotheken, laeuft im Browser und in Node.
 *
 * Verankerung: ziel = {anfang, absatz_index, [zeile, zeile_bis]}; anfang = erste 40 Zeichen
 * des Absatzes, Leerraum zusammengezogen; absatz_index und zeile/zeile_bis sind 0-basiert
 * (zeile_bis eingeschlossen). Stimmt vorher.hash nicht mehr, wird nichts geschrieben (konflikt).
 * Geaendert wird nur die Spanne des betroffenen Absatzes (bei "verschieben" zwei Spannen);
 * Tabs, Zeilenenden und fehlendes Schluss-Newline ausserhalb bleiben byteidentisch. */
(function (root, fabrik) {
  if (typeof module === "object" && module.exports) module.exports = fabrik();
  else root.Redaktion = fabrik();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const ANGEWENDET = "angewendet", KONFLIKT = "konflikt", UEBERSPRUNGEN = "uebersprungen";
  const ARTEN_OHNE_TEXTWIRKUNG = ["ruecknahme", "uebersetzung-uebernehmen", "neu-uebersetzen"];
  const TEXTARTEN = ["ersetzen", "verbinden", "trennen", "loeschen", "verschieben", "fussnote"];
  const FUSSNOTEN_AKTIONEN = ["marker-umbenennen", "marker-setzen", "marker-entfernen", "definition-umbenennen"];
  const MIN_KONTEXT = 8;                                    // marker-setzen: so viele Zeichen Kontext vor der Einfuegestelle

  // Leerraum wie Python (str.isspace / re \s): JS-\s kennt \x1c-\x1f und \x85 nicht, aber ﻿.
  const WS = "\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
  const WS_FOLGE = new RegExp("[" + WS + "]+", "gu");
  const WS_ANFANG = new RegExp("^[" + WS + "]+", "u");
  const WS_ENDE = new RegExp("[" + WS + "]+$", "u");
  const ABSATZ_TRENNER = "\\n[" + WS + "]*\\n";            // wie in korrektur.absatz_spannen
  const ZEILENENDE = /\r?\n/;
  // Fussnotenkennungen wie ops.py: nichts von ] [ und Leerraum (explizite Klasse); ein Marker ist [^id], solange kein ":" folgt.
  const KENNUNG_ZEICHEN = "[^\\]\\[ \\t\\r\\n\\f\\v\\u00a0]";
  const KENNUNG = new RegExp("^(?!\\^)" + KENNUNG_ZEICHEN + "+$", "u");
  const MARKER = "\\[\\^(" + KENNUNG_ZEICHEN + "+)\\](?!:)";
  const BUCHSTABE = /^\p{L}$/u;
  const KLEIN = /^\p{Lowercase}$/u;                         // wie Python str.islower fuer ein Zeichen

  const lstrip = (s) => s.replace(WS_ANFANG, "");
  const rstrip = (s) => s.replace(WS_ENDE, "");
  const strip = (s) => rstrip(lstrip(s));
  const zeichen = (s) => Array.from(s);                     // Codepunkte, nicht UTF-16-Einheiten
  const istObjekt = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
  const hat = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const istGanz = (x) => typeof x === "number" && Number.isInteger(x);

  /** Unicode NFC, jeder Leerraum zu einem Leerzeichen, getrimmt. */
  function normalisiere(text) {
    return strip(text.normalize("NFC").replace(WS_FOLGE, " "));
  }

  function ankerVon(text, laenge) {
    return zeichen(normalisiere(text)).slice(0, laenge === undefined ? 40 : laenge).join("");
  }

  /** FNV-1a 64 Bit ueber UTF-8 des Texts (\r\n als \n), 16 Hexstellen. */
  function pruefsumme(text) {
    const MASKE = 0xFFFFFFFFFFFFFFFFn, PRIME = 0x100000001B3n;
    let h = 0xCBF29CE484222325n;
    for (const b of new TextEncoder().encode(text.replace(/\r\n/g, "\n"))) {
      h = ((h ^ BigInt(b)) * PRIME) & MASKE;
    }
    return h.toString(16).padStart(16, "0");
  }

  function zufallsId() {
    const bytes = new Uint8Array(6);
    const c = typeof globalThis !== "undefined" ? globalThis.crypto : undefined;
    if (c && c.getRandomValues) c.getRandomValues(bytes);
    else for (let i = 0; i < 6; i++) bytes[i] = Math.floor(Math.random() * 256);
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  /** UTC mit Millisekunden, streng steigend: die Reihenfolge der Eintraege eines Geraets bleibt aus `erstellt` ablesbar. */
  let letzteZeit = 0;
  function jetztIso() {
    letzteZeit = Math.max(Date.now(), letzteZeit + 1);
    return new Date(letzteZeit).toISOString();
  }

  function neuerEintrag(buch, ebene, ziel, art, parameter, vorherText, hinweis, geraet) {
    parameter = parameter || {};
    return {
      id: zufallsId(),
      buch: buch,
      ebene: ebene,
      ziel: Object.assign({}, ziel),
      art: art,
      parameter: Object.assign({}, parameter),
      vorher: { hash: pruefsumme(vorherText), ausschnitt: zeichen(vorherText).slice(0, 80).join("") },
      nachher: hat(parameter, "nachher") ? parameter.nachher : null,
      hinweis: hinweis || "",
      erstellt: jetztIso(),
      geraet: geraet || "",
      status: "offen",
    };
  }

  /** Entfernt Eintraege, die ein `ruecknahme`-Eintrag (Ziel-id in parameter.id) aufhebt,
   * und die `ruecknahme`-Eintraege selbst. Reihenfolge bleibt. */
  function ohneZurueckgenommene(eintraege) {
    const wert = (v) => (v === undefined ? null : v);
    const zurueck = new Set();
    for (const e of eintraege) {
      if (istObjekt(e) && e.art === "ruecknahme") zurueck.add(wert(istObjekt(e.parameter) ? e.parameter.id : null));
    }
    return eintraege.filter((e) => !(istObjekt(e) && (e.art === "ruecknahme" || zurueck.has(wert(e.id)))));
  }

  /** Ein `ruecknahme`-Eintrag fuer `eintrag` (hebt ihn bei APIC auf, solange er dort nicht angewendet ist). */
  function ruecknahmeFuer(eintrag, geraet, hinweis, buch) {
    return neuerEintrag(buch || eintrag.buch || "", eintrag.ebene || "chunk-orig", istObjekt(eintrag.ziel) ? eintrag.ziel : {}, "ruecknahme",
                        { id: eintrag.id }, "", hinweis || "Zurückgenommen", geraet);
  }

  /** Wirksame Eintraege fuer Anzeige und Zaehlung: ohne `ruecknahme`-Eintraege und ohne die von ihnen
   * aufgehobenen Ziele. Ein schon `angewendetes` Ziel bleibt stehen (die Rücknahme kam zu spaet). */
  function wirksame(eintraege) {
    const angewendet = new Set(), zurueck = new Set();
    for (const e of eintraege) if (istObjekt(e) && e.status === ANGEWENDET && typeof e.id === "string") angewendet.add(e.id);
    for (const e of eintraege) {
      if (istObjekt(e) && e.art === "ruecknahme" && istObjekt(e.parameter) && !angewendet.has(e.parameter.id)) zurueck.add(e.parameter.id);
    }
    return eintraege.filter((e) => istObjekt(e) && e.art !== "ruecknahme" && !zurueck.has(e.id));
  }

  /** Nimmt den Eintrag `id` zurueck (Spec 5.1: solange er nicht `angewendet` ist) und gibt die neue Liste
   * zurueck (die alte bleibt unberuehrt). `angewendet`, unbekannte ids und `ruecknahme`-Eintraege bleiben
   * unveraendert. Spaetere Texteintraege, die auf dem Ergebnis des entfernten aufbauen (gleicher Chunk,
   * gleicher Absatz oder Anker), werden als `konflikt` markiert, nicht geloescht (auch Folgeketten).
   * War der Eintrag schon bei APIC (nicht mehr `offen`), kommt ein `ruecknahme`-Eintrag (offen) dazu,
   * der mitgesendet wird. */
  function zuruecknehmen(eintraege, id, optionen) {
    const liste = eintraege.slice();
    const i = liste.findIndex((e) => istObjekt(e) && e.id === id);
    if (i < 0) return liste;
    const weg = liste[i];
    if (weg.art === "ruecknahme" || weg.status === ANGEWENDET) return liste;
    liste.splice(i, 1);
    const quellen = [weg];
    for (let j = i; j < liste.length; j++) {
      const e = liste[j];
      if (!istObjekt(e) || !TEXTARTEN.includes(e.art) || !istObjekt(e.ziel) || e.ziel.chunk !== (weg.ziel || {}).chunk) continue;
      if (e.status === ANGEWENDET || e.status === KONFLIKT) continue;
      if (!quellen.some((q) => baueAuf(e, q))) continue;
      liste[j] = Object.assign({}, e, { status: KONFLIKT, grund: "abhängig vom zurückgenommenen Eintrag " + id, vorKonflikt: e.status });
      quellen.push(liste[j]);
    }
    const nieGesendet = weg.status === "offen" || (weg.status === KONFLIKT && weg.vorKonflikt === "offen");
    if (!nieGesendet) liste.push(ruecknahmeFuer(weg, optionen && optionen.geraet));
    return liste;
  }

  /** Baut `e` auf dem Absatz auf, den `q` veraendert (nur Textarten von `q` veraendern ihn). */
  function baueAuf(e, q) {
    if (!TEXTARTEN.includes(q.art) || !istObjekt(q.ziel)) return false;
    const p = istObjekt(q.parameter) ? q.parameter : {};
    const anker = new Set([q.ziel.anfang]);
    if (typeof p.nachher === "string") anker.add(ankerVon(p.nachher));
    if (typeof p.nach_anfang === "string") anker.add(p.nach_anfang);
    const eig = istObjekt(e.parameter) ? e.parameter : {};
    return anker.has(e.ziel.anfang) || (typeof eig.nach_anfang === "string" && anker.has(eig.nach_anfang))
      || (istGanz(e.ziel.absatz_index) && e.ziel.absatz_index === q.ziel.absatz_index);
  }

  /** [start, ende)-Bereiche der Absaetze im UNVERAENDERTEN Text (wie korrektur.absatz_spannen). */
  function absatzSpannen(text) {
    const spannen = [];
    const trenner = new RegExp(ABSATZ_TRENNER, "gu");
    let pos = 0, m;
    const stueck = (ende) => {
      const s = text.slice(pos, ende);
      if (strip(s)) {
        const links = s.length - lstrip(s).length;
        const rechts = rstrip(s).length;
        spannen.push([pos + links, pos + rechts]);
      }
    };
    while ((m = trenner.exec(text)) !== null) {
      stueck(m.index);
      pos = m.index + m[0].length;
    }
    stueck(text.length);
    return spannen;
  }

  /** Index des Ziel-Absatzes: Kandidaten haben gleichen Anker; absatz_index gewinnt, wenn er
   * Kandidat ist; sonst genau ein Kandidat; sonst null (nie der erste Treffer). */
  function finde(text, ziel) {
    const kandidaten = [];
    absatzSpannen(text).forEach(([a, b], i) => { if (ankerVon(text.slice(a, b)) === ziel.anfang) kandidaten.push(i); });
    if (kandidaten.includes(ziel.absatz_index)) return ziel.absatz_index;
    return kandidaten.length === 1 ? kandidaten[0] : null;
  }

  function zeilen(absatz) {
    return [absatz.split(ZEILENENDE), absatz.includes("\r\n") ? "\r\n" : "\n"];
  }

  /** Silbentrennung am Zeilenende (Buchstabe + '-', danach Kleinbuchstabe) entfernen,
   * sonst mit einem Leerzeichen verbinden. */
  function verbinde(oben, unten) {
    const o = zeichen(oben), u = zeichen(unten);
    if (o.length >= 2 && o[o.length - 1] === "-" && BUCHSTABE.test(o[o.length - 2]) && u.length && KLEIN.test(u[0])) {
      return o.slice(0, -1).join("") + unten;
    }
    return rstrip(oben) + " " + lstrip(unten);
  }

  function bereich(ziel, anzahl) {
    const z = ziel.zeile;
    if (!istGanz(z)) return null;
    const bis = hat(ziel, "zeile_bis") ? ziel.zeile_bis : z;
    if (!istGanz(bis) || !(0 <= z && z <= bis && bis < anzahl)) return null;
    return [z, bis];
  }

  /** Zu loeschender Zeichenbereich fuer einen ganzen Absatz samt einem angrenzenden Trenner. */
  function ohneAbsatz(spannen, i) {
    const [a, b] = spannen[i];
    if (i + 1 < spannen.length) return [a, spannen[i + 1][0]];
    if (i > 0) return [spannen[i - 1][1], b];
    return [a, b];
  }

  const konflikt = (text, grund) => ({ text: text, status: KONFLIKT, grund: grund });
  const kennungOk = (k) => typeof k === "string" && KENNUNG.test(k);

  /** Zeilenende fuer einen neu eingegebenen mehrzeiligen Absatz: das des Absatzes, hat er keinen Umbruch,
   * das der Datei (CRLF, sobald irgendwo ein \r\n steht). */
  function zeilenendeFuer(text, absatz) {
    if (absatz.includes("\r\n")) return "\r\n";
    if (absatz.includes("\n")) return "\n";
    return text.includes("\r\n") ? "\r\n" : "\n";
  }

  /** Position HINTER dem woertlichen Kontext `nach` im Absatz (marker-setzen, trennen): mindestens MIN_KONTEXT Zeichen,
   * genau ein Treffer (ueberlappende zaehlen mit). Ergebnis {ende} oder {grund}. */
  function stelle(absatz, nach) {
    if (typeof nach !== "string" || zeichen(nach).length < MIN_KONTEXT) {
      return { grund: "Kontext für die Einfügestelle fehlt oder ist kürzer als " + MIN_KONTEXT + " Zeichen" };
    }
    const treffer = [];
    for (let i = absatz.indexOf(nach); i >= 0; i = absatz.indexOf(nach, i + 1)) treffer.push(i);
    if (treffer.length !== 1) return { grund: treffer.length ? "Einfügestelle nicht eindeutig" : "Einfügestelle nicht gefunden" };
    return { ende: treffer[0] + nach.length };
  }

  function fussnote(text, absatz, a, b, ziel, parameter, zl, trenner) {
    const aktion = parameter.aktion;
    if (!FUSSNOTEN_AKTIONEN.includes(aktion)) return konflikt(text, "unbekannte Fussnoten-Aktion: " + aktion);

    if (aktion === "marker-umbenennen" || aktion === "marker-entfernen") {
      const alt = parameter[aktion === "marker-umbenennen" ? "alt" : "id"], vk = parameter.vorkommen;
      if (!kennungOk(alt) || !istGanz(vk) || vk < 0) return konflikt(text, "Fussnoten-Parameter fehlerhaft (Kennung oder Vorkommen)");
      const treffer = Array.from(absatz.matchAll(new RegExp(MARKER, "gu"))).filter((m) => m[1] === alt);
      if (vk >= treffer.length) return konflikt(text, "Marker [^" + alt + "] (Vorkommen " + vk + ") nicht im Absatz");
      const m = treffer[vk];
      let ersatz = "";
      if (aktion === "marker-umbenennen") {
        const neu = parameter.neu;
        if (!kennungOk(neu)) return konflikt(text, "neue Kennung ungültig (leer, Leerraum oder eckige Klammer)");
        if (neu === alt) return konflikt(text, "neue Kennung ist die alte");
        ersatz = "[^" + neu + "]";
      }
      return ok(text.slice(0, a) + absatz.slice(0, m.index) + ersatz + absatz.slice(m.index + m[0].length) + text.slice(b));
    }

    if (aktion === "marker-setzen") {
      const kennung = parameter.id;
      if (!kennungOk(kennung)) return konflikt(text, "Kennung ungültig (leer, Leerraum oder eckige Klammer)");
      const st = stelle(absatz, parameter.nach);
      if (st.ende === undefined) return konflikt(text, st.grund);
      const ende = st.ende;
      return ok(text.slice(0, a) + absatz.slice(0, ende) + "[^" + kennung + "]" + absatz.slice(ende) + text.slice(b));
    }

    // definition-umbenennen
    const alt = parameter.alt, neu = parameter.neu, z = ziel.zeile;
    if (!kennungOk(alt) || !kennungOk(neu)) return konflikt(text, "Kennung ungültig (leer, Leerraum oder eckige Klammer)");
    if (neu === alt) return konflikt(text, "neue Kennung ist die alte");
    if (!istGanz(z) || !(0 <= z && z < zl.length)) return konflikt(text, "Zeile der Definition fehlt oder liegt außerhalb des Absatzes");
    const kopf = "[^" + alt + "]:";
    if (!zl[z].startsWith(kopf)) return konflikt(text, "Zeile " + z + " ist keine Definition von [^" + alt + "]");
    if (text.split(ZEILENENDE).some((zeile) => zeile.startsWith("[^" + neu + "]:"))) {
      return konflikt(text, "Kennung [^" + neu + "] ist im Kapitel schon als Definition vergeben");
    }
    const neuZeilen = zl.slice();
    neuZeilen[z] = "[^" + neu + "]:" + zl[z].slice(kopf.length);
    return ok(text.slice(0, a) + neuZeilen.join(trenner) + text.slice(b));
  }
  const ok = (text) => ({ text: text, status: ANGEWENDET, grund: "" });

  /** Wendet einen Eintrag an. Ein fehlerhafter Eintrag liefert nie eine Ausnahme, sondern einen
   * Konflikt mit Grund; der Text bleibt dann unveraendert. */
  function wendeAn(text, eintrag) {
    try {
      return wendeAnRoh(text, eintrag);
    } catch (e) {
      return konflikt(text, "fehlerhafter Eintrag: " + (e && e.name ? e.name : "Fehler"));
    }
  }

  function wendeAnRoh(text, eintrag) {
    if (!istObjekt(eintrag)) return konflikt(text, "fehlerhafter Eintrag: kein Objekt");
    const art = eintrag.art;
    if (art === "marke") return ok(text);
    if (ARTEN_OHNE_TEXTWIRKUNG.includes(art)) return { text: text, status: UEBERSPRUNGEN, grund: "keine Textoperation" };
    if (!TEXTARTEN.includes(art)) return konflikt(text, "unbekannte Art: " + art);

    const ziel = eintrag.ziel, parameter = eintrag.parameter;
    if (!istObjekt(ziel)) return konflikt(text, "fehlerhafter Eintrag: ziel fehlt");
    if (!istObjekt(parameter)) return konflikt(text, "fehlerhafter Eintrag: parameter fehlt");
    const erwartet = istObjekt(eintrag.vorher) ? eintrag.vorher.hash : null;
    if (typeof erwartet !== "string" || !erwartet) return konflikt(text, "vorher fehlt");
    const index = finde(text, ziel);
    if (index === null) return konflikt(text, "Absatz nicht gefunden oder nicht eindeutig");
    const spannen = absatzSpannen(text);
    const [a, b] = spannen[index];
    const absatz = text.slice(a, b);
    if (erwartet !== pruefsumme(absatz)) {
      return konflikt(text, "Der Absatz hat sich seit dem Eintrag geändert (vorher stimmt nicht mehr)");
    }
    const [zl, trenner] = zeilen(absatz);

    if (art === "ersetzen") {
      const nachher = parameter.nachher;
      if (typeof nachher !== "string") return konflikt(text, "parameter.nachher fehlt oder ist kein Text");
      if (!strip(nachher)) return konflikt(text, "parameter.nachher ist leer");
      if (new RegExp(ABSATZ_TRENNER, "u").test(strip(nachher))) {
        return konflikt(text, "parameter.nachher enthält eine Leerzeile (würde den Absatz teilen)");
      }
      return ok(text.slice(0, a) + strip(nachher).replace(/\r?\n/g, zeilenendeFuer(text, absatz)) + text.slice(b));
    }

    if (art === "fussnote") return fussnote(text, absatz, a, b, ziel, parameter, zl, trenner);

    if (art === "verbinden") {
      const z = ziel.zeile;
      if (!istGanz(z) || !(0 <= z && z < zl.length - 1)) return konflikt(text, "keine Zeile zum Verbinden");
      const neu = zl.slice(0, z).concat([verbinde(zl[z], zl[z + 1])], zl.slice(z + 2));
      return ok(text.slice(0, a) + neu.join(trenner) + text.slice(b));
    }

    if (art === "trennen" && !hat(ziel, "zeile") && hat(parameter, "nach")) {
      // Form mit Kontext: den Absatz hinter dem Kontexttext teilen (einzeilige Absaetze haben keine Zeile zum Trennen)
      const st = stelle(absatz, parameter.nach);
      if (st.ende === undefined) return konflikt(text, st.grund);
      const vorn = rstrip(absatz.slice(0, st.ende)), hinten = lstrip(absatz.slice(st.ende));
      if (!vorn || !hinten) return konflikt(text, "Trennen würde einen leeren Absatz ergeben");
      const z = zeilenendeFuer(text, absatz);
      return ok(text.slice(0, a) + vorn + z + z + hinten + text.slice(b));
    }

    if (art === "trennen") {
      const z = ziel.zeile;
      if (!istGanz(z) || !(1 <= z && z < zl.length)) return konflikt(text, "keine Zeile zum Trennen");
      const neu = zl.slice(0, z).join(trenner) + trenner + trenner + zl.slice(z).join(trenner);
      return ok(text.slice(0, a) + neu + text.slice(b));
    }

    if (art === "loeschen") {
      if (!hat(ziel, "zeile")) {
        const [von, bis] = ohneAbsatz(spannen, index);
        return ok(text.slice(0, von) + text.slice(bis));
      }
      const br = bereich(ziel, zl.length);
      if (br === null) return konflikt(text, "Zeilen ausserhalb des Absatzes");
      const rest = zl.slice(0, br[0]).concat(zl.slice(br[1] + 1));
      if (!rest.length) {
        const [von, ende] = ohneAbsatz(spannen, index);
        return ok(text.slice(0, von) + text.slice(ende));
      }
      return ok(text.slice(0, a) + rest.join(trenner) + text.slice(b));
    }

    // verschieben
    const br = bereich(ziel, zl.length);
    if (br === null) return konflikt(text, "Zeilen ausserhalb des Absatzes");
    const nach = parameter.nach_anfang;
    const kandidaten = [];
    spannen.forEach(([x, y], i) => { if (ankerVon(text.slice(x, y)) === nach) kandidaten.push(i); });
    if (kandidaten.length !== 1) return konflikt(text, "Zielabsatz zum Verschieben nicht gefunden oder nicht eindeutig");
    if (kandidaten[0] === index) return konflikt(text, "Zielabsatz ist der Quellabsatz");
    const [z, bis] = br;
    const bewegt = zl.slice(z, bis + 1).join(trenner);
    const rest = zl.slice(0, z).concat(zl.slice(bis + 1));
    const zielEnde = spannen[kandidaten[0]][1];
    const aenderungen = [];
    if (rest.length) aenderungen.push([a, b, rest.join(trenner)]);
    else aenderungen.push(ohneAbsatz(spannen, index).concat([""]));
    aenderungen.push([zielEnde, zielEnde, trenner + trenner + bewegt]);
    aenderungen.sort((x, y) => (y[0] - x[0]) || (y[1] - x[1]));      // von hinten nach vorn
    let neuText = text;
    for (const [von, bis_, neu] of aenderungen) neuText = neuText.slice(0, von) + neu + neuText.slice(bis_);
    return ok(neuText);
  }

  /** Wendet die Eintraege der Reihe nach an. Scheitert einer, werden spaetere Eintraege am
   * selben Absatz (gleicher Anker, auch der des erwarteten Ergebnisses) als abhaengiger
   * Konflikt gemeldet, mit der id des Ausloesers im Grund. */
  function spieleAb(text, eintraege) {
    const ergebnisse = [];
    const gesperrt = new Map();                                       // Anker -> id des Ausloesers
    const sperre = (anker, id) => { if (!gesperrt.has(anker)) gesperrt.set(anker, id); };
    for (const e of eintraege) {
      if (!istObjekt(e)) {
        ergebnisse.push(konflikt(text, "fehlerhafter Eintrag: kein Objekt"));
        continue;
      }
      const ziel = istObjekt(e.ziel) ? e.ziel : {};
      const parameter = istObjekt(e.parameter) ? e.parameter : {};
      const anfang = ziel.anfang;
      const ausloeser = typeof anfang === "string" ? gesperrt.get(anfang) : undefined;
      const eid = typeof e.id === "string" ? e.id : "?";
      let erg;
      if (ausloeser !== undefined && TEXTARTEN.includes(e.art)) {
        erg = konflikt(text, "abhängig von Eintrag " + ausloeser + ", der nicht angewendet werden konnte");
        if (typeof parameter.nachher === "string") sperre(ankerVon(parameter.nachher), ausloeser);
      } else {
        erg = wendeAn(text, e);
        if (erg.status === KONFLIKT) {
          if (typeof anfang === "string") sperre(anfang, eid);
          if (typeof parameter.nachher === "string") sperre(ankerVon(parameter.nachher), eid);
        }
      }
      text = erg.text;
      ergebnisse.push(erg);
    }
    return { text: text, ergebnisse: ergebnisse };
  }

  // ---- Speicher, Senden, Stand (Spec 5.2) ------------------------------------------------------

  /** Speicher der Eintraege je Buch ueber ein Schluessel-Wert-Paar kv = {get(key), set(key, value)}
   * (im Browser IndexedDB). Schluessel: "redaktion:<buchId>". */
  function speicher(kv) {
    return {
      laden: async (buchId) => {
        const w = await kv.get("redaktion:" + buchId);
        return Array.isArray(w) ? w : [];
      },
      speichern: async (buchId, eintraege) => { await kv.set("redaktion:" + buchId, eintraege); },
    };
  }

  const basis = (adresse) => String(adresse || "").trim().replace(/\/+$/, "");

  async function antwort(r) {
    if (!r || !r.ok) {
      const f = new Error("APIC antwortete mit Status " + (r ? r.status : "?"));
      f.status = r ? r.status : 0;
      throw f;
    }
    return r.json();
  }

  /** Sendet Eintraege; nach einem 2xx gelten ALLE gesendeten ids als uebermittelt (APIC laesst
   * bereits bekannte ids in `angenommen` weg, ist aber idempotent: eine verlorene Antwort darf
   * nicht zu ewigem Wiederholen fuehren). Bei 400/413 wird halbiert, bis ein einzelner schlechter
   * Eintrag uebrig ist, damit er nicht alle anderen blockiert. Rueckgabe:
   * {gesendet: [ids], fehler: null | {art: "token"|"server"|"netz", code}}; bei Token-, Netz- und
   * sonstigen Serverfehlern wird abgebrochen. */
  async function sendeStapel(eintraege, optionen, fetchImpl) {
    const gesendet = [];
    let fehler = null, stopp = false;
    async function stapel(teil) {
      if (!teil.length || stopp) return;
      try {
        await sende(teil, optionen, fetchImpl);
        for (const e of teil) gesendet.push(e.id);
      } catch (x) {
        const code = x && typeof x.status === "number" ? x.status : 0;
        if (!code) { fehler = { art: "netz", code: 0 }; stopp = true; return; }
        if (code === 401 || code === 403) { fehler = { art: "token", code: code }; stopp = true; return; }
        const zuGross = code === 400 || code === 413;
        if (zuGross && teil.length > 1) {
          const mitte = Math.ceil(teil.length / 2);
          await stapel(teil.slice(0, mitte));
          await stapel(teil.slice(mitte));
          return;
        }
        if (!fehler) fehler = { art: "server", code: code };   // einzelner schlechter Eintrag bleibt offen
        if (!zuGross) stopp = true;
      }
    }
    await stapel(eintraege);
    return { gesendet: gesendet, fehler: fehler };
  }

  /** Schickt Eintraege an APIC. Gibt {angenommen: [ids]} zurueck; bei Netzfehler oder
   * Fehlerstatus wird abgelehnt (der Aufrufer aendert dann nichts). */
  async function sende(eintraege, optionen, fetchImpl) {
    const f = fetchImpl || fetch;
    const r = await f(basis(optionen.adresse) + "/api/aenderungen", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Redaktion-Token": optionen.token || "" },
      body: JSON.stringify({ geraet: optionen.geraet, buch: optionen.buch, eintraege: eintraege }),
    });
    const d = await antwort(r);
    return { angenommen: Array.isArray(d && d.angenommen) ? d.angenommen : [] };
  }

  /** Stand der Eintraege eines Buchs bei APIC: {id: {status, grund, ...}} (Inhalt von "stand"). */
  async function stand(buch, optionen, fetchImpl) {
    const f = fetchImpl || fetch;
    const r = await f(basis(optionen.adresse) + "/api/stand?buch=" + encodeURIComponent(buch), {
      method: "GET",
      headers: { "X-Redaktion-Token": optionen.token || "" },
    });
    const d = await antwort(r);
    return istObjekt(d && d.stand) ? d.stand : {};
  }

  // ---- Auftraege (Neu uebersetzen) und Vorschlag (Spec 5.2) --------------------------------------
  // Fehler tragen `status` (HTTP-Code, 0 bei Netzfehler/Zeitueberschreitung), wie bei `antwort`.

  function pruefeChunk(chunk) {
    if (!istGanz(chunk) || chunk < 0) throw new Error("chunk muss eine Zahl ab 0 sein");
  }

  /** Bittet APIC, einen Original-Chunk neu zu uebersetzen. Gibt {id} zurueck (die Id des Auftrags). */
  async function auftrag(buch, chunk, optionen, fetchImpl) {
    pruefeChunk(chunk);
    const f = fetchImpl || fetch;
    const r = await f(basis(optionen.adresse) + "/api/auftraege", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Redaktion-Token": optionen.token || "" },
      body: JSON.stringify(Object.assign({ art: "neu-uebersetzen", buch: buch, chunk: chunk }, optionen.lektor ? { lektor: optionen.lektor } : {})),
    });
    const d = await antwort(r);
    if (!istObjekt(d) || typeof d.id !== "string" || !d.id) throw new Error("APIC lieferte keine Auftrags-Id");
    return { id: d.id };
  }

  /** Zustand eines Auftrags: {zustand: wartet|laeuft|fertig|fehler, meldung}. 404: APIC kennt ihn nicht (mehr). */
  async function auftragStatus(id, optionen, fetchImpl) {
    const f = fetchImpl || fetch;
    const r = await f(basis(optionen.adresse) + "/api/auftraege/" + encodeURIComponent(id), {
      method: "GET",
      headers: { "X-Redaktion-Token": optionen.token || "" },
    });
    const d = await antwort(r);
    const zustaende = ["wartet", "laeuft", "fertig", "fehler"];
    if (!istObjekt(d) || !zustaende.includes(d.zustand)) throw new Error("APIC lieferte keinen gueltigen Zustand");
    return { zustand: d.zustand, meldung: typeof d.meldung === "string" ? d.meldung : "" };
  }

  /** Vorschlag zu einem Chunk: {alt, neu} (bisherige Uebersetzung und neu uebersetzter Text). 404: keiner da. */
  async function vorschlag(buch, chunk, optionen, fetchImpl) {
    pruefeChunk(chunk);
    const f = fetchImpl || fetch;
    const r = await f(basis(optionen.adresse) + "/api/vorschlag?buch=" + encodeURIComponent(buch) + "&chunk=" + chunk
      + (optionen.lektor ? "&lektor=" + encodeURIComponent(optionen.lektor) : ""), {
      method: "GET",
      headers: { "X-Redaktion-Token": optionen.token || "" },
    });
    const d = await antwort(r);
    if (!istObjekt(d) || typeof d.alt !== "string" || typeof d.neu !== "string") throw new Error("APIC lieferte keinen gueltigen Vorschlag");
    return { alt: d.alt, neu: d.neu };
  }

  /** Zaehlt wirksame Aenderungen und Markierungen (art "marke") getrennt; Rücknahmen und von ihnen
   * aufgehobene Eintraege zaehlen nicht als Aenderung. wartend = alle Eintraege mit Status "offen"
   * (auch Rücknahmen: sie muessen noch zu APIC). */
  function zaehler(eintraege) {
    const z = { aenderungen: 0, markierungen: 0, wartend: 0 };
    for (const e of eintraege) if (istObjekt(e) && e.status === "offen") z.wartend++;
    for (const e of wirksame(eintraege)) {
      if (e.art === "marke") z.markierungen++; else z.aenderungen++;
    }
    return z;
  }

  /** Muessen Eintraege noch bei APIC abgefragt werden? (gesendet oder bestaetigt, aber nicht erledigt). */
  function brauchtStand(liste) {
    return liste.some((e) => e.status === "gesendet" || e.status === "bestaetigt");
  }

  /** Uebernimmt den Stand von APIC in die lokale Liste. Gibt eine neue Liste zurueck (Eintraege unveraendert,
   * wenn nichts zu uebernehmen ist). `uebersprungen` gilt nur fuer Ruecknahmen (APIC wendet sie nie an: erledigt). */
  function uebernehmeStand(liste, stand) {
    return liste.map((e) => {
      const s = stand && stand[e.id];
      if (!s || e.status === ANGEWENDET || e.status === "offen") return e;
      const erlaubt = s.status === "bestaetigt" || s.status === ANGEWENDET || s.status === KONFLIKT
        || (s.status === UEBERSPRUNGEN && e.art === "ruecknahme");
      if (!erlaubt || s.status === e.status) return e;
      if (e.status === KONFLIKT && s.status === "bestaetigt") return e;       // lokaler Konflikt bleibt
      return Object.assign({}, e, { status: s.status, grund: s.grund || "" });
    });
  }

  return { normalisiere, ankerVon, pruefsumme, neuerEintrag, ohneZurueckgenommene, ruecknahmeFuer, wirksame, zuruecknehmen, absatzSpannen, finde, wendeAn, spieleAb,
           speicher, sende, sendeStapel, stand, brauchtStand, uebernehmeStand, auftrag, auftragStatus, vorschlag, zaehler };
});
