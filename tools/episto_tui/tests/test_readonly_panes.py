import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static
from episto_tui.widgets.straenge_pane import StraengePane
from episto_tui.widgets.querbezuege_pane import QuerbezuegePane
from episto_tui.models import Kapitel


class _AnzeigeTestApp(App):
    def compose(self) -> ComposeResult:
        yield StraengePane()
        yield QuerbezuegePane()


@pytest.mark.asyncio
async def test_straenge_pane_zeigt_treffer(temp_buch):
    app = _AnzeigeTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(StraengePane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        inhalt = str(app.query_one(StraengePane).query_one("#inhalt", Static).content)
        assert "Test-Strang" in inhalt


@pytest.mark.asyncio
async def test_straenge_pane_zeigt_platzhalter_ohne_treffer(temp_buch):
    app = _AnzeigeTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(StraengePane)
        pane.lade_kapitel(temp_buch, Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md"))
        await pilot.pause()
        inhalt = str(app.query_one(StraengePane).query_one("#inhalt", Static).content)
        assert "Keine Themen" in inhalt


@pytest.mark.asyncio
async def test_querbezuege_pane_zeigt_bezuege(temp_buch):
    app = _AnzeigeTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(QuerbezuegePane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        inhalt = str(app.query_one(QuerbezuegePane).query_one("#inhalt", Static).content)
        assert "Externer Autor" in inhalt


# --- I-3: Datentext darf nie als Textual-Markup interpretiert werden -------

def _gerendert(widget) -> str:
    return widget.render().plain


@pytest.mark.asyncio
async def test_straenge_pane_zeigt_eckige_klammern_woertlich(temp_buch):
    (temp_buch.pfad / "notizen" / "straenge" / "test-strang.md").write_text(
        "---\nstrang: Klammer-Strang\n---\n\n"
        "### Kapitel 1 · Erstes Kapitel\n"
        "- Popper [LdF] S. 12 [bold]fett?[/bold] und [/] kaputt\n",
        encoding="utf-8",
    )
    app = _AnzeigeTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(StraengePane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        text = _gerendert(pane.query_one("#inhalt", Static))
        assert "Popper [LdF] S. 12 [bold]fett?[/bold] und [/] kaputt" in text


@pytest.mark.asyncio
async def test_querbezuege_pane_zeigt_eckige_klammern_woertlich(temp_buch):
    import json
    (temp_buch.pfad / "querbezuege" / "querbezuege.json").write_text(
        json.dumps({"bezuege": [{
            "autor": "Popper [Hrsg.]", "titel": "LdF [1934]",
            "relation": "ergaenzt", "notiz": "Siehe [/] und [bold]x[/bold].",
        }]}),
        encoding="utf-8",
    )
    app = _AnzeigeTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(QuerbezuegePane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        text = _gerendert(pane.query_one("#inhalt", Static))
        assert "Popper [Hrsg.]" in text
        assert "LdF [1934]" in text
        assert "Siehe [/] und [bold]x[/bold]." in text
