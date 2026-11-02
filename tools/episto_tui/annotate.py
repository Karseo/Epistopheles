from __future__ import annotations
import re
from dataclasses import dataclass
from episto_tui.models import Kommentar


def split_paragraphs(text: str) -> list[str]:
    rohabsaetze = re.split(r"\n\s*\n", text.strip())
    return [a.strip() for a in rohabsaetze if a.strip()]


def locate_paragraph(paragraphs: list[str], absatz_index: int, absatz_anfang: str) -> int | None:
    """Findet den Absatz zu einem Kommentar. Bevorzugt absatz_index, wenn der
    Text dort noch passt; sucht sonst nach dem Textanfang im ganzen Kapitel
    (robust gegen kleine Verschiebungen durch Edits). None = verwaist."""
    praefix = absatz_anfang[:40].strip()
    if not praefix:
        return None
    if 0 <= absatz_index < len(paragraphs) and paragraphs[absatz_index].startswith(praefix[:20]):
        return absatz_index
    for i, absatz in enumerate(paragraphs):
        if absatz.startswith(praefix):
            return i
    return None


_MD_SONDERZEICHEN = re.compile(r"([\\`*_\[\]#>|])")


def maskiere_markdown(text: str) -> str:
    """Nutzereingabe soll woertlich erscheinen: "[LdF]" oder "[/]" duerfen
    weder verschwinden noch das Markdown-Rendering zerlegen."""
    return _MD_SONDERZEICHEN.sub(r"\\\1", text)


@dataclass
class Segment:
    """Ein Block des angezeigten Markdown-Texts. startzeile bezieht sich auf
    den von render_mit_kommentaren() gelieferten Text. absatz_index ist bei
    "absatz" der eigene, bei "kommentar" der Absatz, an dem er haengt (None
    bei verwaisten Kommentaren und bei "kopf")."""
    startzeile: int
    art: str  # "absatz" | "kommentar" | "kopf"
    absatz_index: int | None = None
    kommentar: Kommentar | None = None


def _kommentar_block(kommentar: Kommentar) -> str:
    text = maskiere_markdown(" ".join(kommentar.text.split()))
    return f"> \U0001f4ac {text} — {maskiere_markdown(kommentar.erstellt)}"


def render_mit_kommentaren(paragraphs: list[str], kommentare: list[Kommentar]) -> tuple[str, list[Segment]]:
    """Baut den anzuzeigenden Markdown-Text: nach jedem Absatz seine
    Kommentare als Zitat-Bloecke, am Ende verwaiste Kommentare unter einer
    Ueberschrift. Alle Bloecke sind durch Leerzeilen getrennt; die
    Segmentliste kennt die Startzeile jedes Blocks (fuer die Klick- und
    Faerbe-Zuordnung im ReaderPane)."""
    je_absatz: dict[int, list[Kommentar]] = {}
    verwaist: list[Kommentar] = []
    for kommentar in kommentare:
        index = locate_paragraph(paragraphs, kommentar.absatz_index, kommentar.absatz_anfang)
        if index is None:
            verwaist.append(kommentar)
        else:
            je_absatz.setdefault(index, []).append(kommentar)

    bloecke: list[tuple[str, str, int | None, Kommentar | None]] = []
    for i, absatz in enumerate(paragraphs):
        bloecke.append((absatz, "absatz", i, None))
        for kommentar in je_absatz.get(i, []):
            bloecke.append((_kommentar_block(kommentar), "kommentar", i, kommentar))
    if verwaist:
        bloecke.append(("## Kommentare ohne Absatz", "kopf", None, None))
        for kommentar in verwaist:
            bloecke.append((_kommentar_block(kommentar), "kommentar", None, kommentar))

    segmente: list[Segment] = []
    zeile = 0
    for text, art, absatz_index, kommentar in bloecke:
        segmente.append(Segment(zeile, art, absatz_index, kommentar))
        zeile += text.count("\n") + 2  # Blockzeilen + Leerzeile dazwischen
    return "\n\n".join(text for text, *_ in bloecke), segmente
