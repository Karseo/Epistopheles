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

# Verzeichnis für die Chunk-Dateien
chunk_dir = buch_verzeichnis / "de"

# Liste aller Chunk-Dateien sortiert nach Nummer
chunk_files = sorted(chunk_dir.glob("chunk_*.md"), key=lambda x: int(x.stem.split('_')[1]))

# Speicher für bereits gesehen Kapitelnummern
gesehene_kapitel = set()

# Speichern des vorherigen Kapitels zur Erkennung von Wiederholungen
vorheriges_kapitel = None

# Position in der Datei
position_in_datei = 0

# Aktuelles Segment (wird später mit korrektem Titel gefüllt)
aktuelles_segment = None

for chunk_file in chunk_files:
    print(f"Verarbeite {chunk_file.name}")
    
    with open(chunk_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Aktuelle Position innerhalb des Chunks
    position_in_chunk = 0
    
    for i, line in enumerate(lines):
        position_in_chunk += len(line)
        
        # Suche nach **KAPITEL x** Markierungen
        kapitel_match = kapitel_pattern.search(line.strip())
        
        if kapitel_match:
            kapitel_nr = int(kapitel_match.group(1))
            
            # Nur erstes Vorkommen eines Kapitels verarbeiten (ignoriert Wiederholungen)
            if kapitel_nr not in gesehene_kapitel:
                print(f"Neues Kapitel {kapitel_nr} gefunden in {chunk_file.name}")
                
                # Wenn bereits ein Segment vorhanden ist, speichere es
                if aktuelles_segment is not None:
                    kapitel_struktur["segmente"].append(aktuelles_segment)
                
                # Erstelle neues Segment für das Kapitel
                aktuelles_segment = {
                    "id": f"kapitel_{kapitel_nr}",
                    "nr": str(kapitel_nr),
                    "titel": f"Kapitel {kapitel_nr}",
                    "vorspann": False,
                    "chunk": int(chunk_file.stem.split('_')[1]),
                    "position": position_in_datei + position_in_chunk - len(line)
                }
                
                # Markiere Kapitel als gesehen
                gesehene_kapitel.add(kapitel_nr)
                vorheriges_kapitel = kapitel_nr
                
        else:
            # Suche nach Unterkapitelmarkierungen **...** 
            unterkapitel_match = unterkapitel_pattern.search(line.strip())
            
            if unterkapitel_match and aktuelles_segment is not None:
                unterkapitel_text = unterkapitel_match.group(1).strip()
                
                # Prüfe, ob Unterkapitel ein Standardtext ist (z.B. "Kapitel X")
                if unterkapitel_text.startswith("Kapitel") or \
                   unterkapitel_text in ["ANMERKUNGEN", "ZUSAMMENFASSUNG"]:
                    continue  # Ignoriere Standardunterschriften
                    
                # Prüfe, ob es eine Seitenzahl ist (z.B. Kapitel 1 – Seite 34)
                if re.match(r'^\d+\s*–\s*Seite\s*\d+$', unterkapitel_text):
                    continue  # Ignoriere Seitenangaben
                    
                # Aktualisiere das Titel des aktuellen Segments, wenn es noch leer ist
                if aktuelles_segment["titel"] == f"Kapitel {aktuelles_segment['nr']}":
                    aktuelles_segment["titel"] = unterkapitel_text

    # Endposition innerhalb der Datei aktualisieren
    position_in_datei += position_in_chunk

# Füge letztes Segment hinzu
if aktuelles_segment is not None:
    kapitel_struktur["segmente"].append(aktuelles_segment)

# Speichere die Struktur als JSON-Datei
output_file = buch_verzeichnis / "kapitel.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(kapitel_struktur, f, ensure_ascii=False, indent=2)

print(f"Kapitelstruktur wurde in {output_file} gespeichert")