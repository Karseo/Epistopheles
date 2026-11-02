"""Exportiert die KI-Felder aller getaggten Kapitel nach daten.json, der Datenquelle
des Web-Speedreaders fuer Epistopheles (Chromebook).

    python export_daten.py [--root PFAD] [--out daten.json] [--ohne-volltext] [--ohne-app]

Standardausgabe ist das Epistopheles-Paket <Bibliothek>\\reader\\export-epistopheles\\ (daten.json,
buecher\\ und die App-Dateien daneben).

Nur lesend: liest quelle\\_kapitel_index.json, notizen\\tags.json und die Kapiteltexte
der Buecher. Kapitel ohne jedes KI-Feld entfallen. Neben daten.json entsteht der
Ordner buecher\\ mit je einer Datei b001.json ... (Originaltext der Kapitel).
Das Ergebnis ist regenerierbar und reist nicht mit dem Repo (steht in .gitignore)."""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # tools\ fuer episto_tui

from episto_tui import library  # noqa: E402
from episto_tui.models import Tag  # noqa: E402
import bundle  # noqa: E402

FELDER = ("zusammenfassung", "these", "gegen", "kern", "def", "beleg")


def felder_von(tag: Tag) -> dict:
    """Die KI-Felder eines Kapitels im Schluesselformat von tags.json."""
    daten = tag.to_dict()
    return {f: daten[f] for f in FELDER}


def hat_inhalt(felder: dict) -> bool:
    return any((v.strip() if isinstance(v, str) else any(str(e).strip() for e in v))
               for v in felder.values())


def _schreibe_json(pfad: Path, daten: dict) -> None:
    pfad.write_text(json.dumps(daten, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8", newline="\n")


def exportiere(root: Path, volltext_ordner: Path | None = None) -> dict:
    """Die KI-Felder aller getaggten Kapitel. Mit `volltext_ordner` zusaetzlich je
    Buch eine Datei <id>.json mit dem Originaltext der Kapitel (Markdown). Sie
    traegt dieselbe `erstellt`-Zeit wie daten.json, damit die App Staende nicht
    mischt. Die Buch-`id` gilt nur innerhalb eines Exports."""
    erstellt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if volltext_ordner is not None:
        volltext_ordner.mkdir(parents=True, exist_ok=True)
        for alt in volltext_ordner.glob("b*.json"):        # Reste frueherer Exporte
            alt.unlink()
    buecher = []
    for buch in library.discover_books(root):
        tags = {t.datei: t for t in library.read_all_tags(buch)}
        kapitel, texte = [], {}
        for k in library.list_chapters(buch):
            tag = tags.get(k.datei)
            if tag is None:
                continue
            felder = felder_von(tag)
            if not hat_inhalt(felder):
                continue
            kapitel.append({"nr": k.nr, "titel": k.titel, "felder": felder})
            if volltext_ordner is not None:
                try:
                    texte[str(k.nr)] = library.read_chapter_text(buch, k.datei)
                except OSError:
                    pass                                     # Kapitel ohne Datei: nur KI-Felder
        if not kapitel:
            continue
        buch_id = f"b{len(buecher) + 1:03d}"
        buecher.append({"id": buch_id, "autor": buch.autor, "titel": buch.titel, "kapitel": kapitel})
        if volltext_ordner is not None:
            _schreibe_json(volltext_ordner / f"{buch_id}.json",
                           {"id": buch_id, "erstellt": erstellt, "kapitel": texte})
    return {"erstellt": erstellt, "buecher": buecher}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", help="Wurzelordner der Bibliothek (sonst EPISTO_ROOT / Standard)")
    ap.add_argument("--out", help="Ziel der daten.json (sonst <Bibliothek>\\reader\\export-epistopheles\\daten.json)")
    ap.add_argument("--ohne-volltext", action="store_true",
                    help="nur daten.json, ohne den Ordner buecher\\ mit den Originaltexten")
    ap.add_argument("--ohne-app", action="store_true", help="die App-Dateien nicht neben die Daten kopieren")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")        # Windows-Konsole (cp1252) kennt sonst kein "ü" sicher
    root = library.resolve_root(args.root, os.environ)
    out = Path(args.out) if args.out else bundle.standard_paket(root) / "daten.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    ordner = None if args.ohne_volltext else out.parent / "buecher"
    daten = exportiere(root, ordner)
    _schreibe_json(out, daten)
    if not args.ohne_app:
        bundle.kopiere_app(out.parent)
    anzahl = sum(len(b["kapitel"]) for b in daten["buecher"])
    print(f"{len(daten['buecher'])} Bücher, {anzahl} Kapitel -> {out} ({out.stat().st_size // 1024} KB)")
    if ordner is not None:
        gesamt = sum(p.stat().st_size for p in ordner.glob("b*.json"))
        print(f"Originaltexte -> {ordner} ({gesamt // (1024 * 1024)} MB in {len(daten['buecher'])} Dateien)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
