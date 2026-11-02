"""Tests fuer die Fussnotenanalyse (P2 Task 6). Die Vektoren in testvektoren_fussnoten.json sind von Hand
geschrieben und gelten auch fuer fussnoten.js (speedreader_web/test_fussnoten_js.py)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from redaktion import fussnoten

V = json.loads((Path(__file__).parent / "testvektoren_fussnoten.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("v", V["analysen"], ids=[v["name"] for v in V["analysen"]])
def test_analyse_vektor(v):
    assert fussnoten.analysiere(v["text"]) == v["erwartet"]


@pytest.mark.parametrize("v", V["bilanzen"], ids=[v["name"] for v in V["bilanzen"]])
def test_bilanz_vektor(v):
    assert fussnoten.bilanz(v["vorher"], v["nachher"]) == v["erwartet"]


def test_marker_vorkommen_passt_zu_ops_marker_umbenennen():
    """Die Angaben der Analyse (absatz_index, vorkommen) sind genau die Ziele, die ops.py versteht."""
    from episto_tui.korrektur import absatz_spannen
    from redaktion import ops
    text = "Kopf\n\nA[^2] und B[^2] und C[^1].\n\n[^1]: eins\n[^2]: zwei"
    ana = fussnoten.analysiere(text)
    zweiter = [m for m in ana["marker"] if m["id"] == "2"][1]
    a, b = absatz_spannen(text)[zweiter["absatz_index"]]
    e = ops.neuer_eintrag("A/T", "volltext", {"absatz_index": zweiter["absatz_index"], "anfang": ops.anker_von(text[a:b])},
                          "fussnote", {"aktion": "marker-umbenennen", "alt": "2", "neu": "9",
                                       "vorkommen": zweiter["vorkommen"]}, text[a:b])
    erg = ops.wende_an(text, e)
    assert erg.status == "angewendet" and "A[^2] und B[^9]" in erg.text


def test_leistung_eine_million_zeichen():
    absatz = "Ein Satz mit Verweis[^1] und noch einem[^2] Text, der weitergeht.\n"
    text = "\n\n".join(absatz * 3 for _ in range(1_000_000 // (len(absatz) * 3 + 2))) + "\n\n[^1]: eins\n[^2]: zwei"
    t0 = time.perf_counter()
    ana = fussnoten.analysiere(text)
    assert time.perf_counter() - t0 < 1.0
    assert ana["bilanz"]["definitionen"] == 2 and ana["bilanz"]["marker"] > 10000
