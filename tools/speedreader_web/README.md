# EPISTO Lesen auf Epistopheles (Chromebook)

Stand 2026-11-02. Browser-App für das Lenovo IdeaPad Duet unter Chrome OS (4 GB RAM,
Touch). Entwickelt ausschließlich für ChromeOS; die TUI wird später separat angepasst.

Drei Ansichten desselben Kapitels, umschaltbar oben (Tasten `1` `2` `3`):

| Ansicht | Inhalt |
|---|---|
| **⚡ Speed** | die KI-Felder Wort für Wort an einer festen Stelle (Speedreader aus der TUI, `dok/2026-10-31-speedreader-design.md`) |
| **KI-Text** | dieselben KI-Felder als normaler Text: Zusammenfassung, Thesen, Gegenpositionen, Kernbegriffe, Definitionen, Belege |
| **Original** | der Volltext des Kapitels als Fließtext (Überschriften, Seitenmarken, Zitate, Fußnoten als Anmerkungen) |

Leitlogik: erst der Hinweis (Speed/KI-Text), dann der Originaltext. Das Original bleibt
bewusst ohne Tempo-Automatik.

Keine Installation, keine Abhängigkeiten, kein Internet nötig.

| Datei | Zweck |
|---|---|
| `index.html` | die App (Oberfläche, Ansichten, Kapitelwahl) |
| `speedreader.js` | Kern des Speedreaders: Wortfolge, Erkennungspunkt, Anzeigedauer (Portierung von `episto_tui/speedreader.py`) |
| `lesetext.js` | Markdown-Zerlegung für die Ansicht **Original** |
| `daten.json` | KI-Felder aller getaggten Kapitel, erzeugt am PC (ca. 4 MB, nicht im Repo) |
| `buecher\b001.json` … | Originaltexte, eine Datei je Buch (ca. 50 MB gesamt, größte Datei 2,2 MB, nicht im Repo) |

Es wird immer nur das Volltext-Buch des offenen Kapitels in den Arbeitsspeicher geladen.

## Einrichtung

1. **Daten erzeugen** (am PC, im Ordner `tools`):
   ```
   python speedreader_web/export_daten.py
   ```
   Nur lesend. Das Ergebnis ist das **Epistopheles-Paket**
   `D:\Workspace\!Episto\reader\export-epistopheles\`: `daten.json`, der Ordner `buecher\`
   **und die App-Dateien** (`index.html`, `korrektur.html`, `speedreader.js`, `lesetext.js`,
   `epub.js`, `redaktion.js`, `verdacht.js`, `chunkansicht.js`), die bei jedem Export frisch aus `tools\speedreader_web` danebenkopiert werden.
   Der Ordner ist regenerierbar und steht weder in Git noch in Syncthing.
   Aktueller Stand: 80 Bücher, 1176 Kapitel. Nach jedem neuen Buch
   (taggen, dann `ingest`) den Export wiederholen. `--ohne-volltext` erzeugt nur
   `daten.json` (dann fehlt die Ansicht **Original**), `--ohne-app` kopiert die App-Dateien
   nicht, `--out` wählt einen anderen Ort. Jeder Export vergibt neue
   Buch-Kennungen; `daten.json` und `buecher\` müssen daher vom selben Export stammen
   (die App prüft das über den Stand und meldet Abweichungen).
2. **Auf Epistopheles bringen**: den **ganzen Ordner** `reader\export-epistopheles` auf das Gerät
   kopieren (USB-Stick, Google Drive, oder per Syncthing-Android-App, falls dort eingerichtet).
3. **Öffnen**: in der Dateien-App `index.html` doppelt antippen (öffnet in Chrome).
   Beim ersten Mal **daten.json auswählen** und für die Ansicht **Original** einmal
   **Ordner „buecher“ importieren** (Ordnerauswahl; es werden alle `b….json` darin
   übernommen). Beides wird im Browser gespeichert, danach läuft die App ohne die Dateien
   und ohne WLAN. Zum Aktualisieren im Kapitel-Menü **Daten aktualisieren …** und
   **Volltext importieren …** wählen.

### Alternative: direkt von APIC im WLAN

Am PC (APIC), nach dem Export, im Ordner `reader\export-epistopheles` (dort liegen App und Daten):

```
python -m http.server 8080 --directory reader\export-epistopheles
```

Auf Epistopheles `http://<IP-von-APIC>:8080/` öffnen. Die App holt `daten.json` und
jeweils das Buch für die Ansicht **Original** frisch vom PC und behält Kopien für
offline; ein Import entfällt. Die Windows-Firewall muss Port 8080 im privaten Netz
zulassen; der Server nur starten, solange man ihn braucht (er liefert den ganzen Ordner
ohne Passwort aus).

## Bedienung

- **Umschalter** oben: Speed / KI-Text / Original / Verbindungen; die Wahl wird gemerkt. Beim Wechsel
  Speed → KI-Text scrollt der Text zum Abschnitt des aktuellen Worts; KI-Text → Speed
  startet am obersten sichtbaren Abschnitt.
- **KI-Text und Original:** normales Scrollen per Touch, Pfeiltasten, Leertaste, Bild ↑/↓.
  **A− / A+** (oder `−` / `+`) ändern die Schriftgröße (80–200 %). In **Original** merkt
  sich die App die Lesestelle je Kapitel und öffnet dort nach dem Neuladen wieder.
- **Speed:** Antippen der Wortfläche oder **Start** startet/pausiert; beim Öffnen steht
  der Lauf still. Tempo 100–900 Wörter/min (Standard 400), **−50 / −5 / +5 / +50**;
  **◀ Satz / Satz ▶**, **⏮ Abschn. / Abschn. ⏭**, Fortschrittsbalken zum Springen.
  Der Bildschirm bleibt beim Lesen an (Wake Lock); im Hintergrund-Tab pausiert die App.
