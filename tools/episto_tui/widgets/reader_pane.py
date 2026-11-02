from __future__ import annotations
import bisect
import dataclasses
from datetime import datetime
from textual import events
from textual.widget import Widget
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Input, Markdown, TextArea
from textual.widgets.markdown import MarkdownBlock
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from episto_tui import library, annotate
from episto_tui.models import Buch, Kapitel, Highlight, Kommentar

# "yellow"/"pink" (Rich-Standardnamen) erreichen gegen die Standard-
# Vordergrundfarbe des dunklen Themes (#e0e0e0) nur ~1.2:1 bzw. ~1.16:1
# Kontrast (WCAG AA verlangt >=4.5:1 fuer normalen Text) - de facto
# unlesbar (siehe Task-2-Review, per Screenshot-Export gegen die echte
# Bibliothek gemessen und vom Nutzer bestaetigt: "gelb und rosa ist
# unlesbar, blau ist ok"). Gedaempfte Hex-Toene statt der Namen halten
# denselben Farbeindruck (Dunkelgelb/Oliv, Altrosa), erreichen aber
# gegen #e0e0e0 ~5.6:1 bzw. ~6.9:1 - vergleichbar mit "blue" (~6.5:1),
# das unveraendert bleibt. Der vierte Eintrag "korrektur" (#5c1a1a) ist
# ebenfalls ein gedaempfter Hex-Ton und erreicht gegen #e0e0e0 ~9.8:1.
_HINTERGRUNDFARBE = {"gelb": "#595900", "rosa": "#594347", "blau": "blue", "korrektur": "#5c1a1a"}


# --- Zuordnung Markdown-Widget <-> Absatz (split_paragraphs) -----------------
#
# Die Absatz-Liste (annotate.split_paragraphs) trennt nur an Leerzeilen im
# rohen Text. Textuals Markdown-Widget erzeugt dagegen pro Markdown-Element
# einen eigenen MarkdownBlock (Ueberschrift, Liste, Zitat, ...), teils
# verschachtelt. Eine Ueberschrift + Liste + Zitat ohne Leerzeile dazwischen
# ist EIN Absatz, aber mehrere (verschachtelte) Bloecke; eine "lockere"
# Liste mit Leerzeilen zwischen den Punkten ist umgekehrt EIN Block, aber
# mehrere Absaetze. Eine Zuordnung ueber die Position in der Block-Liste ist
# deshalb falsch (verifiziert: 59 von 103 echten Kapiteln betroffen).
#
# Stattdessen zeilenbasiert: an Markdown.update() geht der Text von
# annotate.render_mit_kommentaren() (Absaetze und Kommentarbloecke, durch
# Leerzeilen getrennt); dessen Segmentliste kennt die Startzeile jedes
# Absatzes bzw. Kommentarblocks. Jeder MarkdownBlock kennt seine Quellzeilen
# (source_range, absolut, auch fuer verschachtelte Bloecke) - per Bisektion
# ergibt sich daraus das Segment.


def _segment_zu_zeile(startzeilen: list[int], zeile: int) -> int:
    # Leerzeilen zwischen zwei Segmenten fallen dem vorigen Segment zu.
    return max(0, bisect.bisect_right(startzeilen, zeile) - 1)


def _zeilenbereich(knoten: Widget) -> tuple[int, int] | None:
    """Quellzeilen [start, ende) eines Knotens im Markdown-Baum: bei einem
    MarkdownBlock dessen source_range, bei einem reinen Container (z.B. dem
    Horizontal eines Listenpunkts) die Spanne der darin enthaltenen Bloecke,
    ohne enthaltene Bloecke (z.B. das Aufzaehlungszeichen) None."""
    if isinstance(knoten, MarkdownBlock):
        return knoten.source_range
    bereiche = [block.source_range for block in knoten.query(MarkdownBlock)]
    if not bereiche:
        return None
    return min(b[0] for b in bereiche), max(b[1] for b in bereiche)


