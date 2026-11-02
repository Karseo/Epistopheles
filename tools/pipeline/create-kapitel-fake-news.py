import json
import re
from pathlib import Path

# Zielverzeichnis für das Buch
buch_verzeichnis = Path(__file__).resolve().parents[2] / "rohdaten" / "Lektor" / "Barclay, Donald A" / "Fake News"

# Überprüfen, ob das Verzeichnis existiert
if not buch_verzeichnis.exists():
    raise FileNotFoundError("Buchverzeichnis nicht gefunden")

# Struktur für die Kapitel
kapitel_struktur = {
    "buch": "Fake News",
    "autor": "Barclay, Donald A",
    "sprache": "de",
    "segmente": []
}

# Regex für KAPITEL- und Unterkapitelüberschriften
kapitel_pattern = re.compile(r'^\*\*KAPITEL\s+(\d+)\s*\*\*$', re.IGNORECASE)
unterkapitel_pattern = re.compile(r'^\*\*(.+?)\*\*$', re.IGNORECASE)

# Liste aller Chunk-Dateien sortiert nach Name
chunks = sorted(buch_verzeichnis.glob("de/chunk_*.md"))

current_segment = None
segment_index = 0

# Alle Chunks durchgehen und Kapitelmarken extrahieren
for chunk in chunks:
    with open(chunk, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Zeilen durchgehen
    for i, line in enumerate(lines):
        # Suche nach KAPITEL Überschriften
        kapitel_match = kapitel_pattern.match(line.strip())
        
        if kapitel_match:
            kapitel_nummer = kapitel_match.group(1)
            
            # Wenn es bereits ein Segment gibt, speichern wir es
            if current_segment is not None:
                kapitel_struktur["segmente"].append(current_segment)
            
            # Neues Segment erstellen
            current_segment = {
                "id": f"kapitel_{kapitel_nummer}",
                "nr": kapitel_nummer,
                "titel": f"Kapitel {kapitel_nummer}",
                "vorspann": False,
                "chunk": int(chunk.name.replace("chunk_", "").replace(".md", "")),
                "position": sum(len(l) + 1 for l in lines[:i])  # Position im Text
            }
            
        else:
            # Suche nach Unterkapitel Überschriften (nur innerhalb eines Kapitels)
            unterkapitel_match = unterkapitel_pattern.match(line.strip())
            if unterkapitel_match and current_segment is not None:
                titel = unterkapitel_match.group(1).strip()
                # Nur speichern, wenn es kein Standard-Kapitel-Titel ist
                if not re.match(r'^KAPITEL\s+\d+$', titel, re.IGNORECASE):
                    # In der Regel wird das erste Unterkapitel als Kapitelname verwendet,
                    # wir können aber einfach den ersten Titel im Kapitel nehmen.
                    current_segment["titel"] = titel
    
    # Letztes Segment speichern
    if current_segment is not None:
        kapitel_struktur["segmente"].append(current_segment)
        current_segment = None

# Speichere die Struktur in einer JSON-Datei
output_file = buch_verzeichnis / "kapitel.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(kapitel_struktur, f, ensure_ascii=False, indent=2)

print(f"Kapitelstruktur für '{buch_verzeichnis.name}' wurde in {output_file} gespeichert")