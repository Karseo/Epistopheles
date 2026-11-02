# Design: Sync-Konflikt-Merge und Volltextsuche (TUI)

Stand: 2026-10-31. Setzt die Punkte 2 und 1 der Verbesserungsvorschläge um.

## Teil 1 — Sync-Konflikte der Notizen zusammenführen

### Problem

`notizen/kommentare.json`, `highlights.json` und `tags.json` liegen je Buch in
einer Datei. Ändern PC und Handy zwischen zwei Syncthing-Abgleichen dieselbe
Datei, behält Syncthing eine Fassung und legt die andere als
`<name>.sync-conflict-<datum>-<id>.json` daneben. Die TUI las diese Kopien nie;
die Notizen des anderen Geräts wirkten verloren. Kommentare hatten außerdem
keine Kennung und wurden über alle fünf Felder identifiziert (zwei gleiche
Kommentare waren nicht unterscheidbar).

### Lösung

- `Kommentar` bekommt das optionale Feld `id` (12 Zeichen). `add_kommentar`
  vergibt sie beim Anlegen und setzt sie am übergebenen Objekt, damit
  `update_kommentar`/`remove_kommentar` den Eintrag über die Kennung finden.
  Altbestand ohne Kennung bleibt gültig und wird weiter über alle Felder
  gefunden. `to_dict` schreibt `id` nur, wenn sie gesetzt ist.
- Highlights brauchen keine Kennung: ihr natürlicher Schlüssel ist
  (`datei`, `absatz_index`).
- `library.merge_konflikte(buch)` führt vorhandene Konfliktkopien der drei
  Dateien mit der Hauptdatei zusammen, sichert die Hauptdatei vorher
  (`backup_before_write`) und verschiebt jede verarbeitete Kopie nach
  `notizen/_backup/`. `merge_alle_konflikte(root)` macht das für alle Bücher.
- Aufrufe: beim Start der App (ganze Bibliothek) und bei jeder Kapitelwahl
  (dieses Buch). Fehler dabei verhindern das Laden nie, sie erscheinen als
  Hinweis. Ein Hinweis meldet die Zahl der zusammengeführten Kopien.

### Regeln je Datei (Hauptdatei = die von Syncthing als neuer gewertete)

| Datei | Regel |
|---|---|
| `kommentare.json` | Vereinigung. Gleich ist, wer dieselbe `id` hat oder (ohne `id`) dieselben Felder. Danach stabil nach `erstellt` sortiert. |
| `highlights.json` | Vereinigung über (`datei`, `absatz_index`); bei zwei Farben am selben Absatz gewinnt die Hauptdatei. |
| `tags.json` | Vereinigung über `datei`; bei zwei Fassungen desselben Kapitels gewinnt die Hauptdatei (`eintraege` wird neu gezählt). |

### Grenzen

- Eine Vereinigung kennt keine Löschungen: ein auf einem Gerät gelöschter
  Kommentar kehrt zurück, wenn ihn die Konfliktkopie noch enthält.
- Bei Tags und Highlights geht die unterlegene Fassung nicht verloren, sie liegt
  in `notizen/_backup/`, wird aber nicht automatisch eingespielt.
- Unlesbare Kopien (kaputtes JSON) bleiben unverändert liegen.
- Konfliktkopien anderer Dateien (Kapiteltexte) werden nicht angefasst.

## Teil 2 — Volltextsuche

### Ziel

Der Weg von einer Frage zur Textstelle: Begriffe eintippen, Treffer ansehen,
in den Text springen. Bewusst ohne Qdrant/Ollama, damit sie auch unter Termux
läuft. Die semantische Suche (Qdrant) bleibt V2 und nur am PC.

### Verhalten

- Aufruf: Taste `s` oder Strg+F, im schmalen Layout der Knopf „Suche"
  (in allen Kontexten außer dem Editiermodus). Dialog `SuchScreen`.
- Eingabe: Wörter und `"Phrasen in Anführungszeichen"`. Ein Absatz trifft, wenn
  er ALLE Begriffe enthält. Groß-/Kleinschreibung egal (`casefold`, also auch
  ß = ss). Begriffe unter 2 Zeichen zählen nicht.
- Enter startet die Suche in einem Hintergrund-Thread (die Oberfläche bleibt
  bedienbar, Esc schließt). Bei offenem Kapitel kann ein Kontrollkästchen auf das
  aktuelle Buch beschränken.
- Ergebnis: höchstens 200 Treffer in Bibliotheksreihenfolge (Autor, Buch,
  Kapitel), je Treffer Buch · Kapitel · Absatznummer und ein Ausschnitt mit
  hervorgehobenen Begriffen. Bei mehr Treffern steht ein Hinweis zum Eingrenzen.
- Auswahl eines Treffers öffnet das Kapitel im Text-Tab und scrollt den
  Lesebereich zum Absatz. Die Absatzzählung ist dieselbe wie im ReaderPane
  (`annotate.split_paragraphs`).

### Umsetzung

- `suche.py`: `parse_anfrage`, `suche(root, anfrage, nur_buch, max_treffer)`,
  `Treffer`, `Ergebnis`. Kapitelweiser Vorfilter (fehlt ein Begriff im ganzen
  Kapitel, wird es nicht in Absätze zerlegt).
- `widgets/such_screen.py`: Dialog, Thread-Worker, Trefferliste (`OptionList`).
- `ChapterSelected` bekommt `absatz_index`; `ReaderPane.lade_kapitel(...,
  absatz_index)` scrollt nach dem Rendern zum Absatz.
- Die Aktionsleiste bekommt den Knopf „Suche"; die Handy-Leiste scrollt
  horizontal, auch wenn nicht alle Knöpfe in 45 Spalten passen.

### Messung

Echte Bibliothek (80 Bücher, 1213 Kapitel, 54,6 MB) in der Linux-VM der
Desktop-App: Lesen der Dateien 8,5 s (gemountetes Verzeichnis), `casefold`
0,16 s, Teilstring-Prüfung 0,02 s. Die Dauer hängt fast nur vom Lesen ab; auf
Windows und auf dem Handy mit lokalem Speicher ist deutlich weniger zu erwarten.
Auf dem Gerät messen (Testliste in `TERMUX.md`). Bei Bedarf: In-Memory-Cache der
gefalteten Texte, Index auf Platte.

### Nicht enthalten

Semantische Suche, Unschärfe (Tippfehler, Wortformen), Treffersortierung nach
Relevanz, Suche in Kommentaren und Tags.

## Tests

`test_library_merge.py` (Kennungen, Merge je Datei, Idempotenz, kaputte Kopie,
fehlende Hauptdatei, ganze Bibliothek), `test_suche.py` (Anfrage-Parsing, UND-
Verknüpfung im Absatz, Phrase, ß/ss, Buchbeschränkung, Trefferlimit, Dialog und
Sprung mit Scroll-Prüfung), Ergänzungen in `test_models.py`, `test_app.py`,
`test_aktionsleiste.py`, `test_layout_schmal.py`.
