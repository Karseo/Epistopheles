# !Episto — Epistemisch souveräne Bibliothek

Digitale Bibliothek von Alexandria: Standardwerke (Philosophie, Soziologie, Ökonomie) als
formatierter Volltext + destillierte Metadaten, zugänglich über ein lokales/Cloud-LLM.
Leitlogik — Umkehrung kognitiver Atrophie:

```
Masse:   KI → Antwort → Ende des Denkens
EPISTO:  KI → Hinweis → Originaltext → Beginn des Denkens
```

## Wichtigste Verzeichnisse

Aufbau der Wurzel (Details: `dok\DATENSTRUKTUR.md`):

- `rohdaten\` — ALLE Roh-Daten, nicht in Git/Syncthing: `Inbox\` Quelldateien, `Lektor\<Autor>\<Titel>\{en,de}\`
  Chunks und Quelldatei, `Outbox\`, `Transfer\`, `en-chunks\<Autor>\<Titel>\` (englische Referenzchunks je Buch)
- `reader\<Autor>\<Werk>\` — FERTIGE Daten für den Reader. Pro Buch: `quelle\*.md` (Volltext, Markdown =
  Source of Truth), `kapitel.json`, `meta.json`, `notizen\strang_taxonomie.json`, `.progress.json`.
  `reader\export-epistopheles\` ist das erzeugte Chromebook-Paket (kein Buch, nicht in Git/Syncthing).
- `tools\` — alle Skripte (generisch, unabhängig vom APIC-Setup): `episto_tui\`, `speedreader_web\`,
  `ingest.*`, `taggen.ps1` …; `tools\pipeline\` = Übersetzungs-Pipeline (`ebook-translate.py` usw.), leitet
  `BASE` aus dem Ablageort ab (`<Wurzel>\rohdaten`, `EBOOK_BASE` übersteuert)
- Redaktion (Korrekturen vom Epistopheles): `tools\redaktion_server.py` (Empfänger, von Hand starten, Token in `hilfsdaten\redaktion\token.txt`), `tools\redaktion_anwenden.py` (Dry-Run, `--ausfuehren`; Exit 0/1/2/3), Doku `tools\speedreader_web\README.md`. Volltext-Korrekturen (Ebene `volltext`, `reader\<Buch>\notizen\redaktion.json`) werden von `lektor-zu-episto.py --ueberschreiben` nach dem Neuaufbau wieder eingespielt (Backup `notizen\_backup\quelle-<Zeit>`, Bericht `redaktion-nachspiel.json`)
- Querverbindungen (Ansicht „Verbindungen“ in der Chromebook-App): `tools\speedreader_web\export_verbindungen.py` (nach `export_daten.py`, liest Qdrant nur lesend, schreibt `verbindungen.json` ins Paket; Exit 0/3/1), Kalibrierung `verbindungen_stichprobe.py`, Doku `tools\speedreader_web\README.md`
- `hilfsdaten\` — `themen.json`, `notizen\` (Buch-Queue), `konzepte\`, `archiv\` (Altbestand, z. B. `Autor.mov`)
- `dok\` — `README.md` (vollständige Werkliste), `NÄCHSTE_SCHRITTE.md` (Resume-Hilfe), `DATENSTRUKTUR.md`

## Pipeline je Buch (Reihenfolge)

1. `tools\pipeline\ebook-translate.py` — en→de mit `aya-expanse:32b`; deutsche Quellen `--source-lang de --ohne-referenz` (liest `rohdaten\Inbox`, schreibt `rohdaten\Lektor`)
2. `tools\pipeline\detect-chapters.py` / `suggest-structure.py` — Anker; sonst TOC-Startseiten auf `## Seite N`-Marker mappen
3. `lektor-zu-episto.py --buch "<Autor>/<Titel>"` → `quelle\` + `kapitel.json`
4. `bereinige-translategemma.py --quelle <pfad> [--reflow] [--ohne-fussnoten]`
5. `taggen.ps1 -Buch <pfad>` (resume-fähig). `zusammenfassung` ist ein Satz (Gegenstand/Gang, ohne Thesen); Altbestand mit langer, thesen-redundanter Zusammenfassung: `neu-zusammenfassen.py` (`--alle`, `--stop`, `--anwenden`)
6. `notizen\strang_taxonomie.json` kuratieren (6 Stränge je Buch, kern-basiert)
7. `straenge.ps1 -Buch <pfad>`
8. `ingest.ps1 -Buch <pfad>` (inkrementell; `-Reset` nur bei Neuaufbau, vermeidet Duplikate)

## Stack (Ollama + Qdrant, lokal)

- Übersetzung `aya-expanse:32b` · Tagging `qwen3.8:27b` (NICHT `apic-general`, defekt) · Embedding `mxbai-embed-large` (1024 dims)
- Qdrant `http://127.0.0.1:6333`, Collection `episto` (Cosine). Vektoren sind regenerierbar → reisen nicht mit.

## Konventionen

- Kommunikation auf Deutsch; technische Begriffe/Bezeichner bleiben englisch.
- Markdown-Volltext ist die Referenz, nicht der Chat; jeder Schritt schreibt auf Disk, Tools sind resume-fähig.
- Qdrant-Bug: `delete-by-filter` panikt (OffsetOutOfBounds) → Re-Ingest nur per Punkt-IDs oder `-Reset`.

## Resume

- Zustand liegt auf Disk, nicht im Chat; jedes Werk hat `.progress.json`.
- „Was kommt als Nächstes" steht im Auto-Memory `buecher-integrations-queue.md`.
