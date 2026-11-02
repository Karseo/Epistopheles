"""Kalibrierhilfe (kein Test): laesst Verdacht.pruefe (speedreader_web/verdacht.js) ueber zufaellige
Rohchunks aus <root>\\rohdaten\\Lektor laufen und gibt je Art die Trefferzahl aus.

    python tools/redaktion/verdacht_stichprobe.py [--root D:\\Workspace\\!Episto] [--anzahl 20] [--seed 1]

Ziel: ein Chunk hat typischerweise weniger als 15 Hinweise; sonst Schwellen in verdacht.js anpassen.
Braucht Node. Nur Standardbibliothek."""
from __future__ import annotations

import argparse
import json
import random
import shutil
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

JS = Path(__file__).resolve().parent.parent / "speedreader_web" / "verdacht.js"
SKRIPT = r"""
const V = require(process.argv[1]);
const fs = require("fs");
const pfade = JSON.parse(fs.readFileSync(0, "utf8"));
const aus = pfade.map(p => V.pruefe(fs.readFileSync(p, "utf8")).map(h => ({ art: h.art, absatz: h.absatz_index, zeile: h.zeile, grund: h.begruendung })));
process.stdout.write(JSON.stringify(aus));
"""


def chunks(root: Path, sprache: str) -> list[Path]:
    return sorted(root.glob(f"rohdaten/Lektor/*/*/{sprache}/chunk_*.md"))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--root", type=Path, default=Path(r"D:\Workspace\!Episto"))
    p.add_argument("--anzahl", type=int, default=20)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--sprache", default="de", choices=["de", "en"])
    p.add_argument("--beispiele", type=int, default=0, help="je Art so viele Beispiele (Grund) ausgeben")
    a = p.parse_args(argv)
    node = shutil.which("node")
    if not node:
        print("Node nicht gefunden", file=sys.stderr)
        return 2
    alle = chunks(a.root, a.sprache)
    if not alle:
        print(f"Keine Chunks unter {a.root}\\rohdaten\\Lektor", file=sys.stderr)
        return 2
    wahl = random.Random(a.seed).sample(alle, min(a.anzahl, len(alle)))
    lauf = subprocess.run([node, "-e", SKRIPT, str(JS)], input=json.dumps([str(x) for x in wahl]),
                          capture_output=True, text=True, encoding="utf-8", check=True)
    ergebnis = json.loads(lauf.stdout)
    summe: Counter = Counter()
    je_chunk = []
    for pfad, hinweise in zip(wahl, ergebnis):
        z = Counter(h["art"] for h in hinweise)
        summe.update(z)
        je_chunk.append(len(hinweise))
        print(f"{len(hinweise):4d}  {pfad.relative_to(a.root / 'rohdaten' / 'Lektor')}  {dict(z)}")
    print("\nSumme je Art:", dict(summe))
    print(f"Hinweise je Chunk: Median {statistics.median(je_chunk)}, Maximum {max(je_chunk)}, "
          f"Chunks >= 15: {sum(1 for n in je_chunk if n >= 15)} von {len(je_chunk)}")
    if a.beispiele:
        gesehen: Counter = Counter()
        for pfad, hinweise in zip(wahl, ergebnis):
            for h in hinweise:
                if gesehen[h["art"]] < a.beispiele:
                    gesehen[h["art"]] += 1
                    print(f"  [{h['art']}] {pfad.name} Absatz {h['absatz']} Zeile {h['zeile']}: {h['grund']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
