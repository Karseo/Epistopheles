# Korrektur-Marken in der TUI + Korrektur-Lauf — Design

Datum: 2026-10-02

> **Überholt am 2026-10-31:** Der Ablauf wurde überarbeitet, siehe
> `2026-10-31-korrektur-workflow-design.md` (Dialog in der TUI auf Taste `x`,
> englisches Fenster statt ganzem Kapitel, Näherung ohne Lektor-Ordner, exaktes
> Ersetzen, Prüfung der Vorschläge). Das hier genannte `tools\korrektur.ps1` gibt es
> nicht; der Kommandozeilenlauf ist `python -m episto_tui.korrektur -Buch <pfad>`.

## Ziel

Beim Korrekturlesen in der TUI sollen fehlerhafte Passagen (z. B. Abbruch
mitten im Satz, fehlerhafte Fußnotenzuordnung) markiert und später in einem
eigenen Lauf **auf Basis des englischen Originaltexts** repariert werden.

Zwei Bausteine:

1. **TUI:** „k" als vierte Markierungsfarbe („korrektur"), exklusiv zu
   gelb/rosa/blau.
2. **Lauf:** `tools\korrektur.ps1` sammelt die „korrektur"-Marken eines Buchs,
   erzeugt per LLM Korrekturvorschläge (englischer Originaltext als Anker) und
   wendet bestätigte Korrekturen direkt in `quelle\*.md` an.

## Kontext (bestehendes System)

- `Highlight.farbe` ist ein freier String (`models.py`); gespeichert in
  `notizen\highlights.json` je Absatz (`datei` + `absatz_index` + `absatz_anfang`).
