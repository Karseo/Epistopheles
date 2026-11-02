"""
check-metadata.py  —  Chunks je Buch auf liegen gebliebene Konvertierungs-
Metadaten pruefen und vorschlagen, wie damit zu verfahren ist

InDesign-EPUBs hinterlassen in den Pandoc-Chunks Reste, die weder Fehler noch
Fliesstext sind: Fussnoten-Referenzen als mehrfach verschachtelte Klammern,
Zeichenformat-Spans ohne sichtbare Auszeichnung, vereinzelt unbekannte
Attribut-Cluster. Uebersetzt wird das mitgeschleppt (aya-expanse:32b laesst
Referenzen unangetastet), es steht also in de\\ **und** en\\.

Fuer Schritt 3 (ebook-build.py) ist das kein Problem: --clean/--footnotes
raeumt es beim Bauen weg. Fuer Schritt 2 aber schon — dort wird der Rohtext
gelesen, getaggt und zitiert (`collect-tags.py`: "der Absatz ist der Beleg,
keine Paraphrase"). Ein Zitat mit einer InDesign-Klammerkette mitten im Satz
ist kein brauchbarer Beleg mehr.

Erkannte Kategorien:
  fussnoten     Fussnotenreferenz im InDesign-Muster, z.B.
                [[[2](#...footnote-046){._idFootnoteLink ._idGenColorInherit}]
                {#...footnote-046-backlink}]{.CharOverride-2}
                -> wird von ebook-build.py (normalize_footnotes) ohnehin zu
                   [^Kapitel-Nr]; hier gemeldet, weil es bis dahin den
                   Rohtext und jedes Zitat davon verunstaltet.
  zeichenformat [Text]{.irgendeine-Klasse} ausserhalb einer Fussnotenreferenz,
                z.B. [offensichtlich]{.CharOverride-1} oder [42]{.small} —
                Pandoc konnte eine Zeichenauszeichnung (meist kursiv, fett,
                Kapitaelchen) keinem Markdown-Attribut zuordnen und liess die
                Klasse roh stehen. Je nach Quelle heisst die Klasse anders
                (CharOverride, italic, small, link, index-locator, …), das
                Muster "sichtbarer Text + Klassenattribut direkt danach" ist
                aber immer dasselbe.

    Nicht erfasst — und bewusst nicht als Defekt gemeldet: reine Anker ohne
    Textinhalt (Kapitelmarken fuer detect-chapters.py, Seitenzahlen fuer die
    Zitate in collect-tags.py/collect-marks.py, Calibre- und Index-Anker).
    Sie sind der Grund, warum die Chunks laut Konzept "roh" bleiben, und
    tauchen typischerweise nicht in einem zitierten Absatz auf.

Verwendung:
  python check-metadata.py                              # alle Buecher, de+en
  python check-metadata.py "Parvini, Neema\\The Populist Delusion"
  python check-metadata.py "<Buch>" --sprache de
  python check-metadata.py "<Buch>" --beispiele 5
  python check-metadata.py "<Buch>" --normalize-footnotes   # Referenzen in
                                                             # den Chunks direkt
                                                             # auf [^Kap-Nr] kuerzen
"""

import argparse
import importlib.util
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE   = Path(os.environ.get("EBOOK_BASE", Path(__file__).resolve().parents[2] / "rohdaten"))
LEKTOR = BASE / "Lektor"
LANGS  = ("de", "en")


