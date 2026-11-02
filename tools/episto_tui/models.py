from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Buch:
    autor: str
    titel: str
    pfad: Path


@dataclass
class Kapitel:
    nr: int
    titel: str
    datei: str


def _str_liste(wert) -> list[str]:
    """Macht aus einem JSON-Listenfeld eine saubere list[str]: None-Eintraege
    fallen weg, alles andere wird zu str. Ist der Wert gar keine Liste (null,
    String, Zahl aus einem kaputten LLM-Tagging-Lauf), ergibt das []."""
    if not isinstance(wert, list):
        return []
    return [str(x) for x in wert if x is not None]


@dataclass
class Tag:
    datei: str
    kapitel_nr: int
    titel: str
    woerter: int
    these: list[str] = field(default_factory=list)
    gegen: list[str] = field(default_factory=list)
    kern: list[str] = field(default_factory=list)
    def_: list[str] = field(default_factory=list)  # "def" ist ein Python-Schluesselwort
    beleg: list[str] = field(default_factory=list)
    zusammenfassung: str = ""

    @staticmethod
    def from_dict(d: dict) -> "Tag":
        return Tag(
            datei=d.get("datei", ""),
            kapitel_nr=d.get("kapitel_nr", 0),
            titel=d.get("titel", ""),
            woerter=d.get("woerter", 0),
            these=_str_liste(d.get("these", [])),
            gegen=_str_liste(d.get("gegen", [])),
            kern=_str_liste(d.get("kern", [])),
            def_=_str_liste(d.get("def", [])),
            beleg=_str_liste(d.get("beleg", [])),
            zusammenfassung=str(d.get("zusammenfassung") or ""),
        )

    def to_dict(self) -> dict:
        return {
            "datei": self.datei,
            "kapitel_nr": self.kapitel_nr,
            "titel": self.titel,
            "woerter": self.woerter,
            "these": list(self.these),
            "gegen": list(self.gegen),
            "kern": list(self.kern),
            "def": list(self.def_),
            "beleg": list(self.beleg),
            "zusammenfassung": self.zusammenfassung,
        }


@dataclass
class Kommentar:
    datei: str
    absatz_index: int
    absatz_anfang: str
    text: str
    erstellt: str
    # Stabile Kennung, damit zwei Geraete (Syncthing) denselben Kommentar
    # wiedererkennen und ihre Staende zusammenfuehren koennen. Altbestand hat
    # keine; add_kommentar() vergibt sie beim Anlegen.
    id: str = ""

    @staticmethod
    def from_dict(d: dict) -> "Kommentar":
        return Kommentar(
            datei=d.get("datei", ""),
            absatz_index=d.get("absatz_index", 0),
            absatz_anfang=d.get("absatz_anfang", ""),
            text=d.get("text", ""),
            erstellt=d.get("erstellt", ""),
            id=str(d.get("id") or ""),
        )

    def to_dict(self) -> dict:
        daten = {
            "datei": self.datei,
            "absatz_index": self.absatz_index,
            "absatz_anfang": self.absatz_anfang,
            "text": self.text,
            "erstellt": self.erstellt,
        }
        if self.id:
            daten["id"] = self.id
        return daten


@dataclass
class Highlight:
    datei: str
    absatz_index: int
    absatz_anfang: str
    farbe: str

    @staticmethod
    def from_dict(d: dict) -> "Highlight":
        return Highlight(
            datei=d.get("datei", ""),
            absatz_index=d.get("absatz_index", 0),
            absatz_anfang=d.get("absatz_anfang", ""),
            farbe=d.get("farbe", ""),
        )

    def to_dict(self) -> dict:
        return {
            "datei": self.datei,
            "absatz_index": self.absatz_index,
            "absatz_anfang": self.absatz_anfang,
            "farbe": self.farbe,
        }
