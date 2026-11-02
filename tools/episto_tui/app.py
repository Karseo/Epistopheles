from __future__ import annotations
from pathlib import Path
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, TabbedContent, TabPane
from textual.binding import Binding
from episto_tui import korrektur, library
from episto_tui.widgets.aktionsleiste import Aktionsleiste
from episto_tui.widgets.herkunft import Herkunft
from episto_tui.widgets.tree_sidebar import LibraryTree, ChapterSelected
from episto_tui.widgets.reader_pane import ReaderPane
from episto_tui.widgets.korrektur_screen import KorrekturScreen
from episto_tui.widgets.notizen_screen import NotizenScreen
from episto_tui.widgets.speedreader_screen import SpeedreaderScreen
from episto_tui.widgets.such_screen import SuchScreen
from episto_tui.widgets.sprung import SpringeZu
from episto_tui.widgets.tags_pane import TagsPane, ZusammenfassungPane
from episto_tui.widgets.straenge_pane import StraengePane
from episto_tui.widgets.querbezuege_pane import QuerbezuegePane

# Unter dieser Terminalbreite (Spalten) gilt das schmale Handy-Layout. 80 ist
# zugleich die Standardgroesse der Tests: sie laufen damit im breiten Modus.
SCHMAL_BREITE = 80

_FOKUS_JE_TAB = {
    "tab-key": ZusammenfassungPane,
    "tab-tags": TagsPane,
    "tab-straenge": StraengePane,
    "tab-querbezuege": QuerbezuegePane,
}

_FELDER_TABS = ("tab-key", "tab-tags")

# Knopf der Aktionsleiste -> Aktion des aktiven Panes (action_<name>).
_KNOPF_AKTION = {
    "bearbeiten": "toggle_edit",
    "gelb": "highlight_gelb",
    "rosa": "highlight_rosa",
    "blau": "highlight_blau",
    "korrektur": "highlight_korrektur",
    "kommentar": "kommentieren",
    "loeschen": "kommentar_loeschen",
    "speichern": "speichern",
    "verwerfen": "verwerfen",
}


