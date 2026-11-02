"""Tests fuer chunk-neu-uebersetzen.py (Task 12) - ohne Ollama; der Uebersetzer ist eine Attrappe."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
TOOLS = HIER.parent
sys.path.insert(0, str(TOOLS))

from episto_tui.korrektur import absatz_spannen  # noqa: E402
from redaktion import ops, protokoll  # noqa: E402

_spec = importlib.util.spec_from_file_location("chunk_neu_uebersetzen", HIER / "chunk-neu-uebersetzen.py")
cnu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cnu)

BUCH = "Autor, Eins/Titel"
ORIGINAL = "Das ist ein lan-\ngen Absatz mit Trennung.\n\nZweiter Absatz bleibt.\n"
ALT_DE = "Bisherige Übersetzung.\n"


@pytest.fixture
def root(tmp_path):
    lektor = tmp_path / "rohdaten" / "Lektor" / "Autor, Eins" / "Titel"
    (lektor / "en").mkdir(parents=True)
    (lektor / "de").mkdir()
    (lektor / "en" / "chunk_000.md").write_bytes(ORIGINAL.encode("utf-8"))
    (lektor / "de" / "chunk_000.md").write_bytes(ALT_DE.encode("utf-8"))
    (lektor / "meta.json").write_text(json.dumps({"quellsprache": "en"}), encoding="utf-8")
    return tmp_path


def verbinden_eintrag(i="e1"):
    a, b = absatz_spannen(ORIGINAL)[0]
    e = ops.neuer_eintrag(BUCH, "chunk-orig", {"chunk": 0, "absatz_index": 0,
                                               "anfang": ops.anker_von(ORIGINAL[a:b]), "zeile": 0},
                          "verbinden", {}, ORIGINAL[a:b])
    e["id"] = i
    return e


def lektor(root):
    return root / "rohdaten" / "Lektor" / "Autor, Eins" / "Titel"


def test_uebersetze_chunk_nimmt_den_korrigierten_text_und_ersetzt_nichts(root):
    protokoll.schreibe_eingang(root, "tab", BUCH, [verbinden_eintrag()])
    assert protokoll.lade_stand(root, BUCH) == {}              # noch "gesendet"
    ziel = cnu.uebersetze_chunk(root, BUCH, 0, lambda t: "DE:" + t)
    assert ziel == lektor(root) / "de" / "chunk_000.md.neu"
    text = ziel.read_bytes().decode("utf-8")
    assert text.startswith("DE:")
    assert "langen Absatz" in text and "lan-\n" not in text
    assert (lektor(root) / "de" / "chunk_000.md").read_bytes() == ALT_DE.encode("utf-8")
    assert (lektor(root) / "en" / "chunk_000.md").read_bytes() == ORIGINAL.encode("utf-8")
    assert protokoll.lade_stand(root, BUCH) == {}              # Stand unveraendert


def test_angewendete_eintraege_werden_nicht_doppelt_abgespielt(root):
    protokoll.schreibe_eingang(root, "tab", BUCH, [verbinden_eintrag()])
    protokoll.setze_stand(root, BUCH, "e1", "angewendet")
    gesehen = []
    cnu.uebersetze_chunk(root, BUCH, 0, lambda t: gesehen.append(t) or "DE:" + t)
    assert gesehen == [ORIGINAL]                               # Eintrag nicht erneut angewendet


def test_zurueckgenommene_und_fremde_chunks_werden_nicht_abgespielt(root):
    fremd = verbinden_eintrag("e2")
    fremd["ziel"] = {**fremd["ziel"], "chunk": 7}
    ruecknahme = ops.neuer_eintrag(BUCH, "chunk-orig", {"chunk": 0}, "ruecknahme", {"id": "e1"}, "")
    protokoll.schreibe_eingang(root, "tab", BUCH, [verbinden_eintrag(), fremd, ruecknahme])
    gesehen = []
    cnu.uebersetze_chunk(root, BUCH, 0, lambda t: gesehen.append(t) or "DE:" + t)
    assert gesehen == [ORIGINAL]


def test_vorhandener_vorschlag_wird_vor_dem_ueberschreiben_gesichert(root):
    neu = lektor(root) / "de" / "chunk_000.md.neu"
    neu.write_text("ALTER VORSCHLAG", encoding="utf-8")
    cnu.uebersetze_chunk(root, BUCH, 0, lambda t: "NEU")
    assert neu.read_text(encoding="utf-8") == "NEU"
    sicherungen = list((lektor(root) / "notizen" / "_backup").glob("chunk_000.md.*.neu"))
    assert [s.read_text(encoding="utf-8") for s in sicherungen] == ["ALTER VORSCHLAG"]


def test_fehler_des_uebersetzers_hinterlaesst_keine_datei(root):
    def kaputt(t):
        raise RuntimeError("Ollama weg")
    with pytest.raises(RuntimeError):
        cnu.uebersetze_chunk(root, BUCH, 0, kaputt)
    with pytest.raises(RuntimeError):
        cnu.uebersetze_chunk(root, BUCH, 0, lambda t: "  ")
    assert not (lektor(root) / "de" / "chunk_000.md.neu").exists()


@pytest.mark.parametrize("buch", ["../../x/y", "A/..", "/abs/pfad", "nur-einer", "Autor/CON", "A/B/C"])
def test_unsichere_buchnamen_werden_abgelehnt(root, buch):
    with pytest.raises(ValueError):
        cnu.uebersetze_chunk(root, buch, 0, lambda t: "x")


def test_ungueltiger_chunk_fehlender_chunk_und_deutsche_quelle(root):
    for chunk in (-1, True, "0"):
        with pytest.raises(ValueError):
            cnu.uebersetze_chunk(root, BUCH, chunk, lambda t: "x")
    with pytest.raises(OSError):
        cnu.uebersetze_chunk(root, BUCH, 5, lambda t: "x")
    (lektor(root) / "meta.json").write_text(json.dumps({"quellsprache": "de"}), encoding="utf-8")
    with pytest.raises(ValueError):
        cnu.uebersetze_chunk(root, BUCH, 0, lambda t: "x")


def test_main_meldet_fehler_mit_exit_1(root, capsys):
    assert cnu.main(["--root", str(root), "--buch", "../../x/y", "--chunk", "0"]) == 1
    assert "Fehler" in capsys.readouterr().err
