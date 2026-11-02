import pytest
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Markdown, TextArea
from episto_tui.widgets.reader_pane import ReaderPane
from episto_tui import library


class _LeseTestApp(App):
    def compose(self) -> ComposeResult:
        yield ReaderPane()


@pytest.mark.asyncio
async def test_lade_kapitel_zeigt_text_im_lesemodus(temp_buch):
    from episto_tui.models import Kapitel
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        assert app.query_one("#anzeige-scroll", VerticalScroll).display is True
        assert app.query_one("#editor", TextArea).display is False


@pytest.mark.asyncio
async def test_langes_kapitel_laesst_sich_scrollen(temp_buch):
    """Markdown selbst waechst mit height:auto auf volle Inhaltshoehe und
    hat kein eigenes Scrolling; ohne einen VerticalScroll-Wrapper schneidet
    der umgebende Vertical-Pane ueberstehenden Text einfach ab, ohne dass
    sich der Rest erreichen liesse (max_scroll_y blieb 0)."""
    from episto_tui.models import Kapitel
    from episto_tui import library

    langer_text = "\n\n".join(f"Absatz Nummer {i} mit etwas Fuelltext." for i in range(1, 61))
    library.write_chapter_text(temp_buch, "0001_erstes-kapitel.md", langer_text)

    app = _LeseTestApp()
    async with app.run_test(size=(80, 20)) as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()

        scroll = app.query_one("#anzeige-scroll", VerticalScroll)
        assert scroll.max_scroll_y > 0, "Kapitel ist laenger als der Viewport, aber nichts zum Scrollen erkannt"

        scroll.scroll_end(animate=False)
        await pilot.pause()
        assert scroll.scroll_y > 0, "scroll_y hat sich nach scroll_end nicht bewegt"


@pytest.mark.asyncio
async def test_langes_kapitel_laesst_sich_mit_der_tastatur_scrollen(temp_buch):
    """Regressionstest fuer den eigentlichen Bug (2026-09-27, zweite Runde):
    der erste Fix (VerticalScroll-Wrapper) hat #anzeige-scroll mechanisch
    scrollbar gemacht, aber lade_kapitel() fokussierte weiterhin das Pane
    SELBST (self.focus()) statt #anzeige-scroll. Textuals Bindings-Kette
    laeuft vom fokussierten Widget aus nach OBEN durch dessen Vorfahren;
    VerticalScroll als KIND des Pane war damit nie in der Kette, seine
    eigenen up/down/pageup/pagedown-Bindings liefen nie. Der vorige Test
    rief scroll_end() direkt als Methode auf und hat genau diese Luecke
    uebersehen - hier wird stattdessen eine echte Taste gedrueckt, ohne
    manuelles .focus() vorher (wie beim echten Oeffnen eines Kapitels)."""
    from episto_tui.models import Kapitel
    from episto_tui import library

    langer_text = "\n\n".join(f"Absatz Nummer {i} mit etwas Fuelltext." for i in range(1, 61))
    library.write_chapter_text(temp_buch, "0001_erstes-kapitel.md", langer_text)

    app = _LeseTestApp()
    async with app.run_test(size=(80, 20)) as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        # Zweite Pause: der Highlight-Worker (faerbt nach dem Markdown-Update
        # alle Bloecke neu ein) muss durch sein, bevor der Tastendruck kommt -
        # sonst war dieser Test seit dem Highlighting-Feature gelegentlich rot.
        await pilot.pause()

        scroll = app.query_one("#anzeige-scroll", VerticalScroll)
        assert app.focused is scroll,"Nach lade_kapitel() muss #anzeige-scroll den Fokus haben, sonst greifen dessen Tasten-Bindings nie"

        await pilot.press("pagedown")
        await pilot.pause()
        assert scroll.scroll_y > 0, "'pagedown' als echter Tastendruck hat nicht gescrollt"


@pytest.mark.asyncio
async def test_escape_verwirft_aenderungen_ohne_speichern(temp_buch):
    from episto_tui.models import Kapitel
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        kapitel = Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md")
        pane.lade_kapitel(temp_buch, kapitel)
        await pilot.pause()

        pane.focus()
        await pilot.press("e")
        await pilot.pause()
        app.query_one("#editor", TextArea).text = "Verworfener Text."

        await pilot.press("escape")
        await pilot.pause()

        from episto_tui import library
        assert library.read_chapter_text(temp_buch, "0002_zweites-kapitel.md") == "Einziger Absatz des zweiten Kapitels."
        assert app.query_one("#anzeige-scroll", VerticalScroll).display is True
        assert app.query_one("#editor", TextArea).display is False