- **☰ Kapitel**: Suche über Autor, Buch und Kapitel; **⏴ ⏵** blättert im Buch (in
  jeder Ansicht). **◐** wechselt Darstellung automatisch / hell / dunkel.
- Zuletzt gelesenes Kapitel, Ansicht, Tempo und Schriftgröße werden gemerkt (nur auf
  diesem Gerät).
- Tasten (Bluetooth-Tastatur): `1` `2` `3` `4` Ansicht, `n`/`p` nächstes/voriges Kapitel;
  in **Speed** zusätzlich Leertaste, ↑/↓ ±50, `+`/`−` ±5, ←/→ Satz, Bild ↑/↓ Abschnitt.

## Verbindungen: ähnliche Stellen, Themen, Querverweise

Vierte Ansicht (Taste `4`): das **Fokusnetz** um das offene Kapitel, nach dem Vorbild eines lokalen Obsidian-Graphen. Mitte = offenes
Kapitel (Halo, Beschriftung darunter), **Ring 1** = bis zu 14 stärkste Nachbarn (beschriftet, Linie zur Mitte), **Ring 2** = bis zu 14
weitere (klein, verblasst, ohne Linie). Die App spricht **nie** mit Qdrant; alles kommt aus der vorberechneten Datei `verbindungen.json`.

**Knoten:** Kapitel (Kreis, Farbe je Werk), Thema (Raute, ein Strang eines Werks), Werk (Ring; Werke außerhalb der Bibliothek sind hohl
und nicht öffenbar). **Kanten:** *ähnlich* (Qdrant, Kapitel zu Kapitel anderer Werke, Strichstärke nach Wert), *Thema*, *Querverweis*
(gestrichelt, mit Relation), *Werk* (Kapitel gehört zu Werk). Die vier Filterknöpfe schalten die Kantenarten ein und aus.

**Bedienung:** Tippen wählt einen Knoten; die Leiste unten zeigt Typ, Beleg (Ausschnitt des ähnlichen Chunks) und die Knöpfe
**Zur Mitte** (nur das Netz bewegt sich, das offene Kapitel bleibt), **Öffnen** (springt ins Kapitel, Ansicht KI-Text) und **Schließen**.
Ziehen verschiebt, Zwei-Finger-Zoom oder **+ / −** zoomt, **◎** setzt zurück. **Liste** zeigt dieselben Verbindungen gruppiert nach
Kantenart (die verlässliche Bedienung auf kleinem Display und für Bildschirmleser). Das Netz folgt jedem Kapitelwechsel.

**Daten erzeugen (am PC, nach `export_daten.py`):**

```
python speedreader_web/export_daten.py
python speedreader_web/export_verbindungen.py --root <Wurzel> [--qdrant http://127.0.0.1:6333]
```

`export_verbindungen.py` liest Qdrant **nur lesend** (Whitelist: Scroll, Query/Recommend, Collection-Info; alles andere wird vor dem
Senden abgelehnt) und schreibt `verbindungen.json` atomar neben `daten.json` (gleicher Stand `erstellt`, sonst lehnt die App sie ab).
Exit **0** = vollständig (oder ausdrücklich `--ohne-qdrant`), **3** = Qdrant fehlt oder ist ausgefallen (Datei enthält dann Themen und
Querverweise, die App zeigt „Ähnliche Stellen fehlen oder sind unvollständig“), **1** = Fehler (z. B. keine `daten.json`; die alte Datei
bleibt unberührt). Qdrant ab 1.10 (Query-API mit Punkt-Id), sonst Rückfall auf `recommend`.

**Laden in der App:** über http frisch vom Server, sonst die Kopie im Gerätespeicher (IndexedDB `verbindungen`); Import von Hand über
**☰ Kapitel → Verbindungen importieren …** oder den Knopf im Hinweis. Die App prüft gegen `daten.json`: anderer Export, andere Version
oder unbekannte Kapitel → Hinweis statt Netz (nie ein falsches Netz); nicht importiert wird, was die Prüfung nicht besteht.

**Kalibrierung (nur auf APIC möglich, dort liegen die echten Vektoren):** Mindestwert (Start 0,55 Cosinus), Zielkapitel je Kapitel
(8), Nachbarn je Chunk (10) und die Rangformel (Summe der drei besten Chunk-Paare) sind Startwerte ohne Bezug zu den echten Büchern.

```
python speedreader_web/verbindungen_stichprobe.py --anzahl 20 --mindestwerte 0.5,0.55,0.6,0.65,0.7
```

zeigt Perzentile, die Zahl übrig bleibender Zielkapitel je Mindestwert (Ziel: typisch 4 bis 8) und die besten Belege zum Gegenlesen;
danach `--mindestwert` / `--je-kapitel` beim Export setzen oder die Konstanten in `export_verbindungen.py` ändern.

**Grenzen:** keine freie semantische Suche und kein Gesamtgraph (nur das Netz um ein Kapitel), Genauigkeit nur auf Kapitelebene (der
Beleg ist eine Vorschau, kein Absatzsprung), keine Bearbeitung von Strängen oder Querverweisen in der App (bleiben Dateien), Ähnlichkeit
nur zwischen verschiedenen Werken. Entwicklung vorerst nur für ChromeOS (Termux-TUI und Syncthing bewusst außen vor). Rund 960 Kapitel
ergeben unter 2 MB JSON; Laden und Zeichnen bleiben dabei unter 2 s (Test mit synthetischen Daten).

### Handprüfung auf Epistopheles (Verbindungen, Touch)

Mehrfinger-Gesten und echtes Antippen sind in Playwright nur eingeschränkt prüfbar; von Hand prüfen:

- [ ] Netz auf 10,1″ lesbar (Beschriftungen, Verblassen, Linienstärke; Vergleich mit dem Referenzbild).
- [ ] Tippen trifft den gewünschten Knoten auch an dichten Stellen; Tippen am unteren Rand wählt aus und die Leiste hebt die Wahl nicht wieder auf.
- [ ] Zwei-Finger-Zoom und Ziehen ohne ungewolltes Scrollen oder Zoomen der Seite; Zoom um die Fingermitte.
- [ ] **Zur Mitte**, **Öffnen**, **Schließen**; hohles Werk: kein Öffnen, kein Zur Mitte.
- [ ] Filterknöpfe; Listenansicht und Rückkehr zum Netz (Größe stimmt wieder).
- [ ] Kapitelwechsel mit ⏴ ⏵: das Netz folgt.
- [ ] Zwischenspeicher im Flugmodus (Netz nach Neuladen noch da); Ladezeit nach dem Start.
- [ ] Hinweise bei fehlender Datei, anderem Export und fehlendem Qdrant.
- [ ] Hell und Dunkel (◐): Netz wird neu gefärbt.

## Korrekturlesen: geteilte Ansicht (`korrektur.html`)

Links das **Original-Ebook** (PDF oder EPUB), rechts die **extrahierte Fassung**, zum
Aufspüren von Extraktions- und Bereinigungsfehlern. Aufruf über **Korrekturlesen ↗** im
Kapitel-Menü der Leseansicht oder direkt `korrektur.html`; **Lesen ↗** führt zurück.

**Rechts** (umschaltbar, Tasten `1` `2` `3`, `n`/`p` blättern):
- **Rohchunks:** die `chunk_NNN.md` aus dem Lektor-Ordner, der unveränderte Extrakt aus der
  Quelldatei: bei fremdsprachigen Quellen `en\chunk_*`, bei deutschen (z. B. Aigner)
  `de\chunk_*`. Die Sprache steht in der Titelzeile, z. B. „128 Rohchunks (en)“. Hat der Lektor
  keine Chunks, werden die englischen Referenzchunks aus `rohdaten\en-chunks` genommen („aus
  en-chunks“, z. B. Bourdieu, *The State Nobility*). Bei Büchern ohne Chunks (z. B. Michels)
  ist der Knopf gesperrt. Jeder Chunk trägt im Wähler und in der Infozeile sein **Kapitel**
  (aus `kapitel.json` des Lektors, mit der Kapitelnummer des Buchs); **→ Kapitel** springt zum
  bereinigten Kapitel dieses Chunks, im Modus „Bereinigt“ springt **→ Chunk** zum ersten Chunk
  des Kapitels. Der Sprung gibt es nur, wenn es gleich viele Kapitelgrenzen wie bereinigte
  Kapitel gibt (aktuell 77 von 81 Büchern); die Kapitelnummer des Buchs kann von der
  Dateinummer der bereinigten Kapitel abweichen (z. B. zählt dort das Vorwort als Kapitel 1).
- **Bereinigt:** `quelle\*.md` aus der Bibliothek, der fertige Kapiteltext, kapitelweise.
  Bei Büchern, die noch nicht in der Bibliothek sind (neu im Lektor), gesperrt.
- **Übersetzung** („Übersetzung prüfen“): Rohchunk der Quelle oben, der übersetzte Chunk
  (`de\chunk_*`) darunter, beide mit demselben Chunk-Wähler und ⏴ ⏵. Nur bei fremdsprachigen
  Quellen mit übersetzten Chunks (aktuell 40 Bücher); bei deutschen Quellen und noch nicht
  übersetzten Büchern ist der Knopf gesperrt. Bei **gleicher Chunkzahl** (34
  Bücher) gehören gleiche Nummern zusammen, und die Kopfzeile zeigt das Längenverhältnis
  de/Quelle (Bestand: Median 1,12); unter 0,8 oder über 1,5 steht **⚠ Länge auffällig**, ein
  Hinweis auf abgeschnittene oder verdoppelte Übersetzung. Bei **abweichender Chunkzahl**
  (6 Bücher, z. B. Kersey 53 ↔ 106, Popper 175 ↔ 77) wird die Zuordnung **proportional geschätzt** und so
  gekennzeichnet; mit ⏴ ⏵ an der Übersetzung lässt sie sich von Hand verschieben (↺ setzt
  zurück, die Verschiebung wird je Buch gemerkt). Die Länge wird dann nicht bewertet.
- **¶** macht Tabs, geschützte Leerzeichen und weiche Trennstriche sichtbar (rot);
  **A− / A+** Schriftgröße. Der Text steht unverändert (Monospace), damit Artefakte
  auffallen.

**Links:**
- **PDF:** der eingebaute Chrome-Betrachter, **Seite … Los** springt zur Seite.
- **EPUB:** eigener Leser (ZIP direkt im Browser, Bilder und Formatierung bleiben
  erhalten), Abschnittswahl und ⏴ ⏵. Keine Skripte, keine Netzzugriffe.
- **Auswahl suchen:** Text rechts markieren, dann diesen Knopf. Beim EPUB springt die
  Ansicht zur Fundstelle und markiert sie (erneut klicken: nächste Fundstelle); beim PDF
  landet der Suchtext in der Zwischenablage (Strg+F, Strg+V im Betrachter).
- Das Ebook kommt **automatisch** aus dem Export (siehe unten) und wird je Buch im Browser
  gespeichert. **Ebook öffnen …** wählt stattdessen eine Datei von Hand (z. B. für Bücher
  ohne Quelle im Export); sie hat bis zum nächsten Import Vorrang.
- Der **Teiler** in der Mitte lässt sich ziehen (oder mit den Pfeiltasten verschieben);
  im Hochformat stehen die Seiten untereinander.

**Daten** (am PC, im Ordner `tools`):

```
python speedreader_web/export_korrektur.py
```

