"""Exportiert die Daten fuer die geteilte Korrekturansicht (korrektur.html) auf
Epistopheles: je Buch die Quelldatei (PDF/EPUB), die extrahierten Rohchunks
(chunk_NNN.md) und den bereinigten Kapiteltext (quelle\\*.md).

    python export_korrektur.py [--root PFAD] [--lektor PFAD] [--out korrektur]
                               [--ohne-ebooks] [--ohne-app]

Standardausgabe ist das Epistopheles-Paket <Bibliothek>\\reader\\export-epistopheles\\ (Ordner korrektur
und die App-Dateien daneben).

Quellen:
  * Lektor-Ordner (Standard <Bibliothek>\\rohdaten\\Lektor, oder --lektor / EPISTO_LEKTOR):
    Lektor\\<Autor>\\<Titel>\\en|de\\ mit der Quelldatei und den chunk_NNN.md. Liegt die
    Quelldatei in en\\ (fremdsprachige Quelle), sind en\\chunk_* die Rohchunks und de\\chunk_*
    die Uebersetzung; liegt sie in de\\ (deutsche Quelle), sind de\\chunk_* die Rohchunks.
  * Lektor\\<Autor>\\<Titel>\\kapitel.json: Kapitelgrenzen (segmente: chunk, position) fuer die Zuordnung Chunk <-> Kapitel.
  * rohdaten\\en-chunks\\<Autor>\\<Titel>\\: Rueckfall fuer Rohchunks, wo der Lektor keine hat.
  * Bibliothek (--root): quelle\\*.md als bereinigter Kapiteltext.
Das Ergebnis (Ordner `korrektur`: index.json, k001.json ..., k001.pdf/.epub ...) ist
regenerierbar und steht in .gitignore. Anders als export_daten.py enthaelt es ALLE Buecher,
auch noch nicht getaggte oder noch nicht ins Repo uebernommene: Korrekturlesen passiert
vor dem Taggen. Nur lesend gegenueber Lektor und Bibliothek."""
from __future__ import annotations
import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # tools\ fuer episto_tui

from episto_tui import library  # noqa: E402
import bundle  # noqa: E402

EBOOK_ENDUNGEN = (".pdf", ".epub")