class EpistoApp(App):
    # Ohne dieses CSS beansprucht TabbedContent implizit fast die gesamte
    # Breite des Horizontal-Containers (sein DEFAULT_CSS setzt keine width),
    # wodurch LibraryTree auf 1 Spalte zusammengedrueckt wird - unlesbar und
    # unbedienbar (Bug gefunden nach dem Merge: "TUI zeigt keinen Content",
    # weil sich ohne lesbaren Baum nie ein Kapitel auswaehlen liess).
    #
    # Schmal (Klasse "schmal" auf dem Screen, siehe _passe_layout_an): der
    # Baum ist ausgeblendet und die Aktionsleiste sichtbar; "baum-offen" laesst
    # den Baum voruebergehend die Tabs ersetzen (Schublade fuers Handy).
    CSS = """
    LibraryTree { width: 60; max-width: 40%; margin-right: 1; border-top: solid $primary; }
    #rechts { width: 1fr; }
    TabbedContent { width: 100%; height: 1fr; }
    Aktionsleiste { display: none; }
    Screen.schmal LibraryTree { display: none; }
    Screen.schmal Aktionsleiste { display: block; }
    Screen.schmal.baum-offen LibraryTree { display: block; width: 1fr; max-width: 100%; margin-right: 0; }
    Screen.schmal.baum-offen TabbedContent { display: none; }
    Screen.schmal.baum-offen #rechts { display: none; }
    """

    # Bewusst KEIN priority=True. Die Tippfilterung des Baums ist ein eigener
    # Modus ("/" startet ihn, siehe tree_sidebar.py): nur darin schluckt
    # LibraryTree druckbare Zeichen. Ausserhalb davon erreichen Ziffern, "0" und
    # "q" die App-Bindings auch bei fokussiertem Baum. on_chapter_selected
    # verschiebt den Fokus nach dem Oeffnen eines Kapitels ausdruecklich in das
    # Pane des aktiven Tabs (der Baum gibt ihn beim Enter NICHT von selbst ab),
    # und auch die Tab-Aktionen legen den Fokus in das neue Pane, weil Textual
    # den Fokus sonst auf None faellt, sobald das bisher fokussierte Pane mit
    # seinem Tab ausgeblendet wird. Im schmalen Modus ist der Knopf "Baum" der
    # Weg zurueck, wenn eine Soft-Tastatur "0" nicht liefert.
    BINDINGS = [
        Binding("q", "quit", "Beenden"),
        Binding("0", "baum_umschalten", "Baum"),
        Binding("s", "suche", "Suche"),
        Binding("ctrl+f", "suche", "Suche", show=False),
        Binding("m", "notizen", "Notizen"),
        Binding("x", "korrektur", "Korrektur"),
        Binding("v", "speedreader", "Speedreader"),
        Binding("n", "naechstes_kapitel", "Weiter"),
        Binding("p", "voriges_kapitel", "Zurück"),
        Binding("1", "tab_text", "Text"),
        Binding("2", "tab_key", "Fazit"),
        Binding("3", "tab_tags", "Tags"),
        Binding("4", "tab_straenge", "Themen"),
        Binding("5", "tab_querbezuege", "Querverweise"),
    ]

    def __init__(self, root: Path | None = None) -> None:
        super().__init__()
        self.root_pfad = root if root is not None else library.DEFAULT_ROOT
        self._kapitel_geladen = False
        # Zuletzt geoeffnetes Kapitel (Ziel von n/p und der Leseposition) und
        # die zuletzt gespeicherte Position (nur bei Aenderung neu schreiben).
        self._aktuell: tuple | None = None
        self._gespeicherte_position: tuple | None = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield LibraryTree(self.root_pfad)
            with Vertical(id="rechts"):
                yield Herkunft()
                with TabbedContent(initial="tab-text"):
                    with TabPane("Text", id="tab-text"):
                        yield ReaderPane()
                    with TabPane("Fazit", id="tab-key"):
                        yield ZusammenfassungPane()
                    with TabPane("Tags", id="tab-tags"):
                        yield TagsPane()
                    with TabPane("Themen", id="tab-straenge"):
                        yield StraengePane()
                    with TabPane("Querverweise", id="tab-querbezuege"):
                        yield QuerbezuegePane()
        yield Aktionsleiste()
        yield Footer()

    def on_mount(self) -> None:
        self._passe_layout_an(self.size.width)
        self._fuehre_konflikte_zusammen(None)
        # Leseposition: beim Start dort weiterlesen, wo man aufgehoert hat, und
        # sie waehrend des Lesens regelmaessig sichern (Termux wird gern ohne
        # sauberes Beenden geschlossen).
        self.call_after_refresh(self._setze_fort)
        self.set_interval(15, self._speichere_position)
        self.call_after_refresh(self._aktualisiere_aktionsleiste)

    def on_resize(self, event: events.Resize) -> None:
        self._passe_layout_an(event.size.width)

    def _passe_layout_an(self, breite: int) -> None:
        schmal = breite < SCHMAL_BREITE
        self.screen.set_class(schmal, "schmal")
        if not schmal:
            self.screen.set_class(False, "baum-offen")
        elif not self._kapitel_geladen:
            # Ohne gewaehltes Kapitel gibt es nichts zu lesen: der Baum ist
            # der Einstieg. Ein unsichtbarer, aber fokussierter Baum wuerde
            # ausserdem Tastendruecke in seinen Filter schlucken.
            self.screen.set_class(True, "baum-offen")
        self._aktualisiere_aktionsleiste()

    def _fuehre_konflikte_zusammen(self, buch) -> None:
        """Syncthing-Konfliktkopien der Notizen (kommentare/highlights/tags)
        mit den Hauptdateien zusammenfuehren, siehe library.merge_konflikte.
        buch=None prueft die ganze Bibliothek (Start). Ein Fehler hier darf
        das Laden nie verhindern."""
        try:
            if buch is None:
                anzahl = library.merge_alle_konflikte(self.root_pfad)
            else:
                anzahl = library.merge_konflikte(buch)
        except Exception as exc:
            self.notify(f"Konfliktkopien nicht zusammengeführt: {exc}", severity="warning")
            return
        if anzahl:
            self.notify(
                f"{anzahl} Sync-Konfliktkopie(n) zusammengeführt "
                "(Originale in notizen/_backup).",
            )

    def _speichere_position(self) -> None:
        if self._aktuell is None:
            return
        buch, kapitel = self._aktuell
        try:
            absatz = self.query_one(ReaderPane).aktueller_absatz()
        except Exception:
            return
        stand = (buch.pfad, kapitel.datei, absatz)
        if stand != self._gespeicherte_position:
            library.speichere_leseposition(buch, kapitel, absatz)
            self._gespeicherte_position = stand

    def _setze_fort(self) -> None:
        position = library.lade_leseposition(self.root_pfad)
        if position is None:
            return
        buch, kapitel, absatz = position
        self._oeffne(buch, kapitel, absatz)
        self.notify(f"Weiter bei: {buch.titel} \u00b7 {kapitel.nr}. {kapitel.titel}")

    async def action_quit(self) -> None:
        self._speichere_position()
        await super().action_quit()

    def _oeffne(self, buch, kapitel, absatz_index: int | None = None, zum_text: bool = True) -> None:
        """Kapitel oeffnen (wie ein Klick im Baum), den Baum-Cursor mitfuehren
        und, bei zum_text, auf den Text-Tab wechseln."""
        self.query_one(LibraryTree).zeige_kapitel(buch, kapitel)
        self.on_chapter_selected(ChapterSelected(buch, kapitel, absatz_index=absatz_index))
        if zum_text:
            self.query_one(TabbedContent).active = "tab-text"
        self._fokussiere_aktiven_tab()

    def on_springe_zu(self, event: SpringeZu) -> None:
        event.stop()
        self._oeffne(event.buch, event.kapitel, event.absatz_index)

    def on_chapter_selected(self, event: ChapterSelected) -> None:
        # Position des Kapitels sichern, das gleich verlassen wird.
        self._speichere_position()
        self._aktuell = (event.buch, event.kapitel)
        self._hinweis_offene_korrekturen(event.buch, event.kapitel)
        # Auch waehrend die TUI laeuft koennen neue Konfliktkopien eintreffen.
        self._fuehre_konflikte_zusammen(event.buch)
        self.query_one(Herkunft).zeige(event.buch, event.kapitel, event.begriff, event.begriff_art)
        # Jedes Pane einzeln absichern: kaputte Daten in einem Pane (z.B. eine
        # unlesbare Datei) sollen nur dieses Pane betreffen, nicht die ganze
        # App beenden oder die uebrigen Panes am Aktualisieren hindern.
        for pane_typ in (ReaderPane, ZusammenfassungPane, TagsPane,
                         StraengePane, QuerbezuegePane):
            try:
                if pane_typ is ReaderPane:
                    self.query_one(pane_typ).lade_kapitel(
                        event.buch, event.kapitel, absatz_index=event.absatz_index)
                else:
                    self.query_one(pane_typ).lade_kapitel(event.buch, event.kapitel)
            except Exception as exc:
                self.notify(f"Fehler beim Laden: {exc}", severity="error")
        self._kapitel_geladen = True
        if self.screen.has_class("baum-offen"):
            # Schublade schliessen; der Fokus darf erst in das Pane, wenn dessen
            # Tab wieder sichtbar ist (sonst fiele er auf None zurueck).
            self.screen.set_class(False, "baum-offen")
            self.call_after_refresh(self._fokussiere_aktiven_tab)
        else:
            self._fokussiere_aktiven_tab()
        self._aktualisiere_aktionsleiste()

    def on_herkunft_zur_bibliothek(self, event: Herkunft.ZurBibliothek) -> None:
        baum = self.query_one(LibraryTree)
        if self.screen.has_class("schmal") and not self.screen.has_class("baum-offen"):
            # Schmal ist der Baum nur als Schublade sichtbar.
            self.screen.set_class(True, "baum-offen")
            self._aktualisiere_aktionsleiste()
        if not baum.zeige_kapitel(event.buch, event.kapitel):
            self.notify("Kapitel nicht in der Bibliothek gefunden.", severity="warning")
            return
        # Der Link hat seinen Zweck erfuellt; die naechste Kapitelwahl blendet
        # die Herkunft wieder ein.
        self.query_one(Herkunft).add_class("leer")
        baum.focus()

    def _fokussiere_aktiven_tab(self) -> None:
        """Legt den Fokus in das Pane des gerade aktiven Tabs, damit dessen
        Tasten (e / ctrl+s / c) und die App-Bindings (Ziffern, q) greifen.
        Bewusst das AKTIVE Pane statt immer ReaderPane: ein verstecktes, aber
        fokussiertes ReaderPane wuerde "e" unsichtbar in den Editiermodus
        schalten, und ctrl+s auf dem Tags-Tab kaeme nicht bei TagsPane an."""
        aktiv = self.query_one(TabbedContent).active
        if aktiv == "tab-text":
            # ReaderPane hat eine eigene Fokus-Logik (Editor beim Bearbeiten,
            # sonst der scrollbare Anzeige-Bereich - siehe dortigen
            # Klassen-Kommentar zu VerticalScroll/Bindings-Kette).
            self.query_one(ReaderPane).fokus_lesebereich()
            return
        self.query_one(_FOKUS_JE_TAB.get(aktiv, ReaderPane)).focus()

    def _aktives_pane(self):
        aktiv = self.query_one(TabbedContent).active
        return self.query_one(_FOKUS_JE_TAB.get(aktiv, ReaderPane))

    def _aktualisiere_aktionsleiste(self) -> None:
        tabs = self.query(TabbedContent)
        leisten = self.query(Aktionsleiste)
        if not tabs or not leisten:
            return
        aktiv = tabs.first().active
        if self.screen.has_class("baum-offen"):
            # Bei offener Schublade sind die Tabs verborgen: Lese-, Bearbeiten-
            # und Farbknoepfe wuerden unsichtbar wirken.
            kontext = "nur_baum"
        elif aktiv == "tab-text":
            reader = self.query(ReaderPane)
            bearbeiten = bool(reader) and reader.first().bearbeiten
            kontext = "bearbeiten" if bearbeiten else "lesen"
        elif aktiv in _FELDER_TABS:
            kontext = "felder"
        else:
            kontext = "nur_baum"
        leisten.first().setze_kontext(kontext)

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        self._aktualisiere_aktionsleiste()

    def on_reader_pane_modus_geaendert(self, event: ReaderPane.ModusGeaendert) -> None:
        self._aktualisiere_aktionsleiste()

    def on_aktionsleiste_aktion_gewaehlt(self, event: Aktionsleiste.AktionGewaehlt) -> None:
        if event.aktion == "baum":
            self.action_baum_umschalten()
            return
        app_aktionen = {
            "suche": self.action_suche,
            "notizen": self.action_notizen,
            "korr": self.action_korrektur,
            "speed": self.action_speedreader,
            "weiter": self.action_naechstes_kapitel,
            "zurueck": self.action_voriges_kapitel,
        }
        if event.aktion in app_aktionen:
            app_aktionen[event.aktion]()
            return
        methode = getattr(self._aktives_pane(), f"action_{_KNOPF_AKTION[event.aktion]}", None)
        if methode is not None:
            methode()

    def action_suche(self) -> None:
        """Volltextsuche oeffnen. Bei offenem Kapitel bietet der Dialog an, nur
        in diesem Buch zu suchen."""
        if isinstance(self.screen, SuchScreen):
            return
        reader = self.query_one(ReaderPane)
        self.push_screen(SuchScreen(self.root_pfad, reader.buch), self._springe_zu_treffer)

    def _springe_zu_treffer(self, treffer) -> None:
        if treffer is None:
            return
        self._oeffne(treffer.buch, treffer.kapitel, treffer.absatz_index)

    def action_notizen(self) -> None:
        """Liste aller Kommentare und Highlights oeffnen."""
        if isinstance(self.screen, (NotizenScreen, SuchScreen)):
            return
        reader = self.query_one(ReaderPane)
        self.push_screen(NotizenScreen(self.root_pfad, reader.buch), self._springe_zu_notiz)

    def _springe_zu_notiz(self, notiz) -> None:
        if notiz is None:
            return
        self._oeffne(notiz.buch, notiz.kapitel, notiz.sprungabsatz())

    def action_speedreader(self) -> None:
        """Schnellleser fuer die KI-Felder (Zusammenfassung, Thesen, ...) des
        aktuellen Kapitels."""
        if isinstance(self.screen, (SpeedreaderScreen, KorrekturScreen, NotizenScreen, SuchScreen)):
            return
        if self._aktuell is None:
            self.notify("Erst ein Kapitel öffnen.", severity="warning")
            return
        buch, kapitel = self._aktuell
        self.push_screen(SpeedreaderScreen(buch, kapitel, library.read_tags(buch, kapitel.datei)))

    def action_korrektur(self) -> None:
        """Dialog zum Abarbeiten der korrektur-Marken (Taste k markiert)."""
        if isinstance(self.screen, (KorrekturScreen, NotizenScreen, SuchScreen)):
            return
        reader = self.query_one(ReaderPane)
        self.push_screen(KorrekturScreen(self.root_pfad, reader.buch), self._nach_korrektur)

    def _nach_korrektur(self, stelle) -> None:
        # Ein geaendertes Kapitel neu laden, damit die Korrektur sofort sichtbar ist.
        if stelle is None:
            return
        buch, kapitel, absatz = stelle
        self._oeffne(buch, kapitel, absatz)

    def _hinweis_offene_korrekturen(self, buch, kapitel) -> None:
        try:
            offen = [m for m in korrektur.sammle_marken(buch) if m.datei == kapitel.datei]
        except Exception:
            return
        if offen:
            self.notify(f"{len(offen)} offene Korrektur-Marke(n) in diesem Kapitel (Taste x).")

    def _blaettere(self, richtung: int) -> None:
        if self._aktuell is None:
            return
        if self.query_one(ReaderPane).bearbeiten:
            self.notify("Erst speichern oder verwerfen (Strg+S / Esc).", severity="warning")
            return
        buch, kapitel = self._aktuell
        ziel = library.kapitel_nachbar(buch, kapitel, richtung)
        if ziel is None:
            self.notify("Letztes Kapitel." if richtung > 0 else "Erstes Kapitel.")
            return
        # Im aktuellen Tab bleiben: wer gerade Fazit oder Tags liest, will beim
        # Weiterblaettern dieselbe Ansicht des naechsten Kapitels.
        self._oeffne(buch, ziel, zum_text=False)

    def action_naechstes_kapitel(self) -> None:
        self._blaettere(+1)

    def action_voriges_kapitel(self) -> None:
        self._blaettere(-1)

    def action_baum_umschalten(self) -> None:
        if not self.screen.has_class("schmal"):
            # Breit steht der Baum immer daneben; "0" bringt nur den Fokus zurueck.
            self.query_one(LibraryTree).focus()
            return
        offen = not self.screen.has_class("baum-offen")
        self.screen.set_class(offen, "baum-offen")
        self._aktualisiere_aktionsleiste()
        if offen:
            self.query_one(LibraryTree).focus()
        else:
            self.call_after_refresh(self._fokussiere_aktiven_tab)

    def action_tab_text(self) -> None:
        self.query_one(TabbedContent).active = "tab-text"
        self._fokussiere_aktiven_tab()

    def action_tab_key(self) -> None:
        self.query_one(TabbedContent).active = "tab-key"
        self._fokussiere_aktiven_tab()

    def action_tab_tags(self) -> None:
        self.query_one(TabbedContent).active = "tab-tags"
        self._fokussiere_aktiven_tab()

    def action_tab_straenge(self) -> None:
        self.query_one(TabbedContent).active = "tab-straenge"
        self._fokussiere_aktiven_tab()

    def action_tab_querbezuege(self) -> None:
        self.query_one(TabbedContent).active = "tab-querbezuege"
        self._fokussiere_aktiven_tab()