Quellen des Exports:
- **Lektor-Ordner** `<Bibliothek>\rohdaten\Lektor`, also `D:\Workspace\!Episto\rohdaten\Lektor`
  (änderbar mit `--lektor PFAD` oder `EPISTO_LEKTOR`): `<Autor>\<Titel>\en|de\` mit der Quelldatei (PDF/EPUB)
  und den Chunks, dazu `kapitel.json` (Kapitelgrenzen in Chunks).
- **en-chunks** `<Bibliothek>\rohdaten\en-chunks\<Autor>\<Titel>\`: Rückfall für Rohchunks, wenn der Lektor
  keine hat (gleiche Ordnernamen wie in `reader`).
- **Bibliothek** (`--root`): `reader\<Autor>\<Titel>\quelle\*.md` als bereinigter Text.
- Ein Bibliotheksbuch wird seinem Lektor-Ordner über den Namen zugeordnet, sonst über den
  Quellpfad in seiner `meta.json`, sonst über einen eindeutig ähnlichen Titel (so werden
  z. B. „O'Neil“ und „Piano“ trotz abweichender Ordnernamen erkannt). Liegt die Quelldatei
  laut `meta.json` woanders (z. B. `rohdaten\Inbox`), wird sie von dort genommen; alte Pfade
  (`…\eBooks\Inbox\…`) werden dabei unter `rohdaten` neu aufgesetzt.
- Bücher nur im Lektor (noch nicht in der Bibliothek) erscheinen ebenfalls, ohne bereinigten Text.

Schreibt den Ordner `reader\export-epistopheles\korrektur` (und kopiert die App-Dateien daneben,
siehe Einrichtung): `index.json`, je Buch `k001.json` … (Chunks, übersetzte Chunks, Kapitelgrenzen
und bereinigte Kapitel) und die Quelldatei als `k001.pdf` / `k001.epub` … Aktueller Stand: 84 Bücher,
82 mit Rohchunks, 81 mit Ebook, **ca. 410 MB**. `--ohne-ebooks` lässt die Quelldateien weg (ca. 150 MB).
Damit enthält das Paket alles aus `rohdaten`, was das Korrekturlesen braucht (Lektor-Chunks,
Quelldateien, Kapitelgrenzen, en-chunks); `Inbox`, `Outbox` und `Transfer` gehören nicht dazu. Auf
Epistopheles kopierst du also nur den **einen** Ordner `reader\export-epistopheles`, nicht `reader`
und `rohdaten` einzeln.
Anders als `export_daten.py` enthält er **alle** Bücher, auch noch nicht getaggte. Der
Export liest nur und verändert weder Lektor noch Bibliothek.

Auf Epistopheles den Ordner `korrektur` einmal importieren (Ordnerauswahl; Bücher und
Ebooks landen im Browserspeicher) oder die App über `http` von APIC öffnen (siehe oben):
dann holt sie Buchdaten und Ebook beim ersten Öffnen eines Buchs vom PC und behält Kopien,
ein Import entfällt. Plant dafür ca. 450 MB Platz auf dem Gerät ein. Gemerkt werden je Buch
Chunk/Kapitel, Seite bzw. Abschnitt und die Lage des Teilers.

## Redaktion: Korrekturen sammeln, senden, am PC einarbeiten

Stand 2026-11-02 (P0 bis P2; Spec `dok/2026-11-02-redaktion-epistopheles-design.md`, Pläne
`dok/2026-11-02-redaktion-p0-p1-implementation-plan.md` und `…-p2-implementation-plan.md`). In der
Ansicht **Rohchunks** von `korrektur.html` lassen sich Fehler im Original-Chunk markieren und
korrigieren, in der Ansicht **Bereinigt** der fertige Volltext (Absätze, Fußnoten). **Die App ändert nie Quelldaten.** Jede Änderung ist ein Eintrag im Protokoll des Geräts;
erst am PC werden Einträge mit `redaktion_anwenden.py --ausfuehren` in den Chunk geschrieben.

### Bedienung am Gerät

- **Verdachtsstellen** (Chunk-Ansicht): Gelb/Rot/Blau markieren mutmaßliche Artefakte (gebrochene
  Zeilen, Fußnoten, Seitenzahlen, Kopfzeilen). Je Stelle: Vorschlag **annehmen**, nur **markieren** oder
  ablehnen. Der Zähler (`#rechts-verdacht`) zeigt die offenen Stellen, bei Konflikten in Warnfarbe.
- **Werkzeugleiste** (erscheint bei einer Textauswahl): *Zeilen verbinden*, *Ausschneiden / verschieben*,
  *Löschen*, *Absatz hier trennen*, *Kapitel beginnt hier*, *Inhaltsverzeichnis*, *Glossar*, *Nur markieren*;
  optional mit Notiz. **Die Operationen wirken auf ganze Zeilen** der Auswahl; **Mehrabsatz-Marken sind nur im
  ersten Absatz sichtbar markiert** (der Eintrag selbst gilt für die ganze Spanne).
- **Änderungen anzeigen**: Liste der Einträge des offenen Buchs mit Status und **Rücknahme** je Eintrag (die
  Rücknahme ist ein eigener Eintrag). **Änderungen als Datei sichern** exportiert das Protokoll des Buchs
  (`{geraet, buch, eintraege}`); am PC mit `--eingang` einlesbar, auch ohne Netz.
- **Neu übersetzen** (Ansicht *Übersetzung*): schickt einen einzelnen Chunk als Auftrag an APIC; das Ergebnis
  erscheint als Vorschlag im **Vergleich** (alt/neu). **Übernehmen** erzeugt nur den Eintrag
  `uebersetzung-uebernehmen`; geschrieben wird er am PC. **Ein Vorschlag wird nie automatisch übernommen.**