@pytest.mark.asyncio
async def test_editieren_und_speichern_schreibt_datei(temp_buch):
    from episto_tui.models import Kapitel
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        kapitel = Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md")
        pane.lade_kapitel(temp_buch, kapitel)
        await pilot.pause()

        pane.focus()
        await pilot.press("e")
        await pilot.pause()
        editor = app.query_one("#editor", TextArea)
        assert editor.display is True
        editor.text = "Komplett neuer Kapiteltext."

        await pilot.press("ctrl+s")
        await pilot.pause()

        from episto_tui import library
        assert library.read_chapter_text(temp_buch, "0002_zweites-kapitel.md") == "Komplett neuer Kapiteltext."
        assert app.query_one("#anzeige-scroll", VerticalScroll).display is True

        backups = list((temp_buch.pfad / "notizen" / "_backup").glob("0002_zweites-kapitel.*.md"))
        assert len(backups) == 1


@pytest.mark.asyncio
async def test_e_fokussiert_editor_und_getipptes_landet_darin(temp_buch):
    """I-5: nach "e" muss der Fokus im TextArea liegen. Vorher blieb er auf
    ReaderPane, und ein weiteres getipptes "e" schaltete (per Pane-Binding)
    sofort zurueck in den Lesemodus, statt im Editor zu landen."""
    from episto_tui.models import Kapitel
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md"))
        await pilot.pause()
        assert app.focused is app.query_one("#anzeige-scroll", VerticalScroll)

        await pilot.press("e")
        await pilot.pause()
        editor = app.query_one("#editor", TextArea)
        assert app.focused is editor

        await pilot.press("x", "e")
        await pilot.pause()
        assert pane.bearbeiten is True
        assert editor.display is True
        assert editor.text == "xeEinziger Absatz des zweiten Kapitels."


@pytest.mark.asyncio
async def test_escape_gibt_fokus_an_anzeige_scroll_zurueck(temp_buch):
    from episto_tui.models import Kapitel
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md"))
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert pane.bearbeiten is False
        assert app.focused is app.query_one("#anzeige-scroll", VerticalScroll)  # nicht None
        # und die Pane-Bindings funktionieren weiter (bubbeln vom Kind hoch):
        await pilot.press("e")
        await pilot.pause()
        assert pane.bearbeiten is True


@pytest.mark.asyncio
async def test_speichern_gibt_fokus_an_anzeige_scroll_zurueck(temp_buch):
    from episto_tui.models import Kapitel
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md"))
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert pane.bearbeiten is False
        assert app.focused is app.query_one("#anzeige-scroll", VerticalScroll)


@pytest.mark.asyncio
async def test_klick_und_farbtaste_faerbt_den_absatz(temp_buch):
    from episto_tui.models import Kapitel
    from textual.widgets.markdown import MarkdownBlock
    from textual.color import Color
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        await pilot.pause()  # Worker (faerbt nach dem Markdown-Update) braucht eine zweite Pause

        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        assert len(bloecke) == 3  # temp_buch: Kapitel 1 hat drei Absaetze

        await pilot.click(bloecke[1])
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        assert bloecke[1].styles.background == Color.parse("#595900")
        assert bloecke[0].styles.background == Color.parse("transparent")
        assert bloecke[2].styles.background == Color.parse("transparent")


@pytest.mark.asyncio
async def test_gleiche_farbtaste_nochmal_entfernt_das_highlight(temp_buch):
    from episto_tui.models import Kapitel
    from textual.widgets.markdown import MarkdownBlock
    from textual.color import Color
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        await pilot.pause()

        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        await pilot.click(bloecke[0])
        await pilot.press("r")
        await pilot.pause()
        await pilot.pause()
        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        assert bloecke[0].styles.background == Color.parse("#594347")

        await pilot.click(bloecke[0])
        await pilot.press("r")
        await pilot.pause()
        await pilot.pause()
        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        assert bloecke[0].styles.background == Color.parse("transparent")


@pytest.mark.asyncio
async def test_andere_farbtaste_wechselt_die_farbe(temp_buch):
    from episto_tui.models import Kapitel
    from textual.widgets.markdown import MarkdownBlock
    from textual.color import Color
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        await pilot.pause()

        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        await pilot.click(bloecke[0])
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        await pilot.click(bloecke[0])
        await pilot.press("b")
        await pilot.pause()
        await pilot.pause()

        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        assert bloecke[0].styles.background == Color.parse("blue")


