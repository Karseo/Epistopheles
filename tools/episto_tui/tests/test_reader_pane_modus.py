import pytest
from textual.app import App, ComposeResult

from episto_tui.models import Kapitel
from episto_tui.widgets.reader_pane import ReaderPane


class _ModusApp(App):
    def __init__(self) -> None:
        super().__init__()
        self.moduse: list[bool] = []

    def compose(self) -> ComposeResult:
        yield ReaderPane()

    def on_reader_pane_modus_geaendert(self, nachricht: ReaderPane.ModusGeaendert) -> None:
        self.moduse.append(nachricht.bearbeiten)


@pytest.mark.asyncio
async def test_reader_pane_meldet_wechsel_zwischen_lesen_und_bearbeiten(temp_buch):
    app = _ModusApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        app.moduse.clear()

        pane.action_toggle_edit()
        await pilot.pause()
        assert app.moduse == [True]

        pane.action_verwerfen()
        await pilot.pause()
        assert app.moduse == [True, False]
        assert pane.bearbeiten is False
