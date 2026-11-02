# Design: Kommentare direkt im Textfenster (Kommentare-Tab entfällt)

## Ziel

Kommentare lassen sich im Lesemodus des `ReaderPane` anlegen, ändern und
löschen, und ihr Text steht direkt unter dem kommentierten Absatz. Damit
ist der Tab "Kommentare" (`KommentarePane`) überflüssig und wird entfernt.

## Hintergrund

Bisher sieht man den Text eines Kommentars nur im Kommentare-Tab; im
Lesemodus erscheint lediglich die hochgestellte Marke `[¹]` am Absatz
(`annotate.render_with_markers`). Der Tab kann außerdem nur anlegen — es
gibt weder Ändern noch Löschen. Fällt der Tab weg, muss der Kommentartext
im Textfenster selbst sichtbar werden, und die fehlenden Funktionen
kommen hinzu.

## Bedienung (nur Lesemodus, analog zum Highlighting)

Wie beim Highlighting bestimmt ein Mausklick, worauf die nächste Taste
wirkt (`ReaderPane.on_click`, zeilenbasierte Zuordnung).

- Klick in einen **Absatz**, dann `c`: unten öffnet sich ein Eingabefeld
  (`Input`), Enter speichert einen neuen Kommentar an diesem Absatz, Esc
  bricht ab.
- Klick auf einen **Kommentarblock**, dann `c`: Eingabefeld mit dem
  bisherigen Text, Enter speichert die Änderung, Esc bricht ab.
- Klick auf einen Kommentarblock, dann `d`: löscht den Kommentar ohne
  Rückfrage. Das Backup vor jedem Schreiben (`backup_before_write`) macht
  es wiederherstellbar.
- `c`/`d` ohne vorherigen Klick, im Editiermodus, oder `d` auf einem Absatz
  (statt Kommentarblock) tun nichts. Ein leerer Text beim Speichern legt
  nichts an bzw. ändert nichts.
- Die Farbtasten `g`/`r`/`b` bleiben unverändert und wirken auf den
  zuletzt angeklickten Absatz; ein Klick auf einen Kommentarblock merkt
  sich dessen Absatz als aktiven Absatz mit, färbt ihn aber nicht selbst.
- Nach Speichern/Abbrechen kehrt der Fokus in den scrollbaren Lesebereich
  zurück (`fokus_lesebereich()`), damit Scrollen und Tasten weiter gehen.

## Anzeige

- Der Kommentar erscheint als Zitat-Block direkt unter seinem Absatz:
  `> 💬 <Text> — <erstellt>`. Die Marken `[¹]` entfallen. Mehrere
  Kommentare zu einem Absatz stehen in Erstellungsreihenfolge untereinander,
  jeweils als eigener Block (Leerzeile dazwischen).
- Der Kommentartext ist Nutzereingabe und wird als reiner Text behandelt:
  Markdown-Sonderzeichen (Backslash, Backtick, Stern, Unterstrich, eckige
  Klammern, Raute, Größer-als, senkrechter Strich) werden mit Backslash
  maskiert, damit z. B. `[LdF]` oder `[/]` nichts zerlegt.
- Kommentare, deren Absatz nicht mehr auffindbar ist
  (`locate_paragraph()` liefert `None`), stehen am Kapitelende unter der
  Überschrift "Kommentare ohne Absatz", ebenfalls als änder-/löschbare
  Blöcke. Sonst wären sie ohne den Tab unsichtbar.

## Datenmodell & Speicherung

`Kommentar` und `notizen/kommentare.json` bleiben unverändert. Kommentare
haben keine ID, daher werden sie über alle gespeicherten Felder
(`datei`, `absatz_index`, `absatz_anfang`, `text`, `erstellt`) identifiziert
(erster exakter Treffer). Neu in `library.py`:

- `update_kommentar(buch, alt: Kommentar, neuer_text: str) -> None`
- `remove_kommentar(buch, kommentar: Kommentar) -> None`

Beide sichern vorher per `backup_before_write`, gehen defensiv mit
kaputten Dateien um wie `add_kommentar`, und tun nichts, wenn kein Treffer
gefunden wird.

## Rendering und Zuordnung

`annotate.render_with_markers` wird durch eine Funktion ersetzt, die den
anzuzeigenden Markdown-Text UND eine Segmentliste liefert. Ein Segment ist
`(startzeile, art, absatz_index, kommentar | None)` mit `art` in
`{"absatz", "kommentar"}`; Startzeilen beziehen sich auf den tatsächlich
übergebenen Text (Absätze, Kommentarblöcke, Abschnitt "Kommentare ohne
Absatz"; jeweils durch eine Leerzeile getrennt).

- `ReaderPane.on_click` ermittelt wie bisher die Startzeile des
  angeklickten Knotens und ordnet sie per Bisektion einem Segment zu; bei
  einem Kommentarsegment wird zusätzlich dessen Absatz als aktiver Absatz
  gesetzt (bei verwaisten Kommentaren: keiner).
- `_faerbe_knoten` färbt weiterhin nur Absatzsegmente; Blöcke, die in ein
  Kommentarsegment fallen, bleiben transparent. Die bestehende Logik "größter
  Knoten, der ganz in einem Segment liegt" bleibt, sie arbeitet nur auf
  Segmenten statt auf reinen Absatz-Startzeilen.
- `_absatz_startzeilen` entfällt bzw. geht in der Segmentliste auf.

## Entfernen des Tabs

`app.py`: Import, `TabPane("Kommentare")`, Binding `5`, `action_tab_kommentare`,
die `KommentarePane`-Zweige in `_fokussiere_aktiven_tab` und
`on_chapter_selected`. Gelöscht werden `widgets/kommentare_pane.py` und
`tests/test_kommentare_pane.py`; `test_app.py` verliert die
`KommentarePane`-Prüfung in `test_fehler_in_einem_pane_legt_app_nicht_lahm`
(Rest bleibt). `test_annotate.py` ersetzt die `render_with_markers`-Tests
durch Tests der neuen Renderfunktion.

## Testing

- `library.py`: `update_kommentar`/`remove_kommentar` — Normalfall,
  fehlende Datei, kein Treffer, gleicher Text an anderem Absatz bleibt
  unberührt, Backup wird angelegt.
- `annotate.py`: Renderfunktion — Kommentarblock unter dem Absatz, mehrere
  Kommentare, Maskierung von `[LdF]`/`[/]`/`*`, verwaiste Kommentare am
  Kapitelende, korrekte Segment-Startzeilen.
- `reader_pane.py` (mit `pilot.click`): Klick auf Absatz + `c` + Text + Enter
  legt an und zeigt den Block; Klick auf Kommentarblock + `c` ändert; `d`
  löscht; Esc bricht ab; `c`/`d` ohne Klick und im Editiermodus tun nichts;
  Farbtaste färbt den Absatz, nicht den Kommentarblock; Klick auf einen
  Kommentar in einem Kapitel mit Liste/Zitat trifft trotzdem das richtige
  Segment; Kommentar mit `[/]` im Text stürzt nicht ab.
- `test_app.py`: kein Tab "Kommentare" mehr, Taste `5` ohne Wirkung auf den
  Tab.
