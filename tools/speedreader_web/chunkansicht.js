/* Chunk-Ansicht A (Spec Redaktion, Schritt 1): Roh-Chunk mit den offenen Eintraegen abgespielt,
 * Verdachtsstellen (verdacht.js) als Hintergrund und Chip an der Zeile, Konflikte am Absatz.
 *
 * Logik (bereite, signatur, entwurf) ist reine Funktion und laeuft in Node; rendere baut das DOM.
 * Alle Oberflaechentexte der Chips und Leisten stehen in data-label (CSS ::before), nicht im
 * Textinhalt: textContent des <pre> bleibt dadurch der angezeigte Chunk-Text (fuer das Markieren).
 *
 * Eingabe von bereite: roh = Text des Chunks (unveraendert), eintraege = alle Eintraege des Buchs,
 * chunk = Chunk-Nummer, abgelehnt = [{anfang, art, zeile}] (auf diesem Geraet abgelehnte Hinweise). */
(function (root, fabrik) {
  if (typeof module === "object" && module.exports) module.exports = fabrik(require("./redaktion.js"), require("./verdacht.js"), require("./fussnoten.js"));
  else root.Chunkansicht = fabrik(root.Redaktion, root.Verdacht, root.Fussnoten);
})(typeof self !== "undefined" ? self : this, function (R, V, F) {
  "use strict";

  const istObjekt = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
  const KATEGORIE = { "zeile-bricht-ab": "umbruch", fragment: "rest", fussnote: "fussnote",
                      "ueberschrift-im-text": "ueberschrift", verzeichnis: "verzeichnis", glossar: "glossar",
                  "marker-ohne-definition": "fussnote", "definition-ohne-marker": "fussnote",
                  "doppelte-definition": "fussnote", "andere-konvention": "fussnote-konvention" };
  const FARBE = { "zeile-bricht-ab": "gelb", fragment: "gelb", fussnote: "rot",
                  "ueberschrift-im-text": "blau", verzeichnis: "blau", glossar: "blau",
                  "marker-ohne-definition": "rot", "definition-ohne-marker": "gelb",
                  "doppelte-definition": "rot", "andere-konvention": "blau" };
  const CHIP = { "zeile-bricht-ab": "Umbruch?", fragment: "Rest?", fussnote: "Fußnote?",
                 "ueberschrift-im-text": "Überschrift?", verzeichnis: "Verzeichnis?", glossar: "Glossar?",
                 "marker-ohne-definition": "Fußnote ohne Text?", "definition-ohne-marker": "Text ohne Verweis?",
                 "doppelte-definition": "Doppelt?", "andere-konvention": "Andere Nummerierung?" };
  const WAS = { verbinden: "Zeile mit der nächsten verbinden", loeschen: "Zeile löschen" };

  /** Ebene der Ansicht: Roh-Chunk (Ziel `chunk`, Standard) oder fertiger Volltext (Ziel `datei`, ohne Verdachtsregeln der Chunks,
   *  dafuer Fussnotenhinweise). `enthalten` = Ids angewendeter Eintraege, die der exportierte Text schon enthaelt;
   *  `nr` = Position der Ansicht in der Liste (Chunk- bzw. Kapitelnummer), fuer die Zwischenspeicher der Oberflaeche. */
  const STANDARD = { ebene: "chunk-orig", zielfeld: "chunk", verdacht: true, enthalten: null };
  const optionenVon = (optionen) => Object.assign({}, STANDARD, optionen || {});

  const eigener = (e, chunk, o) => { o = o || STANDARD; return istObjekt(e) && e.ebene === o.ebene && istObjekt(e.ziel) && e.ziel[o.zielfeld] === chunk; };

  /** Kurzform aller fuer den Chunk relevanten Zustaende; aendert sie sich, muss neu berechnet werden. */
  function signatur(eintraege, chunk, anzahlAbgelehnt, bereit, optionen) {
    const o = optionenVon(optionen);
    const teile = [bereit ? "b" : "u", String(anzahlAbgelehnt | 0)];
    for (const e of eintraege || []) {
      if (!istObjekt(e)) continue;
      if (e.art === "ruecknahme") teile.push("r" + (istObjekt(e.parameter) ? e.parameter.id : ""));
      else if (eigener(e, chunk, o)) teile.push(e.id + ":" + e.status + ":" + (e.grund || ""));
    }
    return teile.join("|");
  }

  const zeilenSchluessel = (zeile) => R.normalisiere(zeile).slice(0, 80);

  /** Ergebnis: {chunk, roh, text, spannen, hinweise, erledigt, konflikte}.
   *  hinweise = offene Hinweise des abgespielten Texts (Verdacht.pruefe), ohne abgelehnte und ohne
   *  bereits markierte; konflikte = [{eintrag, grund, absatz_index|null, quelle}]. */
  function bereite(roh, eintraege, chunk, abgelehnt, bereit, optionen) {
    const o = optionenVon(optionen);
    const aus = { chunk: chunk, nr: o.nr === undefined ? chunk : o.nr, ebene: o.ebene, zielfeld: o.zielfeld, luecke: [], roh: roh, text: roh, spannen: R.absatzSpannen(roh), hinweise: [], erledigt: [], konflikte: [], markierungen: [], bereit: !!bereit };
    if (!bereit) return aus;
    const mein = R.ohneZurueckgenommene(eintraege || []).filter((e) => eigener(e, chunk, o));
    const abspiel = [], marken = new Set();
    for (const e of mein) {
      if (e.art === "marke") { if (typeof e.ziel.zeile === "number") marken.add(e.ziel.anfang + "\u0001" + e.ziel.zeile); continue; }
      if (o.enthalten && o.enthalten.has(e.id)) continue;            // steckt schon im exportierten Text, egal welchen Status die App gerade kennt
      // Am PC angewendet, aber noch nicht im exportierten Text (veralteter Export): trotzdem abspielen (Volltext)
      const imExport = e.status === "angewendet" && o.enthalten && !o.enthalten.has(e.id);
      if (!imExport && (e.status === "angewendet" || e.status === "abgelehnt" || e.status === "uebersprungen")) continue;
      if (e.status === "konflikt") { aus.konflikte.push({ eintrag: e, grund: e.grund || "", quelle: "apic" }); continue; }
      abspiel.push(e);
    }
    const lauf = R.spieleAb(roh, abspiel);
    lauf.ergebnisse.forEach((r, i) => {
      if (r.status !== "konflikt") return;
      if (abspiel[i].status === "angewendet") aus.luecke.push({ eintrag: abspiel[i], grund: r.grund });     // kein Konflikt der Person, sondern Export veraltet
      else aus.konflikte.push({ eintrag: abspiel[i], grund: r.grund, quelle: "lokal" });
    });
    aus.text = lauf.text;
    aus.spannen = R.absatzSpannen(aus.text);

    const abg = new Map();
    for (const a of abgelehnt || []) {
      if (!istObjekt(a)) continue;
      const k = a.anfang + "\u0001" + a.art;
      if (!abg.has(k)) abg.set(k, []);
      abg.get(k).push(a.zeile);
    }
    const zeilenCache = new Map();
    const zeileVon = (ai, zi) => {
      if (!zeilenCache.has(ai)) { const [a, b] = aus.spannen[ai]; zeilenCache.set(ai, aus.text.slice(a, b).split(/\r?\n/)); }
      return zeilenSchluessel(zeilenCache.get(ai)[zi] || "");
    };
    for (const h of o.verdacht ? V.pruefe(aus.text) : fussnotenHinweise(aus)) {
      const liste = abg.get(h.anfang + "\u0001" + h.art);
      if (liste && liste.some((z) => z === undefined || z === zeileVon(h.absatz_index, h.zeile))) continue;
      if (marken.has(h.anfang + "\u0001" + h.zeile)) { aus.erledigt.push(h); continue; }
      aus.hinweise.push(h);
    }
    for (const k of aus.konflikte) {
      const i = R.finde(aus.text, k.eintrag.ziel || {});
      k.absatz_index = i;
    }
    for (const e of mein) {                                  // freie Markierungen (Ansicht B) am Text zeigen
      if (e.art !== "marke" || e.status === "abgelehnt" || typeof e.ziel.zeile !== "number") continue;
      const i = R.finde(aus.text, e.ziel);
      if (i === null) continue;
      const kat = istObjekt(e.parameter) ? e.parameter.kategorie : "";
      const text = istObjekt(e.parameter) && typeof e.parameter.text === "string" ? e.parameter.text : "";
      aus.markierungen.push({ absatz_index: i, zeile: e.ziel.zeile, zeile_bis: typeof e.ziel.zeile_bis === "number" ? e.ziel.zeile_bis : e.ziel.zeile,
                              kategorie: kat || "", text: text });
    }
    return aus;
  }

  /** Fussnotenhinweise des abgespielten Volltexts im Format der Verdachtshinweise; der Vorschlag ist nur das Merken. */
  function fussnotenHinweise(aus) {
    return F.analysiere(aus.text).hinweise.map((h) => {
      const sp = aus.spannen[h.absatz_index];
      return { art: h.art, absatz_index: h.absatz_index, zeile: h.zeile, zeile_bis: h.zeile, anfang: R.ankerVon(aus.text.slice(sp[0], sp[1])),
               begruendung: h.begruendung, vorschlag: { art: "marke", parameter: { kategorie: KATEGORIE[h.art] } } };
    });
  }

  const absatzText = (ansicht, i) => { const s = ansicht.spannen[i]; return s ? ansicht.text.slice(s[0], s[1]) : null; };

  const zielBasis = (ansicht) => ({ [ansicht.zielfeld || "chunk"]: ansicht.chunk });

  /** Daten fuer Redaktion.neuerEintrag: {ziel, art, parameter, vorherText, hinweis}.
   *  was: "annehmen" | "markieren" (Hinweis h) oder "neu" (Konflikt k). null, wenn der Absatz fehlt. */
  function entwurf(ansicht, was, objekt) {
    if (was === "neu") {
      const e = objekt.eintrag, i = objekt.absatz_index;
      const vorherText = i === null || i === undefined ? null : absatzText(ansicht, i);
      if (vorherText === null) return null;
      return { ziel: Object.assign({}, e.ziel, zielBasis(ansicht), { absatz_index: i }), art: e.art,
               parameter: Object.assign({}, e.parameter), vorherText: vorherText, hinweis: e.hinweis || "" };
    }
    const h = objekt, vorherText = absatzText(ansicht, h.absatz_index);
    if (vorherText === null) return null;
    const ziel = Object.assign(zielBasis(ansicht), { anfang: h.anfang, absatz_index: h.absatz_index, zeile: h.zeile });
    if (was === "markieren" || h.vorschlag.art === "marke") {
      ziel.zeile_bis = h.zeile_bis;
      const kat = h.vorschlag.art === "marke" ? h.vorschlag.parameter.kategorie : KATEGORIE[h.art];
      return { ziel: ziel, art: "marke", parameter: { kategorie: kat }, vorherText: vorherText, hinweis: h.begruendung };
    }
    if (h.vorschlag.art === "loeschen") ziel.zeile_bis = h.zeile_bis;
    return { ziel: ziel, art: h.vorschlag.art, parameter: Object.assign({}, h.vorschlag.parameter), vorherText: vorherText, hinweis: h.begruendung };
  }

  // ---- Ansicht B: freie Auswahl -> Absatz und Zeilen -> Eintraege --------------------------------

  const ISTLEER = /\s/;

  /** Zeilen des Absatzes i im abgespielten Text: Startpositionen relativ zum Absatzanfang. */
  function zeilenStarts(ansicht, i) {
    const absatz = absatzText(ansicht, i), starts = [0], re = /\r?\n/g;
    let m;
    while ((m = re.exec(absatz)) !== null) starts.push(m.index + m[0].length);
    return starts;
  }
  /** Index der Zeile, die die Position p (relativ zum Absatz) enthaelt (binaere Suche). */
  function zeileBei(starts, p) {
    let lo = 0, hi = starts.length - 1;
    while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (starts[mid] <= p) lo = mid; else hi = mid - 1; }
    return lo;
  }

  /** Bildet die Auswahl [von, bis) im angezeigten (abgespielten) Text auf Absatz und Zeilen ab.
   *  Leerraum am Rand der Auswahl zaehlt nicht. null, wenn nichts Sichtbares ausgewaehlt ist.
   *  Ergebnis: {absatz_index, absatz_bis, anfang, anfang_bis, zeile, zeile_bis, zeilen, mehrere, von, bis, text}
   *  zeile/zeile_bis gelten im ersten Absatz (bei mehreren Absaetzen reicht zeile_bis bis zu dessen Ende). */
  function auswahlAbbilden(ansicht, von, bis) {
    const t = ansicht.text, sp = ansicht.spannen;
    if (!sp.length || !(von < bis)) return null;
    von = Math.max(0, von); bis = Math.min(t.length, bis);
    while (von < bis && ISTLEER.test(t[von])) von++;
    while (bis > von && ISTLEER.test(t[bis - 1])) bis--;
    if (bis <= von) return null;
    let i0 = -1, i1 = -1;
    for (let i = 0; i < sp.length; i++) {
      if (i0 < 0 && sp[i][1] > von) i0 = i;
      if (sp[i][0] < bis) i1 = i;
    }
    if (i0 < 0 || i1 < i0) return null;
    von = Math.max(von, sp[i0][0]); bis = Math.min(bis, sp[i1][1]);
    if (bis <= von) return null;
    const st0 = zeilenStarts(ansicht, i0);
    const zeile = zeileBei(st0, von - sp[i0][0]);
    const mehrere = i1 !== i0;
    const zeile_bis = mehrere ? st0.length - 1 : zeileBei(st0, bis - 1 - sp[i0][0]);
    return { absatz_index: i0, absatz_bis: i1, anfang: R.ankerVon(absatzText(ansicht, i0)), anfang_bis: R.ankerVon(absatzText(ansicht, i1)),
             zeile: zeile, zeile_bis: zeile_bis, zeilen: st0.length, mehrere: mehrere, von: von, bis: bis, text: t.slice(von, bis) };
  }

  const MARKEN = { kapitel: "kapitelgrenze-vermutet", verzeichnis: "verzeichnis", glossar: "glossar", markieren: "markiert" };

  /** Welche Werkzeuge fuer die Auswahl gelten (Auswahl ueber mehrere Absaetze: nur Markierungen). */
  function werkzeuge(a) {
    const einzeln = !!a && !a.mehrere;
    return { verbinden: einzeln && (a.zeile_bis > a.zeile || a.zeile < a.zeilen - 1), verschieben: einzeln, loeschen: einzeln,
             trennen: einzeln && a.zeile >= 1, kapitel: einzeln, verzeichnis: !!a, glossar: !!a, markieren: !!a };
  }

  /** Eintrags-Entwuerfe fuer ein Werkzeug: {liste:[{ziel, art, parameter, vorherText, hinweis}]} oder {fehler}.
   *  extra = {text} (Freitext der Markierung) bzw. {ziel_absatz} (Index des Zielabsatzes beim Verschieben).
   *  Anker und vorher stammen aus dem abgespielten Text; mehrere Verbindungen werden nacheinander
   *  auf dem jeweils verbundenen Text gebildet. */
  function entwuerfe(ansicht, was, a, extra) {
    extra = extra || {};
    if (!a || !werkzeuge(a)[was]) return { fehler: "Dieses Werkzeug passt nicht zur Auswahl" };
    const absatz = absatzText(ansicht, a.absatz_index);
    if (absatz === null) return { fehler: "Absatz nicht gefunden" };
    const ziel = Object.assign(zielBasis(ansicht), { anfang: a.anfang, absatz_index: a.absatz_index });
    const einer = (art, z, parameter) => ({ liste: [{ ziel: z, art: art, parameter: parameter, vorherText: absatz, hinweis: "" }] });
    if (MARKEN[was]) {
      const p = { kategorie: MARKEN[was] }, notiz = String(extra.text || "").trim();
      if (notiz) p.text = notiz;
      if (a.mehrere) { p.bis_absatz_index = a.absatz_bis; p.bis_anfang = a.anfang_bis; }
      return einer("marke", Object.assign(ziel, { zeile: a.zeile, zeile_bis: a.zeile_bis }), p);
    }
    if (was === "loeschen") return einer("loeschen", Object.assign(ziel, { zeile: a.zeile, zeile_bis: a.zeile_bis }), {});
    if (was === "trennen") return einer("trennen", Object.assign(ziel, { zeile: a.zeile }), {});
    if (was === "verschieben") {
      const j = extra.ziel_absatz, text = ansicht.text;
      if (typeof j !== "number" || !ansicht.spannen[j]) return { fehler: "Zielabsatz nicht gefunden" };
      if (j === a.absatz_index) return { fehler: "Das ist der Quellabsatz: bitte einen anderen Absatz antippen" };
      const nach = R.ankerVon(absatzText(ansicht, j));
      let gleich = 0;
      ansicht.spannen.forEach(([x, y]) => { if (R.ankerVon(text.slice(x, y)) === nach) gleich++; });
      if (gleich !== 1) return { fehler: "Der Zielabsatz beginnt wie ein anderer Absatz: bitte einen eindeutigen wählen" };
      return einer("verschieben", Object.assign(ziel, { zeile: a.zeile, zeile_bis: a.zeile_bis }), { nach_anfang: nach });
    }
    // verbinden: eine Verbindung je Zeilenwechsel im Bereich, jeweils auf dem Text nach der vorigen
    const n = a.zeile_bis > a.zeile ? a.zeile_bis - a.zeile : 1, liste = [];
    let text = ansicht.text;
    for (let k = 0; k < n; k++) {
      const sp = R.absatzSpannen(text)[a.absatz_index];
      if (!sp) return { fehler: "Absatz nicht gefunden" };
      const jetzt = text.slice(sp[0], sp[1]);
      const z = Object.assign({}, ziel, { anfang: R.ankerVon(jetzt), zeile: a.zeile });
      const e = R.neuerEintrag("", ansicht.ebene || "chunk-orig", z, "verbinden", {}, jetzt, "", "");
      const erg = R.wendeAn(text, e);
      if (erg.status !== "angewendet") return { fehler: "Zeilen lassen sich nicht verbinden: " + erg.grund };
      liste.push({ ziel: z, art: "verbinden", parameter: {}, vorherText: jetzt, hinweis: "" });
      text = erg.text;
    }
    return { liste: liste };
  }

  // ---- DOM ------------------------------------------------------------------------------------

  /** Bedienelement ohne Textinhalt: Beschriftung per data-label (CSS), Name per aria-label. */
  function knopf(klasse, label, name, aktion, nr) {
    const b = document.createElement("button");
    b.type = "button"; b.className = klasse; b.dataset.label = label; b.setAttribute("aria-label", name);
    b.dataset.aktion = aktion; if (nr !== undefined) b.dataset.nr = String(nr);
    return b;
  }
  function etikett(klasse, label) {
    const s = document.createElement("span");
    s.className = klasse; s.dataset.label = label;
    return s;
  }

  /** Zeichnet die Ansicht in `pre`. opt = {fuelle(eltern, text), aktion(was, objekt, ansicht)}.
   *  Klick-Behandlung: eine Delegation je <pre>; sie liest immer die zuletzt gezeichnete Ansicht. */
  function rendere(pre, ansicht, opt) {
    pre.textContent = "";
    pre._ca = { ansicht: ansicht, opt: opt };
    if (!pre._caKlick) {
      pre._caKlick = true;
      pre.addEventListener("click", (ev) => {
        const b = ev.target.closest && ev.target.closest("button[data-aktion]");
        if (!b || !pre.contains(b) || !pre._ca) return;
        ev.preventDefault();
        behandle(pre, b);
      });
    }
    const text = ansicht.text, spannen = ansicht.spannen;

    const start = new Map(), decke = new Map();                       // "ai:zi" -> [Hinweisnummern] / Klasse der Zeile
    ansicht.erledigt.forEach((h) => { for (let z = h.zeile; z <= h.zeile_bis; z++) decke.set(h.absatz_index + ":" + z, "markiert"); });
    const markeText = new Map();                                      // "ai:zi" -> Beschreibung der freien Markierung
    (ansicht.markierungen || []).forEach((m) => {
      for (let z = m.zeile; z <= m.zeile_bis; z++) {
        decke.set(m.absatz_index + ":" + z, "markiert");
        markeText.set(m.absatz_index + ":" + z, [m.kategorie, m.text].filter(Boolean).join(": ") || "Markierung");
      }
    });
    ansicht.hinweise.forEach((h, n) => {
      const k = h.absatz_index + ":" + h.zeile;
      if (!start.has(k)) start.set(k, []);
      start.get(k).push(n);
      for (let z = h.zeile; z <= h.zeile_bis; z++) if (!String(decke.get(h.absatz_index + ":" + z) || "").startsWith("verdacht")) decke.set(h.absatz_index + ":" + z, "verdacht verdacht-" + FARBE[h.art]);
    });
    const konfAbsatz = new Map(), konfOben = [];
    ansicht.konflikte.forEach((k, n) => {
      if (k.absatz_index === null || k.absatz_index === undefined) konfOben.push(n);
      else { if (!konfAbsatz.has(k.absatz_index)) konfAbsatz.set(k.absatz_index, []); konfAbsatz.get(k.absatz_index).push(n); }
    });

    let puffer = "";
    const leere = () => { if (puffer) { opt.fuelle(pre, puffer); puffer = ""; } };
    const konfliktBlock = (n) => {
      const k = ansicht.konflikte[n];
      const b = document.createElement("div");
      b.className = "konflikt"; b.setAttribute("role", "group");
      b.setAttribute("aria-label", "Konflikt: " + (k.grund || "ohne Angabe"));
      b.append(etikett("konflikt-chip", "Konflikt"), etikett("konflikt-grund", k.grund || "Eintrag passt nicht mehr zum Text"));
      const neu = knopf("aktion", "Neu anwenden", "Neu anwenden", "neu", n);
      if (k.absatz_index === null || k.absatz_index === undefined) { neu.disabled = true; neu.title = "Absatz nicht gefunden oder nicht eindeutig"; }
      b.append(neu, knopf("aktion", "Verwerfen", "Verwerfen", "verwerfen", n));
      return b;
    };
    konfOben.forEach((n) => { leere(); pre.append(konfliktBlock(n)); });

    const zeile = (ai, zi, s, eol) => {
      const k = ai + ":" + zi, klasse = decke.get(k);
      if (!klasse) { puffer += s + eol; return; }
      leere();
      const span = document.createElement("span");
      span.className = klasse;
      if (markeText.has(k)) { span.dataset.marke = markeText.get(k); span.title = "Markierung: " + markeText.get(k); }
      opt.fuelle(span, s);
      for (const n of start.get(k) || []) {
        const h = ansicht.hinweise[n];
        span.append(knopf("chip", CHIP[h.art], "Verdacht: " + h.begruendung, "chip", n));
        if (!span.dataset.h) span.dataset.h = String(n);
      }
      pre.append(span);
      puffer += eol;
    };

    let pos = 0;
    spannen.forEach(([a, b], ai) => {
      puffer += text.slice(pos, a);
      for (const n of konfAbsatz.get(ai) || []) { leere(); pre.append(konfliktBlock(n)); }
      const absatz = text.slice(a, b), re = /\r?\n/g;
      let von = 0, zi = 0, m;
      while ((m = re.exec(absatz)) !== null) { zeile(ai, zi++, absatz.slice(von, m.index), m[0]); von = m.index + m[0].length; }
      zeile(ai, zi, absatz.slice(von), "");
      pos = b;
    });
    puffer += text.slice(pos);
    leere();
  }

  function behandle(pre, b) {
    const { ansicht, opt } = pre._ca, aktion = b.dataset.aktion, nr = Number(b.dataset.nr);
    if (aktion === "chip") { schalteLeiste(pre, nr); return; }
    if (aktion === "schliessen") { schliesseLeiste(pre); return; }
    const objekt = aktion === "neu" || aktion === "verwerfen" ? ansicht.konflikte[nr] : ansicht.hinweise[nr];
    if (objekt) opt.aktion(aktion, objekt, ansicht);
  }

  function schliesseLeiste(pre) {
    const alt = pre.querySelector(".verdacht-leiste");
    if (alt) alt.remove();
    pre.querySelectorAll('[aria-expanded="true"]').forEach((c) => c.setAttribute("aria-expanded", "false"));
  }

  /** Oeffnet die Leiste zum Hinweis n direkt vor seiner Zeile (oder schliesst sie, wenn sie dort schon offen ist). */
  function schalteLeiste(pre, n) {
    const { ansicht } = pre._ca, h = ansicht.hinweise[n];
    const offen = pre.querySelector(".verdacht-leiste");
    const war = offen && offen.dataset.nr === String(n);
    schliesseLeiste(pre);
    const chip = pre.querySelector('button.chip[data-nr="' + n + '"]');
    if (war || !h || !chip) return;
    const leiste = document.createElement("div");
    leiste.className = "verdacht-leiste"; leiste.dataset.nr = String(n);
    leiste.setAttribute("role", "group"); leiste.setAttribute("aria-label", "Verdacht: " + h.begruendung);
    const was = h.vorschlag.art === "marke" ? "als Markierung „" + h.vorschlag.parameter.kategorie + "“ merken" : WAS[h.vorschlag.art];
    leiste.append(etikett("grund", h.begruendung), etikett("vorschlag", "Vorschlag: " + was),
      knopf("aktion", "Annehmen", "Annehmen", "annehmen", n),
      knopf("aktion", "Ablehnen", "Ablehnen", "ablehnen", n),
      knopf("aktion", "Markieren", "Markieren", "markieren", n),
      knopf("aktion", "Schließen", "Schließen", "schliessen", n));
    chip.setAttribute("aria-expanded", "true");
    chip.closest(".verdacht").before(leiste);
  }

  // ---- Ansicht B: DOM (Auswahl lesen, Werkzeugleiste) --------------------------------------------

  /** Zeichenposition (im angezeigten Text) des DOM-Punkts (node, off) innerhalb von pre.
   *  Nicht mitgezaehlt: Textknoten in [data-leer] (die Pfeile vor Tabs bei aktivem Schalter ¶). */
  function offsetIn(pre, node, off) {
    const r = document.createRange();
    r.selectNodeContents(pre);
    try { r.setEnd(node, off); } catch (e) { return null; }
    const lauf = document.createTreeWalker(pre, NodeFilter.SHOW_TEXT);
    let summe = 0, t;
    while ((t = lauf.nextNode()) !== null) {
      if (t.parentElement && t.parentElement.closest("[data-leer]")) continue;
      if (r.comparePoint(t, t.length) <= 0) { summe += t.length; continue; }      // ganz vor dem Punkt
      if (t === node) summe += off;
      break;
    }
    return summe;
  }

  const NUR_CHUNK = ["kapitel", "verzeichnis", "glossar"];
  const WERKZEUGE = [["verbinden", "Zeilen verbinden"], ["verschieben", "Ausschneiden / verschieben"], ["loeschen", "Löschen"],
                     ["trennen", "Absatz hier trennen"], ["kapitel", "Kapitel beginnt hier"], ["verzeichnis", "Inhaltsverzeichnis"],
                     ["glossar", "Glossar"], ["markieren", "Nur markieren"]];

  /** Haengt die Werkzeugleiste (#werkzeugleiste, im Eltern von pre) an die Auswahl in pre.
   *  opt = {ansicht(): aktuelle Ansicht oder null, ausfuehren(ansicht, liste, was): Promise}. */
  function installiereWerkzeuge(pre, opt) {
    const eltern = pre.parentElement;
    const leiste = document.createElement("div");
    leiste.id = "werkzeugleiste"; leiste.hidden = true; leiste.setAttribute("role", "toolbar"); leiste.setAttribute("aria-label", "Werkzeuge für die Auswahl");
    const reihe = document.createElement("div"); reihe.className = "werkzeug-reihe";
    leiste.append(reihe);
    const knoepfe = {};
    for (const [was, text] of WERKZEUGE) {
      const b = document.createElement("button");
      b.type = "button"; b.dataset.was = was; b.textContent = text;
      reihe.append(b); knoepfe[was] = b;
    }
    const notiz = document.createElement("input");
    notiz.type = "text"; notiz.id = "werkzeug-notiz"; notiz.placeholder = "Notiz (optional)"; notiz.setAttribute("aria-label", "Notiz zur Markierung (optional)");
    notiz.maxLength = 200; notiz.autocomplete = "off";
    const status = document.createElement("span"); status.className = "werkzeug-status"; status.setAttribute("role", "status");
    const abbruch = document.createElement("button");
    abbruch.type = "button"; abbruch.dataset.was = "abbrechen"; abbruch.textContent = "Abbrechen"; abbruch.hidden = true;
    reihe.append(notiz, abbruch);
    leiste.append(status);
    eltern.append(leiste);

    const st = { auswahl: null, ansicht: null, modus: null, halte: false, geplant: 0, laeuft: false, haltTimer: 0, rechteck: null };

    const verberge = () => {
      st.auswahl = null; st.ansicht = null; st.modus = null; st.rechteck = null; st.halte = false; clearTimeout(st.haltTimer);
      leiste.hidden = true; leiste.classList.remove("verschiebt", "kompakt"); delete pre.dataset.verschieben;
      status.textContent = ""; abbruch.hidden = true; notiz.value = "";
    };
    const setzeStatus = (t) => { status.textContent = t; };
    const aktualisiere = () => {
      const w = werkzeuge(st.auswahl), verschiebt = st.modus === "verschieben";
      const volltext = !!st.ansicht && st.ansicht.ebene === "volltext";           // Kapitel, Verzeichnis, Glossar: Sache der Struktur (P3)
      for (const [was] of WERKZEUGE) {
        knoepfe[was].disabled = !w[was] || verschiebt || st.laeuft;
        knoepfe[was].hidden = volltext && NUR_CHUNK.includes(was);
      }
      notiz.disabled = verschiebt; abbruch.hidden = !verschiebt; leiste.classList.toggle("verschiebt", verschiebt);
      if (verschiebt) setzeStatus("Zielabsatz antippen, hinter den die Zeilen kommen");
      else if (st.auswahl && st.auswahl.mehrere) setzeStatus("Auswahl über mehrere Absätze: nur Markierungen");
      else if (!st.laeuft) setzeStatus("Operationen wirken auf ganze Zeilen");
    };
    const platziere = () => {
      if (leiste.hidden) return;
      const sel = document.getSelection();
      let ziel = st.rechteck;
      if (st.modus !== "verschieben" && sel && sel.rangeCount && !sel.isCollapsed) {
        const rs = sel.getRangeAt(0).getClientRects();
        if (rs.length) { const z = rs[rs.length - 1], a = rs[0]; ziel = { oben: a.top, unten: z.bottom, links: z.left }; }
      }
      st.rechteck = ziel;
      const pr = eltern.getBoundingClientRect(), prw = pre.getBoundingClientRect();
      const grob = window.matchMedia && window.matchMedia("(pointer: coarse)").matches ? 28 : 6;   // Platz fuer die Auswahl-Griffe
      const lege = () => {
        const hoch = leiste.offsetHeight, breit = leiste.offsetWidth;
        const unten = ziel ? ziel.unten - pr.top + grob : prw.top - pr.top;
        const oben = ziel ? ziel.oben - pr.top - hoch - grob : -1;
        const passtUnten = unten + hoch <= pr.height, passtOben = oben >= 0;
        let top = passtUnten || !passtOben ? unten : oben;
        top = Math.max(0, Math.min(top, Math.max(0, pr.height - hoch)));
        let left = ziel ? ziel.links - pr.left : 0;
        left = Math.max(0, Math.min(left, Math.max(0, pr.width - breit)));
        return { top: top, left: left, frei: passtUnten || passtOben };
      };
      leiste.classList.remove("kompakt");
      if (st.modus === "verschieben") {                                            // nur Hinweis und Abbrechen, unten am Rand: das Ziel bleibt frei
        leiste.style.left = "0px"; leiste.style.top = Math.max(0, pr.height - leiste.offsetHeight) + "px"; return;
      }
      let o = lege();
      if (!o.frei && ziel) { leiste.classList.add("kompakt"); o = lege(); }     // zu wenig Platz: eine scrollbare Reihe, Auswahl bleibt sichtbar
      const top = o.top, left = leiste.classList.contains("kompakt") ? 0 : o.left;
      leiste.style.top = top + "px"; leiste.style.left = left + "px";
    };

    const lies = () => {
      st.geplant = 0;
      if (st.modus === "verschieben" || st.laeuft || st.halte || leiste.contains(document.activeElement)) return;
      const sel = document.getSelection();
      if (!sel || !sel.rangeCount || sel.isCollapsed) { verberge(); return; }
      const r = sel.getRangeAt(0);
      if (!pre.contains(r.startContainer) || !pre.contains(r.endContainer)) { verberge(); return; }
      const ansicht = opt.ansicht();
      if (!ansicht || !ansicht.bereit) { verberge(); return; }
      const von = offsetIn(pre, r.startContainer, r.startOffset), bis = offsetIn(pre, r.endContainer, r.endOffset);
      const a = von === null || bis === null ? null : auswahlAbbilden(ansicht, von, bis);
      if (!a) { verberge(); return; }
      st.auswahl = a; st.ansicht = ansicht; leiste.hidden = false;
      aktualisiere(); platziere();
    };
    document.addEventListener("selectionchange", () => { if (!st.geplant) st.geplant = requestAnimationFrame(lies); });
    pre.addEventListener("scroll", () => { if (!leiste.hidden && st.modus !== "verschieben") requestAnimationFrame(platziere); }, { passive: true });
    window.addEventListener("resize", () => { if (!leiste.hidden) platziere(); });

    // Eine Beruehrung der Leiste darf die Auswahl nicht aufloesen (sonst verschwaende die Leiste vor dem Klick).
    leiste.addEventListener("pointerdown", (ev) => {
      st.halte = true; clearTimeout(st.haltTimer);
      if (ev.target !== notiz) ev.preventDefault();
    });
    const loeseHalt = () => { clearTimeout(st.haltTimer); st.haltTimer = setTimeout(() => { st.halte = false; }, 500); };
    leiste.addEventListener("pointerup", loeseHalt); leiste.addEventListener("pointercancel", loeseHalt);

    const ausfuehren = async (was, extra) => {
      const a = st.auswahl, ansicht = st.ansicht;
      const ent = entwuerfe(ansicht, was, a, extra);
      if (ent.fehler) { setzeStatus(ent.fehler); return false; }
      st.laeuft = true; aktualisiere(); setzeStatus("Wird gespeichert …");
      try {
        await opt.ausfuehren(ansicht, ent.liste, was);
        st.laeuft = false; verberge();
        const s = document.getSelection(); if (s) s.removeAllRanges();
        return true;
      } catch (e) {
        st.laeuft = false; aktualisiere(); setzeStatus("Nicht gespeichert: " + (e && e.message ? e.message : e));
        return false;
      }
    };
    leiste.addEventListener("click", (ev) => {
      const b = ev.target.closest && ev.target.closest("button[data-was]");
      if (!b || b.disabled || !st.auswahl) return;
      ev.preventDefault();
      const was = b.dataset.was;
      if (was === "abbrechen") { st.modus = null; delete pre.dataset.verschieben; aktualisiere(); return; }
      if (was === "verschieben") { st.modus = "verschieben"; pre.dataset.verschieben = "1"; aktualisiere(); platziere(); return; }
      ausfuehren(was, { text: notiz.value });
    });

    // zweiter Schritt des Verschiebens: Zielabsatz antippen
    pre.addEventListener("click", (ev) => {
      if (st.modus !== "verschieben" || !st.auswahl) return;
      if (ev.target.closest && ev.target.closest("button")) return;
      ev.preventDefault();
      let p = null;
      if (document.caretPositionFromPoint) { const c = document.caretPositionFromPoint(ev.clientX, ev.clientY); if (c) p = [c.offsetNode, c.offset]; }
      else if (document.caretRangeFromPoint) { const c = document.caretRangeFromPoint(ev.clientX, ev.clientY); if (c) p = [c.startContainer, c.startOffset]; }
      if (!p || !pre.contains(p[0])) { setzeStatus("Bitte in den Text eines Absatzes tippen"); return; }
      const pos = offsetIn(pre, p[0], p[1]), sp = st.ansicht.spannen;
      let j = sp.findIndex((s) => s[1] >= pos);
      if (j < 0) j = sp.length - 1;
      ausfuehren("verschieben", { ziel_absatz: j });
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.key !== "Escape" || leiste.hidden) return;
      if (st.modus === "verschieben") { st.modus = null; delete pre.dataset.verschieben; aktualisiere(); } else verberge();
    });
    return { verberge: verberge, element: leiste, zustand: () => st };
  }

  return { bereite, signatur, entwurf, rendere, absatzText, zeilenSchluessel, auswahlAbbilden, werkzeuge, entwuerfe, offsetIn, installiereWerkzeuge };
});
