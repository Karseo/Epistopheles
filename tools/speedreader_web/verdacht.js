/* Verdachtserkennung in Roh-Chunks (Spec Redaktion): findet Stellen, die nach Scan-Resten aussehen
 * (hart gebrochene Zeilen, Seitenzahlen, Kopf-/Fusszeilen, Fussnoten, Ueberschriften im Text,
 * Verzeichnisse, Glossare) und schlaegt eine Redaktions-Operation vor.
 * Reine Funktion, keine Fremdbibliotheken, laeuft im Browser und in Node.
 *
 * Hinweis = {art, absatz_index, zeile, zeile_bis, anfang, begruendung, vorschlag}
 * Absaetze wie in redaktion.js (Trenner: Leerzeile, leere Absaetze zaehlen nicht); zeile/zeile_bis
 * sind 0-basierte Zeilen im Absatz (zeile_bis eingeschlossen); anfang = Anker des Absatzes
 * (erste 40 Zeichen, Leerraum zusammengezogen). vorschlag = {art, parameter} im Format eines
 * Redaktions-Eintrags (verbinden, loeschen, marke). Vorschlaege aendern nichts; die Person entscheidet. */
(function (root, fabrik) {
  if (typeof module === "object" && module.exports) module.exports = fabrik();
  else root.Verdacht = fabrik();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Alle Schwellen an einer Stelle; mit verdacht_stichprobe.py kalibriert.
  const SCHWELLEN = {
    fragmentMaxZeichen: 12,        // Zeile bis zu dieser Laenge ist ein Fragment
    kopfzeileMinAbsaetze: 3,       // wortgleiche Zeile in so vielen Absaetzen = Kopf-/Fusszeile
    ueberschriftMinWoerter: 3,     // GROSSBUCHSTABEN-Zeile erst ab so vielen Woertern
    verzeichnisMinZeilen: 4,       // aufeinanderfolgende Zeilen mit Punktlinien/Seitenzahl
    glossarMinZeilen: 4,           // aufeinanderfolgende Zeilen "Begriff: Erklaerung"
    glossarBegriffMax: 40,         // laengster Begriff vor dem Doppelpunkt
    umbruchLangeZeile: 40,         // Zeile ohne Satzende vor GROSSEM Anfang: erst ab dieser Laenge Umbruch (deutsche Substantive)
    umbruchSchwachMin: 25,         // Zeile mit Satzende (; ) Anfuehrungszeichen, Abkuerzungspunkt) vor kleinem Anfang: ab dieser Laenge
    ankerLaenge: 40,
  };

  const WS = "\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
  const WS_FOLGE = new RegExp("[" + WS + "]+", "gu");
  const WS_RAND = new RegExp("^[" + WS + "]+|[" + WS + "]+$", "gu");
  const ABSATZ_TRENNER = new RegExp("\\n[" + WS + "]*\\n", "gu");
  const ZEILENENDE = /\r?\n/;

  const SATZENDE = /[.!?:;…"”“»«)'’]$/u;
  const KLEIN_ANFANG = /^\p{Ll}/u;
  const SCHWACHES_ENDE = /(?:[;)"”“»«'’]|\b(?:\p{Lu}{1,5}|\d+|Nr|Abb|Tab|Bd|vgl|ca|bzw|usw|Hrsg|Dr|Prof|St|Jr|vs|etc|[Zz]|[Bb]|[Dd]|h)\.)$/u;
  const KEIN_UMBRUCH_ANFANG = /^(?:#|:::|\||[•*+>\-–—]\s|\d+[.)]\s|\[\^|\[Q\b)/u;   // Struktur: Ueberschrift, Tabelle, Liste, Fussnotentext
  const FUSSNOTENZAHL_ANFANG = /^\d{1,3}\s/;
  const SEITENZAHL_ZEILE = /^[—–\-\s]*\d{1,4}[—–\-\s]*$/;
  const PUNKTLINIE = /\.{3,}/;
  const SEITENZAHL_ENDE = /\S\s+\d{1,4}$/;
  const FN_MARKER = /\[\^([^\]\s]+)\](?![:(])/g;   // [^n^](#...) ist ein Link auf Endnoten, kein Marker
  const FN_DEFINITION = /^\[\^([^\]\s]+)\]:/;
  const GLOSSAR_ZEILE = /^([^:[#]{1,80}):\s+\S/u;

  const trimme = (s) => s.replace(WS_RAND, "");
  const normal = (s) => trimme(s.normalize("NFC").replace(WS_FOLGE, " "));
  const anker = (s, n) => Array.from(normal(s)).slice(0, n).join("");

  /** [{text, zeilen}] je nicht-leerem Absatz, in Reihenfolge (wie redaktion.js absatzSpannen). */
  function absaetze(text) {
    const aus = [];
    let pos = 0, m;
    const stueck = (ende) => {
      const s = text.slice(pos, ende);
      if (trimme(s)) aus.push(trimme(s));
    };
    ABSATZ_TRENNER.lastIndex = 0;
    while ((m = ABSATZ_TRENNER.exec(text)) !== null) {
      stueck(m.index);
      pos = m.index + m[0].length;
    }
    stueck(text.length);
    return aus.map((t) => ({ text: t, zeilen: t.split(ZEILENENDE) }));
  }

  function woerter(zeile) { return zeile.split(/\s+/).filter(Boolean); }

  function nurGrossbuchstaben(zeile) {
    return /\p{Lu}/u.test(zeile) && !/\p{Ll}/u.test(zeile);
  }

  /** Laeufe von mindestens `min` aufeinanderfolgenden Zeilen eines Absatzes, fuer die `passt` gilt. */
  function laeufe(zeilen, passt, min) {
    const aus = [];
    let von = -1;
    for (let i = 0; i <= zeilen.length; i++) {
      const ok = i < zeilen.length && passt(zeilen[i]);
      if (ok && von < 0) von = i;
      if (!ok && von >= 0) {
        if (i - von >= min) aus.push([von, i - 1]);
        von = -1;
      }
    }
    return aus;
  }

  function pruefe(text, optionen) {
    const S = Object.assign({}, SCHWELLEN, (optionen && optionen.schwellen) || {});
    const hinweise = [];
    const liste = absaetze(String(text || ""));

    // Zeilen, die in mehreren Absaetzen wortgleich vorkommen (Kopf-/Fusszeilen).
    const vorkommen = new Map();
    liste.forEach((a) => {
      const gesehen = new Set();
      for (const z of a.zeilen) {
        const k = normal(z);
        if (!k || gesehen.has(k)) continue;
        gesehen.add(k);
        vorkommen.set(k, (vorkommen.get(k) || 0) + 1);
      }
    });

    // Fussnoten-Marker und -Definitionen des ganzen Chunks.
    const marker = new Map(), definitionen = new Map();   // id -> [{ai, zi}]
    const merke = (map, id, ai, zi) => { if (!map.has(id)) map.set(id, []); map.get(id).push({ ai: ai, zi: zi }); };
    liste.forEach((a, ai) => a.zeilen.forEach((z, zi) => {
      const t = trimme(z);
      const d = FN_DEFINITION.exec(t);
      if (d) merke(definitionen, d[1], ai, zi);
      FN_MARKER.lastIndex = 0;
      let m;
      while ((m = FN_MARKER.exec(t)) !== null) merke(marker, m[1], ai, zi);
    }));

    // Anker einmal je Absatz berechnen (sonst wird bei vielen Hinweisen der ganze Absatz immer wieder normalisiert).
    const ankerVon = (a) => (a.anker === undefined ? (a.anker = anker(a.text, S.ankerLaenge)) : a.anker);
    const neu = (art, ai, von, bis, begruendung, vorschlag) => hinweise.push({
      art: art, absatz_index: ai, zeile: von, zeile_bis: bis, anfang: ankerVon(liste[ai]),
      begruendung: begruendung, vorschlag: vorschlag,
    });
    const marke = (kategorie) => ({ art: "marke", parameter: { kategorie: kategorie } });

    liste.forEach((a, ai) => {
      const zl = a.zeilen.map(trimme);
      const belegt = new Set();                      // Zeilen in Verzeichnis/Glossar

      for (const [v, b] of laeufe(zl, (z) => PUNKTLINIE.test(z) || SEITENZAHL_ENDE.test(z), S.verzeichnisMinZeilen)) {
        neu("verzeichnis", ai, v, b, (b - v + 1) + " Zeilen mit Punktlinie oder Seitenzahl am Ende: Inhaltsverzeichnis?",
            marke("verzeichnis"));
        for (let i = v; i <= b; i++) belegt.add(i);
      }
      const glossarPasst = (z) => { const m = GLOSSAR_ZEILE.exec(z); return !!m && m[1].length <= S.glossarBegriffMax; };
      for (const [v, b] of laeufe(zl, glossarPasst, S.glossarMinZeilen)) {
        neu("glossar", ai, v, b, (b - v + 1) + " Zeilen der Form Begriff: Erklärung: Glossar?", marke("glossar"));
        for (let i = v; i <= b; i++) belegt.add(i);
      }

      zl.forEach((z, zi) => {
        if (belegt.has(zi) || !z) return;
        const mehrzeilig = zl.length > 1;

        if (mehrzeilig && (z.startsWith("#") || (nurGrossbuchstaben(z) && woerter(z).length >= S.ueberschriftMinWoerter))) {
          neu("ueberschrift-im-text", ai, zi, zi, "Überschrift mitten im Absatz", marke("ueberschrift"));
          return;
        }
        if (!FN_DEFINITION.test(z) && !z.startsWith("#")) {
          const n = vorkommen.get(normal(z)) || 0;
          const seite = SEITENZAHL_ZEILE.test(z);
          const kopf = n >= S.kopfzeileMinAbsaetze;
          if (z.length <= S.fragmentMaxZeichen || seite || kopf) {
            const grund = seite ? "Seitenzahl"
              : kopf ? "Zeile kommt in " + n + " Absätzen wortgleich vor (Kopf-/Fußzeile)"
              : "sehr kurze Zeile (höchstens " + S.fragmentMaxZeichen + " Zeichen)";
            neu("fragment", ai, zi, zi, grund, { art: "loeschen", parameter: {} });
            return;
          }
        }
        if (zi + 1 < zl.length) {
          const nz = zl[zi + 1];
          let grund = "";
          if (nz && !SATZENDE.test(z) && (KLEIN_ANFANG.test(nz) || FUSSNOTENZAHL_ANFANG.test(nz))) {
            grund = "Zeile endet ohne Satzzeichen, die nächste beginnt klein oder mit Fußnotenzahl";
          } else if (nz && !SATZENDE.test(z) && /^\p{Lu}/u.test(nz) && z.length >= S.umbruchLangeZeile
                     && !KEIN_UMBRUCH_ANFANG.test(z) && !KEIN_UMBRUCH_ANFANG.test(nz) && !nurGrossbuchstaben(z) && !nurGrossbuchstaben(nz)) {
            grund = "lange Zeile ohne Satzzeichen am Ende, die nächste beginnt groß (Substantiv?): Umbruch mitten im Satz";
          } else if (nz && KLEIN_ANFANG.test(nz) && SCHWACHES_ENDE.test(z) && z.length >= S.umbruchSchwachMin && !KEIN_UMBRUCH_ANFANG.test(z)) {
            grund = "Zeile endet mit Semikolon, Klammer, Anführungszeichen oder Abkürzung, die nächste beginnt klein";
          }
          if (grund) neu("zeile-bricht-ab", ai, zi, zi, grund, { art: "verbinden", parameter: {} });
        }
      });
    });

    for (const [id, orte] of marker) {
      if (definitionen.has(id)) continue;
      for (const o of orte) neu("fussnote", o.ai, o.zi, o.zi, "Fußnotenmarker [^" + id + "] ohne Definition im Chunk", marke("fussnote"));
    }
    for (const [id, orte] of definitionen) {
      if (marker.has(id)) continue;
      for (const o of orte) neu("fussnote", o.ai, o.zi, o.zi, "Fußnotendefinition [^" + id + "]: ohne Marker im Chunk", marke("fussnote"));
    }

    hinweise.sort((x, y) => x.absatz_index - y.absatz_index || x.zeile - y.zeile);
    return hinweise;
  }

  return { pruefe, SCHWELLEN };
});