### Fertiger Volltext korrigieren (Modus „Bereinigt“, P2)

Gilt für `reader\<Autor>\<Werk>\quelle\*.md`. Auch hier ändert die App nie Dateien: jede Änderung ist ein Eintrag der
Ebene `volltext` mit `ziel.datei`. **Voraussetzung:** ein Datenpaket mit Dateinamen je Kapitel und `enthalten`
(`export_korrektur.py` neu laufen lassen); bei einem alten Paket zeigt die App den Text unverändert und meldet
„Bearbeiten gesperrt: Daten neu exportieren“.

- **Anzeige:** das Kapitel mit den noch offenen Einträgen abgespielt, Fußnotenhinweise als Chips (Verweis ohne Text,
  Text ohne Verweis, doppelter Text, andere Nummerierung), Konflikte am Absatz, `●` im Kapitelwähler bei Kapiteln mit
  Hinweisen. Kopfzeile: „Fußnoten: n Hinweise · k Konflikte“.
- **Absatz bearbeiten:** Absatz antippen → Leiste → **Bearbeiten** → Textfeld → **Speichern** (Eintrag `ersetzen`).
  Unverändert, leer oder mit Leerzeile wird abgewiesen. Ändert sich die Menge der Fußnotenverweise oder -texte, zeigt
  der Dialog die Differenz („Verweis [^2]: 1 → 0“) und verlangt **Trotzdem speichern**. Jeder Eintrag läuft vor dem
  Speichern durch dieselbe Anwendung wie später am PC (Vorprobe).
- **Absatz hier trennen** (Leiste): teilt den angetippten Absatz an dieser Stelle (Art `trennen` mit Kontexttext, nötig
  bei einzeiligen Absätzen). Zu wenig oder mehrdeutiger Kontext wird gemeldet, es entsteht dann kein Eintrag.
- **Werkzeugleiste** bei Textauswahl: *Zeilen verbinden*, *Ausschneiden / verschieben*, *Löschen*, *Absatz hier trennen*
  (Zeilenform), *Nur markieren*. *Kapitel beginnt hier*, *Inhaltsverzeichnis*, *Glossar* gibt es im Volltext nicht (P3).
- **Fußnoten zuordnen:** Verweise `[^id]` und die Köpfe der Fußnotentexte `[^id]:` sind antippbar (Waisen fett, rot
  unterstrichen). Im Dialog das Gegenstück wählen, dann **Fußnotentext umbenennen** oder **Verweis umbenennen**;
  gesperrt, wenn die Zielkennung schon einen Text hat. Dazu **Verweis entfernen** und **Verweis setzen** (Leiste,
  an der angetippten Stelle). Unterstützt ist nur die Schreibweise `[^id]`.
- **Ursache suchen** (Leiste): sucht den Absatz in den übersetzten Chunks (bei deutscher Quelle in den Rohchunks),
  wechselt bei eindeutigem Treffer dorthin und hebt die Stelle hervor. Bei mehreren Treffern oder Teilübereinstimmung
  (Absatz über eine Chunkgrenze) wählt die Person; es wird nie geraten. Die Suche ändert keine Daten. Bei abweichender
  Chunkzahl setzt sie die Verschiebung der Zuordnung (↺ stellt zurück).
- **Stand angewendeter Änderungen:** Der Export nennt je Buch `enthalten` (Ids angewendeter Volltext-Einträge, die im
  Text schon stecken). Einträge, die am PC angewendet, aber noch nicht im Export sind, spielt die App weiter ab, damit
  neue Korrekturen den passenden Vorzustand haben; ein Eintrag aus `enthalten` wird nie erneut abgespielt.

### Verbindung zu APIC (Empfänger)

Der Empfänger `tools\redaktion_server.py` läuft nur, wenn man ihn **von Hand startet** (kein Dienst, kein Autostart):

```
python tools\redaktion_server.py [--root R] [--port 8080] [--host 0.0.0.0] [--paket P]
```

- Er liefert das Epistopheles-Paket (statisch) **und** die API aus einem Ursprung aus; die App also über
  `http://<IP-von-APIC>:8080/korrektur.html` öffnen. Beim Start wird das Token ausgegeben.
- **Token:** `hilfsdaten\redaktion\token.txt` (beim ersten Start mit 16 Hex-Zeichen angelegt). Die Datei liegt
  **nie im ausgelieferten Paket**; der Start wird verweigert, wenn sie dort läge oder das Token leer ist. Anfragen
  tragen es im Header `X-Redaktion-Token`.
- **Schutz:** zuerst IP-Prüfung (nur private Netze und Loopback, sonst 403), dann Token (sonst 401); bei 401/403
  wird nichts gelesen, geschrieben oder verraten. Request-Bodies werden nie protokolliert.
- **Endpunkte:** `GET /api/ping`, `POST /api/aenderungen`, `GET /api/stand?buch=<Autor/Titel>`,
  `POST /api/auftraege`, `GET /api/auftraege/<id>`, `GET /api/vorschlag?buch=&chunk=`.
- **In der App:** Knopf **⇄ APIC**: Adresse (`http://192.168.x.y:8080`), Token und Gerätename eintragen, **Verbindung
  testen**. **Die App speichert das Token im Klartext in `localStorage`** (LAN-Werkzeug, kein Schutz gegen Zugriff
  auf das Gerät).
- **Senden:** automatisch, Wiederholung alle 30 s, bis APIC bestätigt (gleiche `id` wird nie doppelt gespeichert).
  **Gesendet wird nur das geöffnete Buch**; Einträge anderer Bücher warten, bis das Buch geöffnet wird.
  Ohne Netz funktioniert alles andere weiter.
