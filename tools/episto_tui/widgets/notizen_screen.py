from __future__ import annotations
from pathlib import Path
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Input, OptionList, Static
from textual.widgets.option_list import Option
from episto_tui import notizen
from episto_tui.models import Buch

_MAX_ANZEIGE = 300
_FARBE = {"gelb": "yellow", "rosa": "magenta", "blau": "blue", "korrektur": "red"}


class NotizenScreen(ModalScreen["notizen.Notiz | None"]):
    """Liste aller Kommentare und Highlights. Tippen filtert sofort (auch nach
    Art oder Farbe: "kommentar", "gelb", "korrektur"); Enter springt an die
    Textstelle."""

    BINDINGS = [Binding("escape", "abbrechen", "Schließen")]

    DEFAULT_CSS = """
    NotizenScreen { align: center middle; }
    NotizenScreen #notizen-box { width: 100%; height: 100%; padding: 0 1; background: $surface; }
    NotizenScreen #notizen-status { height: auto; color: $text-muted; }
    NotizenScreen OptionList { height: 1fr; }
    NotizenScreen Checkbox { height: auto; }
    """

    def __init__(self, root: Path, aktuelles_buch: Buch | None = None) -> None:
        super().__init__()
        self.root_pfad = root
        self.aktuelles_buch = aktuelles_buch
        self._alle: list[notizen.Notiz] = []
        self._angezeigt: list[notizen.Notiz] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="notizen-box"):
            yield Input(placeholder='Filtern: Wörter, "kommentar", "gelb", "korrektur" …', id="notizen-filter")
            if self.aktuelles_buch is not None:
                yield Checkbox(f"Nur in „{self.aktuelles_buch.titel}“", id="nur-buch")
            yield Static("", id="notizen-status")
            yield OptionList(id="notizen-liste")

    def on_mount(self) -> None:
        self._lade()
        self.query_one("#notizen-filter", Input).focus()

    def _lade(self) -> None:
        nur_buch = None
        kasten = self.query("#nur-buch")
        if kasten and kasten.first(Checkbox).value:
            nur_buch = self.aktuelles_buch
        self._alle = notizen.sammle_notizen(self.root_pfad, nur_buch)
        self._zeige()

    def _zeige(self) -> None:
        eingabe = self.query_one("#notizen-filter", Input).value
        treffer = notizen.filtere(self._alle, eingabe)
        self._angezeigt = treffer[:_MAX_ANZEIGE]
        liste = self.query_one("#notizen-liste", OptionList)
        liste.clear_options()
        optionen = []
        for n in self._angezeigt:
            kopf = Text(f"{n.buch.autor} – {n.buch.titel} · {n.kapitel.nr}. {n.kapitel.titel}"
                        f" · Absatz {n.absatz_index + 1}\n", style="bold")
            if n.art == "Kommentar":
                kopf.append("\U0001f4ac " + " ".join(n.text.split()))
                kopf.append("\n   zu: " + " ".join(n.absatz_anfang.split())[:80], style="dim")
            else:
                kopf.append("▌ ", style=_FARBE.get(n.marke, "white"))
                kopf.append(f"{n.marke}: ", style="bold")
                kopf.append(" ".join(n.absatz_anfang.split())[:100], style="dim")
            optionen.append(Option(kopf))
        liste.add_options(optionen)
        if self._angezeigt:
            liste.highlighted = 0
        mehr = f" (erste {_MAX_ANZEIGE} angezeigt)" if len(treffer) > _MAX_ANZEIGE else ""
        if not self._alle:
            meldung = "Noch keine Kommentare oder Highlights."
        elif not treffer:
            meldung = "Keine passende Notiz."
        else:
            meldung = f"{len(treffer)} von {len(self._alle)} Notizen{mehr}. Tab/↓ wählt, Enter öffnet, Esc schließt."
        self.query_one("#notizen-status", Static).update(meldung)

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self._zeige()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if self._angezeigt:
            self.query_one("#notizen-liste", OptionList).focus()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        event.stop()
        self._lade()

    def action_abbrechen(self) -> None:
        self.dismiss(None)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if 0 <= event.option_index < len(self._angezeigt):
            self.dismiss(self._angezeigt[event.option_index])
