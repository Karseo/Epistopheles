from __future__ import annotations
from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option
from episto_tui import library
from episto_tui.models import Buch, Kapitel
from episto_tui.widgets.sprung import SpringeZu


class StraengePane(VerticalScroll):
    def compose(self):
        # markup=False: Inhalte stammen aus Daten (Zitate wie "[LdF]"), kein Markup.
        yield Static("", id="inhalt", markup=False)
        # Sprungliste: dieselben Themen in den ANDEREN Kapiteln des Buchs.
        yield Static("", id="sprung-titel", markup=False)
        yield OptionList(id="sprung")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._ziele: list[Kapitel] = []
        self._buch: Buch | None = None

    def on_mount(self) -> None:
        self._verstecke_sprungliste()

    def _verstecke_sprungliste(self) -> None:
        self.query_one("#sprung-titel", Static).display = False
        self.query_one("#sprung", OptionList).display = False

    def lade_kapitel(self, buch: Buch, kapitel: Kapitel) -> None:
        self._buch = buch
        treffer = library.read_straenge_for_chapter(buch, kapitel.nr)
        anzeige = self.query_one("#inhalt", Static)
        liste = self.query_one("#sprung", OptionList)
        liste.clear_options()
        self._ziele = []
        self._verstecke_sprungliste()
        if not treffer:
            anzeige.update("Keine Themen für dieses Kapitel gefunden.")
            return
        zeilen = [f"## {t['strang']}\n{t['inhalt']}\n" for t in treffer]
        anzeige.update("\n".join(zeilen))

        kapitel_nach_nr = {k.nr: k for k in library.list_chapters(buch)}
        optionen = []
        for eintrag in library.read_straenge_uebersicht(buch, kapitel.nr):
            for nr, abschnitt in eintrag["andere"]:
                ziel = kapitel_nach_nr.get(nr)
                if ziel is None:
                    continue
                self._ziele.append(ziel)
                optionen.append(Option(Text(f"{eintrag['strang']}  →  {ziel.nr}. {ziel.titel}")))
        if optionen:
            liste.add_options(optionen)
            self.query_one("#sprung-titel", Static).update("Dasselbe Thema in anderen Kapiteln (Enter springt):")
            self.query_one("#sprung-titel", Static).display = True
            liste.display = True

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        if self._buch is not None and 0 <= event.option_index < len(self._ziele):
            self.post_message(SpringeZu(self._buch, self._ziele[event.option_index]))
