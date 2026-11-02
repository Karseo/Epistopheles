/* Zerlegt den Markdown-Volltext eines Kapitels (quelle\*.md) in Anzeige-Bloecke,
 * ohne DOM und ohne HTML-Ausgabe: index.html baut daraus Elemente per
 * textContent. Bewusst klein; die Quellen enthalten nur Ueberschriften, Absaetze,
 * Listen, Zitate, Seitenmarken (## Seite N), Fussnoten und etwas Roh-HTML
 * (<figure>, <span>, <img>) aus den EPUBs. */
(function (root, fabrik) {
  if (typeof module === "object" && module.exports) module.exports = fabrik();
  else root.Lesetext = fabrik();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const FUSSNOTE_DEF = /^\[\^([^\]]+)\]:\s*(.*)$/;
  const SEITE = /^##\s+Seite\s+(\S+)\s*$/i;
  const UEBERSCHRIFT = /^(#{1,6})\s+(.*?)\s*#*\s*$/;
  const LISTE = /^\s*(?:[-*+]|\d+[.)])\s+(.*)$/;
  const LINIE = /^\s*([-*_])(?:\s*\1){2,}\s*$/;
  const NUR_TAGS = /^(?:\s*<[^>]*>)+\s*$/;
  const BILD_ALT = /<img\b[^>]*\balt="([^"]*)"/i;

  // Auszeichnungen innerhalb einer Zeile; Reihenfolge der Alternativen ist wichtig.
  const INLINE = new RegExp(
    [
      "\\\\([*_\\[\\]\\\\])",                                          // 1: maskiertes Zeichen
      "\\[\\^([^\\]]+)\\]",                                            // 2: Fussnotenmarke
      "\\[([^\\]]*)\\]\\([^)]*\\)",                                    // 3: Link -> nur Text
      "\\*\\*([^*]+)\\*\\*",                                           // 4: fett
      "\\*([^*\\n]+)\\*",                                              // 5: kursiv
      "(?<![\\p{L}\\p{N}_])_([^_\\n]+)_(?![\\p{L}\\p{N}_])",           // 6: kursiv mit _ (nicht im Wort)
    ].join("|"),
    "gu"
  );

  const ohneTags = (s) => s.replace(/<[^>]*>/g, "");

  /** Text -> Segmente [{t, b?, em?, fn?}]. fn = Kennung einer Fussnotenmarke. */
  function inline(text) {
    const segmente = [];
    let ende = 0;
    const roh = ohneTags(text);
    for (const m of roh.matchAll(INLINE)) {
      if (m.index > ende) segmente.push({ t: roh.slice(ende, m.index) });
      if (m[1] !== undefined) segmente.push({ t: m[1] });
      else if (m[2] !== undefined) segmente.push({ t: "", fn: m[2] });
      else if (m[3] !== undefined) segmente.push({ t: m[3] });
      else if (m[4] !== undefined) segmente.push({ t: m[4], b: true });
      else segmente.push({ t: m[5] !== undefined ? m[5] : m[6], em: true });
      ende = m.index + m[0].length;
    }
    if (ende < roh.length) segmente.push({ t: roh.slice(ende) });
    return segmente;
  }

  /** Markdown -> Bloecke:
   *  {typ:"h", stufe, text} | {typ:"p"|"li"|"zitat", text} | {typ:"seite", text}
   *  {typ:"bild", text} | {typ:"fn", id, text} | {typ:"hr"} */
  function parse(markdown) {
    const bloecke = [];
    let absatz = [];        // Zeilen des laufenden Absatzes
    let zitat = [];

    const schliesse = () => {
      if (absatz.length) bloecke.push({ typ: "p", text: absatz.join(" ") });
      if (zitat.length) bloecke.push({ typ: "zitat", text: zitat.join(" ") });
      absatz = []; zitat = [];
    };

    for (const rohzeile of String(markdown || "").replace(/\r\n?/g, "\n").split("\n")) {
      let zeile = rohzeile.trim();
      if (!zeile) { schliesse(); continue; }

      const bild = BILD_ALT.exec(zeile);
      if (bild) { schliesse(); if (bild[1].trim()) bloecke.push({ typ: "bild", text: bild[1].trim() }); continue; }
      if (NUR_TAGS.test(zeile)) { schliesse(); continue; }
      zeile = ohneTags(zeile).trim();
      if (!zeile) { schliesse(); continue; }

      let m;
      if ((m = SEITE.exec(zeile))) { schliesse(); bloecke.push({ typ: "seite", text: `Seite ${m[1]}` }); continue; }
      if ((m = UEBERSCHRIFT.exec(zeile))) {
        schliesse();
        const text = ohneTags(m[2]).trim();
        if (text) bloecke.push({ typ: "h", stufe: m[1].length, text });
        continue;
      }
      if ((m = FUSSNOTE_DEF.exec(zeile))) { schliesse(); bloecke.push({ typ: "fn", id: m[1], text: m[2] }); continue; }
      if (LINIE.test(zeile)) { schliesse(); bloecke.push({ typ: "hr" }); continue; }
      if (zeile.startsWith(">")) {
        if (absatz.length) schliesse();
        zitat.push(zeile.replace(/^>+\s?/, ""));
        continue;
      }
      if ((m = LISTE.exec(zeile))) { schliesse(); bloecke.push({ typ: "li", text: m[1] }); continue; }
      if (zitat.length) schliesse();
      absatz.push(zeile);
    }
    schliesse();
    return bloecke;
  }

  /** Kennungen der Fussnoten in Reihenfolge ihres ersten Vorkommens -> Nummer. */
  function fussnotenNummern(bloecke) {
    const nummern = new Map();
    for (const b of bloecke) {
      if (b.typ === "fn" || !b.text) continue;
      for (const s of inline(b.text)) if (s.fn !== undefined && !nummern.has(s.fn)) nummern.set(s.fn, nummern.size + 1);
    }
    for (const b of bloecke) if (b.typ === "fn" && !nummern.has(b.id)) nummern.set(b.id, nummern.size + 1);
    return nummern;
  }

  return { parse, inline, fussnotenNummern };
});
