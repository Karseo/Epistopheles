import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input

from episto_tui.widgets.aktionsleiste import Aktionsleiste, TippKnopf


class _LeisteApp(App):
    def __init__(self) -> None:
        super().__init__()
        self.aktionen: list[str] = []

    def compose(self) -> ComposeResult:
        yield Input(id="eingabe")
        yield Aktionsleiste()

    def on_aktionsleiste_aktion_gewaehlt(self, nachricht: Aktionsleiste.AktionGewaehlt) -> None:
        self.aktionen.append(nachricht.aktion)


def _sichtbar(app: App) -> list[str]:
    return [knopf.name for knopf in app.query(TippKnopf) if knopf.display]


@pytest.mark.asyncio
async def test_startkontext_zeigt_nur_den_baum_knopf():
    app = _LeisteApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert _sichtbar(app) == ["baum", "suche", "notizen", "korr", "speed"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kontext, erwartet", [
    ("lesen", ["baum", "zurueck", "weiter", "suche", "notizen", "korr", "speed", "bearbeiten", "gelb", "rosa", "blau", "korrektur", "kommentar", "loeschen"]),
    ("bearbeiten", ["speichern", "verwerfen"]),
    ("felder", ["baum", "zurueck", "weiter", "suche", "notizen", "korr", "speed", "speichern"]),
    ("nur_baum", ["baum", "suche", "notizen", "korr", "speed"]),
])
async def test_kontext_bestimmt_die_sichtbaren_knoepfe(kontext, erwartet):
    app = _LeisteApp()
    async with app.run_test() as pilot:
        app.query_one(Aktionsleiste).setze_kontext(kontext)
        await pilot.pause()
        assert _sichtbar(app) == erwartet


@pytest.mark.asyncio
async def test_knopf_sendet_seine_aktion_und_nimmt_keinen_fokus():
    app = _LeisteApp()
    async with app.run_test() as pilot:
        app.query_one("#eingabe", Input).focus()
        app.query_one(Aktionsleiste).setze_kontext("lesen")
        await pilot.pause()
        await pilot.click("#knopf-gelb")
        await pilot.pause()
        assert app.aktionen == ["gelb"]
        assert app.focused is app.query_one("#eingabe", Input)


@pytest.mark.asyncio
async def test_lese_knoepfe_passen_in_45_spalten():
    app = _LeisteApp()
    async with app.run_test(size=(45, 10)) as pilot:
        app.query_one(Aktionsleiste).setze_kontext("lesen")
        await pilot.pause()
        sichtbare = [knopf for knopf in app.query(TippKnopf) if knopf.display]
        assert max(k.region.x + k.region.width for k in sichtbare) <= 45
        assert all(k.region.width > 0 for k in sichtbare)
