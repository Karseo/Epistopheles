# Querverbindungen auf Epistopheles: Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Entwurf, wartet auf Freigabe (Abschnitt „Entscheidungen zur Freigabe“). Umsetzung erst danach.

**Goal:** In der Chromebook-App `index.html` eine Ansicht **Verbindungen**, die zum offenen Kapitel zeigt, womit es zusammenhängt: ähnliche Stellen in anderen Werken (aus Qdrant), Themen (Stränge) und Querverweise auf andere Werke (aus den Dateien `notizen\straenge\*.md` und `querbezuege\querbezuege.json`). Dargestellt als **Netz um das aktuelle Kapitel** wie im Referenzbild (dunkler Grund, Fokusknoten in der Mitte, Kanten zu beschrifteten Nachbarn, weiter entfernte Knoten verblasst), mit Tippen zum Weiterwandern und Springen ins Kapitel.

**Architecture:** Die App spricht **nie** mit Qdrant. Ein neues Exportskript `tools\speedreader_web\export_verbindungen.py` läuft auf APIC, liest Themen und Querverweise aus den Buchordnern und fragt Qdrant (nur lesend) nach den ähnlichsten Chunks anderer Werke ab, fasst sie je Kapitel zusammen und schreibt `verbindungen.json` neben `daten.json` ins Paket `reader\export-epistopheles`. In der App berechnen zwei kleine reine JS-Module (`verbindungen.js`: Ausschnitt um den Fokus, `graphlayout.js`: Anordnung) die Darstellung; `graphansicht.js` zeichnet auf einem Canvas und behandelt Berührung. Alles offline, ohne Fremdbibliothek.

**Tech Stack:** Python ≥ 3.10 (nur Standardbibliothek für Neues, wie `ingest.py`), reines HTML/JS ohne Fremdbibliothek, Tests mit pytest und Node, Browserprüfung mit Playwright.

**Basis:** `main` nach Merge von Redaktion P2 (Merge-Commit `8a9cec9`). Testlauf vor Beginn: `cd tools && python -m pytest speedreader_web redaktion test_redaktion_anwenden.py test_redaktion_server.py pipeline -q` → 687 bestanden.

## Ausgangslage (belegt)

- **Qdrant** (`ingest.py`): Collection `episto`, Cosine, 1024 Dimensionen. Je Punkt ein Chunk eines Kapitels, Payload `buch`, `autor`, `datei`, `kapitel_nr`, `abschnitt`, `chunk_idx`, `text`. **Verbindungen sind nicht gespeichert**, nur Vektoren; Punkt-Ids (`next_id`) sind nicht stabil (neu vergeben bei `-Reset`). Die Vektoren sind regenerierbar. Qdrant und Ollama laufen nur auf APIC (`127.0.0.1`).
- **Stränge** (`straenge.ps1`): je Werk `notizen\straenge\<slug>.md` mit Kopf (`strang`, `slug`, `treffer`) und Abschnitten `### Kapitel <nr> · <Abschnitt>`; Index `_strang_index.json`. Ein Strang gehört zu **einem** Werk. Einlesen: `library._parse_strang_datei`.
- **Querverweise** (`querbezuege\querbezuege.json`): je Werk `bezuege[]` mit `ziel` (`<nachname>_<titel-slug>`), `autor`, `titel`, `relation`, `notiz`. Sie gelten für das **ganze Werk**. `library.finde_buch_fuer_ziel` löst sie auf; **bei rund zwei Dritteln liegt das Zielwerk nicht in der Bibliothek.**
- **Web-App:** `index.html` kennt nur Speed / KI-Text / Original (Tasten 1 bis 3), Daten aus `daten.json` (Bücher mit `id`, Kapitel mit `nr`, KI-Felder) und `buecher\bNNN.json`, mit IndexedDB-Zwischenspeicher und `erstellt`-Abgleich. Stränge und Querverweise zeigt sie **nicht**; `export_daten.py` nimmt nur die KI-Felder mit. Die TUI und Termux zeigen Stränge und Querverweise als Listen.
- **Referenzbild** (vom Nutzer): ein lokaler Graph wie in Obsidian: dunkler Grund, ein hervorgehobener Knoten in der Mitte (violett, Beschriftung darunter), rund 12 beschriftete Nachbarn mit dünnen, zur Mitte laufenden Linien, rund 15 weitere Knoten **verblasst und klein**, ohne Linien zur Mitte.

## Global Constraints

