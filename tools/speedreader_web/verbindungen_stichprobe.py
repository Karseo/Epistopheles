"""Hilfswerkzeug zur Kalibrierung der Aehnlichkeit (Plan 2026-11-03, Task 3 Schritt 5) - KEIN Test, auf APIC ausfuehren:

    python verbindungen_stichprobe.py [--qdrant http://127.0.0.1:6333] [--collection episto] [--anzahl 20] [--seed 1]
                                      [--je 10] [--mindestwerte 0.5,0.55,0.6,0.65,0.7]

Zieht `anzahl` zufaellige Kapitel, fragt Qdrant (nur lesend) nach den Nachbarn ihrer Chunks in anderen Werken und zeigt:
  * die Verteilung der Aehnlichkeitswerte (Perzentile),
  * wie viele Zielkapitel je Kapitel bei welchem Mindestwert uebrig bleiben (Ziel: typisch 4 bis 8),
  * je Kapitel die besten drei Belege (Zielkapitel, Wert, Ausschnitt) zum Gegenlesen.
Mindestwert, `je_kapitel` und Rangformel (Summe der drei besten Chunk-Paare) danach in export_verbindungen.py festlegen und die
Zahlen in den Commit schreiben."""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import qdrant_nachbarn as qn  # noqa: E402


def perzentil(werte: list[float], p: float) -> float:
    return sorted(werte)[min(len(werte) - 1, int(p * len(werte)))] if werte else float("nan")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--qdrant", default="http://127.0.0.1:6333")
    ap.add_argument("--collection", default="episto")
    ap.add_argument("--anzahl", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--je", type=int, default=10, help="Nachbarn je Chunk")
    ap.add_argument("--mindestwerte", default="0.5,0.55,0.6,0.65,0.7")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        punkte = qn.lese_punkte(args.qdrant, args.collection)
    except qn.QdrantFehler as e:
        print(f"Qdrant nicht lesbar: {e}", file=sys.stderr)
        return 1
    kapitel: dict[tuple, list[int]] = {}
    for pid, p in punkte.items():
        kapitel.setdefault((p["autor"], p["buch"], p["kapitel_nr"]), []).append(pid)
    werke = {}
    for autor, buch, _ in kapitel:
        werke.setdefault((autor, buch), f"w{len(werke) + 1:03d}")
    kapitel_ids = {f"{werke[(a, b)]}:{nr}" for a, b, nr in kapitel}
    zufall = random.Random(args.seed)
    wahl = zufall.sample(sorted(kapitel), min(args.anzahl, len(kapitel)))
    print(f"{len(punkte)} Punkte, {len(kapitel)} Kapitel, {len(werke)} Werke; Stichprobe: {len(wahl)} Kapitel")
    alle_ids = [pid for k in wahl for pid in kapitel[k]]
    erg = qn.frage_nachbarn(args.qdrant, args.collection, punkte, alle_ids, je=args.je)
    print(f"{erg.abgefragt} Chunks abgefragt ({erg.api}), {erg.fehlend} fehlgeschlagen")
    werte = [t["wert"] for ts in erg.treffer.values() for t in ts]
    print("Verteilung der Werte: " + ", ".join(f"P{int(p * 100)} {perzentil(werte, p):.3f}" for p in (0.05, 0.25, 0.5, 0.75, 0.95)))
    mindest = [float(x) for x in args.mindestwerte.split(",")]
    print("\nZielkapitel je Kapitel (Mittel / Minimum / Maximum) bei Mindestwert:")
    for m in mindest:
        zahlen = []
        for a, b, nr in wahl:
            nb = {pid: erg.treffer[pid] for pid in kapitel[(a, b, nr)] if pid in erg.treffer}
            zahlen.append(len([k for k in qn.fasse_zusammen(nb, punkte, kapitel_ids, werke, m, je_kapitel=10_000)]))
        print(f"  {m:.2f}: {sum(zahlen) / len(zahlen):5.1f} / {min(zahlen)} / {max(zahlen)}")
    print("\nBeste Belege je Kapitel (Mindestwert 0.5):")
    for a, b, nr in wahl:
        nb = {pid: erg.treffer[pid] for pid in kapitel[(a, b, nr)] if pid in erg.treffer}
        kanten = qn.fasse_zusammen(nb, punkte, kapitel_ids, werke, 0.5, je_kapitel=3)
        print(f"- {a} / {b}, Kapitel {nr}")
        for k in kanten:
            print(f"    -> {k['nach']}  {k['wert']:.3f}  {k['beleg'][:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