@pytest.mark.asyncio
async def test_farbtaste_ohne_vorherigen_klick_tut_nichts(temp_buch):
    from episto_tui.models import Kapitel
    from textual.widgets.markdown import MarkdownBlock
    from textual.color import Color
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        await pilot.pause()

        pane.focus()
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        gelesen = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
        assert gelesen == []
        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        for block in bloecke:
            assert block.styles.background == Color.parse("transparent")


@pytest.mark.asyncio
async def test_highlight_bleibt_nach_erneutem_laden_des_kapitels_erhalten(temp_buch):
    from episto_tui.models import Kapitel
    from textual.widgets.markdown import MarkdownBlock
    from textual.color import Color
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        kapitel = Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md")
        pane.lade_kapitel(temp_buch, kapitel)
        await pilot.pause()
        await pilot.pause()

        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        await pilot.click(bloecke[2])
        await pilot.press("b")
        await pilot.pause()
        await pilot.pause()

        # Anderes Kapitel oeffnen und zurueck - simuliert einen Tab-/Kapitelwechsel.
        pane.lade_kapitel(temp_buch, Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md"))
        await pilot.pause()
        await pilot.pause()
        pane.lade_kapitel(temp_buch, kapitel)
        await pilot.pause()
        await pilot.pause()

        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        assert bloecke[2].styles.background == Color.parse("blue")


# --- Zeilenbasierte Absatz-Zuordnung (Final-Review Critical #1) -------------
#
# Echte Konvertierungen enthalten Ueberschriften, Listen und Zitate OHNE
# Leerzeile dazwischen: split_paragraphs() sieht darin EINEN Absatz, Textuals
# Markdown-Widget aber mehrere (teils verschachtelte) MarkdownBlocks. Die
# fruehere Zuordnung ueber die Position in der rekursiven Block-Liste lief
# dadurch am Kapitelende ueber (Farbtaste tat nichts) bzw. traf den falschen
# Absatz.
_GEMISCHTES_KAPITEL = (
    "# Kapitelueberschrift\n"
    "Einleitender Satz direkt unter der Ueberschrift.\n\n"
    "Eine Aufzaehlung:\n"
    "- Punkt eins\n"
    "- Punkt zwei\n"
    "- Punkt drei\n"
    "> Ein Zitat direkt unter der Liste\n"
    "> ueber zwei Zeilen.\n\n"
    "Letzter Absatz des Kapitels."
)


def _oberste_bloecke(app):
    from textual.widgets.markdown import MarkdownBlock
    return list(app.query_one("#anzeige", Markdown).query_children(MarkdownBlock))


@pytest.mark.asyncio
async def test_farbtaste_auf_letztem_absatz_nach_liste_und_zitat_ohne_leerzeilen(temp_buch):
    from episto_tui.models import Kapitel
    from textual.widgets.markdown import MarkdownBlock
    from textual.color import Color
    library.write_chapter_text(temp_buch, "0001_erstes-kapitel.md", _GEMISCHTES_KAPITEL)
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        await pilot.pause()

        # Voraussetzung des Szenarios: deutlich mehr (verschachtelte) Bloecke
        # als Absaetze - genau hier ging die alte Positions-Zuordnung schief.
        alle = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        assert len(alle) > 3

        letzter = _oberste_bloecke(app)[-1]
        await pilot.click(letzter)
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        gelesen = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
        assert [(h.absatz_index, h.farbe) for h in gelesen] == [(2, "gelb")]
        assert gelesen[0].absatz_anfang.startswith("Letzter Absatz")
        bloecke = _oberste_bloecke(app)
        assert bloecke[-1].styles.background == Color.parse("#595900")
        for block in bloecke[:-1]:
            assert block.styles.background == Color.parse("transparent")


@pytest.mark.asyncio
async def test_klick_auf_listenpunkt_faerbt_den_ganzen_umschliessenden_absatz(temp_buch):
    from episto_tui.models import Kapitel
    from textual.widgets.markdown import MarkdownBlock
    from textual.color import Color
    library.write_chapter_text(temp_buch, "0001_erstes-kapitel.md", _GEMISCHTES_KAPITEL)
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        await pilot.pause()

        # Absatz 1 = "Eine Aufzaehlung:" + Liste + Zitat (oberste Bloecke 2-4).
        liste = _oberste_bloecke(app)[3]
        punkt_zwei = list(liste.query(MarkdownBlock))[1]
        await pilot.click(punkt_zwei)
        await pilot.press("b")
        await pilot.pause()
        await pilot.pause()

        gelesen = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
        assert [(h.absatz_index, h.farbe) for h in gelesen] == [(1, "blau")]
        bloecke = _oberste_bloecke(app)
        assert [b.styles.background == Color.parse("blue") for b in bloecke] == [
            False, False, True, True, True, False,
        ]
        # Verschachtelte Bloecke bekommen keine eigene Farbe (wirken ueber
        # den gefaerbten obersten Block trotzdem einfarbig).
        for innerer in bloecke[3].query(MarkdownBlock):
            assert innerer.styles.background == Color.parse("transparent")


@pytest.mark.asyncio
async def test_lockere_liste_mit_leerzeilen_ordnet_jeden_punkt_seinem_absatz_zu(temp_buch):
    """Umgekehrter Fall: Leerzeilen zwischen Listenpunkten machen jeden Punkt
    zu einem eigenen Absatz (split_paragraphs), Markdown aber zu EINEM
    Listen-Block. Der Klick auf Punkt drei muss Absatz 3 treffen, nicht den
    Absatz, in dem die Liste beginnt."""
    from episto_tui.models import Kapitel
    from textual.widgets.markdown import MarkdownBlock
    from textual.color import Color
    library.write_chapter_text(
        temp_buch, "0001_erstes-kapitel.md",
        "Einleitung.\n\n- Punkt eins\n\n- Punkt zwei\n\n- Punkt drei\n\nSchluss.",
    )
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        await pilot.pause()

        liste = _oberste_bloecke(app)[1]
        punkt_drei = list(liste.query(MarkdownBlock))[2]
        await pilot.click(punkt_drei)
        await pilot.press("r")
        await pilot.pause()
        await pilot.pause()

        gelesen = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
        assert [(h.absatz_index, h.farbe) for h in gelesen] == [(3, "rosa")]
        liste = _oberste_bloecke(app)[1]
        punkte = list(liste.query(MarkdownBlock))
        # Der Listen-Block selbst ueberspannt drei Absaetze und bleibt
        # transparent; gefaerbt wird nur der Listenpunkt-Container von Punkt drei.
        assert liste.styles.background == Color.parse("transparent")
        assert punkte[2].parent.parent.styles.background == Color.parse("#594347")
        assert punkte[0].parent.parent.styles.background == Color.parse("transparent")
        assert punkte[1].parent.parent.styles.background == Color.parse("transparent")


# --- Robuste Verankerung ueber locate_paragraph (Final-Review Important #2) --

async def _bearbeite_und_speichere(pilot, app, neuer_text: str) -> None:
    await pilot.press("e")
    await pilot.pause()
    app.query_one("#editor", TextArea).text = neuer_text
    await pilot.press("ctrl+s")
    await pilot.pause()
    await pilot.pause()


_TEXT_MIT_NEUEM_ABSATZ_DAVOR = (
    "Erster Absatz des ersten Kapitels.\n\n"
    "Neu eingefuegter Absatz.\n\n"
    "Zweiter Absatz mit mehr Inhalt zum Testen.\n\n"
    "Dritter Absatz, der letzte hier."
)


@pytest.mark.asyncio
async def test_highlight_bleibt_nach_einfuegen_eines_absatzes_davor_am_richtigen_absatz(temp_buch):
    from episto_tui.models import Kapitel
    from textual.color import Color
    app = _LeseTestApp()
    async with app.run_test(size=(80, 30)) as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        await pilot.pause()

        await pilot.click(_oberste_bloecke(app)[1])  # "Zweiter Absatz ..."
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        await _bearbeite_und_speichere(pilot, app, _TEXT_MIT_NEUEM_ABSATZ_DAVOR)

        bloecke = _oberste_bloecke(app)
        assert len(bloecke) == 4
        assert bloecke[1].styles.background == Color.parse("transparent")  # der neue Absatz
        assert bloecke[2].styles.background == Color.parse("#595900")      # "Zweiter Absatz ..."


@pytest.mark.asyncio
async def test_neues_highlight_nach_bearbeitung_ueberschreibt_verschobenes_nicht(temp_buch):
    """write/remove_highlight schluesseln nach dem gespeicherten Index. Nach
    dem Einfuegen eines Absatzes zeigt der gespeicherte Index 1 des alten
    Highlights auf den NEUEN Absatz - ein neues Highlight dort darf das
    verschobene alte nicht ueberschreiben, und Umschalten muss das
    verschobene Highlight an seinem neuen Platz treffen."""
    from episto_tui.models import Kapitel
    from textual.color import Color
    app = _LeseTestApp()
    async with app.run_test(size=(80, 30)) as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        await pilot.pause()

        await pilot.click(_oberste_bloecke(app)[1])
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        await _bearbeite_und_speichere(pilot, app, _TEXT_MIT_NEUEM_ABSATZ_DAVOR)

        await pilot.click(_oberste_bloecke(app)[1])  # der neue Absatz
        await pilot.press("b")
        await pilot.pause()
        await pilot.pause()

        bloecke = _oberste_bloecke(app)
        assert bloecke[1].styles.background == Color.parse("blue")
        assert bloecke[2].styles.background == Color.parse("#595900")
        gelesen = sorted(
            (h.absatz_index, h.farbe, h.absatz_anfang[:12])
            for h in library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
        )
        assert gelesen == [(1, "blau", "Neu eingefue"), (2, "gelb", "Zweiter Absa")]

        # Gleiche Farbe auf dem verschobenen Absatz entfernt genau dieses Highlight.
        await pilot.click(_oberste_bloecke(app)[2])
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        bloecke = _oberste_bloecke(app)
        assert bloecke[1].styles.background == Color.parse("blue")
        assert bloecke[2].styles.background == Color.parse("transparent")
        verbleibend = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
        assert [(h.absatz_index, h.farbe) for h in verbleibend] == [(1, "blau")]


# --- Kommentare als Bloecke im Lesemodus ------------------------------------

def _klartext(block) -> str:
    from textual.widgets.markdown import MarkdownBlock
    teile = [str(b.content) for b in (block, *block.query(MarkdownBlock))]
    return " ".join(t for t in teile if t)


def _kommentar(anfang, text="Notiz", absatz_index=0):
    from episto_tui.models import Kommentar
    return Kommentar(
        datei="0001_erstes-kapitel.md", absatz_index=absatz_index,
        absatz_anfang=anfang, text=text, erstellt="2026-09-28 10:00",
    )


_ANFANG_1 = "Erster Absatz des ersten Kapitels."
_ANFANG_2 = "Zweiter Absatz mit mehr Inhalt zum Testen."
_ANFANG_3 = "Dritter Absatz, der letzte hier."


async def _lade_kapitel_1(app, pilot, temp_buch):
    from episto_tui.models import Kapitel
    pane = app.query_one(ReaderPane)
    pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
    await pilot.pause()
    await pilot.pause()
    return pane


@pytest.mark.asyncio
async def test_kommentar_wird_als_block_unter_dem_absatz_angezeigt(temp_buch):
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1, "Vgl. Popper [LdF] S. 12 und [/]"))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        texte = [_klartext(b) for b in _oberste_bloecke(app)]
        assert len(texte) == 4  # drei Absaetze + ein Kommentarblock
        assert texte[0] == _ANFANG_1
        assert texte[1] == "\U0001f4ac Vgl. Popper [LdF] S. 12 und [/] — 2026-09-28 10:00"
        assert texte[2] == _ANFANG_2


