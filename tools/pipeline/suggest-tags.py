"""
suggest-tags.py  —  Analyse-Tags vorschlagen, die beim Korrekturlesen bestaetigt werden

Schlaegt je Absatz eines deutschen Chunks ein Tag vor und schreibt es als
Obsidian-Kommentar in einer eigenen Zeile ueber den Absatz:

    %%these peripherie-mechanismus%%
    ::: para
    Jenseits der Kern- und Semi-Peripherie-Laender ...
    :::

Der Vorschlag ist Rohmaterial: beim Korrekturlesen wird bestaetigt, geaendert
oder geloescht. Die Auswahl bleibt damit beim Menschen — das Modell macht nur
die mechanische Vorarbeit.

Vokabular (bewusst klein):
    these   Kernbehauptung, die der Autor belegen will (max. 2 pro Chunk)
    beleg   Daten, Studie, Quelle, die eine These stuetzt
    gegen   Position, die der Autor bestreitet oder referiert
    def     Begriffsbestimmung
    kern    Schluesselstelle
    frag    zweifelhaft, nachpruefen

Verwendung:
  python suggest-tags.py "Field, G. Lowell\\Elitism (Routledge Revivals)" --limit 3
  python suggest-tags.py "<Buch>" --resume
  python suggest-tags.py "<Buch>" --in-place        # Chunks direkt bearbeiten
  python suggest-tags.py "<Pfad>\\de\\chunk_034.md" # einzelne Datei
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import requests

from collections import Counter

BASE   = Path(os.environ.get("EBOOK_BASE", Path(__file__).resolve().parents[2] / "rohdaten"))
LEKTOR = BASE / "Lektor"
OLLAMA = "http://localhost:11434"
# qwen3.8:27b trifft dieselben Stellen wie qwen3.6:27b, braucht aber nur ein
# Drittel der Zeit (gemessen 2026-08-20). qwen3:8b ist zu grosszuegig: es
# markiert fast jeden Absatz und entwertet damit die Auswahl.
MODELL = "qwen3.8:27b"          # Analyse, nicht Uebersetzung
MIN_LEN = 200                   # kuerzere Absaetze bekommen kein Tag
TAGS = ("these", "beleg", "gegen", "def", "kern", "frag")


PROMPT = """Du analysierst Absätze aus einem Sachbuch für eine private Wissensbibliothek.

Ordne jedem Absatz höchstens EIN Tag zu:

these  = Kernbehauptung, die der Autor belegen will. NICHT für Zwischenschritte
         einer Herleitung. Höchstens 2 pro Text.
beleg  = konkrete Daten, Zahlen, Studien oder Quellen, die eine These stützen
gegen  = Position, die der Autor bestreitet oder von anderen referiert
def    = Begriffsbestimmung, Einführung eines Fachbegriffs
kern   = Schlüsselstelle, die den Gedankengang trägt
frag   = zweifelhafte, veraltete oder prüfbedürftige Angabe
-      = kein Tag (Überleitung, Beschreibung, Wiederholung, Zwischenschritt)

Reine Überleitungen, Wiederholungen und Zwischenschritte einer Herleitung
bekommen "-". Ansonsten gilt: im Zweifel lieber ein Tag setzen als keines —
Überflüssiges wird beim Korrekturlesen gestrichen, Übersehenes fällt niemandem
mehr auf.

Antworte je Absatz mit einer Zeile:
<Nummer>|<tag>|<stichwort>

Erfüllt ein Absatz ZWEI verschiedene Funktionen — etwa: er führt einen Begriff
ein UND stellt eine Kernbehauptung auf —, schreibe zwei Zeilen mit derselben
Nummer. Höchstens zwei Zeilen pro Absatz.

Das Stichwort ist ein bis zwei Wörter, klein, mit Bindestrich verbunden, und
benennt das Thema (z.B. "peripherie-mechanismus"). Bei "-" lass es leer.
Keine Erklärungen, keine weiteren Zeilen.
{vokabular}
Absätze:

