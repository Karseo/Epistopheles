from __future__ import annotations
import json
import pytest
from episto_tui.models import Buch


@pytest.fixture
def temp_buch(tmp_path) -> Buch:
    buch_pfad = tmp_path / "reader" / "Testautor, Theo" / "Testbuch"
    quelle = buch_pfad / "quelle"
    notizen = buch_pfad / "notizen"
    quelle.mkdir(parents=True)
    notizen.mkdir(parents=True)
    (notizen / "straenge").mkdir()
    (buch_pfad / "querbezuege").mkdir()

    (quelle / "0001_erstes-kapitel.md").write_text(
        "Erster Absatz des ersten Kapitels.\n\n"
        "Zweiter Absatz mit mehr Inhalt zum Testen.\n\n"
        "Dritter Absatz, der letzte hier.",
        encoding="utf-8",
        newline="\n",
    )
    (quelle / "0002_zweites-kapitel.md").write_text(
        "Einziger Absatz des zweiten Kapitels.",
        encoding="utf-8",
        newline="\n",
    )
    (quelle / "_kapitel_index.json").write_text(
        json.dumps([
            {"nr": 1, "titel": "Erstes Kapitel", "datei": "0001_erstes-kapitel.md"},
            {"nr": 2, "titel": "Zweites Kapitel", "datei": "0002_zweites-kapitel.md"},
        ], ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    (notizen / "tags.json").write_text(
        json.dumps({
            "werk": "Testbuch", "autor": "Testautor, Theo", "sprache": "de",
            "eintraege": 1, "erstellt": "2026-09-27 10:00",
            "kapitel": [{
                "datei": "0001_erstes-kapitel.md", "kapitel_nr": 1,
                "titel": "Erstes Kapitel", "woerter": 12,
                "these": ["Testthese"], "gegen": [], "kern": ["testbegriff"],
                "def": [], "beleg": [], "zusammenfassung": "Kurze Zusammenfassung.",
            }],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    (notizen / "straenge" / "test-strang.md").write_text(
        "---\n"
        "strang: Test-Strang\n"
        "slug: test-strang\n"
        "werk: Testbuch\n"
        "treffer: 1\n"
        "---\n\n"
        "# Strang: Test-Strang\n\n"
        "Definition des Test-Strangs.\n\n"
        "## Fundstellen (1)\n\n"
        "### Kapitel 1 · Erstes Kapitel\n"
        "- Testthese\n",
        encoding="utf-8",
        newline="\n",
    )

    (buch_pfad / "querbezuege" / "querbezuege.json").write_text(
        json.dumps({
            "werk": "testbuch", "autor": "testautor",
            "bezuege": [{
                "ziel": "extern_werk", "autor": "Externer Autor",
                "titel": "Externes Werk", "relation": "ergaenzt",
                "notiz": "Testnotiz.",
            }],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

    return Buch(autor="Testautor, Theo", titel="Testbuch", pfad=buch_pfad)


@pytest.fixture(autouse=True)
def _zustand_isoliert(tmp_path_factory, monkeypatch):
    """Die Leseposition liegt im Benutzerverzeichnis; Tests duerfen dort nie
    schreiben oder von dort lesen."""
    monkeypatch.setenv("EPISTO_ZUSTAND", str(tmp_path_factory.mktemp("zustand") / "zustand.json"))
