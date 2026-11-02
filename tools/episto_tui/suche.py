"""Volltextsuche ueber die Kapiteltexte (quelle\\*.md) der Bibliothek.

Bewusst ohne Qdrant/Ollama: laeuft ueberall, wo die TUI laeuft (auch unter
Termux), und liefert Fundstellen auf Absatzebene, damit die Oberflaeche direkt
dorthin springen kann. Die Absatzzaehlung ist dieselbe wie im ReaderPane
(annotate.split_paragraphs), der absatz_index passt also zur Anzeige."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from episto_tui import library
from episto_tui.annotate import split_paragraphs
from episto_tui.models import Buch, Kapitel

MAX_TREFFER = 200
MIN_TERM_LAENGE = 2
_SNIPPET_BREITE = 160
_TERM = re.compile(r'"([^"]+)"|(\S+)')


@dataclass
class Treffer:
    buch: Buch
    kapitel: Kapitel
    absatz_index: int
    absatz: str
    # Fundstelle (Zeichenposition) des ersten Suchbegriffs im Absatz.
    position: int = 0

    def snippet(self, breite: int = _SNIPPET_BREITE) -> str:
        """Ausschnitt um die Fundstelle, Zeilenumbrueche zu Leerzeichen."""
        text = " ".join(self.absatz.split())
        pos = min(self.position, max(0, len(text) - 1))
        start = max(0, pos - breite // 3)
        ende = min(len(text), start + breite)
        start = max(0, ende - breite)
        schnitt = text[start:ende]
        return ("…" if start > 0 else "") + schnitt + ("…" if ende < len(text) else "")


@dataclass
class Ergebnis:
    terme: list[str] = field(default_factory=list)
    treffer: list[Treffer] = field(default_factory=list)
    abgeschnitten: bool = False
    buecher_durchsucht: int = 0


def parse_anfrage(anfrage: str) -> list[str]:
    """Zerlegt die Eingabe in Suchbegriffe: Woerter, oder "ganze Phrasen" in
    Anfuehrungszeichen. Alles wird klein geschrieben (casefold), zu kurze
    Begriffe (unter MIN_TERM_LAENGE Zeichen) fallen weg."""
    terme = []
    for phrase, wort in _TERM.findall(anfrage):
        term = " ".join((phrase or wort).split()).casefold()
        if len(term) >= MIN_TERM_LAENGE and term not in terme:
            terme.append(term)
    return terme


def suche(root: Path, anfrage: str, *, nur_buch: Buch | None = None,
          max_treffer: int = MAX_TREFFER) -> Ergebnis:
    """Sucht Absaetze, die ALLE Begriffe enthalten (ohne Beachtung der
    Gross-/Kleinschreibung; ss und ß gelten als gleich). Ergebnis in
    Bibliotheksreihenfolge, hoechstens max_treffer; abgeschnitten=True, wenn
    es mehr gab."""
    ergebnis = Ergebnis(terme=parse_anfrage(anfrage))
    if not ergebnis.terme:
        return ergebnis
    buecher = [nur_buch] if nur_buch is not None else library.discover_books(root)
    for buch in buecher:
        ergebnis.buecher_durchsucht += 1
        for kapitel in library.list_chapters(buch):
            try:
                text = library.read_chapter_text(buch, kapitel.datei)
            except (OSError, UnicodeDecodeError):
                continue
            # Billiger Vorfilter: fehlt ein Begriff im ganzen Kapitel, kann
            # kein Absatz alle enthalten - spart das Zerlegen in Absaetze.
            gefaltet = text.casefold()
            if not all(term in gefaltet for term in ergebnis.terme):
                continue
            for index, absatz in enumerate(split_paragraphs(text)):
                klein = absatz.casefold()
                if not all(term in klein for term in ergebnis.terme):
                    continue
                if len(ergebnis.treffer) >= max_treffer:
                    ergebnis.abgeschnitten = True
                    return ergebnis
                ergebnis.treffer.append(Treffer(
                    buch=buch, kapitel=kapitel, absatz_index=index, absatz=absatz,
                    position=klein.find(ergebnis.terme[0]),
                ))
    return ergebnis