- Epistopheles: 4 GB RAM, Chrome/ChromeOS, Touch, 960×600 bis 600×960, Bedienelemente und Trefferflächen mindestens 44 px, alle Oberflächentexte deutsch mit Umlauten, hell und dunkel nach den bestehenden Farbvariablen (das Bild entspricht dem dunklen Thema).
- **Offline:** die App liest nur `verbindungen.json` (bzw. die importierte Kopie). Kein Netzzugriff zu Qdrant oder Ollama, auch nicht optional.
- Keine Fremdbibliothek in der App; auf APIC für alles Neue nur Python-Standardbibliothek.
- **Qdrant nur lesend** (Scroll und Abfragen; nie Schreiben, nie Löschen). Ist Qdrant nicht erreichbar, entsteht trotzdem ein Export mit Themen und Querverweisen und einer ausdrücklichen Warnung; ein **unvollständiger** Ähnlichkeitsteil wird nie als vollständig ausgegeben (Anzahl abgefragt / fehlend steht im Export).
- Der Export ist regenerierbar, steht nicht im Repo (wie `daten.json`) und trägt dieselbe `erstellt`-Zeit wie `daten.json`, damit die App Stände nicht mischt.
- Es wird nur das Netz um **ein** Kapitel im Speicher gehalten (höchstens rund 40 Knoten); kein Gesamtgraph.
- Keine Änderungen an der TUI. Ausnahme: eine reine Hilfsfunktion in `episto_tui\library.py` (Task 2), die das bestehende Verhalten nicht ändert.

## Review Focus

1. **Passende Ids:** `verbindungen.json` verweist auf `b001`/`nr` aus `daten.json` (Buch-Ids gelten nur innerhalb eines Exports). Stimmt `erstellt` nicht überein oder fehlt ein Knoten in `daten.json`, darf die App nichts Falsches verbinden, sondern meldet es. Tests in Task 5 und 9.
2. **Unvollständige oder ausgefallene Qdrant-Abfrage:** keine halbe Datei als vollständig (atomares Schreiben, Zähler im Export, Warnung). Test mit Attrappe, die mittendrin ausfällt (Task 4, 5).
3. **Kanten:** keine Kante auf sich selbst, keine Verbindung innerhalb desselben Werks (Ähnlichkeit), keine Doppelkanten (A→B und B→A werden zu einer Kante mit dem besseren Wert). Test in Task 4 und 6.
4. **Speicher und Zeit auf dem Gerät:** `verbindungen.json` höchstens rund 2 MB bei rund 950 Kapiteln, Anordnung von 40 Knoten unter 50 ms, kein Neuzeichnen im Leerlauf. Messung in Task 7, 9, 10.
5. **Touch:** Trefferfläche je Knoten ≥ 44 px auch bei kleiner Darstellung, Ziehen und Zoomen kollidieren nicht mit dem Scrollen der Seite, Tippen verwechselt nie Knoten und Hintergrund. Browsertest und Handprüfung (Task 8, 10).
6. **Zielwerke außerhalb der Bibliothek** (zwei Drittel der Querverweise): erscheinen als nicht öffnende Knoten, nie als toter Sprung (Task 3, 6, 8).
7. **Lesbarkeit:** Beschriftungen überlappen nicht unlesbar; es gibt zu jedem Netz eine gleichwertige **Liste** (Barrierefreiheit, kleines Display).

---

## Entscheidungen zur Freigabe

Voreinstellungen, bitte gegenlesen:

1. **Vorberechnet statt live.** Die Ähnlichkeiten werden auf APIC beim Export aus Qdrant gelesen. Eine freie semantische Suche vom Chromebook (über den Empfänger) ist **nicht Teil dieses Plans**.
2. **Knoten und Kanten** (an das Bild angelehnt):
   - **Kapitel** (Kreis, Farbe je Werk, Beschriftung `Kurzname · Kapiteltitel`), **Thema** (Raute; ein Strang eines Werks), **Werk** (Ring; nur als Zielpunkt von Querverweisen und als Anker der eigenen Kapitel; Werke außerhalb der Bibliothek hohl und nicht öffenbar).
   - Kanten: **ähnlich** (Qdrant, Kapitel–Kapitel anderer Werke, Strichstärke nach Wert), **Thema** (Kapitel–Thema, dünn), **Querverweis** (Werk–Werk, gestrichelt, Beschriftung mit der Relation, z. B. „ergänzt“), **gehört zu** (Kapitel–Werk, sehr schwach). Themen sind Knoten statt Kapitel-Kapitel-Kanten, damit kein Kantengewirr (n²) entsteht.
