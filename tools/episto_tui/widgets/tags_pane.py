from __future__ import annotations
from textual.containers import ScrollableContainer
from textual.widgets import TextArea, Label, Static
from textual.binding import Binding
from episto_tui import library
from episto_tui.models import Buch, Kapitel, Tag

_LABELS = {
    "these": "These", "gegen": "Gegenpositionen", "kern": "Kernbegriffe",
    "def_": "Definitionen", "beleg": "Belege", "zusammenfassung": "Zusammenfassung",
}
# Einzige Textfeld-Angabe im Tag, die kein Zeilen-Listenfeld ist.
_TEXTFELD = "zusammenfassung"


class TagFelderPane(ScrollableContainer):
    """Editierbare Tag-Felder eines Kapitels. Mehrere Panes (Tabs) zeigen je
    einen Teil der Felder desselben Tags; jede speichert NUR ihre eigenen
    Felder in den frisch gelesenen Tag, damit sie die Felder der anderen Panes
    nicht mit veralteten Werten ueberschreibt."""

    FELDER: tuple[str, ...] = ()
    BINDINGS = [Binding("ctrl+s", "speichern", "Speichern")]

    def __init__(self) -> None:
        super().__init__()
        self.buch: Buch | None = None
        self.kapitel: Kapitel | None = None

    def compose(self):
        yield Static("", id="hinweis")
        for feld in self.FELDER:
            yield Label(_LABELS[feld])
            yield TextArea(id=f"feld-{feld}")

    def _platzhalter(self) -> Tag:
        return Tag(datei=self.kapitel.datei, kapitel_nr=self.kapitel.nr, titel=self.kapitel.titel, woerter=0)

    def lade_kapitel(self, buch: Buch, kapitel: Kapitel) -> None:
        self.buch = buch
        self.kapitel = kapitel
        gefundener_tag = library.read_tags(buch, kapitel.datei)
        hinweis = self.query_one("#hinweis", Static)
        if gefundener_tag is None:
            hinweis.update("Noch nicht getaggt — tools\\taggen.ps1 ausführen.")
            tag = self._platzhalter()
        else:
            hinweis.update("")
            tag = gefundener_tag
        for feld in self.FELDER:
            wert = getattr(tag, feld)
            self.query_one(f"#feld-{feld}", TextArea).text = wert if feld == _TEXTFELD else "\n".join(wert)

    def action_speichern(self) -> None:
        if self.buch is None or self.kapitel is None:
            return
        werte: dict[str, str | list[str]] = {}
        for feld in self.FELDER:
            text = self.query_one(f"#feld-{feld}", TextArea).text
            if feld == _TEXTFELD:
                werte[feld] = text
            else:
                werte[feld] = [zeile.strip() for zeile in text.splitlines() if zeile.strip()]
        tag = library.read_tags(self.buch, self.kapitel.datei)
        if tag is None:
            if not any(w.strip() if isinstance(w, str) else w for w in werte.values()):
                # Unberuehrter Platzhalter: NICHT schreiben. taggen.ps1 haelt
                # jede "datei" in tags.json fuer erledigt und wuerde das Kapitel
                # sonst bei allen kuenftigen Tagging-Laeufen still ueberspringen.
                self.notify("Nichts zu speichern — Kapitel noch nicht getaggt.")
                return
            tag = self._platzhalter()
        for feld, wert in werte.items():
            setattr(tag, feld, wert)
        library.write_tag(self.buch, tag)
        self.notify("Gespeichert.")


class TagsPane(TagFelderPane):
    FELDER = ("gegen", "kern", "def_")


class ZusammenfassungPane(TagFelderPane):
    """Tab "Fazit": Zusammenfassung, These und Belege eines Kapitels."""
    FELDER = (_TEXTFELD, "these", "beleg")

    # Die Zusammenfassung ist kurz (ein Satz, siehe neu-zusammenfassen.py): ihr
    # Feld waechst mit dem Inhalt, hoechstens auf 6 Textzeilen (+ Rahmen). Der
    # restliche Platz gehoert These und Belegen (height: 1fr aus TextArea).
    DEFAULT_CSS = """
    ZusammenfassungPane #feld-zusammenfassung { height: auto; min-height: 3; max-height: 8; }
    """
