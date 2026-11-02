# EPISTO unter Termux (Android)

Stand 2026-09-28. Diese Anleitung ist **nicht auf einem Gerät geprüft**; die
Testliste am Ende ist dafür da.

EPISTO läuft auf dem Handy als Textual-TUI im Terminal-Programm Termux. Die
Bibliothek wird per Syncthing zwischen PC und Handy abgeglichen, in beide
Richtungen. Nicht dabei: semantische Suche (Qdrant), Übersetzen, Taggen, Ingest.

## Voraussetzungen

- Termux aus F-Droid oder von GitHub installieren.
- Rund 150 MB freier Speicher (Bibliothek ca. 70 MB ohne die `en`-Ordner, plus Python-Pakete).
- Syncthing auf dem PC, der Ordner `!Episto` ist der Bibliotheksordner.

## Installation in Termux

```
pkg update
pkg install python syncthing
pip install "textual>=8.2"
```

Textual 8.2 braucht ein aktuelles Python. Ist das Python in Termux zu alt,
meldet `pip` einen Fehler; dann zuerst `pkg upgrade` ausführen.

## Abgleich mit Syncthing

1. In Termux `syncthing` starten. Die Oberfläche öffnet man im Handy-Browser
   unter `http://127.0.0.1:8384`.
2. PC und Handy koppeln (Geräte-ID des jeweils anderen eintragen, am anderen
   Gerät bestätigen).
3. Am PC den Ordner `!Episto` für das Handy freigeben. Auf dem Handy als
   Zielordner `~/episto` wählen (das ist `/data/data/com.termux/files/home/episto`).