3. **Ähnlichkeit nur zwischen verschiedenen Werken**, höchstens 8 je Kapitel. Je Kapitel werden die Chunk-Nachbarn aller seiner Chunks zusammengefasst; **Rang eines Zielkapitels = Summe der drei besten Chunk-Paare**, Mindestwert nach Kalibrierung (Startwert 0,55 Cosinus). Als Beleg kommt je Kante ein kurzer Ausschnitt (höchstens 140 Zeichen) des Zielchunks mit.
4. **Darstellung = Fokusnetz, nicht Gesamtgraph:** Fokus (Mitte, hervorgehoben, Beschriftung darunter), **Ring 1** (bis 14 stärkste Nachbarn, beschriftet, Linien zur Mitte), **Ring 2** (bis 14 weitere, klein und verblasst, ohne Linie zur Mitte, wie im Bild). **Tippen auf einen Knoten** setzt ihn in die Mitte (weiche Bewegung); eine Leiste zeigt ihn mit dem Beleg und dem Knopf **Öffnen** (springt in dieses Kapitel der Ansicht KI-Text). Ziehen verschiebt, Zwei-Finger-Zoom (und Knöpfe + / −) zoomt. Filterknöpfe schalten Kantenarten ein und aus.
5. **Eigene kleine Kräfte-Berechnung** auf einem Canvas (Abstoßung, Federn, Mittenanziehung, feste Ringradien als Startlage, deterministisch); keine Bibliothek.
6. **Gleichwertige Liste** neben oder unter dem Netz (gleiche Daten, gruppiert nach Kantenart), per Knopf umschaltbar; sie ist auf dem kleinen Display und für Bildschirmleser die verlässliche Bedienung.
7. **Neue Ansicht in `index.html`** (Taste 4) statt eigener Seite: sie teilt sich Buch und Kapitel mit den anderen Ansichten. Die Daten stehen in einer eigenen Datei `verbindungen.json` mit IndexedDB-Zwischenspeicher und Import wie bei `daten.json`.
8. **Eine Hilfsfunktion in `library.py`:** `list_straenge(buch)` (Name, Slug, Kapitelnummern) nach dem Muster von `read_straenge_uebersicht`; kein bestehendes Verhalten ändert sich.
9. **Kalibrierung nur auf APIC möglich** (hier gibt es kein Qdrant): Mindestwert, Anzahl je Kapitel und Rangformel werden dort an echten Büchern geprüft (Task 4, Schritt 5); der Plan liefert dafür ein Hilfsskript.

**Nicht Teil von P-Querverbindungen:** freie semantische Suche, Gesamtgraph, Bearbeiten von Strängen oder Querverweisen in der App (bleiben Dateien), Anzeige einzelner Chunks oder absatzgenaues Springen (nur das Kapitel; der Beleg ist Vorschau), Schreibzugriff auf Qdrant, Termux/TUI.

---

## Dateiübersicht

| Datei | Aufgabe |
|---|---|
| `tools/speedreader_web/export_verbindungen.py` | Exportskript: Themen, Querverweise, Ähnlichkeit → `verbindungen.json` |
| `tools/speedreader_web/qdrant_nachbarn.py` | Qdrant lesend: Punkte lesen, Nachbarn abfragen, zu Kapitelkanten zusammenfassen (reine Standardbibliothek) |
| `tools/speedreader_web/verbindungen_stichprobe.py` | Hilfswerkzeug für APIC: Verteilung der Werte, Kalibrierung (kein Test) |
| `tools/episto_tui/library.py` | `list_straenge` |
| `tools/speedreader_web/verbindungen.js` | reiner Kern: Index, Fokusausschnitt, Filter |
| `tools/speedreader_web/graphlayout.js` | reine Anordnung |
| `tools/speedreader_web/graphansicht.js` | Canvas, Berührung, Liste |
| `tools/speedreader_web/index.html`, `bundle.py` | Ansicht „Verbindungen“, Laden, Import; `APP_DATEIEN` |
| `tools/speedreader_web/README.md`, `dok/DATENSTRUKTUR.md`, `CLAUDE.md`, `dok/NÄCHSTE_SCHRITTE.md` | Dokumentation |

Tests liegen neben dem Code (`test_*.py`); Browsertests brauchen Playwright mit passendem Chromium.

## Format `verbindungen.json` (Grundlage aller Aufgaben)

```
{ "version": 1, "erstellt": "<wie daten.json>",
  "qdrant": { "abgefragt": 1234, "fehlend": 0, "mindestwert": 0.55 } | null,
  "werke":   [ { "id": "b001", "autor": "…", "titel": "…" } ],                    // Buch-Id wie in daten.json
  "kapitel": [ { "id": "b001:3", "werk": "b001", "nr": 3, "titel": "…" } ],       // nur Kapitel, die auch in daten.json stehen
  "themen":  [ { "id": "b001#strang-slug", "werk": "b001", "name": "…", "kapitel": [3, 5, 9] } ],
  "aehnlich":[ { "von": "b001:3", "nach": "b007:2", "wert": 0.71, "beleg": "…≤140 Zeichen…" } ],   // gerichtet; die App vereinigt beide Richtungen
  "querverweise": [ { "von": "b001", "nach": "b007" | null, "autor": "…", "titel": "…", "relation": "ergaenzt", "notiz": "…" } ] }
```

