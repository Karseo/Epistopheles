import pytest
from episto_tui import suche
from episto_tui.app import EpistoApp
from episto_tui.widgets.reader_pane import ReaderPane
from episto_tui.widgets.such_screen import SuchScreen
from textual.widgets import OptionList, Input, Checkbox


def test_parse_anfrage_woerter_phrasen_und_kurze_begriffe():
    assert suche.parse_anfrage('Macht "Soziales Kapital" x') == ["macht", "soziales kapital"]
    assert suche.parse_anfrage("  ") == []
    assert suche.parse_anfrage("Macht macht MACHT") == ["macht"]


def test_findet_absatz_mit_index_und_ignoriert_grossschreibung(tmp_path, temp_buch):
    erg = suche.suche(tmp_path, "ZWEITER absatz")
    assert [(t.kapitel.nr, t.absatz_index) for t in erg.treffer] == [(1, 1)]
    assert erg.treffer[0].buch.titel == "Testbuch"
    assert not erg.abgeschnitten


def test_alle_begriffe_muessen_im_selben_absatz_stehen(tmp_path, temp_buch):
    # "Erster" und "letzte" kommen im Kapitel vor, aber in verschiedenen Absaetzen.
    assert suche.suche(tmp_path, "erster letzte").treffer == []
    assert len(suche.suche(tmp_path, "dritter letzte").treffer) == 1


def test_phrase_in_anfuehrungszeichen(tmp_path, temp_buch):
    assert len(suche.suche(tmp_path, '"mehr Inhalt"').treffer) == 1
    assert suche.suche(tmp_path, '"Inhalt mehr"').treffer == []


def test_ss_und_eszett_gelten_als_gleich(tmp_path, temp_buch):
    datei = temp_buch.pfad / "quelle" / "0002_zweites-kapitel.md"
    datei.write_text("Die Straße ist lang.", encoding="utf-8")
    assert len(suche.suche(tmp_path, "strasse").treffer) == 1
    assert len(suche.suche(tmp_path, "STRAßE").treffer) == 1


def test_treffer_ueber_mehrere_kapitel_in_reihenfolge(tmp_path, temp_buch):
    erg = suche.suche(tmp_path, "kapitels")
    assert [t.kapitel.nr for t in erg.treffer] == [1, 2]


def test_nur_buch_begrenzt_die_suche(tmp_path, temp_buch):
    anderes = tmp_path / "reader" / "Zweiter, Zoe" / "Anderes"
    (anderes / "quelle").mkdir(parents=True)
    (anderes / "quelle" / "0001_x.md").write_text("Absatz mit Kapitels.", encoding="utf-8")
    assert {t.buch.titel for t in suche.suche(tmp_path, "kapitels").treffer} == {"Testbuch", "Anderes"}
    erg = suche.suche(tmp_path, "kapitels", nur_buch=temp_buch)
    assert {t.buch.titel for t in erg.treffer} == {"Testbuch"}
    assert erg.buecher_durchsucht == 1


def test_max_treffer_schneidet_ab(tmp_path, temp_buch):
    erg = suche.suche(tmp_path, "kapitels", max_treffer=1)
    assert len(erg.treffer) == 1 and erg.abgeschnitten


def test_ohne_gueltigen_begriff_keine_suche(tmp_path, temp_buch):
    erg = suche.suche(tmp_path, "a")
    assert erg.treffer == [] and erg.buecher_durchsucht == 0


def test_snippet_zeigt_umfeld_der_fundstelle():
    from episto_tui.models import Buch, Kapitel
    absatz = "A" * 300 + " Zielwort " + "B" * 300
    t = suche.Treffer(Buch("a", "b", None), Kapitel(1, "k", "k.md"), 0, absatz,
                      position=absatz.casefold().find("zielwort"))
    s = t.snippet()
    assert "Zielwort" in s and s.startswith("…") and s.endswith("…")
    assert len(s) <= 162


def _langes_kapitel(temp_buch, n=80):
    absaetze = [f"Fuellabsatz Nummer {i} mit etwas Text, damit die Seite waechst." for i in range(n)]
    absaetze[60] = "Hier steht das Suchwort Quantenfeld mitten im langen Kapitel."
    (temp_buch.pfad / "quelle" / "0002_zweites-kapitel.md").write_text("\n\n".join(absaetze), encoding="utf-8")


@pytest.mark.asyncio
async def test_s_oeffnet_dialog_suche_springt_zum_absatz(tmp_path, temp_buch):
    _langes_kapitel(temp_buch)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.press("s")
        await pilot.pause()
        assert isinstance(app.screen, SuchScreen)
        app.screen.query_one("#such-eingabe", Input).value = "quantenfeld"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        liste = app.screen.query_one("#such-treffer", OptionList)
        assert liste.option_count == 1
        liste.focus()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        assert not isinstance(app.screen, SuchScreen)
        reader = app.query_one(ReaderPane)
        assert reader.kapitel.nr == 2
        scroll = reader.query_one("#anzeige-scroll")
        assert scroll.scroll_y > 0, "Lesebereich ist nicht zur Fundstelle gescrollt"


@pytest.mark.asyncio
async def test_esc_schliesst_dialog_ohne_sprung(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, SuchScreen)
        assert app.query_one(ReaderPane).kapitel is None


@pytest.mark.asyncio
async def test_keine_treffer_und_zu_kurze_eingabe_geben_meldung(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+f")
        await pilot.pause()
        eingabe = app.screen.query_one("#such-eingabe", Input)
        eingabe.value = "x"
        await pilot.press("enter")
        await pilot.pause()
        assert "Mindestens" in str(app.screen.query_one("#such-status").render())
        eingabe.value = "gibtesnirgends"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "Keine Treffer" in str(app.screen.query_one("#such-status").render())


@pytest.mark.asyncio
async def test_kontrollkasten_nur_aktuelles_buch_erscheint_erst_mit_offenem_kapitel(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("s")
        await pilot.pause()
        assert not app.screen.query(Checkbox)
        await pilot.press("escape")
        await pilot.pause()
        app.query_one(ReaderPane).lade_kapitel(
            temp_buch, __import__("episto_tui.library", fromlist=["x"]).list_chapters(temp_buch)[0])
        await pilot.press("s")
        await pilot.pause()
        assert len(app.screen.query(Checkbox)) == 1


@pytest.mark.asyncio
async def test_app_tasten_wirken_nicht_hinter_dem_dialog(tmp_path, temp_buch):
    """Mit dem Fokus auf der Trefferliste duerfen q (beenden) und n/p
    (blaettern) nicht durch den Dialog hindurch auf die App wirken. (Textual
    haelt die App-Bindings bei modalen Dialogen ohnehin zurueck; der Test sichert
    das ab, falls sich das aendert.)"""
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        app._oeffne(temp_buch, __import__("episto_tui.library", fromlist=["x"]).list_chapters(temp_buch)[0])
        for _ in range(3):
            await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        app.screen.query_one("#such-eingabe", Input).value = "kapitels"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        liste = app.screen.query_one("#such-treffer", OptionList)
        assert liste.option_count >= 1 and liste.has_focus
        vorher = app.query_one(ReaderPane).kapitel.nr
        await pilot.press("n", "p", "m", "s", "1", "q")
        await pilot.pause()
        assert isinstance(app.screen, SuchScreen)       # weder zweiter Dialog noch beendet
        assert app.query_one(ReaderPane).kapitel.nr == vorher
        assert app.is_running
