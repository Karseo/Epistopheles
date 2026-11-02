from __future__ import annotations
import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from episto_tui import library
from episto_tui.annotate import split_paragraphs, locate_paragraph
from episto_tui.models import Buch, Highlight, Kapitel

STANDARD_MODELL = "aya-expanse:32b"
OLLAMA_URL = "http://localhost:11434/api/chat"
# Wie viele Absaetze links und rechts der geschaetzten Stelle als englischer
# Anker dienen (Fenster = 2 * FENSTER_BREITE + 1 Absaetze) und wie viele Zeichen
# das Fenster hoechstens haben darf (sonst sprengt es den Kontext des Modells).
FENSTER_BREITE = 3
FENSTER_MAX_ZEICHEN = 8000


def sammle_marken(buch: Buch) -> list[Highlight]:
    return library.read_highlights_nach_farbe(buch, "korrektur")


def lektor_pfad_von(buch: Buch, meta: dict) -> Path:
    """Lektor-Ordner des Buchs (meta.json -> lektor_pfad). Nennt der Eintrag einen alten Ablageort
    (C:\\Users\\Dude\\Tools\\eBooks\\Lektor\\..., /mnt/c/... oder D:\\Workspace\\!Episto\\eBooks\\Lektor\\...),
    wird alles hinter dem Ordner `eBooks` unter <Bibliothek>\\rohdaten neu aufgesetzt, sofern es
    dort existiert (der Lektor-Ordner liegt seit dem Umbau in rohdaten\\Lektor). Sonst kommt der
    gespeicherte Pfad unveraendert zurueck."""
    s = str(meta["lektor_pfad"]).replace("\\", "/")
    if s.startswith("/mnt/") and len(s) > 6 and s[6] == "/":
        s = f"{s[5].upper()}:{s[6:]}"                       # /mnt/c/x -> C:/x
    gespeichert = Path(s)
    if gespeichert.exists():
        return gespeichert
    teile = gespeichert.parts
    for i in range(len(teile) - 1, -1, -1):
        if teile[i].lower() == "ebooks":
            neu = library.root_von(buch).joinpath(library.ROHDATEN_ORDNER, *teile[i + 1:])
            if neu.exists():
                return neu
            break
    return gespeichert


def _lade_segmente(buch: Buch) -> list[dict]:
    meta = json.loads((buch.pfad / "meta.json").read_text(encoding="utf-8"))
    lektor_pfad = lektor_pfad_von(buch, meta)
    kap = json.loads((lektor_pfad / "kapitel.json").read_text(encoding="utf-8"))
    return sorted(kap["segmente"], key=lambda s: (int(s["chunk"]), int(s["position"])))


def englischer_kapiteltext(buch: Buch, nr: int, segmente: list[dict] | None = None) -> str:
    if segmente is None:
        segmente = _lade_segmente(buch)
    meta = json.loads((buch.pfad / "meta.json").read_text(encoding="utf-8"))
    start = int(segmente[nr - 1]["chunk"])
    ende = int(segmente[nr]["chunk"]) if nr < len(segmente) else int(meta["chunks"]) - 1
    return "\n\n".join(
        (library.rohchunks_en_ordner(buch) / f"chunk_{i:03d}.md").read_text(encoding="utf-8")
        for i in range(start, ende + 1)
    )


_ABSATZ_TRENNER = re.compile(r"\n\s*\n")


def absatz_spannen(text: str) -> list[tuple[int, int]]:
    """Zeichenbereiche [start, ende) der Absaetze im UNVERAENDERTEN Text, in
    derselben Zaehlung wie annotate.split_paragraphs()."""
    spannen: list[tuple[int, int]] = []
    pos = 0
    for trenner in list(_ABSATZ_TRENNER.finditer(text)) + [None]:
        ende = trenner.start() if trenner is not None else len(text)
        stueck = text[pos:ende]
        if stueck.strip():
            links = len(stueck) - len(stueck.lstrip())
            rechts = len(stueck.rstrip())
            spannen.append((pos + links, pos + rechts))
        if trenner is not None:
            pos = trenner.end()
    return spannen