@pytest.mark.asyncio
async def test_farbtaste_faerbt_den_absatz_nicht_den_kommentarblock(temp_buch):
    from textual.color import Color
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[0])
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()
        bloecke = _oberste_bloecke(app)
        assert bloecke[0].styles.background == Color.parse("#595900")
        assert bloecke[1].styles.background == Color.parse("transparent")
        assert bloecke[2].styles.background == Color.parse("transparent")


@pytest.mark.asyncio
async def test_klick_auf_letzten_absatz_trifft_trotz_kommentarbloecken_den_richtigen_index(temp_buch):
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1, "Eins", 0))
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1, "Zwei", 0))
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_2, "Drei", 1))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        bloecke = _oberste_bloecke(app)
        assert len(bloecke) == 6
        await pilot.click(bloecke[-1])
        await pilot.press("b")
        await pilot.pause()
        await pilot.pause()
        gelesen = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
        assert [(h.absatz_index, h.farbe) for h in gelesen] == [(2, "blau")]


@pytest.mark.asyncio
async def test_klick_auf_kommentarblock_merkt_kommentar_und_absatz(temp_buch):
    k = _kommentar(_ANFANG_2, "Notiz", 1)
    library.add_kommentar(temp_buch, k)
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[2])  # Kommentarblock unter Absatz 2
        assert pane._aktiver_kommentar == k
        assert pane._aktiver_absatz_index == 1
        await pilot.click(_oberste_bloecke(app)[0])  # ein Absatz loest den Kommentar wieder
        assert pane._aktiver_kommentar is None
        assert pane._aktiver_absatz_index == 0


