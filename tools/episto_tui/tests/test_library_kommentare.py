from episto_tui import library
from episto_tui.models import Kommentar


def test_read_kommentare_ohne_datei_gibt_leere_liste(temp_buch):
    assert library.read_kommentare(temp_buch, "0001_erstes-kapitel.md") == []


def test_add_kommentar_und_wieder_lesen(temp_buch):
    kommentar = Kommentar(
        datei="0001_erstes-kapitel.md", absatz_index=0,
        absatz_anfang="Erster Absatz", text="Testkommentar",
        erstellt="2026-09-27 15:00",
    )
    library.add_kommentar(temp_buch, kommentar)

    gelesen = library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")
    assert len(gelesen) == 1
    assert gelesen[0].text == "Testkommentar"


def test_read_kommentare_filtert_nach_datei(temp_buch):
    library.add_kommentar(temp_buch, Kommentar(
        datei="0001_erstes-kapitel.md", absatz_index=0, absatz_anfang="X",
        text="Kapitel 1", erstellt="2026-09-27",
    ))
    library.add_kommentar(temp_buch, Kommentar(
        datei="0002_zweites-kapitel.md", absatz_index=0, absatz_anfang="Y",
        text="Kapitel 2", erstellt="2026-09-27",
    ))

    nur_kapitel_2 = library.read_kommentare(temp_buch, "0002_zweites-kapitel.md")
    assert len(nur_kapitel_2) == 1
    assert nur_kapitel_2[0].text == "Kapitel 2"


def test_add_kommentar_sichert_vorherigen_stand(temp_buch):
    erster = Kommentar(datei="a.md", absatz_index=0, absatz_anfang="A", text="Erst", erstellt="t")
    library.add_kommentar(temp_buch, erster)
    zweiter = Kommentar(datei="a.md", absatz_index=1, absatz_anfang="B", text="Zweit", erstellt="t")
    library.add_kommentar(temp_buch, zweiter)

    backups = list((temp_buch.pfad / "notizen" / "_backup").glob("kommentare.*.json"))
    assert len(backups) == 1  # beim ersten Anlegen existierte die Datei noch nicht


def _kommentar(text="Notiz", absatz_index=0, datei="0001_erstes-kapitel.md"):
    return Kommentar(
        datei=datei, absatz_index=absatz_index, absatz_anfang="Anfang",
        text=text, erstellt="2026-09-28 10:00",
    )


def test_update_kommentar_aendert_nur_den_text_des_treffers(temp_buch):
    a = _kommentar("Alt", absatz_index=0)
    b = _kommentar("Anderer", absatz_index=1)
    library.add_kommentar(temp_buch, a)
    library.add_kommentar(temp_buch, b)

    library.update_kommentar(temp_buch, a, "Neu")

    gelesen = library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")
    assert [(k.absatz_index, k.text) for k in gelesen] == [(0, "Neu"), (1, "Anderer")]
    assert gelesen[0].erstellt == "2026-09-28 10:00"
    assert gelesen[0].absatz_anfang == "Anfang"


def test_update_kommentar_ohne_treffer_tut_nichts_und_sichert_nicht(temp_buch):
    library.add_kommentar(temp_buch, _kommentar("Da"))

    library.update_kommentar(temp_buch, _kommentar("Nicht vorhanden"), "X")

    gelesen = library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")
    assert [k.text for k in gelesen] == ["Da"]
    assert list((temp_buch.pfad / "notizen" / "_backup").glob("kommentare.*.json")) == []


def test_update_und_remove_ohne_datei_tun_nichts(temp_buch):
    library.update_kommentar(temp_buch, _kommentar(), "X")  # keine Exception
    library.remove_kommentar(temp_buch, _kommentar())       # keine Exception
    assert not (temp_buch.pfad / "notizen" / "kommentare.json").exists()


def test_remove_kommentar_entfernt_genau_einen_von_zwei_identischen(temp_buch):
    gleich = _kommentar("Gleich")
    library.add_kommentar(temp_buch, gleich)
    library.add_kommentar(temp_buch, gleich)

    library.remove_kommentar(temp_buch, gleich)

    assert len(library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")) == 1


def test_remove_kommentar_laesst_andere_absaetze_und_kapitel_unberuehrt(temp_buch):
    a = _kommentar("A", absatz_index=0)
    b = _kommentar("B", absatz_index=1)
    c = _kommentar("C", absatz_index=0, datei="0002_zweites-kapitel.md")
    for k in (a, b, c):
        library.add_kommentar(temp_buch, k)

    library.remove_kommentar(temp_buch, a)

    assert [k.text for k in library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")] == ["B"]
    assert [k.text for k in library.read_kommentare(temp_buch, "0002_zweites-kapitel.md")] == ["C"]


def test_update_und_remove_sichern_vorherigen_stand(temp_buch):
    a = _kommentar("Eins")
    library.add_kommentar(temp_buch, a)  # Datei existiert noch nicht: kein Backup

    library.update_kommentar(temp_buch, a, "Zwei")
    library.remove_kommentar(temp_buch, _kommentar("Zwei"))

    backups = list((temp_buch.pfad / "notizen" / "_backup").glob("kommentare.*.json"))
    assert len(backups) == 2
