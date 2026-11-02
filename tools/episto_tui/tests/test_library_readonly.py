from episto_tui import library


def test_read_straenge_for_chapter_findet_treffer(temp_buch):
    treffer = library.read_straenge_for_chapter(temp_buch, 1)
    assert len(treffer) == 1
    assert treffer[0]["strang"] == "Test-Strang"
    assert treffer[0]["abschnitt"] == "Erstes Kapitel"
    assert "Testthese" in treffer[0]["inhalt"]


def test_read_straenge_for_chapter_ohne_treffer(temp_buch):
    assert library.read_straenge_for_chapter(temp_buch, 2) == []


def test_read_straenge_for_chapter_ohne_ordner(tmp_path):
    from episto_tui.models import Buch
    buch = Buch(autor="A", titel="B", pfad=tmp_path)
    assert library.read_straenge_for_chapter(buch, 1) == []


def test_read_querbezuege_liest_bezuege(temp_buch):
    bezuege = library.read_querbezuege(temp_buch)
    assert len(bezuege) == 1
    assert bezuege[0]["autor"] == "Externer Autor"


def test_read_querbezuege_ohne_datei(tmp_path):
    from episto_tui.models import Buch
    buch = Buch(autor="A", titel="B", pfad=tmp_path)
    assert library.read_querbezuege(buch) == []


def test_read_querbezuege_malformed_json_array(tmp_path):
    from episto_tui.models import Buch
    buch_pfad = tmp_path / "reader" / "A" / "B"
    querbezuege_dir = buch_pfad / "querbezuege"
    querbezuege_dir.mkdir(parents=True)
    (querbezuege_dir / "querbezuege.json").write_text("[]", encoding="utf-8")
    buch = Buch(autor="A", titel="B", pfad=buch_pfad)
    assert library.read_querbezuege(buch) == []


def test_read_querbezuege_malformed_json_number(tmp_path):
    from episto_tui.models import Buch
    buch_pfad = tmp_path / "reader" / "A" / "B"
    querbezuege_dir = buch_pfad / "querbezuege"
    querbezuege_dir.mkdir(parents=True)
    (querbezuege_dir / "querbezuege.json").write_text("42", encoding="utf-8")
    buch = Buch(autor="A", titel="B", pfad=buch_pfad)
    assert library.read_querbezuege(buch) == []


def test_read_straenge_with_different_separator(tmp_path):
    from episto_tui.models import Buch
    buch_pfad = tmp_path / "reader" / "A" / "B"
    straenge_dir = buch_pfad / "notizen" / "straenge"
    straenge_dir.mkdir(parents=True)
    (straenge_dir / "test-alt.md").write_text(
        "---\n"
        "strang: Alt-Strang\n"
        "---\n\n"
        "### Kapitel 1 | Ein anderer Titel\n"
        "Inhalt mit anderem Separator.\n",
        encoding="utf-8",
    )
    buch = Buch(autor="A", titel="B", pfad=buch_pfad)
    treffer = library.read_straenge_for_chapter(buch, 1)
    assert len(treffer) == 1
    assert treffer[0]["abschnitt"] == "Ein anderer Titel"
    assert treffer[0]["strang"] == "Alt-Strang"
