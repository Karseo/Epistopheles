# Design: EPISTO-TUI unter Termux (Android)

## Ziel

Die bestehende Textual-TUI (`tools/episto_tui`) läuft unter Termux auf einem
Android-Handy. Sie liest und bearbeitet dieselbe Bibliothek wie am PC; die
Daten werden per Syncthing in beide Richtungen abgeglichen. Bedienung per
Touch und per (Bluetooth-)Tastatur.

## Entscheidungen

- **Umfang:** nur die TUI (Lesen, Highlights, Kommentare, Fazit/Thesen/Tags
  bearbeiten, Stränge und Querverweise ansehen). Keine semantische Suche,
  keine Pipeline (Übersetzen, Taggen, Ingest), kein Qdrant, kein Ollama.
- **Datenabgleich:** Syncthing, Ordner-Sync in beide Richtungen, ohne Cloud.
  Der Repo-Ordner (`!Episto`) wird ganz synchronisiert, also samt
  `tools/episto_tui`; das Handy braucht dadurch keinen zweiten Bezugsweg für
  den Code.
- **Bedienung:** Touch und Tastatur werden beide unterstützt. Die
  Tastenkürzel bleiben unverändert.
- **Layout:** Unter 80 Spalten ist die Seitenleiste eine Schublade.

## Ausgangslage

- Die TUI besteht aus rund 1380 Zeilen Python und hängt nur an `textual`
  (mit `rich`, `markdown-it-py`, `Pygments`; alles reines Python).
- Sie kennt weder Qdrant noch Ollama; Windows-spezifischer Code fehlt bis auf
  `library.DEFAULT_ROOT = D:\Workspace\!Episto`.
- `__main__.py` nimmt keine Argumente. `LibraryTree` ist fest 60 Spalten
  breit; ohne Änderung bleibt im Hochformat (ca. 40–55 Spalten) kein Platz für
  den Text.

## Bausteine

### 1. Pfadauflösung und Start

`library.resolve_root(arg, env)` liefert die Wurzel in dieser Reihenfolge:
`--root` auf der Kommandozeile, Umgebungsvariable `EPISTO_ROOT`, sonst ein
Plattform-Standard (`D:\Workspace\!Episto` unter Windows, sonst
`~/episto`). `__main__.py` liest `--root` per `argparse` und übergibt das
Ergebnis an `EpistoApp(root=...)`; ohne Argumente verhält sich der Start wie
bisher.

Neue Dateien:

- `tools/episto-tui.sh`: Startskript für Termux und Linux
  (`cd` nach `tools`, `python -m episto_tui`, `EPISTO_ROOT` standardmäßig auf
  das Elternverzeichnis des Skripts).
- `.stignore` im Repo-Wurzelordner: Vorlage für den PC; Syncthing überträgt die
  Datei nicht zwischen Geräten. Die Muster gelten daher je Gerät lokal: Am PC
  bleiben `.git`, `.worktrees`, `notizen/_backup` und Ähnliches von der
  Synchronisation ausgeschlossen; auf dem Handy müssen dieselben sechs Muster
  (`**/_backup`, `.git`, `**/__pycache__`, `.worktrees`, `.superpowers`,
  `Autor.mov`) von Hand in der Syncthing-Oberfläche eingetragen werden (wie in
  `TERMUX.md` beschrieben).
- `dok/TERMUX.md`: Einrichtung (`pkg install python syncthing`,
  `pip install textual`, Syncthing-Ordner `~/episto` koppeln, Start,
  Bedienung am Handy) und eine Liste manueller Tests für das Gerät.

Syncthing läuft in Termux und synchronisiert nach `~/episto` (App-privat).
Dadurch entfallen die Dateinamen-Beschränkungen des Android-Speichers; die
vorhandenen Pfade (Kommas, Punkte, Leerzeichen, Umlaute) sind dort unkritisch.

### 2. Responsives Layout

- **Breit (ab 80 Spalten):** wie bisher, nur begrenzt `max-width: 40%` die
  Seitenleiste (`width: 60` bleibt der Sollwert).