@pytest.mark.asyncio
async def test_farbtaste_nach_klick_auf_kommentarblock_faerbt_dessen_absatz(temp_buch):
    from textual.color import Color
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[1])
        await pilot.press("r")
        await pilot.pause()
        await pilot.pause()
        bloecke = _oberste_bloecke(app)
        assert bloecke[0].styles.background == Color.parse("#594347")
        assert bloecke[1].styles.background == Color.parse("transparent")


@pytest.mark.asyncio
async def test_verwaister_kommentar_steht_am_kapitelende_und_ist_anklickbar(temp_buch):
    k = _kommentar("Text, der nicht mehr existiert", "Waise", 9)
    library.add_kommentar(temp_buch, k)
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = await _lade_kapitel_1(app, pilot, temp_buch)
        bloecke = _oberste_bloecke(app)
        texte = [_klartext(b) for b in bloecke]
        assert len(texte) == 5  # drei Absaetze, Ueberschrift, verwaister Kommentar
        assert texte[3] == "Kommentare ohne Absatz"
        assert texte[4].startswith("\U0001f4ac Waise")

        await pilot.click(bloecke[0])
        await pilot.click(bloecke[3])  # Ueberschrift: loest alles
        assert pane._aktiver_kommentar is None and pane._aktiver_absatz_index is None
        await pilot.click(bloecke[4])
        assert pane._aktiver_kommentar == k and pane._aktiver_absatz_index is None


