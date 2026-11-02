"""Einen Original-Chunk neu uebersetzen und als Vorschlag ablegen (Spec 5.2, Task 12).

    python chunk-neu-uebersetzen.py --root R --buch "Autor/Titel" --chunk N
                                    [--ollama-url URL] [--model M]

Liest den Original-Chunk (`<Lektor>\\en\\chunk_NNN.md`), spielt die noch nicht angewendeten
Redaktionseintraege dieses Chunks aus dem Eingang IM SPEICHER darauf ab, uebersetzt das Ergebnis
mit `translate_chunk` aus `ebook-translate.py` und schreibt `<Lektor>\\de\\chunk_NNN.md.neu`.
`de\\chunk_NNN.md` und der Original-Chunk werden nie veraendert; ein vorhandener Vorschlag wird
vor dem Ueberschreiben gesichert. Der Uebersetzer (braucht `requests`) wird erst in `main`
geladen. Exit-Code 0 bei Erfolg, 1 sonst.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Callable

_TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_TOOLS))

import redaktion_anwenden as ra  # noqa: E402
from episto_tui.backup import backup_before_write  # noqa: E402
from redaktion import ops, protokoll  # noqa: E402


def offene_eintraege(root: Path, buch: str, chunk: int) -> list[dict]:
    """Noch nicht angewendete Eintraege der Ebene Original-Chunk fuer diesen Chunk."""
    stand = protokoll.lade_stand(root, buch)
    gueltig = [e for e in protokoll.lade_eingang(root, buch)
               if isinstance(e, dict) and isinstance(e.get("id"), str) and e["id"]]
    ergebnis = []
    for e in ops.ohne_zurueckgenommene(gueltig):
        if e.get("ebene") != ra.EBENE_CHUNK or ra._chunk_nummer(e) != chunk:
            continue
        s = stand.get(e["id"])
        status = s.get("status") if isinstance(s, dict) else "gesendet"
        if status in ra.OFFENE_STAENDE:
            ergebnis.append(e)
    return ergebnis


def uebersetze_chunk(root: Path, buch: str, chunk: int,
                     uebersetzer: Callable[[str], str], lektor: str | None = None) -> Path:
    """Schreibt `de/chunk_NNN.md.neu` und gibt den Pfad zurueck. `lektor` = Schluessel des
    Lektor-Ordners, wenn er vom Buchschluessel abweicht. Wirft ValueError bei unsicherem Buch-
    oder Lektornamen oder deutscher Quelle, OSError bei fehlendem Chunk."""
    if isinstance(chunk, bool) or not isinstance(chunk, int) or chunk < 0:
        raise ValueError("chunk muss eine Zahl ab 0 sein")
    ziel_ref = {"lektor": lektor} if lektor is not None else None
    lektor = ra.lektor_ordner(root, buch, ziel_ref)           # prueft Buch- und Lektorschluessel
    if ra.quellsprache(lektor) != "en":
        raise ValueError("Quelle ist deutsch - es gibt nichts ins Deutsche zu übersetzen")
    text = ra._lies_text(ra.chunk_datei(root, buch, chunk, ziel_ref))
    text, ergebnisse = ops.spiele_ab(text, offene_eintraege(root, buch, chunk))
    konflikte = sum(1 for r in ergebnisse if r.status == ops.STATUS_KONFLIKT)
    if konflikte:
        print(f"Hinweis: {konflikte} Eintrag/Einträge nicht anwendbar (Konflikt); "
              "der Vorschlag enthält sie nicht.", file=sys.stderr)
    neu_text = uebersetzer(text)
    if not isinstance(neu_text, str) or not neu_text.strip():
        raise RuntimeError("Der Übersetzer lieferte keinen Text")
    ziel = lektor / "de" / f"chunk_{chunk:03d}.md.neu"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    backup_before_write(lektor, ziel)
    ra._schreibe_text(ziel, neu_text)
    return ziel


def _lade_translate():
    spec = importlib.util.spec_from_file_location(
        "ebook_translate", Path(__file__).resolve().parent / "ebook-translate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Einen Chunk neu übersetzen (Vorschlag .neu)")
    ap.add_argument("--root", required=True)
    ap.add_argument("--buch", required=True)
    ap.add_argument("--chunk", type=int, required=True)
    ap.add_argument("--lektor", default=None, help="Schlüssel des Lektor-Ordners (Autor/Titel), wenn abweichend")
    ap.add_argument("--ollama-url", default=None)
    ap.add_argument("--model", default=None)
    args = ap.parse_args(argv)
    try:
        et = _lade_translate()
        url = args.ollama_url or et.OLLAMA_URL
        modell = args.model or et.DEFAULT_MODEL

        def uebersetzer(t: str) -> str:
            return et.translate_chunk(t, "en", "English", url, modell, "de", "German")

        ziel = uebersetze_chunk(Path(args.root), args.buch, args.chunk, uebersetzer, args.lektor)
    except (OSError, ValueError, RuntimeError, SystemExit, ImportError) as e:
        print(f"Fehler: {e or type(e).__name__}", file=sys.stderr)
        return 1
    print(f"Vorschlag geschrieben: {ziel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