- **Schmal (unter 80 Spalten):** `EpistoApp.on_resize` setzt die CSS-Klasse
  `schmal`. Der Baum ist ausgeblendet, die Tabs nutzen die volle Breite. Die
  Taste `0` und der Knopf „Baum“ schalten die Baum-Ansicht ein: sie ersetzt
  vorübergehend die Tabs und schließt sich, sobald ein Kapitel gewählt wird
  oder `0` / „Baum“ erneut betätigt wird.
- Die Reiterleiste scrollt nicht (Textual `Tabs` hat `overflow: hidden`); bei sehr schmalen Terminals bleibt „Querverweise“ über die Taste 5 erreichbar.
- Die Schwelle von 80 Spalten entspricht der Standardgröße der bestehenden
  Tests; diese laufen daher unverändert im breiten Modus.

Die Taste `0` gilt nur außerhalb von Eingabefeldern und des Baums, weil beide
druckbare Zeichen selbst verbrauchen; im schmalen Modus ist deshalb der Knopf
„Baum“ der verlässliche Weg.

### 3. Aktionsleiste (Touch)

Neues Widget `widgets/aktionsleiste.py`, nur im schmalen Modus sichtbar,
unten am Bildschirm. Jeder Knopf ruft die vorhandene Aktion des aktiven Panes
auf; die Logik wird nicht dupliziert.

| Kontext | Knöpfe |
|---|---|
| Text-Tab, Lesemodus | Baum, Bearbeiten, Gelb, Rosa, Blau, Kommentar, Löschen |
| Text-Tab, Editiermodus | Speichern, Verwerfen |
| Fazit, Thesen, Tags | Baum, Speichern |
| Stränge, Querverweise | Baum |

- Die Knöpfe nehmen keinen Fokus (`can_focus = False`). Der zuletzt
  angetippte Absatz bleibt dadurch aktiv, und ein offenes Kommentarfeld wird
  vom Tippen auf einen Knopf nicht geschlossen.
- Die Leiste wechselt ihren Inhalt bei Tab-Wechsel und beim Umschalten
  zwischen Lese- und Editiermodus.

### 4. Syncthing und Konflikte

- Ändern beide Geräte dieselbe Datei, legt Syncthing eine Konfliktkopie
  `<name>.sync-conflict-<datum>-<id>.<ext>` an. Die TUI zeigt solche Dateien
  nie als Kapitel an: die Kapitelliste stammt aus `_kapitel_index.json`, und
  der Glob-Fallback ignoriert Namen mit `.sync-conflict-`.
- Die Zeilenenden können je Gerät abweichen (Windows-Git mit CRLF, Handy mit
  LF). Die TUI liest beide; ein Zeilenenden-Unterschied ist nur in `git diff`
  sichtbar.

## Nicht-Ziele

Semantische Suche, Pipeline-Skripte, Qdrant/Ollama auf dem Handy, ein
Git-Remote, eine Oberfläche für Konfliktauflösung, Umbau der Tastenkürzel.

## Tests

Automatisch, headless mit Textual-Pilot:

- `resolve_root`: Argument vor Umgebungsvariable vor Standard.
- Bei 45×40 Zeichen: Baum ausgeblendet; „Baum“ zeigt ihn an; Kapitelwahl
  schließt ihn; bei 100×30 sind Baum und Tabs nebeneinander sichtbar, die
  Aktionsleiste ist ausgeblendet.
- Aktionsleiste: Knöpfe lösen Highlight, Kommentar, Speichern aus und wirken
  auf den zuletzt angetippten Absatz; die Leiste wechselt mit Tab und Modus.
- Kapitelliste ohne Index ignoriert Konfliktkopien.
- Alle bestehenden Tests bleiben grün.

Manuell, auf dem Gerät (Testliste in `TERMUX.md`): Tippen als Mausklick,
Wischen als Scrollen, Softtastatur beim Kommentieren, Strg über die
Termux-Zusatzzeile, Syncthing-Rundlauf (Kommentar am Handy erscheint am PC).
Dieses Verhalten lässt sich unter Windows nicht prüfen.

## Risiken

- Wischen scrollt in Termux je nach Version das Terminal statt die App;
  `TERMUX.md` nennt in diesem Fall die Ersatzbedienung über die Zusatzzeile.
- Textual 8 setzt ein aktuelles Python voraus; das Termux-Paket muss
  mindestens die Version liefern, die `textual>=8.2` verlangt.
