from episto_tui import library
from episto_tui.models import Highlight


def test_read_highlights_ohne_datei_gibt_leere_liste(temp_buch):
    assert library.read_highlights(temp_buch, "0001_erstes-kapitel.md") == []


def test_write_highlight_und_wieder_lesen(temp_buch):
    highlight = Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=0,
        absatz_anfang="Erster Absatz", farbe="gelb",
    )
    library.write_highlight(temp_buch, highlight)

    gelesen = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
    assert len(gelesen) == 1
    assert gelesen[0].farbe == "gelb"


def test_write_highlight_ersetzt_vorhandene_farbe_am_selben_absatz(temp_buch):
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=0,
        absatz_anfang="Erster Absatz", farbe="gelb",
    ))
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=0,
        absatz_anfang="Erster Absatz", farbe="blau",
    ))

    gelesen = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
    assert len(gelesen) == 1
    assert gelesen[0].farbe == "blau"


def test_read_highlights_filtert_nach_datei(temp_buch):
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=0, absatz_anfang="X", farbe="gelb",
    ))
    library.write_highlight(temp_buch, Highlight(
        datei="0002_zweites-kapitel.md", absatz_index=0, absatz_anfang="Y", farbe="rosa",
    ))

    nur_kapitel_2 = library.read_highlights(temp_buch, "0002_zweites-kapitel.md")
    assert len(nur_kapitel_2) == 1
    assert nur_kapitel_2[0].farbe == "rosa"


def test_remove_highlight_entfernt_genau_diesen_absatz(temp_buch):
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=0, absatz_anfang="X", farbe="gelb",
    ))
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=1, absatz_anfang="Y", farbe="rosa",
    ))

    library.remove_highlight(temp_buch, "0001_erstes-kapitel.md", 0)

    gelesen = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
    assert len(gelesen) == 1
    assert gelesen[0].absatz_index == 1


def test_remove_highlight_ohne_datei_tut_nichts(temp_buch):
    library.remove_highlight(temp_buch, "0001_erstes-kapitel.md", 0)  # keine Exception
    assert library.read_highlights(temp_buch, "0001_erstes-kapitel.md") == []


def test_write_highlight_sichert_vorherigen_stand(temp_buch):
    erster = Highlight(datei="a.md", absatz_index=0, absatz_anfang="A", farbe="gelb")
    library.write_highlight(temp_buch, erster)
    zweiter = Highlight(datei="a.md", absatz_index=1, absatz_anfang="B", farbe="rosa")
    library.write_highlight(temp_buch, zweiter)

    backups = list((temp_buch.pfad / "notizen" / "_backup").glob("highlights.*.json"))
    assert len(backups) == 1  # beim ersten Anlegen existierte die Datei noch nicht


def test_read_highlights_nach_farbe_filtert_ueber_alle_dateien(temp_buch):
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=0, absatz_anfang="X", farbe="korrektur"))
    library.write_highlight(temp_buch, Highlight(
        datei="0002_zweites-kapitel.md", absatz_index=0, absatz_anfang="Y", farbe="korrektur"))
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=1, absatz_anfang="Z", farbe="gelb"))

    nur_korrektur = library.read_highlights_nach_farbe(temp_buch, "korrektur")
    assert {h.datei for h in nur_korrektur} == {"0001_erstes-kapitel.md", "0002_zweites-kapitel.md"}
    assert all(h.farbe == "korrektur" for h in nur_korrektur)
