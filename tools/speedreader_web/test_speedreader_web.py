"""Tests fuer den Web-Speedreader (Epistopheles): die JS-Portierung muss dasselbe
liefern wie episto_tui/speedreader.py, und der Export muss das erwartete Format
haben. Der Paritaetstest braucht Node; ohne Node wird er uebersprungen."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent))

from episto_tui import speedreader as sr  # noqa: E402
from episto_tui.models import Tag  # noqa: E402
import export_daten  # noqa: E402

NODE = shutil.which("node")

FAELLE = [
    dict(zusammenfassung="Ein kurzer Satz.", these=["Erste These.", "Zweite These"], gegen=[],
         kern=["Habitus"], **{"def": []}, beleg=["Beleg eins"]),
    dict(zusammenfassung="", these=["Satz [^12] mit Note [^a3]."], gegen=[], kern=[], **{"def": []}, beleg=[]),
    dict(zusammenfassung="", these=["Erste Aussage[^3]. Zweite – Aussage[^4] !"], gegen=[], kern=[],
         **{"def": []}, beleg=[]),
    dict(zusammenfassung="*Betont* und _kursiv_ sowie Gegner_innen, „zitiert“ (Klammer) «Zitat».",
         these=[], gegen=["Rechtsschutzversicherungsunternehmen, wirklich?!"], kern=["a", "zu", "Macht"],
         **{"def": ["Substantiell: ein Wort"]}, beleg=["Äpfel – Öl; Übel… Ende."]),
    dict(zusammenfassung="", these=[], gegen=[], kern=[], **{"def": []}, beleg=[]),
    dict(zusammenfassung="Mehrere   Leerzeichen\nund\tTabs. Zweiter Satz! Dritter Satz? Vierter…",
         these=["Eins", "Zwei drei"], gegen=["x"], kern=["(Substantiell,"], **{"def": ["Habitus"]},
         beleg=["Marx 1867, S. 12."]),
]

NODE_SKRIPT = r"""
const SR = require(process.argv[1]);   // bei "node -e" ist das erste Argument argv[1]
const faelle = JSON.parse(require("fs").readFileSync(0, "utf8"));
const aus = faelle.map((f) => {
  const { woerter, namen } = SR.baueWoerter(f);
  const n = woerter.length;
  return {
    namen,
    woerter: woerter.map((w) => ({ text: w.text, abschnitt: w.abschnitt, marke: w.marke, satzende: w.satzende,
                                    faktor: w.faktor, teile: SR.teileWort(w) })),
    saetze: n ? [...Array(n).keys()].map((i) => [SR.voriger_satzanfang(woerter, i), SR.naechster_satzanfang(woerter, i),
                                                 SR.voriger_abschnitt(woerter, i), SR.naechster_abschnitt(woerter, i)]) : [],
    rest: n ? [SR.restdauer(woerter, 0, 300), SR.restdauer(woerter, n - 1, 900)] : [],
  };
});
process.stdout.write(JSON.stringify(aus));
"""


def _python_erwartung(felder: dict) -> dict:
    tag = Tag(datei="x.md", kapitel_nr=1, titel="t", woerter=1, these=felder["these"], gegen=felder["gegen"],
              kern=felder["kern"], def_=felder["def"], beleg=felder["beleg"],
              zusammenfassung=felder["zusammenfassung"])
    woerter, namen = sr.baue_woerter(tag)
    n = len(woerter)

    def teile(w):
        text = w.text.upper() if w.marke else w.text
        i = min(sr.orp_index(text), len(text) - 1)
        return {"links": text[:i], "mitte": text[i], "rechts": text[i + 1:]}

    return {
        "namen": namen,
        "woerter": [dict(text=w.text, abschnitt=w.abschnitt, marke=w.marke, satzende=w.satzende,
                         faktor=w.faktor, teile=teile(w)) for w in woerter],
        "saetze": [[sr.voriger_satzanfang(woerter, i), sr.naechster_satzanfang(woerter, i),
                    sr.voriger_abschnitt(woerter, i), sr.naechster_abschnitt(woerter, i)] for i in range(n)],
        "rest": [sr.restdauer(woerter, 0, 300), sr.restdauer(woerter, n - 1, 900)] if n else [],
    }


@pytest.mark.skipif(NODE is None, reason="Node nicht installiert")
def test_js_liefert_dasselbe_wie_python():
    ergebnis = subprocess.run([NODE, "-e", NODE_SKRIPT, str(HIER / "speedreader.js")],
                              input=json.dumps(FAELLE), capture_output=True, text=True,
                              encoding="utf-8", check=True)
    js = json.loads(ergebnis.stdout)
    assert len(js) == len(FAELLE)
    for felder, aus_js in zip(FAELLE, js):
        erwartet = _python_erwartung(felder)
        assert aus_js["namen"] == erwartet["namen"]
        assert aus_js["woerter"] == erwartet["woerter"]
        assert aus_js["saetze"] == erwartet["saetze"]
        assert aus_js["rest"] == pytest.approx(erwartet["rest"])


def _baue_buch(root: Path, autor: str, titel: str, kapitel: list, tags: list) -> None:
    buch = root / "reader" / autor / titel
    (buch / "quelle").mkdir(parents=True)
    (buch / "notizen").mkdir()
    (buch / "quelle" / "_kapitel_index.json").write_text(json.dumps(kapitel), encoding="utf-8")
    (buch / "notizen" / "tags.json").write_text(json.dumps({"kapitel": tags}), encoding="utf-8")


def test_export_nur_kapitel_mit_ki_feldern(tmp_path):
    _baue_buch(tmp_path, "Autor, A", "Werk",
               [{"nr": 1, "titel": "Eins", "datei": "0001.md"}, {"nr": 2, "titel": "Zwei", "datei": "0002.md"},
                {"nr": 3, "titel": "Drei", "datei": "0003.md"}],
               [{"datei": "0001.md", "kapitel_nr": 1, "titel": "Eins", "woerter": 5, "zusammenfassung": "Ein Satz.",
                 "these": ["T1"], "gegen": [], "kern": [], "def": [], "beleg": []},
                {"datei": "0002.md", "kapitel_nr": 2, "titel": "Zwei", "woerter": 5, "zusammenfassung": "  ",
                 "these": [], "gegen": [], "kern": [], "def": [], "beleg": []}])
    _baue_buch(tmp_path, "Leer, B", "Ohne Tags", [{"nr": 1, "titel": "X", "datei": "0001.md"}], [])
    daten = export_daten.exportiere(tmp_path)
    assert [b["titel"] for b in daten["buecher"]] == ["Werk"]       # Buch ohne getaggte Kapitel entfaellt
    kap = daten["buecher"][0]["kapitel"]
    assert [k["nr"] for k in kap] == [1]                            # leeres und ungetaggtes Kapitel entfallen
    assert kap[0]["felder"] == {"zusammenfassung": "Ein Satz.", "these": ["T1"], "gegen": [], "kern": [],
                                "def": [], "beleg": []}


def test_export_volltext_je_buch_mit_gleichem_stand(tmp_path):
    _baue_buch(tmp_path, "A, A", "Eins",
               [{"nr": 1, "titel": "K1", "datei": "0001.md"}, {"nr": 2, "titel": "K2", "datei": "0002.md"},
                {"nr": 3, "titel": "K3", "datei": "0003.md"}],
               [{"datei": f"000{n}.md", "kapitel_nr": n, "titel": f"K{n}", "woerter": 1, "zusammenfassung": "Satz."}
                for n in (1, 2, 3)])
    quelle = tmp_path / "reader" / "A, A" / "Eins" / "quelle"
    (quelle / "0001.md").write_text("# Titel\n\nÄpfel [^1]\n\n[^1]: Note", encoding="utf-8")
    (quelle / "0002.md").write_text("Zweiter Text", encoding="utf-8")                # Kapitel 3: Datei fehlt
    _baue_buch(tmp_path, "B, B", "Zwei", [{"nr": 1, "titel": "K", "datei": "1.md"}],
               [{"datei": "1.md", "kapitel_nr": 1, "titel": "K", "woerter": 1, "zusammenfassung": "Satz."}])
    ordner = tmp_path / "ausgabe" / "buecher"
    ordner.mkdir(parents=True)
    (ordner / "b099.json").write_text("{}", encoding="utf-8")                        # Rest eines frueheren Exports

    daten = export_daten.exportiere(tmp_path, ordner)

    assert [b["id"] for b in daten["buecher"]] == ["b001", "b002"]
    assert sorted(p.name for p in ordner.glob("*.json")) == ["b001.json", "b002.json"]
    eins = json.loads((ordner / "b001.json").read_text(encoding="utf-8"))
    assert eins["id"] == "b001" and eins["erstellt"] == daten["erstellt"]
    assert eins["kapitel"] == {"1": "# Titel\n\nÄpfel [^1]\n\n[^1]: Note", "2": "Zweiter Text"}   # Kapitel 3 ohne Datei: kein Text
    assert json.loads((ordner / "b002.json").read_text(encoding="utf-8"))["kapitel"] == {}


def test_export_ohne_volltext_schreibt_keinen_ordner(tmp_path):
    _baue_buch(tmp_path, "A", "B", [{"nr": 1, "titel": "K", "datei": "1.md"}],
               [{"datei": "1.md", "kapitel_nr": 1, "titel": "K", "woerter": 1, "zusammenfassung": "x"}])
    out = tmp_path / "ausgabe" / "daten.json"
    out.parent.mkdir()
    assert export_daten.main(["--root", str(tmp_path), "--out", str(out), "--ohne-volltext"]) == 0
    assert not (out.parent / "buecher").exists()
    assert export_daten.main(["--root", str(tmp_path), "--out", str(out)]) == 0
    assert (out.parent / "buecher" / "b001.json").exists()


def test_export_daten_standardausgabe_ist_das_epistopheles_paket(tmp_path):
    _baue_buch(tmp_path, "A", "B", [{"nr": 1, "titel": "K", "datei": "1.md"}],
               [{"datei": "1.md", "kapitel_nr": 1, "titel": "K", "woerter": 1, "zusammenfassung": "Satz."}])
    (tmp_path / "reader" / "A" / "B" / "quelle" / "1.md").write_text("Text", encoding="utf-8")
    assert export_daten.main(["--root", str(tmp_path)]) == 0
    paket = tmp_path / "reader" / "export-epistopheles"
    assert (paket / "daten.json").is_file() and (paket / "buecher" / "b001.json").is_file()
    for name in ("index.html", "korrektur.html", "speedreader.js", "lesetext.js", "epub.js"):
        assert (paket / name).is_file(), name
    assert export_daten.main(["--root", str(tmp_path), "--ohne-app", "--out", str(tmp_path / "x" / "daten.json")]) == 0
    assert (tmp_path / "x" / "daten.json").is_file() and not (tmp_path / "x" / "index.html").exists()


def test_export_schreibt_datei(tmp_path):
    _baue_buch(tmp_path, "A", "B", [{"nr": 1, "titel": "K", "datei": "1.md"}],
               [{"datei": "1.md", "kapitel_nr": 1, "titel": "K", "woerter": 1, "zusammenfassung": "Ä ö ü ß."}])
    out = tmp_path / "daten.json"
    assert export_daten.main(["--root", str(tmp_path), "--out", str(out)]) == 0
    geladen = json.loads(out.read_text(encoding="utf-8"))
    assert geladen["buecher"][0]["kapitel"][0]["felder"]["zusammenfassung"] == "Ä ö ü ß."
    assert "\\u" not in out.read_text(encoding="utf-8")             # Umlaute unmaskiert, spart Platz


def test_bundle_enthaelt_verdacht_js(tmp_path):
    import bundle
    kopiert = bundle.kopiere_app(tmp_path / "paket")
    assert "verdacht.js" in kopiert and (tmp_path / "paket" / "verdacht.js").is_file()


def test_bundle_enthaelt_chunkansicht_js(tmp_path):
    import bundle
    kopiert = bundle.kopiere_app(tmp_path / "paket")
    assert "chunkansicht.js" in kopiert and (tmp_path / "paket" / "chunkansicht.js").is_file()
    html = (tmp_path / "paket" / "korrektur.html").read_text(encoding="utf-8")
    assert '<script src="verdacht.js">' in html and '<script src="chunkansicht.js">' in html
    assert "fussnoten.js" in kopiert and (tmp_path / "paket" / "fussnoten.js").is_file()
    assert "ursache.js" in kopiert and '<script src="ursache.js">' in html
    assert html.index('<script src="fussnoten.js">') < html.index('<script src="chunkansicht.js">')   # Reihenfolge der Abhaengigkeiten


def test_bundle_enthaelt_redaktion_js(tmp_path):
    import bundle
    kopiert = bundle.kopiere_app(tmp_path / "paket")
    assert "redaktion.js" in kopiert and (tmp_path / "paket" / "redaktion.js").is_file()
    assert '<script src="redaktion.js">' in (tmp_path / "paket" / "korrektur.html").read_text(encoding="utf-8")


def test_bundle_enthaelt_die_dateien_der_verbindungsansicht(tmp_path):
    import bundle
    kopiert = bundle.kopiere_app(tmp_path / "paket")
    for name in ("verbindungen.js", "graphlayout.js", "graphansicht.js"):
        assert name in kopiert and (tmp_path / "paket" / name).is_file()
    html = (tmp_path / "paket" / "index.html").read_text(encoding="utf-8")
    assert all(f'src="{n}"' in html for n in ("verbindungen.js", "graphlayout.js", "graphansicht.js"))