def _schreibe_json(pfad: Path, daten: dict) -> None:
    pfad.write_text(json.dumps(daten, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8", newline="\n")


def dateiname_von(pfad: str) -> str:
    """Dateiname aus einem Pfad beider Schreibweisen (meta.json stammt von Windows oder WSL)."""
    return pfad.replace("\\", "/").rstrip("/").split("/")[-1] if pfad else ""


def _meta(ordner: Path) -> dict:
    return library._lade_json_dict(ordner / "meta.json") or {}


def _chunks_in(ordner: Path) -> list[Path]:
    return sorted(ordner.glob("chunk_*.md")) if ordner.is_dir() else []


def finde_quelle(lektor_buch: Path, meta: dict) -> tuple[Path | None, Path | None]:
    """(Quelldatei, Chunk-Ordner) eines Lektor-Buchs. Die Quelldatei wird zuerst ueber den
    in meta.json genannten Dateinamen gesucht (en\\, de\\, Buchordner), sonst die erste
    PDF/EPUB in dieser Reihenfolge. Rohchunks stehen im Ordner der Quelldatei; hat der
    keine, im anderen Sprachordner."""
    kandidaten: list[Path] = []
    for unter in ("en", "de", ""):
        ordner = lektor_buch / unter if unter else lektor_buch
        if ordner.is_dir():
            kandidaten += sorted(p for p in ordner.iterdir() if p.is_file() and p.suffix.lower() in EBOOK_ENDUNGEN)
    gewuenscht = dateiname_von(str(meta.get("quelldatei") or "")).lower()
    quelle = next((p for p in kandidaten if p.name.lower() == gewuenscht), kandidaten[0] if kandidaten else None)

    erst = quelle.parent if quelle is not None and quelle.parent.name in ("en", "de") else lektor_buch / "en"
    zweit = lektor_buch / ("de" if erst.name == "en" else "en")
    chunk_ordner = next((o for o in (erst, zweit) if _chunks_in(o)), None)
    return quelle, chunk_ordner


def pfad_aus_meta(quelldatei: str, ebooks: Path | None = None) -> Path | None:
    """Quellpfad aus meta.json (Windows- oder WSL-Schreibweise) als Path dieses Rechners.
    Gibt es die Datei dort nicht und nennt der Pfad einen Ordner `eBooks` (alter Ablageort, z. B.
    C:\\Users\\Dude\\Tools\\eBooks\\Inbox\\x.epub), wird sie unter `ebooks` neu aufgesetzt, sofern sie
    dort existiert."""
    if not quelldatei:
        return None
    s = quelldatei.replace("\\", "/")
    if s.startswith("/mnt/") and len(s) > 6 and s[6] == "/":
        s = f"{s[5].upper()}:{s[6:]}"                        # /mnt/c/x -> C:/x
    pfad = Path(s)
    if ebooks is not None and not pfad.exists():
        teile = pfad.parts
        for i in range(len(teile) - 1, -1, -1):
            if teile[i].lower() == "ebooks":
                neu = Path(ebooks).joinpath(*teile[i + 1:])
                if neu.exists():
                    return neu
                break
    return pfad


def _normal(text: str) -> str:
    return "".join(c for c in text.casefold() if c.isalnum())


def _lektor_buch_ordner(lektor: Path) -> list[Path]:
    """Alle Buchordner des Lektors (Lektor\\<Autor>\\<Titel> mit en\\ oder de\\)."""
    ordner = []
    for autor in sorted(p for p in lektor.iterdir() if p.is_dir()):
        for titel in sorted(p for p in autor.iterdir() if p.is_dir()):
            if (titel / "en").is_dir() or (titel / "de").is_dir():
                ordner.append(titel)
    return ordner


def _lektor_aus_meta(meta: dict, lektor: Path) -> Path | None:
    """Buchordner im Lektor, den der Quellpfad aus meta.json nennt (Lektor\\<A>\\<T>\\en\\... oder
    Lektor\\<Ordner>\\en\\...), falls es ihn gibt."""
    pfad = pfad_aus_meta(str(meta.get("quelldatei") or ""))
    if pfad is None:
        return None
    teile = pfad.parts
    namen = [t.lower() for t in teile]
    if lektor.name.lower() not in namen:
        return None
    rest = teile[namen.index(lektor.name.lower()) + 1:]
    for kandidat in ([lektor / rest[0] / rest[1]] if len(rest) >= 2 else []) + ([lektor / rest[0]] if rest else []):
        if kandidat.is_dir() and ((kandidat / "en").is_dir() or (kandidat / "de").is_dir()):
            return kandidat
    return None


def _buchliste(root: Path, lektor: Path | None) -> list[dict]:
    """Vereinigung aus Bibliothek (reader\\<A>\\<T>) und Lektor, sortiert nach Autor/Titel.
    Ein Bibliotheksbuch wird seinem Lektor-Ordner zugeordnet: gleicher Name, sonst der Pfad in
    seiner meta.json, sonst ein eindeutig aehnlicher Titel (O'Neil/Piano haben abweichende
    Ordnernamen). Liegt die Quelldatei laut meta.json ausserhalb des Lektors (z. B. Inbox),
    wird sie als `direkt` mitgenommen."""
    lektor_ordner = _lektor_buch_ordner(lektor) if lektor is not None and lektor.is_dir() else []
    frei = {p: p for p in lektor_ordner}
    eintraege: list[dict] = []
    offen: list[dict] = []
    for buch in library.discover_books(root):
        meta = _meta(buch.pfad)
        e = {"autor": buch.autor, "titel": buch.titel, "buch": buch, "lektor": None, "direkt": None}
        gleich = next((p for p in frei if p.parent.name == buch.autor and p.name == buch.titel), None)
        ordner = gleich or (_lektor_aus_meta(meta, lektor) if lektor else None)
        if ordner is not None and ordner in frei:
            e["lektor"] = frei.pop(ordner)
        else:
            offen.append(e)
        direkt = pfad_aus_meta(str(meta.get("quelldatei") or ""), lektor.parent if lektor is not None else None)
        if direkt is not None and direkt.suffix.lower() in EBOOK_ENDUNGEN and direkt.is_file():
            e["direkt"] = direkt
        eintraege.append(e)
    for e in offen:                                                    # eindeutige Titelaehnlichkeit
        n = _normal(e["titel"])
        treffer = [p for p in frei if len(n) >= 8 and (_normal(p.name) == n or _normal(p.name).startswith(n) or n.startswith(_normal(p.name)))]
        if len(treffer) == 1:
            e["lektor"] = frei.pop(treffer[0])
    for p in frei:                                                     # nur im Lektor vorhanden
        eintraege.append({"autor": p.parent.name, "titel": p.name, "buch": None, "lektor": p, "direkt": None})
    return sorted(eintraege, key=lambda e: (e["autor"], e["titel"]))


def lies_kapitelgrenzen(lektor_buch: Path | None) -> list[dict]:
    """Kapitelgrenzen eines Lektor-Buchs aus <Lektor>\\kapitel.json (`segmente`: chunk, position): nur die
    noetigen Felder, nach (chunk, position) sortiert. Leer bei fehlender oder kaputter Datei."""
    if lektor_buch is None:
        return []
    daten = library._lade_json_dict(lektor_buch / "kapitel.json")
    segmente = daten.get("segmente") if daten else None
    if not isinstance(segmente, list):
        return []
    erg = []
    for s in segmente:
        try:
            erg.append({"nr": str(s.get("nr") or ""), "titel": str(s.get("titel") or ""), "chunk": int(s["chunk"]),
                        "position": int(s.get("position") or 0), "vorspann": bool(s.get("vorspann"))})
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
    return sorted(erg, key=lambda s: (s["chunk"], s["position"]))


def exportiere(root: Path, ordner: Path, lektor: Path | None = None, ebooks: bool = True) -> dict:
    """Schreibt index.json, die Buchdateien (und Ebooks) nach `ordner`, gibt den Index zurueck.
    Rohdaten-Quellen: der Lektor (Chunks, Quelldatei, Kapitelgrenzen) und, wo der Lektor keine Chunks hat,
    rohdaten\\en-chunks\\<Autor>\\<Titel>."""
    rohdaten = lektor.parent if lektor is not None else root / "rohdaten"
    erstellt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ordner.mkdir(parents=True, exist_ok=True)
    for alt in ordner.iterdir():                                     # Reste frueherer Exporte
        if alt.is_file() and (alt.name == "index.json" or (alt.name.startswith("k") and alt.suffix in (".json", *EBOOK_ENDUNGEN))):
            alt.unlink()
    buecher = []
    for nr, eintrag in enumerate(_buchliste(root, lektor), start=1):
        buch_id = f"k{nr:03d}"
        lektor_buch: Path | None = eintrag["lektor"]
        meta = _meta(lektor_buch) if lektor_buch else (_meta(eintrag["buch"].pfad) if eintrag["buch"] else {})
        quelle, chunk_ordner = finde_quelle(lektor_buch, meta) if lektor_buch else (None, None)
        if quelle is None:
            quelle = eintrag["direkt"]                       # z. B. EPUB aus der Inbox ohne Lektor-Ordner
        chunks = [p.read_text(encoding="utf-8") for p in _chunks_in(chunk_ordner)] if chunk_ordner else []
        chunk_quelle, chunk_sprache = ("lektor", chunk_ordner.name) if chunks else ("", "")
        if not chunks:                                       # Rueckfall: die englischen Referenzchunks des Buchs
            en_chunks = _chunks_in(rohdaten / "en-chunks" / eintrag["autor"] / eintrag["titel"])
            if en_chunks:
                chunks = [p.read_text(encoding="utf-8") for p in en_chunks]
                chunk_quelle, chunk_sprache = "en-chunks", "en"
        segmente = lies_kapitelgrenzen(lektor_buch)
        # Uebersetzung: bei fremdsprachiger Quelle (Rohchunks in en\) die de\chunk_* daneben
        uebersetzung = ([p.read_text(encoding="utf-8") for p in _chunks_in(lektor_buch / "de")]
                        if lektor_buch is not None and chunk_ordner is not None and chunk_ordner.name == "en" else [])
        kapitel = []
        if eintrag["buch"] is not None:
            for k in library.list_chapters(eintrag["buch"]):
                try:
                    kapitel.append({"nr": k.nr, "titel": k.titel, "text": library.read_chapter_text(eintrag["buch"], k.datei)})
                except OSError:
                    continue
        ebook = ""
        if ebooks and quelle is not None:
            ebook = buch_id + quelle.suffix.lower()
            shutil.copyfile(quelle, ordner / ebook)
        _schreibe_json(ordner / f"{buch_id}.json",
                       {"id": buch_id, "erstellt": erstellt, "chunks": chunks, "uebersetzung": uebersetzung,
                        "segmente": segmente, "kapitel": kapitel})
        buecher.append({
            "id": buch_id, "autor": eintrag["autor"], "titel": eintrag["titel"],
            "quellsprache": str(meta.get("quellsprache") or ""),
            "quelldatei": quelle.name if quelle is not None else dateiname_von(str(meta.get("quelldatei") or "")),
            "ebook": ebook,
            "chunkSprache": chunk_sprache,
            "chunkQuelle": chunk_quelle,
            "chunks": len(chunks),
            "uebersetzung": len(uebersetzung),
            "segmente": len(segmente),
            "kapitel": [{"nr": k["nr"], "titel": k["titel"]} for k in kapitel],
        })
    index = {"erstellt": erstellt, "buecher": buecher}
    _schreibe_json(ordner / "index.json", index)
    return index


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", help="Wurzelordner der Bibliothek (sonst EPISTO_ROOT / Standard)")
    ap.add_argument("--lektor", help="Lektor-Ordner (sonst EPISTO_LEKTOR, sonst <Bibliothek>\\rohdaten\\Lektor)")
    ap.add_argument("--out", help="Zielordner (sonst <Bibliothek>\\reader\\export-epistopheles\\korrektur)")
    ap.add_argument("--ohne-ebooks", action="store_true", help="PDF/EPUB nicht in den Export kopieren")
    ap.add_argument("--ohne-app", action="store_true", help="die App-Dateien nicht neben den Ordner kopieren")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    root = library.resolve_root(args.root, os.environ)
    lektor = Path(args.lektor or os.environ.get("EPISTO_LEKTOR") or root / library.ROHDATEN_ORDNER / "Lektor")
    if not lektor.is_dir():
        print(f"Hinweis: Lektor-Ordner nicht gefunden ({lektor}): ohne Quelldateien und Rohchunks.")
        lektor = None
    out = Path(args.out) if args.out else bundle.standard_paket(root) / "korrektur"
    index = exportiere(root, out, lektor, ebooks=not args.ohne_ebooks)
    if not args.ohne_app:
        bundle.kopiere_app(out.parent)
    mit_chunks = sum(1 for b in index["buecher"] if b["chunks"])
    mit_ebook = sum(1 for b in index["buecher"] if b["ebook"])
    gesamt = sum(p.stat().st_size for p in out.iterdir() if p.is_file())
    print(f"{len(index['buecher'])} Bücher ({mit_chunks} mit Rohchunks, {mit_ebook} mit Ebook) -> {out} ({gesamt // (1024 * 1024)} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
