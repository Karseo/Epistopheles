# Redaktion auf Epistopheles, P2 (Fertiger Volltext): Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Entwurf, wartet auf Freigabe (Abschnitt „Entscheidungen zur Freigabe“). Umsetzung erst danach.

**Goal:** Auf Epistopheles den fertigen Volltext (`reader\<Autor>\<Werk>\quelle\*.md`) direkt korrigieren (Absatz bearbeiten, Zeilen verbinden / trennen / löschen / verschieben, markieren), Fußnoten zuordnen (Hochzahl im Text ↔ Fußnotentext am Kapitelende) und von einer Textstelle zur Ursache im Chunk springen. Die Einträge fließen wie in P1 zu APIC und werden dort mit `redaktion_anwenden.py` kontrolliert in `quelle\*.md` eingearbeitet; `lektor-zu-episto.py` spielt sie nach einem Neuaufbau wieder ein, statt sie still zu vernichten.

**Architecture:** Wie P0/P1: Korrekturen sind Protokolleinträge mit Ebene `volltext`, Ziel am Text verankert (`datei`, `absatz_index`, `anfang`) und `vorher`-Prüfsumme. Anwendung doppelt (`ops.py` / `redaktion.js`) mit gemeinsamen Testvektoren. Neu in P2: Art `fussnote` (kapitelweit prüfend), Fußnotenanalyse (Python und JS paritätsgeprüft), Volltext-Zweig in `redaktion_anwenden.py` mit eigenem Protokoll `reader\…\notizen\redaktion.json`, ein verallgemeinerter Anzeige-/Werkzeugbaustein in `chunkansicht.js` (Ebene und Zielschlüssel statt fest `chunk-orig`/`chunk`) und die P1-Rest-Aufgabe „Lektor-Schlüssel und Chunk-Sprache“.

**Tech Stack:** unverändert (Python ≥ 3.10 Standardbibliothek für Neues, reines HTML/JS ohne Fremdbibliothek, pytest + Node, Playwright für Browserprüfungen).

**Spec:** `dok/2026-11-02-redaktion-epistopheles-design.md` (Schritt 4 der Tabelle in Abschnitt 4, 5.1, 5.4, 5.5, 6, 8) und `dok/2026-11-02-redaktion-p0-p1-implementation-plan.md`. Setzt Phase **P2** um sowie den in `DATENSTRUKTUR.md` / README unter „Bekannte Grenzen“ für P2 vorgemerkten Punkt (Lektor-Schlüssel, Chunk-Sprache).

**Basis:** Branch `claude/zealous-heisenberg-ept4oz` auf dem Stand von P0/P1. Testlauf vor Beginn: `cd tools && python -m pytest speedreader_web redaktion test_redaktion_anwenden.py test_redaktion_server.py pipeline -q` → **428 passed** (in dieser Cloud-Umgebung nach `pip install pytest rich textual playwright==1.63.0`; Chromium liegt unter `/opt/pw-browsers`, die pip-Version von Playwright muss zur vorinstallierten Node-Version passen, sonst werden die Browsertests übersprungen).

## Ausgangslage (belegt, nach Lesen des Codes)

- **Anzeige:** Der Modus „Bereinigt“ zeigt `daten.kapitel[i].text` als Rohtext in `<pre id="rechts-inhalt">` (`fuelleText`), ohne Absatzbezug, ohne Einträge. `daten.kapitel` enthält nur `{nr, titel, text}`; der **Dateiname** (`ziel.datei`, von `schutz.spiele_nach` und vom Entwurf vorausgesetzt) fehlt im Export.
- **Export liest Text mit `Path.read_text`** (`library.read_chapter_text`) und wandelt damit `\r\n` in `\n`. Für den Hash unschädlich (`pruefsumme` normalisiert), aber die Anzeige weicht von den Bytes ab.
- **Schlüsselproblem:** `buchSchluessel(b)` ist `Autor/Titel` aus der Bibliothek. `redaktion_anwenden.lektor_ordner` leitet daraus den Lektor-Ordner ab; bei O'Neil und Piano heißt der Lektor-Ordner anders, bei Popper „Logik der Forschung“ sind die Rohchunks englisch (`en`), die Quelle deutsch. Für den Volltext ist `reader\<Autor>\<Werk>` maßgeblich, der Bibliotheksschlüssel stimmt dort.
- **Anwenden:** `_plane_buch` überspringt Einträge anderer Ebenen als `chunk-orig` („übersprungen (Ebene …)“). Backups über `backup_before_write(buch_pfad, datei)`, atomares Schreiben und Ablage in `redaktion.json` existieren für Chunks.
- **Schutz:** `schutz.spiele_nach(reader_buch)` und `--ueberschreiben` sind seit P0/P1 vorhanden und getestet, aber nur mit künstlichen Einträgen; sie liefern nur eine **Zahl** nicht anwendbarer Einträge (kein Grund, keine Ids) und es gibt **kein Backup** vor `--ueberschreiben` (README: „bewusst“, solange nichts die Ebene `volltext` schrieb; mit P2 ändert sich das).
- **Fußnoten:** im fertigen Text `[^id]` im Fließtext und `[^id]: Text` am Kapitelende (`lesetext.js` kennt dasselbe). Andere Konventionen (`*N`, nackte Zahl) existieren in Altbeständen.
- **Stand angewendeter Änderungen (Spec 5.5):** Nach `--ausfuehren` zeigt die App bis zum nächsten Export den **alten** Text. Für Chunks ist das als „Export wiederholen“ dokumentiert; im Volltext würden weitere Korrekturen auf dem alten Text mit einem `vorher` entstehen, das am PC nicht mehr passt. Das braucht eine Lösung (Task 1, 9).

## Global Constraints

