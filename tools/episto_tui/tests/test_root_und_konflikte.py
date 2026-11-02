from pathlib import Path

from episto_tui import library
from episto_tui.__main__ import bestimme_root


def test_argument_hat_vorrang_vor_umgebung_und_standard():
    assert library.resolve_root("/a/b", {"EPISTO_ROOT": "/c"}, plattform="linux") == Path("/a/b")


def test_umgebungsvariable_hat_vorrang_vor_standard():
    assert library.resolve_root(None, {"EPISTO_ROOT": "/c"}, plattform="linux") == Path("/c")


def test_standard_unter_windows_ist_default_root():
    assert library.resolve_root(None, {}, plattform="win32") == library.DEFAULT_ROOT


def test_standard_sonst_ist_home_episto(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert library.resolve_root(None, {}, plattform="linux") == tmp_path / "episto"


def test_leere_werte_zaehlen_nicht():
    assert library.resolve_root("", {"EPISTO_ROOT": ""}, plattform="win32") == library.DEFAULT_ROOT


def test_tilde_wird_aufgeloest(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert library.resolve_root("~/lib", {}, plattform="linux") == tmp_path / "lib"


def test_bestimme_root_liest_root_argument():
    assert bestimme_root(["--root", "x"], {}) == Path("x")


def test_bestimme_root_faellt_auf_umgebung_zurueck():
    assert bestimme_root([], {"EPISTO_ROOT": "y"}) == Path("y")


def test_glob_fallback_ignoriert_syncthing_konfliktkopien(temp_buch):
    quelle = temp_buch.pfad / "quelle"
    (quelle / "_kapitel_index.json").unlink()
    (quelle / "0001_erstes-kapitel.sync-conflict-20260928-101010-ABCDEFG.md").write_text(
        "Konflikt", encoding="utf-8")
    dateien = [k.datei for k in library.list_chapters(temp_buch)]
    assert dateien == ["0001_erstes-kapitel.md", "0002_zweites-kapitel.md"]


def test_kapitelliste_mit_index_zeigt_keine_konfliktkopien(temp_buch):
    quelle = temp_buch.pfad / "quelle"
    (quelle / "0001_erstes-kapitel.sync-conflict-20260928-101010-ABCDEFG.md").write_text(
        "Konflikt", encoding="utf-8")
    dateien = [k.datei for k in library.list_chapters(temp_buch)]
    assert dateien == ["0001_erstes-kapitel.md", "0002_zweites-kapitel.md"]


def test_straenge_ignorieren_syncthing_konfliktkopien(temp_buch):
    ordner = temp_buch.pfad / "notizen" / "straenge"
    original = ordner / "test-strang.md"
    (ordner / "test-strang.sync-conflict-20260928-101010-ABCDEFG.md").write_text(
        original.read_text(encoding="utf-8"), encoding="utf-8")
    assert len(library.read_straenge_for_chapter(temp_buch, 1)) == 1
