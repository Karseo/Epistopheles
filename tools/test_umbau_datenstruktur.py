"""Tests fuer umbau_datenstruktur.py: Modellbaum, der den Ablauf vorher -> Merge -> nachher abbildet."""
import shutil
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))

import umbau_datenstruktur as umbau  # noqa: E402


def _schreibe(pfad: Path, text: str = "x") -> Path:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(text, encoding="utf-8")
    return pfad


def _altbaum(root: Path) -> None:
    """Zustand vor dem Umbau."""
    # fertige Daten (getrackt) + ignorierte/untracked Reste im Buchordner
    _schreibe(root / "Autor" / "A, A" / "T1" / "quelle" / "0001.md", "Kapitel")
    _schreibe(root / "Autor" / "A, A" / "T1" / "en" / "chunk_000.md", "EN 0")
    _schreibe(root / "Autor" / "A, A" / "T1" / "en" / "chunk_001.md", "EN 1")
    _schreibe(root / "Autor" / "A, A" / "T1" / "notizen" / "_backup" / "alt.json", "{}")       # ignoriert
    _schreibe(root / "Autor" / "B, B" / "T2" / "quelle" / "0001.md", "Kapitel 2")              # nur untracked, kein en
    (root / "Autor" / "B, B" / "T2" / "en").mkdir()                                              # leerer en-Ordner
    # Rohdaten
    _schreibe(root / "eBooks" / "Inbox" / "a.epub", "EPUB")
    _schreibe(root / "eBooks" / "Lektor" / "A, A" / "T1" / "en" / "chunk_000.md", "EN 0")
    _schreibe(root / "eBooks" / "Outbox" / "o.md")
    _schreibe(root / "eBooks" / "Transfer" / "t.md")
    _schreibe(root / "eBooks" / "ebook-translate.py", "# alt")
    _schreibe(root / "Inbox" / "a.epub", "EPUB")                       # Dublette (identisch)
    _schreibe(root / "Inbox" / "b.pdf", "PDF")                          # nur in der Wurzel-Inbox
    _schreibe(root / "Autor.mov" / "Kant" / "k.md", "alt")
    _schreibe(root / "notizen" / "queue.md", "Queue")
    # Skripte, wie sie der Branch mitbringt
    _schreibe(root / "tools" / "pipeline" / "ebook-translate.py", "# neu")
    (root / "hilfsdaten").mkdir()


def _merge_simulieren(root: Path) -> None:
    """Was `git merge` des Branches tut: getrackte Dateien Autor -> reader, en-Chunks verschwinden."""
    (root / "reader" / "A, A" / "T1").mkdir(parents=True, exist_ok=True)
    shutil.move(str(root / "Autor" / "A, A" / "T1" / "quelle"), str(root / "reader" / "A, A" / "T1" / "quelle"))
    for datei in (root / "Autor" / "A, A" / "T1" / "en").glob("*.md"):
        datei.unlink()                                                  # getrackt, vom Merge geloescht


def test_vorher_kopiert_en_chunks_und_verschiebt_rohdaten(tmp_path):
    _altbaum(tmp_path)
    ergebnis = umbau.Ergebnis()
    for a in umbau.plan_vorher(tmp_path):
        umbau.fuehre_aus(a, ergebnis)
    # en-Chunks: Kopie unter rohdaten\en-chunks, Original bleibt (der Merge entfernt es)
    assert (tmp_path / "rohdaten" / "en-chunks" / "A, A" / "T1" / "chunk_001.md").read_text(encoding="utf-8") == "EN 1"
    assert (tmp_path / "Autor" / "A, A" / "T1" / "en" / "chunk_001.md").exists()
    assert not (tmp_path / "rohdaten" / "en-chunks" / "B, B").exists()      # leerer en-Ordner wird nicht kopiert
    # Rohdaten verschoben, Wurzel-Inbox zusammengefuehrt
    for p in ["Inbox/a.epub", "Inbox/b.pdf", "Lektor/A, A/T1/en/chunk_000.md", "Outbox/o.md", "Transfer/t.md"]:
        assert (tmp_path / "rohdaten" / p).is_file(), p
    assert not (tmp_path / "Inbox").exists() and not (tmp_path / "eBooks" / "Inbox").exists()
    assert ergebnis.zusammengefuehrt == 1 and not ergebnis.konflikte           # a.epub war identisch
    assert (tmp_path / "eBooks" / "ebook-translate.py").exists()               # Skripte noch unberuehrt (kommen in nachher)