# --- Kommentare anlegen / aendern / loeschen --------------------------------

@pytest.mark.asyncio
async def test_klick_c_text_enter_legt_kommentar_an_und_zeigt_ihn(temp_buch):
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[1])
        await pilot.press("c")
        await pilot.pause()
        eingabe = app.query_one("#kommentar-eingabe")
        assert eingabe.display is True
        assert app.focused is eingabe

        # c, d, q und Ziffern sind hier ganz normale Zeichen im Eingabefeld.
        await pilot.press("N", "o", "t", "i", "z", "space", "c", "d", "space", "q", "5")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        gelesen = library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")
        assert [(k.absatz_index, k.text) for k in gelesen] == [(1, "Notiz cd q5")]
        assert gelesen[0].absatz_anfang == _ANFANG_2
        assert eingabe.display is False
        assert app.focused is app.query_one("#anzeige-scroll", VerticalScroll)
        texte = [_klartext(b) for b in _oberste_bloecke(app)]
        assert texte[2].startswith("\U0001f4ac Notiz cd q5")


@pytest.mark.asyncio
async def test_escape_bricht_das_kommentieren_ab(temp_buch):
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[0])
        await pilot.press("c")
        await pilot.press("V", "e", "r", "w")
        await pilot.press("escape")
        await pilot.pause()
        assert library.read_kommentare(temp_buch, "0001_erstes-kapitel.md") == []
        assert app.query_one("#kommentar-eingabe").display is False
        assert app.query_one("#kommentar-eingabe").value == ""
        assert pane.bearbeiten is False
        assert app.focused is app.query_one("#anzeige-scroll", VerticalScroll)


@pytest.mark.asyncio
async def test_leerer_text_legt_keinen_kommentar_an(temp_buch):
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[0])
        await pilot.press("c")
        await pilot.press("space", "space", "enter")
        await pilot.pause()
        assert library.read_kommentare(temp_buch, "0001_erstes-kapitel.md") == []
        assert app.query_one("#kommentar-eingabe").display is False


@pytest.mark.asyncio
async def test_kommentar_mit_markup_zeichen_wird_woertlich_angezeigt(temp_buch):
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[0])
        await pilot.press("c")
        app.query_one("#kommentar-eingabe").value = "Vgl. [LdF] und [/] *stern*"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        erstellt = library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")[0].erstellt
        texte = [_klartext(b) for b in _oberste_bloecke(app)]
        assert texte[1] == "\U0001f4ac Vgl. [LdF] und [/] *stern* — " + erstellt


