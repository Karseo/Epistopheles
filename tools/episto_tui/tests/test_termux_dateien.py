from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_stignore_enthaelt_die_vorgesehenen_muster():
    zeilen = (REPO / ".stignore").read_text(encoding="utf-8").split()
    for muster in ["**/_backup", ".git", "**/__pycache__", ".worktrees", ".superpowers", "test_dir",
                   "rohdaten", "reader/export-epistopheles", "hilfsdaten/archiv", "tools/*.log", ".playwright-mcp"]:
        assert muster in zeilen
    # Rohdaten und Exporte duerfen nie aufs Handy: die Struktur haengt an genau diesen Zeilen
    assert "reader" not in zeilen and "tools" not in zeilen


def test_startskript_hat_shebang_und_unix_zeilenenden():
    daten = (REPO / "tools" / "episto-tui.sh").read_bytes()
    assert daten.startswith(b"#!/usr/bin/env sh\n")
    assert b"\r" not in daten


def test_gitattributes_erzwingt_lf_fuer_skript_und_stignore():
    inhalt = (REPO / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in inhalt
    assert ".stignore text eol=lf" in inhalt
