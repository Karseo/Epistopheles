/* ZIP- und EPUB-Leser fuer die Korrekturansicht (korrektur.html), ohne Fremdbibliothek.
 * oeffneZip() braucht nur DecompressionStream und laeuft auch in Node (Tests).
 * oeffneEpub() braucht DOMParser, also den Browser: liest Container und OPF,
 * liefert die Spine-Abschnitte und baut je Abschnitt ein eigenstaendiges
 * HTML-Dokument (Bilder als data:-URLs, Stylesheets inline, keine Skripte),
 * das in einem iframe per srcdoc angezeigt wird. */
(function (root, fabrik) {
  if (typeof module === "object" && module.exports) module.exports = fabrik();
  else root.Epub = fabrik();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const dekoder = new TextDecoder("utf-8");
  const u16 = (v, o) => v.getUint16(o, true);
  const u32 = (v, o) => v.getUint32(o, true);

  async function entpacke(roh) {
    const strom = new Blob([roh]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
    return new Uint8Array(await new Response(strom).arrayBuffer());
  }

  /** ZIP aus einem ArrayBuffer: {namen(), hat(n), lies(n) -> Uint8Array, text(n) -> string}. */
  function oeffneZip(buffer) {
    const bytes = new Uint8Array(buffer);
    const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    let ende = -1;
    for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 22 - 65535); i--) {
      if (u32(v, i) === 0x06054b50) { ende = i; break; }
    }
    if (ende < 0) throw new Error("Keine ZIP-/EPUB-Datei (Dateiende nicht gefunden).");
    const anzahl = u16(v, ende + 10);
    let p = u32(v, ende + 16);
    const eintraege = new Map();
    for (let k = 0; k < anzahl; k++) {
      if (u32(v, p) !== 0x02014b50) throw new Error("ZIP-Verzeichnis beschädigt.");
      const methode = u16(v, p + 10), komp = u32(v, p + 20);
      const nl = u16(v, p + 28), el = u16(v, p + 30), cl = u16(v, p + 32), lokal = u32(v, p + 42);
      eintraege.set(dekoder.decode(bytes.subarray(p + 46, p + 46 + nl)), { methode, komp, lokal });
      p += 46 + nl + el + cl;
    }
    async function lies(name) {
      const e = eintraege.get(name);
      if (!e) throw new Error("Nicht im Archiv: " + name);
      const start = e.lokal + 30 + u16(v, e.lokal + 26) + u16(v, e.lokal + 28);
      const roh = bytes.subarray(start, start + e.komp);
      if (e.methode === 0) return roh;
      if (e.methode === 8) return entpacke(roh);
      throw new Error(`ZIP-Methode ${e.methode} wird nicht unterstützt (${name}).`);
    }
    return {
      namen: () => [...eintraege.keys()],
      hat: (n) => eintraege.has(n),
      lies,
      text: async (n) => dekoder.decode(await lies(n)),
    };
  }

  /** Pfad `ziel` (relativ zur Datei `basisDatei`) im Archiv; ohne Fragment, %-dekodiert. */
  function pfadAufloesen(basisDatei, ziel) {
    ziel = ziel.split("#")[0];
    try { ziel = decodeURIComponent(ziel); } catch { /* unveraendert */ }
    if (ziel.startsWith("/")) return ziel.slice(1);
    const teile = basisDatei.split("/").slice(0, -1);
    for (const t of ziel.split("/")) {
      if (t === "..") teile.pop(); else if (t && t !== ".") teile.push(t);
    }
    return teile.join("/");
  }

  const MIME = { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif", svg: "image/svg+xml", webp: "image/webp" };

  function alsDataUrl(bytes, typ) {
    let s = "";
    for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return `data:${typ};base64,${btoa(s)}`;
  }

  /** Schriftdateien, Importe und externe url()-Verweise fallen weg: im srcdoc nicht ladbar. */
  function bereinigeCss(css) {
    return css
      .replace(/@font-face\s*\{[^}]*\}/gi, "")
      .replace(/@import[^;]*;/gi, "")
      .replace(/url\(\s*(?!['"]?data:)[^)]*\)/gi, 'url("")');
  }

  const BASIS_CSS = "html{background:#fff;color:#111}body{max-width:42em;margin:0 auto;padding:1em 1.3em 3em;"
    + "font-family:'Noto Serif',Georgia,serif;line-height:1.6;overflow-wrap:break-word}img,svg{max-width:100%;height:auto}"
    + "mark{background:#ffd54a;color:#000}";

  async function oeffneEpub(buffer) {
    const zip = oeffneZip(buffer);
    const dp = new DOMParser();
    const xml = (s) => dp.parseFromString(s, "application/xml");
    const container = xml(await zip.text("META-INF/container.xml"));
    const wurzel = container.querySelector("rootfile");
    if (!wurzel) throw new Error("EPUB ohne Paketdatei (container.xml).");
    const opfPfad = wurzel.getAttribute("full-path");
    const opf = xml(await zip.text(opfPfad));

    const manifest = new Map();
    for (const it of opf.querySelectorAll("manifest > item")) {
      manifest.set(it.getAttribute("id"), {
        href: pfadAufloesen(opfPfad, it.getAttribute("href") || ""),
        typ: it.getAttribute("media-type") || "",
        eig: it.getAttribute("properties") || "",
      });
    }
    const spine = [...opf.querySelectorAll("spine > itemref")]
      .map((r) => manifest.get(r.getAttribute("idref"))).filter((it) => it && /html/.test(it.typ));
    if (!spine.length) throw new Error("EPUB ohne lesbare Abschnitte.");

    // Titel der Abschnitte aus dem Inhaltsverzeichnis (nav.xhtml oder toc.ncx)
    const titel = new Map();
    const merke = (basis, href, text) => {
      const pfad = pfadAufloesen(basis, href || "");
      text = (text || "").replace(/\s+/g, " ").trim();
      if (pfad && text && !titel.has(pfad)) titel.set(pfad, text);
    };
    try {
      const nav = [...manifest.values()].find((it) => /\bnav\b/.test(it.eig));
      if (nav) {
        const d = dp.parseFromString(await zip.text(nav.href), "text/html");
        d.querySelectorAll("nav a[href]").forEach((a) => merke(nav.href, a.getAttribute("href"), a.textContent));
      }
      const ncx = [...manifest.values()].find((it) => /ncx/.test(it.typ));
      if (ncx && !titel.size) {
        const d = xml(await zip.text(ncx.href));
        d.querySelectorAll("navPoint").forEach((n) => {
          const c = n.querySelector("content"), t = n.querySelector("navLabel > text");
          if (c && t) merke(ncx.href, c.getAttribute("src"), t.textContent);
        });
      }
    } catch { /* ohne Inhaltsverzeichnis: Dateinamen */ }

    const abschnitte = spine.map((it, i) => ({
      href: it.href,
      titel: titel.get(it.href) || `Abschnitt ${i + 1} (${it.href.split("/").pop()})`,
    }));
    const typVon = new Map([...manifest.values()].map((it) => [it.href, it.typ]));
    const bilder = new Map();

    async function bildUrl(basis, ziel) {
      if (!ziel || /^(data:|https?:|#)/i.test(ziel)) return ziel;
      const pfad = pfadAufloesen(basis, ziel);
      if (!bilder.has(pfad)) {
        let url = "";
        try {
          const ext = pfad.split(".").pop().toLowerCase();
          url = alsDataUrl(await zip.lies(pfad), typVon.get(pfad) || MIME[ext] || "application/octet-stream");
        } catch { /* Bild fehlt im Archiv */ }
        bilder.set(pfad, url);
      }
      return bilder.get(pfad);
    }

    async function dokument(i) {
      const href = abschnitte[i].href;
      const quelle = await zip.text(href);
      let doc = dp.parseFromString(quelle, "application/xhtml+xml");
      if (doc.querySelector("parsererror")) doc = dp.parseFromString(quelle, "text/html");
      doc.querySelectorAll("script, iframe, object, embed, audio, video").forEach((e) => e.remove());
      const css = [];
      for (const l of [...doc.querySelectorAll('link[rel~="stylesheet"]')]) {
        try { css.push(bereinigeCss(await zip.text(pfadAufloesen(href, l.getAttribute("href") || "")))); } catch { /* fehlt */ }
        l.remove();
      }
      doc.querySelectorAll("style").forEach((s) => css.push(bereinigeCss(s.textContent)));
      for (const img of [...doc.querySelectorAll("img[src]")]) img.setAttribute("src", await bildUrl(href, img.getAttribute("src")));
      for (const im of [...doc.querySelectorAll("image")]) {
        for (const attr of ["href", "xlink:href"]) {
          if (im.hasAttribute(attr)) im.setAttribute(attr, await bildUrl(href, im.getAttribute(attr)));
        }
      }
      const body = doc.body || doc.documentElement;
      return `<!doctype html><html lang="en"><head><meta charset="utf-8"><style>${BASIS_CSS}</style>`
        + `<style>${css.join("\n")}</style></head><body>${body.innerHTML}</body></html>`;
    }

    const textCache = new Map();
    /** Sichtbarer Text eines Abschnitts, Leerraum zusammengezogen (fuer die Suche). */
    async function text(i) {
      if (!textCache.has(i)) {
        const d = dp.parseFromString(await zip.text(abschnitte[i].href), "text/html");
        textCache.set(i, (d.body ? d.body.textContent : "").replace(/\s+/g, " "));
      }
      return textCache.get(i);
    }

    /** Index des ersten Abschnitts ab `ab` (zyklisch), der `nadel` enthaelt; sonst -1. */
    async function finde(nadel, ab = 0) {
      const n = nadel.replace(/\s+/g, " ").trim().toLowerCase();
      if (!n) return -1;
      for (let k = 0; k < abschnitte.length; k++) {
        const i = (ab + k) % abschnitte.length;
        if ((await text(i)).toLowerCase().includes(n)) return i;
      }
      return -1;
    }

    return { abschnitte, dokument, text, finde };
  }

  return { oeffneZip, pfadAufloesen, oeffneEpub, bereinigeCss };
});
