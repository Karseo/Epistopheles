"""Kern des Schnelllesers: macht aus den KI-Feldern eines Kapitels (Zusammen-
fassung, Thesen, Gegenpositionen, Kernbegriffe, Definitionen, Belege) eine
Wortfolge mit Abschnittsmarken, Erkennungspunkt und Anzeigedauer je Wort.

Bewusst nur fuer die destillierten Felder, nicht fuer den Originaltext: Der
Zweck ist ein schneller Ueberblick VOR dem Lesen (Hinweis, dann Originaltext),
nicht das Ueberfliegen der Theorie selbst."""
from __future__ import annotations
import re
from dataclasses import dataclass
from rich.text import Text
from episto_tui.models import Tag

MIN_WPM = 100
MAX_WPM = 900
STANDARD_WPM = 400
WPM_SCHRITT = 50        # grob: Pfeiltasten, Knoepfe -50/+50
WPM_FEIN = 5            # fein: Tasten + und -, Knoepfe -5/+5
SPRUNG_WOERTER = 10

# Reihenfolge und Beschriftung der Abschnitte. Leere Felder entfallen.
ABSCHNITTE = [
    ("zusammenfassung", "Zusammenfassung"),
    ("these", "Thesen"),
    ("gegen", "Gegenpositionen"),
    ("kern", "Kernbegriffe"),
    ("def_", "Definitionen"),
    ("beleg", "Belege"),
]

_FUSSNOTE = re.compile(r"\s*\[\^[^\]]+\]")
_MD = re.compile(r"\*+|^_+|_+$")       # Hervorhebungs-Sternchen und Rand-Unterstriche
_SCHLUSS_ZEICHEN = "\"'»«“”„‘’)]}"
_SATZENDE = ".!?…"
_PAUSE_ZEICHEN = ",;:–—"


@dataclass
class Wort:
    text: str
    abschnitt: int          # Index in der Abschnittsliste
    marke: bool = False     # Abschnittsueberschrift statt Textwort
    satzende: bool = False  # danach beginnt ein neuer Satz / Listeneintrag
    faktor: float = 1.0     # Anzeigedauer relativ zur Grunddauer eines Worts


def kern_des_wortes(text: str) -> str:
    """Das Wort ohne umgebende Satzzeichen und Klammern."""
    return text.strip(_SCHLUSS_ZEICHEN + _SATZENDE + _PAUSE_ZEICHEN + "(['\"„“‘»«")


def _faktor(text: str) -> float:
    kern = kern_des_wortes(text)
    faktor = 1.0
    if len(kern) > 12:
        faktor += 0.6
    elif len(kern) > 8:
        faktor += 0.3
    ende = text.rstrip(_SCHLUSS_ZEICHEN)[-1:]
    if ende and ende in _SATZENDE:
        faktor += 1.0
    elif ende and ende in _PAUSE_ZEICHEN:
        faktor += 0.5
    return faktor


def _tokens(eintrag: str) -> list[str]:
    """Woerter eines Eintrags ohne Fussnotenmarken. Reine Satzzeichen (z. B. das
    Satzende, das hinter einer entfernten Fussnotenmarke uebrig bleibt) haengen
    sich ans vorige Wort, statt als eigenes Wort angezeigt zu werden."""
    token: list[str] = []
    for t in _FUSSNOTE.sub("", eintrag).split():
        t = _MD.sub("", t)
        if not t:
            continue
        if token and not any(c.isalnum() for c in t):
            token[-1] += t
        else:
            token.append(t)
    return token


def baue_woerter(tag: Tag) -> tuple[list[Wort], list[str]]:
    """Die Wortfolge des Kapitels und die Namen der vorkommenden Abschnitte.
    Jeder Abschnitt beginnt mit einem Marken-Wort (z. B. "Thesen"); jeder
    Listeneintrag endet als eigener Satz mit Extrapause."""
    woerter: list[Wort] = []
    namen: list[str] = []
    for feld, name in ABSCHNITTE:
        wert = getattr(tag, feld)
        eintraege = [wert] if isinstance(wert, str) else list(wert)
        eintraege = [e for e in (str(e).strip() for e in eintraege) if e]
        if not eintraege:
            continue
        abschnitt = len(namen)
        namen.append(name)
        woerter.append(Wort(name, abschnitt, marke=True, satzende=True, faktor=2.0))
        for eintrag in eintraege:
            token = _tokens(eintrag)
            for i, t in enumerate(token):
                w = Wort(t, abschnitt, faktor=_faktor(t))
                if i == len(token) - 1:
                    w.satzende = True
                    w.faktor = max(w.faktor, 2.0)
                elif t.rstrip(_SCHLUSS_ZEICHEN)[-1:] in _SATZENDE:
                    w.satzende = True
                woerter.append(w)
    return woerter, namen