Punkt-Ids aus Qdrant stehen **nicht** im Export (nicht stabil); Zuordnung nur über `autor`, `buch`, `kapitel_nr`.

---

## Aufgaben

### Task 1: Themen aus den Strängen lesen

**Files:**
- Modify: `tools/episto_tui/library.py` (neue Funktion `list_straenge`)
- Test: `tools/episto_tui/tests/test_library_straenge.py`

**Interfaces:**
- `list_straenge(buch: Buch) -> list[dict]`: je Strang `{"name", "slug", "kapitel": [nr, …]}` (Kapitelnummern aufsteigend, ohne Doppelte; `slug` aus dem Dateinamen; Strang ohne Fundstelle entfällt; Syncthing-Konfliktdateien `.sync-conflict-` werden übersprungen). Fehlender Ordner oder kaputte Datei: leere Liste beziehungsweise Datei übersprungen, nie eine Ausnahme.

- [ ] **Step 1: Failing tests:** zwei Stränge mit Fundstellen in mehreren Kapiteln; Strang ohne Treffer; kaputte Datei; Konfliktdatei; fehlender Ordner; bestehende Funktionen (`read_straenge_for_chapter`, `read_straenge_uebersicht`) unverändert (vorhandene Tests grün).
- [ ] **Step 2–4:** rot, implementieren (auf `_parse_strang_datei` aufbauen), grün.
- [ ] **Step 5: Commit** `feat: list_straenge für die Verbindungsansicht`.

### Task 2: Querverweise auflösen und Knotenlisten bilden

**Files:**
- Create: `tools/speedreader_web/export_verbindungen.py` (Teil 1: Werke, Kapitel, Themen, Querverweise)
- Test: `tools/speedreader_web/test_export_verbindungen.py`

**Interfaces:**
- Consumes: `daten.json` des Pakets (liest nur `erstellt`, `buecher[].id/autor/titel`, `buecher[].kapitel[].nr/titel`), `library.discover_books`, `library.list_straenge`, `library.read_querbezuege`, `library.finde_buch_fuer_ziel`.
- Produces: `baue_basis(root: Path, daten: dict) -> dict` (Felder `werke`, `kapitel`, `themen`, `querverweise` im Format oben). Nur Bücher und Kapitel, die in `daten.json` stehen; Themen verweisen nur auf Kapitel, die es dort gibt (sonst entfällt die Nummer, Themen mit weniger als 2 Kapiteln entfallen); Querverweis: `nach` = Buch-Id, wenn das Zielwerk in der Bibliothek **und** in `daten.json` liegt, sonst `null` mit `autor`/`titel` des Verweises. Beim Lesen ungültige Einträge werden übersprungen (Datei kaputt, `bezuege` keine Liste, Eintrag kein Objekt).

