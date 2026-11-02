/* Fussnotenanalyse fuer den fertigen Volltext (P2): Marker [^id], Definitionen "[^id]: Text" am Zeilenanfang,
 * Hinweise bei fehlender Zuordnung. Gegenstueck zu tools/redaktion/fussnoten.py (gleiche Regeln, gleiche
 * Vektoren in tools/redaktion/testvektoren_fussnoten.json). Reine Funktionen, keine Fremdbibliothek.
 *
 * absatz_index / zeile / vorkommen sind genau die Ziele, die redaktion.js (Art "fussnote") versteht.
 * Andere Fussnotenkonventionen werden nur gemeldet ("andere-konvention"), nie bearbeitet. */
(function (root, fabrik) {
  if (typeof module === "object" && module.exports) module.exports = fabrik(require("./redaktion.js"));
  else root.Fussnoten = fabrik(root.Redaktion);
})(typeof self !== "undefined" ? self : this, function (R) {
  "use strict";

  const KENNUNG_ZEICHEN = "[^\\]\\[ \\t\\r\\n\\f\\v\\u00a0]";
  const MARKER = "\\[\\^(" + KENNUNG_ZEICHEN + "+)\\](?!:)";
  const DEFINITION = new RegExp("^\\[\\^(" + KENNUNG_ZEICHEN + "+)\\]:", "u");
  const NUMMERZEILE = /^\*?\d{1,3}[.)]?[ \t ]+\S/;
  const ZEILENENDE = /\r?\n/;
  const LETZTE_ABSAETZE = 10, MIN_NUMMERZEILEN = 3;
  const TEXTE = {
    "marker-ohne-definition": (id) => "Verweis [^" + id + "] hat keinen Fußnotentext",
    "definition-ohne-marker": (id) => "Fußnotentext [^" + id + "] wird nirgends verwiesen",
    "doppelte-definition": (id) => "Fußnotentext [^" + id + "] ist mehrfach vorhanden",
    "andere-konvention": () => "Fußnoten scheinen nicht als [^Nr] ausgezeichnet zu sein (Zeilen mit Nummer am Kapitelende)",
  };

  const hinweis = (art, id, absatz, zeile) => ({ art: art, id: id, absatz_index: absatz, zeile: zeile, begruendung: TEXTE[art](id) });

  /** {marker, definitionen, hinweise, bilanz}; Felder siehe fussnoten.py. */
  function analysiere(text) {
    const absaetze = R.absatzSpannen(text).map(([a, b]) => text.slice(a, b).split(ZEILENENDE));
    const marker = [], definitionen = [];
    absaetze.forEach((zeilen, ai) => {
      const gezaehlt = new Map();
      let inDef = false;
      zeilen.forEach((zeile, zi) => {
        const d = DEFINITION.exec(zeile);
        if (d) { inDef = true; definitionen.push({ id: d[1], absatz_index: ai, zeile: zi }); }
        for (const m of zeile.matchAll(new RegExp(MARKER, "gu"))) {
          const k = m[1], n = gezaehlt.get(k) || 0;
          marker.push({ id: k, absatz_index: ai, zeile: zi, vorkommen: n, in_definition: inDef });
          gezaehlt.set(k, n + 1);
        }
      });
    });

    const mitMarker = new Set(marker.map((m) => m.id)), mitDefinition = new Set(definitionen.map((d) => d.id));
    const ereignisse = [];
    const gesehenMarker = new Set();
    for (const m of marker) {
      if (!mitDefinition.has(m.id) && !gesehenMarker.has(m.id)) {
        ereignisse.push([m.absatz_index, m.zeile, ereignisse.length, hinweis("marker-ohne-definition", m.id, m.absatz_index, m.zeile)]);
      }
      gesehenMarker.add(m.id);
    }
    const gesehenDef = new Set();
    for (const d of definitionen) {
      let art = null;
      if (gesehenDef.has(d.id)) art = "doppelte-definition";
      else if (!mitMarker.has(d.id)) art = "definition-ohne-marker";
      gesehenDef.add(d.id);
      if (art) ereignisse.push([d.absatz_index, d.zeile, ereignisse.length, hinweis(art, d.id, d.absatz_index, d.zeile)]);
    }
    ereignisse.sort((x, y) => (x[0] - y[0]) || (x[1] - y[1]) || (x[2] - y[2]));
    const hinweise = ereignisse.map((e) => e[3]);

    if (!definitionen.length) {
      const treffer = [];
      for (let ai = Math.max(0, absaetze.length - LETZTE_ABSAETZE); ai < absaetze.length; ai++) {
        absaetze[ai].forEach((zeile, zi) => { if (!zeile.startsWith("#") && NUMMERZEILE.test(zeile)) treffer.push([ai, zi]); });
      }
      if (treffer.length >= MIN_NUMMERZEILEN) hinweise.push(hinweis("andere-konvention", "", treffer[0][0], treffer[0][1]));
    }
    return { marker: marker, definitionen: definitionen, hinweise: hinweise,
             bilanz: { marker: marker.length, definitionen: definitionen.length } };
  }

  function zaehle(liste) {
    const z = new Map();
    for (const e of liste) z.set(e.id, (z.get(e.id) || 0) + 1);
    return z;
  }

  function diff(x, y) {
    const zx = zaehle(x), zy = zaehle(y), aus = {};
    for (const k of new Set([...zx.keys(), ...zy.keys()])) {
      const a = zx.get(k) || 0, b = zy.get(k) || 0;
      if (a !== b) aus[k] = [a, b];
    }
    return aus;
  }

  /** Unterschied der Fussnoten zweier Fassungen: {marker, definitionen, neue_hinweise}; siehe fussnoten.py. */
  function bilanz(vorher, nachher) {
    const a = analysiere(vorher), b = analysiere(nachher);
    const bekannt = new Set(a.hinweise.map((h) => h.art + "\u0000" + h.id));
    return { marker: diff(a.marker, b.marker), definitionen: diff(a.definitionen, b.definitionen),
             neue_hinweise: b.hinweise.filter((h) => !bekannt.has(h.art + "\u0000" + h.id)) };
  }

  return { analysiere, bilanz };
});
