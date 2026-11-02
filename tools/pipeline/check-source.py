"""
check-source.py  —  Quelldatei gegen den Bestand pruefen, bevor sie eingelesen wird

Ein Buch kann in mehreren Ausgaben und Formaten auftauchen. Ohne Pruefung
entstehen Dubletten im Lektor-Bestand und spaeter in der Bibliothek.

Identitaet, in dieser Reihenfolge geprueft (Buecherkarton-Spec, Abschnitt 8.1):
  1. ISBN        — aus Metadaten oder Dateiname (Anna's-Archive-Konvention)
  2. Autor+Titel — normalisiert
  3. SHA-256     — erkennt nur exakt dieselbe Datei

Formatregel: **Nicht-EPUB wird durch EPUB ersetzt.** PDF-Konvertate entstehen
ueber den pypdf-Fallback und verlieren regelmaessig Text, Kapitelstruktur und
Fussnoten. Gemessen an *The Prophets of Doom*: 494.239 Zeichen aus dem PDF
gegenueber 656.426 aus dem EPUB — ein Drittel des Textes fehlte, dazu alle
Kapitelmarken und Fussnoten.

Verwendung:
  python check-source.py "<datei.epub>"      # eine Datei
  python check-source.py --inbox             # alles in Inbox\\
  python check-source.py --inbox --kurz
"""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ebook_pfade import quelle_aufloesen   # noqa: E402  alte Pfade aus meta.json auf BASE umsetzen
BASE   = Path(os.environ.get("EBOOK_BASE", Path(__file__).resolve().parents[2] / "rohdaten"))
LEKTOR = BASE / "Lektor"
INBOX  = BASE / "Inbox"

# Qualitaetsrang der Quellformate: hoeher ist besser.
# EPUB und Verwandte tragen Struktur, Metadaten und Fussnoten; PDF wird ueber
# einen Text-Extraktions-Fallback gelesen und verliert davon das meiste.
FORMAT_RANG = {
    ".epub": 3, ".fb2": 3, ".odt": 3, ".docx": 3, ".html": 3, ".htm": 3,
    ".mobi": 2, ".azw": 2, ".azw3": 2, ".lit": 2, ".prc": 2,   # via Calibre → EPUB
    ".pdf": 1,
}


