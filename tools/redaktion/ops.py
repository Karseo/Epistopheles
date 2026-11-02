"""Redaktions-Eintraege und ihre Text-Operationen (Spec 5.1).

Reine Funktionen, nur Standardbibliothek. Die Anwendung ist in JavaScript
(redaktion.js auf dem Geraet) doppelt vorhanden; beide laufen gegen dieselben
Testvektoren (testvektoren.json).

Verankerung: `ziel` = {anfang, absatz_index, [zeile, zeile_bis]}.
- `anfang`: anker_von(Absatz), d. h. die ersten 40 Zeichen, Leerraum zusammengezogen.
- `absatz_index`: Nummer des Absatzes (Zaehlung wie korrektur.absatz_spannen), 0-basiert.
- `zeile`/`zeile_bis`: Zeilen INNERHALB des Absatzes, 0-basiert, beide Grenzen eingeschlossen.
Stimmt die Pruefsumme `vorher.hash` des Absatzes nicht mehr, wird nicht geschrieben (konflikt).
Geaendert wird ausschliesslich die Spanne des betroffenen Absatzes (bei `verschieben` zwei
Spannen); Tabs, Zeilenenden und fehlendes Schluss-Newline ausserhalb bleiben byteidentisch.
"""
from __future__ import annotations

import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

from episto_tui.korrektur import absatz_spannen, ersetze_absatz_exakt

STATUS_ANGEWENDET = "angewendet"
STATUS_KONFLIKT = "konflikt"
STATUS_UEBERSPRUNGEN = "uebersprungen"

# Arten ohne Wirkung auf den Text: werden uebersprungen, nicht als Konflikt gemeldet.
ARTEN_OHNE_TEXTWIRKUNG = ("ruecknahme", "uebersetzung-uebernehmen", "neu-uebersetzen")
TEXTARTEN = ("ersetzen", "verbinden", "trennen", "loeschen", "verschieben")

_FNV_OFFSET = 0xCBF29CE484222325
_FNV_PRIME = 0x100000001B3
_MASKE = 0xFFFFFFFFFFFFFFFF
_ZEILENENDE = re.compile(r"\r?\n")
_ABSATZ_TRENNER = re.compile(r"\n\s*\n")     # wie in korrektur.absatz_spannen


@dataclass
class Ergebnis:
    text: str
    status: str            # "angewendet" | "konflikt" | "uebersprungen"
    grund: str = ""