- [ ] **Step 1: Failing tests** (Modellbaum in `tmp_path`): Themen und Kapitelfilter (Kapitel ohne KI-Felder entfällt auch im Strang); Querverweis auf Werk in der Bibliothek, auf Werk außerhalb (`nach` null), auf Werk in der Bibliothek aber ohne Eintrag in `daten.json` (`nach` null); kaputte `querbezuege.json`; Umlaute in Titeln; Ids `b001:3` und `b001#slug` stabil und eindeutig (Slugs doppelt in zwei Werken ergeben zwei Themen).
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: Basis der Verbindungsdaten (Werke, Kapitel, Themen, Querverweise)`.

### Task 3: Qdrant lesen und Ähnlichkeit zu Kapitelkanten zusammenfassen

**Files:**
- Create: `tools/speedreader_web/qdrant_nachbarn.py`
- Test: `tools/speedreader_web/test_qdrant_nachbarn.py` (mit Attrappen-Server auf `http.server` in einem Thread, wie `test_redaktion_server.py`)

**Interfaces:**
- `lese_punkte(qdrant: str, collection: str, fetch=...) -> dict[int, dict]`: Scroll (Seitenweise, `with_vector: false`, nur die Payload-Felder `autor`, `buch`, `kapitel_nr`, `chunk_idx`), Punkt-Id → Schlüsselfelder.
- `frage_nachbarn(qdrant, collection, punkt_ids: list[int], je: int, fetch=...) -> dict[int, list[Treffer]]`: je Punkt die ähnlichsten Punkte **anderer Werke** (Filter `must_not` auf `buch` des Ausgangspunkts, serverseitig), `Treffer = {id, wert, autor, buch, kapitel_nr, text}` (`text` auf 140 Zeichen gekürzt). Bevorzugt `POST /collections/<c>/points/query/batch` (Qdrant ≥ 1.10, die Abfrage nimmt die Punkt-Id als Eingabe, **kein Ollama-Aufruf nötig**), Rückfall auf `points/recommend`; Batchgröße einstellbar. Fehler einer Anfrage werden gezählt (`fehlend`), nie verschluckt; Wiederholung mit Pause bei Netzfehlern (wie `ingest.py`).
- `fasse_zusammen(nachbarn, punkte, kapitel_ids, mindestwert, je_kapitel=8) -> list[dict]`: Kapitelkanten im Format `aehnlich`: Kapitel A → Kapitel B über alle Chunk-Paare; Rang = Summe der drei besten Paare; unter `mindestwert` fällt weg; keine Kante auf sich selbst oder innerhalb desselben Werks; Beleg = Text des besten Zielchunks; Kapitel, die nicht in `kapitel_ids` stehen, entfallen.

- [ ] **Step 1: Failing tests:** `fasse_zusammen` rein (Rangformel, Mindestwert, höchstens 8, nie Selbstkante oder gleiches Werk, unbekanntes Kapitel entfällt, deterministische Reihenfolge bei Gleichstand); Attrappe: Scroll über mehrere Seiten, Batch-Abfrage mit Filter (der Filter steht im Request), Rückfall auf `recommend` bei 404 der Query-API, Netzfehler mit Wiederholung, endgültig fehlgeschlagene Anfrage erhöht `fehlend` und bricht nicht ab; **nur lesende Aufrufe** (die Attrappe lässt alles außer `scroll`, `query`, `recommend`, `GET collections` mit 405 scheitern; der Test beweist, dass nie geschrieben oder gelöscht wird).
- [ ] **Step 2–4:** rot, implementieren (`urllib`, `json`, nur Standardbibliothek; Antworten als UTF-8 lesen, wie in `suche.ps1` begründet), grün.
- [ ] **Step 5: Kalibrierung auf APIC (von dir auszuführen, hier nicht möglich):** `verbindungen_stichprobe.py` fragt für 20 zufällige Kapitel ab und gibt die Verteilung der Werte, die Zahl der Kanten je Kapitel und je Kapitel die besten drei Belege aus. Mindestwert, `je_kapitel` und Rangformel so wählen, dass ein Kapitel typischerweise 4 bis 8 plausible Nachbarn hat; Zahlen im Commit nennen.
- [ ] **Step 6: Commit** `feat: Ähnlichkeit zwischen Kapiteln aus Qdrant (lesend)`.

### Task 4: Export zusammenführen und ins Paket schreiben

**Files:**
- Modify: `tools/speedreader_web/export_verbindungen.py` (`exportiere`, `main`), `tools/speedreader_web/bundle.py` (Standardpfad, kein neuer App-Dateiname hier)
- Test: `tools/speedreader_web/test_export_verbindungen.py` (erweitern)

**Interfaces:**
- `exportiere(root: Path, ordner: Path | None = None, qdrant: str | None = "http://127.0.0.1:6333", collection="episto", mindestwert=…, fetch=...) -> dict`: liest `daten.json` im Paketordner (fehlt sie: `ValueError` mit dem Hinweis, zuerst `export_daten.py` auszuführen), baut `baue_basis`, ergänzt `aehnlich` und `qdrant`-Zähler, setzt `erstellt` aus `daten.json`, schreibt `verbindungen.json` **atomar** (temporäre Datei, dann `os.replace`). `qdrant=None` oder nicht erreichbar → `aehnlich: []`, `qdrant: null`, Warnung in der Ausgabe; Rückgabewert enthält `warnungen`.
- `main(argv) -> int` (`--root`, `--out`, `--qdrant URL`, `--collection`, `--ohne-qdrant`, `--mindestwert`); Exit 0 vollständig, 3 mit Warnungen (Qdrant fehlt oder `fehlend > 0`), 1 bei ungültiger Eingabe oder fehlender `daten.json`.

- [ ] **Step 1: Failing tests** (Testwurzel mit Attrappen-Qdrant): vollständiger Export (Felder, `erstellt` gleich `daten.json`, `qdrant.fehlend == 0`); ohne Qdrant Exit 3 und leerer Ähnlichkeitsteil; Qdrant fällt mitten im Lauf aus: `fehlend > 0`, Exit 3, **keine** stillschweigend vollständige Datei, vorhandene alte Datei bleibt bei Abbruch vor dem Schreiben erhalten; fehlende `daten.json` Exit 1; Größe der Datei für eine künstliche Bibliothek mit 950 Kapiteln und 8 Kanten je Kapitel unter 2 MB (Review Focus 4); Umlaute und Sonderzeichen unverändert.
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: verbindungen.json exportieren`.