@pytest.mark.asyncio
async def test_klick_auf_kommentarblock_c_aendert_den_text(temp_buch):
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1, "Alt"))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[1])
        await pilot.press("c")
        await pilot.pause()
        eingabe = app.query_one("#kommentar-eingabe")
        assert eingabe.display is True
        assert eingabe.value == "Alt"
        eingabe.value = "Neu"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        gelesen = library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")
        assert [(k.text, k.erstellt) for k in gelesen] == [("Neu", "2026-09-28 10:00")]
        assert _klartext(_oberste_bloecke(app)[1]).startswith("\U0001f4ac Neu")


@pytest.mark.asyncio
async def test_klick_auf_kommentarblock_d_loescht_den_kommentar(temp_buch):
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1, "Weg damit"))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        assert len(_oberste_bloecke(app)) == 4
        await pilot.click(_oberste_bloecke(app)[1])
        await pilot.press("d")
        await pilot.pause()
        await pilot.pause()
        assert library.read_kommentare(temp_buch, "0001_erstes-kapitel.md") == []
        assert len(_oberste_bloecke(app)) == 3


@pytest.mark.asyncio
async def test_verwaister_kommentar_laesst_sich_loeschen(temp_buch):
    library.add_kommentar(temp_buch, _kommentar("Text, der nicht mehr existiert", "Waise", 9))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[4])
        await pilot.press("d")
        await pilot.pause()
        await pilot.pause()
        assert library.read_kommentare(temp_buch, "0001_erstes-kapitel.md") == []
        assert len(_oberste_bloecke(app)) == 3


@pytest.mark.asyncio
async def test_c_und_d_ohne_klick_tun_nichts(temp_buch):
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1, "Bleibt"))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.press("c")
        await pilot.press("d")
        await pilot.pause()
        assert app.query_one("#kommentar-eingabe").display is False
        assert len(library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")) == 1


@pytest.mark.asyncio
async def test_d_auf_einem_absatz_loescht_nichts(temp_buch):
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1, "Bleibt"))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[0])
        await pilot.press("d")
        await pilot.pause()
        assert len(library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")) == 1


@pytest.mark.asyncio
async def test_c_im_editiermodus_oeffnet_kein_kommentarfeld(temp_buch):
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[0])
        await pilot.press("e")
        await pilot.pause()
        assert pane.bearbeiten is True
        await pilot.press("c", "d")
        await pilot.pause()
        assert app.query_one("#kommentar-eingabe").display is False
        assert library.read_kommentare(temp_buch, "0001_erstes-kapitel.md") == []


@pytest.mark.asyncio
async def test_kapitelwechsel_schliesst_offenes_kommentarfeld(temp_buch):
    from episto_tui.models import Kapitel
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[0])
        await pilot.press("c")
        await pilot.pause()
        pane.lade_kapitel(temp_buch, Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md"))
        await pilot.pause()
        assert app.query_one("#kommentar-eingabe").display is False


# --- Offenes Kommentarfeld darf nicht in den Editiermodus ueberleben --------

@pytest.mark.asyncio
async def test_klick_in_den_lesebereich_schliesst_offenes_kommentarfeld(temp_buch):
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[1])
        await pilot.press("c")
        await pilot.pause()
        eingabe = app.query_one("#kommentar-eingabe")
        assert eingabe.display is True

        await pilot.click(_oberste_bloecke(app)[2])
        await pilot.pause()
        assert eingabe.display is False
        assert pane._kommentar_ziel is None
        assert pane._aktiver_absatz_index == 2


@pytest.mark.asyncio
async def test_klick_ins_kommentarfeld_laesst_es_offen(temp_buch):
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[1])
        await pilot.press("c")
        await pilot.pause()
        eingabe = app.query_one("#kommentar-eingabe")
        await pilot.click(eingabe)
        await pilot.pause()
        assert eingabe.display is True
        assert pane._kommentar_ziel == ("neu", 1)