- Farben heute: `gelb` (#595900), `rosa` (#594347), `blau` (blue) —
  Hintergrundfarben in `reader_pane.py` `_HINTERGRUNDFARBE`.
- Tasten `g`/`r`/`b`, Knöpfe „Gelb/Rosa/Blau" in der Aktionsleiste; Toggle über
  `_schalte_highlight(farbe)`.
- `meta.json` enthält `lektor_pfad` (Pfad zum Lektor-Quellordner), dort liegt
  `kapitel.json` mit `segmente` (Chunk + Position je Kapitel).
- `en\chunk_*.md` sind 1:1 zu `de\chunk_*.md` (gleicher Chunk-Index).

## Teil 1 — TUI: „k" als vierte Markierungsfarbe

Keine Änderung am Datenmodell. Vier Dateien:

1. `widgets/reader_pane.py`
   - `_HINTERGRUNDFARBE["korrektur"] = "#5c1a1a"` (gedämpftes Dunkelrot).
   - `BINDINGS` + `Binding("k", "highlight_korrektur", "Korrektur")`.
   - `action_highlight_korrektur(self)` → `self._schalte_highlight("korrektur")`.
2. `widgets/aktionsleiste.py`
   - `_KNOEPFE` + `("korrektur", "K")` (Label „K", damit 8 Lese-Knöpfe ins 45-Spalten-Mobile-Layout passen).
   - `KONTEXTE["lesen"]` + `"korrektur"`.
3. `app.py`
   - `_KNOPF_AKTION["korrektur"] = "highlight_korrektur"`.

Verhalten: identisch zum bestehenden Toggle; ein Absatz hat genau eine Farbe
(gelb/rosa/blau/korrektur). Bei der Umsetzung prüfen, dass `k` nirgends sonst
belegt ist (in den aktuellen Bindings ist es frei).

## Teil 2 — Korrektur-Lauf `tools\korrektur.ps1`

Aufruf: `.\korrektur.ps1 -Buch "<Episto-Buchpfad>" [-Model aya-expanse:32b] [-Limit N]`

### Ablauf

1. `notizen\highlights.json` lesen, nach `farbe == "korrektur"` filtern. Leer →
   Meldung, Ende.
2. `meta.json` → `lektor_pfad` → `kapitel.json` → `segmente` (sortiert nach
   Chunk/Position).
3. Je Marke:
   - Kapitelnummer aus dem Dateinamen-Präfix (`0005_…` → 5). Englisches
     Grounding = `en\`-Chunks vom Start-Chunk des Kapitels
     (`segmente[nr-1].chunk`) bis zum Start-Chunk des Folge-Kapitels
     (`segmente[nr].chunk`), **inklusive beider Grenz-Chunks** (beim letzten
     Kapitel bis Chunk-Ende).
   - Kaputten deutschen Absatz lesen (gleiche Absatz-Aufteilung wie das
     ReaderPane, Leerzeilen-basiert).
   - LLM-Korrektur mit dem kompletten englischen Kapiteltext als Anker.
   - Interaktive Abfrage und ggf. Anwenden.
4. `highlights.json` zurückschreiben (ohne übernommene Marken).

### LLM-Prompt

System:
> Du bist ein Lektor für ein übersetztes Buch. Der folgende deutsche Absatz ist
> fehlerhaft (z. B. Abbruch mitten im Satz oder fehlerhafte Fußnotenzuordnung).
> Nutze den englischen Originaltext des Kapitels, um den deutschen Absatz
> korrekt zu reparieren. Antworte ausschließlich mit dem korrigierten deutschen
> Absatz (Markdown bleibt erhalten).

User:
> Deutscher Absatz (fehlerhaft):\n{absatz}\n\nEnglisches Original (Kapitel):\n{englisch}

### Interaktive Abfrage

```
[3/12] 0005_krise-des-institutionalismus.md, Absatz 7
  fehlerhaft: Der Autor argumentiert, dass die Krise des [^12]
  korrigiert: Der Autor argumentiert, dass die Krise des Institutionalismus …[^12]
  Übernehmen? [j/n/e]   (e = Lauf beenden)
```

- `j`: Absatz in `quelle\*.md` ersetzen (vorher Backup nach `notizen\_backup\`,
  wie die TUI) und die „korrektur"-Marke entfernen.
- `n`: überspringen, Marke bleibt.
- `e`: Lauf beenden; bereits Übernommenes ist gespeichert.

### Grounding (Approach A)

Dem LLM wird der **komplette englische Kapiteltext** + der kaputte Absatz
gereicht. Keine 1:1-Absatzzuordnung — das LLM findet die Stelle selbst.

### Bewusste Grenze (MVP)

Der Reparatur-Prompt ist generisch; das LLM erkennt selbst, ob Satzabbruch,
Fußnote o. ä. vorliegt. Fußnoten, die sich damit nicht sauber reparieren lassen,
bleiben markiert (der Nutzer verwirft). Fußnotenspezifische Logik (Notes-Kapitel
als zusätzlicher Kontext) ist eine spätere Ausbaustufe.

### Fehlerfälle

- Marke zeigt auf nicht (mehr) existierenden Absatz → überspringen mit Warnung.
- `lektor_pfad`/`kapitel.json` fehlt → Meldung, Abbruch (nicht still falsch
  korrigieren).
- LLM antwortet ungültig → 1 Retry, dann überspringen.

## Datenfluss

```
TUI („k" markieren) ──► highlights.json (farbe="korrektur")
                                   │
korrektur.ps1 -Buch <pfad>  ◄──────┘
   ├─ LLM (aya-expanse:32b): kaputter Absatz + englisches Kapitel → Korrektur
   ├─ [j] quelle\*.md ersetzen + Marke entfernen
   └─ highlights.json zurückschreiben
```

## Tests

- TUI: `k` setzt/entfernt die „korrektur"-Marke (Binding + Aktionsleisten-Knopf);
  Farbe exklusiv zu gelb/rosa/blau.
- Lauf: Grounding-Zuordnung (Kapitel → `en\`-Chunk-Bereich) korrekt; Absatz-
  Ersatz erhält die Absatzzahl; übernommene Marken werden entfernt, verworfene
  bleiben; Backup wird vor dem Schreiben angelegt.
- Bestehende Tests (`pytest`) bleiben grün.

## Ausbaustufen (nicht in diesem MVP)

- Fenster-Grounding (Approach B) für sehr große Kapitel.
- Fußnotenspezifische Korrektur (Notes-Kapitel als Kontext).
- Wrapper über alle Bücher (`--alle`).
