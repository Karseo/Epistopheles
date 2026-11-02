"""Alle eigenen Notizen (Kommentare und Highlights) der Bibliothek als flache
Liste, durchsuchbar und mit Sprung an die Textstelle."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from episto_tui import library, annotate
from episto_tui.models import Buch, Kapitel


@dataclass
class Notiz:
    art: str            # "Kommentar" oder "Highlight"
    buch: Buch
    kapitel: Kapitel
    absatz_index: int
    absatz_anfang: str
    text: str           # Kommentartext; bei Highlights leer
    marke: str          # Farbe (Highlight) bzw. Erstelldatum (Kommentar)

    def suchtext(self) -> str:
        # Art und Farbe zaehlen mit: "gelb" oder "kommentar" im Filter genuegt.
        teile = [self.art, self.marke, self.text, self.absatz_anfang,
                 self.buch.autor, self.buch.titel, self.kapitel.titel]
        return " ".join(teile).casefold()

    def sprungabsatz(self) -> int:
        """Absatzindex im AKTUELLEN Kapiteltext (der gespeicherte Index kann nach
        Textaenderungen verrutscht sein, dann zaehlt der Absatzanfang)."""
        try:
            text = library.read_chapter_text(self.buch, self.kapitel.datei)
        except OSError:
            return self.absatz_index
        gefunden = annotate.locate_paragraph(
            annotate.split_paragraphs(text), self.absatz_index, self.absatz_anfang)
        return self.absatz_index if gefunden is None else gefunden


def sammle_notizen(root: Path, nur_buch: Buch | None = None) -> list[Notiz]:
    """Alle Kommentare und Highlights, nach Buch, Kapitel und Absatz sortiert.
    Eintraege zu nicht mehr vorhandenen Kapiteln werden uebersprungen."""
    notizen: list[Notiz] = []
    for buch in ([nur_buch] if nur_buch is not None else library.discover_books(root)):
        kommentare = library.read_alle_kommentare(buch)
        highlights = library.read_alle_highlights(buch)
        if not kommentare and not highlights:
            continue
        kapitel_nach_datei = {k.datei: k for k in library.list_chapters(buch)}
        for k in kommentare:
            kapitel = kapitel_nach_datei.get(k.datei)
            if kapitel is not None:
                notizen.append(Notiz("Kommentar", buch, kapitel, k.absatz_index,
                                     k.absatz_anfang, k.text, k.erstellt))
        for h in highlights:
            kapitel = kapitel_nach_datei.get(h.datei)
            if kapitel is not None:
                notizen.append(Notiz("Highlight", buch, kapitel, h.absatz_index,
                                     h.absatz_anfang, "", h.farbe))
    notizen.sort(key=lambda n: (n.buch.autor.casefold(), n.buch.titel.casefold(),
                                n.kapitel.nr, n.absatz_index, n.art))
    return notizen


def filtere(notizen: list[Notiz], eingabe: str) -> list[Notiz]:
    """Alle Woerter der Eingabe muessen in der Notiz vorkommen (ohne Beachtung
    der Gross-/Kleinschreibung)."""
    woerter = eingabe.casefold().split()
    return [n for n in notizen if all(w in n.suchtext() for w in woerter)]
