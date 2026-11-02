import pytest
from episto_tui.app import EpistoApp
from episto_tui.widgets.reader_pane import ReaderPane
from episto_tui.widgets.tags_pane import TagsPane, ZusammenfassungPane
from episto_tui.widgets.straenge_pane import StraengePane
from episto_tui.widgets.querbezuege_pane import QuerbezuegePane
from episto_tui.widgets.tree_sidebar import LibraryTree


@pytest.mark.asyncio
async def test_baum_hat_lesbare_breite_und_tabbedcontent_ueberragt_den_bildschirm_nicht(tmp_path, temp_buch):
    """Ohne eigenes CSS beansprucht TabbedContent implizit fast die gesamte
    Breite des Horizontal-Containers, wodurch LibraryTree auf 1 Spalte
    zusammengedrueckt wird (unlesbar/unbedienbar) - das Symptom, das als
    'TUI zeigt keinen Content' gemeldet wurde: ohne lesbaren Baum laesst
    sich nie ein Kapitel auswaehlen."""
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(120, 40)) as pilot:
        baum = app.query_one(LibraryTree)
        assert baum.size.width >= 20, (
            f"Baum ist nur {baum.size.width} Spalten breit - Buchtitel nicht lesbar"
        )
        assert baum.region.x + baum.size.width <= app.screen.size.width


