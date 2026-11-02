from episto_tui import library


def test_read_chapter_text(temp_buch):
    text = library.read_chapter_text(temp_buch, "0002_zweites-kapitel.md")
    assert text == "Einziger Absatz des zweiten Kapitels."


def test_write_chapter_text_schreibt_und_sichert(temp_buch):
    library.write_chapter_text(temp_buch, "0002_zweites-kapitel.md", "Neuer Inhalt.")

    assert library.read_chapter_text(temp_buch, "0002_zweites-kapitel.md") == "Neuer Inhalt."

    backups = list((temp_buch.pfad / "notizen" / "_backup").glob("0002_zweites-kapitel.*.md"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "Einziger Absatz des zweiten Kapitels."
