# -*- coding: utf-8 -*-
"""Einmal-Helfer: kapitel.json fuer Buchter 'Wer wird Milliardär' bauen.
Kapiteltitel stehen in den H1-Zeilen mit title="..."-Attribut (Campus-EPUB,
technische ISBN-Anker ohne lesbaren Namen)."""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BUCH = Path(__file__).resolve().parents[2] / "rohdaten" / "Lektor" / "Buchter, Heike" / "Wer wird Milliardär"
DE = BUCH / "de"
ZIEL = BUCH / "kapitel.json"

HEADING = re.compile(r'(?m)^# .*?title="([^"]+)"[^\n]*$')

segmente = []
for f in sorted(DE.glob("chunk_*.md")):
    if not re.fullmatch(r"chunk_\d+\.md", f.name):
        continue
    chunk = int(re.search(r"chunk_(\d+)", f.name).group(1))
    text = f.read_text(encoding="utf-8", errors="replace")
    for m in HEADING.finditer(text):
        titel = m.group(1).strip()
        zeile = m.group(0)
        # Klassifikation: Backmatter vs. Sachkapitel
        if ".appendix" in zeile or ".impress" in zeile or "Backmatter" in zeile:
            vorspann = True
        else:
            vorspann = False
        # Nummer abspalten (Konvention: nr separat, Titel ohne Nummer)
        m_nr = re.match(r'^(\d+)\s+(.+)$', titel)
        nr, titel_clean = (m_nr.group(1), m_nr.group(2).strip()) if m_nr else ("", titel)
        segmente.append({
            "id": "", "nr": nr, "titel": titel_clean,
            "chunk": chunk, "position": m.start(), "vorspann": vorspann,
        })

# Reihenfolge sicherstellen
segmente.sort(key=lambda s: (s["chunk"], s["position"]))

print("Gefundene Segmente:")
for s in segmente:
    tag = "VORSPANN" if s["vorspann"] else "kapitel"
    nr = f" [{s['nr']}]" if s["nr"] else ""
    print(f"  chunk_{s['chunk']:03d}:{s['position']:5d}  {tag:8}{nr:5}  {s['titel']}")

kapitel = [s for s in segmente if not s["vorspann"]]
vorspann_titel = [s["titel"] for s in segmente if s["vorspann"]]

out = {
    "quelle": "title-attribut",
    "kapitel": kapitel,
    "vorspann": vorspann_titel,
    "segmente": segmente,
}
ZIEL.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nGeschrieben: {ZIEL}")
print(f"  Sachkapitel: {len(kapitel)}  |  Backmatter: {len(vorspann_titel)}")
