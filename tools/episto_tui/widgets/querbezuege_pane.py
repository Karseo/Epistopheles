from __future__ import annotations
from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option
from episto_tui import library
from episto_tui.models import Buch, Kapitel
from episto_tui.widgets.sprung import SpringeZu


class QuerbezuegePane(VerticalScroll):
    def compose(self):
        # markup=False: Inhalte stammen aus Daten (Zitate wie "[LdF]"), kein Markup.
        yield Static("", id="inhalt", markup=False)
        yield Static("", id="sprung-titel", markup=False)
        yield OptionList(id="sprung")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._ziele: list[tuple[Buch, Kapitel]] = []

    def on_mount(self) -> None:
        self.query_one("#sprung-titel", Static).display = False
        self.query_one("#sprung", OptionList).display = False

    def lade_kapitel(self, buch: Buch, kapitel: Kapitel) -> None:
        bezuege = library.read_querbezuege(buch)
        anzeige = self.query_one("#inhalt", Static)
        liste = self.query_one("#sprung", OptionList)
        liste.clear_options()
        self._ziele = []
        self.query_one("#sprung-titel", Static).display = False
        liste.display = False
        if not bezuege:
            anzeige.update("Keine Querverweise für dieses Werk erfasst.")
            return
        zeilen = [
            f"**{b.get('autor', '')}** — {b.get('titel', '')}  ({b.get('relation', '')})\n{b.get('notiz', '')}\n"
            for b in bezuege
        ]
        anzeige.update("\n".join(zeilen))

        # Nur Verweise auf Werke, die in der Bibliothek liegen, sind springbar.
        buecher = library.discover_books(library.root_von(buch))
        optionen = []
        for b in bezuege:
            ziel_buch = library.finde_buch_fuer_ziel(buecher, str(b.get("ziel", "")))
            if ziel_buch is None or ziel_buch.pfad == buch.pfad:
                continue
            kapitel_liste = library.list_chapters(ziel_buch)
            if not kapitel_liste:
                continue
            self._ziele.append((ziel_buch, kapitel_liste[0]))
            optionen.append(Option(Text(
                f"{ziel_buch.autor} – {ziel_buch.titel}  ({b.get('relation', '')})  → öffnen")))
        if optionen:
            liste.add_options(optionen)
            self.query_one("#sprung-titel", Static).update("In der Bibliothek vorhanden (Enter öffnet das Werk):")
            self.query_one("#sprung-titel", Static).display = True
            liste.display = True

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if 0 <= event.option_index < len(self._ziele):
            buch, kapitel = self._ziele[event.option_index]
            self.post_message(SpringeZu(buch, kapitel))
