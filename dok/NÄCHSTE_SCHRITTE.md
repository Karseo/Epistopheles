# Nächste Schritte — Resume-Hilfe

Stand: **78 Bücher** vollständig integriert (Volltext → Tags → Stränge → Qdrant).
Diese Datei dient als Einstieg nach einer Pause.

## Zustand

- **Bibliothek:** `d:\Workspace\!Episto\` — Überblick und vollständige Werkliste in `dok\README.md` (Abschnitt „Ankerwerk-Referenz").
- **Buch-Queue** (erledigte + offene Gruppen, Inbox-Reste) liegt in `hilfsdaten/notizen/buecher-integrations-queue.md` — maßgeblich für „was kommt als Nächstes".
- **Qdrant:** `:6333`, Collection `episto`, Embed `mxbai-embed-large` (1024 dims).

## Pipeline je Buch

1. **Übersetzen/chunken** — `ebook-translate.py` (en→de mit `aya-expanse:32b`; deutsche Quellen mit `--source-lang de --ohne-referenz`).
2. **Kapitelstruktur** — `detect-chapters.py` (Anker); sonst `suggest-structure.py` oder manuell:
   - PDF ohne Anker: Kapitel-Startseiten aus dem TOC auf die `## Seite N`-/`_page_N`-Marker mappen.
   - EPUB: aus `[**…**]{.calibre..}`, `# [] Titel`-H1 oder `# TITLE {.AUD_h1}` rekonstruieren.
3. **Brücke** — `lektor-zu-episto.py --buch "<Autor>/<Titel>"` (→ `quelle\` + `kapitel.json`).
4. **Bereinigung** — `bereinige-translategemma.py --quelle <pfad> [--reflow] [--ohne-fussnoten]`.
5. **Tagging** — `taggen.ps1 -Buch <pfad>` (resume-fähig).
6. **Taxonomie** — `notizen\strang_taxonomie.json` kuratieren (6 Stränge je Buch, kern-basiert).
7. **Stränge** — `straenge.ps1 -Buch <pfad>`.
8. **Ingest** — `ingest.ps1 -Buch <pfad>`.

## Werkzeuge & Zustand

| Komponente | Pfad / Wert |
|------------|-------------|
| Übersetzung | `aya-expanse:32b` (Ollama) |
| Tagging | `qwen3.8:27b` (Ollama) — NICHT `apic-general` (defekt) |
| Embedding | `mxbai-embed-large` (1024 dims) |
| Vektorisierung | `ingest.ps1` (`-Buch` inkrementell, `-Reset` komplett) |
| Bereinigung | `bereinige-translategemma.py` (Fußnoten `N→*N`, Seitenzahlen, Reflow) |
| PDF-Extraktion (Zwei-Spalten) | `pdf-zweispaltig-zu-text.py` (PDFify-Degradationen: Leerzeichen + Spaltentrennung) |
| Brücke | `lektor-zu-episto.py` |

## Offene Punkte

- **Marginal-Titel** (niedrige Priorität, laut Memory): *Lasst uns offen reden* (Schreiber), *BETWEEN CRIME AND DOXA* (Whyte), *Critical capital* (Holm), *Elitism and the Approach to God* (Raybould).
- **Nicht relevant:** *Education and achievement*, *Made in China*, *Money.pdf*, *Trachtenberg.pdf*.
- **Qdrant-Bug:** `delete-by-filter` panikt (OffsetOutOfBounds) → Re-Ingest nur per Punkt-IDs oder `-Reset`.

## Hinweise für die nächste Session

- Zustand liegt komplett auf Disk, nicht im Chat; jedes Werk hat `.progress.json`.
- Falls Qdrant nach Neustart weg ist: Dienst starten, dann `ingest.ps1 -Reset` (Vektoren sind aus `quelle\` regenerierbar).
- Bei neuem Buch: `ingest.ps1 -Buch <pfad>` verwenden (statt `-Reset`), um Duplikate zu vermeiden.

## Querverbindungen auf Epistopheles (Stand: Code fertig, Echtbetrieb offen)

- Ansicht „Verbindungen“ (Fokusnetz: Qdrant-Ähnlichkeit, Themen, Querverweise) ist gebaut und getestet (Attrappe, synthetische Daten).
  Doku, Handprüfliste und Grenzen: `tools\speedreader_web\README.md`, Abschnitt „Verbindungen“.
- **Von dir auf APIC, in dieser Reihenfolge:**
  1. `python tools\speedreader_web\export_daten.py` (aktueller Stand von `daten.json`).
  2. `python tools\speedreader_web\verbindungen_stichprobe.py --anzahl 20` und Mindestwert / Zielkapitel je Kapitel an echten Büchern festlegen
     (Startwerte 0,55 / 8 sind nicht kalibriert; Qdrant 1.18.2 ist laut Plan vorgesehen).
  3. `python tools\speedreader_web\export_verbindungen.py --root <Wurzel>`: Laufzeit, Ausgabe und Exit-Code prüfen (0 = vollständig, 3 = Qdrant-Problem).
  4. Paket aufs Gerät, Handprüfliste durchgehen.
- Offen: Qualität der Ähnlichkeiten (Rangformel), Lesbarkeit bei dichten echten Kapiteln, Mehrfinger-Gesten auf dem Gerät.

## Redaktion auf Epistopheles (Stand: P0 bis P2 umgesetzt)

- Bedienung, Einarbeiten, Grenzen und die **Handprüfliste für Touch**: `tools\speedreader_web\README.md`, Abschnitt „Redaktion“.
  Die Handprüfung auf dem Gerät steht für P1 und P2 noch aus.
- **Nach dem Einarbeiten am PC** den Export wiederholen (`export_korrektur.py`, `export_daten.py`).
- **Nächste Phase P3 (Struktur):** Gerüst (Vorspann, Kapitel, Anhang, Inhaltsverzeichnis, Glossar), Kapitelgrenzen verschieben,
  Kapitel teilen / zusammenführen (Nummerierung `NNNN_*.md`, Kopplung an `tags.json`), Typen kennzeichnen; die in P1/P2 gesetzten
  Marken „Kapitel beginnt hier“ / „Inhaltsverzeichnis“ / „Glossar“ werden dort bestätigt oder verworfen. Danach P4 (KI-Inhalte,
  „veraltet“ über `dateien[…].hash_aktuell`) und P5 (Buch-Übersicht). Plan für P3 vor dem Bauen schreiben und freigeben lassen.
