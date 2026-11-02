import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static
from episto_tui.app import EpistoApp
from episto_tui.models import Buch, Kapitel
from episto_tui.widgets.tree_sidebar import LibraryTree


async def _waehle_begriff(app, pilot) -> LibraryTree:
    baum = app.query_one(LibraryTree)
    baum.focus()
    await pilot.press("slash", "t", "e")  # >= 2 Zeichen: Begriffe-Knoten fuellt sich
    baum.select_node(list(baum.root.children)[1].children[0])
    for _ in range(3):
        await pilot.pause()
    return baum


@pytest.mark.asyncio
async def test_klick_auf_quellzeile_springt_zum_kapitel_in_der_bibliothek(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        baum = await _waehle_begriff(app, pilot)
        assert baum.filter_text == "te"

        await pilot.click("#quelle")
        for _ in range(3):
            await pilot.pause()

        assert baum.filter_text == ""  # Filter haette das Kapitel ausblenden koennen
        knoten = baum.cursor_node
        assert knoten is not None and knoten.data is not None
        assert knoten.data[0].pfad == temp_buch.pfad
        assert knoten.data[1].datei == "0001_erstes-kapitel.md"
        bibliothek = list(baum.root.children)[0]
        assert knoten.parent.parent is bibliothek
        assert bibliothek.is_expanded and knoten.parent.is_expanded
        assert app.focused is baum
        # Nach dem Sprung verschwindet die Herkunftszeile aus dem Textfenster ...
        from episto_tui.widgets.herkunft import Herkunft
        assert app.query_one(Herkunft).has_class("leer")
        assert app.query_one(Herkunft).region.height == 0
        # ... und kommt bei der naechsten Kapitelwahl wieder.
        baum.select_node(knoten.parent.children[1])
        for _ in range(3):
            await pilot.pause()
        assert not app.query_one(Herkunft).has_class("leer")
        assert "2. Zweites Kapitel" in str(app.query_one("#quelle", Static).content)


@pytest.mark.asyncio
async def test_klick_auf_quellzeile_oeffnet_im_schmalen_layout_die_schublade(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        baum = await _waehle_begriff(app, pilot)
        assert not app.screen.has_class("baum-offen")  # Kapitelwahl schliesst die Schublade

        await pilot.click("#quelle")
        for _ in range(3):
            await pilot.pause()

        assert app.screen.has_class("baum-offen")
        assert baum.cursor_node.data[1].datei == "0001_erstes-kapitel.md"
        assert app.focused is baum
        from episto_tui.widgets.herkunft import Herkunft
        assert app.query_one(Herkunft).has_class("leer")


@pytest.mark.asyncio
async def test_quellzeile_ohne_gewaehltes_kapitel_ist_ausgeblendet(tmp_path, temp_buch):
    from episto_tui.widgets.herkunft import Herkunft
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        assert app.query_one(Herkunft).has_class("leer")
        assert app.query_one(Herkunft).region.height == 0


class _BaumApp(App):
    def __init__(self, root):
        super().__init__()
        self._root = root

    def compose(self) -> ComposeResult:
        yield LibraryTree(self._root)


@pytest.mark.asyncio
async def test_zeige_kapitel_meldet_false_fuer_unbekanntes_kapitel(tmp_path, temp_buch):
    app = _BaumApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        unbekannt = Buch("Niemand", "Nichts", tmp_path / "reader" / "Niemand" / "Nichts")
        assert baum.zeige_kapitel(unbekannt, Kapitel(1, "x", "0001_x.md")) is False