4. Die Datei `.stignore` im Repo ist eine Vorlage für den PC; Syncthing überträgt
   sie nicht zwischen Geräten. Am PC werden mit ihr `.git`, `.worktrees`,
   `notizen/_backup` und Ähnliches von der Synchronisation ausgeschlossen. Auf
   dem Handy müssen dieselben Muster von Hand eingetragen werden. Sie
   sorgen dafür, dass das Handy Backups und den Bytecode-Cache
   (`__pycache__`), die dort entstehen, nicht selbst zum PC hochlädt und
   nichts davon vom PC annimmt: Syncthing-Oberfläche
   aufrufen (`http://127.0.0.1:8384`), Ordner bearbeiten, Reiter
   „Ignoriermuster", eine Zeile pro Muster:
   ```
   **/_backup
   .git
   **/__pycache__
   .worktrees
   .superpowers
   .playwright-mcp
   test_dir
   rohdaten
   reader/export-epistopheles
   hilfsdaten/archiv
   tools/*.log
   Inbox
   eBooks
   ```
   Die TUI liest nur `reader\<Autor>\<Titel>\` (`quelle`, `notizen`, `kapitel.json`, `querbezuege`).
   Ohne die Muster `rohdaten` (Quelldateien, Lektor- und en-Chunks der Übersetzungs-Pipeline, mehrere
   hundert MB), `reader/export-epistopheles` (Chromebook-Paket, über 400 MB), `hilfsdaten/archiv`,
   `test_dir` (Windows-venv) und `tools/*.log` landen weit über 100 MB Ballast auf dem Handy.
   `Inbox` und `eBooks` sind Altlast-Muster aus der Zeit vor dem Umbau (Datenstruktur: `dok/DATENSTRUKTUR.md`);
   sie schaden nicht und bleiben als Sicherung eingetragen. **Nach dem Umbau** auf dem Handy `rohdaten`,
   `reader/export-epistopheles` und `hilfsdaten/archiv` ergänzen; `Autor.mov` und `**/en` werden nicht mehr gebraucht.
   Die englischen Referenzchunks für die Korrektur (`rohdaten/en-chunks`) liegen nicht auf dem Handy, dort gilt
   weiter: kein englisches Original, Korrigieren von Hand.
5. Die TUI erst nach dem ersten vollständigen Abgleich starten.

Damit Android Syncthing im Hintergrund nicht beendet, in Termux
`termux-wake-lock` ausführen (oder Termux in den Android-Einstellungen von der
Akku-Optimierung ausnehmen).

Der komplette Ordner wird abgeglichen, also auch `tools/episto_tui`: das Handy
braucht dadurch keinen zweiten Weg für den Programmcode.

## Start

```
sh ~/episto/tools/episto-tui.sh
```

Oder von Hand:

```
cd ~/episto/tools
EPISTO_ROOT=~/episto python -m episto_tui
```

Der Wurzelordner lässt sich auch mit `--root PFAD` angeben; ein relativer Pfad
gilt ab dem Ordner, aus dem man das Skript aufruft.

Am PC startet man die TUI mit `python -m episto_tui` im Ordner `tools`.
`tools/episto-tui.ps1` ist ein älteres, unabhängiges PowerShell-Menü und nicht
das Windows-Gegenstück von `episto-tui.sh`.

## Bedienung am Handy

- **Hochformat (unter 80 Spalten):** Beim Start ist der Baum offen. Ein Kapitel
  antippen öffnet es und schließt den Baum. Der Knopf **Baum** unten öffnet ihn
  wieder.
- **Querformat (ab 80 Spalten):** wie am PC, Baum links neben dem Text.
- **Baum filtern:** `/` drücken, dann tippen. Enter übernimmt den Filter, Esc löscht ihn.
  Ohne `/` gehen Tastenkürzel (Ziffern, `q`) auch bei fokussiertem Baum.
- **Reiter:** antippen, oder die Tasten 1 bis 5. Die Reiterleiste scrollt nicht:
  bei sehr schmalen Terminals (unter 41 Spalten) ist der Reiter
  „Querverweise“ nur über die Taste 5 erreichbar.
- **Text-Reiter:** einen Absatz antippen, dann **Gelb**, **Rosa** oder
  **Blau** zum Hervorheben. **Komm** legt einen Kommentar am angetippten Absatz
  an; einen Kommentarblock antippen und **Komm** ändert ihn, **Lösch** löscht
  ihn. **Edit** öffnet den Editor, **Speichern** und **Verwerfen** beenden ihn.
- **Blättern:** Knöpfe ◀ und ▶ (Tasten `p` und `n`) wechseln zum vorigen und
  nächsten Kapitel des Buchs und bleiben im aktiven Reiter. Die Leiste hat im
  Lesemodus zwei Zeilen: oben Navigation, unten Bearbeiten.
- **Weiterlesen:** Beim Start öffnet die TUI die zuletzt gelesene Stelle wieder.
  Sie wird in `~/.episto_tui/zustand.json` gemerkt (nur auf diesem Gerät, nicht
  per Syncthing).
- **Themen und Querverweise:** Unter dem Text stehen Listen zum Springen: dasselbe
  Thema in anderen Kapiteln, und Querverweise auf Werke, die in der Bibliothek
  liegen. Enter öffnet das Ziel.
- **Notizen:** Knopf **Notiz** (Taste `m`) listet alle Kommentare und Highlights;
  Tippen filtert (auch nach `gelb`, `kommentar` …), Enter springt zur Stelle.
- **Korrektur:** `K` (Taste `k`) markiert einen fehlerhaften Absatz. Der Knopf **Korr**
  (Taste `x`) öffnet den Dialog zum Abarbeiten: deutscher Absatz zum Bearbeiten,
  darunter das englische Original, **Übernehmen** schreibt nur diesen Absatz. Den
  Vorschlag des Sprachmodells (Ollama) gibt es nur am PC; auf dem Handy bleibt das
  Korrigieren von Hand, und das englische Original fehlt dort (Ordner `rohdaten` wird nicht
  synchronisiert).
- **Speedreader:** Knopf **Speed** (Taste `v`) zeigt die KI-Felder des Kapitels
  (Zusammenfassung, Thesen, Gegenpositionen, Kernbegriffe, Definitionen, Belege)
  Wort für Wort an einer festen Stelle, als Überblick vor dem Originaltext.
  Start/Pause: Leertaste oder Knopf; Tempo (Standard 400 Wörter pro Minute) grob mit
  ↑/↓ (±50), fein mit `+`/`−` (±5), auch über die Knöpfe; Sprung zum Satz- oder
  Abschnittsanfang mit ←/→ oder den Knöpfen. Das Tempo wird gemerkt.
- **Suche:** Knopf **Suche** (oder Taste `s`, Strg+F). Begriffe eintippen, Enter
  sucht im Volltext der ganzen Bibliothek; alle Begriffe müssen im selben Absatz
  stehen, `"in Anführungszeichen"` sucht eine Phrase, Groß-/Kleinschreibung und
  ß/ss sind egal. Mit geöffnetem Kapitel lässt sich auf das aktuelle Buch
  beschränken. Ein Treffer springt in den Text zum Absatz. Angezeigt werden
  höchstens 200 Treffer.
- **Fazit (Zusammenfassung, These, Belege) und Tags:** Text ändern, dann **Speichern**.
- **Themen** (intern „Stränge“) und **Querverweise:** der Text ist nur zur Ansicht, die Sprunglisten darunter öffnen das Ziel (siehe oben).
- Mit Bluetooth-Tastatur gelten die Tastenkürzel wie am PC. Strg gibt es über
  die Zusatzzeile von Termux.

## Betrieb mit Samsung DeX

**Nicht auf einem Gerät geprüft.** Unter DeX läuft Termux in einem Fenster, das
sich beliebig vergrößern lässt. Ab 80 Spalten gilt das breite Layout: Baum links,
Tabs rechts, keine Aktionsleiste. Bedienung dann wie am PC mit Maus und
Tastatur, auch die Tastenkürzel (Strg+S usw.) ohne Zusatzzeile.

- Beim Ziehen des Fensters über die Schwelle von 80 Spalten wechselt die TUI
  zwischen Schublade und Seitenleiste (`on_resize`); das ist headless getestet,
  nicht aber im echten Termux-Fenster.
- Termux muss im Hintergrund weiterlaufen dürfen: `termux-wake-lock` und
  Termux in den Android-Einstellungen von der Akku-Optimierung ausnehmen,
  sonst beendet Samsung den Syncthing-Prozess.

## Konflikte

Ändern PC und Handy dieselbe Datei gleichzeitig, legt Syncthing eine Kopie
`<name>.sync-conflict-<datum>-<id>.<endung>` an. Die TUI zeigt solche Dateien
nicht als Kapitel an. Die beiden Fassungen von Hand vergleichen und die
überflüssige löschen.

**Der wahrscheinlichste Konflikt:** Kommentare, Highlights und Tags liegen je
Buch in `notizen/kommentare.json`, `notizen/highlights.json` und
`notizen/tags.json`. Es genügt, auf beiden Geräten zwischen zwei Abgleichen
verschiedene Kapitel desselben Buchs zu kommentieren, um einen Konflikt
auszulösen. Die TUI führt solche Konfliktkopien dieser drei Dateien beim Start
und bei jeder Kapitelwahl selbst mit der Hauptdatei zusammen und meldet es
(„Sync-Konfliktkopie(n) zusammengeführt"). Die verarbeitete Kopie liegt danach
in `notizen/_backup/`.

- **Kommentare:** werden vereinigt (jeder hat eine Kennung `id`; Kommentare ohne
  Kennung aus Altbestand gelten bei gleichen Feldern als gleich).
- **Highlights:** werden vereinigt; liegen an einem Absatz zwei verschiedene
  Farben, gewinnt die Hauptdatei.
- **Tags:** werden je Kapitel vereinigt; wurde dasselbe Kapitel auf beiden
  Geräten bearbeitet, gewinnt die Hauptdatei. Die andere Fassung steht in
  `notizen/_backup/` und lässt sich von Hand nachtragen.
- **Grenze:** Eine Vereinigung kennt keine Löschungen. Ein auf einem Gerät
  gelöschter Kommentar kehrt zurück, wenn ihn die Konfliktkopie noch enthält.
- Unlesbare Konfliktkopien (kaputtes JSON) bleiben unverändert liegen.
- Konfliktkopien anderer Dateien (z. B. Kapiteltexte) werden **nicht** automatisch
  zusammengeführt: beide Fassungen von Hand vergleichen und die überflüssige löschen.

## Wenn Wischen das Terminal statt der App scrollt

Termux ersetzt dann das Scrollen der App. Abhilfe: die Zusatzzeile um
Bildtasten erweitern. In `~/.termux/termux.properties`:

```
extra-keys = [['ESC','CTRL','PGUP','PGDN','UP','DOWN','LEFT','RIGHT']]
```

Danach `termux-reload-settings` ausführen.

## Testliste für das Gerät

Diese Punkte lassen sich unter Windows nicht prüfen:

- [ ] `pip install "textual>=8.2"` läuft durch, `sh ~/episto/tools/episto-tui.sh --help` zeigt die Hilfe.
- [ ] Im Hochformat startet die TUI mit offenem Baum.
- [ ] Tippen auf ein Kapitel öffnet es (Tippen zählt als Mausklick).
- [ ] Wischen scrollt den Text (sonst siehe oben).
- [ ] Die Knopfleiste ist vollständig sichtbar; Reiter „Querverweise“ per Antippen oder Taste 5 erreichbar.
- [ ] Absatz antippen, **Gelb** färbt ihn.
- [ ] Kommentar: Absatz antippen, **Komm**, Text mit der Softtastatur, Enter.
- [ ] Editor: **Edit**, Text ändern, **Speichern**.
- [ ] Strg über die Zusatzzeile von Termux funktioniert (z. B. Strg+S im Editor).
- [ ] Fazit-Reiter: Text ändern, **Speichern**, die Änderung erscheint nach dem Abgleich am PC.
- [ ] Ein am PC angelegter Kommentar erscheint nach dem Abgleich am Handy.
- [ ] Suche: Knopf **Suche**, Begriff eintippen, Enter; Treffer antippen springt zum Absatz. Dauer der ersten Suche notieren.
- [ ] Konflikt: dasselbe Buch auf PC und Handy kommentieren, abgleichen; beide Kommentare sind da, Meldung „zusammengeführt" erscheint.
- [ ] ◀ ▶ blättern; die zweizeilige Leiste ist vollständig sichtbar und antippbar.
- [ ] TUI beenden und neu starten: die zuletzt gelesene Stelle öffnet sich wieder (auch nach Wegwischen von Termux).
- [ ] Notizen: Knopf **Notiz**, Treffer antippen springt zur Stelle.
- [ ] Korrektur: Absatz mit **K** markieren, **Korr** öffnet den Dialog; Text ändern, **Übernehmen**; alle Knöpfe sichtbar und antippbar.
- [ ] Speedreader: Knopf **Speed**, **Start**, Tempo ändern, Sprungknöpfe; die Wortzeile und alle Knöpfe sind vollständig sichtbar. Ist das Standardtempo von 400 Wörtern pro Minute angenehm?
- [ ] Im Querformat (ab 80 Spalten) steht der Baum neben dem Text.
- [ ] DeX: Fenster über/unter 80 Spalten ziehen, Baum wechselt zwischen Schublade und Seitenleiste.
- [ ] DeX: Mausklick auf Kapitel und Mausrad im Text funktionieren.
- [ ] DeX: Strg+S im Editor mit physischer Tastatur speichert (ohne Zusatzzeile).
- [ ] DeX: Termux läuft bei verkleinertem Fenster weiter, Syncthing wird nicht beendet.
