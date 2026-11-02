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
