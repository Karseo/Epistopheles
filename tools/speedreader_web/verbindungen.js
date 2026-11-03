/* Kern der Ansicht "Verbindungen" (Plan 2026-11-03, Task 5): aus verbindungen.json einen Index bauen, daraus den Ausschnitt
 * um einen Fokusknoten (Ring 1 beschriftet, Ring 2 verblasst), dieselben Daten als Liste und die Pruefung gegen daten.json.
 * Reine Funktionen, kein DOM, keine Fremdbibliothek; laeuft im Browser und in Node. Die Ausgabe ist deterministisch
 * (Gleichstand entscheidet die Id), unabhaengig von der Reihenfolge der Eingabe.
 *
 * Knoten-Ids: Werk "b001", Kapitel "b001:3", Thema "b001#slug", Werk ausserhalb der Bibliothek "x:<Autor>|<Titel>" (hohl, nicht oeffnbar).
 * Kantenarten: aehnlich (Kapitel-Kapitel, Qdrant), thema (Thema-Kapitel), querverweis (Werk-Werk), werk (Kapitel-Werk). */
(function (root, fabrik) {
  if (typeof module === "object" && module.exports) module.exports = fabrik();
  else root.Verbindungen = fabrik();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const VERSION = 1;
  const ART_RANG = { aehnlich: 0, querverweis: 1, werk: 2, thema: 3 };       // Reihenfolge der Nachbarn in einem Ring
  const RESERVIERT = 5;                                                       // Plaetze fuer Werk und Themen im Ring 1 eines Kapitels
  const RELATION = { ergaenzt: "ergänzt" };

  const istObjekt = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
  const liste = (x) => (Array.isArray(x) ? x : []);
  const text = (x) => (typeof x === "string" ? x : "");
  const nachname = (autor) => { const a = text(autor).trim(); return a.split(",")[0].trim() || a; };
  const relationKlar = (r) => RELATION[r] || text(r).replace(/-/g, " ");
  const kurzLabel = (autor, titel) => [nachname(autor), text(titel)].filter(Boolean).join(" · ");

  /** Index aus dem Inhalt von verbindungen.json: {knoten: Map, kanten: [...], nachbarn: Map(id -> [{k, n}]), erstellt, qdrant}.
   *  Unbrauchbare Eintraege (kein Objekt, unbekannte Knoten, Kanten auf sich selbst) werden uebersprungen. */
  function baue(daten) {
    const g = { knoten: new Map(), kanten: [], nachbarn: new Map(), erstellt: istObjekt(daten) ? daten.erstellt : undefined, qdrant: istObjekt(daten) ? daten.qdrant : null };
    if (!istObjekt(daten)) return g;
    const werkAutor = new Map();
    const kante = (von, nach, art, wert, label, beleg) => {
      if (von === nach || !g.knoten.has(von) || !g.knoten.has(nach)) return null;
      const k = { von: von, nach: nach, art: art, wert: wert, label: label || "", beleg: beleg || "" };
      g.kanten.push(k);
      for (const [a, b] of [[von, nach], [nach, von]]) {
        if (!g.nachbarn.has(a)) g.nachbarn.set(a, []);
        g.nachbarn.get(a).push({ k: k, n: b });
      }
      return k;
    };
    for (const w of liste(daten.werke)) {
      if (!istObjekt(w) || typeof w.id !== "string") continue;
      werkAutor.set(w.id, w.autor);
      g.knoten.set(w.id, { id: w.id, typ: "werk", werk: w.id, label: kurzLabel(w.autor, w.titel), offen: true });
    }
    for (const k of liste(daten.kapitel)) {
      if (!istObjekt(k) || typeof k.id !== "string" || !werkAutor.has(k.werk)) continue;
      g.knoten.set(k.id, { id: k.id, typ: "kapitel", werk: k.werk, nr: k.nr, label: kurzLabel(werkAutor.get(k.werk), k.titel), offen: true });
      kante(k.id, k.werk, "werk", 0);
    }
    for (const t of liste(daten.themen)) {
      if (!istObjekt(t) || typeof t.id !== "string" || !werkAutor.has(t.werk)) continue;
      g.knoten.set(t.id, { id: t.id, typ: "thema", werk: t.werk, label: text(t.name) || t.id, offen: true });
      for (const nr of liste(t.kapitel)) kante(t.id, `${t.werk}:${nr}`, "thema", 0);
    }
    const beste = new Map();                                                  // Paar (sortiert) -> bester Eintrag (beide Richtungen vereinigt)
    for (const a of liste(daten.aehnlich)) {
      if (!istObjekt(a) || typeof a.von !== "string" || typeof a.nach !== "string" || typeof a.wert !== "number") continue;
      if (a.von === a.nach || !g.knoten.has(a.von) || !g.knoten.has(a.nach)) continue;
      const schluessel = a.von < a.nach ? a.von + "\u0000" + a.nach : a.nach + "\u0000" + a.von;
      const alt = beste.get(schluessel);
      if (!alt || a.wert > alt.wert || (a.wert === alt.wert && a.von < alt.von)) beste.set(schluessel, a);
    }
    for (const a of beste.values()) kante(a.von, a.nach, "aehnlich", a.wert, "", text(a.beleg));
    const gesehen = new Set();
    for (const q of liste(daten.querverweise)) {
      if (!istObjekt(q) || !g.knoten.has(q.von)) continue;
      let nach = q.nach;
      if (typeof nach !== "string" || !g.knoten.has(nach)) {                  // Werk ausserhalb der Bibliothek: hohler Knoten
        if (!text(q.autor) && !text(q.titel)) continue;
        nach = `x:${text(q.autor)}|${text(q.titel)}`;
        if (!g.knoten.has(nach)) g.knoten.set(nach, { id: nach, typ: "werk", werk: null, label: kurzLabel(q.autor, q.titel) || text(q.titel), offen: false });
      }
      const dopp = `${q.von}\u0000${nach}\u0000${text(q.relation)}`;
      if (gesehen.has(dopp)) continue;
      gesehen.add(dopp);
      kante(q.von, nach, "querverweis", 0, relationKlar(q.relation), text(q.notiz));
    }
    return g;
  }

  /** Reihenfolge der Nachbarn: Kantenart (aehnlich, querverweis, werk, thema), dann Wert absteigend, dann Id. */
  function vergleiche(a, b) {
    return (ART_RANG[a.k.art] - ART_RANG[b.k.art]) || (b.k.wert - a.k.wert) || (a.n < b.n ? -1 : a.n > b.n ? 1 : 0);
  }

  /** Ausschnitt um `id`: {knoten: [{id, typ, ring, label, werk, offen, nr?, ueber?}], kanten: [{von, nach, art, wert, label, beleg}]}.
   *  Ring 0 = Fokus, Ring 1 = bis `ring1` staerkste Nachbarn (ein Kapitel behaelt Plaetze fuer Werk und Themen), Ring 2 = bis `ring2`
   *  Nachbarn der Nachbarn (`ueber` nennt den Ring-1-Knoten): nur Knoten. Kanten gibt es nur zwischen Fokus und Ring 1 und
   *  innerhalb von Ring 1. `optionen.arten` schaltet Kantenarten ab (Standard alle an). Unbekannter oder hohler Fokus: leer mit `fehler`. */
  function fokus(g, id, optionen) {
    const o = Object.assign({ ring1: 14, ring2: 14 }, optionen || {});
    const arten = Object.assign({ aehnlich: true, thema: true, querverweis: true, werk: true }, o.arten || {});
    const mitte = g.knoten.get(id);
    if (!mitte) return { knoten: [], kanten: [], fehler: "Unbekannter Knoten" };
    if (!mitte.offen) return { knoten: [], kanten: [], fehler: "Dieses Werk liegt nicht in der Bibliothek und ist nicht oeffnbar" };
    const erlaubt = (e) => arten[e.k.art] !== false;
    const bestePerNachbar = (eintraege, ausschluss) => {
      const m = new Map();
      for (const e of eintraege) {
        if (!erlaubt(e) || ausschluss.has(e.n)) continue;
        const alt = m.get(e.n);
        if (!alt || vergleiche(e, alt) < 0) m.set(e.n, e);
      }
      return [...m.values()].sort(vergleiche);
    };
    // Ring 1
    const kandidaten = bestePerNachbar(g.nachbarn.get(id) || [], new Set([id]));
    let gewaehlt;
    if (mitte.typ === "kapitel") {                                            // Werk und Themen bleiben, auch wenn es viele aehnliche gibt
      const struktur = kandidaten.filter((e) => e.k.art === "werk" || e.k.art === "thema").slice(0, Math.min(RESERVIERT, o.ring1));
      const rest = kandidaten.filter((e) => !struktur.includes(e)).slice(0, Math.max(0, o.ring1 - struktur.length));
      gewaehlt = struktur.concat(rest).sort(vergleiche);
    } else gewaehlt = kandidaten.slice(0, o.ring1);
    const ring1 = gewaehlt.map((e) => e.n);
    const sichtbar = new Set([id, ...ring1]);
    // Ring 2: Nachbarn der Ring-1-Knoten, die noch nicht dabei sind
    const m2 = new Map();
    for (const r of ring1) {
      for (const e of bestePerNachbar(g.nachbarn.get(r) || [], sichtbar)) {
        const alt = m2.get(e.n);
        if (!alt || vergleiche(e, alt.e) < 0) m2.set(e.n, { e: e, ueber: r });
      }
    }
    const ring2 = [...m2.entries()].sort((a, b) => vergleiche(a[1].e, b[1].e)).slice(0, o.ring2);
    // Ausgabe
    const knoten = (n, ring, ueber) => {
      const k = g.knoten.get(n), aus = { id: k.id, typ: k.typ, ring: ring, label: k.label, werk: k.werk, offen: k.offen };
      if (k.nr !== undefined) aus.nr = k.nr;
      if (ueber !== undefined) aus.ueber = ueber;
      return aus;
    };
    const kanten = [], gesehen = new Set();
    for (const n of sichtbar) {
      for (const e of g.nachbarn.get(n) || []) {
        if (!erlaubt(e) || !sichtbar.has(e.n) || gesehen.has(e.k)) continue;
        gesehen.add(e.k);
        kanten.push({ von: e.k.von, nach: e.k.nach, art: e.k.art, wert: e.k.wert, label: e.k.label, beleg: e.k.beleg });
      }
    }
    kanten.sort((a, b) => (a.von < b.von ? -1 : a.von > b.von ? 1 : a.nach < b.nach ? -1 : a.nach > b.nach ? 1 : a.art < b.art ? -1 : a.art > b.art ? 1 : 0));
    return { knoten: [knoten(id, 0)].concat(ring1.map((n) => knoten(n, 1)), ring2.map(([n, x]) => knoten(n, 2, x.ueber))), kanten: kanten };
  }

  /** Dieselben Verbindungen als Liste: [{gruppe, eintraege: [{id, label, typ, offen, wert?, beleg?, relation?, richtung?}]}], leere Gruppen entfallen. */
  function liste_(g, id) {
    const mitte = g.knoten.get(id);
    if (!mitte) return [];
    const nach = (n) => g.knoten.get(n);
    const proId = new Map();
    for (const e of g.nachbarn.get(id) || []) {
      const alt = proId.get(e.n);
      if (!alt || vergleiche(e, alt) < 0) proId.set(e.n, e);
    }
    const eintrag = (e) => {
      const n = nach(e.n), x = { id: n.id, label: n.label, typ: n.typ, offen: n.offen };
      if (e.k.art === "aehnlich") { x.wert = e.k.wert; x.beleg = e.k.beleg; }
      if (e.k.art === "querverweis") { x.relation = e.k.label; x.beleg = e.k.beleg; x.richtung = e.k.von === id ? "aus" : "ein"; }
      return x;
    };
    const nachNr = (a, b) => ((a.nr ?? 0) - (b.nr ?? 0)) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
    const alle = [...proId.values()];
    const gruppe = (name, art, sortiere) => {
      const treffer = alle.filter((e) => e.k.art === art);
      if (sortiere) treffer.sort((a, b) => sortiere(nach(a.n), nach(b.n)));
      return treffer.length ? { gruppe: name, eintraege: treffer.map(eintrag) } : null;
    };
    const aus = mitte.typ === "kapitel"
      ? [gruppe("Ähnliche Stellen", "aehnlich"), gruppe("Themen", "thema", (a, b) => (a.id < b.id ? -1 : 1)), gruppe("Werk", "werk")]
      : mitte.typ === "thema"
        ? [gruppe("Kapitel in diesem Thema", "thema", nachNr)]
        : [gruppe("Querverweise", "querverweis", (a, b) => (a.id < b.id ? -1 : 1)), gruppe("Kapitel", "werk", nachNr)];
    if (mitte.typ === "kapitel") {                                            // Ähnliche nach Wert absteigend (vergleiche sortiert schon so)
      const g0 = aus[0];
      if (g0) g0.eintraege.sort((a, b) => (b.wert - a.wert) || (a.id < b.id ? -1 : 1));
    }
    return aus.filter(Boolean);
  }

  /** Passen die Verbindungsdaten zu daten.json (`tage`)? {ok, grund, fehlend: [Kapitel-Ids], hinweise: [Text]}.
   *  Nicht ok: andere Version, anderer Export (`erstellt`), Kapitel, die in daten.json fehlen (Buch-Ids gelten nur innerhalb eines Exports).
   *  `hinweise` (ok bleibt wahr): ohne Qdrant exportiert oder Abfragen fehlgeschlagen. */
  function pruefe(daten, tage) {
    const nein = (grund, fehlend) => ({ ok: false, grund: grund, fehlend: fehlend || [], hinweise: [] });
    if (!istObjekt(daten) || !istObjekt(tage)) return nein("Keine Verbindungsdaten oder keine daten.json");
    if (daten.version !== VERSION) return nein(`Die Verbindungsdaten haben eine andere Version (${daten.version}, erwartet ${VERSION}): export_verbindungen.py erneut ausführen`);
    if (typeof daten.erstellt !== "string" || !Array.isArray(tage.buecher)) return nein("Die daten.json hat nicht das erwartete Format");
    if (daten.erstellt !== tage.erstellt) return nein(`Die Verbindungsdaten gehören zu einem anderen Export als daten.json (${daten.erstellt} statt ${tage.erstellt})`);
    const vorhanden = new Map();
    for (const b of tage.buecher) if (istObjekt(b)) vorhanden.set(b.id, new Set(liste(b.kapitel).filter(istObjekt).map((k) => k.nr)));
    const fehlend = [];
    for (const k of liste(daten.kapitel)) if (istObjekt(k) && !(vorhanden.get(k.werk) || new Set()).has(k.nr)) fehlend.push(k.id);
    if (fehlend.length) return nein(`${fehlend.length} Kapitel der Verbindungsdaten stehen nicht in daten.json: beide Dateien neu exportieren`, fehlend);
    const hinweise = [];
    if (daten.qdrant === null || daten.qdrant === undefined) hinweise.push("Ähnliche Stellen fehlen: die Daten wurden ohne Qdrant exportiert.");
    else if (istObjekt(daten.qdrant) && daten.qdrant.fehlend > 0) {
      hinweise.push(`Ähnliche Stellen sind unvollständig (${daten.qdrant.fehlend} von ${daten.qdrant.abgefragt} Abfragen fehlgeschlagen).`);
    }
    return { ok: true, grund: "", fehlend: [], hinweise: hinweise };
  }

  return { baue: baue, fokus: fokus, liste: liste_, pruefe: pruefe };
});
