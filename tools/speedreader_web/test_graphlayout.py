"""Tests fuer graphlayout.js (Anordnung des Fokusnetzes): deterministisch, innerhalb der Flaeche, ohne Ueberlappung. Node; ohne Node uebersprungen."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node nicht installiert")

SKRIPT = r"""
const L = require(process.argv[1]);
const e = JSON.parse(require("fs").readFileSync(0, "utf8"));
const t0 = Date.now();
const f = new Function("L", "d", "return (() => {" + e.code + "})();");
const r = f(L, e.daten);
process.stdout.write(JSON.stringify({ r: r, ms: Date.now() - t0 }));
"""


def js(code, daten=None):
    lauf = subprocess.run([NODE, "-e", SKRIPT, str(HIER / "graphlayout.js")], input=json.dumps({"code": code, "daten": daten}),
                          capture_output=True, text=True, encoding="utf-8", check=True)
    erg = json.loads(lauf.stdout)
    return erg["r"], erg["ms"]


def netz(n1=14, n2=14, kanten=True):
    """Fokus 'f', Ring 1 'a0..', Ring 2 'b0..' (je an einen Ring-1-Knoten gebunden), Kanten Fokus-Ring1 und eine zwischen Ring-1-Knoten."""
    knoten = [{"id": "f", "ring": 0}] + [{"id": f"a{i}", "ring": 1} for i in range(n1)] + [{"id": f"b{i}", "ring": 2, "ueber": f"a{i % max(1, n1)}"} for i in range(n2)]
    ks = [{"von": "f", "nach": f"a{i}", "art": "aehnlich", "wert": 0.7} for i in range(n1)] + ([{"von": "a0", "nach": "a1", "art": "aehnlich", "wert": 0.6}] if n1 > 1 and kanten else [])
    return {"knoten": knoten, "kanten": ks if kanten else []}


CODE = "return L.ordne(d, 600, 400);"


def test_deterministisch():
    a, _ = js(CODE, netz())
    b, _ = js(CODE, netz())
    assert a == b and len(a["positionen"]) == 29


def test_alle_knoten_innerhalb_der_flaeche_mit_rand_und_nur_endliche_zahlen():
    r, _ = js("return L.ordne(d, 600, 400, { rand: 24 });", netz())
    for i, p in r["positionen"].items():
        rad = r["radius"][i]
        assert all(isinstance(v, (int, float)) for v in (p["x"], p["y"])) and p["x"] == p["x"] and p["y"] == p["y"]
        assert 24 - 0.01 <= p["x"] - rad and p["x"] + rad <= 600 - 24 + 0.01, i
        assert 24 - 0.01 <= p["y"] - rad and p["y"] + rad <= 400 - 24 + 0.01, i


def test_fokus_liegt_in_der_mitte_und_hat_den_groessten_radius():
    r, _ = js(CODE, netz())
    assert abs(r["positionen"]["f"]["x"] - 300) < 1 and abs(r["positionen"]["f"]["y"] - 200) < 1
    assert r["radius"]["f"] > r["radius"]["a0"] > r["radius"]["b0"]


def test_keine_zwei_knoten_naeher_als_die_summe_ihrer_radien():
    for n1, n2 in ((14, 14), (10, 14), (14, 11), (3, 3), (1, 5)):
        r, _ = js(CODE, netz(n1, n2))
        p, rad = r["positionen"], r["radius"]
        ids = list(p)
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                d = ((p[ids[a]]["x"] - p[ids[b]]["x"]) ** 2 + (p[ids[a]]["y"] - p[ids[b]]["y"]) ** 2) ** 0.5
                assert d >= rad[ids[a]] + rad[ids[b]] - 0.5, (n1, n2, ids[a], ids[b], d)


def test_ring_2_liegt_im_mittel_weiter_aussen_als_ring_1():
    r, _ = js(CODE, netz())
    mitte = r["positionen"]["f"]
    def mittel(praefix):
        ds = [((p["x"] - mitte["x"]) ** 2 + (p["y"] - mitte["y"]) ** 2) ** 0.5 for i, p in r["positionen"].items() if i.startswith(praefix)]
        return sum(ds) / len(ds)
    assert mittel("b") > mittel("a") > 40


def test_ring_2_knoten_liegen_nahe_ihrem_ring_1_knoten():
    r, _ = js(CODE, netz(14, 14))
    p = r["positionen"]
    def d(a, b):
        return ((p[a]["x"] - p[b]["x"]) ** 2 + (p[a]["y"] - p[b]["y"]) ** 2) ** 0.5
    nah = sum(d(f"b{i}", f"a{i}") <= min(d(f"b{i}", f"a{j}") for j in range(14) if j != i) + 1e-9 for i in range(14))
    assert nah >= 12                                                                  # fast jeder liegt bei seinem eigenen Ring-1-Knoten


def test_ohne_iterationen_liegen_die_ringe_auf_ellipsen():
    r, _ = js("return L.ordne(d, 600, 400, { iterationen: 0, rand: 24 });", netz(8, 0))
    p = r["positionen"]
    werte = [(((p[f"a{i}"]["x"] - 300) / (276 * 0.55)) ** 2 + ((p[f"a{i}"]["y"] - 200) / (176 * 0.55)) ** 2) ** 0.5 for i in range(8)]
    assert all(abs(w - 1) < 0.02 for w in werte)


def test_leistung_40_knoten():
    r, ms = js(CODE, netz(20, 19))
    assert len(r["positionen"]) == 40 and ms < 200                                    # Plan: Ziel 50 ms, grosszuegige Grenze 200 ms


def test_randfaelle_ohne_ausnahme():
    r, _ = js("return [L.ordne({ knoten: [], kanten: [] }, 600, 400), L.ordne(null, 600, 400), L.ordne(d, 600, 400)];", {"knoten": [{"id": "x", "ring": 0}], "kanten": []})
    assert r[0] == {"positionen": {}, "radius": {}} and r[1] == {"positionen": {}, "radius": {}}
    assert abs(r[2]["positionen"]["x"]["x"] - 300) < 1
    # ohne ueber, unbekannter Ring, Kante auf unbekannte Id, doppelte Ids, winzige oder ungueltige Flaeche: nie Ausnahme, nie NaN
    d = {"knoten": [{"id": "f", "ring": 0}, {"id": "a", "ring": 1}, {"id": "b", "ring": 2}, {"id": "c", "ring": 7}, {"id": "a", "ring": 1}, {"nope": 1}],
         "kanten": [{"von": "f", "nach": "gibt-es-nicht"}, {"von": "a", "nach": "a"}, None]}
    r, _ = js("return [L.ordne(d, 600, 400), L.ordne(d, 50, 40), L.ordne(d, 0, 0), L.ordne(d, NaN, undefined)];", d)
    for erg in r:
        assert set(erg["positionen"]) == {"f", "a", "b", "c"}
        assert all(v == v and abs(v) < 1e6 for p in erg["positionen"].values() for v in p.values())


def test_viele_knoten_und_kleine_flaeche_bleiben_endlich_und_innerhalb():
    r, _ = js("return L.ordne(d, 260, 180, { rand: 16 });", netz(30, 30))
    for i, p in r["positionen"].items():
        assert 0 <= p["x"] <= 260 and 0 <= p["y"] <= 180, i


def test_hochformat_und_querformat_nutzen_die_flaeche():
    quer, _ = js("return L.ordne(d, 960, 400);", netz())
    hoch, _ = js("return L.ordne(d, 400, 960);", netz())
    def spanne(r, achse):
        w = [p[achse] for p in r["positionen"].values()]
        return max(w) - min(w)
    assert spanne(quer, "x") > spanne(quer, "y") and spanne(hoch, "y") > spanne(hoch, "x")
