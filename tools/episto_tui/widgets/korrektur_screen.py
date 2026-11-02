from __future__ import annotations
import json
from pathlib import Path
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Static, TextArea
from episto_tui import korrektur, library
from episto_tui.models import Buch


class _Knopf(Button):
    """Button ohne die 2 Spalten Luft, die Textual an jede Beschriftung haengt
    (siehe TippKnopf): sonst passt die Knopfreihe nicht in 45 Spalten."""

    def get_content_width(self, container, viewport) -> int:
        return max((len(zeile) for zeile in self.label.plain.splitlines()), default=0)


class KorrekturScreen(ModalScreen["tuple | None"]):
    """Abarbeiten der korrektur-Marken (Taste k im Lesemodus markiert, Taste x
    oeffnet diesen Dialog).

    Oben der fehlerhafte deutsche Absatz als Arbeitsfeld, darunter ein Fenster
    des englischen Originals. "Vorschlag" fragt das lokale Sprachmodell (Ollama)
    im Hintergrund; das Ergebnis landet im Arbeitsfeld, wird geprueft und kann
    von Hand weiter bearbeitet werden. "Uebernehmen" schreibt NUR diesen Absatz
    ins Kapitel (mit Sicherung) und entfernt die Marke. Ohne Ollama oder ohne
    englisches Original (Handy) bleibt das Korrigieren von Hand."""

    BINDINGS = [
        Binding("escape", "schliessen", "Schließen"),
        Binding("ctrl+s", "uebernehmen", "Übernehmen"),
        Binding("ctrl+l", "vorschlag", "Vorschlag"),
        Binding("ctrl+r", "marke_weg", "Marke weg"),  # ctrl+d ist im TextArea "Zeichen loeschen"
    ]

    DEFAULT_CSS = """
    KorrekturScreen { align: center middle; }
    KorrekturScreen #korr-box { width: 100%; height: 100%; padding: 0 1; background: $surface; }
    KorrekturScreen #korr-kopf { height: auto; text-style: bold; }
    KorrekturScreen .korr-titel { height: auto; color: $text-muted; }
    KorrekturScreen TextArea { height: 1fr; }
    KorrekturScreen #korr-status { height: auto; }
    KorrekturScreen Horizontal { height: auto; }
    KorrekturScreen _Knopf { min-width: 4; margin-right: 1; }
    KorrekturScreen Checkbox { height: auto; }
    """

    def __init__(self, root: Path, aktuelles_buch: Buch | None = None) -> None:
        super().__init__()
        self.root_pfad = root
        self.aktuelles_buch = aktuelles_buch
        self._marken: list[korrektur.OffeneMarke] = []
        self._i = 0
        self._en: list[str] | None = None
        self._en_fehler = ""
        self._en_genau = True
        self._fenster = (0, 0)
        self._letzte_stelle: tuple | None = None
        self._cache_en: dict[tuple, tuple] = {}
        self._angefragt = 0

    # --- Aufbau ----------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical(id="korr-box"):
            yield Static("", id="korr-kopf")
            if self.aktuelles_buch is not None:
                yield Checkbox("Ganze Bibliothek", id="ganze-bibliothek")
            yield Static("Deutsch (bearbeiten):", classes="korr-titel")
            yield TextArea("", id="korr-de", soft_wrap=True)
            yield Static("", id="korr-en-titel", classes="korr-titel")
            yield TextArea("", id="korr-en", read_only=True, soft_wrap=True)
            yield Static("", id="korr-status")
            with Horizontal():
                yield _Knopf("◀", id="knopf-zurueck", compact=True)
                yield _Knopf("▶", id="knopf-vor", compact=True)
                yield _Knopf("Original", id="knopf-original", compact=True)
            # Englisches Fenster verschieben: einzeln oder in Zehnerschritten
            # (bei der Naeherung ueber das ganze Buch liegt man oft ein paar
            # Absaetze daneben).
            with Horizontal():
                yield _Knopf("EN−10", id="knopf-en-hoch10", compact=True)
                yield _Knopf("EN−1", id="knopf-en-hoch", compact=True)
                yield _Knopf("EN+1", id="knopf-en-runter", compact=True)
                yield _Knopf("EN+10", id="knopf-en-runter10", compact=True)
            with Horizontal():
                yield _Knopf("Vorschlag", id="knopf-vorschlag", compact=True)
                yield _Knopf("Übernehmen", id="knopf-uebernehmen", compact=True, variant="success")
                yield _Knopf("Marke weg", id="knopf-marke-weg", compact=True)
                yield _Knopf("Schließen", id="knopf-schliessen", compact=True)

    def on_mount(self) -> None:
        self._lade_marken()
        self.query_one("#korr-de", TextArea).focus()

    def _lade_marken(self) -> None:
        ganze = self.query("#ganze-bibliothek")
        nur_buch = self.aktuelles_buch is not None and not (ganze and ganze.first(Checkbox).value)
        buecher = [self.aktuelles_buch] if nur_buch else library.discover_books(self.root_pfad)
        self._marken = korrektur.sammle_offene_marken(buecher)
        self._i = 0
        self._zeige()

    # --- Anzeige ---------------------------------------------------------------

    @property
    def _marke(self) -> korrektur.OffeneMarke | None:
        return self._marken[self._i] if 0 <= self._i < len(self._marken) else None

    def _status(self, meldung: str) -> None:
        self.query_one("#korr-status", Static).update(meldung)

    def _lade_englisch(self, marke: korrektur.OffeneMarke) -> None:
        """Englische Absaetze und Startfenster fuer diese Marke (je Marke im
        Zwischenspeicher, damit Hin- und Herblaettern nichts neu liest)."""
        schluessel = (marke.buch.pfad, marke.highlight.datei, marke.absatz_index)
        if schluessel not in self._cache_en:
            if marke.absatz_index is None:
                self._cache_en[schluessel] = (None, "Absatz nicht auffindbar", True, (0, 0))
            else:
                try:
                    anker = korrektur.englischer_anker(marke.buch, marke.highlight.datei, marke.absatz_index)
                    self._cache_en[schluessel] = (anker.absaetze, "", anker.genau, anker.fenster)
                except (OSError, ValueError) as exc:
                    self._cache_en[schluessel] = (None, f"{type(exc).__name__}: {exc}", True, (0, 0))
        self._en, self._en_fehler, self._en_genau, self._fenster = self._cache_en[schluessel]

    def _zeige(self) -> None:
        de = self.query_one("#korr-de", TextArea)
        en = self.query_one("#korr-en", TextArea)
        kopf = self.query_one("#korr-kopf", Static)
        marke = self._marke
        if marke is None:
            kopf.update("Keine offenen Korrektur-Marken." if not self._marken else "Alle Marken abgearbeitet.")
            de.load_text("")
            en.load_text("")
            self.query_one("#korr-en-titel", Static).update("")
            self._status("Im Lesemodus markiert die Taste k einen Absatz zur Korrektur.")
            return
        kopf.update(f"Korrektur {self._i + 1}/{len(self._marken)} · {marke.buch.autor} – {marke.buch.titel}"
                    f" · {marke.kapitel.nr}. {marke.kapitel.titel}"
                    + (f" · Absatz {marke.absatz_index + 1}" if marke.absatz_index is not None else ""))
        de.load_text(marke.absatz)
        self._lade_englisch(marke)
        if marke.absatz_index is None:
            self._status("Absatz nicht mehr auffindbar (Text wurde geändert). „Marke weg“ entfernt die Marke.")
        else:
            self._status("")
        self._zeige_englisch()

    def _zeige_englisch(self) -> None:
        en = self.query_one("#korr-en", TextArea)
        titel = self.query_one("#korr-en-titel", Static)
        marke = self._marke
        if marke is None:
            return
        if self._en is None:
            titel.update("Englisches Original:")
            en.load_text(f"Nicht verfügbar ({self._en_fehler}).\nTypisch auf dem Handy: der Ordner en wird nicht synchronisiert.")
            return
        start, ende = self._fenster
        art = "" if self._en_genau else " – Näherung über das ganze Buch, bitte mit EN−/EN+ zurechtrücken"
        titel.update(f"Englisches Original, Absätze {start + 1}–{ende} von {len(self._en)}{art}:")
        en.load_text("\n\n".join(self._en[start:ende]))

    # --- Aktionen ---------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        aktion = {
            "knopf-zurueck": lambda: self._gehe(-1),
            "knopf-vor": lambda: self._gehe(+1),
            "knopf-en-hoch10": lambda: self._verschiebe(-10),
            "knopf-en-hoch": lambda: self._verschiebe(-1),
            "knopf-en-runter": lambda: self._verschiebe(+1),
            "knopf-en-runter10": lambda: self._verschiebe(+10),
            "knopf-original": self._original,
            "knopf-vorschlag": self.action_vorschlag,
            "knopf-uebernehmen": self.action_uebernehmen,
            "knopf-marke-weg": self.action_marke_weg,
            "knopf-schliessen": self.action_schliessen,
        }.get(event.button.id)
        if aktion:
            aktion()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        event.stop()
        self._lade_marken()

    def _gehe(self, schritt: int) -> None:
        if self._marken:
            self._i = (self._i + schritt) % len(self._marken)
            self._zeige()

    def _verschiebe(self, schritte: int) -> None:
        if self._en is not None and self._marke is not None:
            self._fenster = korrektur.verschiebe_fenster(self._fenster, schritte, len(self._en))
            marke = self._marke
            schluessel = (marke.buch.pfad, marke.highlight.datei, marke.absatz_index)
            absaetze, fehler, genau, _ = self._cache_en[schluessel]
            self._cache_en[schluessel] = (absaetze, fehler, genau, self._fenster)
            self._zeige_englisch()

    def _original(self) -> None:
        marke = self._marke
        if marke is not None:
            self.query_one("#korr-de", TextArea).load_text(marke.absatz)
            self._status("Ursprünglicher Text wiederhergestellt.")

    def action_vorschlag(self) -> None:
        marke = self._marke
        if marke is None or marke.absatz_index is None:
            return
        if self._en is None:
            self._status("Ohne englisches Original kein Vorschlag – von Hand korrigieren.")
            return
        self._angefragt += 1
        self._status(f"Vorschlag wird geholt ({korrektur.modell()}) …")
        englisch = korrektur.fenster_text(self._en, self._fenster)
        self._hole_vorschlag(self._angefragt, marke, marke.absatz, englisch)

    # Thread-Worker: der Aufruf dauert bei einem 32B-Modell Sekunden bis Minuten.
    @work(thread=True, exclusive=True, group="korrektur-llm")
    def _hole_vorschlag(self, nummer: int, marke, absatz: str, englisch: str) -> None:
        try:
            try:
                vorschlag = korrektur.korrigiere(absatz, englisch, korrektur.modell())
            except Exception:           # ein Wiederholungsversuch, wie im Kommandozeilenlauf
                vorschlag = korrektur.korrigiere(absatz, englisch, korrektur.modell())
            fehler = ""
        except Exception as exc:
            vorschlag, fehler = "", f"{type(exc).__name__}: {exc}"
        self.app.call_from_thread(self._vorschlag_da, nummer, marke, absatz, vorschlag, fehler)

    def _vorschlag_da(self, nummer: int, marke, absatz: str, vorschlag: str, fehler: str) -> None:
        # Veraltete Antwort (inzwischen andere Marke oder neuere Anfrage): verwerfen.
        if nummer != self._angefragt or marke is not self._marke:
            return
        if fehler:
            self._status(f"Kein Vorschlag: {fehler}\nIst Ollama gestartet? Sonst von Hand korrigieren.")
            return
        self.query_one("#korr-de", TextArea).load_text(vorschlag)
        warnungen = korrektur.pruefe_vorschlag(absatz, vorschlag)
        if warnungen:
            self._status("Vorschlag eingesetzt – bitte prüfen:\n" + "\n".join(f"· {w}" for w in warnungen))
        else:
            self._status("Vorschlag eingesetzt. Prüfen, bei Bedarf ändern, dann Übernehmen (Strg+S).")

    def action_uebernehmen(self) -> None:
        marke = self._marke
        if marke is None:
            return
        neu = self.query_one("#korr-de", TextArea).text.strip()
        if marke.absatz_index is None:
            self._status("Absatz nicht mehr auffindbar – nur „Marke weg“ ist möglich.")
            return
        if not neu:
            self._status("Der Absatz wäre leer – nicht übernommen.")
            return
        if neu == marke.absatz.strip():
            self._status("Text unverändert – nichts zu übernehmen. „Marke weg“ entfernt nur die Marke.")
            return
        try:
            index = korrektur.wende_an(marke, neu)
        except (ValueError, OSError) as exc:
            self._status(f"Nicht übernommen: {exc}")
            return
        self._letzte_stelle = (marke.buch, marke.kapitel, index)
        self._entferne_aktuelle(f"Absatz {index + 1} in „{marke.kapitel.titel}“ übernommen.")

    def action_marke_weg(self) -> None:
        marke = self._marke
        if marke is None:
            return
        korrektur.entferne_marke(marke)
        self._entferne_aktuelle("Marke entfernt (Text unverändert).")

    def _entferne_aktuelle(self, meldung: str) -> None:
        del self._marken[self._i]
        if self._i >= len(self._marken):
            self._i = 0
        self._zeige()
        # _zeige() setzt den Status zurueck; die Rueckmeldung zur Aktion soll bleiben.
        self._status(meldung if self._marken else meldung + "\nKeine weiteren Marken.")

    def action_schliessen(self) -> None:
        # Ergebnis: die zuletzt geaenderte Stelle, damit die App den Text neu laedt.
        self.dismiss(self._letzte_stelle)
