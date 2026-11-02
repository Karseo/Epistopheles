from episto_tui import library
from episto_tui.models import Buch


def test_discover_books_findet_buecher_mit_quelle_ordner(tmp_path, temp_buch):
    gefunden = library.discover_books(tmp_path)
    assert len(gefunden) == 1
    assert gefunden[0].autor == "Testautor, Theo"
    assert gefunden[0].titel == "Testbuch"


def test_discover_books_ignoriert_ordner_ohne_quelle(tmp_path):
    (tmp_path / "reader" / "X" / "OhneQuelle").mkdir(parents=True)
    gefunden = library.discover_books(tmp_path)
    assert gefunden == []


def test_discover_books_liest_nur_den_reader_ordner_und_ueberspringt_exporte(tmp_path):
    def buch(pfad):
        (pfad / "quelle").mkdir(parents=True)
    buch(tmp_path / "reader" / "Autor, A" / "Echt")
    buch(tmp_path / "reader" / "export-epistopheles" / "korrektur")       # Export ist kein Autor
    buch(tmp_path / "reader" / "_technisch" / "X")
    buch(tmp_path / "rohdaten" / "Lektor" / "Autor, B" / "Roh")           # Rohdaten sind keine Buecher
    buch(tmp_path / "Autor" / "Alt, C" / "AlterOrdner")                   # der Ordner heisst nicht mehr Autor
    assert [(b.autor, b.titel) for b in library.discover_books(tmp_path)] == [("Autor, A", "Echt")]


def test_discover_books_leeres_root_gibt_leere_liste(tmp_path):
    assert library.discover_books(tmp_path) == []


def test_list_chapters_liest_kapitel_index(temp_buch):
    kapitel = library.list_chapters(temp_buch)
    assert [k.datei for k in kapitel] == ["0001_erstes-kapitel.md", "0002_zweites-kapitel.md"]
    assert kapitel[0].nr == 1
    assert kapitel[0].titel == "Erstes Kapitel"


def test_list_chapters_fallback_ohne_index(tmp_path):
    buch = Buch(autor="A", titel="B", pfad=tmp_path / "reader" / "A" / "B")
    (buch.pfad / "quelle").mkdir(parents=True)
    (buch.pfad / "quelle" / "0001_irgendwas.md").write_text("x", encoding="utf-8")
    kapitel = library.list_chapters(buch)
    assert len(kapitel) == 1
    assert kapitel[0].datei == "0001_irgendwas.md"


def test_list_chapters_fallback_bei_kaputtem_index(tmp_path):
    buch = Buch(autor="A", titel="B", pfad=tmp_path / "reader" / "A" / "B")
    (buch.pfad / "quelle").mkdir(parents=True)
    (buch.pfad / "quelle" / "0001_kapitel.md").write_text("x", encoding="utf-8")
    (buch.pfad / "quelle" / "0002_kapitel.md").write_text("y", encoding="utf-8")
    # Schreibe malformed JSON -> sollte fallback zu Glob auslösen
    (buch.pfad / "quelle" / "_kapitel_index.json").write_text(
        "{invalid json content", encoding="utf-8"
    )
    kapitel = library.list_chapters(buch)
    # Sollte auf Glob zurückfallen und 2 Dateien finden
    assert len(kapitel) == 2
    assert kapitel[0].datei == "0001_kapitel.md"
    assert kapitel[1].datei == "0002_kapitel.md"


def test_list_chapters_fallback_bei_fehlenden_feldern(tmp_path):
    buch = Buch(autor="A", titel="B", pfad=tmp_path / "reader" / "A" / "B")
    (buch.pfad / "quelle").mkdir(parents=True)
    (buch.pfad / "quelle" / "0001_kapitel.md").write_text("x", encoding="utf-8")
    # Schreibe JSON mit fehlenden Feldern -> sollte fallback zu Glob auslösen
    (buch.pfad / "quelle" / "_kapitel_index.json").write_text(
        '[{"nr": 1}]', encoding="utf-8"  # titel und datei fehlen
    )
    kapitel = library.list_chapters(buch)
    # Sollte auf Glob zurückfallen und 1 Datei finden
    assert len(kapitel) == 1
    assert kapitel[0].datei == "0001_kapitel.md"


def test_list_chapters_fallback_bei_index_als_dict(tmp_path):
    """I-1: _kapitel_index.json ist valides JSON, aber ein Objekt statt einer
    Liste -> Glob-Fallback statt Absturz (vorher startete die App nicht)."""
    buch = Buch(autor="A", titel="B", pfad=tmp_path / "reader" / "A" / "B")
    (buch.pfad / "quelle").mkdir(parents=True)
    (buch.pfad / "quelle" / "0001_kapitel.md").write_text("x", encoding="utf-8")
    (buch.pfad / "quelle" / "_kapitel_index.json").write_text(
        '{"nr": 1, "titel": "T", "datei": "0001_kapitel.md"}', encoding="utf-8"
    )
    kapitel = library.list_chapters(buch)
    assert [k.datei for k in kapitel] == ["0001_kapitel.md"]


def test_list_chapters_fallback_bei_index_mit_nicht_dict_eintraegen(tmp_path):
    buch = Buch(autor="A", titel="B", pfad=tmp_path / "reader" / "A" / "B")
    (buch.pfad / "quelle").mkdir(parents=True)
    (buch.pfad / "quelle" / "0001_kapitel.md").write_text("x", encoding="utf-8")
    (buch.pfad / "quelle" / "_kapitel_index.json").write_text("[1, 2]", encoding="utf-8")
    kapitel = library.list_chapters(buch)
    assert [k.datei for k in kapitel] == ["0001_kapitel.md"]
