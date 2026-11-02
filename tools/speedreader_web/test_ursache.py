"""Tests fuer ursache.js ("Ursache suchen", P2 Task 13): reine Funktionen, laufen in Node. Ohne Node uebersprungen."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node nicht installiert")

SKRIPT = r"""
const U = require(process.argv[1]);
const a = JSON.parse(require("fs").readFileSync(0, "utf8"));
const t0 = Date.now();
const aus = a.faelle.map((f) => {
  if (f.fn === "suche") return U.suche(f.absatz, f.quellen, f.optionen);
  if (f.fn === "tokenisiere") return U.tokenisiere(f.text).map((t) => [t.w, f.text.slice(t.von, t.bis)]);
  if (f.fn === "bereinige") return U.bereinige(f.text);
  if (f.fn === "finde") { const r = U.finde(f.text, f.fenster); return r && [r.von, r.bis, f.text.slice(r.von, r.bis)]; }
  if (f.fn === "fenster") return U.fenster(f.woerter);
});
process.stdout.write(JSON.stringify({ aus: aus, ms: Date.now() - t0 }));
"""


def lauf(*faelle):
    r = subprocess.run([NODE, "-e", SKRIPT, str(HIER / "ursache.js")], input=json.dumps({"faelle": list(faelle)}),
                       capture_output=True, text=True, encoding="utf-8", check=True)
    d = json.loads(r.stdout)
    return d["aus"] if len(faelle) > 1 else d["aus"][0], d["ms"]


def suche(absatz, quellen, **opt):
    return lauf({"fn": "suche", "absatz": absatz, "quellen": quellen, "optionen": opt})[0]


SATZ1 = "Der Repräsentant ist nicht bloß ein Delegierter der Wähler, wie Pitkin in ihrer Studie betonte, dass die Abgeordneten ihr Urteil nicht bloß weitergeben."
SATZ2 = "Repräsentation erfordert Distanz und Responsivität, damit das Volk das Handeln derer beurteilen kann, die in seinem Namen handeln."
FUELL = "Ganz anderer Text ohne jede Überschneidung mit den gesuchten Sätzen steht hier und füllt den Chunk auf."


def test_tokenisiere_fuegt_silbentrennung_am_zeilenende_zusammen_aber_nicht_bei_grossbuchstabe():
    erg, _ = lauf({"fn": "tokenisiere", "text": "Die Reprä-\nsentation und Mehr-\nEbenen, sowie Wort­teil 12 [^3]"})
    assert [w for w, _ in erg] == ["die", "repräsentation", "und", "mehr", "ebenen", "sowie", "wortteil"]
    assert erg[1][1] == "Reprä-\nsentation"                       # Position umfasst beide Teile


def test_bereinige_entfernt_marker_html_und_links():
    erg, _ = lauf({"fn": "bereinige", "text": "Satz[^12] mit <span class=\"x\">HTML</span> und [Link](http://x.de) Ende"})
    assert "[^" not in erg and "<" not in erg and "http" not in erg and "Link" in erg and "HTML" in erg


def test_eindeutig_trotz_fussnotenmarker_und_silbentrennung():
    absatz = SATZ1.replace("Repräsentant", "Repräsentant[^1]").replace("Delegierter", "**Delegierter**")
    quellen = [FUELL, SATZ1.replace("Repräsentant ist", "Reprä-\nsentant ist") + " " + FUELL, FUELL]
    erg = suche(absatz, quellen)
    assert erg["art"] == "eindeutig" and [t["chunk"] for t in erg["treffer"]] == [1]
    t = erg["treffer"][0]
    assert t["anzahl"] == 3 and t["fenster"].startswith("der repräsentant") and quellen[1][t["versatz"]:].startswith("Der Reprä-\nsentant")
    assert t["laenge"] > 20


def test_mehrdeutig_wenn_der_satz_in_zwei_chunks_steht():
    erg = suche(SATZ1, [SATZ1, FUELL, SATZ1])
    assert erg["art"] == "mehrdeutig" and [t["chunk"] for t in erg["treffer"]] == [0, 2]


def test_absatz_ueber_chunkgrenze_ist_mehrdeutig_nie_geraten():
    erste, zweite = SATZ1[:60], SATZ1[60:]
    erg = suche(SATZ1, [erste, zweite, FUELL])
    assert erg["art"] == "mehrdeutig" and sorted(t["chunk"] for t in erg["treffer"]) == [0, 1]


def test_ein_einziges_stueck_bei_mehreren_fenstern_ist_nur_mehrdeutig():
    kurz = " ".join(SATZ1.split()[:6])                          # nur das erste Fenster findet sich
    erg = suche(SATZ1, [kurz, FUELL])
    assert erg["art"] == "mehrdeutig" and len(erg["treffer"]) == 1 and erg["treffer"][0]["anzahl"] == 1


def test_keine_und_zu_kurz():
    assert suche(SATZ1, [FUELL, FUELL])["art"] == "keine"
    e = suche("Zu kurz hier", [FUELL])
    assert e["art"] == "keine" and "zu kurz" in e["grund"]


def test_kurzer_absatz_mit_einem_fenster_ist_eindeutig_bei_einem_treffer():
    erg = suche("Der Wähler urteilt selbst.", ["nichts " + FUELL, "Der Wähler urteilt selbst und mehr."])
    assert erg["art"] == "eindeutig" and erg["treffer"][0]["chunk"] == 1


def test_bereich_begrenzt_die_suche():
    quellen = [SATZ1, FUELL, SATZ1]
    assert suche(SATZ1, quellen)["art"] == "mehrdeutig"
    erg = suche(SATZ1, quellen, bereich=[1, 2])
    assert erg["art"] == "eindeutig" and erg["treffer"][0]["chunk"] == 2
    assert suche(SATZ1, quellen, bereich=[1, 1])["art"] == "keine"


def test_finde_im_angezeigten_text_gibt_genau_die_stelle():
    text = "Vorspann.\n\nDer Repräsentant\tist nicht bloß ein Delegierter der Wähler."
    erg, _ = lauf({"fn": "finde", "text": text, "fenster": "der repräsentant ist nicht bloß ein"})
    assert erg[2] == "Der Repräsentant\tist nicht bloß ein"
    assert lauf({"fn": "finde", "text": text, "fenster": "gibt es nicht"})[0] is None


def test_leistung_500_chunks():
    quellen = [(FUELL + " ") * 60 for _ in range(500)]            # ca. 6000 Zeichen je Chunk
    quellen[321] = quellen[321] + SATZ2
    erg, ms = lauf({"fn": "suche", "absatz": SATZ2, "quellen": quellen, "optionen": {}})
    assert erg["art"] == "eindeutig" and erg["treffer"][0]["chunk"] == 321
    assert ms < 1500                                              # Plan: Ziel 500 ms, großzügige Grenze 1500 ms
