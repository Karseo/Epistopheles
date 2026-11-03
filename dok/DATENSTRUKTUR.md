# Datenstruktur der Bibliothekswurzel

Stand 2026-11-02. Ersetzt die Aufteilung `Autor\` + `eBooks\` + lose Ordner. Leitgedanke: **Roh-Daten,
fertige Reader-Daten, Skripte und Hilfsdaten liegen in je einem eigenen Ordner**, damit klar ist, was
synchronisiert, versioniert und regeneriert wird.

```
D:\Workspace\!Episto\
├─ rohdaten\                    ALLE Roh-Daten        (nicht in Git, nicht in Syncthing)
│   ├─ Inbox\                   Quelldateien (EPUB/PDF), Eingang der Pipeline
│   ├─ Lektor\<Autor>\<Titel>\  Arbeitsordner je Buch: {en,de}\chunk_NNN.md, Quelldatei, meta.json, kapitel.json
│   ├─ Outbox\  Transfer\       Ausgaben und Handarbeit
│   └─ en-chunks\<Autor>\<Titel>\chunk_NNN.md    englische Referenzchunks je Buch (für die TUI-Korrektur)
├─ reader\                      FERTIGE Daten für den Reader (Git + Syncthing)
│   ├─ <Autor>\<Titel>\         quelle\*.md (Source of Truth), kapitel.json, meta.json, notizen\, querbezuege\, .progress.json
│   └─ export-epistopheles\     erzeugtes Chromebook-Paket (kein Buch; nicht in Git/Syncthing)
├─ tools\                       ALLE Skripte          (Git + Syncthing)
│   ├─ episto_tui\  speedreader_web\  ingest.*  taggen.ps1  straenge.ps1  lektor-zu-episto.py  …
│   └─ pipeline\                Übersetzungs-Pipeline (ebook-translate.py, detect-chapters.py, …, index.md)
├─ hilfsdaten\                  themen.json, notizen\ (Buch-Queue), konzepte\, archiv\ (Altbestand)
├─ dok\                         Dokumentation
└─ CLAUDE.md  .gitignore  .stignore  !code!.ps1
```

## Regeln

- **Roh → fertig nur über Skripte.** `rohdaten\Lektor` wird von `tools\pipeline\ebook-translate.py` gefüllt;
  `tools\lektor-zu-episto.py` baut daraus `reader\<Autor>\<Titel>\` und kopiert die Referenzchunks nach
  `rohdaten\en-chunks`. Der Reader (TUI, Epistopheles) liest nie aus `rohdaten`, ausgenommen die
  Korrektur-Funktion (englisches Original).
- **Autor-/Titelordner sind Schlüssel.** Ihre Namen stehen in Qdrant (`autor`, `buch`), in
  `~/.episto_tui/zustand.json` und verbinden `reader\<A>\<T>` mit `rohdaten\Lektor\<A>\<T>` und
  `rohdaten\en-chunks\<A>\<T>`. Sie dürfen nur zusammen mit diesen Stellen umbenannt werden. Der
  Wurzelname `reader` selbst ist frei (Qdrant speichert nur Namen, keine Pfade).
- **Tiefe bleibt fest:** `<Wurzel>\reader\<Autor>\<Titel>` (`library.root_von` = `parents[2]`).
- **Nicht synchronisieren/versionieren:** `rohdaten`, `reader/export-epistopheles`, `hilfsdaten/archiv`
  (`.stignore`, `.gitignore`). Auf dem Handy müssen diese Zeilen von Hand in Syncthing eingetragen werden
  (`dok/TERMUX.md`).

## Redaktion (Korrekturen vom Gerät)

| Was | Wo |
|---|---|
| Eingang der Einträge | `hilfsdaten\redaktion\eingang\<Buchschlüssel>\` (eine Datei je Sendung, `_stand.json` mit dem Status je `id`); der Buchschlüssel `Autor, Vorname/Titel` wird geprüft und bei Unsicherheit abgelehnt |
| Token des Empfängers | `hilfsdaten\redaktion\token.txt` (nie im Paket, nicht in Git/Syncthing) |
| angewendete Korrekturen, Chunks | `rohdaten\Lektor\<Autor>\<Titel>\redaktion.json` (`ebook-translate.py` bricht ohne `--resume` ab, solange sie existiert) |
| angewendete Korrekturen, Volltext | `reader\<Autor>\<Werk>\notizen\redaktion.json`: `eintraege` (Ebene `volltext`, Anwendungsreihenfolge) und `dateien` (je `quelle\*.md`: `hash_original`, `hash_aktuell`, `zuletzt`); versioniert und synchronisiert; `lektor-zu-episto.py --ueberschreiben` spielt sie nach dem Neuaufbau wieder ein |
| Bericht des Nachspiels | `reader\<Autor>\<Werk>\notizen\redaktion-nachspiel.json` (nicht anwendbare Einträge einzeln mit `id`, `datei`, `grund`; `basis_geaendert`); verschwindet, wenn nichts zu melden ist; die Konflikte gehen als `nachspiel` in den Export, eine Rücknahme löst sie auf (Eintrag im Protokoll dann `zurueckgenommen`) |
| Backups vor jedem Schreiben | Chunks: `rohdaten\Lektor\<Autor>\<Titel>\notizen\_backup`; Volltext: `reader\<Autor>\<Werk>\notizen\_backup` (auch `quelle-<Zeit>\` vor `lektor-zu-episto.py --ueberschreiben`, wenn das Protokoll Volltext-Einträge enthält) |
| Stand im Export | `reader\export-epistopheles\korrektur\k0xx.json`: je Kapitel `datei`, dazu `enthalten` (Ids angewendeter Volltext-Einträge, die im Text stecken, ohne Nachspiel-Konflikte) und `nachspiel` (Id → Grund der Einträge, die der Neuaufbau nicht wieder einspielen konnte); `index.json`: je Buch `reader` / `lektor` (Schlüssel `Autor/Titel`) und `chunkSprache` |
| Übersetzungsvorschläge | `de\chunk_NNN.md.neu` im Lektor-Buchordner, bis zur Übernahme |

Programme: `tools\redaktion_server.py` (Empfänger, von Hand starten), `tools\redaktion_anwenden.py`
(Einarbeiten, Dry-Run als Standard); Bedienung und Exit-Codes: `tools\speedreader_web\README.md`, Abschnitt „Redaktion“.

## Verbindungen (Querverbindungen in der App)

| Was | Wo |
|---|---|
| Datei | `reader\export-epistopheles\verbindungen.json`, erzeugt von `tools\speedreader_web\export_verbindungen.py` nach `export_daten.py` (nicht in Git/Syncthing; Vektoren bleiben in Qdrant) |
| Format | `{version: 1, erstellt (= daten.json), qdrant: {abgefragt, fehlend, mindestwert} oder null, werke: [{id, autor, titel}], kapitel: [{id "b001:3", werk, nr, titel}], themen: [{id "b001#slug", werk, name, kapitel: [nr]}], aehnlich: [{von, nach, wert, beleg ≤ 140 Zeichen}], querverweise: [{von, nach oder null, autor, titel, relation, notiz}]}` |
| Ids | Werk `b001`, Kapitel `b001:3`, Thema `b001#slug` (gelten nur innerhalb eines Exports, wie `daten.json`); Werk außerhalb der Bibliothek `x:<Autor>\|<Titel>` (nur in der App, hohl) |
| Quellen | Themen: `reader\<Autor>\<Werk>\notizen\straenge\*.md`; Querverweise: `querbezuege\querbezuege.json`; Ähnlichkeit: Qdrant `episto` (nur lesend, Zuordnung über Payload Autor/Buch/Kapitelnummer, Punkt-Ids werden nicht gespeichert) |