def ersetze_absatz_exakt(text: str, index: int, neuer_absatz: str) -> str:
    """Ersetzt genau einen Absatz und laesst den Rest des Kapitels
    zeichengenau unveraendert (Leerzeilen, Zeilenenden, EOF)."""
    spannen = absatz_spannen(text)
    if not (0 <= index < len(spannen)):
        raise ValueError(f"Absatz {index} ausserhalb 0..{len(spannen) - 1}")
    start, ende = spannen[index]
    return text[:start] + neuer_absatz.strip() + text[ende:]


def ersetze_absatz(text: str, index: int, neuer_absatz: str) -> str:
    """Ersetzt einen Absatz und gibt den GANZEN Kapiteltext zurueck.

    Bekannte Einschraenkung (bewusst einfach gehalten): Der Rueckgabewert
    ist keine Minimal-Aenderung, sondern eine normalisierte Neufassung des
    gesamten Kapitels - alle Absaetze werden mit "\n\n" wieder verbunden und
    am Ende wird ein abschliessendes "\n" (EOF-Newline) angefuegt. Dadurch
    gehen z. B. urspruengliche Leerzeilen-Gruppierungen oder ein fehlendes
    EOF-Newline verloren. Fuer den Korrektur-Lauf ist das akzeptiert."""
    absaetze = split_paragraphs(text)
    if not (0 <= index < len(absaetze)):
        raise ValueError(f"Absatz {index} ausserhalb 0..{len(absaetze) - 1}")
    absaetze[index] = neuer_absatz.strip()
    return "\n\n".join(absaetze) + "\n"


def englische_absaetze(buch: Buch, nr: int, segmente: list[dict] | None = None) -> list[str]:
    return split_paragraphs(englischer_kapiteltext(buch, nr, segmente))


def englisches_fenster(anzahl_de: int, index: int, anzahl_en: int,
                       breite: int = FENSTER_BREITE) -> tuple[int, int]:
    """Fenster [start, ende) im englischen Kapitel um die Stelle, die dem
    deutschen Absatz `index` (von `anzahl_de`) ungefaehr entspricht. Die
    Uebersetzung folgt dem Original absatzweise; ueber das Kapitel gesehen
    stimmt das Verhaeltnis daher gut, im Einzelnen weicht es ab, deshalb ein
    Fenster statt eines Absatzes (und in der Oberflaeche verschiebbar)."""
    if anzahl_en <= 0:
        return 0, 0
    if anzahl_de <= 0:
        mitte = 0
    else:
        mitte = int((index + 0.5) / anzahl_de * anzahl_en)
    return _fenster_um(mitte, breite, anzahl_en)


def _fenster_um(mitte: int, breite: int, anzahl: int) -> tuple[int, int]:
    groesse = min(2 * breite + 1, anzahl)
    start = min(max(mitte - breite, 0), anzahl - groesse)
    return start, start + groesse


def alle_englischen_absaetze(buch: Buch) -> list[str]:
    """Der englische Volltext des Buchs (rohdaten/en-chunks/<Autor>/<Titel>/chunk_*.md in
    Reihenfolge) als Absatzliste. FileNotFoundError, wenn es keine Rohchunks gibt."""
    ordner = library.rohchunks_en_ordner(buch)
    chunks = sorted(ordner.glob("chunk_*.md"))
    if not chunks:
        raise FileNotFoundError(f"kein englisches Original in {ordner}")
    return split_paragraphs("\n\n".join(c.read_text(encoding="utf-8") for c in chunks))


