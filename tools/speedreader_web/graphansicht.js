/* Darstellung des Fokusnetzes (Plan 2026-11-03, Task 7): Canvas wie im Referenzbild (dunkler Grund, Fokus mit Hof in der Mitte,
 * beschriftete Nachbarn mit dünnen Linien, weiter entfernte Knoten klein und verblasst ohne Linie), Berührung (Tippen, Ziehen,
 * Zwei-Finger-Zoom, Mausrad), Filter je Kantenart, Detailleiste mit Beleg, gleichwertige Liste. Keine Fremdbibliothek.
 *
 * Reine Teile (in Node testbar): trifft, kuerze, beschriftungen, uebergang, werkFarbe, zeichne (gegen jedes Canvas-2D-artige Objekt).
 * `installiere` baut die Oberflaeche in ein Element und nutzt verbindungen.js (Ausschnitt, Liste) und graphlayout.js (Anordnung). */
(function (root, fabrik) {
  if (typeof module === "object" && module.exports) module.exports = fabrik(require("./verbindungen.js"), require("./graphlayout.js"));
  else root.Graphansicht = fabrik(root.Verbindungen, root.Graphlayout);
})(typeof self !== "undefined" ? self : this, function (V, GL) {
  "use strict";

  const SCHRIFT = 12, ZEILE = 16, MAX_BREITE = 150, MIN_TREFFER = 22;          // Trefferflaeche: Radius 22 px = 44 px Durchmesser
  const ZOOM_MIN = 0.6, ZOOM_MAX = 2.5, WISCHEN = 8;
  const ARTEN = [["aehnlich", "Ähnlich"], ["thema", "Themen"], ["querverweis", "Querverweise"], ["werk", "Werk"]];
  const TYP_NAME = { kapitel: "Kapitel", thema: "Thema", werk: "Werk" };
  const FARB_TONE = [205, 28, 145, 285, 52, 335, 100, 0];

  // ---- reine Teile ------------------------------------------------------------------------------------------------

  /** Id des Knotens an der Bildschirmposition (x, y) oder null. Position = Weltposition * Zoom + Verschiebung; die Trefferflaeche hat
   *  mindestens `mindest` px Radius (Standard 22 = 44 px), auch bei kleinem Knoten und kleinem Zoom; der naechste Knoten gewinnt. */
  function trifft(positionen, radius, t, x, y, mindest) {
    const m = mindest === undefined ? MIN_TREFFER : mindest;
    let bester = null, abstand = Infinity;
    for (const id in positionen) {
      const p = positionen[id], d = Math.hypot(x - (p.x * t.k + t.tx), y - (p.y * t.k + t.ty));
      if (d <= Math.max(m, (radius[id] || 0) * t.k) && d < abstand) { bester = id; abstand = d; }
    }
    return bester;
  }

  /** Text auf `maxPx` Breite kuerzen (mit "…"); passt nichts mehr, bleibt "" uebrig. `messe(text)` liefert die Breite. */
  function kuerze(text, maxPx, messe) {
    text = String(text || "");
    if (!text || messe(text) <= maxPx) return text;
    let lo = 0, hi = text.length;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (messe(text.slice(0, mid).trimEnd() + "…") <= maxPx) lo = mid; else hi = mid - 1;
    }
    return lo > 0 ? text.slice(0, lo).trimEnd() + "…" : "";
  }

  /** Beschriftungen: {id: {x, y, w, h, text, ausrichtung: "links"|"rechts"|"mitte"}} (Rechteck oben links, in Weltkoordinaten). Der Fokus
   *  steht unter seinem Knoten, Ring-1-Knoten neben ihrem (nach aussen, sonst darunter/darueber), Ring 2 hat keine (ausser `zusaetzlich`).
   *  Kein Text ueberdeckt einen Knoten oder einen anderen Text und keiner ragt aus der Flaeche; was nicht passt, wird gekuerzt, sonst weggelassen
   *  (nur der Fokus bekommt immer eine, notfalls in die Flaeche geschoben). */
  function beschriftungen(knoten, positionen, radius, flaeche, messe, optionen) {
    const o = Object.assign({ maxBreite: MAX_BREITE, hoehe: ZEILE, rand: 2, zusaetzlich: [] }, optionen || {});
    const B = flaeche.breite, H = flaeche.hoehe, h = o.hoehe;
    const gesetzt = [], aus = {};
    const mitte = knoten.find((k) => k.ring === 0), mp = mitte ? positionen[mitte.id] : { x: B / 2, y: H / 2 };
    const frei = (r, eigene) => {
      if (r.x < o.rand || r.y < o.rand || r.x + r.w > B - o.rand || r.y + r.h > H - o.rand) return false;
      if (gesetzt.some((g) => r.x < g.x + g.w && g.x < r.x + r.w && r.y < g.y + g.h && g.y < r.y + r.h)) return false;
      for (const id in positionen) {
        if (id === eigene) continue;
        const p = positionen[id], nx = Math.min(Math.max(p.x, r.x), r.x + r.w), ny = Math.min(Math.max(p.y, r.y), r.y + r.h);
        if (Math.hypot(p.x - nx, p.y - ny) < (radius[id] || 0) + 1) return false;
      }
      return true;
    };
    const versuche = (k, reihenfolge, breiten) => {
      const p = positionen[k.id], r0 = radius[k.id] || 0;
      for (const maxPx of breiten) {
        const text = kuerze(k.label, maxPx, messe);
        if (!text) continue;
        const w = Math.ceil(messe(text)) + 6;
        const kand = {
          rechts: { x: p.x + r0 + 4, y: p.y - h / 2, ausrichtung: "links" }, links: { x: p.x - r0 - 4 - w, y: p.y - h / 2, ausrichtung: "rechts" },
          unten: { x: p.x - w / 2, y: p.y + r0 + 3, ausrichtung: "mitte" }, oben: { x: p.x - w / 2, y: p.y - r0 - 3 - h, ausrichtung: "mitte" },
        };
        for (const name of reihenfolge) {
          const c = kand[name], r = { x: c.x, y: c.y, w: w, h: h, text: text, ausrichtung: c.ausrichtung };
          if (frei(r, k.id)) { gesetzt.push(r); aus[k.id] = r; return true; }
        }
      }
      return false;
    };
    if (mitte && positionen[mitte.id]) {                                                   // Fokus: immer beschriftet
      if (!versuche(mitte, ["unten", "oben", "rechts", "links"], [o.maxBreite * 1.4, o.maxBreite, 100, 60])) {
        const p = positionen[mitte.id], text = kuerze(mitte.label, o.maxBreite, messe), w = Math.ceil(messe(text)) + 6;
        const r = { x: Math.min(Math.max(p.x - w / 2, o.rand), B - o.rand - w), y: Math.min(p.y + (radius[mitte.id] || 0) + 3, H - o.rand - h), w: w, h: h, text: text, ausrichtung: "mitte" };
        gesetzt.push(r); aus[mitte.id] = r;
      }
    }
    const reihe = knoten.filter((k) => k.ring === 1).concat(knoten.filter((k) => k.ring !== 0 && k.ring !== 1 && o.zusaetzlich.includes(k.id)));
    for (const k of reihe) {
      const p = positionen[k.id];
      if (!p) continue;
      const rechts = p.x >= mp.x;
      versuche(k, rechts ? ["rechts", "unten", "oben", "links"] : ["links", "unten", "oben", "rechts"], [o.maxBreite, 100, 60]);
    }
    return aus;
  }

  /** Zwischenstand zwischen zwei Anordnungen (t von 0 bis 1, weich): {positionen, radius, alpha}. Knoten nur in `nach` blenden ein (und stehen
   *  schon bei t = 0 in `positionen`), Knoten nur in `von` blenden aus und fehlen bei t = 1. */
  function uebergang(von, nach, t) {
    const e = t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t), positionen = {}, radius = {}, alpha = {};
    for (const id in nach.positionen) {
      const b = nach.positionen[id], a = von.positionen[id];
      if (a) {
        positionen[id] = { x: a.x + (b.x - a.x) * e, y: a.y + (b.y - a.y) * e };
        radius[id] = (von.radius[id] || 0) + ((nach.radius[id] || 0) - (von.radius[id] || 0)) * e;
        alpha[id] = 1;
      } else { positionen[id] = { x: b.x, y: b.y }; radius[id] = nach.radius[id] || 0; alpha[id] = e; }
    }
    if (e < 1) {
      for (const id in von.positionen) {
        if (nach.positionen[id]) continue;
        positionen[id] = { x: von.positionen[id].x, y: von.positionen[id].y }; radius[id] = von.radius[id] || 0; alpha[id] = 1 - e;
      }
    }
    return { positionen: positionen, radius: radius, alpha: alpha };
  }

  /** Stabile Farbe je Werk (aus der Id); Werke ausserhalb der Bibliothek grau. `dunkel` waehlt hellere Toene fuer dunklen Grund. */
  function werkFarbe(werkId, dunkel) {
    if (!werkId) return dunkel ? "#9a9486" : "#6b665e";
    let h = 0x811c9dc5;
    for (let i = 0; i < werkId.length; i++) { h ^= werkId.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
    return `hsl(${FARB_TONE[h % FARB_TONE.length]}, 55%, ${dunkel ? 64 : 42}%)`;
  }

  /** Zeichnet die Szene {knoten, kanten, positionen, radius, labels, alpha?} mit Transformation t = {k, tx, ty}.
   *  `farben` = {bg, text, gedaempft, akzent, linie, dunkel}; z = {breite, hoehe, dpr, ausgewaehlt}. */
  function zeichne(ctx, szene, t, farben, z) {
    const dpr = z.dpr || 1, alpha = szene.alpha || {}, pos = szene.positionen, rad = szene.radius, knoten = szene.knoten || [];
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.globalAlpha = 1;
    ctx.fillStyle = farben.bg;
    ctx.fillRect(0, 0, z.breite, z.hoehe);
    ctx.save();
    ctx.translate(t.tx, t.ty);
    ctx.scale(t.k, t.k);
    ctx.setLineDash([]);
    ctx.lineCap = "round";
    for (const k of szene.kanten || []) {                                                   // Kanten
      const a = pos[k.von], b = pos[k.nach];
      if (!a || !b) continue;
      const w = k.wert || 0;
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
      if (k.art === "aehnlich") { ctx.strokeStyle = farben.akzent; ctx.globalAlpha = 0.35 + 0.5 * Math.min(1, w); ctx.lineWidth = 1 + 2 * Math.min(1, w); }
      else if (k.art === "querverweis") { ctx.strokeStyle = farben.akzent; ctx.globalAlpha = 0.75; ctx.lineWidth = 1.2; ctx.setLineDash([6, 4]); }
      else { ctx.strokeStyle = farben.gedaempft; ctx.globalAlpha = k.art === "thema" ? 0.5 : 0.25; ctx.lineWidth = 1; }
      ctx.stroke();
      ctx.setLineDash([]);
    }
    ctx.globalAlpha = 1;
    const knotenZeichnen = (k) => {
      const p = pos[k.id];
      if (!p) return;
      const r = rad[k.id] || 6, a = alpha[k.id] === undefined ? 1 : alpha[k.id], farbe = werkFarbe(k.werk, farben.dunkel);
      ctx.globalAlpha = (k.ring >= 2 ? 0.35 : 1) * a;
      if (k.ring === 0) {                                                                    // Fokus: Hof und Kern
        ctx.fillStyle = farben.akzent;
        ctx.globalAlpha = 0.15 * a; ctx.beginPath(); ctx.arc(p.x, p.y, r + 12, 0, 6.2832); ctx.fill();
        ctx.globalAlpha = 0.28 * a; ctx.beginPath(); ctx.arc(p.x, p.y, r + 6, 0, 6.2832); ctx.fill();
        ctx.globalAlpha = a; ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, 6.2832); ctx.fill();
      } else if (!k.offen) {                                                                // Werk ausserhalb der Bibliothek: hohl
        ctx.strokeStyle = farbe; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, 6.2832); ctx.stroke();
      } else if (k.typ === "thema") {                                                       // Raute
        ctx.fillStyle = farben.akzent;
        ctx.beginPath(); ctx.moveTo(p.x, p.y - r - 1); ctx.lineTo(p.x + r + 1, p.y); ctx.lineTo(p.x, p.y + r + 1); ctx.lineTo(p.x - r - 1, p.y); ctx.closePath(); ctx.fill();
      } else if (k.typ === "werk") {                                                        // Ring
        ctx.fillStyle = farben.bg; ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, 6.2832); ctx.fill();
        ctx.strokeStyle = farbe; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, 6.2832); ctx.stroke();
      } else {                                                                              // Kapitel
        ctx.fillStyle = farbe; ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, 6.2832); ctx.fill();
      }
      if (z.ausgewaehlt === k.id) {
        ctx.globalAlpha = a; ctx.strokeStyle = farben.text; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(p.x, p.y, r + 5, 0, 6.2832); ctx.stroke();
      }
    };
    for (const k of knoten) if (k.ring >= 2) knotenZeichnen(k);
    for (const k of knoten) if (k.ring === 1) knotenZeichnen(k);
    for (const k of knoten) if (k.ring === 0) knotenZeichnen(k);
    ctx.globalAlpha = 1;
    ctx.textBaseline = "middle";
    for (const k of szene.kanten || []) {                                                   // Relation der Querverweise an der Kantenmitte
      const a = pos[k.von], b = pos[k.nach];
      if (!a || !b || k.art !== "querverweis" || !k.label) continue;
      ctx.font = `${SCHRIFT - 1}px system-ui, sans-serif`; ctx.textAlign = "center"; ctx.fillStyle = farben.gedaempft;
      ctx.fillText(k.label, (a.x + b.x) / 2, (a.y + b.y) / 2 - 8);
    }
    const labels = szene.labels || {};
    for (const id in labels) {                                                              // Beschriftungen mit Hof fuer die Lesbarkeit
      const l = labels[id], ring = (knoten.find((k) => k.id === id) || {}).ring;
      ctx.font = `${ring === 0 ? "600 " : ""}${ring === 0 ? SCHRIFT + 1 : SCHRIFT}px system-ui, sans-serif`;
      ctx.textAlign = l.ausrichtung === "links" ? "left" : l.ausrichtung === "rechts" ? "right" : "center";
      const x = l.ausrichtung === "links" ? l.x + 3 : l.ausrichtung === "rechts" ? l.x + l.w - 3 : l.x + l.w / 2, y = l.y + l.h / 2;
      ctx.lineWidth = 3; ctx.strokeStyle = farben.bg; ctx.lineJoin = "round";
      ctx.strokeText(l.text, x, y);
      ctx.fillStyle = ring === 0 ? farben.text : farben.text; ctx.globalAlpha = ring === 0 ? 1 : 0.9;
      ctx.fillText(l.text, x, y);
    }
    ctx.restore();
    ctx.globalAlpha = 1;
  }

  // ---- Oberflaeche ---------------------------------------------------------------------------------------------------

  const CSS = `
.graph { position: relative; display: flex; flex-direction: column; min-height: 0; height: 100%; gap: 6px; }
.graph button { font: inherit; color: var(--text, #ece8de); background: var(--knopf, #2a2720); border: 1px solid var(--linie, #38352d); border-radius: 12px;
  min-height: 44px; min-width: 44px; padding: 0 12px; }
.graph button[aria-pressed="true"] { background: var(--akzent, #4fc3d9); color: var(--bg, #14130f); font-weight: 700; border-color: var(--akzent, #4fc3d9); }
.graph button:disabled { opacity: .45; }
.graph-leiste { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.graph-leiste .platz { flex: 1; }
.graph-flaeche { position: relative; flex: 1 1 auto; min-height: 220px; border-radius: 14px; overflow: hidden; background: var(--bg, #14130f); border: 1px solid var(--linie, #38352d); }
.graph-flaeche canvas { position: absolute; inset: 0; width: 100%; height: 100%; touch-action: none; display: block; }
.graph-hinweis { color: var(--gedaempft, #9a9486); font-size: .85em; min-height: 1.2em; }
/* Ueberlagert den unteren Rand: die Flaeche darf sich beim Antippen nicht verschieben (sonst trifft der nachgereichte Klick die Leiste) */
.graph-detail { position: absolute; left: 6px; right: 6px; bottom: 6px; z-index: 2; display: grid; gap: 4px; padding: 8px 10px; border: 1px solid var(--linie, #38352d); border-radius: 12px; background: var(--flaeche, #1d1b16); box-shadow: 0 2px 10px rgba(0,0,0,.35); }
.graph-detail[hidden], .graph-liste[hidden], .graph-flaeche[hidden] { display: none; }
.graph-detail b { overflow-wrap: anywhere; } .graph-detail small { color: var(--gedaempft, #9a9486); overflow-wrap: anywhere; }
.graph-detail .zeile { display: flex; flex-wrap: wrap; gap: 6px; }
.graph-liste { flex: 1 1 auto; min-height: 0; overflow: auto; display: grid; gap: 4px; align-content: start; }
.graph-liste h3 { margin: 8px 0 2px; font-size: .9rem; color: var(--gedaempft, #9a9486); }
.graph-liste .eintrag { display: flex; gap: 6px; align-items: stretch; }
.graph-liste .eintrag .waehle { flex: 1; text-align: left; display: grid; gap: 2px; padding: 6px 12px; height: auto; }
.graph-liste .eintrag small { color: var(--gedaempft, #9a9486); font-weight: 400; overflow-wrap: anywhere; }
`;

  function el(doc, tag, klasse, text) {
    const e = doc.createElement(tag);
    if (klasse) e.className = klasse;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  /** Baut die Oberflaeche in `eltern`. optionen = {oeffnen(id), fokusGeaendert(id), verbindungen, layout}.
   *  Rueckgabe: {setzeDaten(graph), setzeFokus(id, {ohneAnimation}), setzeArten(arten), zustand(), zerstoere()}. */
  function installiere(eltern, optionen) {
    const o = Object.assign({ oeffnen: null, fokusGeaendert: null, verbindungen: V, layout: GL }, optionen || {});
    const doc = eltern.ownerDocument, win = doc.defaultView;
    if (!doc.querySelector("style[data-graphansicht]")) { const s = el(doc, "style"); s.dataset.graphansicht = "1"; s.textContent = CSS; doc.head.append(s); }
    const abbruch = new AbortController(), sig = { signal: abbruch.signal };
    const zustand = { graph: null, fokusId: null, arten: { aehnlich: true, thema: true, querverweis: true, werk: true }, szene: null, anzeige: null,
                      t: { k: 1, tx: 0, ty: 0 }, ausgewaehlt: null, liste: false, b: 300, h: 200, geplant: 0, anim: 0 };

    const wurzel = el(doc, "div", "graph");
    const leiste = el(doc, "div", "graph-leiste");
    const filterKnoepfe = {};
    for (const [art, name] of ARTEN) {
      const b = el(doc, "button", "", name); b.type = "button"; b.dataset.art = art; b.setAttribute("aria-pressed", "true");
      b.title = `${name} ein- oder ausblenden`; filterKnoepfe[art] = b; leiste.append(b);
    }
    leiste.append(el(doc, "span", "platz"));
    const knopf = (text, name, aktion) => { const b = el(doc, "button", "", text); b.type = "button"; b.setAttribute("aria-label", name); b.title = name; b.dataset.aktion = aktion; return b; };
    const grosser = knopf("+", "Vergrößern", "plus"), kleiner = knopf("−", "Verkleinern", "minus"), zurueck = knopf("◎", "Ansicht zurücksetzen", "mitte");
    const listeKnopf = knopf("Liste", "Zwischen Netz und Liste wechseln", "liste"); listeKnopf.setAttribute("aria-pressed", "false");
    leiste.append(kleiner, grosser, zurueck, listeKnopf);
    const flaeche = el(doc, "div", "graph-flaeche");
    const canvas = el(doc, "canvas"); canvas.setAttribute("role", "img");
    flaeche.append(canvas);
    const detail = el(doc, "div", "graph-detail"); detail.hidden = true;
    const listenFeld = el(doc, "div", "graph-liste"); listenFeld.hidden = true;
    const hinweis = el(doc, "div", "graph-hinweis"); hinweis.setAttribute("role", "status");
    wurzel.append(leiste, flaeche, listenFeld, detail, hinweis);
    eltern.append(wurzel);

    const ctx = canvas.getContext("2d");
    const mess = doc.createElement("canvas").getContext("2d");
    mess.font = `${SCHRIFT}px system-ui, sans-serif`;
    const messe = (t) => mess.measureText(t).width;
    const reduziert = () => !!(win.matchMedia && win.matchMedia("(prefers-reduced-motion: reduce)").matches);

    const farbenLesen = () => {
      const cs = win.getComputedStyle(wurzel), v = (n, f) => (cs.getPropertyValue(n).trim() || f);
      const bg = v("--bg", "#14130f"), m = /^#([0-9a-f]{6})$/i.exec(bg), rgb = /rgba?\((\d+)[ ,]+(\d+)[ ,]+(\d+)/.exec(bg);
      const c = m ? [parseInt(m[1].slice(0, 2), 16), parseInt(m[1].slice(2, 4), 16), parseInt(m[1].slice(4), 16)] : rgb ? [+rgb[1], +rgb[2], +rgb[3]] : [20, 19, 15];
      return { bg: bg, text: v("--text", "#ece8de"), gedaempft: v("--gedaempft", "#9a9486"), akzent: v("--akzent", "#4fc3d9"), linie: v("--linie", "#38352d"),
               dunkel: (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) < 128 };
    };

    function baueSzene(id) {
      const f = o.verbindungen.fokus(zustand.graph, id, { arten: zustand.arten });
      if (!f.knoten.length) return null;
      const lay = o.layout.ordne(f, zustand.b, zustand.h);
      const labels = beschriftungen(f.knoten, lay.positionen, lay.radius, { breite: zustand.b, hoehe: zustand.h }, messe,
                                    { zusaetzlich: zustand.ausgewaehlt ? [zustand.ausgewaehlt] : [] });
      return { knoten: f.knoten, kanten: f.kanten, positionen: lay.positionen, radius: lay.radius, labels: labels };
    }
    const plane = () => { if (!zustand.geplant) zustand.geplant = win.requestAnimationFrame(() => { zustand.geplant = 0; zeichneJetzt(); }); };
    function zeichneJetzt() {
      const s = zustand.anzeige || zustand.szene;
      if (!s) { ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, canvas.width, canvas.height); return; }
      zeichne(ctx, s, zustand.t, farbenLesen(), { breite: zustand.b, hoehe: zustand.h, dpr: dpr(), ausgewaehlt: zustand.ausgewaehlt });
    }
    const dpr = () => Math.min(win.devicePixelRatio || 1, 2);

    function groesseAnpassen() {
      const r = flaeche.getBoundingClientRect(), b = Math.max(120, Math.round(r.width)), h = Math.max(120, Math.round(r.height));
      if (b === zustand.b && h === zustand.h && canvas.width === Math.round(b * dpr())) return false;
      zustand.b = b; zustand.h = h;
      canvas.width = Math.round(b * dpr()); canvas.height = Math.round(h * dpr());
      return true;
    }

    function beschreibung() {
      const f = zustand.szene && zustand.szene.knoten.find((k) => k.ring === 0);
      canvas.setAttribute("aria-label", f ? `Verbindungsnetz zu ${f.label}: ${zustand.szene.knoten.length - 1} Verbindungen. Dieselben Verbindungen stehen in der Liste.` : "Keine Verbindungen");
    }

    function neuAufbauen(animiert) {
      if (!zustand.graph || !zustand.fokusId) { zustand.szene = null; zustand.anzeige = null; beschreibung(); plane(); return; }
      const alt = zustand.szene, neu = baueSzene(zustand.fokusId);
      zustand.anim++;
      const meine = zustand.anim;
      beschreibung();
      if (alt && neu && animiert && !reduziert()) {
        zustand.szene = neu;
        const start = win.performance.now();
        const schritt = (jetzt) => {
          if (meine !== zustand.anim) return;
          const t = Math.min(1, (jetzt - start) / 350), z = uebergang(alt, neu, t);
          if (t >= 1) { zustand.anzeige = null; plane(); return; }
          const ids = new Set(neu.knoten.map((k) => k.id));
          zustand.anzeige = { knoten: neu.knoten.concat(alt.knoten.filter((k) => !ids.has(k.id))), kanten: [], labels: {}, positionen: z.positionen, radius: z.radius, alpha: z.alpha };
          zeichneJetzt();
          win.requestAnimationFrame(schritt);
        };
        win.requestAnimationFrame(schritt);
      } else { zustand.szene = neu; zustand.anzeige = null; plane(); }
      zeigeListe();
      zeigeDetail();
    }

    function knotenDaten(id) { return zustand.szene && zustand.szene.knoten.find((k) => k.id === id); }
    function kanteZu(id) {
      const s = zustand.szene;
      if (!s) return null;
      return s.kanten.find((k) => (k.von === zustand.fokusId && k.nach === id) || (k.nach === zustand.fokusId && k.von === id)) || s.kanten.find((k) => k.von === id || k.nach === id) || null;
    }
    function zeigeDetail() {
      detail.textContent = "";
      const k = !zustand.liste && zustand.ausgewaehlt && knotenDaten(zustand.ausgewaehlt);
      if (!k) { detail.hidden = true; return; }
      detail.hidden = false; zustand.detailZeit = win.performance.now();
      detail.append(el(doc, "b", "", k.label), el(doc, "small", "", k.offen ? TYP_NAME[k.typ] || k.typ : "Werk außerhalb der Bibliothek (nicht öffnbar)"));
      const e = kanteZu(k.id);
      if (e && k.id !== zustand.fokusId) {
        if (e.art === "aehnlich") detail.append(el(doc, "small", "", `Ähnlichkeit ${Math.round(e.wert * 100)} %` + (e.beleg ? `: „${e.beleg}“` : "")));
        else if (e.art === "querverweis") detail.append(el(doc, "small", "", `Querverweis: ${e.label}` + (e.beleg ? ` – ${e.beleg}` : "")));
        else if (e.art === "thema") detail.append(el(doc, "small", "", "gehört zum selben Thema"));
        else if (e.art === "werk") detail.append(el(doc, "small", "", "gehört zu diesem Werk"));
      }
      const zeile = el(doc, "div", "zeile");
      const mitteBtn = knopf("Zur Mitte", "Diesen Knoten in die Mitte setzen", "zurmitte");
      mitteBtn.textContent = "Zur Mitte"; mitteBtn.disabled = !k.offen || k.id === zustand.fokusId;
      zeile.append(mitteBtn);
      if (k.typ === "kapitel") { const b = knopf("Öffnen", "Dieses Kapitel öffnen", "oeffnen"); b.textContent = "Öffnen"; zeile.append(b); }
      const zu = knopf("Schließen", "Auswahl aufheben", "abwaehlen"); zu.textContent = "Schließen";
      zeile.append(zu);
      detail.append(zeile);
    }
    function zeigeListe() {
      listenFeld.textContent = "";
      if (!zustand.graph || !zustand.fokusId) return;
      const f = zustand.szene && zustand.szene.knoten.find((k) => k.ring === 0);
      if (f) {
        const kopf = el(doc, "div", "eintrag"), t = el(doc, "div", "", ""); t.style.flex = "1";
        t.append(el(doc, "b", "", f.label), el(doc, "br"), el(doc, "small", "", TYP_NAME[f.typ] || f.typ));
        kopf.append(t);
        if (f.typ === "kapitel") { const b = knopf("Öffnen", "Dieses Kapitel öffnen", "oeffnen"); b.textContent = "Öffnen"; b.dataset.id = f.id; kopf.append(b); }
        listenFeld.append(kopf);
      }
      for (const gr of o.verbindungen.liste(zustand.graph, zustand.fokusId)) {
        listenFeld.append(el(doc, "h3", "", gr.gruppe));
        for (const e of gr.eintraege) {
          const zeile = el(doc, "div", "eintrag");
          const w = knopf("", e.label, "waehle"); w.className = "waehle"; w.dataset.id = e.id; w.disabled = !e.offen;
          w.append(el(doc, "span", "", e.label));
          const sub = e.wert !== undefined ? `Ähnlichkeit ${Math.round(e.wert * 100)} %` + (e.beleg ? `: „${e.beleg}“` : "")
            : e.relation ? `${e.richtung === "ein" ? "verwiesen von" : "verweist"}: ${e.relation}` : !e.offen ? "nicht in der Bibliothek" : "";
          if (sub) w.append(el(doc, "small", "", sub));
          zeile.append(w);
          if (e.typ === "kapitel") { const b = knopf("Öffnen", "Dieses Kapitel öffnen", "oeffnen"); b.textContent = "Öffnen"; b.dataset.id = e.id; zeile.append(b); }
          listenFeld.append(zeile);
        }
      }
    }

    function waehle(id) {
      zustand.ausgewaehlt = id;
      if (zustand.szene) zustand.szene.labels = beschriftungen(zustand.szene.knoten, zustand.szene.positionen, zustand.szene.radius, { breite: zustand.b, hoehe: zustand.h }, messe,
                                                                { zusaetzlich: id ? [id] : [] });
      zeigeDetail(); plane();
    }
    function setzeFokus(id, opt) {
      const k = zustand.graph && zustand.graph.knoten.get(id);
      if (!k || !k.offen) return false;
      zustand.fokusId = id; zustand.ausgewaehlt = null; zustand.t = { k: 1, tx: 0, ty: 0 };
      neuAufbauen(!(opt && opt.ohneAnimation));
      if (o.fokusGeaendert) o.fokusGeaendert(id);
      return true;
    }
    function zoomUm(faktor, x, y) {
      const t = zustand.t, k = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, t.k * faktor)), f = k / t.k;
      zustand.t = { k: k, tx: x - (x - t.tx) * f, ty: y - (y - t.ty) * f };
      plane();
    }

    // Bedienung
    filterKnoepfe && Object.values(filterKnoepfe).forEach((b) => b.addEventListener("click", () => {
      zustand.arten[b.dataset.art] = !zustand.arten[b.dataset.art];
      b.setAttribute("aria-pressed", String(zustand.arten[b.dataset.art]));
      if (zustand.ausgewaehlt && !knotenDaten(zustand.ausgewaehlt)) zustand.ausgewaehlt = null;
      neuAufbauen(true);
    }, sig));
    leiste.addEventListener("click", (ev) => {
      const b = ev.target.closest("button[data-aktion]");
      if (!b) return;
      const mitte = { x: zustand.b / 2, y: zustand.h / 2 };
      if (b.dataset.aktion === "plus") zoomUm(1.25, mitte.x, mitte.y);
      else if (b.dataset.aktion === "minus") zoomUm(0.8, mitte.x, mitte.y);
      else if (b.dataset.aktion === "mitte") { zustand.t = { k: 1, tx: 0, ty: 0 }; plane(); }
      else if (b.dataset.aktion === "liste") {
        zustand.liste = !zustand.liste;
        listeKnopf.setAttribute("aria-pressed", String(zustand.liste)); listeKnopf.textContent = zustand.liste ? "Netz" : "Liste";
        flaeche.hidden = zustand.liste; listenFeld.hidden = !zustand.liste; zeigeDetail();
        if (!zustand.liste) { win.requestAnimationFrame(() => { if (groesseAnpassen()) neuAufbauen(false); plane(); }); }
      }
    }, sig);
    const aktionen = (ev) => {
      const b = ev.target.closest("button[data-aktion]");
      if (!b) return;
      if (b.closest(".graph-detail") && win.performance.now() - (zustand.detailZeit || 0) < 400) return;      // nachgereichter Klick des Antippens
      if (b.dataset.aktion === "zurmitte" && zustand.ausgewaehlt) setzeFokus(zustand.ausgewaehlt);
      else if (b.dataset.aktion === "abwaehlen") waehle(null);
      else if (b.dataset.aktion === "oeffnen") { const id = b.dataset.id || zustand.ausgewaehlt; if (id && o.oeffnen) o.oeffnen(id); }
      else if (b.dataset.aktion === "waehle") setzeFokus(b.dataset.id);
    };
    detail.addEventListener("click", aktionen, sig);
    listenFeld.addEventListener("click", aktionen, sig);

    // Berührung: ein Finger tippt oder zieht, zwei Finger zoomen und verschieben
    const zeiger = new Map();
    let geste = null;
    const ort = (ev) => { const r = canvas.getBoundingClientRect(); return { x: ev.clientX - r.left, y: ev.clientY - r.top }; };
    canvas.addEventListener("pointerdown", (ev) => {
      try { canvas.setPointerCapture(ev.pointerId); } catch (e) { /* kein Capture noetig */ }
      zeiger.set(ev.pointerId, ort(ev));
      if (zeiger.size === 1) geste = { start: ort(ev), bewegt: false, t0: Object.assign({}, zustand.t) };
      else if (zeiger.size === 2) {
        const [p, q] = [...zeiger.values()];
        geste = { bewegt: true, t0: Object.assign({}, zustand.t), d0: Math.hypot(p.x - q.x, p.y - q.y) || 1, m0: { x: (p.x + q.x) / 2, y: (p.y + q.y) / 2 } };
      }
    }, sig);
    canvas.addEventListener("pointermove", (ev) => {
      if (!zeiger.has(ev.pointerId) || !geste) return;
      zeiger.set(ev.pointerId, ort(ev));
      if (zeiger.size >= 2 && geste.d0) {
        const [p, q] = [...zeiger.values()], d = Math.hypot(p.x - q.x, p.y - q.y) || 1, m = { x: (p.x + q.x) / 2, y: (p.y + q.y) / 2 };
        const k = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, geste.t0.k * d / geste.d0)), wx = (geste.m0.x - geste.t0.tx) / geste.t0.k, wy = (geste.m0.y - geste.t0.ty) / geste.t0.k;
        zustand.t = { k: k, tx: m.x - wx * k, ty: m.y - wy * k };
        plane();
      } else if (zeiger.size === 1 && geste.start) {
        const p = ort(ev), dx = p.x - geste.start.x, dy = p.y - geste.start.y;
        if (!geste.bewegt && Math.hypot(dx, dy) > WISCHEN) geste.bewegt = true;
        if (geste.bewegt) { zustand.t = { k: geste.t0.k, tx: geste.t0.tx + dx, ty: geste.t0.ty + dy }; plane(); }
      }
    }, sig);
    const ende = (ev) => {
      if (!zeiger.has(ev.pointerId)) return;
      const war = zeiger.size === 1 && geste && !geste.bewegt && ev.type === "pointerup";
      const p = ort(ev);
      zeiger.delete(ev.pointerId);
      if (war && zustand.szene) {
        const s = zustand.szene, id = trifft(s.positionen, s.radius, zustand.t, p.x, p.y);
        waehle(id);
      }
      if (zeiger.size === 0) geste = null;
      else if (zeiger.size === 1) { const rest = [...zeiger.values()][0]; geste = { start: rest, bewegt: true, t0: Object.assign({}, zustand.t) }; }
    };
    canvas.addEventListener("pointerup", ende, sig);
    canvas.addEventListener("pointercancel", ende, sig);
    canvas.addEventListener("wheel", (ev) => { ev.preventDefault(); const p = ort(ev); zoomUm(ev.deltaY < 0 ? 1.15 : 1 / 1.15, p.x, p.y); }, { passive: false, signal: abbruch.signal });

    const beobachter = typeof win.ResizeObserver === "function" ? new win.ResizeObserver(() => { if (!flaeche.hidden && groesseAnpassen()) neuAufbauen(false); }) : null;
    if (beobachter) beobachter.observe(flaeche);
    groesseAnpassen();

    return {
      setzeDaten(graph) {
        zustand.graph = graph; zustand.szene = null;
        if (zustand.fokusId && !(graph && graph.knoten.get(zustand.fokusId))) zustand.fokusId = null;
        neuAufbauen(false);
      },
      setzeFokus: setzeFokus,
      setzeArten(arten) {
        Object.assign(zustand.arten, arten);
        for (const [art] of ARTEN) filterKnoepfe[art].setAttribute("aria-pressed", String(zustand.arten[art] !== false));
        neuAufbauen(true);
      },
      zustand() {
        const s = zustand.szene, t = zustand.t, pos = {};
        if (s) for (const id in s.positionen) pos[id] = { x: s.positionen[id].x * t.k + t.tx, y: s.positionen[id].y * t.k + t.ty };
        return { fokus: zustand.fokusId, ausgewaehlt: zustand.ausgewaehlt, liste: zustand.liste, arten: Object.assign({}, zustand.arten), transform: Object.assign({}, t),
                 ringe: s ? [0, 1, 2].map((r) => s.knoten.filter((k) => k.ring === r).map((k) => k.id)) : [[], [], []], positionen: pos,
                 labels: s ? Object.keys(s.labels) : [], animiert: !!zustand.anzeige, flaeche: { b: zustand.b, h: zustand.h } };
      },
      zerstoere() { zustand.anim++; if (beobachter) beobachter.disconnect(); abbruch.abort(); if (zustand.geplant) win.cancelAnimationFrame(zustand.geplant); wurzel.remove(); },
    };
  }

  return { trifft, kuerze, beschriftungen, uebergang, werkFarbe, zeichne, installiere };
});