{absaetze}"""

VOKABULAR_HINWEIS = """
WICHTIG — bereits in diesem Buch vergebene Stichworte:
{liste}

Greife diese auf, wo das Thema dasselbe ist. Ein neues Stichwort nur für ein
wirklich neues Thema. Dieselbe Sache muss überall gleich heißen: aus
"elite-herrschaft", "elite-organisation" und "elite-macht" wird sonst dreimal
dasselbe unter drei Namen, und der Zusammenhang zerfällt.
"""


def bloecke(text: str) -> list[dict]:
    """
    Zerlegt einen Chunk in Bloecke. Pandoc-Divs (::: para ... :::) bleiben
    zusammen; der Einfuegepunkt fuer das Tag ist die Zeile des Div-Beginns.
    """
    zeilen = text.splitlines()
    ergebnis, i = [], 0
    while i < len(zeilen):
        z = zeilen[i]
        if re.match(r'^:::+\s*\S', z):                 # Div-Beginn
            start = i
            i += 1
            inhalt = []
            while i < len(zeilen) and not re.match(r'^:::+\s*$', zeilen[i]):
                inhalt.append(zeilen[i])
                i += 1
            i += 1                                      # schliessendes :::
            ergebnis.append({"start": start, "text": "\n".join(inhalt).strip(),
                             "art": z.strip()})
        elif z.strip():
            start = i
            inhalt = []
            while i < len(zeilen) and zeilen[i].strip():
                inhalt.append(zeilen[i])
                i += 1
            ergebnis.append({"start": start, "text": "\n".join(inhalt).strip(),
                             "art": "absatz"})
        else:
            i += 1
    return ergebnis


def ueberschrift(block: dict) -> bool:
    """Ueberschriften-Divs und Markdown-Headings bekommen kein Tag."""
    if block["art"].startswith("::: h"):
        return True
    return bool(re.match(r'^#{1,6}\s', block["text"]))


MAX_TAGS_PRO_ABSATZ = 2


VOKABULAR_MAX = 40      # so viele Stichworte kommen in den Prompt


def frage_modell(kandidaten: list[tuple[int, str]], modell: str,
                 ollama: str, vokabular: Counter | None = None,
                 timeout: int = 300) -> dict[int, list[tuple[str, str]]]:
    """
    Ein Aufruf je Chunk statt je Absatz — das spart den Grossteil der Laufzeit.
    Liefert {index: [(tag, stichwort), ...]} — ein Absatz kann zwei Funktionen
    erfuellen (z.B. Begriff einfuehren UND These aufstellen).

    Das bisher vergebene Stichwort-Vokabular geht mit in den Prompt. Ohne das
    bewertet das Modell jeden Chunk isoliert und erfindet fuer dieselbe Sache
    jedes Mal einen neuen Namen — die spaetere Strangbildung ueber Stichworte
    faellt dann in lauter Einzelfunde auseinander (gemessen: 36 Stichworte auf
    38 Tags).
    """
    if not kandidaten:
        return {}
    teile = [f"[{n}]\n{t}\n" for n, t in kandidaten]

    vok = ""
    if vokabular:
        liste = ", ".join(s for s, _ in vokabular.most_common(VOKABULAR_MAX))
        if liste:
            vok = VOKABULAR_HINWEIS.format(liste=liste)
    prompt = PROMPT.format(absaetze="\n".join(teile), vokabular=vok)

    r = requests.post(f"{ollama}/api/generate", json={
        "model": modell,
        "prompt": prompt,
        "stream": False,
        # num_ctx explizit: sonst schneidet Ollama still ab
        "options": {"temperature": 0.0, "num_ctx": 16384},
    }, timeout=timeout)
    r.raise_for_status()
    antwort = r.json().get("response", "")

    # Denkspuren mancher Modelle entfernen
    antwort = re.sub(r'<think>.*?</think>', '', antwort, flags=re.S | re.I)

    ergebnis: dict[int, list[tuple[str, str]]] = {}
    for zeile in antwort.splitlines():
        m = re.match(r'\s*\[?(\d+)\]?\s*\|\s*([a-z-]+)\s*\|?\s*(.*)', zeile.strip())
        if not m:
            continue
        idx, tag, stichwort = int(m.group(1)), m.group(2).strip(), m.group(3).strip()
        if tag not in TAGS:
            continue
        # Umlaute aufloesen: Stichworte werden spaeter gruppiert und
        # tauchen in Dateinamen auf — ASCII ist dort robuster.
        s = stichwort.lower()
        for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
            s = s.replace(a, b)
        eintrag = (tag, re.sub(r'[^\w-]+', '-', s).strip('-')[:40])

        liste = ergebnis.setdefault(idx, [])
        if any(t == tag for t, _ in liste):      # dasselbe Tag nicht doppelt
            continue
        if len(liste) >= MAX_TAGS_PRO_ABSATZ:    # Inflation begrenzen
            continue
        liste.append(eintrag)
    return ergebnis


def tagge(text: str, modell: str, ollama: str,
          vokabular: Counter | None = None) -> tuple[str, int]:
    """Liefert die getaggte Fassung und die Zahl gesetzter Tags."""
    bl = bloecke(text)
    kandidaten = [(i, b["text"]) for i, b in enumerate(bl)
                  if len(b["text"]) >= MIN_LEN and not ueberschrift(b)]
    vorschlaege = frage_modell(kandidaten, modell, ollama, vokabular)
    if not vorschlaege:
        return text, 0
    if vokabular is not None:          # Vokabular fortschreiben
        for eintraege in vorschlaege.values():
            for _, stichwort in eintraege:
                if stichwort:
                    vokabular[stichwort] += 1

    zeilen = text.splitlines()
    gesetzt = 0
    # von hinten einfuegen, damit die Zeilennummern gueltig bleiben
    for i in sorted(vorschlaege, reverse=True):
        marken = [f"%%{tag} {stichwort}%%" if stichwort else f"%%{tag}%%"
                  for tag, stichwort in vorschlaege[i]]
        for marke in reversed(marken):      # Reihenfolge des Modells erhalten
            zeilen.insert(bl[i]["start"], marke)
        gesetzt += len(marken)
    return "\n".join(zeilen) + "\n", gesetzt


def hat_tags(text: str) -> bool:
    return bool(re.search(r'(?m)^%%(' + "|".join(TAGS) + r')\b', text))


def sammle_vokabular(chunks: list[Path]) -> Counter:
    """
    Bereits vergebene Stichworte einlesen — aus den Originalen und den
    danebenliegenden .tagged.md. Bei --resume beginnt der Lauf damit nicht
    wieder bei null und benennt dieselben Themen weiter gleich.
    """
    vok = Counter()
    gesehen = set()
    for f in chunks:
        for kandidat in (f, f.with_suffix(".tagged.md")):
            if not kandidat.exists() or kandidat in gesehen:
                continue
            gesehen.add(kandidat)
            text = kandidat.read_text(encoding='utf-8', errors='replace')
            for m in re.finditer(r'(?m)^%%\w+\s+([^%]+)%%\s*$', text):
                s = m.group(1).strip()
                if s:
                    vok[s] += 1
    return vok


def finde_chunks(ziel: str) -> list[Path]:
    p = Path(ziel)
    if not (p.is_file() or p.is_dir()):
        p = LEKTOR / ziel          # relativ zum Lektor-Verzeichnis versuchen
    if p.is_file():
        return [p.resolve()]
    if not p.is_dir():
        raise SystemExit(f"[FEHLER] Nicht gefunden: {ziel}")
    d = p / "de" if (p / "de").is_dir() else p
    return sorted(d.glob("chunk_*.md"))


def main():
    ap = argparse.ArgumentParser(
        description="Analyse-Tags vorschlagen (Bestaetigung beim Korrekturlesen)"
    )
    ap.add_argument("ziel", help="Buchordner oder einzelne Chunk-Datei")
    ap.add_argument("--model", default=MODELL)
    ap.add_argument("--ollama-url", default=OLLAMA)
    ap.add_argument("--in-place", action="store_true",
                    help="Chunks direkt bearbeiten (sonst: .tagged.md daneben)")
    ap.add_argument("--resume", action="store_true",
                    help="Chunks ueberspringen, die bereits Tags tragen")
    ap.add_argument("--limit", type=int, default=0,
                    help="nur die ersten N Chunks (zum Kalibrieren)")
    ap.add_argument("--ohne-themenliste", action="store_true",
                    help="bibliotheksweite themen.json nicht als Startvokabular nutzen")
    args = ap.parse_args()

    chunks = finde_chunks(args.ziel)
    if args.limit:
        chunks = chunks[:args.limit]
    if not chunks:
        raise SystemExit("[FEHLER] Keine Chunks gefunden.")

    print("=" * 62)
    print(f"Tag-Vorschlaege | Modell: {args.model}")
    print(f"Chunks: {len(chunks)}   Ziel: "
          + ("in-place" if args.in_place else "*.tagged.md"))
    print("=" * 62)

    gesamt = uebersprungen = 0
    verteilung = Counter()

    # Stichwort-Vokabular des Buchs — waechst mit jedem Chunk und geht in den
    # naechsten Prompt ein, damit dieselbe Sache ueberall gleich heisst.
    vokabular = sammle_vokabular(chunks)
    aus_buch = len(vokabular)

    # Bibliotheksweite Themenliste als Startmenge: sonst entsteht je Buch ein
    # eigenes Stichwort-Universum und Straenge enden an der Buchgrenze.
    if not args.ohne_themenliste:
        try:
            import themen
            for t, d in themen.lade().get("themen", {}).items():
                if t not in vokabular:
                    vokabular[t] = d.get("quellen", 1)
        except Exception as e:
            print(f"[!] Themenliste nicht geladen: {e}")

    if vokabular:
        aus_liste = len(vokabular) - aus_buch
        print(f"Vokabular: {aus_buch} aus dem Buch"
              + (f", {aus_liste} aus der Themenliste" if aus_liste else "") + "\n")

    for n, f in enumerate(chunks, 1):
        text = f.read_text(encoding='utf-8', errors='replace')
        if args.resume and hat_tags(text):
            uebersprungen += 1
            continue

        ziel = f if args.in_place else f.with_suffix(".tagged.md")
        try:
            neu, anzahl = tagge(text, args.model, args.ollama_url, vokabular)
        except requests.exceptions.Timeout:
            print(f"  [{n}/{len(chunks)}] {f.name}: Timeout — uebersprungen")
            continue
        except Exception as e:
            print(f"  [{n}/{len(chunks)}] {f.name}: {e}")
            continue

        for m in re.finditer(r'(?m)^%%(\w+)', neu):
            verteilung[m.group(1)] += 1
        ziel.write_text(neu, encoding='utf-8')
        gesamt += anzahl
        print(f"  [{n}/{len(chunks)}] {f.name}: {anzahl} Tags -> {ziel.name}")

    print(f"\n{gesamt} Tags gesetzt"
          + (f", {uebersprungen} Chunks uebersprungen" if uebersprungen else ""))
    if verteilung:
        print("Verteilung: " + ", ".join(f"{t}={n}" for t, n in verteilung.most_common()))
    if not args.in_place:
        print("\nDie .tagged.md-Dateien pruefen, dann ueber die Originale kopieren.")


if __name__ == "__main__":
    main()
