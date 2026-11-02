# Design: Korrektur-Workflow in der TUI

Stand: 2026-10-31. Überarbeitet den Ablauf aus `2026-10-02-korrektur-marken-design.md`.

## Ausgangslage und Schwächen

Der Ablauf war: im Lesemodus mit `k` einen fehlerhaften Absatz markieren, später
einen getrennten Kommandozeilenlauf (`python -m episto_tui.korrektur -Buch …`)
starten, der Absatz für Absatz ein Sprachmodell fragt und `[j/n/e]` verlangt.
(Das im Design genannte `tools\korrektur.ps1` gibt es nicht.) Schwächen:

1. **Ganzes englisches Kapitel als Anker.** Lange Kapitel sprengen den Kontext
   des Modells, und das Modell muss die Stelle selbst finden.
2. **Die Kapitelzuordnung hängt am Lektor-Ordner.** Die Chunk-Grenzen der Kapitel
   stehen nur in `kapitel.json` des Lektor-Ordners (`meta.json` → `lektor_pfad`,
   z. B. `C:\Users\Dude\Tools\eBooks\Lektor\…`). Die eigene `kapitel.json` der Bücher
   hat keine `segmente`. Fehlt der Ordner (die Auflösung von `eBooks\` ist geplant),
   brach der Lauf mit „Grounding nicht verfügbar" ab.
3. **`ersetze_absatz` schrieb das ganze Kapitel neu** (normalisierte Leerzeilen,
   erzwungenes Zeilenende am Dateiende).
4. **Kein Eingreifen vor dem Übernehmen:** nur ja/nein, Anzeige auf 120 Zeichen
   gekürzt, kein Prüfen des Vorschlags, kein Bearbeiten.
5. **Blockierend und getrennt von der TUI:** Wartezeit pro Absatz, kein Blick auf
   Original und Umfeld, kein Weg am Handy.

## Neuer Ablauf

`k` markiert wie bisher. Neu: **`x`** (Handy: Knopf **Korr**) öffnet den Dialog
„Korrektur" für das aktuelle Buch (Kontrollkästchen „Ganze Bibliothek").

Der Dialog zeigt je offener Marke:

- oben den **fehlerhaften deutschen Absatz als Arbeitsfeld** (frei bearbeitbar),
- darunter ein **Fenster des englischen Originals** (7 Absätze, lesbar, verschiebbar
  mit EN−10 / EN−1 / EN+1 / EN+10),
- **Vorschlag** (Strg+L): fragt das lokale Modell im Hintergrund (Ollama,
  `aya-expanse:32b`, überschreibbar mit `EPISTO_KORREKTUR_MODELL`). Der Vorschlag
  landet im Arbeitsfeld, nicht im Text. Fehler (Ollama aus) erscheinen als Hinweis,
  nichts stürzt ab. Ein Wiederholungsversuch wie im Kommandozeilenlauf.
- **Prüfung des Vorschlags** mit Warnungen: leer; unverändert; unter halber oder
  über 2,5-facher Länge; beginnt wie eine Modellantwort („Hier ist …"); aus einem
  Absatz wurden mehrere; Fußnotenmarken (`[^n]`, `*n`) weichen vom Original ab.
- **Übernehmen** (Strg+S): schreibt nur diesen Absatz ins Kapitel (mit Sicherung in
  `notizen/_backup/`) und entfernt die Marke. Leer oder unverändert wird nicht
  übernommen.
- **Marke weg** (Strg+R): entfernt nur die Marke, der Text bleibt.
- **Original**: stellt den ursprünglichen Text im Arbeitsfeld wieder her.
- ◀ ▶ blättern zwischen den Marken. Esc schließt; ein geändertes Kapitel wird im
  Lesebereich neu geladen.

Beim Öffnen eines Kapitels mit offenen Marken erscheint ein Hinweis („Taste x").

Ohne Ollama oder ohne englisches Original (Handy: `en` wird nicht synchronisiert)
bleibt das Korrigieren von Hand; der Dialog nennt dann den Grund.

## Kern (`korrektur.py`)

- `absatz_spannen`, `ersetze_absatz_exakt`: ersetzt genau einen Absatz und lässt den
  Rest **zeichengenau** stehen (Leerzeilen, `\r\n`, Dateiende). Gleiche Zählung wie
  `split_paragraphs`. `ersetze_absatz` bleibt für Altaufrufe.
- `englischer_anker(buch, datei, absatz_index)`: erst über die Kapitelgrenzen des
  Lektor-Ordners (`genau`), sonst **Näherung über das ganze Buch**:
  `globales_fenster` bildet die Stelle des deutschen Absatzes (Zeichenanteil im
  ganzen Buch) auf dieselbe relative Stelle im englischen Volltext ab. Ungenauer
  (Vorspann, Anhang und Übersetzungsunterschiede verschieben um einige Absätze),
  daher breiteres Fenster, der Hinweis „Näherung" und die Verschiebeknöpfe.
  Probe an *The Theory of Democratic Elitism* (Kapitel „Elitekonsens"): das Fenster
  traf das Thema; an *Capitalism, Socialism and Democracy* lag es etwa einen
  Abschnitt vor dem Ziel.
- `englisches_fenster`, `verschiebe_fenster`, `fenster_text` (kürzt von außen auf
  höchstens 8000 Zeichen), `pruefe_vorschlag`, `sammle_offene_marken`,
  `wende_an` (sucht den Absatz beim Schreiben neu; nicht mehr auffindbar → nichts
  wird verändert), `entferne_marke`.
- Der Kommandozeilenlauf nutzt dasselbe: Fenster statt Kapitel (`-Voll` für das
  ganze Kapitel), Fallback auf die Näherung statt Abbruch, vollständige Anzeige,
  Warnungen, exaktes Ersetzen.

## Nicht enthalten

- Marken automatisch entfernen, wenn man den Absatz im Editor ändert.
- Fußnotenspezifische Korrektur (Notes-Kapitel als zusätzlicher Kontext).
- Stapel-Lauf über alle Bücher ohne Dialog.
- Eine bessere Zuordnung als Zeichenanteil (z. B. über Seitenzahlen oder
  Eigennamen/Zahlen als Anker).
- Langfristig sinnvoll: die Kapitelgrenzen (`segmente`) in die eigene `kapitel.json`
  der Bücher übernehmen, dann braucht es den Lektor-Ordner nicht mehr.

## Tests

`tests/test_korrektur_workflow.py`: Absatzspannen (auch `\r\n`, Randfälle), exaktes
Ersetzen, Fenster (Anfang, Ende, kurze Kapitel), Kürzen, Vorschlagsprüfung,
offene Marken (aufgelöst, verwaist), `wende_an` (Sicherung, Verschiebung,
verschwundener Absatz), Kommandozeile (Fenster, `-Voll`, Näherung), Dialog
(Anzeige, Vorschlag im Hintergrund, Fehler, Übernehmen, Marke weg, unverändert/leer,
ohne Original, verwaiste Marke, Navigation, Näherungshinweis, Handybreite),
Hinweis beim Kapitelöffnen. Das Sprachmodell ist in den Tests ersetzt; der echte
Ollama-Aufruf ist **nicht** getestet.
