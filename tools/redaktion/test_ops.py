from __future__ import annotations
import json
from pathlib import Path

import pytest

from episto_tui.korrektur import absatz_spannen
from redaktion import ops

VEKTOREN = json.loads((Path(__file__).parent / "testvektoren.json").read_text(encoding="utf-8"))


def _eintrag(text: str, index: int, art: str, parameter: dict | None = None, **ziel_extra) -> dict:
    a, b = absatz_spannen(text)[index]
    ziel = {"absatz_index": index, "anfang": ops.anker_von(text[a:b])}
    ziel.update(ziel_extra)
    return ops.neuer_eintrag("Autor/Titel", "volltext", ziel, art, parameter or {}, text[a:b])


@pytest.mark.parametrize("v", VEKTOREN, ids=[v["name"] for v in VEKTOREN])
def test_testvektor(v):
    text, ergebnisse = ops.spiele_ab(v["text"], v["eintraege"])
    assert text == v["erwartet_text"]
    assert ergebnisse[-1].status == v["erwartet_status"]
    if "erwartet_stati" in v:
        assert [e.status for e in ergebnisse] == v["erwartet_stati"]


EINZELN = [v for v in VEKTOREN if len(v["eintraege"]) == 1]


@pytest.mark.parametrize("v", EINZELN, ids=[v["name"] for v in EINZELN])
def test_testvektor_einzeln_wende_an(v):
    """Hat ein Vektor genau einen Eintrag, liefert wende_an dasselbe wie spiele_ab."""
    erg = ops.wende_an(v["text"], v["eintraege"][0])
    assert erg.text == v["erwartet_text"]
    assert erg.status == v["erwartet_status"]


def test_normalisiere_und_anker():
    assert ops.normalisiere("  Äpfel \t\r\n  und\nBirnen ") == "Äpfel und Birnen"
    assert ops.anker_von("x" * 100) == "x" * 40
    assert ops.anker_von("a  b\n\nc", 3) == "a b"


def test_pruefsumme_ist_stabil():
    assert ops.pruefsumme("Äpfel\r\nBirnen") == ops.pruefsumme("Äpfel\nBirnen")
    s = ops.pruefsumme("Äpfel\nBirnen")
    assert len(s) == 16
    int(s, 16)
    # veroeffentlichte FNV-1a-64-Werte (Known-Answer, unabhaengig von dieser Implementierung)
    assert ops.pruefsumme("") == "cbf29ce484222325"
    assert ops.pruefsumme("a") == "af63dc4c8601ec8c"
    assert ops.pruefsumme("foobar") == "85944171f73967e8"
    assert ops.pruefsumme("a") != ops.pruefsumme("b")


def test_neuer_eintrag_felder():
    e = ops.neuer_eintrag("A/T", "volltext", {"anfang": "x"}, "ersetzen", {"nachher": "y"},
                          "z" * 200, hinweis="h", geraet="g")
    assert len(e["id"]) == 12
    int(e["id"], 16)
    assert e["status"] == "offen"
    assert e["buch"] == "A/T" and e["ebene"] == "volltext" and e["art"] == "ersetzen"
    assert e["vorher"] == {"hash": ops.pruefsumme("z" * 200), "ausschnitt": "z" * 80}
    assert e["hinweis"] == "h" and e["geraet"] == "g"
    assert e["erstellt"]
    assert ops.neuer_eintrag("A/T", "ki", {}, "marke", {}, "")["id"] != e["id"]


def test_verbinden_entfernt_silbentrennung_nur_vor_kleinbuchstabe():
    text = "Die Reprä-\nsentation der Welt."
    erg = ops.wende_an(text, _eintrag(text, 0, "verbinden", zeile=0))
    assert erg.status == "angewendet"
    assert erg.text == "Die Repräsentation der Welt."
    text = "Ein Satz.\nNeu beginnt es."
    erg = ops.wende_an(text, _eintrag(text, 0, "verbinden", zeile=0))
    assert erg.text == "Ein Satz. Neu beginnt es."
    text = "Das Ost-\nWest-Gefälle."
    erg = ops.wende_an(text, _eintrag(text, 0, "verbinden", zeile=0))
    assert erg.text == "Das Ost- West-Gefälle."


