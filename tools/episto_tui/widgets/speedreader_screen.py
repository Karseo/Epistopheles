from __future__ import annotations
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static
from episto_tui import library, speedreader
from episto_tui.models import Buch, Kapitel, Tag
from episto_tui.widgets.aktionsleiste import TippKnopf

# Halbe Breite der Wortzeile: der Erkennungspunkt steht in Spalte HALB, die Zeile
# ist 2*HALB+1 breit und passt damit auch in 45 Handy-Spalten.
HALB = 18


class SpeedreaderScreen(ModalScreen[None]):
    """Schnellleser fuer die KI-Felder eines Kapitels: ein Wort nach dem anderen
    an fester Stelle (Erkennungspunkt rot), Abschnitte mit Ueberschrift,
    Satzzeichen und lange Woerter bekommen mehr Zeit. Gedacht als Ueberblick
    vor dem Originaltext, nicht als Ersatz dafuer."""

    BINDINGS = [
        Binding("escape", "schliessen", "Schließen"),
        Binding("space", "pause", "Start/Pause"),
        Binding("up", "schneller", "Schneller (+50)"),
        Binding("down", "langsamer", "Langsamer (−50)"),
        Binding("plus", "fein_schneller", "+5"),
        Binding("minus", "fein_langsamer", "−5"),
        Binding("left", "satz_zurueck", "Satz zurück"),
        Binding("right", "satz_vor", "Satz vor"),
    ]

    DEFAULT_CSS = """
    SpeedreaderScreen { align: center middle; }
    SpeedreaderScreen #sr-box { width: 100%; height: 100%; padding: 0 1; background: $surface; }
    SpeedreaderScreen #sr-kopf { height: auto; text-style: bold; }
    SpeedreaderScreen #sr-mitte { height: 1fr; align: center middle; }
    SpeedreaderScreen #sr-wort { width: 37; height: 3; }
    SpeedreaderScreen #sr-status { height: auto; color: $text-muted; }
    SpeedreaderScreen Horizontal { height: auto; }
    SpeedreaderScreen TippKnopf { min-width: 4; margin-right: 1; }
    """

    def __init__(self, buch: Buch, kapitel: Kapitel, tag: Tag | None) -> None:
        super().__init__()
        self.buch = buch
        self.kapitel = kapitel
        self._woerter, self._abschnitte = speedreader.baue_woerter(tag) if tag is not None else ([], [])
        self._i = 0
        self._laeuft = False
        self._timer = None
        self._wpm = speedreader.begrenze_tempo(
            library.lade_zustand().get("speedreader_wpm", speedreader.STANDARD_WPM))

    # --- Aufbau ----------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical(id="sr-box"):
            yield Static(f"{self.buch.autor} – {self.buch.titel} · {self.kapitel.nr}. {self.kapitel.titel}",
                         id="sr-kopf", markup=False)
            with Vertical(id="sr-mitte"):
                yield Static("", id="sr-wort", markup=False)
            yield Static("", id="sr-status", markup=False)
            with Horizontal():
                yield TippKnopf("◀◀", name="abschnitt_zurueck", id="knopf-abschnitt-zurueck", compact=True)
                yield TippKnopf("◀ Satz", name="satz_zurueck", id="knopf-satz-zurueck", compact=True)
                yield TippKnopf("Start", name="pause", id="knopf-pause", compact=True)
                yield TippKnopf("Satz ▶", name="satz_vor", id="knopf-satz-vor", compact=True)
                yield TippKnopf("▶▶", name="abschnitt_vor", id="knopf-abschnitt-vor", compact=True)
            with Horizontal():
                yield TippKnopf("−50", name="langsamer", id="knopf-langsamer", compact=True)
                yield TippKnopf("−5", name="fein_langsamer", id="knopf-fein-langsamer", compact=True)
                yield TippKnopf("+5", name="fein_schneller", id="knopf-fein-schneller", compact=True)
                yield TippKnopf("+50", name="schneller", id="knopf-schneller", compact=True)
                yield TippKnopf("Schließen", name="schliessen", id="knopf-schliessen", compact=True)

    def on_mount(self) -> None:
        self._zeige()

    # --- Anzeige ---------------------------------------------------------------

    def _zeige(self) -> None:
        wort_widget = self.query_one("#sr-wort", Static)
        status = self.query_one("#sr-status", Static)
        pause_knopf = self.query_one("#knopf-pause", TippKnopf)
        if not self._woerter:
            wort_widget.update("")
            status.update("Für dieses Kapitel gibt es keine KI-Felder (noch nicht getaggt).")
            return
        wort = self._woerter[self._i]
        zeile = Text()
        zeile.append(" " * HALB + "│\n", style="dim")
        zeile.append_text(speedreader.render_wort(wort, HALB))
        zeile.append("\n" + " " * HALB + "│", style="dim")
        wort_widget.update(zeile)
        rest = int(round(speedreader.restdauer(self._woerter, self._i, self._wpm)))
        zustand = "läuft" if self._laeuft else ("Ende" if self._ist_am_ende() else "Pause")
        status.update(
            f"{self._abschnitte[wort.abschnitt]} · Wort {self._i + 1}/{len(self._woerter)} · "
            f"{self._wpm} Wörter/min · ~{rest // 60}:{rest % 60:02d} übrig · {zustand}")
        pause_knopf.label = "Pause" if self._laeuft else ("Neu" if self._ist_am_ende() else "Start")

    def _ist_am_ende(self) -> bool:
        return bool(self._woerter) and self._i >= len(self._woerter) - 1

    # --- Ablauf ----------------------------------------------------------------

    def _plane(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if not self._laeuft or not self._woerter:
            return
        if self._i < len(self._woerter) - 1:
            self._timer = self.set_timer(speedreader.dauer(self._woerter[self._i], self._wpm), self._tick)
        else:
            self._laeuft = False              # per Sprung ans Ende gelandet: Lauf beenden
            self._zeige()

    def _tick(self) -> None:
        self._timer = None
        if not self._laeuft:
            return
        if self._i < len(self._woerter) - 1:
            self._i += 1
        if self._i >= len(self._woerter) - 1:
            self._laeuft = False
        self._zeige()
        self._plane()

    def _springe(self, ziel: int) -> None:
        if self._woerter:
            self._i = min(max(ziel, 0), len(self._woerter) - 1)
            self._zeige()
            self._plane()          # Wartezeit des neuen Worts beginnt neu

    # --- Aktionen ---------------------------------------------------------------

    def on_button_pressed(self, event) -> None:
        event.stop()
        methode = getattr(self, f"action_{event.button.name}", None)
        if methode is not None:
            methode()

    def action_pause(self) -> None:
        if not self._woerter:
            return
        if not self._laeuft and self._ist_am_ende():
            self._i = 0                       # nach dem Ende von vorn beginnen
        self._laeuft = not self._laeuft
        self._zeige()
        self._plane()

    def _setze_tempo(self, wpm: int) -> None:
        self._wpm = speedreader.begrenze_tempo(wpm)
        zustand = library.lade_zustand()
        zustand["speedreader_wpm"] = self._wpm
        library.speichere_zustand(zustand)
        self._zeige()
        self._plane()

    def action_schneller(self) -> None:
        self._setze_tempo(self._wpm + speedreader.WPM_SCHRITT)

    def action_langsamer(self) -> None:
        self._setze_tempo(self._wpm - speedreader.WPM_SCHRITT)

    def action_fein_schneller(self) -> None:
        self._setze_tempo(self._wpm + speedreader.WPM_FEIN)

    def action_fein_langsamer(self) -> None:
        self._setze_tempo(self._wpm - speedreader.WPM_FEIN)

    def action_satz_zurueck(self) -> None:
        if self._woerter:
            self._springe(speedreader.voriger_satzanfang(self._woerter, self._i))

    def action_satz_vor(self) -> None:
        if self._woerter:
            self._springe(speedreader.naechster_satzanfang(self._woerter, self._i))

    def action_abschnitt_zurueck(self) -> None:
        if self._woerter:
            self._springe(speedreader.voriger_abschnitt(self._woerter, self._i))

    def action_abschnitt_vor(self) -> None:
        if self._woerter:
            self._springe(speedreader.naechster_abschnitt(self._woerter, self._i))

    def action_schliessen(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._laeuft = False
        self.dismiss(None)
