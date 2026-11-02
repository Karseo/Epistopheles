"""
detect-chapters.py  —  Kapitelstruktur aus den Chunks rekonstruieren

Pandoc erzeugt beim Zusammenfuehren der EPUB-Kapiteldateien Anker der Form

    []{#02_-_The_Rulers_and_the_Ruled.xhtml}

Sie stehen dort, wo das Kapitel beginnt — auch mitten in einem Chunk, denn die
Chunkgrenzen liegen mechanisch bei 8000 Zeichen. Markdown-Ueberschriften (##)
fehlen dagegen bei vielen Buechern voellig; wer nur danach sucht, haelt die
Gliederung faelschlich fuer nicht vorhanden.

Manche Verlage (calibre-Konvertierungen) tragen im Anker selbst nur einen
technischen Dateinamen ('part0005.html'), Kapitelnummer und -titel stehen
stattdessen in der Ueberschrift direkt danach:

    # [2: Giambattista Vico]{.italic1} {#part0005.html_toc_marker-2-2 .level}

Die Anker-ID vor '_toc_marker' verweist auf denselben Anker, der Level
('.level' fuer echte Kapitel, '.level1'/'.level3' fuer Titelei/Anhang) ist
zuverlaessiger als der Dateiname, um Vorspann zu erkennen. Wo eine solche
Ueberschrift auf einen Anker folgt, hat sie Vorrang vor der aus dem
Dateinamen geratenen Nummer/Titel.

Ausgabe: <Buch>\\kapitel.json
    kapitel[]         Nummer, Id, Titel, Startchunk, Zeichenposition
    chunk_zuordnung   je Chunk das Kapitel (bei Wechsel im Chunk: beide)

Andere Skripte lesen diese Datei, um Belegstellen mit Kapitel statt nur mit
Chunk-Nummer auszuweisen. build-chapters.py baut daraus je Kapitel eine
eigene Markdown-Datei.

Verwendung:
  python detect-chapters.py "Parvini, Neema\\The Populist Delusion"
  python detect-chapters.py --alle
  python detect-chapters.py --alle --dry-run
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE   = Path(os.environ.get("EBOOK_BASE", Path(__file__).resolve().parents[2] / "rohdaten"))
LEKTOR = BASE / "Lektor"

# Kapitel-Anker: []{#02_-_The_Rulers_and_the_Ruled.xhtml}
# Alles ausser der schliessenden Klammer zulassen: Kapiteldateinamen enthalten
# Kommas, Bindestriche und Apostrophe. Eine enge Zeichenklasse laesst einzelne
# Kapitel stillschweigend verschwinden (erlebt: Kapitel 5 fehlte in der Liste).
ANKER = re.compile(r'\[\]\{#([^}]+\.x?html)\}')
# Fallback: Markdown-Ueberschrift
HEADING = re.compile(r'(?m)^#{1,3}\s+(.+)$')

# Zweites, zuverlaessigeres Merkmal (calibre-Konvertierungen, s. Docstring):
# Ueberschrift mit Anker-ID vor '_toc_marker' und Level-Klasse.
TOC_HEADING = re.compile(
    r'(?m)^#{1,3}\s+(.+?)\s*\{#([^}]+?)_toc_marker-(\d+)-(\d+)\s+\.(level\d*)\}\s*$'
)


def toc_heading_bei(text: str, anker_id: str, ab: int, fenster: int = 800) -> dict | None:
    """
    Sucht im Ausschnitt nach `ab` eine TOC_HEADING-Ueberschrift, deren Anker-ID
    zum eben gefundenen leeren Anker []{#anker_id} passt, und liefert daraus
    Titel, Nummer (aus 'N: Titel', sonst die laufende TOC-Nummer) und Level.
    """
    for m in TOC_HEADING.finditer(text[ab:ab + fenster]):
        if m.group(2) != anker_id:
            continue
        titel = re.sub(r'\{[^}]*\}', '', m.group(1))
        titel = re.sub(r'[\[\]]', '', titel).strip()
        m_nr = re.match(r'^(\d+)\s*[:.]\s*(.+)$', titel)
        nr, titel = (m_nr.group(1), m_nr.group(2).strip()) if m_nr else (m.group(4), titel)
        return {"titel": titel, "nr": nr, "level": m.group(5), "nummeriert": bool(m_nr)}
    return None


# Fallback fuer Titelei ohne eigene Ueberschrift (Titelseite, Impressum):
# das gedruckte Inhaltsverzeichnis selbst verlinkt jeden Anker mit lesbarem
# Titel, z.B. '[Titelseite](#part0001.html_toc_marker-1-1)'.
TOC_LINK = re.compile(r'\[([^\]]{1,120})\]\(#([^)]+?)(?:_toc_marker-\d+-\d+)?\)')


def toc_link_titel(text: str, anker_id: str) -> str:
    """Titel aus dem Inhaltsverzeichnis-Eintrag desselben Chunks, sonst ''."""
    for m in TOC_LINK.finditer(text):
        if m.group(2) == anker_id:
            return m.group(1).strip()
    return ""

# Positive Kapitelmerkmale — sie schlagen den Vorspann-Filter.
# Manche Verlage haengen an JEDE Datei '-title' an, auch an die Kapitel
# (erlebt: 12_chapter-title-1.html). Ohne diese Vorrangregel verwirft der
# Filter unten die gesamte Gliederung.
KAPITEL_JA = re.compile(
    r'(chapter|kapitel|introduction|einleitung|vorwort|preface|'
    r'conclusion|fazit|schluss|nachwort|afterword|prolog|epilog|'
    r'\bpart\b|\bteil\b)', re.I)

# Dateien, die kein inhaltliches Kapitel sind
KEIN_KAPITEL = re.compile(
    r'(title|half.?title|cover|toc|table.?of.?contents|copyright|colophon|'
    r'imprint|description|dedication|acknowledge|index|illustration|'
    r'bibliograph|glossar)', re.I)


def ist_vorspann(anker_id: str) -> bool:
    """Titelei/Apparat — aber nur, wenn kein Kapitelmerkmal dagegensteht."""
    if KAPITEL_JA.search(anker_id):
        return False
    return bool(KEIN_KAPITEL.search(anker_id))

# Plausibilitaetsgrenze fuer den Ueberschriften-Fallback: hoechstens so viele
# Kapitel wie Chunks mal diesem Faktor.
#
# Ein Kapitel umfasst im 8000-Zeichen-Raster in aller Regel mehrere Chunks.
# Kommt rechnerisch mehr als ein Kapitel auf zwei Chunks, sind es keine
# Kapitel, sondern Marginalien und Seitenzahlen, die Pandoc als Ueberschriften
# ausgegeben hat. Gemessen 2026-08-20: The State Nobility 329 "Kapitel" bei
# 214 Chunks (1,54), Prophets of Doom 131 bei 69 (1,90), Democratic Elitism
# 151 bei 115 (1,31) — dagegen In Defense of Elitism 18 bei 58 (0,31), was
# tatsaechlich der Gliederung entspricht.
#
# Anker werden nicht geprueft: sie stammen aus der EPUB-Struktur und sind
# verlaesslich.
FALLBACK_MAX_ANTEIL = 0.5


def titel_aus_id(anker_id: str) -> tuple[str, str]:
    """
    '02_-_The_Rulers_and_the_Ruled.xhtml' -> ('02', 'The Rulers and the Ruled')
    'Bibliography.xhtml'                  -> ('',   'Bibliography')
    """
    # Anker sind URL-kodiert: '%2C' steht fuer das Komma im Dateinamen
    stamm = unquote(re.sub(r'\.x?html$', '', anker_id))

    # Verlagsschema 'NN_chapter-title-N': die fuehrende Zahl ist die
    # Dateireihenfolge, die hintere die Kapitelnummer. Der Titel selbst steht
    # nicht im Anker — 'Kapitel N' ist alles, was sich sicher ableiten laesst.
    m = re.search(r'chapter[-_]?(?:title[-_]?)?(\d+)\b', stamm, re.I)
    if m:
        return m.group(1), f"Kapitel {int(m.group(1))}"
    for wort, klartext in (("introduction", "Einleitung"),
                           ("einleitung", "Einleitung"),
                           ("preface", "Vorwort"), ("vorwort", "Vorwort"),
                           ("conclusion", "Fazit"), ("fazit", "Fazit"),
                           ("afterword", "Nachwort"), ("epilog", "Epilog"),
                           ("prolog", "Prolog")):
        if wort in stamm.lower():
            return "", klartext

    # Schema 'NN_-_Titel': fuehrende Zahl ist die Kapitelnummer
    m = re.match(r'^(\d+)[_\-\s]+(.*)$', stamm)
    nr, rest = (m.group(1), m.group(2)) if m else ("", stamm)
    rest = rest.strip("_-. ")
    return nr, re.sub(r'[_]+', ' ', rest).strip()


def sammle_anker(d: Path) -> list[dict]:
    """Kapitelmarken in Lesereihenfolge, mit Chunk und Position im Chunk."""
    treffer = []
    for f in sorted(d.glob("chunk_*.md")):
        if f.name.endswith(".tagged.md"):
            continue
        nr = re.search(r'chunk_(\d+)', f.name)
        chunk = int(nr.group(1)) if nr else -1
        text = f.read_text(encoding='utf-8', errors='replace')
        for m in ANKER.finditer(text):
            anker_id = m.group(1)

            # Fortsetzungsseite derselben Datei (mehrseitige Bibliografie o.ae.)
            # — keine neue Inhaltsgrenze, nur ein Seitenumbruch.
            m_split = re.search(r'_split_(\d+)\.x?html$', anker_id)
            if m_split and int(m_split.group(1)) > 0:
                continue

            kap_nr, titel = titel_aus_id(anker_id)
            vorspann = ist_vorspann(anker_id)

            # Zuverlaessigeres Merkmal, falls vorhanden: Ueberschrift mit
            # toc_marker direkt nach dem Anker (s. Docstring). Massgeblich
            # fuer Vorspann ist, ob die Ueberschrift ein 'N: Titel'-Muster
            # traegt — echte Kapitel haben das immer, Titelei/Anhang nie
            # (der Level allein unterscheidet das nicht zuverlaessig: manche
            # Verlage vergeben 'level' auch an die Titelseite).
            hinweis = toc_heading_bei(text, anker_id, m.end())
            if hinweis:
                if hinweis["titel"]:
                    titel = hinweis["titel"]
                if hinweis["nr"]:
                    kap_nr = hinweis["nr"]
                if not hinweis["nummeriert"]:
                    vorspann = True

            # Weder eine hilfreiche Ueberschrift noch ein sprechender
            # Dateiname: letzter Versuch ueber den Inhaltsverzeichnis-Eintrag
            # im selben Chunk (z.B. Titelseite, Impressum ohne eigene
            # Ueberschrift).
            if not titel or re.fullmatch(r'part\d+', titel, re.I):
                toc_titel = toc_link_titel(text, anker_id)
                if toc_titel:
                    titel = re.sub(r'^\d+\s*[:.]\s*', '', toc_titel).strip()

            # Anker ohne beschreibenden Namen (nur Ziffern) sind technische
            # Marken, keine Kapitel — erlebt: '1.xhtml' auf der Titelseite.
            if not titel or re.fullmatch(r'\d+', titel):
                continue
            treffer.append({
                "id": anker_id,
                "nr": kap_nr,
                "titel": titel,
                "chunk": chunk,
                "position": m.start(),
                "vorspann": vorspann,
            })
    return treffer


def sammle_headings(d: Path) -> list[dict]:
    """Fallback fuer Buecher ohne Anker: Markdown-Ueberschriften."""
    treffer = []
    for f in sorted(d.glob("chunk_*.md")):
        if f.name.endswith(".tagged.md"):
            continue
        nr = re.search(r'chunk_(\d+)', f.name)
        chunk = int(nr.group(1)) if nr else -1
        text = f.read_text(encoding='utf-8', errors='replace')
        for m in HEADING.finditer(text):
            titel = re.sub(r'\{[^}]*\}', '', m.group(1)).strip()
            if 2 < len(titel) < 90:
                treffer.append({
                    "id": "", "nr": "", "titel": titel,
                    "chunk": chunk, "position": m.start(), "vorspann": False,
                })
    return treffer


def chunk_liste(d: Path) -> list[int]:
    """Sortierte Chunknummern eines Sprachordners, ohne .tagged.md."""
    return sorted(int(re.search(r'chunk_(\d+)', f.name).group(1))
                  for f in d.glob("chunk_*.md")
                  if not f.name.endswith(".tagged.md"))


def struktur_aus_marken(marken: list[dict], chunks: list[int], quelle: str) -> dict:
    """
    Baut kapitel/vorspann/chunk_zuordnung/segmente aus einer Liste von Marken
    (id, nr, titel, chunk, position, vorspann) — unabhaengig davon, WIE die
    Marken gefunden wurden (Anker, Ueberschriften-Fallback oder das lokale
    LLM in suggest-structure.py). Eine gemeinsame Implementierung stellt
    sicher, dass jeder Erkennungsweg dasselbe kapitel.json-Format liefert,
    das kapitel_lookup.py und build-chapters.py lesen.
    """
    # Vorspann (Titelei, Inhaltsverzeichnis) nicht als Kapitel zaehlen,
    # aber als Marke behalten — sonst faengt Kapitel 1 zu frueh an.
    kapitel = [m for m in marken if not m["vorspann"]]

    # Je Chunk: welche Kapitel beginnen darin, und welches gilt am Chunkanfang
    zuordnung: dict[str, dict] = {}
    laufend = ""
    m_idx = 0
    for c in chunks:
        beginnt = []
        while m_idx < len(kapitel) and kapitel[m_idx]["chunk"] == c:
            beginnt.append(kapitel[m_idx])
            m_idx += 1
        eintrag = {"gilt": laufend}
        if beginnt:
            eintrag["beginnt"] = [
                {"titel": b["titel"], "nr": b["nr"], "position": b["position"]}
                for b in beginnt
            ]
            laufend = beginnt[-1]["titel"]
        eintrag["endet_in"] = laufend
        zuordnung[str(c)] = eintrag

    return {
        "quelle": quelle,
        "kapitel": [{"nr": k["nr"], "titel": k["titel"], "id": k["id"],
                     "chunk": k["chunk"], "position": k["position"]}
                    for k in kapitel],
        "vorspann": [m["titel"] for m in marken if m["vorspann"]],
        "chunk_zuordnung": zuordnung,
        # vollstaendige, geordnete Liste aller Marken (Kapitel + Vorspann)
        # mit Position — Grundlage fuer build-chapters.py
        "segmente": [{"id": m["id"], "nr": m["nr"], "titel": m["titel"],
                      "chunk": m["chunk"], "position": m["position"],
                      "vorspann": m["vorspann"]}
                     for m in marken],
    }


def baue_struktur(d: Path, max_anteil: float = FALLBACK_MAX_ANTEIL) -> dict:
    """Kapitelliste und Chunk-Zuordnung. Anker haben Vorrang vor Ueberschriften."""
    chunk_zahl = sum(1 for f in d.glob("chunk_*.md")
                     if not f.name.endswith(".tagged.md"))

    marken = sammle_anker(d)
    quelle = "anker"
    if not marken:
        marken = sammle_headings(d)
        quelle = "ueberschrift"
        # Fallback nur uebernehmen, wenn die Zahl plausibel ist
        if marken and chunk_zahl:
            anteil = len(marken) / chunk_zahl
            if anteil > max_anteil:
                return {
                    "quelle": "keine",
                    "verworfen": {
                        "grund": "Ueberschriften unplausibel",
                        "gefunden": len(marken),
                        "chunks": chunk_zahl,
                        "anteil": round(anteil, 2),
                        "grenze": max_anteil,
                    },
                    "kapitel": [], "chunk_zuordnung": {},
                }
    if not marken:
        return {"quelle": "keine", "kapitel": [], "chunk_zuordnung": {}}

    return struktur_aus_marken(marken, chunk_liste(d), quelle)


def finde_buecher(ziel: str | None) -> list[Path]:
    if ziel:
        p = Path(ziel)
        if not p.is_dir():
            p = LEKTOR / ziel
        if not p.is_dir():
            raise SystemExit(f"[FEHLER] Nicht gefunden: {ziel}")
        return [p.resolve()]
    treffer = []
    for autor in sorted(LEKTOR.iterdir()):
        if not autor.is_dir():
            continue
        for buch in sorted(autor.iterdir()):
            if buch.is_dir() and (buch / "de").is_dir():
                treffer.append(buch)
    return treffer


def main():
    ap = argparse.ArgumentParser(
        description="Kapitelstruktur aus Anker-Marken der Chunks rekonstruieren"
    )
    ap.add_argument("buch", nargs="?", default=None)
    ap.add_argument("--alle", action="store_true")
    ap.add_argument("--sprache", default="de", choices=["de", "en"])
    ap.add_argument("--max-anteil", type=float, default=FALLBACK_MAX_ANTEIL,
                    help="Plausibilitaetsgrenze fuer den Ueberschriften-Fallback: "
                         "hoechstens so viele Kapitel je Chunk (Standard 0.5)")
    ap.add_argument("--dry-run", action="store_true", help="nur anzeigen")
    args = ap.parse_args()

    if not args.buch and not args.alle:
        raise SystemExit("[FEHLER] Buch angeben oder --alle verwenden.")

    print("=" * 64)
    print(f"Kapitelerkennung{' (DRY-RUN)' if args.dry_run else ''} | Sprache: {args.sprache}")
    print("=" * 64)

    ohne = []
    for buch in finde_buecher(None if args.alle else args.buch):
        d = buch / args.sprache
        if not d.is_dir():
            continue
        s = baue_struktur(d, args.max_anteil)
        n = len(s["kapitel"])
        if not n:
            ohne.append(buch.name)
            v = s.get("verworfen")
            if v:
                print(f"\n{buch.parent.name}\\{buch.name}")
                print(f"  [verworfen] {v['gefunden']} Überschriften bei "
                      f"{v['chunks']} Chunks = {v['anteil']} je Chunk "
                      f"(Grenze {v['grenze']})")
                print("              vermutlich Marginalien, keine Kapitel")
            elif not args.alle:
                print(f"\n{buch.name}: keine Kapitelmarken gefunden.")
            continue

        geteilt = sum(1 for e in s["chunk_zuordnung"].values()
                      if e.get("beginnt") and e.get("gilt"))
        print(f"\n{buch.parent.name}\\{buch.name}")
        print(f"  {n} Kapitel aus {s['quelle']}"
              + (f", {len(s['vorspann'])} Vorspann-Marken" if s["vorspann"] else ""))
        print(f"  Chunks mit Kapitelwechsel mittendrin: {geteilt}")
        if not args.alle:
            for k in s["kapitel"]:
                nr = f"{k['nr']}. " if k["nr"] else ""
                print(f"      {nr}{k['titel'][:46]:48} ab chunk_{k['chunk']:03d}")

        if not args.dry_run:
            ziel = buch / "kapitel.json"
            ziel.write_text(json.dumps(s, ensure_ascii=False, indent=2),
                            encoding='utf-8')
            print(f"  -> {ziel}")

    if ohne:
        print(f"\nOhne Kapitelmarken ({len(ohne)}): " + ", ".join(o[:30] for o in ohne))
    if args.dry_run:
        print("(DRY-RUN — nichts geschrieben.)")


if __name__ == "__main__":
    main()