- Eingänge liegen unter `hilfsdaten\redaktion\eingang\<Buchschlüssel>\`; der Buchschlüssel wird geprüft und bei Unsicherheit
  abgelehnt (`..`, absolute Pfade, verbotene Zeichen), nie "repariert". Jede Sendung ergibt eine Datei.

### Neu übersetzen: Voraussetzungen und Grenzen

- **Gesperrt**, wenn die Chunkzahlen von Original und Übersetzung verschieden sind oder die Zuordnung von Hand
  verschoben wurde (↺ setzt zurück): dann ist nicht sicher, welcher Chunk gemeint ist.
- Der Auftrag startet **erst, wenn alle Nicht-Marken-Einträge dieses Chunks bei APIC angekommen sind** (sonst würde mit
  altem Text übersetzt); Einträge anderer Chunks stören nicht. Aufträge laufen einzeln nacheinander.
- Die **Warteschlange liegt nur im Speicher** des Empfängers: nach einem Neustart antwortet die Auftrags-ID mit
  404; den Wunsch dann in der App neu anstoßen.
- **Verwerfen** im Vergleich löscht die Vorschlagsdatei `de\chunk_NNN.md.neu` bei APIC **nicht**.
- **Übernehmen** legt nur den Eintrag `uebersetzung-uebernehmen` an; am PC kopiert `redaktion_anwenden.py
  --ausfuehren` `chunk_NNN.md.neu` nach `chunk_NNN.md` (Backup, `.neu` danach gelöscht). Konflikt, wenn `.neu`
  fehlt oder Übersetzung beziehungsweise Vorschlag nicht mehr dem im Vergleich gesehenen Stand entsprechen.

### Einarbeiten am PC: `redaktion_anwenden.py`

```
python tools\redaktion_anwenden.py [--root R] [--buch "Autor/Titel"] [--eingang DATEI]               # Dry-Run
python tools\redaktion_anwenden.py [--root R] [--buch "Autor/Titel"] [--eingang DATEI] --ausfuehren
```

Immer zuerst den Dry-Run lesen. Mit `--ausfuehren` wird je Chunk zuerst ein Backup angelegt, dann atomar
geschrieben, der Stand im Eingang gesetzt und `redaktion.json` im Lektor-Buchordner fortgeschrieben.

**Ebene `volltext`:** Einträge ändern `reader\<Buch>\quelle\<datei>` (nur reine Dateinamen `*.md`, nie `_*`, nie
Pfade). Backup nach `reader\<Buch>\notizen\_backup`, Protokoll in `reader\<Buch>\notizen\redaktion.json`
(`eintraege`; `dateien` mit `hash_original` vor der ersten Änderung und `hash_aktuell`; Grundlage für „KI-Inhalt
veraltet“ in P4). Der Bericht nennt je Datei die Fußnotenbilanz vorher/nachher („Marker 2→1, Definitionen 2→2“) und
neu entstandene Fußnotenhinweise; sie ändern den Exit-Code nicht. Eine Korrektur wird nicht zurückgenommen, sondern
durch einen neuen Eintrag korrigiert.

**Exit-Codes:**

| Code | Bedeutung |
|---|---|
| 0 | in Ordnung (auch wenn Rücknahmen als „nicht möglich“ in der Summenzeile stehen) |
| 1 | ungültige Eingabe (Buchschlüssel, `--eingang`-Datei) |
| 2 | mindestens ein Konflikt (Absatz stimmt nicht mehr mit der Prüfsumme überein; es wurde nichts still geschrieben) |
| 3 | nur Warnungen (Zeilen mit `WARNUNG:`, z. B. Chunk geschrieben, aber Stand oder `redaktion.json` nicht fortgeschrieben) |

Konflikt (2) hat Vorrang vor Warnungen (3). **Rücknahmen**, die nicht mehr möglich sind (Ziel schon angewendet),
erscheinen als „N Rücknahmen nicht möglich“ in der Summenzeile und zählen nicht als Konflikt (Exit 0).

**Backups** liegen für Chunks unter `<lektor>\notizen\_backup` (im Lektor-Buchordner), für den Volltext unter
`reader\<Buch>\notizen\_backup`.

**`lektor-zu-episto.py --ueberschreiben` und Volltext-Korrekturen:** Ohne `--ueberschreiben` bricht das Skript ab, sobald
`quelle\*.md` existiert. Mit `--ueberschreiben` wird **zuerst gesichert, wenn `reader\<Buch>\notizen\redaktion.json`
Volltext-Einträge enthält** (Kopie der Kapitel nach `notizen\_backup\quelle-<Zeit>\`; ohne solche Einträge gibt es,
wie bisher, kein Backup), dann neu aufgebaut und das Protokoll **wieder eingespielt**. Jeder Eintrag, der danach nicht
mehr greift (anderer Dateiname, geänderter Ausgangstext), steht einzeln mit Datei, Id und Grund in der Ausgabe und in
`reader\<Buch>\notizen\redaktion-nachspiel.json` (zusätzlich `basis_geaendert`: Dateien, deren Ausgangstext nicht mehr
der ist, auf dem die Korrektur entstand); `redaktion_anwenden.py` nennt den offenen Bericht im Dry-Run. Das Protokoll
bleibt vollständig. **Solche Einträge sind in der App sichtbar:** der Export nimmt sie aus `enthalten` und nennt sie unter
`nachspiel` (Id → Grund); die App spielt sie nie ab (App und PC sehen denselben Text), sondern zeigt sie am Absatz als
Konflikt mit **Neu anwenden** (neuer Eintrag auf dem aktuellen Text) oder **Verwerfen**. Beides sendet eine Rücknahme; sie
setzt den Eintrag im Protokoll auf `zurueckgenommen` (das Nachspiel ignoriert ihn danach) und entfernt ihn aus dem Bericht.
Die `redaktion.json` im **Lektor**-Buchordner (Korrekturen an Rohchunks) wird dabei **nicht**
verwendet. Handänderungen in `quelle\*.md`, die nicht über das Protokoll liefen, gehen beim Neuaufbau verloren (nur das
Backup bleibt): vorher selbst sichern; `--dry-run` zeigt, was geschehen würde.

**Schutz der Übersetzung:** `tools\pipeline\ebook-translate.py` bricht ohne `--resume` ab, wenn im
Lektor-Buchordner eine `redaktion.json` existiert (eine Neuübersetzung würde alle Korrekturen überschreiben);
`--korrekturen-verwerfen` verwirft sie ausdrücklich. Der Guard blockiert derzeit **auch `--dry-run` ohne
`--resume`**; für einen Probelauf `--dry-run --resume` verwenden.

**Nach dem Einarbeiten am PC den Export wiederholen** (`export_korrektur.py`, `export_daten.py`): bis dahin erscheinen
angewendete Chunk-Korrekturen nicht in der Ansicht, und Verdachtshinweise tauchen wieder auf. Für den Volltext gleicht
die App das über `enthalten` aus (siehe oben).

**Reihenfolge der Einträge:** `erstellt` hat Millisekunden und steigt je Gerät streng; der Eingang sortiert danach
(ältere Einträge ohne Millisekunden zählen als `.000`). Einträge am selben Absatz werden in dieser Reihenfolge
angewendet, das `vorher` des nächsten ist das `nachher` des vorigen.

### Bekannte Grenzen

- **Abweichender Lektor-Schlüssel (O'Neil, Piano) und englische Rohchunks bei deutscher Quelle (Popper):** behoben mit P2.
  Der Export nennt je Buch `reader`, `lektor` und `chunkSprache`; die App schreibt `ziel.lektor` und `ziel.sprache` in
  Chunk-Einträge, `redaktion_anwenden.py` und **Neu übersetzen** folgen dem (Schlüssel wie ein Buchschlüssel geprüft,
  Sprache nur `en`/`de`; ein Lauf bearbeitet je Buch genau einen Lektor-Ordner, abweichende Einträge bleiben als
  „uneinheitliches Ziel“ liegen). Bei Popper bleibt **Neu übersetzen** gesperrt (Quelle deutsch). Einträge aus der Zeit
  vor P2 tragen die Felder nicht und enden bei diesen drei Büchern weiter als Konflikt; neu korrigieren.
- **Volltext:** nur die Fußnotenschreibweise `[^id]` (andere Konventionen werden gemeldet, nicht bearbeitet); kein
  Renummerieren ganzer Fußnotenfolgen; Absätze lassen sich nicht zwischen Kapiteln verschieben, Kapitel nicht teilen oder
  zusammenführen (P3). Handarbeit in `quelle\*.md` außerhalb des Protokolls wird beim Neuaufbau nicht wieder eingespielt.
- **„Ursache suchen“** ist ein textuelles Verfahren (Wortfenster). Stark umgeschriebene Absätze, sehr kurze Absätze
  (unter 4 Wörtern) und Absätze über Chunkgrenzen liefern „mehrdeutig“ oder „keine“.
- **Verschiebe-Leiste:** liegt unten im Textfenster und kann bei kurzen Kapiteln das Ziel verdecken; scrollen hilft.
- **Kersey und Parvini** haben zusätzlich `de\chunk_NNN.tagged.md`: die de-Liste ist doppelt, **Neu übersetzen** ist gesperrt.
- **Standard-Wurzel:** `redaktion_server.py` nimmt `EPISTO_ROOT` oder `D:\Workspace\!Episto`, `redaktion_anwenden.py`
  den Elternordner von `tools`. In einem Worktree können beide auseinanderlaufen: `--root` immer ausdrücklich angeben.
- `ebook-translate.py --resume --ohne-referenz` bei einem englischen Buch löscht `de\` ohne Backup (Altbestand).

### Handprüfung auf Epistopheles (Touch)

Echtes Long-Press-Auswählen mit Auswahl-Griffen ist in Playwright **nicht testbar**; vor der Freigabe auf dem
Gerät von Hand prüfen:

- [ ] Wort per Long-Press auswählen, Griffe ziehen, über mehrere Zeilen erweitern: Werkzeugleiste erscheint und verdeckt die Auswahl nicht.
- [ ] Jede Operation per Fingertipp (Verbinden, Ausschneiden/verschieben, Löschen, Trennen, Kapitel, Verzeichnis, Glossar, Markieren) und Abbrechen.
- [ ] Verdachtsstelle annehmen / markieren / ablehnen per Fingertipp; Zähler stimmt.
- [ ] Bedienelemente mindestens 44 px in 960×600 und 600×960 (bekannte Ausnahme: `#de-zurueck` / `#de-vor` sind 36 px, Altbestand).
- [ ] Änderungen anzeigen, Rücknahme, Änderungen als Datei sichern.
- [ ] Flugmodus: Korrigieren funktioniert; nach Rückkehr des Netzes kommen die Einträge bei APIC an.
- [ ] Neu übersetzen, Vergleich, Übernehmen / Verwerfen im WLAN.
- [ ] Volltext: Absatz antippen (Fingerkuppe trifft den gewünschten Absatz, Leiste verdeckt ihn nicht), Bearbeiten mit der Bildschirmtastatur (Speichern/Abbrechen bleiben oben sichtbar, Tabs und Umlaute stimmen).
- [ ] Volltext: **Absatz hier trennen** und **Verweis setzen** an einer per Finger angetippten Stelle: die Stelle ist die gemeinte (Zeiger steht hinter dem getippten Zeichen).
- [ ] Fußnoten: Verweise und Fußnotentexte lassen sich einzeln antippen (auch dicht beieinander, Trefferfläche ≥ 44 px), Zuordnen / Umbenennen / Entfernen, Rücknahme über „Änderungen anzeigen“.
- [ ] Ursache suchen: Sprung in die Übersetzung, Hervorhebung sichtbar, Auswahl bei mehreren Treffern; ↺ stellt die Zuordnung zurück.
- [ ] Auswahl im Volltext (Long-Press, Griffe): Werkzeugleiste ohne Kapitel/Verzeichnis/Glossar, Verbinden/Löschen/Verschieben/Markieren.