def _lade_translate():
    pfad = Path(__file__).parent / "ebook-translate.py"
    spec = importlib.util.spec_from_file_location("ebook_translate", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul

_et = _lade_translate()


def isbn_aus(text: str) -> str:
    m = re.search(r'isbn13?\s*([0-9Xx\-]{10,17})', text)
    return m.group(1).replace("-", "").upper() if m else ""


def sha256(f: Path, block: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(f, "rb") as fh:
        while chunk := fh.read(block):
            h.update(chunk)
    return h.hexdigest()


def normalisiere(s: str) -> str:
    s = (s or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r'[^a-z0-9]+', '', s)


def beschreibe_quelle(datei: Path) -> dict:
    """Kennzeichen einer Quelldatei — ohne sie zu konvertieren."""
    meta = _et.read_metadata(datei)
    autor = _et.sanitize_filename(
        _et.normalize_author(meta.get("author", ""), meta.get("file_as", "")),
        _et.MAX_AUTHOR_LEN)
    titel = _et.sanitize_filename(_et.clean_title(meta.get("title", "")),
                                  _et.MAX_TITLE_LEN)
    return {
        "datei": datei,
        "endung": datei.suffix.lower(),
        "rang": FORMAT_RANG.get(datei.suffix.lower(), 0),
        "autor": autor,
        "titel": titel,
        "jahr": meta.get("year", ""),
        "isbn": meta.get("isbn", "") or isbn_aus(datei.stem),
    }


def bestand() -> list[dict]:
    """Vorhandene Buecher mit ihren Kennzeichen."""
    eintraege = []
    if not LEKTOR.is_dir():
        return eintraege
    for autor_d in sorted(LEKTOR.iterdir()):
        if not autor_d.is_dir():
            continue
        for buch in sorted(autor_d.iterdir()):
            if not buch.is_dir():
                continue
            mf = buch / "meta.json"
            meta = {}
            if mf.exists():
                try:
                    meta = json.loads(mf.read_text(encoding='utf-8'))
                except Exception:
                    pass
            quelle = quelle_aufloesen(meta.get("quelldatei", ""), BASE)
            endung = quelle.suffix.lower()
            if not endung:      # Quelle im Sprachordner suchen
                for lang in ("en", "de"):
                    for p in (buch / lang).glob("*") if (buch / lang).is_dir() else []:
                        if p.suffix.lower() in FORMAT_RANG:
                            quelle, endung = p, p.suffix.lower()
                            break
                    if endung:
                        break
            eintraege.append({
                "buch": buch,
                "autor": meta.get("autor", autor_d.name),
                "titel": meta.get("titel", buch.name),
                "isbn": meta.get("isbn", "") or isbn_aus(quelle.name),
                "quelle": quelle,
                "endung": endung,
                "rang": FORMAT_RANG.get(endung, 0),
                "chunks": len(list((buch / "de").glob("chunk_*.md")))
                          if (buch / "de").is_dir() else 0,
                "getaggt": (buch / "notizen" / "tags.md").exists(),
            })
    return eintraege


def finde_treffer(neu: dict, vorhanden: list[dict]) -> list[tuple[dict, list[str]]]:
    """Vorhandene Buecher, die dieselbe Quelle sein koennten — mit Begruendung."""
    treffer = []
    a_neu, t_neu = normalisiere(neu["autor"]), normalisiere(neu["titel"])
    for e in vorhanden:
        gruende = []
        if neu["isbn"] and e["isbn"] and neu["isbn"] == e["isbn"]:
            gruende.append("ISBN")
        a_alt, t_alt = normalisiere(e["autor"]), normalisiere(e["titel"])
        if t_neu and t_alt and (t_neu in t_alt or t_alt in t_neu):
            if not a_neu or not a_alt or a_neu in a_alt or a_alt in a_neu:
                gruende.append("Autor+Titel")
        if e["quelle"].name and e["quelle"].name == neu["datei"].name:
            gruende.append("Dateiname")
        if gruende:
            treffer.append((e, gruende))
    return treffer


def empfehlung(neu: dict, alt: dict) -> tuple[str, str]:
    """(Kurzwort, Begruendung) nach der Formatregel."""
    if neu["rang"] > alt["rang"]:
        return ("ERSETZEN",
                f"{neu['endung']} ist strukturierter als {alt['endung'] or '?'} — "
                f"Regel: nicht-EPUB durch EPUB ersetzen")
    if neu["rang"] < alt["rang"]:
        return ("VERWERFEN",
                f"vorhandene Quelle {alt['endung']} ist besser als {neu['endung']}")
    if alt["getaggt"]:
        return ("VERWERFEN", "gleiches Format, vorhandenes Buch ist bereits getaggt")
    return ("PRUEFEN", "gleiches Format — Ausgabe oder Auflage vergleichen")


def main():
    ap = argparse.ArgumentParser(
        description="Quelldatei gegen den Bestand pruefen (Dubletten, Formatregel)"
    )
    ap.add_argument("datei", nargs="?", default=None,
                    help="Quelldatei (Pfad oder Dateiname in Inbox\\)")
    ap.add_argument("--inbox", action="store_true", help="alle Dateien in Inbox\\")
    ap.add_argument("--kurz", action="store_true", help="nur eine Zeile je Datei")
    ap.add_argument("--sha", action="store_true",
                    help="zusaetzlich SHA-256 vergleichen (liest die Dateien)")
    args = ap.parse_args()

    if args.datei:
        p = Path(args.datei)
        if not p.exists():
            p = INBOX / args.datei
        if not p.exists():
            raise SystemExit(f"[FEHLER] Nicht gefunden: {args.datei}")
        dateien = [p.resolve()]
    elif args.inbox:
        dateien = sorted(f for f in INBOX.glob("*")
                         if f.is_file() and f.suffix.lower() in FORMAT_RANG)
    else:
        raise SystemExit("[FEHLER] Datei angeben oder --inbox verwenden.")

    vorhanden = bestand()
    print("=" * 70)
    print(f"Quellenpruefung: {len(dateien)} Datei(en) gegen {len(vorhanden)} Bücher")
    print("=" * 70)

    frei = kollision = 0
    for f in dateien:
        neu = beschreibe_quelle(f)
        treffer = finde_treffer(neu, vorhanden)

        if not treffer:
            frei += 1
            if args.kurz:
                print(f"  [frei]  {f.name[:62]}")
            else:
                print(f"\n{f.name[:66]}")
                print(f"  {neu['autor']} — {neu['titel']}"
                      + (f" ({neu['jahr']})" if neu["jahr"] else ""))
                print(f"  keine Kollision — kann eingelesen werden")
            continue

        kollision += 1
        alt, gruende = treffer[0]
        wort, warum = empfehlung(neu, alt)
        if args.kurz:
            print(f"  [{wort:9}] {f.name[:52]} → {alt['buch'].name[:28]}")
            continue

        print(f"\n{f.name[:66]}")
        print(f"  {neu['autor']} — {neu['titel']}"
              + (f" ({neu['jahr']})" if neu["jahr"] else "")
              + (f", ISBN {neu['isbn']}" if neu["isbn"] else ""))
        for e, g in treffer:
            print(f"  KOLLISION ({'+'.join(g)}): {e['buch'].parent.name}\\{e['buch'].name}")
            print(f"      Quelle  {e['endung'] or '?'}   Chunks {e['chunks']}"
                  + ("   getaggt" if e["getaggt"] else ""))
            if args.sha and e["quelle"].exists():
                gleich = sha256(f) == sha256(e["quelle"])
                print(f"      SHA-256 {'identisch' if gleich else 'verschieden'}")
        print(f"  → {wort}: {warum}")
        if wort == "ERSETZEN":
            print(f"      alten Ordner sichern, dann:")
            print(f'      python ebook-translate.py "{f.name}" --source-lang en')

    print(f"\n{frei} ohne Kollision, {kollision} mit Kollision.")


if __name__ == "__main__":
    main()