def test_nur_der_betroffene_absatz_aendert_sich_byteexakt():
    text = ("Erster\tAbsatz  mit\tTabs.\r\n\r\n"
            "Zweiter Absatz mit Reprä-\r\nsentation und\tTab.\r\n"
            "Zweite Zeile.\r\n\r\n\r\n"
            "Dritter\tAbsatz ohne Schluss-Newline")
    for index, art, extra in [(1, "verbinden", {"zeile": 0}), (1, "trennen", {"zeile": 2}),
                              (1, "ersetzen", {})]:
        param = {"nachher": "Neu\tgefasst."} if art == "ersetzen" else {}
        erg = ops.wende_an(text, _eintrag(text, index, art, param, **extra))
        assert erg.status == "angewendet", (art, erg.grund)
        a, b = absatz_spannen(text)[index]
        absatz = text[a:b]
        if art == "verbinden":
            neu = "Zweiter Absatz mit Repräsentation und\tTab.\r\nZweite Zeile."
        elif art == "trennen":
            neu = "Zweiter Absatz mit Reprä-\r\nsentation und\tTab.\r\n\r\nZweite Zeile."
        else:
            neu = "Neu\tgefasst."
        assert absatz != neu
        assert erg.text == text[:a] + neu + text[b:]
    # letzter Absatz ohne Schluss-Newline
    erg = ops.wende_an(text, _eintrag(text, 2, "ersetzen", {"nachher": "Ende."}))
    a, b = absatz_spannen(text)[2]
    assert erg.text == text[:a] + "Ende." and not erg.text.endswith("\n")


def test_doppelter_anker_ohne_passenden_index_ist_konflikt():
    kopf = "Kopfzeile des Buches, die sich oft wiederholt: "
    text = f"{kopf}eins\n\n{kopf}zwei\n\n{kopf}drei"
    e = _eintrag(text, 1, "ersetzen", {"nachher": "X"})
    assert e["ziel"]["anfang"] == ops.anker_von(kopf + "eins")  # alle drei gleich
    e["ziel"]["absatz_index"] = 7
    erg = ops.wende_an(text, e)
    assert erg.status == "konflikt"
    assert erg.text == text
    del e["ziel"]["absatz_index"]
    assert ops.finde_absatz(text, e["ziel"]) is None


def test_doppelter_anker_mit_index_trifft():
    kopf = "Kopfzeile des Buches, die sich oft wiederholt: "
    text = f"{kopf}eins\n\n{kopf}zwei\n\n{kopf}drei"
    e = _eintrag(text, 1, "ersetzen", {"nachher": "X"})
    assert ops.finde_absatz(text, e["ziel"]) == 1
    erg = ops.wende_an(text, e)
    assert erg.status == "angewendet"
    assert erg.text == f"{kopf}eins\n\nX\n\n{kopf}drei"


def test_eindeutiger_anker_gewinnt_bei_verschobenem_index():
    text = "Alpha eins.\n\nBeta zwei.\n\nGamma drei."
    e = _eintrag(text, 2, "ersetzen", {"nachher": "G."})
    e["ziel"]["absatz_index"] = 0
    assert ops.finde_absatz(text, e["ziel"]) == 2


def test_geaenderter_vorzustand_ist_konflikt():
    lang = "Alpha eins mit einem recht langen Anfang, der den Anker füllt"
    text = f"{lang}, Ende.\n\nBeta zwei."
    e = _eintrag(text, 0, "ersetzen", {"nachher": "A."})
    geaendert = f"{lang}, Ende!\n\nBeta zwei."
    erg = ops.wende_an(geaendert, e)
    assert erg.status == "konflikt"
    assert erg.text == geaendert
    assert "vorher" in erg.grund.lower() or "geändert" in erg.grund.lower()


def test_abhaengige_eintraege_werden_konflikt_wenn_der_vorige_scheitert():
    text = "Alpha eins.\n\nBeta zwei."
    e1 = _eintrag(text, 0, "ersetzen", {"nachher": "Alpha EINS."})
    text_nach_1 = "Alpha EINS.\n\nBeta zwei."
    e2 = _eintrag(text_nach_1, 0, "ersetzen", {"nachher": "Alpha EINS!"})
    e3 = _eintrag(text, 1, "ersetzen", {"nachher": "B."})
    e1["vorher"]["hash"] = ops.pruefsumme("etwas ganz anderes")  # e1 scheitert
    ergebnis_text, erg = ops.spiele_ab(text, [e1, e2, e3])
    assert [e.status for e in erg] == ["konflikt", "konflikt", "angewendet"]
    assert e1["id"] in erg[1].grund
    assert ergebnis_text == "Alpha eins.\n\nB."


def test_kette_am_selben_absatz_wird_in_reihenfolge_angewendet():
    text = "Alpha eins.\n\nBeta zwei."
    e1 = _eintrag(text, 0, "ersetzen", {"nachher": "Alpha EINS."})
    e2 = _eintrag("Alpha EINS.\n\nBeta zwei.", 0, "ersetzen", {"nachher": "Alpha EINS!"})
    t, erg = ops.spiele_ab(text, [e1, e2])
    assert [e.status for e in erg] == ["angewendet", "angewendet"]
    assert t == "Alpha EINS!\n\nBeta zwei."


