from __future__ import annotations
import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "lektor_zu_episto", Path(__file__).parent / "lektor-zu-episto.py")
lze = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(lze)


def _lektor_buch(wurzel: Path) -> Path:
    b = wurzel / "lektor" / "Autor" / "Titel"
    (b / "de").mkdir(parents=True)
    (b / "de" / "chunk_000.md").write_text("# Eins\n\nErster Absatz.\n\nZweiter Absatz.", encoding="utf-8")
    (b / "kapitel.json").write_text(json.dumps(
        {"segmente": [{"titel": "Eins", "chunk": 0, "position": 0}]}), encoding="utf-8")
    return wurzel


def _lauf(wurzel: Path, **kw):
    dry = kw.pop("dry_run", False)
    lze.verarbeite("Autor/Titel", wurzel / "lektor", wurzel / "reader", "de", "en", dry, **kw)


def test_lektor_zu_episto_verweigert_ueberschreiben_ohne_schalter(tmp_path):
    w = _lektor_buch(tmp_path)
    quelle = w / "reader" / "Autor" / "Titel" / "quelle"
    quelle.mkdir(parents=True)
    (quelle / "0001_x.md").write_text("handkorrigiert", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        _lauf(w)
    assert "--ueberschreiben" in str(exc.value)
    assert (quelle / "0001_x.md").read_text(encoding="utf-8") == "handkorrigiert"
    assert not (quelle / "_kapitel_index.json").exists()
    assert not (quelle.parent / "meta.json").exists()


def test_lektor_zu_episto_dry_run_ist_ausgenommen(tmp_path):
    w = _lektor_buch(tmp_path)
    quelle = w / "reader" / "Autor" / "Titel" / "quelle"
    quelle.mkdir(parents=True)
    (quelle / "0001_x.md").write_text("alt", encoding="utf-8")
    _lauf(w, dry_run=True)
    assert (quelle / "0001_x.md").read_text(encoding="utf-8") == "alt"


def test_lektor_zu_episto_erstlauf_und_ueberschreiben(tmp_path):
    w = _lektor_buch(tmp_path)
    _lauf(w)
    quelle = w / "reader" / "Autor" / "Titel" / "quelle"
    assert (quelle / "0001_eins.md").is_file()
    with pytest.raises(SystemExit):
        _lauf(w)
    _lauf(w, ueberschreiben=True)


def test_lektor_zu_episto_meldet_nicht_anwendbare_eintraege(tmp_path, capsys):
    w = _lektor_buch(tmp_path)
    buch = w / "reader" / "Autor" / "Titel"
    (buch / "notizen").mkdir(parents=True)
    (buch / "notizen" / "redaktion.json").write_text('{"eintraege": 5}', encoding="utf-8")
    _lauf(w)
    assert "nicht" in capsys.readouterr().out.lower()


# --- P2 Task 8: Kette anwenden -> --ueberschreiben -> Nachspiel -----------------------------------------

import redaktion_anwenden as ra  # noqa: E402
from episto_tui.korrektur import absatz_spannen  # noqa: E402
from redaktion import ops, protokoll  # noqa: E402

BUCH = "Autor/Titel"


def _quelle(w: Path) -> Path:
    return w / "reader" / "Autor" / "Titel" / "quelle" / "0001_eins.md"


def _ersetzen(text: str, index: int, nachher: str) -> dict:
    a, b = absatz_spannen(text)[index]
    return ops.neuer_eintrag(BUCH, "volltext", {"datei": "0001_eins.md", "absatz_index": index,
                                                "anfang": ops.anker_von(text[a:b])},
                             "ersetzen", {"nachher": nachher}, text[a:b], geraet="t")


def _kette_bis_angewendet(w: Path) -> str:
    _lauf(w)
    urtext = _quelle(w).read_bytes().decode("utf-8")
    protokoll.schreibe_eingang(w, "tablet", BUCH, [_ersetzen(urtext, 1, "Erster Absatz, korrigiert.")])
    assert ra.main(["--root", str(w), "--ausfuehren"]) == 0
    return urtext


def test_kette_anwenden_ueberschreiben_nachspiel_ergibt_denselben_text(tmp_path, capsys):
    """Review Focus 4: Neuaufbau liefert wieder den Urtext, die Korrektur wird wieder eingespielt."""
    w = _lektor_buch(tmp_path)
    urtext = _kette_bis_angewendet(w)
    korrigiert = _quelle(w).read_bytes()
    assert korrigiert != urtext.encode("utf-8")
    _lauf(w, ueberschreiben=True)
    assert _quelle(w).read_bytes() == korrigiert
    buch = w / "reader" / "Autor" / "Titel"
    assert not (buch / "notizen" / "redaktion-nachspiel.json").exists()
    sicherungen = list((buch / "notizen" / "_backup").glob("quelle-*/0001_eins.md"))
    assert len(sicherungen) == 1 and sicherungen[0].read_bytes() == korrigiert        # Stand vor dem Neuaufbau


def test_ueberschreiben_meldet_konflikte_einzeln_und_schreibt_bericht(tmp_path, capsys):
    w = _lektor_buch(tmp_path)
    _kette_bis_angewendet(w)
    (w / "lektor" / "Autor" / "Titel" / "de" / "chunk_000.md").write_text(
        "# Eins\n\nGanz neuer erster Absatz.\n\nZweiter Absatz.", encoding="utf-8")        # Basis hat sich geaendert
    capsys.readouterr()
    _lauf(w, ueberschreiben=True)
    out = capsys.readouterr().out
    assert "0001_eins.md" in out and "WARNUNG" in out
    b = json.loads((w / "reader" / "Autor" / "Titel" / "notizen" / "redaktion-nachspiel.json").read_text(encoding="utf-8"))
    assert len(b["konflikte"]) == 1 and b["konflikte"][0]["datei"] == "0001_eins.md" and b["konflikte"][0]["id"] in out
    assert b["basis_geaendert"] == ["0001_eins.md"]


def test_dry_run_sichert_nichts(tmp_path):
    w = _lektor_buch(tmp_path)
    _kette_bis_angewendet(w)
    vorher = _quelle(w).read_bytes()
    n_backups = len(list((w / "reader" / "Autor" / "Titel" / "notizen" / "_backup").glob("*")))
    _lauf(w, dry_run=True, ueberschreiben=True)
    assert _quelle(w).read_bytes() == vorher
    assert len(list((w / "reader" / "Autor" / "Titel" / "notizen" / "_backup").glob("*"))) == n_backups
