import pytest
from textual.widgets import Markdown, TabbedContent, TextArea
from textual.widgets.markdown import MarkdownBlock

from episto_tui import library
from episto_tui.app import EpistoApp
from episto_tui.widgets.aktionsleiste import Aktionsleiste, TippKnopf
from episto_tui.widgets.reader_pane import ReaderPane
from episto_tui.widgets.tree_sidebar import LibraryTree

_LESEN = ["baum", "zurueck", "weiter", "suche", "notizen", "korr", "speed", "bearbeiten", "gelb", "rosa", "blau", "korrektur", "kommentar", "loeschen"]


def _sichtbare_knoepfe(app) -> list[str]:
    return [knopf.name for knopf in app.query(TippKnopf) if knopf.display]


async def _waehle_erstes_kapitel(app, pilot) -> None:
    baum = app.query_one(LibraryTree)
    kapitel_knoten = list(baum.root.children)[0].children[0].children[0]
    baum.select_node(kapitel_knoten)
    for _ in range(3):
        await pilot.pause()


@pytest.mark.asyncio
async def test_breit_zeigt_baum_neben_den_tabs_ohne_aktionsleiste(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert not app.screen.has_class("schmal")
        assert 0 < app.query_one(LibraryTree).region.width <= 40
        assert app.query_one(TabbedContent).region.width > 0
        assert app.query_one(Aktionsleiste).region.height == 0


@pytest.mark.asyncio
async def test_schmal_startet_mit_offenem_baum_und_verborgenen_tabs(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        assert app.screen.has_class("schmal")
        assert app.screen.has_class("baum-offen")
        assert app.query_one(LibraryTree).region.width >= 40
        assert app.query_one(TabbedContent).region.height == 0
        assert app.query_one(Aktionsleiste).region.height == 1
        assert _sichtbare_knoepfe(app) == ["baum", "suche", "notizen", "korr", "speed"]


@pytest.mark.asyncio
async def test_offene_schublade_zeigt_nur_den_baum_knopf(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)
        assert _sichtbare_knoepfe(app) == _LESEN

        await pilot.click("#knopf-baum")
        await pilot.pause()
        await pilot.pause()
        assert app.screen.has_class("baum-offen")
        assert _sichtbare_knoepfe(app) == ["baum", "suche", "notizen", "korr", "speed"]

        await pilot.pause(0.3)
        await pilot.click("#knopf-baum")
        await pilot.pause()
        await pilot.pause()
        assert not app.screen.has_class("baum-offen")
        assert _sichtbare_knoepfe(app) == _LESEN


@pytest.mark.asyncio
async def test_kapitelwahl_schliesst_die_baum_ansicht(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)
        assert not app.screen.has_class("baum-offen")
        assert app.query_one(ReaderPane).kapitel.nr == 1
        assert app.query_one(TabbedContent).region.height > 0
        assert app.query_one(LibraryTree).region.width == 0


@pytest.mark.asyncio
async def test_baum_knopf_und_taste_null_schalten_die_ansicht_um(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)

        await pilot.click("#knopf-baum")
        await pilot.pause()
        assert app.screen.has_class("baum-offen")
        assert app.query_one(TabbedContent).region.height == 0

        # Textual ignoriert Klicks auf einen Button waehrend dessen Aktiv-Effekt
        # (0.2 s); pause() ohne Dauer wartet keine echte Zeit ab.
        await pilot.pause(0.3)
        await pilot.click("#knopf-baum")
        await pilot.pause()
        await pilot.pause()
        assert not app.screen.has_class("baum-offen")

        await pilot.press("0")
        await pilot.pause()
        assert app.screen.has_class("baum-offen")
        assert app.focused is app.query_one(LibraryTree)


@pytest.mark.asyncio
async def test_taste_null_fokussiert_im_breiten_modus_den_baum(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)
        assert app.focused is not app.query_one(LibraryTree)
        await pilot.press("0")
        await pilot.pause()
        assert app.focused is app.query_one(LibraryTree)
        assert not app.screen.has_class("baum-offen")


@pytest.mark.asyncio
async def test_wechsel_in_den_breiten_modus_setzt_baum_offen_zurueck(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        assert app.screen.has_class("baum-offen")
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        assert not app.screen.has_class("schmal")
        assert not app.screen.has_class("baum-offen")
        assert app.query_one(TabbedContent).region.width > 0


@pytest.mark.asyncio
async def test_leiste_wechselt_kontext_mit_tab_und_modus(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)
        assert _sichtbare_knoepfe(app) == _LESEN

        await pilot.press("2")
        await pilot.pause()
        assert _sichtbare_knoepfe(app) == ["baum", "zurueck", "weiter", "suche", "notizen", "korr", "speed", "speichern"]

        await pilot.press("5")
        await pilot.pause()
        assert _sichtbare_knoepfe(app) == ["baum", "suche", "notizen", "korr", "speed"]

        await pilot.press("1")
        await pilot.pause()
        assert _sichtbare_knoepfe(app) == _LESEN

        await pilot.click("#knopf-bearbeiten")
        await pilot.pause()
        assert app.query_one(ReaderPane).bearbeiten is True
        assert _sichtbare_knoepfe(app) == ["speichern", "verwerfen"]

        await pilot.click("#knopf-verwerfen")
        await pilot.pause()
        assert app.query_one(ReaderPane).bearbeiten is False
        assert _sichtbare_knoepfe(app) == _LESEN


@pytest.mark.asyncio
async def test_farbknopf_faerbt_den_zuletzt_angetippten_absatz(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)
        bloecke = list(app.query_one("#anzeige", Markdown).query_children(MarkdownBlock))
        await pilot.click(bloecke[1])
        await pilot.pause()
        await pilot.click("#knopf-gelb")
        await pilot.pause()
        highlights = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
        assert [(h.absatz_index, h.farbe) for h in highlights] == [(1, "gelb")]


@pytest.mark.asyncio
async def test_k_taste_markiert_absatz_als_korrektur(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)
        bloecke = list(app.query_one("#anzeige", Markdown).query_children(MarkdownBlock))
        await pilot.click(bloecke[1])
        await pilot.pause()
        await pilot.press("k")
        await pilot.pause()
        highlights = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
        assert [(h.absatz_index, h.farbe) for h in highlights] == [(1, "korrektur")]


@pytest.mark.asyncio
async def test_speichern_knopf_im_fazit_reiter_schreibt_die_zusammenfassung(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)
        await pilot.press("2")
        await pilot.pause()
        app.query_one("#feld-zusammenfassung", TextArea).text = "Per Knopf gespeichert."
        await pilot.click("#knopf-speichern")
        await pilot.pause()
        tag = library.read_tags(temp_buch, "0001_erstes-kapitel.md")
        assert tag.zusammenfassung == "Per Knopf gespeichert."


@pytest.mark.asyncio
async def test_offenes_kommentarfeld_ueberlebt_komm_und_farbknopf(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)
        bloecke = list(app.query_one("#anzeige", Markdown).query_children(MarkdownBlock))
        await pilot.click(bloecke[1])
        await pilot.pause()
        await pilot.click("#knopf-kommentar")
        await pilot.pause()
        eingabe = app.query_one("#kommentar-eingabe")
        assert app.focused is eingabe
        await pilot.press("N", "o", "t", "i", "z")
        assert eingabe.value == "Notiz"

        await pilot.pause(0.3)
        await pilot.click("#knopf-kommentar")
        await pilot.pause()
        assert eingabe.value == "Notiz"
        assert app.focused is eingabe

        await pilot.click("#knopf-gelb")
        for _ in range(3):
            await pilot.pause()
        assert eingabe.display is True
        assert eingabe.value == "Notiz"
        assert app.focused is eingabe


@pytest.mark.asyncio
async def test_korrektur_knopf_faerbt_den_zuletzt_angetippten_absatz(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)
        bloecke = list(app.query_one("#anzeige", Markdown).query_children(MarkdownBlock))
        await pilot.click(bloecke[1])
        await pilot.pause()
        await pilot.click("#knopf-korrektur")
        await pilot.pause()
        highlights = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
        assert [(h.absatz_index, h.farbe) for h in highlights] == [(1, "korrektur")]


@pytest.mark.asyncio
async def test_breit_baum_und_tabs_stehen_nebeneinander(tmp_path, temp_buch):
    """Regression: TabbedContent ausserhalb des Horizontal-Containers schrumpfte
    den Baum auf eine Zeile und legte die Tabs darunter."""
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        baum = app.query_one(LibraryTree).region
        tabs = app.query_one(TabbedContent).region
        assert baum.height > 10
        assert tabs.x >= baum.right
        assert tabs.y == baum.y


@pytest.mark.asyncio
async def test_kapitelwahl_loest_keine_fehlermeldung_aus(tmp_path, temp_buch, monkeypatch):
    """Regression: die Lade-Schleife fragte entfernte Panes ab -> bei jeder
    Kapitelwahl erschien der Toast "Fehler beim Laden"."""
    app = EpistoApp(root=tmp_path)
    meldungen = []
    monkeypatch.setattr(app, "notify", lambda *a, **k: meldungen.append((a, k)))
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)
        assert meldungen == []
