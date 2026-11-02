# Workflow zur Zusammenfassung übersetzter, unredigierter Chunks zu inhaltlichen Einheiten

## 1. Bestehender Workflow (Ingest, Tagging, Stränge)

- **Ingest-Pipeline**: `ingest.ps1` zerlegt Volltext absatzweise in ~250-Wort-Chunks für Vektorisierung
- **Tagging**: `taggen.ps1` analysiert jedes Kapitel einzeln und erzeugt strukturierte Metadaten
- **Stränge**: `straenge.ps1` aggregiert Konzeptstränge aus den Tags

## 2. Projektstruktur

```
!Episto\
├── Autor\
│   └── <Autor>\
│       └── <Buch>\
│           ├── STRUKTUR.md
│           ├── meta.json
│           ├── kapitel.json
│           ├── .progress.json
│           ├── quelle\                 ← Original-Volltext
│           ├── notizen\                ← Tags, Stränge
│           ├── analysen\
│           └── querbezuege\
```

## 3. Translationsverarbeitung

### Ablauf für Übersetzungen:
1. Original-Volltext liegt in `quelle\*.md`
2. Neue transkribierte Version wird in `de\` abgelegt
3. Chunks werden in `de\chunks\` erzeugt (nicht im ursprünglichen Originalformat)
4. Mapping von Chunk-Identifikatoren zur ursprünglichen Kapitelstruktur

## 4. Workflow zum Zusammenführen übersetzter Chunks 

### Schritt 1: Chunk-Erstellung
- Generiere übersetzte Chunks aus `de\*.md` Dateien (gleiche Struktur wie Original)
- Speichere in `de\chunks\*.md`
- Jede Chunk-Datei enthält: 
  - Original-Kapitelnummer und -Titel
  - Startposition im Originaltext
  - Content mit allen relevanten Informationen

### Schritt 2: Mapping von Übersetzung zu Originalstruktur
- Erstelle `de\chunk_to_original.json` als Index:
  ```
  {
    "chunks": [
      {
        "chunk_id": "#123",
        "original_file": "001_kapitel1.md",
        "original_position": "p14-27",
        "translation_file": "chunk_123.md"
      }
    ]
  }
  ```

### Schritt 3: Zusammenfassung inhaltlicher Einheiten
- Für jede Übersetzungskomponente:
  - Extrahiere relevante Thesen und Kernbegriffe aus `notizen\tags.json` (original)
  - Erstelle inhaltliche Einheit in `de\inhalte\`
  - Verknüpfe mit originalen Tags über Chunk-Identifier

## 5. Integration in bestehende Prozesse

### Anpassungen an `taggen.ps1`:
Die Übersetzung kann als separater Pipeline-Schritt entworfen werden:
```
quelle\*.md               →   de\chunks\*.md
   ↓                                  ↓
original Tags (via taggen)    →   übersetzte Zusammenfassungen
```

### Implementierung in `straenge.ps1`:
- Verarbeite `de\inhalte\*.md` Dateien wie normale Stränge
- Füge Übersetzungsinhalte in die bestehende Strang-Aggregation ein

## 6. Behaltung der Original-Chunks

- Alle unredigierten Chunks werden im `quelle\` Ordner erhalten
- Übersetzte Versionen existieren separat in dem `de\` Ordner 
- Beide Versionen sind vollständig dokumentiert und verknüpft