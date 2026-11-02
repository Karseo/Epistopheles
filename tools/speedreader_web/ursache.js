/* "Ursache suchen" (P2): zu einem Absatz des fertigen Volltexts die Stelle im uebersetzten (oder, bei deutscher Quelle,
 * im extrahierten) Chunk finden. Reine Funktionen, keine Fremdbibliothek, laeuft im Browser und in Node.
 *
 * Verfahren: Text in kleingeschriebene Woerter (nur Buchstaben) zerlegen; Fussnotenmarker, Markdown, HTML und
 * Zeilenend-Silbentrennung stoeren dabei nicht. Aus dem Absatz werden bis zu drei Wortfenster (Anfang, Mitte, Ende,
 * je 6 Woerter) gebildet und in jedem Chunk gesucht. EINDEUTIG nur, wenn genau ein Chunk Fenster enthaelt und es
 * mindestens zwei der Fenster sind (bei kuerzeren Absaetzen mit nur einem Fenster: dieses eine); sonst MEHRDEUTIG
 * (mehrere Chunks oder zu wenig Belege, z. B. Absatz ueber eine Chunkgrenze) oder KEINE. Es wird nie geraten. */
(function (root, fabrik) {
  if (typeof module === "object" && module.exports) module.exports = fabrik();
  else root.Ursache = fabrik();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const FENSTER = 6, MIN_WOERTER = 4, MAX_TREFFER = 8;
  // Zeilenende-Silbentrennung "Reprä-\nsentation" oder weicher Trennstrich: zusammenfuegen, wenn danach klein weitergeht
  const LUECKE_TRENNUNG = /^(?:­|[-­][ \t]*\r?\n[ \t]*)$/;
  const KLEIN = /^\p{Ll}/u;

  /** Absatz-Markdown entschaerfen: Fussnotenmarker, HTML-Tags, Links (nur der Text bleibt). */
  function bereinige(absatz) {
    return String(absatz)
      .replace(/\[\^[^\]]*\]/g, " ")
      .replace(/<[^>]*>/g, " ")
      .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1");
  }

  /** Woerter (nur Buchstaben, klein) mit Position im Text; Silbentrennung am Zeilenende ist zusammengefuegt. */
  function tokenisiere(text) {
    const roh = [];
    for (const m of String(text).matchAll(/\p{L}+/gu)) roh.push({ w: m[0], von: m.index, bis: m.index + m[0].length });
    const aus = [];
    for (let i = 0; i < roh.length; i++) {
      let t = roh[i];
      while (i + 1 < roh.length && LUECKE_TRENNUNG.test(text.slice(t.bis, roh[i + 1].von)) && KLEIN.test(roh[i + 1].w)) {
        t = { w: t.w + roh[i + 1].w, von: t.von, bis: roh[i + 1].bis };
        i++;
      }
      aus.push({ w: t.w.toLowerCase(), von: t.von, bis: t.bis });
    }
    return aus;
  }

  /** Bis zu drei Fenster (Anfang, Mitte, Ende), als Text " w1 w2 … " mit Leerzeichen an den Raendern; ohne Doppelte. */
  function fenster(woerter) {
    if (woerter.length < MIN_WOERTER) return [];
    const n = Math.min(FENSTER, woerter.length);
    const starts = [0, Math.floor((woerter.length - n) / 2), woerter.length - n];
    const aus = [];
    for (const s of starts) {
      const f = " " + woerter.slice(s, s + n).join(" ") + " ";
      if (!aus.includes(f)) aus.push(f);
    }
    return aus;
  }

  const cache = new WeakMap();           // Quellenliste -> je Chunk {text (" w1 w2 … "), start: Position je Wort im Chunk-Text, ende}
  function indexVon(quellen) {
    let ix = cache.get(quellen);
    if (!ix || ix.laenge !== quellen.length) {
      ix = { laenge: quellen.length, chunks: new Array(quellen.length) };
      cache.set(quellen, ix);
    }
    return ix;
  }
  function chunkIndex(quellen, i) {
    const ix = indexVon(quellen);
    let c = ix.chunks[i];
    if (!c) {
      const tok = tokenisiere(typeof quellen[i] === "string" ? quellen[i] : "");
      const pos = new Array(tok.length);                 // Zeichenposition des Worts im verbundenen Text
      let p = 1;
      tok.forEach((t, k) => { pos[k] = p; p += t.w.length + 1; });
      c = { text: " " + tok.map((t) => t.w).join(" ") + " ", pos: pos, tok: tok };
      ix.chunks[i] = c;
    }
    return c;
  }
  /** Wortindex, dessen Anfang bei der Position p des verbundenen Texts liegt (binaere Suche). */
  function wortBei(pos, p) {
    let lo = 0, hi = pos.length - 1;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (pos[mid] < p) lo = mid + 1; else hi = mid; }
    return lo;
  }

  /** Ergebnis {art: "eindeutig"|"mehrdeutig"|"keine", grund, treffer: [{chunk, versatz, laenge, anzahl, fenster}]}.
   *  quellen = Liste der Chunk-Texte; optionen.bereich = [von, bis] (Chunk-Indizes, einschliesslich) begrenzt die Suche. */
  function suche(absatz, quellen, optionen) {
    const woerter = tokenisiere(bereinige(absatz)).map((t) => t.w);
    const fs = fenster(woerter);
    if (!fs.length) return { art: "keine", grund: "Der Absatz ist zu kurz für eine verlässliche Suche", treffer: [] };
    const bereich = optionen && Array.isArray(optionen.bereich) ? optionen.bereich : null;
    const von = bereich ? Math.max(0, bereich[0]) : 0, bis = bereich ? Math.min(quellen.length - 1, bereich[1]) : quellen.length - 1;
    const treffer = [];
    for (let i = von; i <= bis; i++) {
      const c = chunkIndex(quellen, i);
      let anzahl = 0, erster = null;
      for (const f of fs) {
        const p = c.text.indexOf(f);
        if (p >= 0) { anzahl++; if (erster === null || p < erster.p) erster = { p: p, f: f }; }
      }
      if (!anzahl) continue;
      const w0 = wortBei(c.pos, erster.p + 1), n = erster.f.trim().split(" ").length;
      const a = c.tok[w0], z = c.tok[Math.min(c.tok.length - 1, w0 + n - 1)];
      treffer.push({ chunk: i, versatz: a.von, laenge: z.bis - a.von, anzahl: anzahl, fenster: erster.f.trim() });
    }
    if (!treffer.length) return { art: "keine", grund: "", treffer: [] };
    treffer.sort((x, y) => (y.anzahl - x.anzahl) || (x.chunk - y.chunk));
    const noetig = Math.min(2, fs.length);
    const art = treffer.length === 1 && treffer[0].anzahl >= noetig ? "eindeutig" : "mehrdeutig";
    return { art: art, grund: "", treffer: treffer.slice(0, MAX_TREFFER) };
  }

  /** Stelle eines Wortfensters ("w1 w2 …", wie `fenster` in treffer) in einem (angezeigten) Text: {von, bis} oder null. */
  function finde(text, wortfenster) {
    const w = String(wortfenster).trim().split(" ").filter(Boolean), tok = tokenisiere(text);
    if (!w.length) return null;
    for (let i = 0; i + w.length <= tok.length; i++) {
      let gleich = true;
      for (let k = 0; k < w.length; k++) if (tok[i + k].w !== w[k]) { gleich = false; break; }
      if (gleich) return { von: tok[i].von, bis: tok[i + w.length - 1].bis };
    }
    return null;
  }

  return { bereinige, tokenisiere, fenster, suche, finde };
});