### Task 5: Kern der Ansicht (reine Funktionen in JavaScript)

**Files:**
- Create: `tools/speedreader_web/verbindungen.js`
- Test: `tools/speedreader_web/test_verbindungen_js.py` (Node)

**Interfaces:**
- `Verbindungen.baue(daten) -> Graph`: Index aus `verbindungen.json`: Knoten nach Id, Nachbarschaftslisten **beider Richtungen** für `aehnlich` (bei A→B und B→A gilt der bessere Wert, eine Kante), Themen- und Werkkanten, Querverweiskanten (Werk–Werk, auch zu hohlen Zielen).
- `Verbindungen.fokus(graph, knotenId, optionen) -> {knoten: [{id, typ: "kapitel"|"thema"|"werk", ring: 0|1|2, label, werk, offen: bool}], kanten: [{von, nach, art, wert, label}]}` mit `optionen = {arten: {...}, ring1: 14, ring2: 14}`: Ring 1 = stärkste direkte Nachbarn (Rang: ähnlich nach Wert, dann Themen, dann Werk), Ring 2 = Nachbarn der Nachbarn (verblasst, **nur Knoten, keine Kanten zur Mitte**; Kanten zwischen Ring-1-Knoten bleiben). Filter nach Kantenart; deterministisch; höchstens `ring1 + ring2 + 1` Knoten.
- `Verbindungen.liste(graph, knotenId) -> [{gruppe, eintraege}]` (gleiche Daten als Liste: Ähnliche Stellen, Themen, Querverweise).
- `Verbindungen.pruefe(daten, tageDaten) -> {ok, grund}`: Abgleich von `erstellt` mit `daten.json`; Kapitel-Ids, die es dort nicht gibt, werden gemeldet (Review Focus 1).

- [ ] **Step 1: Failing tests:** Spiegelung der Kanten (A→B und B→A ergeben eine Kante mit dem Maximum); Obergrenzen; Filter; Fokus auf Thema und auf Werk; hohles Werk (`offen: false`, nicht fokussierbar); Querverweis-Beschriftung; Ring 2 ohne Kante zur Mitte; Reihenfolge deterministisch; `pruefe` bei abweichendem `erstellt` und unbekannter Id; Leistung: Graph aus 950 Kapiteln und 7 600 Kanten bauen unter 300 ms, Fokus unter 10 ms (großzügige Grenzen 1000 ms und 50 ms).
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: Kern der Verbindungsansicht (Fokusausschnitt, Filter, Liste)`.

### Task 6: Anordnung (reine Funktion)

**Files:**
- Create: `tools/speedreader_web/graphlayout.js`
- Test: `tools/speedreader_web/test_graphlayout.py` (Node)

**Interfaces:**
- `Graphlayout.ordne(fokus, breite, hoehe, optionen) -> {positionen: {id: {x, y}}, radius: {id: r}}`: Startlage auf Ringen (Fokus in der Mitte, Ring 1 gleichmäßig auf dem inneren, Ring 2 auf dem äußeren Kreis, Winkel deterministisch aus der Id), dann feste Zahl Schritte (Standard 120) einer Kräfteberechnung (Abstoßung, Federn der Kanten, Mittenanziehung, Begrenzung auf die Fläche). Knotenradien: Fokus groß, Ring 1 mittel, Ring 2 klein. **Kein Zufall** (gleiche Eingabe → gleiche Anordnung).

- [ ] **Step 1: Failing tests:** deterministisch; alle Knoten innerhalb der Fläche mit Rand; Fokus nahe der Mitte; keine zwei Knoten näher als die Summe ihrer Radien (bei höchstens 40 Knoten in 600×400); Ring-2-Knoten weiter außen als Ring-1-Knoten im Mittel; Leistung: 40 Knoten unter 50 ms (großzügige Grenze 200 ms); ein einziger Knoten und ein leerer Ausschnitt ergeben keine Ausnahme.
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: deterministische Anordnung des Fokusnetzes`.

### Task 7: Zeichnen und Berührung (Canvas)

**Files:**
- Create: `tools/speedreader_web/graphansicht.js`
- Test: `tools/speedreader_web/test_graphansicht.py` (Node für die reinen Teile)

