import pytest
from textual.app import App, ComposeResult
from textual.widgets import TextArea, Static
from episto_tui.widgets.tags_pane import TagsPane, ZusammenfassungPane
from episto_tui.models import Kapitel


class _TagsTestApp(App):
    """Zeigt beide Tag-Panes, wie die echte App (je einen Teil der Felder)."""

    def compose(self) -> ComposeResult:
        yield ZusammenfassungPane()
        yield TagsPane()


@pytest.mark.asyncio
async def test_lade_kapitel_zeigt_vorhandene_tags(temp_buch):
    app = _TagsTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ZusammenfassungPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        assert app.query_one("#feld-these", TextArea).text == "Testthese"
        assert pane.query_one("#hinweis", Static).content == ""


@pytest.mark.asyncio
async def test_lade_kapitel_zeigt_hinweis_ohne_tags(temp_buch):
    app = _TagsTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ZusammenfassungPane)
        pane.lade_kapitel(temp_buch, Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md"))
        await pilot.pause()
        hinweis = str(pane.query_one("#hinweis", Static).content)
        assert "taggen.ps1" in hinweis


@pytest.mark.asyncio
async def test_speichern_schreibt_geaenderte_these(temp_buch):
    app = _TagsTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ZusammenfassungPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()

        feld = app.query_one("#feld-these", TextArea)
        feld.text = "Geaenderte These 1\nGeaenderte These 2"

        pane.focus()
        await pilot.press("ctrl+s")
        await pilot.pause()

        from episto_tui import library
        tag = library.read_tags(temp_buch, "0001_erstes-kapitel.md")
        assert tag.these == ["Geaenderte These 1", "Geaenderte These 2"]


@pytest.mark.asyncio
async def test_speichern_mit_fokus_auf_textarea_feld(temp_buch):
    """Realistischer Ablauf: Nutzer klickt in ein Feld, tippt, drueckt ctrl+s,
    WAEHREND das TextArea-Feld selbst (nicht die TagsPane) den Fokus haelt.
    Bestaetigt, dass TextArea._on_key() ctrl+s nicht abfaengt und das Binding
    trotzdem bis zur TagsPane durchbubbelt."""
    app = _TagsTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ZusammenfassungPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()

        feld = app.query_one("#feld-these", TextArea)
        feld.focus()
        await pilot.pause()
        assert app.focused is feld

        feld.text = "Fokussiertes Feld These"
        await pilot.press("ctrl+s")
        await pilot.pause()

        from episto_tui import library
        tag = library.read_tags(temp_buch, "0001_erstes-kapitel.md")
        assert tag.these == ["Fokussiertes Feld These"]


def _sammle_meldungen(app, monkeypatch) -> list[str]:
    meldungen: list[str] = []
    original = app.notify

    def notify(message, *args, **kwargs):
        meldungen.append(str(message))
        return original(message, *args, **kwargs)

    monkeypatch.setattr(app, "notify", notify)
    return meldungen


@pytest.mark.asyncio
async def test_speichern_ohne_eingabe_bei_ungetaggtem_kapitel_schreibt_nichts(temp_buch, monkeypatch):
    """I-6: ctrl+s auf dem leeren Platzhalter eines ungetaggten Kapitels darf
    keinen leeren Stub in tags.json schreiben -- taggen.ps1 wuerde das
    Kapitel sonst fuer immer als "schon getaggt" ueberspringen."""
    tags_pfad = temp_buch.pfad / "notizen" / "tags.json"
    vorher = tags_pfad.read_bytes()
    app = _TagsTestApp()
    async with app.run_test() as pilot:
        meldungen = _sammle_meldungen(app, monkeypatch)
        pane = app.query_one(ZusammenfassungPane)
        pane.lade_kapitel(temp_buch, Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md"))
        await pilot.pause()
        pane.focus()
        await pilot.press("ctrl+s")
        await pilot.pause()

        from episto_tui import library
        assert library.read_tags(temp_buch, "0002_zweites-kapitel.md") is None
        assert tags_pfad.read_bytes() == vorher
        assert not (temp_buch.pfad / "notizen" / "_backup").exists()
        assert any("Nichts zu speichern" in m for m in meldungen)
        assert not any(m == "Gespeichert." for m in meldungen)


@pytest.mark.asyncio
async def test_speichern_ohne_eingabe_legt_keine_tags_json_an(temp_buch, monkeypatch):
    """Wie oben, aber ohne vorhandene tags.json: es darf keine entstehen."""
    tags_pfad = temp_buch.pfad / "notizen" / "tags.json"
    tags_pfad.unlink()
    app = _TagsTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ZusammenfassungPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        pane.focus()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert not tags_pfad.exists()


@pytest.mark.asyncio
async def test_neues_taggen_ueber_ui_wird_gespeichert(temp_buch, monkeypatch):
    """I-6-Gegenprobe: tippt der Nutzer etwas in ein ungetaggtes Kapitel,
    muss das ganz normal gespeichert werden."""
    app = _TagsTestApp()
    async with app.run_test() as pilot:
        meldungen = _sammle_meldungen(app, monkeypatch)
        pane = app.query_one(ZusammenfassungPane)
        pane.lade_kapitel(temp_buch, Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md"))
        await pilot.pause()
        feld = app.query_one("#feld-these", TextArea)
        feld.focus()
        await pilot.pause()
        await pilot.press("N", "e", "u")
        await pilot.press("ctrl+s")
        await pilot.pause()

        from episto_tui import library
        tag = library.read_tags(temp_buch, "0002_zweites-kapitel.md")
        assert tag is not None
        assert tag.these == ["Neu"]
        assert "Gespeichert." in meldungen


@pytest.mark.asyncio
async def test_nur_zusammenfassung_bei_ungetaggtem_kapitel_wird_gespeichert(temp_buch):
    app = _TagsTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ZusammenfassungPane)
        pane.lade_kapitel(temp_buch, Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md"))
        await pilot.pause()
        app.query_one("#feld-zusammenfassung", TextArea).text = "Nur eine Zusammenfassung."
        pane.focus()
        await pilot.press("ctrl+s")
        await pilot.pause()

        from episto_tui import library
        tag = library.read_tags(temp_buch, "0002_zweites-kapitel.md")
        assert tag is not None
        assert tag.zusammenfassung == "Nur eine Zusammenfassung."


@pytest.mark.asyncio
async def test_speichern_eines_getaggten_kapitels_meldet_gespeichert(temp_buch, monkeypatch):
    app = _TagsTestApp()
    async with app.run_test() as pilot:
        meldungen = _sammle_meldungen(app, monkeypatch)
        pane = app.query_one(ZusammenfassungPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        pane.focus()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert meldungen == ["Gespeichert."]


@pytest.mark.asyncio
async def test_jede_pane_zeigt_nur_ihre_felder(temp_buch):
    app = _TagsTestApp()
    async with app.run_test() as pilot:
        for pane_typ in (ZusammenfassungPane, TagsPane):
            app.query_one(pane_typ).lade_kapitel(
                temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        def felder(pane_typ):
            return [f.id for f in app.query_one(pane_typ).query(TextArea)]
        assert felder(ZusammenfassungPane) == ["feld-zusammenfassung", "feld-these", "feld-beleg"]
        assert felder(TagsPane) == ["feld-gegen", "feld-kern", "feld-def_"]


@pytest.mark.asyncio
async def test_speichern_in_einer_pane_ueberschreibt_andere_felder_nicht(temp_buch):
    """Die Panes laden denselben Tag und speichern je einen Teil: Speichern in
    der Fazit-Pane darf eine spaetere, in der Tags-Pane gespeicherte Aenderung
    (und umgekehrt) nicht mit dem beim Laden gemerkten Stand ueberschreiben."""
    from episto_tui import library
    app = _TagsTestApp()
    async with app.run_test() as pilot:
        for pane_typ in (ZusammenfassungPane, TagsPane):
            app.query_one(pane_typ).lade_kapitel(
                temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        thesen, tags = app.query_one(ZusammenfassungPane), app.query_one(TagsPane)

        thesen.query_one("#feld-these", TextArea).text = "Neue These"
        thesen.focus()
        await pilot.press("ctrl+s")
        await pilot.pause()

        tags.query_one("#feld-kern", TextArea).text = "Neuer Kernbegriff"
        tags.focus()
        await pilot.press("ctrl+s")
        await pilot.pause()

        tag = library.read_tags(temp_buch, "0001_erstes-kapitel.md")
        assert tag.these == ["Neue These"]
        assert tag.kern == ["Neuer Kernbegriff"]


@pytest.mark.asyncio
async def test_fazit_pane_speichert_zusammenfassung_these_und_belege_zusammen(temp_buch):
    from episto_tui import library
    app = _TagsTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ZusammenfassungPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        app.query_one("#feld-zusammenfassung", TextArea).text = "Neues Fazit."
        app.query_one("#feld-these", TextArea).text = "These A\nThese B"
        app.query_one("#feld-beleg", TextArea).text = "Beleg 1"
        pane.focus()
        await pilot.press("ctrl+s")
        await pilot.pause()

        tag = library.read_tags(temp_buch, "0001_erstes-kapitel.md")
        assert tag.zusammenfassung == "Neues Fazit."
        assert tag.these == ["These A", "These B"]
        assert tag.beleg == ["Beleg 1"]
        assert tag.kern == ["testbegriff"]  # Felder der Tags-Pane bleiben unberuehrt