def globales_fenster(buch: Buch, datei: str, absatz_index: int, en_absaetze: list[str],
                     breite: int = FENSTER_BREITE + 1) -> tuple[int, int]:
    """Naeherung OHNE Kapitelgrenzen des englischen Originals: Die Stelle des
    deutschen Absatzes im ganzen Buch (Zeichenanteil) wird auf die gleiche
    relative Stelle im englischen Volltext abgebildet. Ungenauer als die
    Kapitelzuordnung (Vorspann, Anhang und Uebersetzungsunterschiede verschieben
    die Stelle um einige Absaetze), deshalb ein breiteres Fenster; in der
    Oberflaeche laesst es sich verschieben."""
    vorher = 0
    gesamt = 0
    offset = 0
    for kapitel in library.list_chapters(buch):
        try:
            text = library.read_chapter_text(buch, kapitel.datei)
        except (OSError, UnicodeDecodeError):
            continue
        if kapitel.datei == datei:
            spannen = absatz_spannen(text)
            offset = vorher + (spannen[absatz_index][0] if 0 <= absatz_index < len(spannen) else 0)
        vorher += len(text)
        gesamt += len(text)
    anteil = offset / gesamt if gesamt else 0.0
    ziel = anteil * sum(len(a) for a in en_absaetze)
    summe = 0
    mitte = len(en_absaetze) - 1
    for i, absatz in enumerate(en_absaetze):
        summe += len(absatz)
        if summe >= ziel:
            mitte = i
            break
    return _fenster_um(mitte, breite, len(en_absaetze))


@dataclass
class EnglischerAnker:
    absaetze: list[str]
    fenster: tuple[int, int]
    genau: bool        # True: Kapitelgrenzen bekannt; False: Naeherung ueber das ganze Buch


def englischer_anker(buch: Buch, datei: str, absatz_index: int,
                     segmente: list[dict] | None = None) -> EnglischerAnker:
    """Englische Absaetze samt Startfenster fuer den deutschen Absatz. Erst ueber
    die Kapitelgrenzen des Lektor-Ordners (meta.json -> lektor_pfad); fehlt der
    (er liegt oft nicht mehr da oder ausserhalb der synchronisierten Bibliothek),
    ueber die Naeherung im ganzen Buch. OSError/FileNotFoundError, wenn es gar
    kein englisches Original gibt."""
    anzahl_de = len(split_paragraphs(library.read_chapter_text(buch, datei)))
    nr = kapitelnummer(datei)
    if nr is not None:
        try:
            absaetze = englische_absaetze(buch, nr, segmente)
            if absaetze:
                return EnglischerAnker(absaetze, englisches_fenster(anzahl_de, absatz_index, len(absaetze)), True)
        except (OSError, KeyError, IndexError, ValueError, json.JSONDecodeError):
            pass
    absaetze = alle_englischen_absaetze(buch)
    return EnglischerAnker(absaetze, globales_fenster(buch, datei, absatz_index, absaetze), False)


def verschiebe_fenster(fenster: tuple[int, int], schritte: int, anzahl_en: int) -> tuple[int, int]:
    """Verschiebt das Fenster um `schritte` Absaetze, ohne es ueber die Grenzen
    des Kapitels zu schieben oder seine Groesse zu aendern."""
    start, ende = fenster
    groesse = ende - start
    start = min(max(start + schritte, 0), max(0, anzahl_en - groesse))
    return start, min(anzahl_en, start + groesse)


def fenster_text(en_absaetze: list[str], fenster: tuple[int, int],
                 max_zeichen: int = FENSTER_MAX_ZEICHEN) -> str:
    """Der Text des Fensters; zu lange Fenster werden von aussen gekuerzt,
    bis sie passen (die mittleren Absaetze bleiben)."""
    start, ende = fenster
    absaetze = en_absaetze[start:ende]
    while len(absaetze) > 1 and sum(len(a) for a in absaetze) > max_zeichen:
        absaetze = absaetze[1:] if len(absaetze) % 2 == 0 else absaetze[:-1]
    return "\n\n".join(absaetze)


_FUSSNOTE = re.compile(r"\[\^[^\]]+\]|(?<![\w*])\*\d+\b")
_PLAUDEREI = re.compile(
    r"^\s*(hier ist|here is|korrigierter absatz|korrektur|der korrigierte)", re.IGNORECASE)


