from __future__ import annotations
from textual.containers import Vertical
from textual.content import Content
from textual.message import Message
from textual.widgets import Static
from episto_tui.models import Buch, Kapitel


class _QuellZeile(Static):
    """Anklickbare Zeile "Aus: Autor - Buch - Kapitel"."""

    def on_click(self, event) -> None:
        event.stop()
        self.parent.zur_bibliothek()


class Herkunft(Vertical):
    """Zeile ueber den Tabs: woher der gezeigte Text stammt.

    Bei Wahl ueber "Begriffe & Definitionen" steht in einer eigenen Zeile der
    angeklickte Eintrag. Ein Klick auf die Quellzeile springt in der
    Seitenleiste zu diesem Kapitel unter "Bibliothek". Die Zeilen brechen um,
    damit auch lange Buchtitel auf dem schmalen Handy-Terminal vollstaendig
    sind."""

    # Gekuerzt: die volle Definition steht im Tab "Tags"; auf dem schmalen
    # Terminal soll die Herkunftszeile nicht den Text verdraengen.
    _MAX_BEGRIFF = 140

    DEFAULT_CSS = """
    Herkunft { height: auto; background: $boost; }
    Herkunft.leer { display: none; }
    Herkunft Static { padding: 0 1; color: $text-muted; }
    Herkunft #begriff { display: none; }
    Herkunft.mit-begriff #begriff { display: block; }
    Herkunft #quelle { text-style: underline; }
    Herkunft #quelle:hover { color: $text; background: $primary 30%; }
    """

    class ZurBibliothek(Message):
        """Die Quellzeile wurde angeklickt."""

        def __init__(self, buch: Buch, kapitel: Kapitel) -> None:
            self.buch = buch
            self.kapitel = kapitel
            super().__init__()

    def __init__(self) -> None:
        super().__init__(id="herkunft", classes="leer")
        self._buch: Buch | None = None
        self._kapitel: Kapitel | None = None

    def compose(self):
        yield Static("", id="begriff")
        quelle = _QuellZeile("", id="quelle")
        quelle.tooltip = "Klick: in der Bibliothek anzeigen"
        yield quelle

    def zeige(self, buch: Buch, kapitel: Kapitel, begriff: str | None = None,
              begriff_art: str | None = None) -> None:
        self._buch, self._kapitel = buch, kapitel
        # Content(...) statt str: Autor/Titel/Begriff sind Daten, kein Markup.
        quelle = f"Aus: {buch.autor} \u2013 {buch.titel} \u00b7 {kapitel.nr}. {kapitel.titel}"
        self.query_one("#quelle", Static).update(Content(quelle))
        if begriff:
            if len(begriff) > self._MAX_BEGRIFF:
                begriff = begriff[: self._MAX_BEGRIFF - 1] + "\u2026"
            self.query_one("#begriff", Static).update(Content(f"{begriff_art}: \u201e{begriff}\u201c"))
        self.set_class(bool(begriff), "mit-begriff")
        self.remove_class("leer")

    def zur_bibliothek(self) -> None:
        if self._buch is not None and self._kapitel is not None:
            self.post_message(self.ZurBibliothek(self._buch, self._kapitel))
