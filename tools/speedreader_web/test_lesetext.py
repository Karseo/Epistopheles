"""Tests fuer lesetext.js (Markdown-Zerlegung des Originaltexts). Laeuft in Node;
ohne Node werden die Tests uebersprungen."""
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
const { funktion, eingabe } = JSON.parse(require("fs").readFileSync(0, "utf8"));
const aus = funktion === "parse" ? L.parse(eingabe)
          : funktion === "inline" ? L.inline(eingabe)
          : [...L.fussnotenNummern(L.parse(eingabe))];
process.stdout.write(JSON.stringify(aus));
"""


def js(funktion: str, eingabe: str):
    lauf = subprocess.run([NODE, "-e", SKRIPT, str(HIER / "lesetext.js")],
                          input=json.dumps({"funktion": funktion, "eingabe": eingabe}),
                          capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(lauf.stdout)


def test_bloecke_ueberschrift_absatz_seite_liste_zitat_fussnote_linie():
    md = ("# Titel\n\n## Seite 12\n\nZeile a\nZeile b\n\n> Zitat a\n> Zitat b\n\n- eins\n- zwei\n\n"
          "1. nummeriert\n\n[^1]: Anmerkung\n\n---\n")
    assert js("parse", md) == [
        {"typ": "h", "stufe": 1, "text": "Titel"},
        {"typ": "seite", "text": "Seite 12"},
        {"typ": "p", "text": "Zeile a Zeile b"},
        {"typ": "zitat", "text": "Zitat a Zitat b"},
        {"typ": "li", "text": "eins"}, {"typ": "li", "text": "zwei"}, {"typ": "li", "text": "nummeriert"},
        {"typ": "fn", "id": "1", "text": "Anmerkung"},
        {"typ": "hr"},
    ]


def test_roh_html_faellt_weg_bilder_behalten_ihren_alternativtext():
    md = ('<figure>\n<span id="x" class="pagebreak"></span><img src="a.png" alt="Eine Zeichnung" />\n</figure>\n\n'
          "Text mit <b>Tag</b> darin.\n\n<div>\n")
    assert js("parse", md) == [{"typ": "bild", "text": "Eine Zeichnung"},
                               {"typ": "p", "text": "Text mit Tag darin."}]


def test_leer_und_crlf():
    assert js("parse", "") == []
    assert js("parse", "A\r\nB\r\n\r\nC") == [{"typ": "p", "text": "A B"}, {"typ": "p", "text": "C"}]


def test_sternchen_am_zeilenanfang_ist_kein_listenpunkt():
    assert js("parse", "*oinops* heisst Wein") == [{"typ": "p", "text": "*oinops* heisst Wein"}]


def test_inline_auszeichnungen():
    seg = js("inline", "Er *betont* **fett** _kurz_ Gegner_innen[^3] [Link](http://x) <b>tag</b>")
    assert {"t": "betont", "em": True} in seg
    assert {"t": "fett", "b": True} in seg
    assert {"t": "kurz", "em": True} in seg
    assert {"t": "", "fn": "3"} in seg
    assert "".join(s["t"] for s in seg) == "Er betont fett kurz Gegner_innen Link tag"   # Unterstrich im Wort bleibt


def test_inline_maskierte_zeichen_bleiben_woertlich():
    seg = js("inline", "a \\*frei\\* b")
    assert "".join(s["t"] for s in seg) == "a *frei* b"
    assert not any(s.get("em") for s in seg)


def test_fussnoten_werden_in_reihenfolge_des_vorkommens_nummeriert():
    md = "Text[^b] und[^a].\n\n[^a]: A\n[^b]: B\n[^z]: unbenutzt"
    assert js("nummern", md) == [["b", 1], ["a", 2], ["z", 3]]