def orp_index(text: str) -> int:
    """Index des Erkennungspunkts (der Buchstabe, auf den das Auge faellt) im
    Wort: etwa ab der Mitte des ersten Drittels, wie bei den ueblichen
    Schnellleseverfahren (bei sehr langen Woertern rund 30 % der Laenge). Umgebende Satzzeichen zaehlen nicht mit."""
    kern = kern_des_wortes(text)
    versatz = text.find(kern) if kern else 0
    laenge = len(kern)
    if laenge <= 1:
        index = 0
    elif laenge <= 5:
        index = 1
    elif laenge <= 9:
        index = 2
    elif laenge <= 13:
        index = 3
    else:
        index = (3 * laenge + 5) // 10     # ab 14: rund 30 % der Laenge (bei 14 -> 4), damit der Punkt bei langen Woertern nicht nach vorn wandert
    return max(0, versatz) + index


def render_wort(wort: Wort, halb: int) -> Text:
    """Eine Zeile der Breite 2*halb+1, in der der Erkennungspunkt des Worts in
    Spalte `halb` steht (der Blick bleibt an einer Stelle). Sehr lange Woerter
    wuerden rechts herausragen: dann rutscht das ganze Wort nach links, der
    Erkennungspunkt weicht fuer dieses eine Wort aus. Nur was auch so nicht
    passt (ueber 2*halb+1 Zeichen), wird mit … gekuerzt."""
    breite = 2 * halb + 1
    text = wort.text.upper() if wort.marke else wort.text
    if len(text) > breite:
        text = text[:breite - 1] + "…"
    i = min(orp_index(text), len(text) - 1)
    links, mitte, rechts = text[:i], text[i], text[i + 1:]
    ueberstand = max(0, len(rechts) - halb)
    einrueckung = max(0, halb - len(links) - ueberstand)
    zeile = Text(" " * einrueckung)
    stil = "bold cyan" if wort.marke else None
    zeile.append(links, style=stil)
    zeile.append(mitte, style="bold red" if not wort.marke else "bold cyan reverse")
    zeile.append(rechts, style=stil)
    return zeile


def satzanfang(woerter: list[Wort], i: int) -> int:
    """Index des ersten Worts des Satzes, in dem Wort `i` steht."""
    j = min(max(i, 0), len(woerter) - 1)
    while j > 0 and not woerter[j - 1].satzende:
        j -= 1
    return j


def voriger_satzanfang(woerter: list[Wort], i: int) -> int:
    """Zurueck zum Anfang des laufenden Satzes; steht man schon dort, zum Anfang
    des davor liegenden."""
    start = satzanfang(woerter, i)
    if start == i and i > 0:
        return satzanfang(woerter, i - 1)
    return start


def naechster_satzanfang(woerter: list[Wort], i: int) -> int:
    for j in range(i + 1, len(woerter)):
        if woerter[j - 1].satzende:
            return j
    return len(woerter) - 1


def abschnittsanfang(woerter: list[Wort], i: int) -> int:
    """Index des Marken-Worts des Abschnitts von Wort `i`."""
    a = woerter[i].abschnitt
    while i > 0 and woerter[i - 1].abschnitt == a:
        i -= 1
    return i


def voriger_abschnitt(woerter: list[Wort], i: int) -> int:
    anfang = abschnittsanfang(woerter, i)
    if anfang == i and i > 0:
        return abschnittsanfang(woerter, i - 1)
    return anfang


def naechster_abschnitt(woerter: list[Wort], i: int) -> int:
    a = woerter[i].abschnitt
    for j in range(i + 1, len(woerter)):
        if woerter[j].abschnitt != a:
            return j
    return len(woerter) - 1


def grunddauer(wpm: int) -> float:
    return 60.0 / min(max(wpm, MIN_WPM), MAX_WPM)


def dauer(wort: Wort, wpm: int) -> float:
    return grunddauer(wpm) * wort.faktor


def restdauer(woerter: list[Wort], i: int, wpm: int) -> float:
    """Sekunden vom Wort `i` bis zum Ende bei Tempo `wpm`."""
    return sum(dauer(w, wpm) for w in woerter[i:])


def begrenze_tempo(wpm: int) -> int:
    return min(max(int(wpm), MIN_WPM), MAX_WPM)