def normalisiere(text: str) -> str:
    """Unicode NFC, jeder Leerraum zu einem Leerzeichen, getrimmt."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def anker_von(text: str, laenge: int = 40) -> str:
    return normalisiere(text)[:laenge]


def pruefsumme(text: str) -> str:
    """FNV-1a 64 Bit ueber UTF-8 des Texts (\\r\\n als \\n), 16 Hexstellen."""
    h = _FNV_OFFSET
    for byte in text.replace("\r\n", "\n").encode("utf-8"):
        h = ((h ^ byte) * _FNV_PRIME) & _MASKE
    return f"{h:016x}"


def neuer_eintrag(buch: str, ebene: str, ziel: dict, art: str, parameter: dict,
                  vorher_text: str, hinweis: str = "", geraet: str = "") -> dict:
    return {
        "id": secrets.token_hex(6),
        "buch": buch,
        "ebene": ebene,
        "ziel": dict(ziel),
        "art": art,
        "parameter": dict(parameter),
        "vorher": {"hash": pruefsumme(vorher_text), "ausschnitt": vorher_text[:80]},
        "nachher": parameter.get("nachher"),
        "hinweis": hinweis,
        "erstellt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "geraet": geraet,
        "status": "offen",
    }


def ohne_zurueckgenommene(eintraege: list[dict]) -> list[dict]:
    """Entfernt Eintraege, die ein `ruecknahme`-Eintrag (Ziel-id in parameter.id) aufhebt,
    und die `ruecknahme`-Eintraege selbst. Reihenfolge bleibt."""
    def ziel_id(e: dict) -> object:
        p = e.get("parameter")
        return p.get("id") if isinstance(p, dict) else None

    zurueck = {ziel_id(e) for e in eintraege if e.get("art") == "ruecknahme"}
    return [e for e in eintraege if e.get("art") != "ruecknahme" and e.get("id") not in zurueck]


def finde_absatz(text: str, ziel: dict) -> int | None:
    """Index des Ziel-Absatzes. Kandidaten sind Absaetze mit gleichem Anker; `absatz_index`
    gewinnt, wenn er Kandidat ist; sonst genau ein Kandidat; sonst None (nie der erste Treffer)."""
    anfang = ziel.get("anfang")
    kandidaten = [i for i, (a, b) in enumerate(absatz_spannen(text)) if anker_von(text[a:b]) == anfang]
    if ziel.get("absatz_index") in kandidaten:
        return ziel["absatz_index"]
    return kandidaten[0] if len(kandidaten) == 1 else None


def _zeilen(absatz: str) -> tuple[list[str], str]:
    trenner = "\r\n" if "\r\n" in absatz else "\n"
    return _ZEILENENDE.split(absatz), trenner


def _verbinde(oben: str, unten: str) -> str:
    """Silbentrennung am Zeilenende (Buchstabe + '-', danach Kleinbuchstabe) entfernen,
    sonst mit einem Leerzeichen verbinden."""
    if len(oben) >= 2 and oben[-1] == "-" and oben[-2].isalpha() and unten[:1].islower():
        return oben[:-1] + unten
    return oben.rstrip() + " " + unten.lstrip()


def _bereich(ziel: dict, anzahl: int) -> tuple[int, int] | None:
    z = ziel.get("zeile")
    if not isinstance(z, int):
        return None
    bis = ziel.get("zeile_bis", z)
    if not isinstance(bis, int) or not (0 <= z <= bis < anzahl):
        return None
    return z, bis


def _ohne_absatz(text: str, spannen: list[tuple[int, int]], i: int) -> tuple[int, int]:
    """Zu loeschender Zeichenbereich fuer einen ganzen Absatz samt einem angrenzenden Trenner."""
    a, b = spannen[i]
    if i + 1 < len(spannen):
        return a, spannen[i + 1][0]
    if i > 0:
        return spannen[i - 1][1], b
    return a, b


def _konflikt(text: str, grund: str) -> Ergebnis:
    return Ergebnis(text, STATUS_KONFLIKT, grund)


def wende_an(text: str, eintrag: dict) -> Ergebnis:
    """Wendet einen Eintrag an. Ein fehlerhafter Eintrag (Einträge kommen von Geräten) liefert
    nie eine Ausnahme, sondern einen Konflikt mit Grund; der Text bleibt dann unverändert."""
    try:
        return _wende_an(text, eintrag)
    except Exception as exc:  # noqa: BLE001 - jede Fehlform eines Eintrags ist ein Konflikt
        return _konflikt(text, f"fehlerhafter Eintrag: {type(exc).__name__}")


def _wende_an(text: str, eintrag: dict) -> Ergebnis:
    if not isinstance(eintrag, dict):
        return _konflikt(text, "fehlerhafter Eintrag: kein Objekt")
    art = eintrag.get("art")
    if art == "marke":
        return Ergebnis(text, STATUS_ANGEWENDET)
    if art in ARTEN_OHNE_TEXTWIRKUNG:
        return Ergebnis(text, STATUS_UEBERSPRUNGEN, "keine Textoperation")
    if art not in TEXTARTEN:
        return _konflikt(text, f"unbekannte Art: {art}")

    ziel = eintrag.get("ziel")
    parameter = eintrag.get("parameter")
    if not isinstance(ziel, dict):
        return _konflikt(text, "fehlerhafter Eintrag: ziel fehlt")
    if not isinstance(parameter, dict):
        return _konflikt(text, "fehlerhafter Eintrag: parameter fehlt")
    vorher = eintrag.get("vorher")
    erwartet = vorher.get("hash") if isinstance(vorher, dict) else None
    if not isinstance(erwartet, str) or not erwartet:
        return _konflikt(text, "vorher fehlt")
    index = finde_absatz(text, ziel)
    if index is None:
        return _konflikt(text, "Absatz nicht gefunden oder nicht eindeutig")
    spannen = absatz_spannen(text)
    a, b = spannen[index]
    absatz = text[a:b]
    if erwartet != pruefsumme(absatz):
        return _konflikt(text, "Der Absatz hat sich seit dem Eintrag geändert (vorher stimmt nicht mehr)")

    zeilen, trenner = _zeilen(absatz)

    if art == "ersetzen":
        nachher = parameter.get("nachher")
        if not isinstance(nachher, str):
            return _konflikt(text, "parameter.nachher fehlt oder ist kein Text")
        if not nachher.strip():
            return _konflikt(text, "parameter.nachher ist leer")
        if _ABSATZ_TRENNER.search(nachher.strip()):
            return _konflikt(text, "parameter.nachher enthält eine Leerzeile (würde den Absatz teilen)")
        return Ergebnis(ersetze_absatz_exakt(text, index, nachher), STATUS_ANGEWENDET)

    if art == "verbinden":
        z = ziel.get("zeile")
        if not isinstance(z, int) or not (0 <= z < len(zeilen) - 1):
            return _konflikt(text, "keine Zeile zum Verbinden")
        neu = zeilen[:z] + [_verbinde(zeilen[z], zeilen[z + 1])] + zeilen[z + 2:]
        return Ergebnis(text[:a] + trenner.join(neu) + text[b:], STATUS_ANGEWENDET)

    if art == "trennen":
        z = ziel.get("zeile")
        if not isinstance(z, int) or not (1 <= z < len(zeilen)):
            return _konflikt(text, "keine Zeile zum Trennen")
        neu = trenner.join(zeilen[:z]) + trenner * 2 + trenner.join(zeilen[z:])
        return Ergebnis(text[:a] + neu + text[b:], STATUS_ANGEWENDET)

    if art == "loeschen":
        if "zeile" not in ziel:
            von, bis = _ohne_absatz(text, spannen, index)
            return Ergebnis(text[:von] + text[bis:], STATUS_ANGEWENDET)
        bereich = _bereich(ziel, len(zeilen))
        if bereich is None:
            return _konflikt(text, "Zeilen ausserhalb des Absatzes")
        z, bis = bereich
        rest = zeilen[:z] + zeilen[bis + 1:]
        if not rest:
            von, ende = _ohne_absatz(text, spannen, index)
            return Ergebnis(text[:von] + text[ende:], STATUS_ANGEWENDET)
        return Ergebnis(text[:a] + trenner.join(rest) + text[b:], STATUS_ANGEWENDET)

    # verschieben
    bereich = _bereich(ziel, len(zeilen))
    if bereich is None:
        return _konflikt(text, "Zeilen ausserhalb des Absatzes")
    nach = parameter.get("nach_anfang")
    kandidaten = [i for i, (x, y) in enumerate(spannen) if anker_von(text[x:y]) == nach]
    if len(kandidaten) != 1:
        return _konflikt(text, "Zielabsatz zum Verschieben nicht gefunden oder nicht eindeutig")
    if kandidaten[0] == index:
        return _konflikt(text, "Zielabsatz ist der Quellabsatz")
    z, bis = bereich
    bewegt = trenner.join(zeilen[z:bis + 1])
    rest = zeilen[:z] + zeilen[bis + 1:]
    ziel_ende = spannen[kandidaten[0]][1]
    if rest:
        aenderungen = [(a, b, trenner.join(rest))]
    else:
        aenderungen = [_ohne_absatz(text, spannen, index) + ("",)]
    aenderungen.append((ziel_ende, ziel_ende, trenner * 2 + bewegt))
    for von, bis_, neu in sorted(aenderungen, key=lambda t: (t[0], t[1]), reverse=True):
        text = text[:von] + neu + text[bis_:]
    return Ergebnis(text, STATUS_ANGEWENDET)


def spiele_ab(text: str, eintraege: list[dict]) -> tuple[str, list[Ergebnis]]:
    """Wendet die Eintraege der Reihe nach an. Scheitert einer, werden spaetere Eintraege am
    selben Absatz (gleicher Anker, auch der des erwarteten Ergebnisses) als abhaengiger
    Konflikt gemeldet, mit der id des Ausloesers im Grund."""
    ergebnisse: list[Ergebnis] = []
    gesperrt: dict[str, str] = {}      # Anker -> id des ausloesenden Eintrags
    for e in eintraege:
        if not isinstance(e, dict):
            ergebnisse.append(_konflikt(text, "fehlerhafter Eintrag: kein Objekt"))
            continue
        ziel = e.get("ziel") if isinstance(e.get("ziel"), dict) else {}
        parameter = e.get("parameter") if isinstance(e.get("parameter"), dict) else {}
        anfang = ziel.get("anfang")
        ausloeser = gesperrt.get(anfang) if isinstance(anfang, str) else None
        eid = e.get("id", "?") if isinstance(e.get("id", "?"), str) else "?"
        if ausloeser is not None and e.get("art") in TEXTARTEN:
            erg = _konflikt(text, f"abhängig von Eintrag {ausloeser}, der nicht angewendet werden konnte")
            nachher = parameter.get("nachher")
            if isinstance(nachher, str):
                gesperrt.setdefault(anker_von(nachher), ausloeser)
        else:
            erg = wende_an(text, e)
            if erg.status == STATUS_KONFLIKT:
                if isinstance(anfang, str):
                    gesperrt.setdefault(anfang, eid)
                nachher = parameter.get("nachher")
                if isinstance(nachher, str):
                    gesperrt.setdefault(anker_von(nachher), eid)
        text = erg.text
        ergebnisse.append(erg)
    return text, ergebnisse