def _aufgeloeste_highlights(absaetze: list[str], highlights: list[Highlight]) -> list[tuple[int | None, Highlight]]:
    """Wie bei Kommentaren (annotate.render_mit_kommentaren): der gespeicherte
    absatz_index ist nur ein Hinweis, massgeblich ist locate_paragraph() mit
    dem Textanfang - sonst wandert ein Highlight nach einer Bearbeitung
    (z.B. neuer Absatz davor) auf den falschen Absatz. None = verwaist."""
    return [
        (annotate.locate_paragraph(absaetze, h.absatz_index, h.absatz_anfang), h)
        for h in highlights
    ]


class ReaderPane(Vertical, can_focus=True):
    # can_focus=True: Vertical ist standardmaessig nicht fokussierbar, aber die
    # BINDINGS (e / ctrl+s / escape / g / r / b / c / d) muessen auf einem fokussierten
    # Widget sitzen, damit sie ueberhaupt in die Tastatur-Dispatch-Kette
    # gelangen (siehe Tests, die pane.focus() explizit aufrufen).
    #
    # Im Lesemodus fokussiert fokus_lesebereich() trotzdem NICHT das Pane
    # selbst, sondern #anzeige-scroll: Textuals Bindings-Kette laeuft vom
    # fokussierten Widget aus nach OBEN durch dessen Vorfahren. Waere das
    # Pane fokussiert, kaeme VerticalScrolls eigene up/down/pageup/pagedown-
    # Bindings (fuer echtes Scrollen per Tastatur) nie zum Zug, weil
    # VerticalScroll ein Kind des Pane ist, nicht ein Vorfahre. Mit Fokus
    # auf #anzeige-scroll gilt beides: dessen eigene Scroll-Bindings UND die
    # Bindings dieser Klasse (Vorfahre) werden beide geprüft (empirisch
    # verifiziert, siehe Session vom 2026-09-27 - "kann nicht scrollen").
    BINDINGS = [
        Binding("e", "toggle_edit", "Editieren"),
        Binding("ctrl+s", "speichern", "Speichern"),
        Binding("escape", "verwerfen", "Verwerfen"),
        Binding("g", "highlight_gelb", "Gelb"),
        Binding("r", "highlight_rosa", "Rosa"),
        Binding("b", "highlight_blau", "Blau"),
        Binding("k", "highlight_korrektur", "Korrektur"),
        Binding("c", "kommentieren", "Kommentar"),
        Binding("d", "kommentar_loeschen", "Kommentar löschen"),
    ]

    # Reaktiv, damit die Aktionsleiste (Touch) ihre Knoepfe wechseln kann,
    # egal ob der Modus per Taste "e" oder per Knopf umgeschaltet wurde.
    bearbeiten = reactive(False)

    class ModusGeaendert(Message):
        def __init__(self, bearbeiten: bool) -> None:
            self.bearbeiten = bearbeiten
            super().__init__()

    def watch_bearbeiten(self, wert: bool) -> None:
        self.post_message(self.ModusGeaendert(wert))

    def __init__(self) -> None:
        super().__init__()
        self.buch: Buch | None = None
        self.kapitel: Kapitel | None = None
        # Zuletzt per Klick getroffener Absatz - Ziel der naechsten
        # Farbtaste. None, solange noch nicht (oder nicht auf einen
        # MarkdownBlock) geklickt wurde.
        self._aktiver_absatz_index: int | None = None
        # Zuletzt per Klick getroffener Kommentarblock (None bei einem Klick
        # auf einen Absatz): Ziel von "c" (aendern) und "d" (loeschen).
        self._aktiver_kommentar: Kommentar | None = None
        # Was das offene Kommentarfeld bei Enter tut: ("neu", absatz_index)
        # oder ("aendern", Kommentar); None = Feld geschlossen.
        self._kommentar_ziel: tuple[str, int | Kommentar] | None = None
        # Segmente des zuletzt an #anzeige uebergebenen Texts - die
        # Klick-Zuordnung muss sich auf genau den ANGEZEIGTEN Text beziehen.
        self._angezeigte_segmente: list[annotate.Segment] = []
        self._angezeigte_startzeilen: list[int] = []
        # Absatz, zu dem nach dem naechsten Rendern gescrollt wird (Suche).
        self._springe_zu: int | None = None
        # Zuletzt gelesener (oberster sichtbarer) Absatz. Wird beim Scrollen
        # nachgefuehrt; solange der Tab verborgen ist, scrollt nichts, der
        # Wert bleibt also gueltig (siehe aktueller_absatz).
        self._lese_absatz: int = 0
        self._lese_timer = None
        # False, solange Markdown.update() die Bloecke des neuen Kapitels noch
        # mountet: bis dahin gehoeren die Bloecke zum alten Kapitel.
        self._gerendert = False

    def compose(self):
        # Markdown selbst waechst mit height:auto auf volle Inhaltshoehe und
        # hat kein eigenes Scrolling (overflow-y: hidden in seinem
        # DEFAULT_CSS); erst der umgebende VerticalScroll gibt einen
        # Viewport mit tatsaechlichem Scroll vor (Bug: laengere Kapitel
        # liessen sich gar nicht scrollen, ueberstehender Text wurde vom
        # Vertical-Pane selbst nur abgeschnitten).
        with VerticalScroll(id="anzeige-scroll"):
            yield Markdown(id="anzeige")
        yield TextArea(id="editor")
        yield Input(placeholder="Kommentar eintippen, Enter speichert, Esc bricht ab", id="kommentar-eingabe")

    def on_mount(self) -> None:
        self.query_one("#editor", TextArea).display = False
        self.query_one("#kommentar-eingabe", Input).display = False
        self.watch(self.query_one("#anzeige-scroll", VerticalScroll), "scroll_y", self._scroll_geaendert)

    def _scroll_geaendert(self, _alt: float, _neu: float) -> None:
        # Entprellt: beim Scrollen kommen viele Ereignisse hintereinander.
        if self._lese_timer is not None:
            self._lese_timer.stop()
        self._lese_timer = self.set_timer(0.15, self._merke_lese_absatz)

    def _merke_lese_absatz(self) -> None:
        absatz = self._berechne_oberen_absatz()
        if absatz is not None:
            self._lese_absatz = absatz

    def _berechne_oberen_absatz(self) -> int | None:
        """Index des Absatzes am oberen Rand des Lesebereichs; None, wenn das
        nicht bestimmbar ist (verborgen, noch nicht gerendert, Editiermodus)."""
        if (self.bearbeiten or not self._gerendert or not self._angezeigte_segmente
                or not self._sichtbar_im_baum()):
            return None
        scroll = self.query_one("#anzeige-scroll", VerticalScroll)
        if scroll.region.height == 0:
            return None
        oberkante = scroll.region.y
        for kind in self.query_one("#anzeige", Markdown).children:
            bereich = _zeilenbereich(kind)
            if bereich is None or kind.region.height == 0:
                continue
            if kind.region.bottom > oberkante:
                segment = self._angezeigte_segmente[
                    _segment_zu_zeile(self._angezeigte_startzeilen, bereich[0])
                ]
                if segment.absatz_index is not None:
                    return segment.absatz_index
        return None

    def aktueller_absatz(self) -> int:
        """Absatz, bei dem der Leser gerade steht (fuer die Leseposition)."""
        absatz = self._berechne_oberen_absatz()
        return absatz if absatz is not None else self._lese_absatz

    def lade_kapitel(self, buch: Buch, kapitel: Kapitel, absatz_index: int | None = None) -> None:
        self.buch = buch
        self.kapitel = kapitel
        self._springe_zu = absatz_index
        self._lese_absatz = absatz_index or 0
        self.bearbeiten = False
        self._aktiver_absatz_index = None
        self._aktiver_kommentar = None
        self._schliesse_kommentar_eingabe(fokus=False)
        self._zeige_lesemodus()

    def _zeige_lesemodus(self) -> None:
        text = library.read_chapter_text(self.buch, self.kapitel.datei)
        kommentare = library.read_kommentare(self.buch, self.kapitel.datei)
        absaetze = annotate.split_paragraphs(text)
        annotiert, segmente = annotate.render_mit_kommentaren(absaetze, kommentare)
        anzeige = self.query_one("#anzeige", Markdown)
        self._gerendert = False
        update_abschluss = anzeige.update(annotiert)
        self._angezeigte_segmente = segmente
        self._angezeigte_startzeilen = [s.startzeile for s in segmente]
        highlights = library.read_highlights(self.buch, self.kapitel.datei)
        # Markdown.update() mountet seine MarkdownBlock-Kinder asynchron;
        # erst nach dem zurueckgegebenen Awaitable existieren die NEUEN
        # Bloecke, die hier eingefaerbt werden sollen. Ueber einen Worker
        # statt eines await, damit diese Methode (und ihre synchronen
        # Aufrufer lade_kapitel()/die action_*-Methoden) nicht async werden
        # muss - das wuerde jeden bestehenden synchronen
        # lade_kapitel()-Testaufruf zu einer nie ausgefuehrten Coroutine
        # machen. exclusive=True verhindert, dass ein spaeterer, schnellerer
        # Aufruf von einem noch laufenden aelteren Worker ueberschrieben wird.
        self.run_worker(
            self._faerbe_absaetze(update_abschluss, absaetze, segmente, highlights),
            group="highlight-render", exclusive=True,
        )
        self.query_one("#anzeige-scroll", VerticalScroll).display = True
        self.query_one("#editor", TextArea).display = False
        # Fokus nur setzen, wenn dieses Pane gerade wirklich sichtbar ist:
        # app.py.on_chapter_selected() ruft lade_kapitel() fuer ALLE Panes
        # auf, auch fuer das Pane eines gerade NICHT aktiven Tabs. Wuerde ein
        # verstecktes Pane trotzdem fokussiert, kann Textuals verzoegerte
        # Hide-Kaskade (ContentSwitcher versteckt eine TabPane -> Hide-Events
        # an alle Kind-Widgets, teils erst nach einem spaeteren Refresh
        # zugestellt) den kurz zuvor korrekt gesetzten Fokus des WIRKLICH
        # aktiven Tabs wieder zerstoeren (siehe dritte Scroll-Bug-Runde,
        # 2026-09-27: TagsPane bekam nach dem Kapitel-Wechsel trotz aktivem
        # Tags-Tab ein verspaetetes Hide-Event und wurde geblurred, weil
        # zuvor kurzzeitig das versteckte ReaderPane fokussiert worden war).
        if self._sichtbar_im_baum():
            self.fokus_lesebereich()

    async def _faerbe_absaetze(
        self, update_abschluss, absaetze: list[str], segmente: list[annotate.Segment],
        highlights: list[Highlight],
    ) -> None:
        await update_abschluss
        self._gerendert = True
        farbe_je_absatz: dict[int, str] = {}
        # Exakte Treffer (gespeicherter == aufgeloester Index) zuletzt, damit
        # sie gewinnen, falls zwei Highlights auf denselben Absatz zeigen.
        for index, h in sorted(
            _aufgeloeste_highlights(absaetze, highlights),
            key=lambda paar: paar[0] == paar[1].absatz_index,
        ):
            if index is not None:
                farbe_je_absatz[index] = h.farbe
        self._faerbe_knoten(
            self.query_one("#anzeige", Markdown), segmente,
            [s.startzeile for s in segmente], farbe_je_absatz,
        )
        if self._springe_zu is not None:
            ziel, self._springe_zu = self._springe_zu, None
            self.call_after_refresh(self._scrolle_zu_absatz, segmente, ziel)

    def _scrolle_zu_absatz(self, segmente: list[annotate.Segment], absatz_index: int,
                           versuch: int = 0) -> None:
        """Scrollt den obersten Block des Absatzes an den Anfang des
        Lesebereichs. Unbekannter Index (Text zwischenzeitlich geaendert):
        bleibt oben stehen."""
        startzeile = next(
            (s.startzeile for s in segmente if s.art == "absatz" and s.absatz_index == absatz_index),
            None,
        )
        if startzeile is None:
            return
        anzeige = self.query_one("#anzeige", Markdown)
        scroll = self.query_one("#anzeige-scroll", VerticalScroll)
        for kind in anzeige.children:
            bereich = _zeilenbereich(kind)
            if bereich is not None and bereich[1] > startzeile:
                scroll.scroll_to_widget(kind, top=True, animate=False)
                break
        # Direkt nach dem Start ist das Layout oft noch nicht fertig (virtuelle
        # Hoehe 0): das Scrollen verpufft. Dann kurz warten und erneut versuchen.
        if scroll.max_scroll_y == 0 and versuch < 8:
            self.set_timer(0.1, lambda: self._scrolle_zu_absatz(segmente, absatz_index, versuch + 1))

    def _faerbe_knoten(
        self, container: Widget, segmente: list[annotate.Segment],
        startzeilen: list[int], farbe_je_absatz: dict[int, str],
    ) -> None:
        """Faerbt jeweils den groessten Knoten ein, der vollstaendig in EINEM
        Segment liegt: normalerweise die obersten Bloecke (direkte Kinder von
        #anzeige - verschachtelte Listenpunkte/Zitatinhalte bleiben
        transparent und wirken durch ihren gefaerbten Eltern-Block trotzdem
        einfarbig). Nur Absatz-Segmente werden gefaerbt; Kommentarbloecke und
        die Ueberschrift verwaister Kommentare bleiben transparent. Ein Block,
        der mehrere Segmente ueberspannt (z.B. eine Liste mit Leerzeilen
        zwischen den Punkten), wird selbst nicht gefaerbt, sondern in seine
        Kinder zerlegt; ein solcher Block ohne innere Bloecke (z.B. Codeblock
        mit Leerzeile) folgt seiner Startzeile - genau wie die Klick-Zuordnung
        in on_click()."""

        def farbe_von(segment_index: int) -> str:
            segment = segmente[segment_index]
            if segment.art != "absatz":
                return "transparent"
            return _HINTERGRUNDFARBE.get(farbe_je_absatz.get(segment.absatz_index), "transparent")

        for kind in container.children:
            bereich = _zeilenbereich(kind)
            if bereich is None:
                continue
            start, ende = bereich
            erster = _segment_zu_zeile(startzeilen, start)
            letzter = _segment_zu_zeile(startzeilen, max(start, ende - 1))
            ist_blatt = isinstance(kind, MarkdownBlock) and not kind.query(MarkdownBlock)
            if erster == letzter or ist_blatt:
                kind.styles.background = farbe_von(erster)
            else:
                kind.styles.background = "transparent"
                self._faerbe_knoten(kind, segmente, startzeilen, farbe_je_absatz)

    def _sichtbar_im_baum(self) -> bool:
        """Ob dieses Widget und alle Vorfahren aktuell display=True haben
        (anders als is_on_screen synchron und ohne Compositor-Verzoegerung,
        da ContentSwitcher display beim Tab-Wechsel sofort umschaltet)."""
        knoten = self
        while knoten is not None:
            if not knoten.display:
                return False
            knoten = knoten.parent
        return True

    def fokus_lesebereich(self) -> None:
        """Fuer app.py: legt den Fokus in das gerade sichtbare innere
        Widget dieses Panes (Editor beim Bearbeiten, sonst die scrollbare
        Anzeige) - z.B. beim Wechsel auf den Text-Tab per Zifferntaste, wo
        kein lade_kapitel()-Aufruf stattfindet."""
        if self._kommentar_ziel is not None:
            # Ein offenes Kommentarfeld behaelt den Fokus (Softtastatur).
            self.query_one("#kommentar-eingabe", Input).focus()
        elif self.bearbeiten:
            self.query_one("#editor", TextArea).focus()
        else:
            self.query_one("#anzeige-scroll", VerticalScroll).focus()

    def on_click(self, event: events.Click) -> None:
        # Bestimmt nur, WELCHER Absatz von der naechsten Farbtaste betroffen
        # waere - faerbt hier noch nichts ein (Design: Klick + Taste, nicht
        # Klick allein). Ein Klick daneben (z.B. auf #anzeige-scroll selbst,
        # wenn der Text nicht die ganze Hoehe ausfuellt) laesst die zuvor
        # per Klick getroffene Auswahl unveraendert stehen.
        if self.bearbeiten or self.buch is None:
            return
        geklickt = event.widget
        # Ein Klick in den Lesebereich schliesst ein offenes Kommentarfeld
        # (sonst bliebe sein Ziel veraltet und das Feld koennte bis in den
        # Editiermodus ueberleben). Ein Klick INS Feld selbst (Click bubbelt
        # bis hierher) darf es nicht schliessen.
        if self._kommentar_ziel is not None:
            eingabe = self.query_one("#kommentar-eingabe", Input)
            if geklickt is None or eingabe not in geklickt.ancestors_with_self:
                self._schliesse_kommentar_eingabe(fokus=False)
        anzeige = self.query_one("#anzeige", Markdown)
        if geklickt is None or anzeige not in geklickt.ancestors:
            return
        # Vom getroffenen Widget nach oben bis zum ersten Knoten mit
        # Quellzeilen (ein MarkdownBlock oder z.B. der Container eines
        # Listenpunkts, wenn das Aufzaehlungszeichen selbst getroffen wurde).
        # Dessen Startzeile bestimmt den Absatz - zeilenbasiert statt ueber
        # die Position in einer Block-Liste, siehe _segment_zu_zeile().
        knoten: Widget | None = geklickt
        while knoten is not None and knoten is not anzeige:
            bereich = _zeilenbereich(knoten)
            if bereich is not None:
                if self._angezeigte_segmente:
                    segment = self._angezeigte_segmente[
                        _segment_zu_zeile(self._angezeigte_startzeilen, bereich[0])
                    ]
                    self._aktiver_absatz_index = segment.absatz_index
                    self._aktiver_kommentar = segment.kommentar
                return
            knoten = knoten.parent

    def action_highlight_gelb(self) -> None:
        self._schalte_highlight("gelb")

    def action_highlight_rosa(self) -> None:
        self._schalte_highlight("rosa")

    def action_highlight_blau(self) -> None:
        self._schalte_highlight("blau")

    def action_highlight_korrektur(self) -> None:
        self._schalte_highlight("korrektur")

    def _schalte_highlight(self, farbe: str) -> None:
        if self.bearbeiten or self.buch is None or self._aktiver_absatz_index is None:
            return
        text = library.read_chapter_text(self.buch, self.kapitel.datei)
        absaetze = annotate.split_paragraphs(text)
        index = self._aktiver_absatz_index
        if not (0 <= index < len(absaetze)):
            return
        aufgeloest = _aufgeloeste_highlights(
            absaetze, library.read_highlights(self.buch, self.kapitel.datei),
        )
        # library.write/remove_highlight schluesseln nach dem GESPEICHERTEN
        # absatz_index. Nach einer Bearbeitung (z.B. neuer Absatz davor) kann
        # der gespeicherte Index eines Highlights auf einen anderen Absatz
        # zeigen als sein aufgeloester - ein Schreiben an diesen Index wuerde
        # dann ein fremdes Highlight ueberschreiben. Deshalb zuerst alle
        # veralteten Anker auf ihren aufgeloesten Index nachziehen (erst alle
        # entfernen, dann neu schreiben, damit sie sich nicht gegenseitig
        # ueberschreiben). Verwaiste Highlights (None, ihr Absatz existiert
        # nicht mehr) bleiben stehen, koennen aber von einem Schreibvorgang
        # an ihrem gespeicherten Index ersetzt werden - sichtbar waren sie
        # ohnehin nicht mehr.
        veraltet = [(i, h) for i, h in aufgeloest if i is not None and i != h.absatz_index]
        for _i, h in veraltet:
            library.remove_highlight(self.buch, self.kapitel.datei, h.absatz_index)
        for i, h in veraltet:
            library.write_highlight(self.buch, dataclasses.replace(h, absatz_index=i))
        bestehend = next((h for i, h in aufgeloest if i == index), None)
        if bestehend is not None and bestehend.farbe == farbe:
            library.remove_highlight(self.buch, self.kapitel.datei, index)
        else:
            library.write_highlight(self.buch, Highlight(
                datei=self.kapitel.datei, absatz_index=index,
                absatz_anfang=absaetze[index][:80], farbe=farbe,
            ))
        self._zeige_lesemodus()

    def _schliesse_kommentar_eingabe(self, fokus: bool = True) -> None:
        self._kommentar_ziel = None
        eingabe = self.query_one("#kommentar-eingabe", Input)
        eingabe.value = ""
        eingabe.display = False
        if fokus:
            self.fokus_lesebereich()

    def action_kommentieren(self) -> None:
        if self.bearbeiten or self.buch is None:
            return
        if self._kommentar_ziel is not None:
            # Feld ist schon offen: Text nicht ueberschreiben, nur Fokus zurueck.
            self.query_one("#kommentar-eingabe", Input).focus()
            return
        if self._aktiver_kommentar is not None:
            ziel: tuple[str, int | Kommentar] = ("aendern", self._aktiver_kommentar)
            vorbelegung = self._aktiver_kommentar.text
        elif self._aktiver_absatz_index is not None:
            ziel = ("neu", self._aktiver_absatz_index)
            vorbelegung = ""
        else:
            return
        self._kommentar_ziel = ziel
        eingabe = self.query_one("#kommentar-eingabe", Input)
        eingabe.value = vorbelegung
        eingabe.display = True
        eingabe.focus()

    def action_kommentar_loeschen(self) -> None:
        if self.bearbeiten or self.buch is None or self._aktiver_kommentar is None:
            return
        if self._kommentar_ziel is not None:
            # Offenes Kommentarfeld: sein Ziel darf nicht veralten.
            return
        library.remove_kommentar(self.buch, self._aktiver_kommentar)
        self._aktiver_kommentar = None
        self._zeige_lesemodus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "kommentar-eingabe":
            return
        event.stop()
        if self.bearbeiten:
            return
        ziel = self._kommentar_ziel
        text = event.value.strip()
        self._schliesse_kommentar_eingabe()
        if ziel is None or not text or self.buch is None:
            return
        art, wert = ziel
        if art == "neu":
            absaetze = annotate.split_paragraphs(
                library.read_chapter_text(self.buch, self.kapitel.datei)
            )
            if not (0 <= wert < len(absaetze)):
                return
            library.add_kommentar(self.buch, Kommentar(
                datei=self.kapitel.datei, absatz_index=wert,
                absatz_anfang=absaetze[wert][:80], text=text,
                erstellt=datetime.now().strftime("%Y-%m-%d %H:%M"),
            ))
        else:
            library.update_kommentar(self.buch, wert, text)
            self._aktiver_kommentar = None
        self._zeige_lesemodus()

    def action_toggle_edit(self) -> None:
        if self.buch is None:
            return
        if self.bearbeiten:
            self._zeige_lesemodus()
            self.bearbeiten = False
        else:
            # Ein offenes Kommentarfeld darf nicht in den Editiermodus
            # mitkommen (der Fokus geht unten ohnehin an den Editor).
            self._schliesse_kommentar_eingabe(fokus=False)
            text = library.read_chapter_text(self.buch, self.kapitel.datei)
            editor = self.query_one("#editor", TextArea)
            editor.text = text
            editor.display = True
            self.query_one("#anzeige-scroll", VerticalScroll).display = False
            self.bearbeiten = True
            # Tastendruecke muessen im Editor landen -- bliebe der Fokus auf
            # dem Pane, wuerde schon das naechste getippte "e" (Pane-Binding)
            # zurueck in den Lesemodus schalten und die Eingabe verwerfen.
            editor.focus()

    def action_speichern(self) -> None:
        if not self.bearbeiten or self.buch is None:
            return
        neuer_text = self.query_one("#editor", TextArea).text
        library.write_chapter_text(self.buch, self.kapitel.datei, neuer_text)
        # Absaetze koennen sich verschoben haben: alte Klick-Auswahl verwerfen.
        self._aktiver_absatz_index = None
        self._aktiver_kommentar = None
        self.bearbeiten = False
        self._zeige_lesemodus()

    def action_verwerfen(self) -> None:
        if self._kommentar_ziel is not None:
            self._schliesse_kommentar_eingabe()
            return
        if not self.bearbeiten:
            return
        self.bearbeiten = False
        self._zeige_lesemodus()