def test_nachher_raeumt_reste_auf_und_pruefen_ist_gruen(tmp_path):
    _altbaum(tmp_path)
    for a in umbau.plan_vorher(tmp_path):
        umbau.fuehre_aus(a, umbau.Ergebnis())
    _merge_simulieren(tmp_path)
    ergebnis = umbau.Ergebnis()
    for a in umbau.plan_nachher(tmp_path):
        umbau.fuehre_aus(a, ergebnis)
    assert not ergebnis.konflikte
    # Reste aus Autor\ liegen jetzt im reader, en\ nicht
    assert (tmp_path / "reader" / "A, A" / "T1" / "notizen" / "_backup" / "alt.json").is_file()
    assert (tmp_path / "reader" / "B, B" / "T2" / "quelle" / "0001.md").is_file()
    assert not any(tmp_path.glob("reader/*/*/en"))
    assert not (tmp_path / "Autor").exists()
    # Altbestand und Skripte archiviert, Queue in hilfsdaten
    assert (tmp_path / "hilfsdaten" / "archiv" / "Autor.mov" / "Kant" / "k.md").is_file()
    assert (tmp_path / "hilfsdaten" / "notizen" / "queue.md").is_file()
    assert (tmp_path / "hilfsdaten" / "archiv" / "eBooks-vor-umbau" / "ebook-translate.py").read_text(encoding="utf-8") == "# alt"
    assert (tmp_path / "tools" / "pipeline" / "ebook-translate.py").read_text(encoding="utf-8") == "# neu"
    assert not (tmp_path / "eBooks").exists() and not (tmp_path / "notizen").exists()
    assert umbau.pruefen(tmp_path) == []


def test_abweichende_datei_wird_nie_ueberschrieben_sondern_gemeldet(tmp_path):
    _altbaum(tmp_path)
    _schreibe(tmp_path / "Inbox" / "a.epub", "ANDERER INHALT")                  # gleicher Name, anderer Inhalt
    ergebnis = umbau.Ergebnis()
    for a in umbau.plan_vorher(tmp_path):
        umbau.fuehre_aus(a, ergebnis)
    assert len(ergebnis.konflikte) == 1
    assert (tmp_path / "rohdaten" / "Inbox" / "a.epub").read_text(encoding="utf-8") == "EPUB"     # Ziel unveraendert
    assert (tmp_path / "Inbox" / "a.epub").read_text(encoding="utf-8") == "ANDERER INHALT"          # Quelle bleibt liegen
    assert (tmp_path / "rohdaten" / "Inbox" / "b.pdf").is_file()                                   # der Rest wurde trotzdem verschoben


def test_pruefen_meldet_altlasten(tmp_path):
    (tmp_path / "Autor").mkdir()
    (tmp_path / "reader").mkdir()
    probleme = umbau.pruefen(tmp_path)
    assert any("Autor" in p for p in probleme) and any("keine Buecher" in p for p in probleme)


def test_main_dry_run_veraendert_nichts_und_nachher_verlangt_den_merge(tmp_path, capsys):
    _altbaum(tmp_path)
    assert umbau.main(["vorher", "--root", str(tmp_path), "--trotz-aenderungen"]) == 0
    assert "Dry-Run" in capsys.readouterr().out
    assert (tmp_path / "Inbox" / "b.pdf").exists() and not (tmp_path / "rohdaten").exists()
    assert umbau.main(["nachher", "--root", str(tmp_path)]) == 3               # reader\ fehlt: Branch noch nicht gemergt
    assert "reader" in capsys.readouterr().out