## Tests

```
python -m pytest speedreader_web redaktion
python -m pytest test_redaktion_anwenden.py test_redaktion_server.py pipeline
```

Zusätzlich im Ordner `tools`: `python -m pytest test_lektor_zu_episto_schutz.py` (Schutz und Nachspiel in der Pipeline).

Redaktion: `redaktion\` (Operationen und Vektoren, Fußnotenanalyse, Protokoll, Schutz, Aufträge, Testwurzel),
`test_redaktion_js.py`, `test_fussnoten_js.py`, `test_ursache.py`, `test_verdacht.py`, `test_chunkansicht.py` (Node) sowie die
Browsertests `test_werkzeugleiste.py`, `test_aenderungsliste.py`, `test_neu_uebersetzen.py`, `test_lektor_schluessel.py`,
`test_volltext.py`, `test_fussnoten_ui.py`, `test_ursache_ui.py`, `test_graphansicht_ui.py`, `test_verbindungen_ui.py` und der **Gesamtlauf** `test_gesamtlauf_p2.py` (Urtext →
Export → App → Empfänger → Einarbeiten → neuer Export → Neuaufbau mit Nachspiel; ohne Playwright übersprungen).
Verbindungen: `test_export_verbindungen.py`, `test_qdrant_nachbarn.py` (Qdrant-Attrappe), `test_verbindungen_js.py`, `test_graphlayout.py`,
`test_graphansicht.py` (Node) und der **Gesamtlauf** `test_gesamtlauf_verbindungen.py` (Export → App → Öffnen, Qdrant-Ausfall, 950 Kapitel).
Browsertests brauchen Playwright mit passendem Chromium (die pip-Version muss zur installierten Browserversion passen,
sonst werden sie übersprungen). `python -m redaktion.testwurzel <Ordner>` (im Ordner `tools`) baut eine kleine Test-Bibliothek samt Paket.

- `test_speedreader_web.py`: Paritätstest — `speedreader.js` (Node) und `speedreader.py`
  rechnen dieselben Fälle (Wörter, Flags, Faktoren, Erkennungspunkt, Sprungziele,
  Restdauer); Export mit und ohne Volltext. Ändert man Zeiten oder Tokenisierung,
  **beide Dateien** anpassen.
- `test_lesetext.py`: Markdown-Zerlegung (Überschriften, Absätze, Listen, Zitate,
  Seitenmarken, Fußnoten, Roh-HTML, maskierte Zeichen).
- `test_export_korrektur.py`: Export der Korrekturdaten (Quelldatei und Rohchunks aus dem
  Lektor, übersetzte Chunks, en/de-Zuordnung, Zuordnung Bibliothek ↔ Lektor über Name/meta.json/Titel,
  Quelldatei außerhalb des Lektors, Kapitelgrenzen, Rückfall auf en-chunks, Reste früherer Exporte,
  `--ohne-ebooks`, Standardpaket mit App-Dateien).
- `bundle.py`: Hilfsmodul für das Paket `reader\export-epistopheles` (Standardpfad, App-Dateien kopieren).
- `test_epub.py`: ZIP-Schicht von `epub.js` (gespeicherte und komprimierte Einträge,
  UTF-8-Namen, angehängte Bytes, Pfadauflösung, CSS-Bereinigung).

Ohne Node werden die JS-Tests übersprungen. Die Oberfläche selbst ist per Browser
(Playwright, Chromium) geprüft, nicht automatisiert.

## Nicht geprüft / Grenzen

- Nicht auf Epistopheles selbst getestet, nur im Desktop-Browser (Viewports 960×600,
  600×960, 360×640). Offen: Antippen von `index.html` aus der Dateien-App, die
  Ordnerauswahl für den Volltext und die Speicherung der Daten unter `file://` auf
  Chrome OS; ebenso Speicher- und Zeitbedarf des Imports (80 Dateien, 50 MB) auf dem Gerät.
