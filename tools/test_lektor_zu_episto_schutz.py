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