def pruefe_vorschlag(original: str, vorschlag: str) -> list[str]:
    """Warnungen zu einem Korrekturvorschlag (leere Liste = unauffaellig).
    Die Pruefung erkennt typische Fehler von Sprachmodellen, ersetzt aber nicht
    das Lesen."""
    warnungen: list[str] = []
    neu = vorschlag.strip()
    if not neu:
        return ["Der Vorschlag ist leer."]
    if neu == original.strip():
        warnungen.append("Der Vorschlag ist unveraendert.")
    laenge = len(original.strip()) or 1
    if len(neu) < 0.5 * laenge:
        warnungen.append("Der Vorschlag ist weniger als halb so lang wie das Original.")
    elif len(neu) > 2.5 * laenge:
        warnungen.append("Der Vorschlag ist mehr als 2,5-mal so lang wie das Original.")
    if _PLAUDEREI.match(neu):
        warnungen.append("Der Vorschlag beginnt wie eine Antwort des Modells, nicht wie Buchtext.")
    if len(split_paragraphs(neu)) > 1 and len(split_paragraphs(original)) == 1:
        warnungen.append("Aus einem Absatz wurden mehrere.")
    alt, jetzt = sorted(_FUSSNOTE.findall(original)), sorted(_FUSSNOTE.findall(neu))
    if alt != jetzt:
        warnungen.append("Die Fussnotenmarken weichen vom Original ab.")
    return warnungen


@dataclass
class OffeneMarke:
    """Eine korrektur-Marke samt aufgeloestem Absatz."""
    buch: Buch
    kapitel: Kapitel
    highlight: Highlight
    absatz_index: int | None   # None: Absatz nicht mehr auffindbar
    absatz: str                # leer, wenn nicht auffindbar


def sammle_offene_marken(buecher: list[Buch]) -> list[OffeneMarke]:
    """Alle korrektur-Marken der Buecher, nach Buch, Kapitel und Absatz
    sortiert. Marken zu verschwundenen Kapiteldateien werden uebersprungen."""
    ergebnis: list[OffeneMarke] = []
    for buch in buecher:
        marken = sammle_marken(buch)
        if not marken:
            continue
        kapitel_nach_datei = {k.datei: k for k in library.list_chapters(buch)}
        for h in marken:
            kapitel = kapitel_nach_datei.get(h.datei)
            if kapitel is None:
                continue
            try:
                absaetze = split_paragraphs(library.read_chapter_text(buch, h.datei))
            except (OSError, UnicodeDecodeError):
                continue
            index = locate_paragraph(absaetze, h.absatz_index, h.absatz_anfang)
            ergebnis.append(OffeneMarke(
                buch, kapitel, h, index, absaetze[index] if index is not None else ""))
    ergebnis.sort(key=lambda m: (m.buch.autor.casefold(), m.buch.titel.casefold(),
                                 m.kapitel.nr, m.highlight.absatz_index))
    return ergebnis


def wende_an(marke: OffeneMarke, neuer_absatz: str) -> int:
    """Schreibt den korrigierten Absatz zeichengenau in das Kapitel (mit
    Sicherung) und entfernt die Marke. Der Absatz wird DABEI neu gesucht, nicht
    dem Index der Marke vertraut: das Kapitel kann sich seit dem Laden der Liste
    geaendert haben. Gibt den Absatzindex zurueck. ValueError, wenn der Absatz
    nicht mehr auffindbar ist (dann bleibt alles unveraendert)."""
    text = library.read_chapter_text(marke.buch, marke.highlight.datei)
    index = locate_paragraph(split_paragraphs(text), marke.highlight.absatz_index,
                             marke.highlight.absatz_anfang)
    if index is None:
        raise ValueError("Absatz nicht mehr auffindbar")
    library.write_chapter_text(marke.buch, marke.highlight.datei,
                               ersetze_absatz_exakt(text, index, neuer_absatz))
    library.remove_highlight(marke.buch, marke.highlight.datei, marke.highlight.absatz_index)
    return index


def entferne_marke(marke: OffeneMarke) -> None:
    library.remove_highlight(marke.buch, marke.highlight.datei, marke.highlight.absatz_index)


def kapitelnummer(datei: str) -> int | None:
    try:
        return int(datei.split("_")[0])
    except ValueError:
        return None


def modell() -> str:
    return os.environ.get("EPISTO_KORREKTUR_MODELL") or STANDARD_MODELL


