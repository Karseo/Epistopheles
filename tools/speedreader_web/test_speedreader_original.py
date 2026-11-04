"""Speedreader mit Originaltext: speedreader.js baueWoerterAusBloecken (Node; ohne Node uebersprungen)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node nicht installiert")

SKRIPT = r"""
const S = require(process.argv[1]), L = require(process.argv[2]);
const e = JSON.parse(require("fs").readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(new Function("S", "L", "t", e.code)(S, L, e.text)));
"""


def js(code, text=""):
    r = subprocess.run([NODE, "-e", SKRIPT, str(HIER / "speedreader.js"), str(HIER / "lesetext.js")], input=json.dumps({"code": code, "text": text}),
                       capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(r.stdout)


BAU = "const r = S.baueWoerterAusBloecken(L.parse(t), 'Kap'); return {namen: r.namen, w: r.woerter.map(x => [x.text, x.abschnitt, x.satzende, x.faktor])};"


def test_ueberschriften_beginnen_abschnitte_und_text_davor_heisst_anfang():
    r = js(BAU, "Vorspann hier.\n\n# Kapitel *Eins*\n\nText danach.\n\n## Unterpunkt\n\nNoch mehr.\n")
    assert r["namen"] == ["Kap", "Kapitel Eins", "Unterpunkt"]
    assert [w[0] for w in r["w"]] == ["Vorspann", "hier.", "Kapitel", "Eins", "Text", "danach.", "Unterpunkt", "Noch", "mehr."]
    assert [w[1] for w in r["w"]] == [0, 0, 1, 1, 1, 1, 2, 2, 2]


def test_seiten_bilder_linien_und_fussnotentexte_werden_uebersprungen_marken_entfallen():
    r = js(BAU, "Satz mit Marke[^1] und Link [hier](http://x.de).\n\n## Seite 12\n\n---\n\n<img alt=\"Abb\" src=\"a.png\">\n\n[^1]: Fussnotentext nie lesen\n")
    assert [w[0] for w in r["w"]] == ["Satz", "mit", "Marke", "und", "Link", "hier."]


def test_absatzende_ist_satzende_mit_mindestens_doppelter_dauer_listen_und_zitate_zaehlen():
    r = js(BAU, "Erster Absatz ohne Punkt\n\n- Listenpunkt\n\n> Zitat hier\n")
    ende = [w for w in r["w"] if w[2]]
    assert [w[0] for w in ende] == ["Punkt", "Listenpunkt", "hier"] and all(w[3] >= 2.0 for w in ende)


def test_leere_oder_kaputte_eingaben_geben_keine_woerter():
    r = js("return [S.baueWoerterAusBloecken([], 'x'), S.baueWoerterAusBloecken(null), S.baueWoerterAusBloecken([null, {typ:'p'}, {typ:'p', text:'  '}, {typ:'h', text:'**'}])];")
    assert all(x == {"woerter": [], "namen": []} for x in r)


def test_lange_ueberschrift_wird_im_namen_gekuerzt_aber_ganz_gelesen():
    r = js(BAU, "# " + " ".join(["Wort"] * 40) + "\n")
    assert len(r["namen"][0]) <= 60 and r["namen"][0].endswith("…") and len(r["w"]) == 40


def test_baueWoerter_der_ki_felder_bleibt_unveraendert():
    r = js("return S.baueWoerter({zusammenfassung: 'Ein Satz hier.', these: ['A b', 'C d.']});")
    assert r["namen"] == ["Zusammenfassung", "Thesen"] and [w["text"] for w in r["woerter"]] == ["Zusammenfassung", "Ein", "Satz", "hier.", "Thesen", "A", "b", "C", "d."]