**Interfaces:**
- Reine Teile: `trifft(positionen, radius, transform, x, y, mindestRadius=22) -> id | null` (Trefferfläche mindestens 44 px, auch bei Zoom; nächster Knoten gewinnt), `beschriftungen(positionen, radius, breite, hoehe) -> {id: {x, y, ausrichtung}}` (Beschriftung neben dem Knoten, vermeidet Überlappung und Ränder; Fokus unterhalb wie im Bild), `uebergang(von, nach, t)`.
- DOM: `Graphansicht.installiere(eltern, optionen) -> {setzeFokus(id), setzeDaten(graph), setzeArten(arten), zerstoere()}`. Zeichnung wie im Bild: Grund aus `--bg`, Fokus mit Hof in `--akzent`, Kanten dünn in gedämpfter Akzentfarbe (stärker bei höherem Wert, Querverweise gestrichelt mit Relation), Ring 2 klein und halbtransparent ohne Beschriftung, Ring 1 mit heller Beschriftung; Werkfarben aus einer festen Palette (je Werk stabil aus der Id); hell und dunkel über die bestehenden Variablen. Berührung über Pointer Events: Tippen (Knoten wählen), Ziehen (verschieben), Zwei-Finger-Zoom und Knöpfe + / − / Mitte; **`touch-action: none` nur auf dem Canvas**, damit die Seite sonst normal scrollt. Neuzeichnen nur bei Änderung (`requestAnimationFrame` nur während des Übergangs), Hochauflösung über `devicePixelRatio` begrenzt auf 2.
- Leiste unter dem Netz: gewählter Knoten (Typ, Titel, Werk), bei Ähnlichkeit Wert und **Beleg**, Knöpfe **Zur Mitte** (Fokus wechseln) und **Öffnen** (nur bei Kapitel); Filterknöpfe je Kantenart mit `aria-pressed`; Knopf **Liste** schaltet auf die Listenansicht (gleiche Daten, Knopf je Eintrag zum Springen).

