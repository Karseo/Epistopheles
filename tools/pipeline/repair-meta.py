"""
repair-meta.py  —  fehlende meta.json in Buchordnern rekonstruieren

Buecher aus der Zeit vor Einfuehrung der meta.json haben keine. Schritt 3
faellt dann auf die Ordnerstruktur zurueck; Jahr, Quellsprache und
Chunk-Groesse fehlen. Dieses Skript baut die Datei aus dem nach, was im
Buchordner steht.

Quellen der Rekonstruktion:
  Autor/Titel   Ordnernamen (kuratiert — hat Vorrang vor Dateimetadaten)
  Jahr, Volltitel  Metadaten der Quelldatei in de\\ bzw. en\\
  Quellsprache  Sprachordner, in dem die Quelldatei liegt
  chunks        Anzahl chunk_*.md
  chunk_size    .progress.json, sonst Standard
  zeichen       Summe der Chunks der Quellsprache

Verwendung:
  python repair-meta.py --dry-run
  python repair-meta.py
  python repair-meta.py "Horton, Scott\\Provoked"
  python repair-meta.py --force        # auch vorhandene meta.json neu schreiben
"""

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE   = Path(os.environ.get("EBOOK_BASE", Path(__file__).resolve().parents[2] / "rohdaten"))
LEKTOR = BASE / "Lektor"
LANGS  = ("de", "en")
BUCH_EXTS = {".epub", ".pdf", ".mobi", ".azw3", ".odt", ".docx", ".fb2", ".rtf"}


def _lade_translate_modul():
    pfad = Path(__file__).parent / "ebook-translate.py"
    spec = importlib.util.spec_from_file_location("ebook_translate", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul

_et = _lade_translate_modul()


def finde_buecher(ziel: str | None) -> list[Path]:
    """Buchordner = enthaelt de\\ oder en\\ mit chunk_*.md."""
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


def finde_quelle(buch: Path) -> tuple[Path | None, str]:
    """Quelldatei und die Sprache des Ordners, in dem sie liegt."""
    for lang in LANGS:
        d = buch / lang
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.is_file() and p.suffix.lower() in BUCH_EXTS:
                return p, lang
    # Quelle einer dritten Sprache liegt im Buchordner selbst
    for p in sorted(buch.iterdir()):
        if p.is_file() and p.suffix.lower() in BUCH_EXTS:
            return p, ""
    return None, ""


def zaehle_chunks(buch: Path, lang: str) -> int:
    d = buch / lang
    return len(list(d.glob("chunk_*.md"))) if d.is_dir() else 0


def baue_meta(buch: Path) -> dict:
    autor = buch.parent.name
    titel = buch.name

    quelle, quell_lang = finde_quelle(buch)
    roh = _et.read_metadata(quelle) if quelle else {"author": "", "title": "", "year": ""}

    # Fortschrittsdatei liefert chunk_size-Kontext und die urspruengliche Quelle
    prog = {}
    pf = buch / ".progress.json"
    if pf.exists():
        try:
            prog = json.loads(pf.read_text(encoding='utf-8'))
        except Exception:
            pass

    chunks = max(zaehle_chunks(buch, l) for l in LANGS)
    total  = int(prog.get("total") or chunks)

    # Zeichenzahl der Quellfassung (bei uebernommenem Quelltext = Originaltext)
    zeichen = 0
    ref_lang = quell_lang or "en"
    d = buch / ref_lang
    if d.is_dir():
        for f in d.glob("chunk_*.md"):
            try:
                zeichen += len(f.read_text(encoding='utf-8', errors='replace'))
            except Exception:
                pass

    vollstaendig = all(zaehle_chunks(buch, l) >= total for l in LANGS) and total > 0

    return {
        "titel":        titel,
        "autor":        autor,
        "jahr":         roh.get("year", ""),
        "titel_voll":   roh.get("title", "") or titel,
        "autor_voll":   roh.get("author", "") or autor,
        "quelldatei":   str(quelle) if quelle else "",
        "original":     "",
        "quellsprache": quell_lang,
        "sprachen":     list(LANGS),
        "quelle_uebernommen": quell_lang,
        "modell":       _et.DEFAULT_MODEL,
        "chunk_size":   _et.CHUNK_SIZE,
        "chunks":       total,
        "ordner_grund": "rekonstruiert (repair-meta.py)",
        "status":       "fertig" if vollstaendig else "unvollstaendig",
        "zeichen_quelle": zeichen,
        "erstellt":     time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def main():
    ap = argparse.ArgumentParser(
        description="Fehlende meta.json in Buchordnern rekonstruieren"
    )
    ap.add_argument("buch", nargs="?", default=None,
                    help="einzelnes Buch ('<Autor>\\<Titel>' oder Pfad); ohne Angabe alle")
    ap.add_argument("--dry-run", action="store_true", help="nur anzeigen")
    ap.add_argument("--force", action="store_true",
                    help="auch vorhandene meta.json neu schreiben")
    args = ap.parse_args()

    buecher = finde_buecher(args.buch)
    if not buecher:
        print("Keine Buchordner gefunden.")
        return

    print("=" * 62)
    print(f"meta.json reparieren {'(DRY-RUN)' if args.dry_run else ''}: "
          f"{len(buecher)} Buch/Buecher geprueft")
    print("=" * 62)

    geschrieben = uebersprungen = 0
    for buch in buecher:
        kurz = f"{buch.parent.name}\\{buch.name}"
        ziel = buch / "meta.json"
        if ziel.exists() and not args.force:
            uebersprungen += 1
            continue

        m = baue_meta(buch)
        print(f"\n{kurz}")
        print(f"  Autor  : {m['autor']}")
        print(f"  Titel  : {m['titel_voll']}")
        print(f"  Jahr   : {m['jahr'] or '(unbekannt)'}")
        print(f"  Quelle : {Path(m['quelldatei']).name if m['quelldatei'] else '(fehlt)'}"
              f"  [{m['quellsprache'] or 'dritte Sprache'}]")
        print(f"  Chunks : {m['chunks']}   Status: {m['status']}")
        if not args.dry_run:
            ziel.write_text(json.dumps(m, ensure_ascii=False, indent=2),
                            encoding='utf-8')
        geschrieben += 1

    print(f"\n{geschrieben} geschrieben, {uebersprungen} hatten bereits eine meta.json.")
    if args.dry_run:
        print("(DRY-RUN — es wurde nichts geschrieben.)")


if __name__ == "__main__":
    main()