- Gilt unverändert wie in P0/P1: 4 GB RAM, Touch, 960×600 bis 600×960, Bedienelemente ≥ 44 px, alle Oberflächentexte deutsch mit Umlauten, offline-first, keine Fremdbibliothek in der App, auf APIC nur Standardbibliothek, Quelldaten nie direkt von der App geändert, Einarbeiten nur mit `--ausfuehren` nach Dry-Run, vor jedem Schreiben Backup, Verankerung mit `vorher`-Prüfsumme, Konflikt statt Raten, keine automatische Rangfolge zwischen Ebenen, Aufträge nur auf Wunsch.
- **`quelle\*.md` bleibt Source of Truth.** Änderungen am Volltext gehen nur als Einträge der Ebene `volltext` durch das Protokoll; Python (`ops.py`) und JS (`redaktion.js`) liefern byteidentische Ergebnisse (gemeinsame `testvektoren.json`).
- **Nur Textdateien `quelle\*.md`** werden verändert. `_kapitel_index.json`, `kapitel.json`, `meta.json`, `notizen\tags.json` (KI-Inhalte) und Dateinamen bleiben unberührt; Kapitel teilen / zusammenführen / Grenzen verschieben gehört zu P3, KI-Inhalte zu P4. P2 hält nur den Prüfsummen-Vermerk bereit, aus dem P4 „KI-Inhalt veraltet“ ableitet (Task 7).
- **Neue Felder am Eintrag** (`ziel.datei`, `ziel.lektor`, `ziel.sprache`) kommen von Geräten und sind nicht vertrauenswürdig: `datei` nur reiner Dateiname, der in `quelle\` existiert und auf `.md` endet (nicht mit `_` beginnend); `lektor` wie ein Buchschlüssel validiert (`protokoll.eingang_ordner`-Regeln); `sprache` nur `"en"` oder `"de"` (Whitelist). Abweichung → Konflikt, nie Reparatur.
- Das Protokoll des Volltexts liegt in `reader\<Autor>\<Werk>\notizen\redaktion.json` (versioniert / synchronisiert, wie Spec 5.4); die Lektor-`redaktion.json` (Chunk-Ebene) bleibt davon getrennt.
- Keine Änderungen an der TUI.

## Review Focus

1. **Fußnotenbilanz:** Keine Operation darf unbemerkt Marker oder Definitionen verlieren, verdoppeln oder eine Kennung zweimal vergeben. `fussnote`-Aktionen prüfen kapitelweit (Kennung schon vergeben → Konflikt); Absatzbearbeitung warnt in der App, wenn sich die Menge der `[^id]` ändert; der Dry-Run meldet die Bilanz vor / nach. Tests in Task 4, 6, 7, 10.
2. **Byte-Treue der Quelldatei:** Tabs, `\r\n`, fehlendes Schluss-Newline, `## Seite N`-Marker, Roh-HTML und Fußnotendefinitionen außerhalb des betroffenen Absatzes bleiben bytegleich. Mehrzeilige Bearbeitung in einer `\r\n`-Datei darf keine gemischten Zeilenenden erzeugen. Tests in Task 1, 4, 7.
3. **Pfad- und Eingabesicherheit:** `ziel.datei`, `ziel.lektor`, `ziel.sprache` (Global Constraints), Buchschlüssel mit Sonderzeichen. Es wird nie außerhalb von `reader\<Buch>\quelle` bzw. des Lektor-Ordners geschrieben. Tests in Task 2, 7.
4. **Wiederholbarkeit und stilles Verwerfen:** Kette *anwenden → `lektor-zu-episto.py --ueberschreiben` → `spiele_nach`* liefert denselben Text; Einträge, die nach dem Neuaufbau nicht mehr greifen (andere Dateinamen, geänderte Basis), werden **einzeln mit Grund** gemeldet und bleiben im Protokoll, nie nur gezählt. Test in Task 8.
5. **Veralteter Export:** Die App darf nie auf einem Text aufbauen, der angewendete Änderungen nicht enthält, ohne es zu merken. Lösung über `enthalten` im Buchexport (Task 1, 9); Test: Eintrag A angewendet, Export alt → App zeigt A trotzdem abgespielt, `vorher` des Folgeeintrags passt.
6. **Ketten in einer Runde:** Zwei `fussnote`-Einträge, die sich aufeinander stützen (A→B, danach B→C), und ein Satz Einträge am selben Absatz laufen in Entstehungsreihenfolge; scheitert einer, sind die abhängigen `konflikt (abhängig)`. Tests in Task 4, 5.
7. **Falsche Ursachenzuordnung:** „Ursache suchen“ springt nur bei eindeutigem Treffer; bei mehreren oder keinem Treffer zeigt die App das ehrlich an (keine Raterei). Test in Task 13.

---

## Entscheidungen zur Freigabe

Ich habe folgende Voreinstellungen gewählt; bitte widersprechen, was nicht passt:

1. **Bearbeitungsgranularität = ganzer Absatz plus die vorhandenen Strukturwerkzeuge.** „Absatz bearbeiten“ erzeugt einen `ersetzen`-Eintrag mit dem vollständigen neuen Absatz (kein Zeichen-Diff). Verbinden, Trennen, Löschen, Verschieben und Markieren verwenden dieselben Arten wie in P1. *Alternative: Wortgenaue Diff-Einträge; verworfen, weil `vorher`-Prüfung und Paritätstest dann deutlich aufwendiger werden und Konflikte häufiger würden.*
2. **Fußnoten bekommen eine eigene Art `fussnote` mit vier Aktionen** (`marker-umbenennen`, `marker-setzen`, `marker-entfernen`, `definition-umbenennen`). Zuordnen heißt in der Bedienung: Hochzahl antippen, Fußnotentext antippen, „Zuordnen“. Es werden nur die Konvention `[^id]` unterstützt; andere Konventionen werden als Hinweis „andere Konvention“ gemeldet, nicht bearbeitet. Das Verschieben einer Definition ans Kapitelende läuft über das vorhandene `verschieben`. *Nicht-Ziel: Renummerieren ganzer Folgen (später).*
3. **Lektor-Schlüssel und Chunk-Sprache stehen im Eintrag** (`ziel.lektor`, `ziel.sprache`), den die App aus `index.json` (`lektor`, `chunkSprache`) übernimmt. *Alternative: Zuordnungsdatei auf APIC; verworfen, weil sie ein zweites Datum zum Pflegen wäre und der Eintrag dann nicht mehr für sich auswertbar ist.* Der Eingangsordner bleibt nach dem **Bibliotheksschlüssel** geordnet.
4. **Backup vor `lektor-zu-episto.py --ueberschreiben`, wenn `notizen\redaktion.json` Volltext-Einträge enthält** (Kopie der bisherigen `quelle\*.md` nach `notizen\_backup\quelle-<Zeit>\`). Das **weicht von der bisherigen README-Aussage ab** („bewusst kein Backup“), weil ab P2 Handarbeit in diesen Dateien steckt. Ohne Volltext-Einträge bleibt es beim bisherigen Verhalten.
5. **Stand angewendeter Änderungen nur für den Volltext** (Feld `enthalten` im Buchexport). Die Chunk-Ebene behält das P1-Verhalten („Export wiederholen“).
6. **„Ursache suchen“ führt bis zum Chunk** (Übersetzung bzw. bei deutscher Quelle Rohchunk), nicht zur Struktur; ein Strukturgerüst gibt es erst mit P3. Die Suche ist ein textuelles, bewusst vorsichtiges Verfahren (Task 13), kein Versprechen für jeden Absatz.
7. **Verdachtshinweise im Volltext beschränken sich auf Fußnoten** (Marker ohne Definition, Definition ohne Marker, doppelte Kennung, andere Konvention). Die Chunk-Regeln (abgerissene Zeilen, Kopfzeilen) passen nicht auf bereinigten Text und werden nicht übernommen.
8. **Trennen an einer Textstelle** (Task 12a, nachgetragen): neue Form der Art `trennen` mit Kontexttext, nötig weil die meisten Absätze im Volltext einzeilig sind.

Nicht Teil von P2: Strukturgerüst, Kapitel teilen / zusammenführen / Grenzen, Typen Inhaltsverzeichnis / Glossar (P3); KI-Felder bearbeiten und „veraltet“-Anzeige (P4); Buch-Übersicht (P5); Neu übersetzen und Chunk-Ebene unverändert, außer der Schlüssel-Korrektur in Task 2 und 3.

---

## Dateiübersicht

| Datei | Aufgabe |
|---|---|
| `tools/speedreader_web/export_korrektur.py` | `datei` je Kapitel, Bytes statt `read_text`, `reader`/`lektor` im Index, `enthalten` |
| `tools/redaktion/ops.py`, `testvektoren.json` | Art `fussnote`, Zeilenenden-Treue bei `ersetzen` |
| `tools/redaktion/fussnoten.py` (neu), `testvektoren_fussnoten.json` (neu) | Fußnotenanalyse und Bilanz (rein) |
| `tools/speedreader_web/redaktion.js`, `fussnoten.js` (neu) | Gegenstücke in JS, Paritätstests |
| `tools/redaktion_anwenden.py`, `tools/redaktion/protokoll.py` | Volltext-Zweig, Lektor-Schlüssel / Sprache am Eintrag, Fußnotenbilanz im Bericht |
| `tools/redaktion/schutz.py`, `tools/lektor-zu-episto.py` | Nachspiel mit Einzelbericht, Backup vor `--ueberschreiben` |
| `tools/redaktion_server.py`, `tools/pipeline/chunk-neu-uebersetzen.py` | Lektor-Schlüssel in Aufträgen / Vorschlag |
| `tools/speedreader_web/chunkansicht.js` | Ebene und Zielschlüssel verallgemeinern |
| `tools/speedreader_web/ursache.js` (neu) | „Ursache suchen“ (rein) |
| `tools/speedreader_web/korrektur.html`, `bundle.py` | Volltext-Ansicht, Editor, Fußnotenzuordnung, Ursache suchen; `APP_DATEIEN` |
| `tools/speedreader_web/README.md`, `dok/DATENSTRUKTUR.md`, `CLAUDE.md` | Dokumentation |

Tests liegen jeweils neben dem Code. Jede Aufgabe endet mit einem Commit; vor jedem Commit läuft die volle Testsuite (Befehl siehe „Basis“).

---

## P2a: Grundlage (Daten, Operationen, Einarbeiten)

### Task 1: Export: Dateiname, Bytes, Schlüssel, Stand angewendeter Änderungen

**Files:**
- Modify: `tools/speedreader_web/export_korrektur.py`
- Test: `tools/speedreader_web/test_export_korrektur.py`

**Interfaces:**
- Produces in `k0xx.json`: `kapitel[i] = {nr, titel, datei, text}` (`text` aus den **Bytes** der Datei, UTF-8, Zeilenenden unverändert) und `enthalten: [id, …]` (Ids der Einträge mit Ebene `volltext` und Status `angewendet` aus `reader\<Buch>\notizen\redaktion.json`; fehlende / kaputte Datei → `[]`).
- Produces in `index.json` je Buch: `reader` (`"Autor/Werk"` des Bibliotheksbuchs, sonst `""`) und `lektor` (`"Autor/Ordner"` des zugeordneten Lektor-Ordners, sonst `""`). Bestehende Felder bleiben.
- Hinweis: Die App, die ein altes Paket ohne diese Felder bekommt, muss weiter laufen (Task 9: Rückfall `datei` unbekannt → Volltext nur lesbar, Bearbeiten gesperrt mit Hinweis „Daten neu exportieren“).

- [ ] **Step 1: Failing tests:** `test_kapitel_haben_dateiname`; `test_kapitel_text_behaelt_windows_zeilenenden` (Datei mit `\r\n` und Tab, Export enthält sie unverändert, Review Focus 2); `test_index_nennt_reader_und_lektor_schluessel` (Testwurzel mit abweichendem Lektor-Ordnernamen wie bei O'Neil); `test_enthalten_listet_angewendete_volltext_eintraege_und_ignoriert_kaputte_datei`.
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: Export mit Dateiname, Bytes-Text, Schlüsseln und Stand angewendeter Volltext-Änderungen`.

### Task 2: Einarbeiten Chunk-Ebene: Lektor-Schlüssel und Chunk-Sprache aus dem Eintrag

**Files:**
- Modify: `tools/redaktion_anwenden.py` (`lektor_ordner`, `chunk_datei`, `en_chunks_datei`, `_plane_uebernahme`, `_plane_buch`), `tools/redaktion/protokoll.py` (Hilfsfunktion zur Validierung)
- Test: `tools/test_redaktion_anwenden.py`, `tools/redaktion/test_protokoll.py`

**Interfaces:**
- Consumes: `ziel.lektor` (optional), `ziel.sprache` (optional) am Eintrag der Ebene `chunk-orig` und an `uebersetzung-uebernehmen`.
- Produces: `protokoll.pruefe_schluessel(wert: str) -> str` (gibt `"Autor/Titel"` zurück oder wirft `ValueError`, dieselben Regeln wie `eingang_ordner`; Aufruf aus `lektor_ordner`), `lektor_ordner(root, buch, ziel: dict | None = None)`: nimmt `ziel["lektor"]`, wenn vorhanden, sonst `buch`. `chunk_datei(root, buch, chunk, ziel=None)`: Sprache = `ziel["sprache"]` (nur `en`/`de`), sonst `quellsprache(lektor)` wie bisher. Die Sperre „Quelle deutsch, Rohchunks englisch“ (Popper) entfällt für **Korrekturen**; für **Neu übersetzen** bleibt sie, solange `quellsprache == "de"`.
- Einträge desselben Chunks, aber mit abweichendem `lektor`/`sprache`, werden **nicht** gemischt (eigene Gruppe je Datei, sonst Konflikt „uneinheitliches Ziel“).

- [ ] **Step 1: Failing tests:** `test_lektor_schluessel_im_ziel_ueberschreibt_den_buchschluessel`; `test_unsicherer_lektor_schluessel_ist_konflikt` (`"../x/y"`, absolut, drei Teile; Review Focus 3); `test_sprache_en_bei_deutscher_quelle_schreibt_in_en` (Popper-Fall); `test_sprache_ausserhalb_der_whitelist_ist_konflikt`; `test_ohne_lektor_und_sprache_unveraendertes_verhalten` (Regression).
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: Lektor-Schlüssel und Chunk-Sprache am Eintrag (Einarbeiten)`.

### Task 3: Aufträge und App: Lektor-Schlüssel mitgeben

**Files:**
- Modify: `tools/redaktion_server.py` (`POST /api/auftraege`, `GET /api/vorschlag`), `tools/pipeline/chunk-neu-uebersetzen.py` (`uebersetze_chunk`), `tools/redaktion/auftraege.py` (Schlüssel der Warteschlange), `tools/speedreader_web/korrektur.html` (Chunk-Einträge und Aufträge tragen `ziel.lektor`, `ziel.sprache` aus `index.json`)
- Test: `tools/test_redaktion_server.py`, `tools/pipeline/test_chunk_neu_uebersetzen.py`, `tools/speedreader_web/test_neu_uebersetzen.py` (Browser)

**Interfaces:**
- `POST /api/auftraege` nimmt zusätzlich `lektor` (optional, wie ein Buchschlüssel validiert); `GET /api/vorschlag?buch=&chunk=&lektor=` ebenso. Fehlt `lektor`, gilt `buch` (bisheriges Verhalten).
- App: `neueAenderung(…)` ergänzt jeden Eintrag der Ebene `chunk-orig` um `ziel.lektor` (nur wenn `index.buecher[].lektor` nicht leer und ungleich dem Bibliotheksschlüssel) und `ziel.sprache` (`index.buecher[].chunkSprache`, wenn `en`/`de`).

- [ ] **Step 1: Failing tests:** Server: Auftrag mit `lektor` startet den Wrapper mit dem Lektor-Schlüssel; unsicherer `lektor` → 400, nichts geschrieben (Review Focus 3); Wrapper: `uebersetze_chunk` liest den Chunk aus dem Lektor-Ordner. Browser (Testwurzel mit abweichendem Lektor-Ordner): Korrektur annehmen → Eintrag trägt `ziel.lektor`.
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: O'Neil, Piano, Popper: Korrekturen und Neu übersetzen mit Lektor-Schlüssel`.

### Task 4: Operationen: Art `fussnote` und Zeilenenden-Treue (Python)

**Files:**
- Modify: `tools/redaktion/ops.py`, `tools/redaktion/testvektoren.json`
- Create: `tools/redaktion/fussnoten.py` (nur die Erkennungs-Regex hier gemeinsam nutzbar machen; Analyse folgt in Task 6)
- Test: `tools/redaktion/test_ops.py`

**Interfaces:**
- Neue Art `"fussnote"` in `TEXTARTEN`. `ziel` wie bisher (`anfang`, `absatz_index`, optional `zeile`), `parameter.aktion` ∈:
  - `"marker-umbenennen"`: `{alt, neu, vorkommen}` — das `vorkommen`-te `[^alt]` (0-basiert) im Absatz wird `[^neu]`. Definitionszeilen (`[^…]:`) zählen nicht als Marker.
  - `"marker-setzen"`: `{id, nach}` — `[^id]` wird direkt hinter den Text `nach` (≥ 8 Zeichen, normalisiert, kommt im Absatz **genau einmal** vor) eingefügt.
  - `"marker-entfernen"`: `{id, vorkommen}`.
  - `"definition-umbenennen"`: `ziel.zeile` ist die Zeile `[^alt]: …`; `{alt, neu}`.
- **Kapitelweite Prüfung** (der Text ist das ganze Kapitel): `neu` bzw. `id` darf als Definition (bei `definition-umbenennen`, `marker-umbenennen` auf eine Kennung ohne Definition ist erlaubt, doppelte Marker sind erlaubt wie bei Mehrfachverweisen) nicht schon vergeben sein → Konflikt „Kennung bereits vergeben“. Kennungen: nicht leer, ohne `]`, Leerraum, `^` am Anfang.
- `ersetzen`: enthält `parameter.nachher` Zeilenumbrüche und der Quellabsatz benutzt `\r\n`, werden sie auf `\r\n` gesetzt (Review Focus 2). Gilt für beide Ebenen; Vektoren decken Chunk- und Volltextfall ab.

- [ ] **Step 1: Failing tests** (`test_ops.py` und neue Fälle in `testvektoren.json`): je Aktion Erfolg und Konflikt; `test_fussnote_doppelte_kennung_ist_konflikt`; `test_fussnote_aenderung_laesst_rest_byteidentisch` (Tabs, CRLF, `## Seite 12`, Roh-HTML, Definitionsblock am Kapitelende, ohne Schluss-Newline); `test_fussnote_kette_a_nach_b_dann_b_nach_c`; `test_ersetzen_mehrzeilig_in_crlf_datei_bleibt_crlf`.
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: Fußnoten-Operationen und Zeilenenden-Treue in ops.py`.

### Task 5: Gegenstück in JavaScript

**Files:**
- Modify: `tools/speedreader_web/redaktion.js`
- Test: `tools/speedreader_web/test_redaktion_js.py` (läuft alle Vektoren aus Task 4 gegen JS)

- [ ] **Step 1:** Paritätstest läuft rot (neue Vektoren).
- [ ] **Step 2–4:** `wendeAn` um `fussnote` und die Zeilenenden-Regel erweitern; Paritätstest und `spieleAb`-Ketten grün.
- [ ] **Step 5: Commit** `feat: Fußnoten-Operationen in JavaScript mit Paritätstest`.

### Task 6: Fußnotenanalyse (Python und JS, paritätsgeprüft)

**Files:**
- Modify: `tools/redaktion/fussnoten.py`
- Create: `tools/speedreader_web/fussnoten.js`, `tools/redaktion/testvektoren_fussnoten.json`
- Test: `tools/redaktion/test_fussnoten.py`, `tools/speedreader_web/test_fussnoten_js.py`

**Interfaces:**
- `analysiere(text) -> {marker: [{id, absatz_index, zeile, vorkommen}], definitionen: [{id, absatz_index, zeile}], hinweise: [{art, id, absatz_index, zeile, begruendung}], bilanz: {marker, definitionen}}`; JS: `Fussnoten.analysiere`. Hinweisarten: `"marker-ohne-definition"`, `"definition-ohne-marker"`, `"doppelte-definition"`, `"andere-konvention"` (Zeilen am Kapitelende der Form `^\d{1,3}[.)]?\s` ohne `[^`-Definitionen oder `*N`, nur wenn das Kapitel sonst keine `[^`-Definition hat). `bilanz(vorher, nachher)` gibt die Differenz je Kennung zurück (für Warnung und Dry-Run).
- Nur Standardbibliothek / reines JS; Marker in Definitionszeilen (`[^1]: siehe [^2]`) zählen als Marker des Definitionsblocks, nicht als Fließtextmarker (Vektor).

- [ ] **Step 1: Failing tests:** gemeinsame Vektoren (Kapitel mit sauberer Zuordnung, Marker ohne Definition, Waise, Doppelung, andere Konvention, Definition über zwei Zeilen); `test_leistung`: 1 000 000 Zeichen in < 300 ms (großzügige Grenze 1000 ms, Review: 4 GB RAM).
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: Fußnotenanalyse für den Volltext (Python/JS)`.

### Task 7: Einarbeiten am PC: Volltext-Zweig

**Files:**
- Modify: `tools/redaktion_anwenden.py` (neuer Zweig in `_plane_buch` / `fuehre_aus` / Bericht), `tools/redaktion/protokoll.py` (`lade_redaktion` / `speichere_redaktion` erhalten unbekannte Felder, `reader_ordner`)
- Test: `tools/test_redaktion_anwenden.py`

**Interfaces:**
- `reader_ordner(root, buch) -> Path` (`root/reader/<Autor>/<Werk>`, Schlüsselprüfung wie `eingang_ordner`). `plane` behandelt Einträge der Ebene `volltext` mit Status `offen` / `gesendet` je Datei (`ziel.datei`): Datei einlesen als Bytes, `ops.spiele_ab`, Ergebnis je Eintrag; Datei fehlt oder Name unzulässig → Konflikt für alle Einträge dieser Datei. `BuchPlan` bekommt `volltext: list[DateiPlan]` (analog `ChunkPlan`).
- `fuehre_aus`: je geänderter Datei Backup (`backup_before_write(reader_buch, datei)`), atomar schreiben (gemeinsame Hilfsfunktion statt der privaten aus `schutz.py`), Stand im Eingang auf `angewendet`, Eintrag an `reader\…\notizen\redaktion.json` unter `"eintraege"` anhängen (Reihenfolge = Anwendungsreihenfolge), Vermerk `"dateien": {name: {"hash_original": …, "hash_aktuell": …}}` (`hash_original` nur beim ersten Mal setzen; Prüfsumme des Texts vor der ersten Änderung; Grundlage für „KI veraltet“ in P4).
- Bericht: je Datei die geänderten Absätze, **Fußnotenbilanz vorher / nachher** (`fussnoten.analysiere`, neue Hinweise ausdrücklich genannt) und Konflikte mit Grund. Exit-Codes unverändert (0/1/2/3). `uebersprungen (Ebene …)` entfällt für `volltext`; andere Ebenen (`struktur`, `ki`) bleiben übersprungen.
- Schon in `redaktion.json` vermerkte Einträge werden wie bei Chunks nur als `angewendet` nachgetragen (Abbruch zwischen Schreiben und Stand).
- Rücknahme (`ruecknahme`) eines noch nicht angewendeten Volltext-Eintrags verhindert die Anwendung; bei bereits angewendeten „nicht möglich“ (wie P1). Die Korrektur eines angewendeten Eintrags erfolgt durch einen neuen Eintrag.

- [ ] **Step 1: Failing tests** (Modellbaum in `tmp_path`, `reader\…\quelle` mit Tabs / CRLF / Fußnoten): `test_dry_run_volltext_aendert_nichts_und_nennt_absatz_und_bilanz`; `test_ausfuehren_schreibt_datei_mit_backup_und_vermerkt_redaktion_json`; `test_nur_betroffener_absatz_aendert_sich_byteexakt_in_quelldatei` (Review Focus 2); `test_konflikt_bei_geaendertem_absatz_exit_2_und_nichts_geschrieben`; `test_unzulaessige_datei_ist_konflikt` (`../x.md`, `_kapitel_index.json`, `kapitel.json`; Review Focus 3); `test_bilanz_meldet_verlorene_definition`; `test_hash_original_wird_nur_einmal_gesetzt`; `test_zwei_laeufe_bauen_aufeinander_auf` (zweiter Lauf: `vorher` = Ergebnis des ersten); `test_ruecknahme_verhindert_anwendung_volltext`; Regression: bestehende Chunk-Tests unverändert grün.
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: Volltext-Korrekturen am PC einarbeiten (Dry-Run, Backup, Fußnotenbilanz)`.

### Task 8: Schutz: Nachspiel mit Einzelbericht und Backup

**Files:**
- Modify: `tools/redaktion/schutz.py`, `tools/lektor-zu-episto.py`
- Test: `tools/redaktion/test_schutz.py`, `tools/test_lektor_zu_episto_schutz.py`

**Interfaces:**
- `spiele_nach(reader_buch) -> int` bleibt (Rückgabe = Zahl nicht anwendbarer Einträge, bestehende Tests grün), schreibt zusätzlich `notizen\redaktion-nachspiel.json` (`{"zeit", "angewendet": n, "konflikte": [{"id", "datei", "grund"}], "basis_geaendert": [datei, …]}`; `basis_geaendert` = Dateien, deren Text vor dem ersten Eintrag nicht mehr `dateien[name].hash_original` entspricht). Bei 0 Konflikten wird eine vorhandene Datei entfernt.
- `sichere_quelle(reader_buch) -> Path | None`: legt, falls `notizen\redaktion.json` Volltext-Einträge enthält und `quelle\*.md` existieren, eine Kopie unter `notizen\_backup\quelle-<yyyymmddTHHMMSS>\` an (Entscheidung 4); `lektor-zu-episto.py` ruft sie nach `pruefe_ueberschreiben` und vor dem Schreiben (nicht bei `--dry-run`) auf.
- `lektor-zu-episto.py` druckt zusätzlich je Konflikt eine Zeile mit `datei` und `grund`; `redaktion_anwenden.py` nennt im Dry-Run offene Nachspiel-Konflikte des Buchs (`notizen\redaktion-nachspiel.json`).

- [ ] **Step 1: Failing tests:** `test_nachspiel_bericht_nennt_jeden_konflikt_mit_grund`; `test_basis_geaendert_wird_gemeldet`; `test_backup_nur_bei_volltext_eintraegen`; `test_kette_anwenden_ueberschreiben_nachspiel_ergibt_denselben_text` (Review Focus 4; echter Aufruf von `verarbeite(..., ueberschreiben=True)` auf einer Testwurzel; Skript per `importlib` laden); `test_dry_run_sichert_nichts`.
- [ ] **Step 2–4:** rot, implementieren, grün; `python tools/lektor-zu-episto.py --help` läuft.
- [ ] **Step 5: Commit** `feat: Nachspiel von Volltext-Korrekturen mit Einzelbericht und Backup vor --ueberschreiben`.

---

## P2b: Oberfläche auf Epistopheles

### Task 9: Volltext-Ansicht mit Einträgen (Chunkansicht verallgemeinern, `enthalten`)

**Files:**
- Modify: `tools/speedreader_web/chunkansicht.js`, `tools/speedreader_web/korrektur.html`, `tools/speedreader_web/bundle.py` (`APP_DATEIEN` um `fussnoten.js`)
- Test: `tools/speedreader_web/test_chunkansicht.py` (erweitern), neu `tools/speedreader_web/test_volltext.py` (Browser)

**Interfaces:**
- `Chunkansicht.bereite(roh, eintraege, schluessel, abgelehnt, bereit, optionen)` bleibt mit der alten Signatur aufrufbar. Neu `optionen = {ebene: "chunk-orig" | "volltext", zielfeld: "chunk" | "datei", verdacht: false}`; `eigener(e, schluessel)` prüft Ebene und `ziel[zielfeld]`. Standard = bisheriges Verhalten (Regression: alle bestehenden Tests unverändert grün). Verdachtsregeln aus `verdacht.js` nur bei `ebene === "chunk-orig"`; im Volltext liefert `bereite` die Fußnotenhinweise (Task 6) in derselben Form `hinweise`.
- App, Modus **Bereinigt**: zeigt `daten.kapitel[i].text` **mit den Einträgen des Kapitels abgespielt**, die weder `angewendet` noch in `daten.enthalten` stehen; angewendete Einträge, die **nicht** in `enthalten` sind, werden zusätzlich abgespielt (Review Focus 5). Kopfzeile zeigt `Fußnoten: n Hinweise`, im Kapitelwähler `●` bei Kapiteln mit Hinweisen (erst nach Berechnung). Bearbeiten ist gesperrt mit Hinweis, wenn `datei` oder `enthalten` im Datenpaket fehlt (altes Paket), oder wenn das Buch keine Einträge speichern kann (Einträge noch nicht geladen).
- Einträge der Ebene `volltext` erhalten `buch = index.reader` (Fallback `Autor/Titel`) und `ziel.datei`.

- [ ] **Step 1: Failing tests:** Node: `bereite` mit `ebene: "volltext"` ignoriert Chunk-Einträge und umgekehrt; `enthalten`-Logik (Eintrag A angewendet und enthalten → nicht doppelt; angewendet und nicht enthalten → abgespielt); Browser: Kapitel zeigt offenen Eintrag abgespielt, Konflikt-Chip am Absatz, Reload erhält den Zustand.
- [ ] **Step 2–4:** rot, implementieren (Verdacht-/Fußnotenpfad nur für das gezeigte Kapitel, Ergebnis je Kapitel zwischenspeichern), grün.
- [ ] **Step 5: Commit** `feat: Volltext-Ansicht mit Einträgen und Fußnotenhinweisen`.

### Task 10: Absatz bearbeiten

**Files:**
- Modify: `tools/speedreader_web/korrektur.html`, `tools/speedreader_web/chunkansicht.js` (Entwurf `ersetzen`)
- Test: `tools/speedreader_web/test_volltext.py`

**Interfaces:**
- Absatz im Modus Bereinigt antippen → Leiste mit **Bearbeiten**; öffnet unter dem Absatz ein Textfeld (`<textarea id="absatz-editor">`, vorbelegt mit dem gezeigten Absatz, Schrift ≥ 16 px), **Speichern** (≥ 44 px) / **Abbrechen**. Speichern legt einen `ersetzen`-Eintrag an (`ebene: "volltext"`, `ziel = {datei, absatz_index, anfang}`, `parameter.nachher`, `vorher` = Text des gezeigten, also abgespielten Absatzes). Unverändert → kein Eintrag. Leerzeilen im Feld → Meldung „Ein Absatz darf keine Leerzeile enthalten; zum Teilen ‚Absatz hier trennen‘ benutzen“ (der Konflikt in `ops` bleibt Rückfall).
- **Fußnotenwarnung:** ändert sich die Menge der `[^id]` (verloren / hinzugekommen) gegenüber dem Absatz davor, zeigt der Dialog vor dem Speichern die Differenz und verlangt eine zweite Bestätigung („Fußnotenverweise geändert: [^3] fehlt“); Review Focus 1.

- [ ] **Step 1: Failing checks** (Playwright): `#absatz-editor` fehlt; nach Implementierung: Bearbeiten → Speichern erzeugt genau einen Eintrag mit richtigem `vorher.hash`; Text sofort sichtbar; Leiste zählt; Tabs im Rest des Kapitels unverändert; Fußnotenmarker entfernen → Warnung, Abbrechen erzeugt keinen Eintrag; zwei Änderungen am selben Absatz bauen aufeinander auf (Kette).
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: Absatz im Volltext bearbeiten`.

### Task 11: Strukturwerkzeuge im Volltext (verbinden, trennen, löschen, verschieben, markieren)

**Files:**
- Modify: `tools/speedreader_web/chunkansicht.js` (`installiereWerkzeuge` nimmt `optionen.ebene`/`zielfeld`), `tools/speedreader_web/korrektur.html`
- Test: `tools/speedreader_web/test_volltext.py`, `tools/speedreader_web/test_werkzeugleiste.py` (Regression)

**Interfaces:**
- Die Werkzeugleiste (P1) erscheint auch im Modus Bereinigt. Aktiv sind **Zeilen verbinden**, **Ausschneiden / verschieben**, **Löschen**, **Absatz hier trennen**, **Nur markieren** (`marke`, `ebene: "volltext"`, Kategorien frei, mit Notiz). „Kapitel beginnt hier“, „Inhaltsverzeichnis“, „Glossar“ sind im Volltext **ausgeblendet** (P3). Verschieben bleibt innerhalb des Kapitels (Zielabsatz im selben Kapitel); Einträge tragen `ziel.datei`.
- Eine ganze Absatzauswahl über mehrere Absätze → nur „Nur markieren“ (wie P1).

- [ ] **Step 1: Failing check** (Playwright): in Bereinigt keine `#werkzeugleiste`; danach je Werkzeug ein Eintrag mit richtiger `art` und `ebene: "volltext"`; Text ändert sich sichtbar; „Kapitel beginnt hier“ fehlt; P1-Tests der Chunk-Ansicht unverändert grün.
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: Strukturwerkzeuge im Volltext`.

### Task 12: Fußnote zuordnen

**Files:**
- Modify: `tools/speedreader_web/korrektur.html`, `tools/speedreader_web/chunkansicht.js` (Marker- und Definitionszeilen als antippbare Bereiche, `data-fn`)
- Test: `tools/speedreader_web/test_fussnoten_ui.py` (Browser)

**Interfaces:**
- In Bereinigt sind `[^id]` im Fließtext und Definitionszeilen `[^id]: …` als antippbare Bereiche markiert (min. 44 px Trefferfläche, `data-fn`); Hinweisfarben: Marker ohne Definition rot, Definition ohne Marker gelb. Dialog `#fussnote-zuordnen`:
  1. Marker antippen → Schritt 2 „Fußnotentext wählen“ (Liste der Waisen zuerst, dann alle Definitionen des Kapitels mit Textanfang) → **Zuordnen**.
  2. Ergebnis ist ein Eintrag `fussnote`/`definition-umbenennen` (Definition erhält die Kennung des Markers), bei belegter Zielkennung ausdrücklich: „[^7] hat schon eine Definition“, kein Eintrag; Alternative **Marker umbenennen** (`marker-umbenennen`) wird angeboten.
  3. Weitere Aktionen: **Marker entfernen**, **Marker hier setzen** (nach Auswahl im Text: `marker-setzen` mit `nach` = die 40 Zeichen vor der Auswahl; nicht eindeutig → Meldung, kein Eintrag).
- Mehrere Schritte (z. B. erst `A→B`, dann `B→C`) werden in **einer** Runde angelegt (`neueAenderungen`, beide oder keiner; Review Focus 6).

- [ ] **Step 1: Failing checks** (Playwright, Testkapitel mit vertauschten Kennungen und einer Waise): Zuordnen erzeugt `definition-umbenennen`; Hinweis „Waise“ verschwindet; belegte Kennung wird abgewiesen; Marker setzen mit mehrdeutigem Kontext erzeugt nichts; Rücknahme über die Änderungsliste (P1) stellt den Zustand wieder her.
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: Fußnoten im Volltext zuordnen`.

### Task 12a: Absatz an einer Textstelle trennen (nachgetragen)

*Nachtrag nach Task 11:* Im fertigen Volltext sind die meisten Absätze einzeilig; „Absatz hier trennen“ arbeitet auf ganzen Zeilen und ist dort deaktiviert, der Absatz-Editor weist Leerzeilen ab. Der Hauptfall „Absatzgrenze fehlt“ aus dem Entwurf (Abschnitt 1) wäre damit nicht bedienbar. Diese Aufgabe schließt die Lücke.

**Files:**
- Modify: `tools/redaktion/ops.py`, `tools/redaktion/testvektoren.json`, `tools/speedreader_web/redaktion.js`, `tools/speedreader_web/korrektur.html`
- Test: `tools/redaktion/test_ops.py`, `tools/speedreader_web/test_redaktion_js.py`, `tools/speedreader_web/test_volltext.py`

**Interfaces:**
- Art `trennen` bekommt eine zweite Form: `parameter.nach` (wörtlicher Kontext, mindestens 8 Zeichen, kommt im Absatz genau einmal vor, überlappende Treffer zählen mit), ohne `ziel.zeile`. Der Absatz wird hinter diesem Kontext geteilt: `absatz[:ende].rstrip()` + zwei Zeilenenden + `absatz[ende:].lstrip()`; das Zeilenende ist das des Absatzes, sonst das der Datei (wie bei `ersetzen`). Ist einer der beiden Teile leer, ist das ein Konflikt (nie ein leerer Absatz). Mit `ziel.zeile` gilt unverändert die bisherige Zeilenform. Gemeinsame Suchfunktion mit `marker-setzen` (`_finde_stelle`), damit beide dieselben Regeln haben.
- UI: In der Absatzleiste ein Knopf **Absatz hier trennen** (neben „Verweis setzen“), der den Zeiger des Antippens benutzt; Kontext wie bei „Verweis setzen“ (bis 40 Zeichen, bei Mehrdeutigkeit länger, sonst ehrliche Meldung). Die Kontextbildung wird dazu aus dem Code von „Verweis hier setzen“ in eine gemeinsame Funktion gezogen. Die Werkzeugleiste behält ihre Zeilenform für mehrzeilige Absätze.
- Folge: Nach dem Trennen haben beide Teile eigene Anker; spätere Einträge am zweiten Teil bauen auf dem abgespielten Text auf (Kette, Test).

- [ ] **Step 1: Failing tests:** Vektoren in `testvektoren.json` (von Hand): Trennen mitten im einzeiligen Absatz; in CRLF-Datei (`\r\n\r\n` als neues Trennzeichen); Kontext zu kurz, nicht gefunden, mehrdeutig; Trennen am Anfang und am Ende (leerer Teil, Konflikt); Kette „trennen, dann ersetzen am zweiten Teil“; Zeilenform bleibt unverändert (Regression). Paritätstest JS gegen Python. Browser: Zeiger in einem einzeiligen Absatz, **Absatz hier trennen**, Text enthält die Leerzeile, Zähler zeigt eine Änderung, Fußnotenbilanz unverändert, Rücknahme stellt den Absatz wieder her; Zeiger zu nah am Absatzanfang: Meldung, kein Eintrag.
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: Absatz an einer Textstelle trennen`.

### Task 13: Ursache suchen

**Files:**
- Create: `tools/speedreader_web/ursache.js`
- Modify: `tools/speedreader_web/korrektur.html`, `tools/speedreader_web/bundle.py`
- Test: `tools/speedreader_web/test_ursache.py` (Node), `tools/speedreader_web/test_volltext.py` (Browser)

**Interfaces:**
- `Ursache.suche(absatz, quellen, optionen) -> {treffer: [{chunk, versatz, wortfenster}], art: "eindeutig" | "mehrdeutig" | "keine"}`. Verfahren: Fußnotenmarker, Markdown-Zeichen und Tags entfernen, Text kleinschreiben, Silbentrennstriche und Interpunktion normalisieren; drei Wortfenster (Anfang, Mitte, Ende, je 6 Wörter) suchen; **eindeutig** nur, wenn mindestens zwei Fenster im selben Chunk liegen und kein anderer Chunk ein Fenster enthält. `quellen` = `daten.uebersetzung` (bei übersetzter Quelle) bzw. `daten.chunks` (bei deutscher Quelle). Bei gleich langen Kapitel- und Segmentlisten wird der Suchbereich auf den Chunk-Bereich des Kapitels begrenzt (vorhandene `kapitelZuChunk`-Logik umgekehrt).
- UI: Knopf **Ursache suchen** in der Absatzleiste: Treffer eindeutig → wechselt zu Übersetzung (bzw. Rohchunks) am Chunk und hebt die Fundstelle hervor; mehrdeutig → Liste der Kandidaten zum Wählen; keine → „Keine eindeutige Stelle gefunden“. Keine Änderung an Daten.

- [ ] **Step 1: Failing tests:** Node: eindeutiger Treffer trotz Fußnotenmarker und Silbentrennung; mehrdeutiger Text (Wiederholung in zwei Chunks) → `mehrdeutig`; Text ohne Entsprechung → `keine`; Leistung: 500 Chunks à 6 000 Zeichen in < 500 ms (Grenze 1500 ms). Browser: Sprung öffnet den richtigen Chunk (Review Focus 7).
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: Ursache suchen vom Volltext zum Chunk`.

### Task 14: Dokumentation und Gesamtlauf

**Files:**
- Modify: `tools/speedreader_web/README.md` (Abschnitt „Redaktion“: Volltext bearbeiten, Fußnoten zuordnen, Ursache suchen, `enthalten`, Backup vor `--ueberschreiben`, Nachspiel-Bericht; „Bekannte Grenzen“ aktualisieren; Handprüfliste für Touch ergänzen), `dok/DATENSTRUKTUR.md` (`reader\…\notizen\redaktion.json` und `redaktion-nachspiel.json`, Felder `dateien`, `enthalten`, `reader`/`lektor` im Export), `CLAUDE.md` (eine Zeile zum Volltext-Zweig und zum Schutz), `dok/NÄCHSTE_SCHRITTE.md` (P3 als Nächstes)

- [ ] **Step 1:** `export_korrektur.py` und `export_daten.py` laufen auf einer Testwurzel; Paket enthält `fussnoten.js`, `ursache.js`.
- [ ] **Step 2: Gesamttest:** `cd tools && python -m pytest speedreader_web redaktion test_redaktion_anwenden.py test_redaktion_server.py pipeline -q` → alles grün (Erwartung: 428 plus die neuen, keine übersprungenen Browsertests).
- [ ] **Step 3: Durchlauf auf einer Testwurzel mit Kopie eines Buchs (Playwright, kein Eingriff in echte Daten):** Kapitel öffnen, Absatz bearbeiten, Zeilen verbinden, Fußnote zuordnen, Ursache suchen; Empfänger gestartet → Einträge im Eingang; `redaktion_anwenden.py` Dry-Run zeigt Absätze und Fußnotenbilanz, `--ausfuehren` schreibt `quelle\*.md` mit Backup und `redaktion.json`; Export wiederholt → `enthalten` gefüllt; `lektor-zu-episto.py` ohne `--ueberschreiben` bricht ab, mit `--ueberschreiben` entsteht Backup, Nachspiel liefert denselben Text; Konfliktfall (Basis geändert) erscheint im Bericht mit Grund.
- [ ] **Step 4: Handprüfung auf Epistopheles** (nicht automatisierbar, bleibt Aufgabe der Person; Liste in der README): Absatz-Editor mit Bildschirmtastatur, Auswahlgriffe im Volltext, Fußnoten-Trefferflächen ≥ 44 px, Flugmodus.
- [ ] **Step 5: Commit** `docs: Redaktion P2`.

---

## Selbstprüfung

- **Spec-Abdeckung (P2):** Direkt im Text korrigieren (Task 9–11), Fußnote zuordnen (Task 4–6, 12), „Ursache suchen“ (Task 13), Markieren (Task 11), Protokoll und Einarbeiten mit Dry-Run / Backup / Konflikt (Task 7), Wiederholbarkeit und Schutz vor stillem Überschreiben (Task 8), „Stand angewendeter Änderungen“ aus Spec 5.5 für den Volltext (Task 1, 9), P1-Rest „Lektor-Schlüssel und Chunk-Sprache“ (Task 2, 3). **Nicht in diesem Plan:** Strukturgerüst, Kapitelgrenzen, Typen (P3), KI-Inhalte (P4), Buch-Übersicht (P5), Renummerieren ganzer Fußnotenfolgen, andere Fußnotenkonventionen als `[^id]`, Verschieben von Absätzen zwischen Kapiteln.
- **Bewusste Abweichungen / Risiken:** Backup vor `--ueberschreiben` (Entscheidung 4) ändert eine bisher dokumentierte Aussage; `ersetzen` ändert Zeilenenden-Verhalten in `ops` (Task 4, mit Vektoren für beide Ebenen abgesichert); Kersey und Parvini (doppelte `de`-Liste) bleiben für Neu übersetzen gesperrt.
- **Typkonsistenz:** `neuer_eintrag`/`neuerEintrag`, `spiele_ab`/`spieleAb`, `analysiere` (Python / JS), `lektor_ordner(root, buch, ziel)`, `ziel.datei` / `ziel.lektor` / `ziel.sprache` werden in Task 1, 2, 3, 7, 8, 9 einheitlich verwendet; Eintragsfelder stammen aus Spec 5.1.
- **Proportion:** Der Plan beschreibt Schnittstellen, Tests und Prüfpunkte, aber keine Funktionskörper.