## Wo im Code die Namen stehen

| Was | Wo |
|---|---|
| `reader`, `rohdaten`, `export-epistopheles` | `tools/episto_tui/library.py` (`READER_ORDNER`, `ROHDATEN_ORDNER`, `EXPORT_ORDNER`) |
| englische Referenzchunks | `library.rohchunks_en_ordner(buch)` (Rückfall auf `<Buch>\en` nur für Altbestand) |
| Lektor-Ordner, `BASE` der Pipeline | `tools/pipeline/*.py`: `BASE = <Wurzel>\rohdaten` (Env `EBOOK_BASE`); `themen.json` aus `hilfsdaten` (Env `EBOOK_HILFSDATEN`) |
| alte Quellpfade in `meta.json` | `tools/pipeline/ebook_pfade.py`, `korrektur.lektor_pfad_von`, `export_korrektur.pfad_aus_meta`: alles hinter `…\eBooks\` wird unter `rohdaten` neu aufgesetzt |
| `reader`-Standardpfade der Skripte | `ingest.py/.ps1`, `episto-tui.ps1`, `neu-zusammenfassen.py`, `lektor-zu-episto.py`, `ocr-zu-episto.py` |
| Epistopheles-Paket | `tools/speedreader_web/bundle.py` (`reader\export-epistopheles`, App-Dateien werden mitkopiert) |

## Umzug vom alten Aufbau (einmalig, 2026-11)

Der Umbau hat zwei Teile, weil ein Teil in Git liegt und ein Teil nicht:

1. Branch `worktree-datenstruktur` (versioniert): `Autor\` → `reader\`, `Autor.mov\` → `hilfsdaten\archiv\`,
   en-Chunks aus Git, Pipeline-Skripte nach `tools\pipeline`, Code, Tests, Doku, Ignore-Regeln.
2. `tools\umbau_datenstruktur.py` (unversioniert/ignoriert): `eBooks\Inbox|Lektor|Outbox|Transfer` und
   Wurzel-`Inbox\` → `rohdaten\`, en-Chunks → `rohdaten\en-chunks`, ignorierte Notizen und neue Bücher aus
   `Autor\` → `reader\`, `notizen\` → `hilfsdaten\notizen`, alte `eBooks`-Skripte → `hilfsdaten\archiv`.

Ablauf: Syncthing pausieren → getrackte Änderungen committen → `umbau_datenstruktur.py vorher --ausfuehren` →
`git merge worktree-datenstruktur` → `umbau_datenstruktur.py nachher --ausfuehren` → `… pruefen` → Syncthing
wieder starten (am Handy erst nach Aktualisierung der Ignorierliste). Das Skript überschreibt nie, führt nur
identische Dateien zusammen und meldet abweichende (Exit-Code 2). Jeder Schritt hat einen Dry-Run (ohne `--ausfuehren`).

### Handy (Termux) nach dem Umzug

1. Syncthing am Handy erst starten, wenn der PC fertig ist.
2. Ignoriermuster ergänzen: `rohdaten`, `reader/export-epistopheles`, `hilfsdaten/archiv`.
3. Startbefehl unverändert: `sh ~/episto/tools/episto-tui.sh` (`tools\` heißt weiter `tools`).
4. Danach die Leseposition prüfen (`~/.episto_tui/zustand.json` hält `<Autor>/<Titel>`, nicht Pfade).