def _lade_build():
    """ebook-build.py als Modul laden — normalize_footnotes() soll nur an
    einer Stelle implementiert sein, nicht hier zusaetzlich nachgebaut werden
    (gleiches Verfahren wie check-source.py mit ebook-translate.py)."""
    pfad = Path(__file__).parent / "ebook-build.py"
    spec = importlib.util.spec_from_file_location("ebook_build", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul

_eb = _lade_build()

# [sichtbarer Text]{.klasse …} direkt hintereinander — das allgemeine Pandoc-
# Muster fuer eine Zeichenauszeichnung, die keinem Markdown-Attribut zugeordnet
# werden konnte. Erfasst CharOverride ebenso wie andere Quellen-Konventionen
# (.italic, .small, .link, .index-locator, …), s. Docstring.
ZEICHENFORMAT = re.compile(r'\[([^\[\]{}]{1,200})\]\{\.[^}]{1,80}\}')

# Klassen, die trotz des obigen Musters keine Meldung wert sind.
UNKRITISCH = ("calibre", "unnumbered")


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
            if buch.is_dir() and any((buch / l).glob("chunk_*.md")
                                     for l in LANGS if (buch / l).is_dir()):
                treffer.append(buch)
    return treffer


def pruefe_text(text: str) -> dict:
    """Zaehlt die beiden Kategorien in einem Chunk und liefert Beispiele.

    Die Fussnoten-Erkennung laeuft ueber die echte Transformation aus
    ebook-build.py: alles, was normalize_footnotes() zu [^Kap-Nr] verkuerzt,
    war eine Fussnotenreferenz. So bleiben Erkennung und spaetere Bereinigung
    zwangslaeufig synchron — die Referenz verschwindet dabei aus dem Text und
    kann darum unten nicht doppelt als Zeichenformat auftauchen.
    """
    normalisiert = _eb.normalize_footnotes(text)
    fn_treffer = re.findall(r'\[\^[^\]]+\]', normalisiert)

    zeichenformat = []
    for m in ZEICHENFORMAT.finditer(normalisiert):
        klasse = re.search(r'\{\.([^\s}]+)', m.group(0))
        if klasse and klasse.group(1) in UNKRITISCH:
            continue
        inhalt = m.group(1).strip()
        # reine Zahlen/Symbole sind Seiten- oder Registerverweise, keine
        # Auszeichnung an sichtbarem Fliesstext
        if not inhalt or inhalt.isdigit() or not re.search(r'[^\W\d_]', inhalt):
            continue
        zeichenformat.append(m.group(0))

    return {
        "fussnoten": len(fn_treffer),
        "fussnoten_beispiele": fn_treffer,
        "zeichenformat": len(zeichenformat),
        "zeichenformat_beispiele": zeichenformat,
    }


def kurz_liste(beispiele: list[str], n: int) -> list[str]:
    out = []
    for b in beispiele[:n]:
        b = re.sub(r'\s+', ' ', b).strip()
        out.append(b if len(b) <= 90 else b[:87] + "…")
    return out


def normalisiere_fussnoten_in_datei(pfad: Path) -> bool:
    """Schreibt eine Chunk-Datei mit gekuerzten Fussnotenreferenzen zurueck.
    Ruehrt sonst nichts an — Tags (%%…%%) und Hervorhebungen (==…==) bleiben
    unberuehrt, weil die Regex ausschliesslich auf footnote-Anker zielt."""
    alt = pfad.read_text(encoding='utf-8', errors='replace')
    neu = _eb.normalize_footnotes(alt)
    if neu == alt:
        return False
    pfad.write_text(neu, encoding='utf-8', newline='\n')
    return True


def main():
    ap = argparse.ArgumentParser(
        description="Chunks auf InDesign-/Pandoc-Metadatenreste pruefen"
    )
    ap.add_argument("buch", nargs="?", default=None)
    ap.add_argument("--sprache", choices=["de", "en", "beide"], default="beide")
    ap.add_argument("--beispiele", type=int, default=2,
                    help="Beispielausschnitte je Kategorie und Buch (Standard 2)")
    ap.add_argument("--normalize-footnotes", action="store_true",
                    help="Fussnotenreferenzen in den Chunks direkt auf "
                         "[^Kapitel-Nr] kuerzen (nur mit Buchangabe)")
    args = ap.parse_args()

    if args.normalize_footnotes and not args.buch:
        raise SystemExit("[FEHLER] --normalize-footnotes braucht ein bestimmtes Buch.")

    sprachen = LANGS if args.sprache == "beide" else (args.sprache,)
    buecher = finde_buecher(args.buch)

    print("=" * 72)
    print(f"Metadaten-Pruefung{' + Kuerzung' if args.normalize_footnotes else ''}: "
          f"{len(buecher)} Buch/Buecher")
    print("=" * 72)

    gesamt = {"fussnoten": 0, "zeichenformat": 0}
    fehlende_footnotes_md = []

    for buch in buecher:
        buch_befund = {"fussnoten": 0, "zeichenformat": 0}
        buch_beispiele = {"fussnoten": [], "zeichenformat": []}
        gekuerzte_dateien = 0

        for lang in sprachen:
            d = buch / lang
            if not d.is_dir():
                continue
            fussnoten_in_sprache = 0
            for f in sorted(d.glob("chunk_*.md")):
                text = f.read_text(encoding='utf-8', errors='replace')
                befund = pruefe_text(text)
                fussnoten_in_sprache += befund["fussnoten"]
                for k in ("fussnoten", "zeichenformat"):
                    buch_befund[k] += befund[k]
                    buch_beispiele[k].extend(befund[f"{k}_beispiele"])

                if args.normalize_footnotes and lang == "de" and befund["fussnoten"]:
                    if normalisiere_fussnoten_in_datei(f):
                        gekuerzte_dateien += 1

            if fussnoten_in_sprache and not (d / "footnotes.md").exists():
                fehlende_footnotes_md.append(f"{buch.parent.name}\\{buch.name} [{lang}]")

        if not any(buch_befund.values()):
            continue

        print(f"\n{buch.parent.name}\\{buch.name}")
        if buch_befund["fussnoten"]:
            print(f"  Fussnoten-Referenzen (InDesign): {buch_befund['fussnoten']}x")
            for b in kurz_liste(buch_beispiele["fussnoten"], args.beispiele):
                print(f"      {b}")
        if buch_befund["zeichenformat"]:
            print(f"  Zeichenformat-Reste ([Text]{{.Klasse}}): {buch_befund['zeichenformat']}x")
            for b in kurz_liste(buch_beispiele["zeichenformat"], args.beispiele):
                print(f"      {b}")

        for k in gesamt:
            gesamt[k] += buch_befund[k]

        if args.normalize_footnotes and gekuerzte_dateien:
            print(f"  -> Fussnotenreferenzen in {gekuerzte_dateien} de-Chunk(s) auf "
                  f"[^Kapitel-Nr] gekuerzt.")

    if not any(gesamt.values()):
        print("\nKeine liegen gebliebenen Metadatenreste gefunden.")
        return

    print("\n" + "-" * 72)
    print(f"Insgesamt: {gesamt['fussnoten']}x Fussnoten-Referenzen, "
          f"{gesamt['zeichenformat']}x Zeichenformat-Reste.")

    print("\nVorschlag zum Verfahren:")
    if gesamt["fussnoten"]:
        print("  Fussnoten-Referenzen: kein Fehler — ebook-build.py normalisiert sie beim")
        print("  Bauen automatisch zu [^Kapitel-Nr] (--footnotes/--clean). Sie stoeren aber")
        print("  jedes Zitat in Schritt 2 (notizen\\tags.md, notizen\\hervorhebungen.md).")
        if fehlende_footnotes_md:
            print("  Fussnotentexte fehlen noch fuer:")
            for e in fehlende_footnotes_md:
                print(f"    python extract-footnotes.py \"{e.split(' [')[0]}\"")
        print("  Danach optional direkt in den Chunks kuerzen:")
        print(f"    python check-metadata.py \"<Buch>\" --normalize-footnotes")
    if gesamt["zeichenformat"]:
        print("  Zeichenformat-Reste: vermutlich verlorene Kursiv-/Fett-/Kapitaelchen-")
        print("  Auszeichnung oder ein Register-/Verweiselement der Quelle. Keine")
        print("  automatische Korrektur — an den Beispielen oben reicht meist ein Blick,")
        print("  ob es sich um Fliesstext (dann im Quell-EPUB nachsehen, welche")
        print("  Auszeichnung die Klasse traegt) oder um Register/Apparat handelt (dann")
        print("  unkritisch, wie fix-chunks.py es auch fuer die Sprachpruefung behandelt).")


if __name__ == "__main__":
    main()