def test_ohne_zurueckgenommene_entfernt_ziel_und_ruecknahme():
    a = {"id": "a", "art": "ersetzen", "parameter": {}}
    b = {"id": "b", "art": "marke", "parameter": {}}
    r = {"id": "r", "art": "ruecknahme", "parameter": {"id": "a"}}
    c = {"id": "c", "art": "loeschen", "parameter": {}}
    assert ops.ohne_zurueckgenommene([a, b, r, c]) == [b, c]
    assert ops.ohne_zurueckgenommene([b, c]) == [b, c]
    # Ruecknahme einer unbekannten id entfernt nur sich selbst
    assert ops.ohne_zurueckgenommene([b, {"id": "r2", "art": "ruecknahme",
                                          "parameter": {"id": "zzz"}}]) == [b]
    assert ops.ohne_zurueckgenommene([]) == []


def test_arten_ohne_textwirkung_werden_uebersprungen():
    text = "Alpha eins."
    for art in ("ruecknahme", "uebersetzung-uebernehmen", "neu-uebersetzen"):
        erg = ops.wende_an(text, {"id": "x", "art": art, "parameter": {}, "ziel": {}})
        assert (erg.text, erg.status) == (text, "uebersprungen")
        assert erg.grund == "keine Textoperation"
    erg = ops.wende_an(text, {"id": "x", "art": "marke", "parameter": {}, "ziel": {"anfang": "nix"}})
    assert (erg.text, erg.status) == (text, "angewendet")


def test_unbekannte_art_ist_konflikt():
    erg = ops.wende_an("Text", {"id": "x", "art": "zaubern", "parameter": {}, "ziel": {}})
    assert erg.status == "konflikt"
    assert "zaubern" in erg.grund


def test_spiele_ab_laesst_eingabe_unveraendert():
    text = "Alpha eins.\n\nBeta zwei."
    e = _eintrag(text, 0, "ersetzen", {"nachher": "A."})
    kopie = json.loads(json.dumps(e))
    ops.spiele_ab(text, [e])
    assert e == kopie


KEY_WEG = object()


def _kaputt(**aenderung) -> dict:
    text = "Alpha eins.\n\nBeta zwei."
    e = _eintrag(text, 0, "ersetzen", {"nachher": "A."})
    for k, v in aenderung.items():
        if v is KEY_WEG:
            del e[k]
        else:
            e[k] = v
    return e


@pytest.mark.parametrize("aenderung", [
    {"ziel": None}, {"parameter": None}, {"ziel": KEY_WEG}, {"parameter": KEY_WEG},
    {"vorher": KEY_WEG}, {"vorher": None}, {"vorher": {}}, {"parameter": {"nachher": None}},
    {"parameter": {"nachher": 123}}, {"parameter": {}}, {"parameter": {"nachher": ""}},
    {"parameter": {"nachher": "  \n "}}, {"parameter": {"nachher": "Eins.\n\nZwei."}},
    {"parameter": {"nachher": "Eins.\r\n \r\nZwei."}},
], ids=lambda a: str({k: ("-" if v is KEY_WEG else v) for k, v in a.items()}))
def test_fehlerhafter_eintrag_ist_konflikt_ohne_ausnahme(aenderung):
    text = "Alpha eins.\n\nBeta zwei."
    e = _kaputt(**aenderung)
    erg = ops.wende_an(text, e)
    assert (erg.text, erg.status) == (text, "konflikt")
    assert erg.grund
    ok = _eintrag(text, 1, "ersetzen", {"nachher": "B."})
    t, ergs = ops.spiele_ab(text, [e, ok])
    assert [x.status for x in ergs] == ["konflikt", "angewendet"]
    assert t == "Alpha eins.\n\nB."


def test_eintrag_ohne_objekt_ist_konflikt():
    assert ops.wende_an("T", None).status == "konflikt"
    t, ergs = ops.spiele_ab("T", [None, 5])
    assert t == "T" and [x.status for x in ergs] == ["konflikt", "konflikt"]


def test_fehlendes_vorher_hash_ist_konflikt_vorher_fehlt():
    e = _kaputt()
    del e["vorher"]["hash"]
    erg = ops.wende_an("Alpha eins.\n\nBeta zwei.", e)
    assert erg.status == "konflikt" and "vorher fehlt" in erg.grund