@pytest.mark.asyncio
async def test_app_zeigt_baum_und_kann_kapitel_oeffnen(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        bibliothek_knoten = list(baum.root.children)[0]
        buch_knoten = list(bibliothek_knoten.children)[0]
        kapitel_knoten = buch_knoten.children[0]
        baum.select_node(kapitel_knoten)
        await pilot.pause()

        from textual.containers import VerticalScroll
        anzeige = app.query_one(ReaderPane).query_one("#anzeige-scroll", VerticalScroll)
        assert anzeige.display is True

        from textual.widgets import TextArea
        these_feld = app.query_one(ZusammenfassungPane).query_one("#feld-these", TextArea)
        assert these_feld.text == "Testthese"


async def _oeffne_erstes_kapitel_per_tastatur(pilot) -> None:
    """Echter Ablauf wie beim Nutzer: Pfeiltasten im Baum bis zum ersten
    Kapitel, dann Enter -- kein select_node()/focus()-Abkuerzung. Cursor
    startet auf "Bibliothek" (bereits aufgeklappt); ein "down" fuehrt zum
    (eingeklappten) Buch-Knoten, Enter klappt ihn auf, das zweite "down"
    landet auf dem ersten Kapitel-Blatt."""
    await pilot.press("down", "enter", "down", "enter")
    await pilot.pause()


@pytest.mark.asyncio
async def test_zifferntasten_wechseln_tabs(tmp_path, temp_buch):
    """I-4: LibraryTree hat beim Start den Fokus und faengt einzelne Zeichen
    fuer ihre Tippfilterung ab. Das Oeffnen eines Kapitels (echter Ablauf per
    Tastatur, kein manuelles .focus()) muss den Fokus in das aktive Pane
    verschieben -- erst dadurch erreichen Ziffern die App-Bindings statt den
    Baumfilter. Vorher blieb der Fokus nach Enter im Baum und "2" landete im
    Filter."""
    from textual.containers import VerticalScroll
    from textual.widgets import TabbedContent
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        await _oeffne_erstes_kapitel_per_tastatur(pilot)
        assert app.query_one(ReaderPane).kapitel.nr == 1
        assert app.focused is app.query_one(ReaderPane).query_one("#anzeige-scroll", VerticalScroll)

        await pilot.press("3")
        await pilot.pause()
        assert app.query_one(TabbedContent).active == "tab-tags"
        assert baum.filter_text == ""
        assert app.focused is app.query_one(TagsPane)

        await pilot.press("1")
        await pilot.pause()
        assert app.query_one(TabbedContent).active == "tab-text"
        assert app.focused is app.query_one(ReaderPane).query_one("#anzeige-scroll", VerticalScroll)


@pytest.mark.asyncio
async def test_kapitel_oeffnen_fokussiert_aktiven_tab_nicht_verstecktes_reader_pane(tmp_path, temp_buch):
    """I-4: steht der Nutzer schon auf dem Tags-Tab, darf das Oeffnen eines
    Kapitels den Fokus nicht in das (versteckte) ReaderPane legen -- sonst
    wuerde "e" unsichtbar den Editiermodus einschalten und ctrl+s die Tags
    nicht speichern."""
    from textual.widgets import TabbedContent
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        app.query_one(TabbedContent).active = "tab-tags"
        await pilot.pause()
        await _oeffne_erstes_kapitel_per_tastatur(pilot)
        assert app.focused is app.query_one(TagsPane)
        await pilot.press("e")
        await pilot.pause()
        assert app.query_one(ReaderPane).bearbeiten is False


@pytest.mark.asyncio
async def test_footer_zeigt_tastenkuerzel(tmp_path, temp_buch):
    from textual.widgets import Footer
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        assert len(app.query(Footer)) == 1


@pytest.mark.asyncio
async def test_tab_reihenfolge_und_unbelegte_taste_6_tut_nichts(tmp_path, temp_buch):
    from textual.widgets import TabbedContent, TabPane
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        assert [pane.id for pane in app.query(TabPane)] == [
            "tab-text", "tab-key", "tab-tags", "tab-straenge", "tab-querbezuege",
        ]
        await _oeffne_erstes_kapitel_per_tastatur(pilot)
        await pilot.press("6")
        await pilot.pause()
        assert app.is_running
        assert app.query_one(TabbedContent).active == "tab-text"


@pytest.mark.asyncio
@pytest.mark.parametrize("taste, tab, pane_typ", [
    ("2", "tab-key", ZusammenfassungPane),
    ("3", "tab-tags", TagsPane),
    ("4", "tab-straenge", StraengePane),
    ("5", "tab-querbezuege", QuerbezuegePane),
])
async def test_ziffern_2_bis_5_oeffnen_fazit_tags_themen_und_querverweise(tmp_path, temp_buch, taste, tab, pane_typ):
    from textual.widgets import TabbedContent
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await _oeffne_erstes_kapitel_per_tastatur(pilot)
        await pilot.press(taste)
        await pilot.pause()
        assert app.query_one(TabbedContent).active == tab
        assert app.focused is app.query_one(pane_typ)


@pytest.mark.asyncio
async def test_q_und_ziffern_werden_normal_in_editor_getippt(tmp_path, temp_buch):
    """Regressionstest: sobald ein Textfeld den Fokus haelt (hier ReaderPane
    im Editiermodus), muessen "q" und Ziffern ganz normale Zeichen sein, die
    im Feld landen -- sie duerfen NICHT die App beenden oder den Tab
    wechseln. (Waere ohnehin auch mit priority=True auf den App-Bindings der
    Fall gewesen, siehe Task-14-Review: Textual entfernt Tasten, die ein
    fokussiertes TextArea/Input selbst konsumieren will, aus jeder
    Bindings-Ebene inkl. priority -- Tree.check_consume_key existiert aber
    nicht, LibraryTree ist nur ueber ihr eigenes on_key betroffen. Dieser
    Test sichert das beobachtbare Verhalten unabhaengig von der Erklaerung
    ab.)"""
    from textual.containers import VerticalScroll
    from textual.widgets import TabbedContent, TextArea
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        bibliothek_knoten = list(baum.root.children)[0]
        buch_knoten = list(bibliothek_knoten.children)[0]
        kapitel_knoten = buch_knoten.children[0]
        baum.select_node(kapitel_knoten)
        await pilot.pause()

        # Kein manuelles .focus() mehr noetig (I-4/I-5): das Oeffnen des
        # Kapitels legt den Fokus in den scrollbaren Anzeigebereich des
        # ReaderPane, "e" legt ihn in den Editor.
        pane = app.query_one(ReaderPane)
        assert app.focused is pane.query_one("#anzeige-scroll", VerticalScroll)
        await pilot.press("e")
        await pilot.pause()

        editor = pane.query_one("#editor", TextArea)
        assert editor.display is True
        assert app.focused is editor
        editor.text = ""
        await pilot.pause()

        for zeichen in "quelle 15":
            await pilot.press("space" if zeichen == " " else zeichen)
        await pilot.pause()

        assert editor.text == "quelle 15"
        assert app.is_running
        assert app.query_one(TabbedContent).active == "tab-text"


@pytest.mark.asyncio
async def test_q_im_filtermodus_wird_getippt_und_beendet_nicht(tmp_path, temp_buch):
    """Im Filtermodus des Baums ("/") gehoert jedes Zeichen dem Filter, auch "q"
    (z.B. fuer "Quelle")."""
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        assert app.focused is baum  # Standardfokus, nichts wurde umgesetzt

        await pilot.press("slash", "q")
        await pilot.pause()

        assert app.is_running
        assert baum.filter_text == "q"


@pytest.mark.asyncio
async def test_ziffern_erreichen_bindings_bei_fokussiertem_baum_ausserhalb_des_filtermodus(tmp_path, temp_buch):
    """Regression: der Baum schluckte Ziffern und "q" fuer die Tippfilterung,
    solange er den Fokus hatte (Start, Sprung per Klick auf die Quellzeile)."""
    from textual.widgets import TabbedContent
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        assert app.focused is baum
        await pilot.press("3")
        await pilot.pause()
        assert baum.filter_text == ""
        assert app.query_one(TabbedContent).active == "tab-tags"


@pytest.mark.asyncio
async def test_fehler_in_einem_pane_legt_app_nicht_lahm(tmp_path, temp_buch, monkeypatch):
    """I-1: wirft ein einzelnes Pane beim Laden (kaputte Daten), darf das
    weder die App beenden noch die uebrigen Panes am Aktualisieren hindern."""
    from textual.widgets import Static
    from episto_tui.widgets.straenge_pane import StraengePane

    def kaputt(self, buch, kapitel):
        raise ValueError("simulierte kaputte Tags")

    monkeypatch.setattr(TagsPane, "lade_kapitel", kaputt)
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        baum.select_node(list(baum.root.children)[0].children[0].children[0])
        await pilot.pause()

        assert app.is_running
        reader = app.query_one(ReaderPane)
        assert reader.kapitel is not None and reader.kapitel.nr == 1
        # Panes NACH dem kaputten TagsPane wurden trotzdem geladen:
        straenge = str(app.query_one(StraengePane).query_one("#inhalt", Static).content)
        assert "Test-Strang" in straenge


@pytest.mark.asyncio
async def test_app_mit_echten_kaputten_dateien(tmp_path, temp_buch):
    """I-1 End-to-End mit echten Dateien statt Monkeypatch: _kapitel_index.json
    als Objekt (verhinderte vorher den App-Start) und tags.json mit null in
    einem Listenfeld (vorher TypeError im TagsPane)."""
    from textual.widgets import TextArea
    (temp_buch.pfad / "quelle" / "_kapitel_index.json").write_text(
        '{"kaputt": true}', encoding="utf-8")
    (temp_buch.pfad / "notizen" / "tags.json").write_text(
        '{"kapitel": [{"datei": "0001_erstes-kapitel.md", "these": [null, "Rest"]}]}',
        encoding="utf-8")
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        bibliothek_knoten = list(baum.root.children)[0]
        buch_knoten = list(bibliothek_knoten.children)[0]
        assert len(buch_knoten.children) == 2  # Glob-Fallback
        baum.select_node(buch_knoten.children[0])
        await pilot.pause()
        assert app.is_running
        assert app.query_one(ZusammenfassungPane).query_one("#feld-these", TextArea).text == "Rest"


@pytest.mark.asyncio
async def test_kompletter_tastatur_ablauf_oeffnen_editieren_speichern(tmp_path, temp_buch):
    """I-4 + I-5 zusammen, nur per Tastatur: Kapitel oeffnen -> "e" ->
    tippen -> ctrl+s -> danach wechselt "3" den Tab (Fokus nicht verloren)."""
    from textual.containers import VerticalScroll
    from textual.widgets import TabbedContent
    from episto_tui import library
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await _oeffne_erstes_kapitel_per_tastatur(pilot)
        await pilot.press("e", "N", "e", "u", "space")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert library.read_chapter_text(temp_buch, "0001_erstes-kapitel.md").startswith(
            "Neu Erster Absatz")
        assert app.focused is app.query_one(ReaderPane).query_one("#anzeige-scroll", VerticalScroll)
        await pilot.press("3")
        await pilot.pause()
        assert app.query_one(TabbedContent).active == "tab-tags"


@pytest.mark.asyncio
async def test_herkunftszeile_nennt_autor_buch_und_kapitel(tmp_path, temp_buch):
    from textual.widgets import Static
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await _oeffne_erstes_kapitel_per_tastatur(pilot)
        text = str(app.query_one("#quelle", Static).content)
        assert "Testautor, Theo" in text
        assert "Testbuch" in text
        assert "1. Erstes Kapitel" in text


@pytest.mark.asyncio
async def test_herkunftszeile_nennt_bei_begriff_den_angeklickten_eintrag(tmp_path, temp_buch):
    """Wahl ueber "Begriffe & Definitionen": der Text oeffnet sich, die Herkunftszeile
    muss sagen, welcher Begriff/welche Definition aus welchem Buch gemeint ist."""
    from textual.widgets import Static
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        baum.focus()
        await pilot.press("slash", "t", "e")
        baum.select_node(list(baum.root.children)[1].children[0])
        await pilot.pause()
        assert "Kernbegriff: „testbegriff“" in str(app.query_one("#begriff", Static).content)
        assert "Aus: Testautor, Theo – Testbuch" in str(app.query_one("#quelle", Static).content)


@pytest.mark.asyncio
@pytest.mark.parametrize("woerter", [3, 120])
async def test_fazit_zusammenfassung_ist_kompakt_und_these_belege_bekommen_den_platz(tmp_path, temp_buch, woerter):
    """Die Zusammenfassung waechst mit ihrem Inhalt, aber hoechstens auf 8 Zeilen
    (inkl. Rahmen); These und Belege teilen sich den Rest und sind groesser."""
    import json
    from textual.widgets import TextArea
    tags_pfad = temp_buch.pfad / "notizen" / "tags.json"
    daten = json.loads(tags_pfad.read_text(encoding="utf-8"))
    daten["kapitel"][0]["zusammenfassung"] = " ".join(["wort"] * woerter)
    tags_pfad.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")

    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 40)) as pilot:
        await _oeffne_erstes_kapitel_per_tastatur(pilot)
        await pilot.press("2")
        for _ in range(3):
            await pilot.pause()
        pane = app.query_one(ZusammenfassungPane)
        hoehe = {feld.id: feld.region.height for feld in pane.query(TextArea)}
        assert hoehe["feld-zusammenfassung"] <= 8
        assert hoehe["feld-these"] > hoehe["feld-zusammenfassung"]
        assert hoehe["feld-beleg"] > hoehe["feld-zusammenfassung"]


@pytest.mark.asyncio
async def test_konfliktkopie_wird_beim_start_zusammengefuehrt_und_gemeldet(tmp_path, temp_buch):
    import json
    notizen = temp_buch.pfad / "notizen"
    kopie = notizen / "kommentare.sync-conflict-20261001-120000-ABCDEFG.json"
    kopie.write_text(json.dumps({"kommentare": [{
        "datei": "0001_erstes-kapitel.md", "absatz_index": 0, "absatz_anfang": "Erster Absatz",
        "text": "Vom Handy", "erstellt": "2026-10-01 09:00", "id": "h1",
    }]}), encoding="utf-8")
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert not kopie.exists()
        assert any("zusammengeführt" in n.message for n in app._notifications)
    from episto_tui import library
    assert library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")[0].text == "Vom Handy"