- [ ] **Step 1: Failing tests (Node):** `trifft` bei kleinem Knoten und bei Zoom 0,5 (Trefferfläche bleibt ≥ 44 px), nächster Knoten gewinnt, Hintergrund → `null`; `beschriftungen` ohne Überlappung der Rechtecke für ein 40-Knoten-Beispiel und innerhalb der Fläche; Übergang liefert bei `t = 0` und `1` die Endwerte.
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: Canvas-Darstellung des Fokusnetzes mit Berührung`.

### Task 8: In die App einbauen, Daten laden

**Files:**
- Modify: `tools/speedreader_web/index.html`, `tools/speedreader_web/bundle.py` (`APP_DATEIEN` um `verbindungen.js`, `graphlayout.js`, `graphansicht.js`)
- Test: `tools/speedreader_web/test_verbindungen_ui.py` (Browser), `tools/speedreader_web/test_speedreader_web.py` (Bundle)

**Interfaces:**
- Vierter Knopf `data-ansicht="verbindungen"` („Verbindungen“, Taste 4); Fokus = aktuelles Kapitel (`b<id>:<nr>`); beim Kapitelwechsel folgt das Netz. **Öffnen** setzt Buch und Kapitel auf das Ziel und die Ansicht auf KI-Text; **Zur Mitte** ändert nur den Fokus des Netzes, nicht das offene Kapitel.
- Laden wie `daten.json`: `fetch("verbindungen.json")` mit IndexedDB-Zwischenspeicher (`verbindungen`), Import über Dateiauswahl (Dialog wie bei `daten.json`), `Verbindungen.pruefe` gegen `daten.json`. Fehlt die Datei: Hinweis „Noch keine Verbindungsdaten: am PC `export_verbindungen.py` ausführen“; weicht `erstellt` ab: „Verbindungsdaten gehören zu einem anderen Export“ (kein Netz); `qdrant: null` oder `fehlend > 0`: sichtbarer Hinweis „Ähnliche Stellen fehlen oder sind unvollständig“.
- Es wird nur der Ausschnitt um den Fokus gehalten; der Graph-Index (950 Kapitel) bleibt im Speicher (rund 2 MB JSON).

- [ ] **Step 1: Failing checks** (Playwright, Testwurzel mit Attrappen-Qdrant und kleinen Beispieldaten): Ansicht öffnen (`canvas` da, Fokus = offenes Kapitel); Tippen auf einen Nachbarn setzt ihn in die Mitte und zeigt die Leiste mit Beleg; **Öffnen** springt in das Kapitel (KI-Text); Hohles Werk hat keinen Öffnen-Knopf; Filter für Ähnlichkeit aus → keine ähnlichen Knoten; **Liste** zeigt dieselben Einträge und springt; fehlende Datei und abweichendes `erstellt` zeigen die Hinweise; Kapitelwechsel in einer anderen Ansicht verschiebt den Fokus mit; alle Bedienelemente ≥ 44 px bei 960×600 und 600×960; nach dem Neuladen bleibt der Zwischenspeicher nutzbar (Netz weg).
- [ ] **Step 2–4:** rot, implementieren, grün; `bundle`-Test erweitern.
- [ ] **Step 5: Sichtprüfung:** Bildschirmfotos bei 960×600 und 600×960 (dunkel und hell) neben das Referenzbild legen; Abweichungen (Beschriftung, Verblassen, Linienstärke) nachbessern.
- [ ] **Step 6: Commit** `feat: Ansicht „Verbindungen“ in der Lese-App`.

### Task 9: Dokumentation und Gesamtlauf

**Files:**
- Modify: `tools/speedreader_web/README.md` (Ansicht, Export, Daten, Grenzen, Handprüfliste), `dok/DATENSTRUKTUR.md` (`verbindungen.json`, Format), `CLAUDE.md` (eine Zeile), `dok/NÄCHSTE_SCHRITTE.md`
- Test: `tools/speedreader_web/test_gesamtlauf_verbindungen.py`

- [ ] **Step 1: Gesamtlauf-Test** (Testwurzel mit Attrappen-Qdrant, ohne Eingriff in echte Daten): `export_daten` → `export_verbindungen` (Exit 0) → App im Browser → Ansicht öffnen → Nachbar antippen → **Öffnen** → richtiges Kapitel; danach Export mit ausgefallenem Qdrant (Exit 3): App zeigt den Hinweis und Themen/Querverweise weiter; Leistung: synthetische Datei mit 950 Kapiteln lädt und zeichnet in der App unter 2 s (großzügige Grenze), Heap deutlich unter dem Limit.
- [ ] **Step 2: Gesamttest:** `cd tools && python -m pytest speedreader_web redaktion test_redaktion_anwenden.py test_redaktion_server.py pipeline episto_tui -q` → alles grün (Erwartung: 687 plus die neuen).
- [ ] **Step 3: Handprüfliste für Epistopheles (Touch)** in die README: Netz bei 10,1″ lesbar; Tippen trifft den gewünschten Knoten auch bei dichten Stellen; Zwei-Finger-Zoom und Ziehen ohne ungewolltes Scrollen der Seite; Beschriftung nicht unlesbar überlappend; Listenansicht; Zwischenspeicher im Flugmodus; Ladezeit nach dem Start.
- [ ] **Step 4: Durchlauf auf APIC mit echten Daten (von dir):** `export_daten.py`, `export_verbindungen.py` (Laufzeit und Ausgabe prüfen, Kalibrierung aus Task 3), Paket aufs Gerät; die Angaben dazu in die README.
- [ ] **Step 5: Commit** `docs: Querverbindungen`.

---

## Selbstprüfung

- **Abdeckung:** beide Verbindungsarten (Qdrant-Ähnlichkeit, Task 3 bis 4; Themen und Querverweise, Task 1 bis 2), Darstellung wie im Bild (Task 5 bis 8: Fokusnetz, Ringe, Verblassen, Tippen, Öffnen), Offline-Betrieb (nur `verbindungen.json`), Staleness und Ausfälle (Task 4, 5, 8), Liste als Gegenstück (Task 5, 7, 8), Dokumentation und Gesamtlauf (Task 9).
- **Bewusste Grenzen:** keine Live-Suche, kein Gesamtgraph, nur Kapitelgenauigkeit, Beleg nur als Vorschau. Die **Qualität der Ähnlichkeiten** (Mindestwert, Rangformel) lässt sich hier nicht beurteilen, nur auf APIC mit den echten Büchern (Task 3, Schritt 5); die Handprüfung auf dem Gerät steht wie bei der Redaktion aus.
- **Risiken:** Qdrant-Version (Query-API ab 1.10, sonst Rückfall auf `recommend`); die Laufzeit des Exports bei vielen Chunks (Batch-Abfragen, Fortschrittsanzeige, wiederholbar); Lesbarkeit des Netzes auf 10,1″ (deshalb Obergrenzen, Beschriftungsplatzierung und Liste).
- **Typkonsistenz:** Knoten-Ids `b001:3` (Kapitel), `b001#slug` (Thema), `b001` (Werk) in Export, `verbindungen.js`, `graphlayout.js`, `graphansicht.js` und App einheitlich; Kantenarten `aehnlich`, `thema`, `querverweis`, `werk`.
- **Proportion:** Der Plan beschreibt Schnittstellen, Tests und Prüfpunkte, aber keine Funktionskörper.