@pytest.mark.asyncio
async def test_offenes_kommentarfeld_ueberlebt_den_editiermodus_nicht(temp_buch):
    """Review-Ablauf: Feld offen -> anderswo klicken -> e -> Text aendern ->
    Enter im Feld. Frueher speicherte das den Kommentar und schaltete danach
    in die Lese-Ansicht (bearbeiten=True, Editor versteckt): die ungespeicherten
    Kapitel-Aenderungen waren still verloren."""
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[1])
        await pilot.press("c")
        await pilot.pause()
        await pilot.click(_oberste_bloecke(app)[2])
        await pilot.press("e")
        await pilot.pause()
        editor = app.query_one("#editor", TextArea)
        eingabe = app.query_one("#kommentar-eingabe")
        assert pane.bearbeiten is True
        assert eingabe.display is False
        assert pane._kommentar_ziel is None
        editor.text = "Ungespeicherte Aenderung."

        # Selbst ein Submit des (nicht mehr sichtbaren) Felds darf nichts tun.
        eingabe.post_message(eingabe.Submitted(eingabe, "Zu spaet"))
        await pilot.pause()
        assert pane.bearbeiten is True
        assert editor.display is True
        assert app.query_one("#anzeige-scroll", VerticalScroll).display is False
        assert editor.text == "Ungespeicherte Aenderung."
        assert library.read_kommentare(temp_buch, "0001_erstes-kapitel.md") == []


@pytest.mark.asyncio
async def test_eingabe_submit_bei_bearbeiten_speichert_nichts_und_laesst_editor_stehen(temp_buch):
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.press("e")
        await pilot.pause()
        editor = app.query_one("#editor", TextArea)
        editor.text = "Noch nicht gespeichert."
        pane._kommentar_ziel = ("neu", 0)
        eingabe = app.query_one("#kommentar-eingabe")
        eingabe.post_message(eingabe.Submitted(eingabe, "Text"))
        await pilot.pause()
        await pilot.pause()
        assert library.read_kommentare(temp_buch, "0001_erstes-kapitel.md") == []
        assert pane.bearbeiten is True
        assert editor.display is True
        assert editor.text == "Noch nicht gespeichert."


@pytest.mark.asyncio
async def test_escape_im_editiermodus_verwirft_die_aenderung_auch_bei_offenem_feld(temp_buch):
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[1])
        await pilot.press("c")
        await pilot.pause()
        pane.focus()  # Fokus weg vom Feld (Tastatur-Weg statt Klick)
        await pilot.press("e")
        await pilot.pause()
        assert pane.bearbeiten is True
        assert app.query_one("#kommentar-eingabe").display is False
        await pilot.press("escape")
        await pilot.pause()
        assert pane.bearbeiten is False
        assert app.query_one("#editor", TextArea).display is False


# --- Aktiver Absatz/Kommentar nach ctrl+s -----------------------------------

@pytest.mark.asyncio
async def test_nach_speichern_gibt_es_keinen_aktiven_absatz_mehr(temp_buch):
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[2])
        assert pane._aktiver_absatz_index == 2

        await _bearbeite_und_speichere(pilot, app, _TEXT_MIT_NEUEM_ABSATZ_DAVOR)
        assert pane._aktiver_absatz_index is None
        assert pane._aktiver_kommentar is None

        await pilot.press("c")
        await pilot.pause()
        assert app.query_one("#kommentar-eingabe").display is False


# --- Klick auf Kommentar in Kapitel mit Liste/Zitat -------------------------

@pytest.mark.asyncio
async def test_klick_zuordnung_mit_kommentar_in_kapitel_mit_liste_und_zitat(temp_buch):
    """Absatz 1 = "Eine Aufzaehlung:" + Liste + Zitat (mehrere Bloecke), direkt
    dahinter der Kommentarblock. Die Zuordnung ist zeilenbasiert und war schon
    einmal Ort eines schweren Fehlers."""
    k = _kommentar("Eine Aufzaehlung:", "Notiz zur Liste", 1)
    library.write_chapter_text(temp_buch, "0001_erstes-kapitel.md", _GEMISCHTES_KAPITEL)
    library.add_kommentar(temp_buch, k)
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        from textual.widgets.markdown import MarkdownBlock
        pane = await _lade_kapitel_1(app, pilot, temp_buch)
        bloecke = _oberste_bloecke(app)
        kommentarblock = next(b for b in bloecke if _klartext(b).startswith("\U0001f4ac Notiz zur Liste"))
        await pilot.click(kommentarblock)
        assert pane._aktiver_kommentar == k
        assert pane._aktiver_absatz_index == 1

        liste = next(b for b in _oberste_bloecke(app) if list(b.query(MarkdownBlock)) and "Punkt eins" in _klartext(b))
        await pilot.click(list(liste.query(MarkdownBlock))[1])
        assert pane._aktiver_kommentar is None
        assert pane._aktiver_absatz_index == 1

        await pilot.click(_oberste_bloecke(app)[-1])
        assert pane._aktiver_kommentar is None
        assert pane._aktiver_absatz_index == 2