- Der Originaltext wird als Markdown vereinfacht dargestellt (keine Tabellen, Bilder
  nur als Beschriftung). Rauschen aus der EPUB-Aufbereitung erscheint, wie es in
  `quelle\*.md` steht.
- Keine Verbindung zwischen Speed-Wort und Absatz im Original (nur Abschnittssprung
  zwischen Speed und KI-Text).
- Kein Wechsel des Kapitels über Buchgrenzen hinweg außer über die Kapitelwahl.
- Korrekturansicht: Rohchunks und Original sind nicht automatisch Stelle für Stelle
  gekoppelt (die Chunks tragen keine Seitenzahlen); die Verbindung stellt **Auswahl
  suchen** her. Beim PDF lässt sich nicht programmatisch suchen. Das PDF-Rendering ist
  nur über Chromiums Betrachter geprüft (Seitensprung per `#page=`), nicht visuell. Es
  werden keine Korrekturen gespeichert oder markiert (anders als die TUI-Marken);
  die Ansicht dient dem Auffinden.
- EPUB-Leser: Schriftdateien und externe Verweise fallen weg, sonst bleibt das Aussehen
  der Datei erhalten. Getestet mit allen 9 EPUBs aus `Inbox\` im Desktop-Browser (öffnen,
  mittleren Abschnitt anzeigen, Bilder laden); die PDFs dort nicht einzeln.
- Kapitel wie „Cover“ oder „Halftitle“ erscheinen ebenfalls (so liegen sie in `tags.json`).