_SYSTEM = (
    "Du bist ein Lektor für ein übersetztes Buch. Der folgende deutsche Absatz ist "
    "fehlerhaft (z. B. Abbruch mitten im Satz oder fehlerhafte Fußnotenzuordnung). "
    "Nutze den englischen Originaltext des Kapitels, um den deutschen Absatz korrekt "
    "zu reparieren. Antworte ausschließlich mit dem korrigierten deutschen Absatz "
    "(Markdown bleibt erhalten)."
)


def korrigiere(absatz: str, englisch: str, model: str = STANDARD_MODELL,
               ollama_url: str = OLLAMA_URL) -> str:
    body = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0.2},
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Deutscher Absatz (fehlerhaft):\n{absatz}\n\nEnglisches Original (Kapitel):\n{englisch}"},
        ],
    }
    import requests  # nur fuer den Ollama-Aufruf; auf dem Handy (ohne Ollama) nicht noetig
    resp = requests.post(ollama_url, json=body, timeout=600)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def main(argv: list[str] | None = None) -> None:
    """Korrektur-Lauf auf der Kommandozeile (die TUI bietet dasselbe im Dialog,
    Taste x). Als Anker dient ein Fenster des englischen Kapitels um die
    geschaetzte Stelle; -Voll schickt stattdessen das ganze Kapitel."""
    parser = argparse.ArgumentParser(prog="episto_tui.korrektur")
    parser.add_argument("-Buch", required=True)
    parser.add_argument("-Model", default=modell())
    parser.add_argument("-Limit", type=int, default=0)
    parser.add_argument("-Voll", action="store_true", help="ganzes englisches Kapitel statt Fenster")
    args = parser.parse_args(argv)

    buch = Buch(autor="", titel="", pfad=Path(args.Buch))
    marken = sammle_offene_marken([buch])
    if not marken:
        print("Keine korrektur-Marken.")
        return
    if args.Limit > 0:
        marken = marken[:args.Limit]

    try:
        segmente = _lade_segmente(buch)
    except (OSError, KeyError, json.JSONDecodeError):
        segmente = None      # englischer_anker faellt auf die Naeherung ueber das ganze Buch zurueck

    gesamt = len(marken)
    for i, marke in enumerate(marken, 1):
        datei = marke.highlight.datei
        if marke.absatz_index is None:
            print(f"[{i}/{gesamt}] {datei}: Absatz nicht gefunden, ueberspringe.")
            continue
        nr = kapitelnummer(datei)
        if nr is None:
            print(f"[{i}/{gesamt}] {datei}: Dateiname ohne Kapitelnummer, ueberspringe.")
            continue
        try:
            anker = englischer_anker(buch, datei, marke.absatz_index, segmente)
        except (OSError, ValueError):
            print(f"[{i}/{gesamt}] {datei}: Englisches Original nicht lesbar, ueberspringe.")
            continue
        if not anker.genau:
            print(f"[{i}/{gesamt}] {datei}: Hinweis: Naeherung ueber das ganze Buch (keine Kapitelgrenzen).")
        if args.Voll and anker.genau:
            englisch = "\n\n".join(anker.absaetze)
        else:
            englisch = fenster_text(anker.absaetze, anker.fenster)
        kaputt = marke.absatz
        try:
            korrigiert = korrigiere(kaputt, englisch, args.Model)
        except Exception:  # 1 Retry, dann ueberspringen
            try:
                korrigiert = korrigiere(kaputt, englisch, args.Model)
            except Exception as exc2:
                print(f"[{i}/{gesamt}] {datei}: LLM fehlgeschlagen ({exc2}), ueberspringe.")
                continue
        print(f"[{i}/{gesamt}] {datei}, Absatz {marke.absatz_index}")
        print(f"  fehlerhaft: {kaputt}")
        print(f"  korrigiert: {korrigiert}")
        for warnung in pruefe_vorschlag(kaputt, korrigiert):
            print(f"  ACHTUNG: {warnung}")
        antwort = input("  Uebernehmen? [j/n/e] ").strip().lower()
        if antwort == "e":
            print("Lauf beendet.")
            return
        if antwort == "j":
            try:
                wende_an(marke, korrigiert)
                print("  uebernommen.")
            except ValueError as exc:
                print(f"  nicht uebernommen: {exc}.")


if __name__ == "__main__":
    main()
