"""
kapitel_lookup.py  —  gemeinsame Kapitelzuordnung fuer die Einsammel-Skripte

Liest die von detect-chapters.py erzeugte kapitel.json und beantwortet die
Frage: zu welchem Kapitel gehoert eine Fundstelle?

Der Modulname traegt bewusst keinen Bindestrich — so laesst er sich normal
importieren, waehrend die ausfuehrbaren Skripte der Toolchain (collect-tags.py
usw.) ueber importlib geladen werden muessten.

Entscheidend ist die Position im Chunk: Chunkgrenzen liegen mechanisch bei
8000 Zeichen, Kapitelgrenzen fallen deshalb regelmaessig mitten hinein. Wer
nur die Chunk-Nummer betrachtet, ordnet die erste Haelfte eines solchen Chunks
dem falschen Kapitel zu.
"""

import json
from pathlib import Path


def lade(buch: Path) -> dict:
    """kapitel.json eines Buchs. Fehlt sie, ist das kein Fehler."""
    f = buch / "kapitel.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding='utf-8'))
    except Exception:
        return {}


def bestimme(struktur: dict, chunk: int, position: int = 0) -> dict | None:
    """
    Kapitel einer Fundstelle. Beginnt im selben Chunk ein neues Kapitel vor
    der Fundstelle, gilt dieses — sonst das am Chunkanfang laufende.
    """
    if not struktur:
        return None
    eintrag = struktur.get("chunk_zuordnung", {}).get(str(chunk))
    if not eintrag:
        return None

    titel = eintrag.get("gilt") or ""
    nr = ""
    for b in eintrag.get("beginnt", []):
        if b.get("position", 0) <= position:
            titel, nr = b.get("titel", ""), b.get("nr", "")
        else:
            break

    if not titel:
        return None
    if not nr:      # Nummer aus der Kapitelliste nachschlagen
        for k in struktur.get("kapitel", []):
            if k.get("titel") == titel:
                nr = k.get("nr", "")
                break
    return {"nr": nr, "titel": titel}


def bezeichnung(kap: dict | None, kurz: bool = False) -> str:
    """'5. Sovereignty, Friends and Enemies' bzw. 'Kap. 5'. Ohne Treffer ''."""
    if not kap:
        return ""
    nr, titel = kap.get("nr", ""), kap.get("titel", "")
    if kurz:
        return f"Kap. {int(nr)}" if nr.isdigit() else (titel[:24] if titel else "")
    return f"{int(nr)}. {titel}" if nr.isdigit() else titel
