from __future__ import annotations
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button

# Reihenfolge = Reihenfolge in der Leiste. Alle Knoepfe existieren von Anfang
# an; je Kontext werden nur die passenden sichtbar geschaltet (kein Neuaufbau
# der Leiste, also keine Wettlaeufe mit noch nicht entfernten Widgets).
_KNOEPFE = [
    ("baum", "Baum"),
    ("zurueck", "\u25c0"),
    ("weiter", "\u25b6"),
    ("suche", "Suche"),
    ("notizen", "Notiz"),
    ("korr", "Korr"),
    ("speed", "Speed"),
    ("bearbeiten", "Edit"),
    ("gelb", "Gelb"),
    ("rosa", "Rosa"),
    ("blau", "Blau"),
    ("korrektur", "K"),
    ("kommentar", "Komm"),
    ("loeschen", "Lösch"),
    ("speichern", "Speichern"),
    ("verwerfen", "Verwerfen"),
]

# Zwei Zeilen: oben Navigation, unten Bearbeiten. Zusammen passen die Knoepfe
# nicht mehr in die 45-Spalten-Handybreite; eine Zeile ohne sichtbaren Knopf
# wird ausgeblendet, die Leiste bleibt dann bei einer Zeile Hoehe.
_NAVIGATION = ("baum", "zurueck", "weiter", "suche", "notizen", "korr", "speed")

KONTEXTE: dict[str, frozenset[str]] = {
    "lesen": frozenset({"baum", "zurueck", "weiter", "suche", "notizen", "korr", "speed", "bearbeiten", "gelb", "rosa", "blau", "korrektur", "kommentar", "loeschen"}),
    "bearbeiten": frozenset({"speichern", "verwerfen"}),
    "felder": frozenset({"baum", "zurueck", "weiter", "suche", "notizen", "korr", "speed", "speichern"}),
    "nur_baum": frozenset({"baum", "suche", "notizen", "korr", "speed"}),
}


class TippKnopf(Button, can_focus=False):
    """Knopf der Aktionsleiste. Nimmt bewusst keinen Fokus: der zuletzt
    angetippte Absatz (ReaderPane) und ein offenes Kommentarfeld muessen
    erhalten bleiben, wenn man auf einen Knopf tippt."""

    def get_content_width(self, container, viewport) -> int:
        # Textuals Button haengt an jede Beschriftung fest 2 Spalten Luft an
        # (Button.get_content_width: "+ 2"). Mit dem zusaetzlichen Korr-Knopf
        # passen die acht Lese-Knoepfe in der 45-Spalten-Handybreite sonst
        # nicht mehr in die Leiste (6+6+6+6+6+6+6+7 = 49 > 45). Wir messen
        # daher nur die Beschriftung; den Mindestabstand setzt min-width.
        return max((len(zeile) for zeile in self.label.plain.splitlines()), default=0)


class _Zeile(Horizontal):
    DEFAULT_CSS = """
    _Zeile {
        height: 1;
        width: 1fr;
        overflow-x: auto;
        scrollbar-size-horizontal: 0;
    }
    _Zeile TippKnopf { min-width: 5; }
    """


class Aktionsleiste(Vertical):
    DEFAULT_CSS = """
    Aktionsleiste {
        height: auto;
        width: 1fr;
    }
    """

    class AktionGewaehlt(Message):
        def __init__(self, aktion: str) -> None:
            self.aktion = aktion
            super().__init__()

    def __init__(self) -> None:
        super().__init__(id="aktionsleiste")
        self.kontext: str | None = None

    def compose(self):
        with _Zeile(id="zeile-navigation"):
            for aktion, beschriftung in _KNOEPFE:
                if aktion in _NAVIGATION:
                    yield TippKnopf(beschriftung, compact=True, name=aktion, id=f"knopf-{aktion}")
        with _Zeile(id="zeile-bearbeiten"):
            for aktion, beschriftung in _KNOEPFE:
                if aktion not in _NAVIGATION:
                    yield TippKnopf(beschriftung, compact=True, name=aktion, id=f"knopf-{aktion}")

    def on_mount(self) -> None:
        # Hat die App den Kontext schon vor dem Einhaengen gesetzt, gilt der.
        self._wende_kontext_an()

    def setze_kontext(self, kontext: str) -> None:
        self.kontext = kontext
        self._wende_kontext_an()

    def _wende_kontext_an(self) -> None:
        sichtbar = KONTEXTE[self.kontext or "nur_baum"]
        for knopf in self.query(TippKnopf):
            knopf.display = knopf.name in sichtbar
        for zeile in self.query(_Zeile):
            zeile.display = any(k.display for k in zeile.query(TippKnopf))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.post_message(self.AktionGewaehlt(event.button.name))
