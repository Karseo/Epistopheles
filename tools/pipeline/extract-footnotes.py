"""
extract-footnotes.py  —  Fussnotentexte aus dem Quell-EPUB nachziehen

Pandoc verliert bei InDesign-EPUBs die Fussnotentexte: im Chunk-Bestand
stehen nur die Referenzen, die Ziele fehlen. Dieses Skript liest die
Fussnoten direkt aus dem EPUB und legt sie als Pandoc-Definitionen ab.

Eingabe : Quell-EPUB im Buchordner (<Buch>\\<lang>\\*.epub)
Ausgabe : <Buch>\\<lang>\\footnotes.md   mit Zeilen der Form
              [^01-011]: Text der Fussnote

Der Bezeichner ist derselbe wie in ebook-build.py (normalize_footnotes):
Kapitelnummer aus dem Dateinamen + Nummer aus der Anker-ID. Damit passen
Referenz und Definition im Gesamttext zusammen.

Verwendung:
  python extract-footnotes.py "Parvini, Neema\\The Populist Delusion"
  python extract-footnotes.py --alle
  python extract-footnotes.py --alle --dry-run
"""

import argparse
import os
import re
import sys
import warnings
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
warnings.filterwarnings("ignore")

from bs4 import BeautifulSoup

BASE   = Path(os.environ.get("EBOOK_BASE", Path(__file__).resolve().parents[2] / "rohdaten"))
LEKTOR = BASE / "Lektor"
LANGS  = ("en", "de")


def finde_epub(buch: Path) -> tuple[Path | None, str]:
    """Quell-EPUB und der Sprachordner, in dem es liegt."""
    for lang in LANGS:
        d = buch / lang
        if d.is_dir():
            for p in sorted(d.iterdir()):
                if p.is_file() and p.suffix.lower() == ".epub":
                    return p, lang
    for p in sorted(buch.iterdir()):
        if p.is_file() and p.suffix.lower() == ".epub":
            return p, LANGS[0]
    return None, ""


def kapitelnummer(dateiname: str) -> str:
    """'OEBPS/01_-_Introduction.xhtml' -> '01'; ohne fuehrende Zahl -> ''."""
    m = re.match(r'(\d+)', Path(dateiname).name)
    return m.group(1) if m else ""


def saeubere(text: str) -> str:
    """
    Einzeilig machen und den Ruecksprung-Marker am Anfang entfernen.
    Pandoc-Fussnotendefinitionen duerfen nicht umbrechen, sonst reisst die
    Zuordnung ab.
    """
    t = re.sub(r'\s+', ' ', text).strip()
    # fuehrende Fussnotennummer bzw. Pfeil aus dem Ruecksprung-Link
    t = re.sub(r'^[←↩↑\*†‡]\s*', '', t)
    t = re.sub(r'^\d{1,3}[\.\)\s]\s*', '', t)
    return t.strip()


def extrahiere(epub_pfad: Path) -> dict[str, str]:
    """Liefert {bezeichner: fussnotentext} aus allen Kapiteldateien."""
    noten: dict[str, str] = {}
    with zipfile.ZipFile(epub_pfad) as z:
        dokumente = [n for n in z.namelist()
                     if n.lower().endswith((".xhtml", ".html"))]
        for name in sorted(dokumente):
            kap = kapitelnummer(name)
            if not kap:
                continue          # Cover, Titelei, Inhaltsverzeichnis
            soup = BeautifulSoup(z.read(name).decode("utf-8", errors="replace"),
                                 "lxml")
            for el in soup.find_all(id=re.compile(r'footnote-\d+$')):
                m = re.search(r'footnote-(\d+)$', el.get("id", ""))
                if not m:
                    continue
                text = saeubere(el.get_text(" ", strip=True))
                if text:
                    noten[f"{kap}-{m.group(1)}"] = text
    return noten


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
            if buch.is_dir() and any((buch / l).is_dir() for l in LANGS):
                treffer.append(buch)
    return treffer


def referenzen_im_bestand(buch: Path, lang: str) -> set[str]:
    """Welche Fussnoten-Bezeichner kommen in den Chunks tatsaechlich vor?"""
    gefunden = set()
    d = buch / lang
    if not d.is_dir():
        return gefunden
    muster = re.compile(r'footnote-(\d+)')
    kap = re.compile(r'#(\d+)[^)]*?footnote-(\d+)')
    for f in d.glob("chunk_*.md"):
        t = f.read_text(encoding='utf-8', errors='replace')
        for m in kap.finditer(t):
            gefunden.add(f"{m.group(1)}-{m.group(2)}")
        for m in re.finditer(r'\[\^([\w-]+)\]', t):
            gefunden.add(m.group(1))
    return gefunden


def main():
    ap = argparse.ArgumentParser(
        description="Fussnotentexte aus dem Quell-EPUB als Pandoc-Definitionen ablegen"
    )
    ap.add_argument("buch", nargs="?", default=None,
                    help="Buchordner ('<Autor>\\<Titel>' oder Pfad)")
    ap.add_argument("--alle", action="store_true", help="alle Buecher durchgehen")
    ap.add_argument("--dry-run", action="store_true", help="nur anzeigen")
    args = ap.parse_args()

    if not args.buch and not args.alle:
        raise SystemExit("[FEHLER] Buch angeben oder --alle verwenden.")

    buecher = finde_buecher(None if args.alle else args.buch)
    print("=" * 62)
    print(f"Fussnoten-Extraktion{' (DRY-RUN)' if args.dry_run else ''}: "
          f"{len(buecher)} Buch/Buecher")
    print("=" * 62)

    for buch in buecher:
        epub, lang = finde_epub(buch)
        if not epub:
            continue
        noten = extrahiere(epub)
        if not noten:
            if not args.alle:
                print(f"\n{buch.name}: keine Fussnoten im EPUB gefunden.")
            continue

        refs = referenzen_im_bestand(buch, lang)
        treffer = set(noten) & refs if refs else set()

        print(f"\n{buch.parent.name}\\{buch.name}  [{lang}]")
        print(f"  Fussnoten im EPUB      : {len(noten)}")
        print(f"  Referenzen in Chunks   : {len(refs)}")
        print(f"  davon mit Definition   : {len(treffer)}")
        ohne = refs - set(noten)
        if ohne:
            print(f"  Referenzen ohne Text   : {len(ohne)}  "
                  f"({', '.join(sorted(ohne)[:6])}{' …' if len(ohne) > 6 else ''})")

        if not args.dry_run:
            zeilen = [f"[^{k}]: {noten[k]}" for k in sorted(noten)]
            inhalt = "\n\n".join(zeilen) + "\n"
            # In BEIDE Sprachordner schreiben, nicht nur in den der Quelldatei:
            # die Fussnoten-Bezeichner (Kapitel-Nr aus normalize_footnotes)
            # sind sprachunabhaengig, die uebersetzte Fassung braucht dieselbe
            # Datei ebenso wie die uebernommene Quelle (ebook-build.py und
            # build-chapters.py suchen footnotes.md je im eigenen Sprachordner).
            for zl in LANGS:
                d = buch / zl
                if d.is_dir() and any(d.glob("chunk_*.md")):
                    (d / "footnotes.md").write_text(inhalt, encoding='utf-8')
                    print(f"  -> {d / 'footnotes.md'}")


if __name__ == "__main__":
    main()
