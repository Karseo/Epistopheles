"""Paritaet von fussnoten.js mit fussnoten.py (gemeinsame Vektoren). Ohne Node uebersprungen."""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

from redaktion import fussnoten  # noqa: E402

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node nicht installiert")
V = json.loads((HIER.parent / "redaktion" / "testvektoren_fussnoten.json").read_text(encoding="utf-8"))

SKRIPT = r"""
const F = require(process.argv[1]);
const a = JSON.parse(require("fs").readFileSync(0, "utf8"));
const t0 = Date.now();
let aus;
if (a.funktion === "analysiere") aus = a.texte.map((t) => F.analysiere(t));
else aus = a.paare.map(([x, y]) => F.bilanz(x, y));
process.stdout.write(JSON.stringify({ aus: aus, ms: Date.now() - t0 }));
"""


def js(**kw):
    lauf = subprocess.run([NODE, "-e", SKRIPT, str(HIER / "fussnoten.js")], input=json.dumps(kw),
                          capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(lauf.stdout)


def test_analyse_vektoren_in_js():
    erg = js(funktion="analysiere", texte=[v["text"] for v in V["analysen"]])["aus"]
    for v, e in zip(V["analysen"], erg):
        assert e == v["erwartet"], v["name"]


def test_bilanz_vektoren_in_js():
    erg = js(funktion="bilanz", paare=[[v["vorher"], v["nachher"]] for v in V["bilanzen"]])["aus"]
    for v, e in zip(V["bilanzen"], erg):
        assert e == v["erwartet"], v["name"]


def test_js_stimmt_mit_python_bei_randfaellen_ueberein():
    texte = [
        "Kopf 😀\n\nA[^ä] B[^😀] C[^a b] D[^]\n\n[^ä]: ä\n[^😀]: smile\n[^]: leer",
        "Text[^1] und[^1:] X\n\n[^1]:kein Leerzeichen\n[^1]: doppelt",
        "Zeile\r\n\r\n12 Eins\r\n*3 Zwei\r\n4) Drei\r\n5. Vier",
        "# 12 Kopf\n\n1 a\n2 b\n\n\n\n3 c",
    ]
    erg = js(funktion="analysiere", texte=texte)["aus"]
    for t, e in zip(texte, erg):
        assert e == fussnoten.analysiere(t), t


def test_leistung_eine_million_zeichen():
    absatz = "Ein Satz mit Verweis[^1] und noch einem[^2] Text, der weitergeht.\n"
    text = "\n\n".join(absatz * 3 for _ in range(1_000_000 // (len(absatz) * 3 + 2))) + "\n\n[^1]: eins\n[^2]: zwei"
    r = js(funktion="analysiere", texte=[text])
    assert r["ms"] < 1000                         # Plan: Ziel 300 ms, grosszuegige Grenze 1000 ms
    assert r["aus"][0] == fussnoten.analysiere(text)
