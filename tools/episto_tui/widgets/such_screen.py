from __future__ import annotations
from pathlib import Path
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Input, OptionList, Static
from textual.widgets.option_list import Option
from episto_tui import suche
from episto_tui.models import Buch


class SuchScreen(ModalScreen["suche.Treffer | None"]):
    """Volltextsuche als Vollbild-Dialog: Begriffe eintippen, Enter sucht,
    Auswahl eines Treffers springt dorthin (Dialog liefert den Treffer)."""

    BINDINGS = [Binding("escape", "abbrechen", "Schließen")]

    DEFAULT_CSS = """
    SuchScreen { align: center middle; }
    SuchScreen #such-box { width: 100%; height: 100%; padding: 0 1; background: $surface; }
    SuchScreen #such-status { height: auto; color: $text-muted; }
    SuchScreen OptionList { height: 1fr; }
    SuchScreen Checkbox { height: auto; }
    """

    def __init__(self, root: Path, aktuelles_buch: Buch | None = None) -> None:
        super().__init__()
        self.root_pfad = root
        self.aktuelles_buch = aktuelles_buch
        self._treffer: list[suche.Treffer] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="such-box"):
            yield Input(
                placeholder='Suchbegriffe (alle müssen im Absatz stehen), "Phrase" in Anführungszeichen',
                id="such-eingabe",
            )
            if self.aktuelles_buch is not None:
                yield Checkbox(f"Nur in „{self.aktuelles_buch.titel}“", id="nur-buch")
            yield Static("Enter sucht · Esc schließt", id="such-status")
            yield OptionList(id="such-treffer")

    def on_mount(self) -> None:
        self.query_one("#such-eingabe", Input).focus()

    def action_abbrechen(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        anfrage = event.value
        if not suche.parse_anfrage(anfrage):
            self._status(f"Mindestens ein Begriff mit {suche.MIN_TERM_LAENGE}+ Zeichen eingeben.")
            return
        nur_buch = None
        kontrollkasten = self.query("#nur-buch")
        if kontrollkasten and kontrollkasten.first(Checkbox).value:
            nur_buch = self.aktuelles_buch
        self._status("Suche läuft …")
        self.query_one("#such-treffer", OptionList).clear_options()
        self._suche_im_hintergrund(anfrage, nur_buch)

    # Thread-Worker: die Suche liest viele Dateien und darf die Oberflaeche
    # (Eingabe, Esc) nicht blockieren. exclusive: eine neue Suche ersetzt die
    # laufende.
    @work(thread=True, exclusive=True, group="suche")
    def _suche_im_hintergrund(self, anfrage: str, nur_buch: Buch | None) -> None:
        ergebnis = suche.suche(self.root_pfad, anfrage, nur_buch=nur_buch)
        self.app.call_from_thread(self._zeige_ergebnis, ergebnis)

    def _zeige_ergebnis(self, ergebnis: suche.Ergebnis) -> None:
        self._treffer = ergebnis.treffer
        liste = self.query_one("#such-treffer", OptionList)
        liste.clear_options()
        optionen = []
        for treffer in ergebnis.treffer:
            kopf = (f"{treffer.buch.autor} – {treffer.buch.titel} · "
                    f"{treffer.kapitel.nr}. {treffer.kapitel.titel} · Absatz {treffer.absatz_index + 1}")
            text = Text(kopf + "\n", style="bold")
            text.append(self._hervorheben(treffer.snippet(), ergebnis.terme))
            optionen.append(Option(text))
        liste.add_options(optionen)
        if not ergebnis.treffer:
            self._status(f"Keine Treffer ({ergebnis.buecher_durchsucht} Buch/Bücher durchsucht).")
            return
        mehr = f" – Anzeige bei {len(ergebnis.treffer)} abgebrochen, Suche eingrenzen" if ergebnis.abgeschnitten else ""
        self._status(f"{len(ergebnis.treffer)} Treffer{mehr}. Enter öffnet, Esc schließt.")
        # Ohne vorgewaehlte Zeile tut Enter in der Liste nichts.
        liste.highlighted = 0
        liste.focus()

    @staticmethod
    def _hervorheben(snippet: str, terme: list[str]) -> Text:
        text = Text(snippet)
        klein = snippet.lower()
        for term in terme:
            start = klein.find(term)
            while start != -1:
                text.stylize("bold reverse", start, start + len(term))
                start = klein.find(term, start + len(term))
        return text

    def _status(self, meldung: str) -> None:
        self.query_one("#such-status", Static).update(meldung)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if 0 <= event.option_index < len(self._treffer):
            self.dismiss(self._treffer[event.option_index])
