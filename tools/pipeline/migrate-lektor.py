"""
migrate-lektor.py  —  Buecher vom flachen aufs zweisprachige Schema heben

Alt:  Lektor\\<Autor>\\<Titel>\\chunk_NNN.md          (implizit Deutsch)
Neu:  Lektor\\<Autor>\\<Titel>\\de\\chunk_NNN.md
      Lektor\\<Autor>\\<Titel>\\en\\chunk_NNN.md

Die deutschen Chunks werden nach de\\ verschoben. Die englische Fassung wird
aus der archivierten Quelldatei rekonstruiert: Extraktion und Chunking sind
deterministisch, bei gleicher chunk_size entsteht exakt dieselbe Aufteilung
wie beim urspruenglichen Lauf. Fehlt die Quelldatei oder war die Quelle nicht
englisch, bleibt en\\ leer und muss per ebook-translate.py --resume erzeugt
werden.

Verwendung:
  python migrate-lektor.py --dry-run          # zeigen, was passieren wuerde
  python migrate-lektor.py                    # alle Buecher migrieren
  python migrate-lektor.py "Scott Horton\\Provoked"
  python migrate-lektor.py --keine-quelle     # nur verschieben, en\\ nicht bauen
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ebook_pfade import quelle_aufloesen   # noqa: E402  alte Pfade aus meta.json auf BASE umsetzen
BASE   = Path(os.environ.get("EBOOK_BASE", Path(__file__).resolve().parents[2] / "rohdaten"))
LEKTOR = BASE / "Lektor"

# Funktionen aus Schritt 1 wiederverwenden — identische Extraktion und
# identisches Chunking sind Voraussetzung fuer die Rekonstruktion.
# Der Dateiname enthaelt einen Bindestrich, daher Laden ueber den Pfad.
def _lade_translate_modul():
    import importlib.util
    pfad = Path(__file__).parent / "ebook-translate.py"
    spec = importlib.util.spec_from_file_location("ebook_translate", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul

_et = _lade_translate_modul()


def finde_buecher(ziel: str | None) -> list[Path]:
    """Buchordner = enthaelt chunk_*.md flach ODER einen de\\-Unterordner."""
    if ziel:
        p = Path(ziel)
        if not p.is_dir():
            p = LEKTOR / ziel
        if not p.is_dir():
            raise SystemExit(f"[FEHLER] Nicht gefunden: {ziel}")
        return [p.resolve()]

    treffer = []
    for d in LEKTOR.rglob("*"):
        if not d.is_dir() or d.name in ("de", "en", "media", "argumente"):
            continue
        if any(d.glob("chunk_*.md")):
            treffer.append(d)
    return sorted(treffer)


def quelldatei(book_dir: Path, meta: dict, explizit: str | None = None) -> Path | None:
    """Quelldatei: explizit angegeben, aus meta.json, sonst im Autor-Ordner suchen."""
    if explizit:
        p = Path(explizit)
        if not p.exists():
            p = BASE / "Inbox" / explizit
        if not p.exists():
            raise SystemExit(f"[FEHLER] --quelle nicht gefunden: {explizit}")
        return p.resolve()
    q = meta.get("quelldatei", "")
    if q:
        p = quelle_aufloesen(q, BASE)
        if p.exists():
            return p
    exts = (".epub", ".pdf", ".odt", ".docx", ".fb2", ".html", ".rtf")
    for kandidat in list(book_dir.parent.glob("*")) + list(book_dir.glob("*")):
        if kandidat.is_file() and kandidat.suffix.lower() in exts:
            if kandidat.stem.lower().startswith(book_dir.name.lower()[:20]):
                return kandidat
    treffer = [p for p in book_dir.parent.glob("*")
               if p.is_file() and p.suffix.lower() in exts]
    return treffer[0] if len(treffer) == 1 else None


def migriere(book_dir: Path, dry: bool, keine_quelle: bool,
             explizite_quelle: str | None = None) -> dict:
    ergebnis = {"buch": str(book_dir), "verschoben": 0, "en_chunks": 0, "hinweis": ""}

    meta_file = book_dir / "meta.json"
    meta = {}
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding='utf-8'))
        except Exception:
            pass

    de_dir = book_dir / "de"
    flach  = sorted(book_dir.glob("chunk_*.md"))

    # ── 1. Deutsche Chunks nach de\ ───────────────────────────────────────────
    if flach:
        if not dry:
            de_dir.mkdir(exist_ok=True)
            for f in flach:
                ziel = de_dir / f.name
                if ziel.exists():
                    ergebnis["hinweis"] = "de\\ war teilweise gefuellt"
                    continue
                shutil.move(str(f), str(ziel))
        ergebnis["verschoben"] = len(flach)
    elif de_dir.is_dir() and any(de_dir.glob("chunk_*.md")):
        ergebnis["hinweis"] = "bereits migriert"

    # ── 2. Fortschrittsdatei aufs Sprachformat heben ──────────────────────────
    prog_file = book_dir / ".progress.json"
    if prog_file.exists() and not dry:
        try:
            p = json.loads(prog_file.read_text(encoding='utf-8'))
            if "completed" in p and "sprachen" not in p:
                p = {"total": p.get("total", 0), "source": p.get("source", ""),
                     "sprachen": {"de": {"completed": p.get("completed", [])}}}
                prog_file.write_text(json.dumps(p, ensure_ascii=False, indent=2),
                                     encoding='utf-8')
        except Exception as e:
            ergebnis["hinweis"] = f"progress nicht lesbar: {e}"

    # ── 3. Englische Fassung aus der Quelldatei rekonstruieren ────────────────
    en_dir = book_dir / "en"
    if keine_quelle:
        ergebnis["hinweis"] = (ergebnis["hinweis"] + " | en\\ nicht gebaut").strip(" |")
        return ergebnis
    if en_dir.is_dir() and any(en_dir.glob("chunk_*.md")):
        ergebnis["hinweis"] = (ergebnis["hinweis"] + " | en\\ vorhanden").strip(" |")
        return ergebnis

    quelle = quelldatei(book_dir, meta, explizite_quelle)
    if not quelle:
        ergebnis["hinweis"] = (ergebnis["hinweis"] + " | Quelldatei fehlt").strip(" |")
        return ergebnis

    quellsprache = (meta.get("quellsprache") or "").lower()
    if quellsprache and quellsprache != "en":
        ergebnis["hinweis"] = (
            ergebnis["hinweis"] + f" | Quelle ist '{quellsprache}', en\\ muss uebersetzt werden"
        ).strip(" |")
        return ergebnis

    chunk_size = int(meta.get("chunk_size") or _et.CHUNK_SIZE)
    try:
        lesbar, _ = _et.ensure_readable(quelle)
        text   = _et.extract_text(lesbar)
        chunks = _et.split_into_chunks(text, chunk_size)
    except SystemExit as e:
        ergebnis["hinweis"] = (ergebnis["hinweis"] + f" | Extraktion: {e}").strip(" |")
        return ergebnis
    except Exception as e:
        ergebnis["hinweis"] = (ergebnis["hinweis"] + f" | Extraktion: {e}").strip(" |")
        return ergebnis

    erwartet = int(meta.get("chunks") or 0)
    if erwartet and len(chunks) != erwartet:
        ergebnis["hinweis"] = (
            ergebnis["hinweis"]
            + f" | Chunkzahl weicht ab ({len(chunks)} statt {erwartet}) — en\\ nicht gebaut"
        ).strip(" |")
        return ergebnis

    if not dry:
        en_dir.mkdir(exist_ok=True)
        for i, c in enumerate(chunks):
            (en_dir / f"chunk_{i:03d}.md").write_text(c, encoding='utf-8')
        # Fortschritt fuer en\ eintragen
        try:
            p = json.loads(prog_file.read_text(encoding='utf-8')) if prog_file.exists() \
                else {"total": len(chunks), "source": str(quelle), "sprachen": {}}
            p.setdefault("sprachen", {})["en"] = {"completed": list(range(len(chunks)))}
            p.setdefault("total", len(chunks))
            prog_file.write_text(json.dumps(p, ensure_ascii=False, indent=2),
                                 encoding='utf-8')
        except Exception:
            pass
    ergebnis["en_chunks"] = len(chunks)
    return ergebnis


def main():
    ap = argparse.ArgumentParser(
        description="Buecher vom flachen aufs zweisprachige Schema (de\\ + en\\) heben"
    )
    ap.add_argument("buch", nargs="?", default=None,
                    help="einzelnes Buch (Pfad oder '<Autor>\\<Titel>'); ohne Angabe alle")
    ap.add_argument("--dry-run", action="store_true",
                    help="nur anzeigen, nichts aendern")
    ap.add_argument("--keine-quelle", action="store_true",
                    help="nur nach de\\ verschieben, en\\ nicht rekonstruieren")
    ap.add_argument("--quelle", default=None,
                    help="Quelldatei explizit angeben (Pfad oder Dateiname in Inbox\\); "
                         "nur zusammen mit einem einzelnen Buch sinnvoll")
    args = ap.parse_args()

    if args.quelle and not args.buch:
        raise SystemExit("[FEHLER] --quelle nur zusammen mit einem einzelnen Buch.")

    buecher = finde_buecher(args.buch)
    if not buecher:
        print("Nichts zu migrieren — kein Buch im flachen Schema gefunden.")
        return

    print("=" * 62)
    print(f"Migration {'(DRY-RUN)' if args.dry_run else ''}: {len(buecher)} Buch/Buecher")
    print("=" * 62)

    for b in buecher:
        print(f"\n{b.relative_to(LEKTOR) if LEKTOR in b.parents else b}")
        r = migriere(b, args.dry_run, args.keine_quelle, args.quelle)
        if r["verschoben"]:
            print(f"  de\\  {r['verschoben']} Chunks verschoben")
        if r["en_chunks"]:
            print(f"  en\\  {r['en_chunks']} Chunks aus Quelldatei rekonstruiert")
        if r["hinweis"]:
            print(f"  [!] {r['hinweis']}")
        if not (r["verschoben"] or r["en_chunks"] or r["hinweis"]):
            print("  nichts zu tun")

    if args.dry_run:
        print("\n(DRY-RUN — es wurde nichts geaendert.)")


if __name__ == "__main__":
    main()
