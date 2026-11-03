"""Tests fuer die reinen Teile von graphansicht.js (Trefferflaeche, Beschriftung, Uebergang, Zeichnen gegen ein Aufzeichnungs-Canvas). Node."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node nicht installiert")

SKRIPT = r"""
const G = require(process.argv[1]);
const GL = require(process.argv[2]);
const V = require(process.argv[3]);
const e = JSON.parse(require("fs").readFileSync(0, "utf8"));
const messe = (t) => t.length * 7;
const f = new Function("G", "GL", "V", "d", "messe", "return (() => {" + e.code + "})();");
process.stdout.write(JSON.stringify(f(G, GL, V, e.daten, messe)));
"""


def js(code, daten=None):
    lauf = subprocess.run([NODE, "-e", SKRIPT, str(HIER / "graphansicht.js"), str(HIER / "graphlayout.js"), str(HIER / "verbindungen.js")],
                          input=json.dumps({"code": code, "daten": daten}), capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(lauf.stdout)


def netz(n1=14, n2=14, label=lambda i: f"Nachname{i} · Ein ziemlich langer Kapiteltitel Nummer {i}"):
    knoten = [{"id": "f", "typ": "kapitel", "ring": 0, "label": "Fokus · Das Kapitel in der Mitte", "werk": "b001", "offen": True}] \
        + [{"id": f"a{i}", "typ": ("thema" if i % 5 == 0 else "kapitel"), "ring": 1, "label": label(i), "werk": f"b{i % 4 + 1:03d}", "offen": True} for i in range(n1)] \
        + [{"id": f"b{i}", "typ": "kapitel", "ring": 2, "label": f"Zweiter Ring {i}", "werk": "b002", "offen": True, "ueber": f"a{i % max(1, n1)}"} for i in range(n2)]
    kanten = [{"von": "f", "nach": f"a{i}", "art": ("thema" if i % 5 == 0 else "aehnlich"), "wert": 0.55 + i / 40, "label": ""} for i in range(n1)]
    kanten.append({"von": "a1", "nach": "a2", "art": "querverweis", "wert": 0, "label": "ergänzt"})
    return {"knoten": knoten, "kanten": kanten}


# --- trifft -----------------------------------------------------------------------------------------------------

def test_trifft_hat_mindestens_44_px_trefferflaeche_auch_bei_kleinem_knoten_und_zoom():
    code = '''const pos = { a: { x: 100, y: 100 }, b: { x: 300, y: 100 } }, rad = { a: 6, b: 6 };
      const t1 = { k: 1, tx: 0, ty: 0 }, t05 = { k: 0.5, tx: 0, ty: 0 };
      return { mitteA: G.trifft(pos, rad, t1, 100, 100), randA: G.trifft(pos, rad, t1, 100 + 21, 100), ausserhalb: G.trifft(pos, rad, t1, 100 + 23, 100),
               zoomRand: G.trifft(pos, rad, t05, 50 + 21, 50), zoomAus: G.trifft(pos, rad, t05, 50 + 23, 50), leer: G.trifft(pos, rad, t1, 200, 300), keine: G.trifft({}, {}, t1, 1, 1) };'''
    r = js(code)
    assert r == {"mitteA": "a", "randA": "a", "ausserhalb": None, "zoomRand": "a", "zoomAus": None, "leer": None, "keine": None}


def test_trifft_waehlt_den_naechsten_knoten_und_beachtet_verschiebung():
    code = '''const pos = { a: { x: 100, y: 100 }, b: { x: 120, y: 100 } }, rad = { a: 6, b: 6 };
      return [G.trifft(pos, rad, { k: 1, tx: 0, ty: 0 }, 104, 100), G.trifft(pos, rad, { k: 1, tx: 0, ty: 0 }, 116, 100),
              G.trifft(pos, rad, { k: 2, tx: -100, ty: -100 }, 100, 100), G.trifft({ g: { x: 50, y: 50 } }, { g: 16 }, { k: 1, tx: 0, ty: 0 }, 50 + 30, 50)];'''
    assert js(code) == ["a", "b", "a", None]                      # 30 px neben dem grossen Fokus (Radius 16, Treffer 22) ist daneben


# --- kuerze und beschriftungen ------------------------------------------------------------------------------------

def test_kuerze_schneidet_auf_die_breite_und_haengt_punkte_an():
    r = js('return [G.kuerze("kurz", 100, messe), G.kuerze("Ein sehr langer Titel der nicht passt", 100, messe), G.kuerze("x", 3, messe), G.kuerze("", 50, messe)];')
    assert r[0] == "kurz" and r[1].endswith("…") and len(r[1]) * 7 <= 100 and len(r[1]) > 5 and r[2] == "" and r[3] == ""


def _rechtecke(lab):
    return [(v["x"], v["y"], v["x"] + v["w"], v["y"] + v["h"]) for v in lab.values()]


def _ueberlappen(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def test_beschriftungen_ueberlappen_nicht_und_liegen_in_der_flaeche():
    for b, h in ((960, 600), (600, 960), (600, 400)):
        n = netz()
        r = js(f'''const lay = GL.ordne(d, {b}, {h}); return G.beschriftungen(d.knoten, lay.positionen, lay.radius, {{ breite: {b}, hoehe: {h} }}, messe);''', n)
        rects = _rechtecke(r)
        assert "f" in r and all(i.startswith("a") or i == "f" for i in r)             # Ring 2 hat nie eine Beschriftung
        assert all(0 <= x0 and 0 <= y0 and x1 <= b and y1 <= h for x0, y0, x1, y1 in rects), (b, h)
        assert not any(_ueberlappen(rects[i], rects[j]) for i in range(len(rects)) for j in range(i + 1, len(rects))), (b, h)


def test_beschriftungen_ueberdecken_keine_knoten_und_der_fokus_steht_darunter():
    b, h = 960, 600
    r = js(f'''const lay = GL.ordne(d, {b}, {h}); return [G.beschriftungen(d.knoten, lay.positionen, lay.radius, {{ breite: {b}, hoehe: {h} }}, messe), lay];''', netz())
    lab, lay = r
    f = lay["positionen"]["f"]
    assert lab["f"]["y"] > f["y"] + lay["radius"]["f"] - 1 and lab["f"]["ausrichtung"] == "mitte"
    for i, l in lab.items():
        for k, p in lay["positionen"].items():
            if k == i:
                continue
            nx, ny = min(max(p["x"], l["x"]), l["x"] + l["w"]), min(max(p["y"], l["y"]), l["y"] + l["h"])
            assert ((p["x"] - nx) ** 2 + (p["y"] - ny) ** 2) ** 0.5 >= lay["radius"][k] - 0.5, (i, k)       # kein Knoten unter einem Text


def test_beschriftungen_kuerzen_lange_titel_und_beschriften_im_querformat_fast_alle():
    b, h = 960, 600
    lab = js(f'''const lay = GL.ordne(d, {b}, {h}); return G.beschriftungen(d.knoten, lay.positionen, lay.radius, {{ breite: {b}, hoehe: {h} }}, messe);''', netz())
    assert all(v["w"] <= 150 * 1.4 + 8 for v in lab.values()) and all(v["w"] <= 158 for i, v in lab.items() if i != "f") and any(v["text"].endswith("…") for v in lab.values())
    assert sum(1 for i in lab if i.startswith("a")) >= 11                                    # 14 Nachbarn: mindestens 11 sind beschriftet


def test_zusaetzliche_beschriftung_fuer_einen_ring_2_knoten_und_wegfall_bei_platzmangel():
    b, h = 960, 600
    lab = js(f'''const lay = GL.ordne(d, {b}, {h}); return G.beschriftungen(d.knoten, lay.positionen, lay.radius, {{ breite: {b}, hoehe: {h} }}, messe, {{ zusaetzlich: ["b3"] }});''', netz())
    assert "b3" in lab and "b4" not in lab
    eng = js('''const lay = GL.ordne(d, 200, 120); return G.beschriftungen(d.knoten, lay.positionen, lay.radius, { breite: 200, hoehe: 120 }, messe);''', netz())
    assert isinstance(eng, dict)                                                             # keine Ausnahme; was nicht passt, fehlt einfach


# --- uebergang --------------------------------------------------------------------------------------------------

def test_uebergang_liefert_an_den_enden_die_endwerte_und_blendet_neue_knoten_ein():
    code = '''const von = { positionen: { a: { x: 0, y: 0 }, alt: { x: 10, y: 10 } }, radius: { a: 5, alt: 5 } };
      const nach = { positionen: { a: { x: 100, y: 50 }, neu: { x: 20, y: 20 } }, radius: { a: 9, neu: 5 } };
      return [G.uebergang(von, nach, 0), G.uebergang(von, nach, 1), G.uebergang(von, nach, 0.5)];'''
    z0, z1, zm = js(code)
    assert z0["positionen"]["a"] == {"x": 0, "y": 0} and z0["alpha"]["alt"] == 1 and z0["alpha"]["neu"] == 0 and "neu" in z0["positionen"]
    assert z1["positionen"]["a"] == {"x": 100, "y": 50} and z1["alpha"]["neu"] == 1 and "alt" not in z1["positionen"]
    assert 0 < zm["positionen"]["a"]["x"] < 100 and abs(zm["positionen"]["a"]["x"] - 50) < 1e-9 and 5 < zm["radius"]["a"] < 9
    assert abs(zm["alpha"]["alt"] - 0.5) < 1e-9 and abs(zm["alpha"]["neu"] - 0.5) < 1e-9


# --- zeichne (Aufzeichnungs-Canvas) -----------------------------------------------------------------------------------

AUFZEICHNUNG = '''
const aufruf = [];
const ctx = new Proxy({}, { get: (_, name) => name === "aufruf" ? aufruf : (...a) => { aufruf.push([name, ...a]); return undefined; },
                            set: (_, name, wert) => { aufruf.push(["set:" + name, wert]); return true; } });
const farben = { bg: "#14130f", text: "#ece8de", gedaempft: "#9a9486", akzent: "#4fc3d9", linie: "#38352d", dunkel: true };
function lauf(daten, auswahl, t) {
  const b = 960, h = 600, lay = GL.ordne(daten, b, h);
  const labels = G.beschriftungen(daten.knoten, lay.positionen, lay.radius, { breite: b, hoehe: h }, messe);
  aufruf.length = 0;
  G.zeichne(ctx, { knoten: daten.knoten, kanten: daten.kanten, positionen: lay.positionen, radius: lay.radius, labels: labels }, t || { k: 1, tx: 0, ty: 0 }, farben,
            { breite: b, hoehe: h, dpr: 2, ausgewaehlt: auswahl || null });
  return aufruf.slice();
}
'''


def test_zeichne_beschriftet_fokus_und_ring_1_aber_nie_ring_2_und_zeichnet_querverweise_gestrichelt():
    r = js(AUFZEICHNUNG + 'const a = lauf(d); return { texte: a.filter(x => x[0] === "fillText").map(x => x[1]), strich: a.filter(x => x[0] === "setLineDash").map(x => x[1].length), anzahl: a.length };', netz())
    assert any(t.startswith("Fokus · Das Kapitel") for t in r["texte"])
    assert any(t.startswith("Nachname") for t in r["texte"]) and not any(t.startswith("Zweiter Ring") for t in r["texte"])
    assert "ergänzt" in r["texte"]                                                            # Beschriftung der Querverweis-Kante
    assert 2 in r["strich"] and 0 in r["strich"]                                              # gestrichelt gezeichnet, danach wieder durchgezogen


def test_zeichne_setzt_hochaufloesung_und_farben_und_wirft_nie():
    r = js(AUFZEICHNUNG + 'const a = lauf(d, "a2"); return { transform: a.find(x => x[0] === "setTransform"), hatBg: a.some(x => x[0] === "set:fillStyle" && x[1] === "#14130f"), anzahl: a.length };', netz())
    assert r["transform"][1:3] == [2, 0] and r["hatBg"] and r["anzahl"] > 100
    r = js(AUFZEICHNUNG + 'return [lauf({ knoten: [], kanten: [] }).length > 0, lauf({ knoten: [{ id: "x", typ: "werk", ring: 0, label: "Nur", werk: null, offen: false }], kanten: [] }).length > 0];', None)
    assert r == [True, True]


def test_zeichne_unterscheidet_knotenarten_und_hohle_werke():
    n = netz(3, 0)
    n["knoten"].append({"id": "w", "typ": "werk", "ring": 1, "label": "Werk", "werk": "b001", "offen": True})
    n["knoten"].append({"id": "x", "typ": "werk", "ring": 1, "label": "Extern", "werk": None, "offen": False})
    r = js(AUFZEICHNUNG + 'const a = lauf(d); return { fuellungen: a.filter(x => x[0] === "fill").length, striche: a.filter(x => x[0] === "stroke").length, rauten: a.filter(x => x[0] === "closePath").length };', n)
    assert r["fuellungen"] > 4 and r["striche"] > 4 and r["rauten"] >= 1                     # Themen sind Rauten (Pfad mit closePath)


def test_werkfarbe_ist_stabil_und_unterscheidet_werke():
    r = js('return [G.werkFarbe("b001", true), G.werkFarbe("b001", true), G.werkFarbe("b002", true), G.werkFarbe("b001", false), G.werkFarbe(null, true)];')
    assert r[0] == r[1] and r[0] != r[2] and r[0] != r[3] and isinstance(r[4], str) and r[4]
