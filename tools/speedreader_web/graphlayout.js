/* Anordnung des Fokusnetzes (Plan 2026-11-03, Task 6): reine Funktion ohne DOM und ohne Zufall (gleiche Eingabe, gleiche Anordnung).
 *
 * Start: der Fokus in der Mitte (fest), Ring 1 gleichmaessig auf einer inneren Ellipse, Ring 2 auf einer aeusseren Ellipse und
 * dort in der Naehe des Ring-1-Knotens, ueber den er kam (`ueber`). Danach eine feste Zahl Schritte einer Kraeftberechnung:
 * Abstossung aller Paare, Federn der Kanten und zum `ueber`-Knoten, Rueckstellung zur Startlage und sanft auf die Ringellipse,
 * Begrenzung auf die Flaeche, abkuehlende Schrittweite; zuletzt eine Entzerrung, damit sich bei genug Platz nichts beruehrt.
 * Die Ellipsen folgen dem Seitenverhaeltnis der Flaeche. Radien: Fokus gross, Ring 1 mittel, Ring 2 klein (in Pixeln). */
(function (root, fabrik) {
  if (typeof module === "object" && module.exports) module.exports = fabrik();
  else root.Graphlayout = fabrik();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const RING = { 1: 0.55, 2: 0.95 };                   // Anteil der nutzbaren Halbachse
  const ANKER_1 = 0.6, ANKER_2 = 1.0;                   // Rueckstellung zur Startlage: haelt Ring 2 bei seinem Ring-1-Knoten
  const istObjekt = (x) => x !== null && typeof x === "object" && !Array.isArray(x);

  /** FNV-1a (32 Bit) der Id: stabile Startdrehung ohne Zufall. */
  function hash(text) {
    let h = 0x811c9dc5;
    for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
    return h >>> 0;
  }

  /** {positionen: {id: {x, y}}, radius: {id: r}} fuer `fokus` = {knoten: [{id, ring, ueber?}], kanten: [{von, nach, art?, wert?}]}.
   *  optionen: iterationen (120), rand (24 px Abstand zum Flaechenrand), r0/r1/r2 (Knotenradien 16/11/6), luecke (6 px Mindestabstand). */
  function ordne(fokus, breite, hoehe, optionen) {
    const o = Object.assign({ iterationen: 120, rand: 24, r0: 16, r1: 11, r2: 6, luecke: 6 }, optionen || {});
    const b = Math.max(120, Number(breite) || 0), h = Math.max(100, Number(hoehe) || 0);
    const gesehen = new Set(), knoten = [];
    for (const k of istObjekt(fokus) && Array.isArray(fokus.knoten) ? fokus.knoten : []) {
      if (istObjekt(k) && typeof k.id === "string" && !gesehen.has(k.id)) { gesehen.add(k.id); knoten.push(k); }
    }
    const n = knoten.length;
    if (!n) return { positionen: {}, radius: {} };
    const cx = b / 2, cy = h / 2, hx = Math.max(10, b / 2 - o.rand), hy = Math.max(10, h / 2 - o.rand), kurz = Math.min(hx, hy);
    const ring = (k) => (k.ring === 0 ? 0 : k.ring === 2 ? 2 : k.ring === 1 ? 1 : 2);        // Unbekanntes verhaelt sich wie Ring 2
    const radiusVon = (r) => (r === 0 ? o.r0 : r === 1 ? o.r1 : o.r2);
    const idx = new Map(knoten.map((k, i) => [k.id, i]));
    const rg = knoten.map(ring);
    const r = rg.map(radiusVon);
    const x = new Array(n), y = new Array(n), winkel = new Array(n).fill(0);
    const mitteIdx = rg.indexOf(0);
    const start = (hash(mitteIdx >= 0 ? knoten[mitteIdx].id : knoten[0].id) % 3600) / 3600 * 2 * Math.PI;
    const setze = (i, w, anteil) => { winkel[i] = w; x[i] = cx + anteil * hx * Math.cos(w); y[i] = cy + anteil * hy * Math.sin(w); };
    const ring1 = [], ring2 = [];
    knoten.forEach((k, i) => { if (rg[i] === 0 && i === mitteIdx) { x[i] = cx; y[i] = cy; } else if (rg[i] === 1 || rg[i] === 0) ring1.push(i); else ring2.push(i); });
    ring1.forEach((i, j) => setze(i, start + (2 * Math.PI * j) / ring1.length, RING[1]));
    const kinder = new Map();                                                                    // Ring-1-Index -> Ring-2-Indizes
    const lose = [];
    for (const i of ring2) {
      const u = idx.get(knoten[i].ueber);
      if (u !== undefined && ring1.includes(u)) { if (!kinder.has(u)) kinder.set(u, []); kinder.get(u).push(i); } else lose.push(i);
    }
    for (const [u, liste] of kinder) {
      const schritt = Math.min(0.32, (2 * Math.PI) / (ring1.length * Math.max(1, liste.length)) * 0.8);
      liste.forEach((i, j) => setze(i, winkel[u] + (j - (liste.length - 1) / 2) * schritt, RING[2]));
    }
    lose.forEach((i, j) => setze(i, start + Math.PI / Math.max(1, ring1.length) + (2 * Math.PI * j) / Math.max(1, lose.length), RING[2]));
    const sx = x.slice(), sy = y.slice();
    const feste = new Set(rg.map((v, i) => (v === 0 && i === mitteIdx ? i : -1)).filter((i) => i >= 0));
    const kanten = [];
    for (const k of istObjekt(fokus) && Array.isArray(fokus.kanten) ? fokus.kanten : []) {
      if (!istObjekt(k) || !idx.has(k.von) || !idx.has(k.nach) || k.von === k.nach) continue;
      const a = idx.get(k.von), c = idx.get(k.nach);
      kanten.push([a, c, (rg[a] === 0 || rg[c] === 0) ? 0.55 * kurz : 0.45 * kurz]);
    }
    const ueber = knoten.map((k, i) => (rg[i] === 2 && idx.has(k.ueber) ? idx.get(k.ueber) : -1));

    const begrenze = (i) => {
      const lox = o.rand + r[i], hix = b - o.rand - r[i], loy = o.rand + r[i], hiy = h - o.rand - r[i];
      x[i] = hix < lox ? cx : Math.min(hix, Math.max(lox, x[i]));
      y[i] = hiy < loy ? cy : Math.min(hiy, Math.max(loy, y[i]));
    };
    const k2 = (hx * hy * 4 / n) * 0.25;                                                          // Abstossung ~ k^2 / d
    const dx = new Array(n), dy = new Array(n);
    for (let t = 0; t < o.iterationen; t++) {
      const temp = (1 - t / o.iterationen) * 0.2 * kurz + 0.5;
      dx.fill(0); dy.fill(0);
      for (let i = 0; i < n; i++) {
        for (let j = i + 1; j < n; j++) {
          let ex = x[i] - x[j], ey = y[i] - y[j], d = Math.hypot(ex, ey);
          if (d < 0.01) { const w = ((i * 7 + j * 13) % 360) * Math.PI / 180; ex = Math.cos(w); ey = Math.sin(w); d = 0.01; }
          const f = k2 / (d * d);
          dx[i] += (ex / d) * f * d; dy[i] += (ey / d) * f * d; dx[j] -= (ex / d) * f * d; dy[j] -= (ey / d) * f * d;
        }
      }
      for (const [a, c, laenge] of kanten) {
        const ex = x[c] - x[a], ey = y[c] - y[a], d = Math.hypot(ex, ey) || 0.01, f = (d - laenge) * 0.05;
        dx[a] += (ex / d) * f; dy[a] += (ey / d) * f; dx[c] -= (ex / d) * f; dy[c] -= (ey / d) * f;
      }
      for (let i = 0; i < n; i++) {
        if (ueber[i] >= 0) {                                                                      // Ring 2 bei seinem Ring-1-Knoten halten
          const u = ueber[i], ex = x[u] - x[i], ey = y[u] - y[i], d = Math.hypot(ex, ey) || 0.01, f = (d - 0.4 * kurz) * 0.04;
          dx[i] += (ex / d) * f; dy[i] += (ey / d) * f;
        }
        if (!feste.has(i)) { const a = rg[i] === 2 ? ANKER_2 : ANKER_1; dx[i] += (sx[i] - x[i]) * a; dy[i] += (sy[i] - y[i]) * a; }
        if (rg[i] > 0 && !feste.has(i)) {                                                         // sanft auf die Ringellipse zurueck
          const ex = (x[i] - cx) / hx, ey = (y[i] - cy) / hy, rho = Math.hypot(ex, ey) || 0.01, soll = RING[rg[i]] || RING[2];
          const f = (soll - rho) * 0.12 * kurz;
          dx[i] += (ex / rho) * f * hx / kurz; dy[i] += (ey / rho) * f * hy / kurz;
        }
      }
      for (let i = 0; i < n; i++) {
        if (feste.has(i)) continue;
        const l = Math.hypot(dx[i], dy[i]) || 1, s = Math.min(l, temp);
        x[i] += (dx[i] / l) * s; y[i] += (dy[i] / l) * s;
        begrenze(i);
      }
    }
    // Entzerrung: nichts beruehrt sich, solange die Flaeche es hergibt (der feste Fokus weicht nie)
    for (let durchgang = 0; durchgang < 80; durchgang++) {
      let bewegt = false;
      for (let i = 0; i < n; i++) {
        for (let j = i + 1; j < n; j++) {
          const mind = r[i] + r[j] + 1;
          let ex = x[i] - x[j], ey = y[i] - y[j], d = Math.hypot(ex, ey);
          if (d >= mind) continue;
          if (d < 0.01) { const w = ((i * 11 + j * 17) % 360) * Math.PI / 180; ex = Math.cos(w); ey = Math.sin(w); d = 1; }
          const schub = (mind - d) / d, fi = feste.has(i), fj = feste.has(j);
          const ai = fi ? 0 : fj ? 1 : 0.5, aj = fj ? 0 : fi ? 1 : 0.5;
          x[i] += ex * schub * ai; y[i] += ey * schub * ai; x[j] -= ex * schub * aj; y[j] -= ey * schub * aj;
          begrenze(i); begrenze(j);
          bewegt = true;
        }
      }
      if (!bewegt) break;
    }
    const positionen = {}, radius = {};
    knoten.forEach((k, i) => { positionen[k.id] = { x: Math.round(x[i] * 10) / 10, y: Math.round(y[i] * 10) / 10 }; radius[k.id] = r[i]; });
    return { positionen: positionen, radius: radius };
  }

  return { ordne: ordne };
});
