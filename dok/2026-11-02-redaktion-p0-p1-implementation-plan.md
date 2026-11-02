# Redaktion auf Epistopheles, P0 (Grundlage) und P1 (Chunk-Korrektur): Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auf Epistopheles Original-Chunks korrigieren (Verdachtsstellen vorschlagen, frei markieren), die Korrekturen automatisch übers WLAN zu APIC schicken, dort kontrolliert einarbeiten und auf Wunsch einzelne Chunks neu übersetzen.

**Architecture:** Korrekturen sind Einträge in einem Protokoll (Ziel am Text verankert, mit Prüfsumme des Vorzustands). Die Anwendung der Einträge steht doppelt vor (Python für APIC, JavaScript für das Gerät) und wird mit gemeinsamen Testvektoren verglichen. Ein kleiner Empfänger (`tools/redaktion_server.py`) nimmt Einträge an und liefert die App aus; `redaktion_anwenden.py` arbeitet sie per Dry-Run in die Rohdaten ein; Pipeline-Skripte bekommen Schutzmechanismen.

**Tech Stack:** Python ≥ 3.10 (nur Standardbibliothek für alles Neue), reines HTML/JavaScript in `tools/speedreader_web` (keine Fremdbibliothek), Tests mit pytest und Node (wie bisher über pytest gestartet), Browserprüfung mit Playwright.

**Spec:** `dok/2026-11-02-redaktion-epistopheles-design.md` (Abschnitte 4, 5.1 bis 5.4, 6; Skizzen in `dok/2026-11-02-redaktion-mockups-chunk-bearbeiten.html`). Dieser Plan setzt die Phasen **P0** und **P1** um.

## Global Constraints

- Epistopheles: 4 GB RAM, Chrome/ChromeOS, Touch, 960×600 bis 600×960, Bedienelemente mindestens 44 px; alle Oberflächentexte deutsch mit korrekten Umlauten.
- Die App funktioniert **ohne Netz**; nur Senden und Aufträge brauchen APIC. Nur das geöffnete Buch wird im Speicher gehalten.
- Keine Fremdbibliotheken in der App; auf APIC für alles Neue nur Python-Standardbibliothek (`from __future__ import annotations`, Python ≥ 3.10).
- Quelldaten werden **nie** direkt von der App geändert; Änderungen sind Protokolleinträge, am PC nur mit `--ausfuehren` angewendet, vorher Dry-Run, vor jedem Schreiben `episto_tui.backup.backup_before_write`.
- Verankerung am Text (`anfang` = erste 40 Zeichen, Leerraum zusammengezogen) mit `vorher`-Prüfsumme; stimmt sie nicht mehr: `konflikt`, nie still schreiben.
- Keine automatische Rangfolge zwischen Ebenen; Konflikte meldet die App, die Person entscheidet. Aufträge (Neu übersetzen) nur auf ausdrücklichen Wunsch, einzeln nacheinander.
- Empfänger: nur private Netzbereiche (und Loopback), Token im Header `X-Redaktion-Token`, Token in `hilfsdaten\redaktion\token.txt`; läuft nur, wenn man ihn startet; Absender wiederholen alle 30 s.
- `ebook-translate.py` ohne `--resume` bricht ab, wenn `redaktion.json` im Lektor-Buchordner existiert (Ausnahme `--korrekturen-verwerfen`); `lektor-zu-episto.py` überschreibt vorhandene `quelle\*.md` nur mit `--ueberschreiben`.
- Keine Änderungen an der TUI. Alles liegt unter `tools\`; erzeugte Daten unter `hilfsdaten\redaktion\` und im Epistopheles-Paket.

## Review Focus

1. **Roh-Chunks mit Tabs und Windows-Zeilenenden:** Eine Korrektur darf außerhalb des betroffenen Absatzes kein Byte verändern (Tabs zwischen Wörtern, `\r\n`, fehlendes Schluss-Newline). Test in Task 1.
2. **Nicht eindeutiger Anker** (gleiche Kopfzeile in vielen Absätzen): Treffer nur über `absatz_index`, sonst `konflikt`, nie der erste passende. Test in Task 1.
3. **Buchname mit Sonderzeichen und Angriffsversuch** (`Autor, Vorname`, Umlaute, Punkte, `..`, absolute Pfade): sichere Ablage, kein Schreiben außerhalb von `hilfsdaten\redaktion\eingang`. Test in Task 3 und 4.
4. **Wiederholtes und abgebrochenes Senden:** doppelte Einträge (gleiche `id`) werden nicht doppelt gespeichert; halb gelesene oder kaputte Anfrage ändert nichts. Test in Task 4.
5. **Falsches oder fehlendes Token, fremde IP:** 401 beziehungsweise 403, es wird nichts geschrieben und keine Auskunft über Bücher gegeben. Test in Task 4.

---

## Dateiübersicht

| Datei | Aufgabe |
|---|---|
| `tools/redaktion/ops.py` | Einträge erzeugen, Anker, Prüfsumme, Text-Operationen anwenden / abspielen (rein, ohne Dateizugriff) |
| `tools/redaktion/testvektoren.json` | gemeinsame Testfälle für Python und JavaScript |
| `tools/redaktion/protokoll.py` | Eingang, Stand und `redaktion.json` lesen/schreiben, sichere Buchpfade |
| `tools/redaktion/schutz.py` | Prüfung für `ebook-translate.py` (Abbruch ohne `--resume`) |
| `tools/redaktion/auftraege.py` | Warteschlange für Neuübersetzung (einzeln nacheinander) |
| `tools/redaktion_server.py` | Empfänger und Auslieferung der App auf APIC |
| `tools/redaktion_anwenden.py` | Einarbeiten am PC (Dry-Run, Backup, Konflikte) |
| `tools/pipeline/chunk-neu-uebersetzen.py` | einzelnen Chunk mit korrigiertem Original neu übersetzen, Vorschlag ablegen |
| `tools/speedreader_web/redaktion.js` | Gegenstück zu `ops.py`, Protokollspeicher, Senden |
| `tools/speedreader_web/verdacht.js` | Verdachtserkennung (rein) |
| `tools/speedreader_web/korrektur.html` | Oberfläche: Verbindung, Änderungsleiste, Verdachtsstellen, Werkzeugleiste, Änderungsliste, Neu übersetzen |
| `tools/pipeline/ebook-translate.py`, `tools/lektor-zu-episto.py` | Schutz einbauen |

Tests liegen jeweils neben dem Code (`test_*.py`).

---

## P0: Grundlage

### Task 1: Einträge und Text-Operationen (Python)

**Files:**
- Create: `tools/redaktion/__init__.py` (leer), `tools/redaktion/ops.py`, `tools/redaktion/testvektoren.json`
- Test: `tools/redaktion/test_ops.py`

**Interfaces:**
- Consumes: `episto_tui.korrektur.absatz_spannen(text) -> list[tuple[int, int]]` (Absätze im unveränderten Text), `episto_tui.korrektur.ersetze_absatz_exakt(text, index, neuer_absatz) -> str`.
- Produces (von Task 2, 3, 5, 8 bis 13 genutzt):
  - `normalisiere(text: str) -> str` (Unicode NFC, Leerraum zu einem Leerzeichen, getrimmt)
  - `anker_von(text: str, laenge: int = 40) -> str` (= `normalisiere(text)[:laenge]`)
  - `pruefsumme(text: str) -> str` (FNV-1a 64 Bit über UTF-8 von `text` mit `\r\n`→`\n`, 16 Hexstellen)
  - `neuer_eintrag(buch: str, ebene: str, ziel: dict, art: str, parameter: dict, vorher_text: str, hinweis: str = "", geraet: str = "") -> dict` (Felder wie Spec 5.1; `id` = 12 Hex zufällig, `status` = `"offen"`, `vorher` = `{"hash", "ausschnitt"}` mit Ausschnitt = erste 80 Zeichen)
  - `@dataclass Ergebnis(text: str, status: str, grund: str = "")`, `status` ∈ `"angewendet"`, `"konflikt"`
  - `finde_absatz(text: str, ziel: dict) -> int | None`
  - `wende_an(text: str, eintrag: dict) -> Ergebnis`
  - `spiele_ab(text: str, eintraege: list[dict]) -> tuple[str, list[Ergebnis]]`
  - Textarten (`art`): `"ersetzen"` (`parameter.nachher`), `"verbinden"` (Zeile `ziel.zeile` mit der nächsten verbinden), `"trennen"` (Absatz vor `ziel.zeile` teilen), `"loeschen"` (Zeilen `ziel.zeile` bis `ziel.zeile_bis`, ohne `zeile` den ganzen Absatz), `"verschieben"` (Zeilen `zeile` bis `zeile_bis` als neuer Absatz nach dem Absatz mit `parameter.nach_anfang`), `"marke"` (keine Textwirkung).

- [ ] **Step 1: Failing tests** in `test_ops.py`: Test jedes Eintrags in `testvektoren.json` (Felder je Fall: `name`, `text`, `eintraege`, `erwartet_text`, `erwartet_status`), außerdem benannte Tests:
  - `test_verbinden_entfernt_silbentrennung_nur_vor_kleinbuchstabe`: `"…Reprä-\nsentation"` → `"…Repräsentation"`; `"Satz.\nNeu"` → `"Satz. Neu"`.
  - `test_nur_der_betroffene_absatz_aendert_sich_byteexakt` (Review Focus 1): Text mit `\t` zwischen Wörtern, `\r\n` und ohne Schluss-Newline; nach `wende_an` ist `erwartet == text[:a] + neu + text[b:]` für die Absatzspanne `(a, b)`.
  - `test_doppelter_anker_ohne_passenden_index_ist_konflikt` (Review Focus 2) und `test_doppelter_anker_mit_index_trifft`.
  - `test_geaenderter_vorzustand_ist_konflikt`, `test_abhaengige_eintraege_werden_konflikt_wenn_der_vorige_scheitert` (Reihenfolge-Kette am selben Absatz, `grund` nennt die `id` des Auslösers).
  - `test_pruefsumme_ist_stabil`: `pruefsumme("Äpfel\r\nBirnen") == pruefsumme("Äpfel\nBirnen")` und 16 Hexstellen.

- [ ] **Step 2:** `cd tools && python -m pytest redaktion/test_ops.py -q` → FAIL (Modul fehlt).
- [ ] **Step 3: Implement** `ops.py` mit den Signaturen oben. Auflösung des Ziels: Kandidaten = Absätze, deren `anker_von` gleich `ziel["anfang"]`; `ziel["absatz_index"]` gewinnt, wenn er Kandidat ist; sonst genau ein Kandidat; sonst `None`. Zeilentrenner innerhalb eines Absatzes wird erkannt (`\r\n` oder `\n`) und beim Zusammensetzen beibehalten. Geändert wird nur die Spanne des Absatzes (bei `verschieben` zwei Spannen), der Rest bleibt unverändert.
- [ ] **Step 4:** Tests laufen → PASS.
- [ ] **Step 5: Commit** `feat: Redaktions-Einträge und Text-Operationen`.

### Task 2: Gegenstück in JavaScript mit Paritätstest

**Files:**
- Create: `tools/speedreader_web/redaktion.js`
- Test: `tools/speedreader_web/test_redaktion_js.py`

**Interfaces:**
- Consumes: `tools/redaktion/testvektoren.json`, die Semantik aus Task 1.
- Produces: globales `Redaktion` (UMD wie `speedreader.js`, auch per `require` in Node) mit `normalisiere`, `ankerVon`, `pruefsumme` (FNV-1a 64 Bit, `BigInt`), `neuerEintrag(buch, ebene, ziel, art, parameter, vorherText, hinweis, geraet)`, `finde(text, ziel) -> number | null`, `wendeAn(text, eintrag) -> {text, status, grund}`, `spieleAb(text, eintraege) -> {text, ergebnisse}`. Spätere Tasks erweitern dieselbe Datei um den Speicher und das Senden (Task 7).

- [ ] **Step 1: Failing test** `test_js_stimmt_mit_python_ueberein`: läuft für alle Testvektoren Node (`node -e`, Muster wie `test_lesetext.py`), vergleicht `erwartet_text` und `erwartet_status`; zusätzlich Gleichheit von `pruefsumme` und `ankerVon` mit den Python-Werten für 5 feste Strings (inkl. Umlaut, `\r\n`, leerer String). Überspringen, wenn Node fehlt.
- [ ] **Step 2:** Test laufen lassen → FAIL.
- [ ] **Step 3: Implement** `redaktion.js` (gleiche Regeln wie Task 1; Absatzspannen wie `korrektur.absatz_spannen`: Trenner `\n\s*\n`, Spannen im unveränderten Text).
- [ ] **Step 4:** PASS, dazu `pytest redaktion speedreader_web -q`.
- [ ] **Step 5: Commit** `feat: Redaktions-Operationen in JavaScript mit Paritätstest`.

### Task 3: Protokolldateien und sichere Buchpfade

**Files:**
- Create: `tools/redaktion/protokoll.py`
- Test: `tools/redaktion/test_protokoll.py`

**Interfaces:**
- Consumes: Eintragsformat aus Task 1.
- Produces:
  - `buch_schluessel(autor: str, titel: str) -> str` (`"Autor/Titel"`)
  - `eingang_ordner(root: Path, buch: str) -> Path` (`root/hilfsdaten/redaktion/eingang/<Autor>/<Titel>`; wirft `ValueError` bei `..`, absoluten Teilen, leeren Teilen, mehr oder weniger als zwei Teilen, Pfadtrennern im Teil)
  - `schreibe_eingang(root: Path, geraet: str, buch: str, eintraege: list[dict]) -> list[str]` (gibt die neu angenommenen Ids zurück; Einträge mit schon bekannter `id` werden übersprungen; Datei `<geraet>-<yyyymmddTHHMMSS>.json`, Gerätename wird bereinigt)
  - `lade_eingang(root: Path, buch: str) -> list[dict]` (alle Einträge des Buchs, nach `erstellt` sortiert, je `id` einmal)
  - `setze_stand(root: Path, buch: str, id: str, status: str, grund: str = "") -> None` und `lade_stand(root: Path, buch: str) -> dict[str, dict]` (`_stand.json` im Eingangsordner des Buchs)
  - `lade_redaktion(pfad: Path) -> dict` und `speichere_redaktion(pfad: Path, daten: dict) -> None` (`{"eintraege": [...], "chunks": {...}}`, fehlende Datei → leere Struktur, UTF-8, `ensure_ascii=False`)

- [ ] **Step 1: Failing tests:**
  - `test_schreibe_eingang_ist_idempotent`: zweimal gleiche Einträge → zweite Antwort `[]`, nur eine Datei.
  - `test_unsichere_buchnamen_werden_abgelehnt` (Review Focus 3): `"../x/y"`, `"A/../B"`, `"/abs/y"`, `"A"`, `"A/B/C"`, `"A/"` → `ValueError`; `"Bueno de Mesquita, Bruce/The Dictator's Handbook"` und `"Müller, Äh/Ü.ber (1)"` gehen.
  - `test_stand_wird_gespeichert_und_gelesen`, `test_fehlende_redaktion_datei_ist_leer`.
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: Protokolldateien und sichere Buchpfade`.

### Task 4: Empfänger auf APIC

**Files:**
- Create: `tools/redaktion_server.py`
- Test: `tools/test_redaktion_server.py`

**Interfaces:**
- Consumes: `protokoll.schreibe_eingang`, `lade_stand`, `buch_schluessel`; später `auftraege.Warteschlange` (Task 12).
- Produces: `erzeuge_server(root: Path, host: str = "0.0.0.0", port: int = 8080, paket: Path | None = None, token: str | None = None, ip_erlaubt: Callable[[str], bool] | None = None) -> ThreadingHTTPServer` (`token=None` → aus `hilfsdaten\redaktion\token.txt`, wird mit 16 Hex angelegt, wenn sie fehlt; `ip_erlaubt=None` → `ipaddress`: privat oder Loopback; `paket=None` → `root/reader/export-epistopheles`) und `main(argv) -> int` (`--root`, `--port`, `--host`, gibt die Adresse und das Token aus). Endpunkte:
  - `GET /api/ping` → `{"ok": true}`
  - `POST /api/aenderungen` Body `{"geraet": str, "buch": str, "eintraege": [...]}` → `{"angenommen": [ids]}`
  - `GET /api/stand?buch=<A/T>` → `{"stand": {id: {"status", "grund"}}}`
  - Statische Dateien aus `paket`; alle Antworten mit CORS-Headern (`Access-Control-Allow-Origin: *`, `-Headers: X-Redaktion-Token, Content-Type`, `-Methods`, `Access-Control-Allow-Private-Network: true`), `OPTIONS` beantwortet Preflight ohne Token.
  - Fehler: fremde IP 403, falsches/fehlendes Token 401 (für alle `/api/*` außer `OPTIONS`), ungültiger Buchname 400, kaputtes JSON 400. Statische Dateien brauchen kein Token, aber die IP-Prüfung.

- [ ] **Step 1: Failing tests** (Server auf `port=0` in einem Thread, `urllib`):
  - `test_ping_mit_token_ok_ohne_token_401_mit_falschem_401` (Review Focus 5); `test_fremde_ip_wird_abgewiesen` (`ip_erlaubt=lambda ip: False` → 403, Eingangsordner bleibt leer).
  - `test_aenderungen_werden_gespeichert_und_wiederholung_ist_idempotent` (Review Focus 4): zweimal gleicher Body → erste Antwort mit Ids, zweite `[]`, eine Datei.
  - `test_kaputter_body_und_abgebrochene_anfrage_aendern_nichts` (ungültiges JSON → 400; Body kürzer als `Content-Length` → keine Datei).
  - `test_buchname_mit_pfadangriff_wird_abgelehnt` (`"../../x/y"` → 400, nichts außerhalb von `eingang`).
  - `test_statische_auslieferung_und_cors_preflight` (`index.html` aus `paket`; `OPTIONS /api/aenderungen` ohne Token → 204 mit `Access-Control-Allow-Private-Network`).
  - `test_stand_liefert_status_der_ids`.
- [ ] **Step 2–4:** rot, implementieren (`http.server`, `ipaddress`, `secrets`), grün.
- [ ] **Step 5: Commit** `feat: Empfänger für Redaktionsänderungen auf APIC`.

### Task 5: Einarbeiten am PC (Chunk-Ebene)

**Files:**
- Create: `tools/redaktion_anwenden.py`
- Test: `tools/test_redaktion_anwenden.py`

**Interfaces:**
- Consumes: `ops.spiele_ab`, `protokoll.lade_eingang/lade_stand/setze_stand/lade_redaktion/speichere_redaktion`, `episto_tui.backup.backup_before_write(buch_pfad: Path, datei: Path)`.
- Produces: `chunk_datei(root: Path, buch: str, chunk: int) -> Path` (Ordner `rohdaten/Lektor/<A>/<T>/en`, bei `meta.json`-`quellsprache == "de"` `de`; Datei `chunk_{chunk:03d}.md`), `plane(root: Path, buch: str | None = None, eingang_datei: Path | None = None) -> list[BuchPlan]`, `fuehre_aus(root: Path, plaene: list[BuchPlan]) -> dict` (`{"angewendet": int, "konflikte": int}`), `main(argv) -> int` (Standard Dry-Run; `--root`, `--buch`, `--eingang <Datei>`, `--ausfuehren`; Exit 0 ohne Konflikt, 2 mit Konflikt). Nur Einträge der Ebene `chunk-orig` mit Status `offen`/`gesendet`; Einträge anderer Ebenen werden gezählt und übersprungen. Angewendete Chunks: Backup, neuen Text schreiben, den Eintrag `status = "angewendet"` im Eingangsstand setzen, die Chunk-Nummer samt `hash_original` (Prüfsumme des Textes vor der ersten Änderung) in `rohdaten\Lektor\<A>\<T>\redaktion.json` unter `"chunks"` festhalten und die Einträge in `"eintraege"` anhängen. Existiert `rohdaten/en-chunks/<A>/<T>/chunk_NNN.md`, wird sie mit dem gleichen Text überschrieben (auch mit Backup).

- [ ] **Step 1: Failing tests** (Modellbaum in `tmp_path`):
  - `test_dry_run_aendert_nichts_und_nennt_die_aenderungen`.
  - `test_ausfuehren_schreibt_chunk_mit_backup_und_vermerkt_redaktion_json`.
  - `test_konflikt_bleibt_liegen_und_setzt_status_konflikt` (Chunk wurde inzwischen geändert; Exit-Code 2).
  - `test_en_chunks_kopie_wird_mitgezogen`.
  - `test_deutsche_quelle_schreibt_in_de` (`quellsprache = "de"`).
  - `test_eingang_datei_wird_eingelesen_ohne_server` (Rückfall-Weg: `--eingang datei.json` mit `{"geraet","buch","eintraege"}`).
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: Redaktionsänderungen am PC einarbeiten (Dry-Run, Backup)`.

### Task 6: Schutz in den Pipeline-Skripten

**Files:**
- Create: `tools/redaktion/schutz.py`
- Modify: `tools/pipeline/ebook-translate.py` (Guard vor dem Zurücksetzen von `.progress.json`, bei `if not args.resume`, ca. Zeile 915 bis 922; neuer Schalter `--korrekturen-verwerfen`), `tools/lektor-zu-episto.py` (`verarbeite(...)` bekommt `ueberschreiben: bool = False`, CLI `--ueberschreiben`; nach dem Schreiben `spiele_nach`)
- Test: `tools/redaktion/test_schutz.py`, `tools/test_lektor_zu_episto_schutz.py`

**Interfaces:**
- Produces: `schutz.pruefe_neuuebersetzung(buch_ordner: Path, resume: bool, verwerfen: bool) -> str | None` (Fehlertext, wenn `buch_ordner/redaktion.json` existiert und weder `resume` noch `verwerfen`; sonst `None`), `schutz.pruefe_ueberschreiben(quelle_ordner: Path, ueberschreiben: bool, dry_run: bool) -> str | None` (Fehlertext, wenn `quelle_ordner` bereits `*.md` enthält und weder `ueberschreiben` noch `dry_run`), `schutz.spiele_nach(reader_buch: Path) -> int` (spielt die Einträge mit Ebene `volltext` und Status `angewendet` aus `notizen/redaktion.json` auf die neu erzeugten `quelle\*.md` ab; gibt die Zahl nicht anwendbarer Einträge zurück, schreibt keinen Konflikt still weg).

- [ ] **Step 1: Failing tests:** `test_neuuebersetzung_ohne_resume_wird_blockiert_wenn_redaktion_json_existiert`; `..._erlaubt_mit_resume_oder_verwerfen`; `..._erlaubt_ohne_redaktion_json`; `test_lektor_zu_episto_verweigert_ueberschreiben_ohne_schalter` (Skript per `importlib` laden, Dateiname hat Bindestriche; Buch mit vorhandener `quelle\0001_x.md` → Abbruchtext); `test_spiele_nach_wendet_volltext_eintraege_an_und_meldet_unanwendbare`.
- [ ] **Step 2–4:** rot, implementieren, `ebook-translate.py` und `lektor-zu-episto.py` je mit wenigen Zeilen einbinden (Import über `sys.path` auf `tools`), grün; `python lektor-zu-episto.py --help` und `python tools/pipeline/ebook-translate.py --help` laufen.
- [ ] **Step 5: Commit** `feat: Schutz vor stillem Überschreiben von Korrekturen in der Pipeline`.

### Task 7: App: Verbindung, Änderungsspeicher, Senden, Änderungsleiste

**Files:**
- Modify: `tools/speedreader_web/redaktion.js` (Speicher und Senden), `tools/speedreader_web/korrektur.html`, `tools/speedreader_web/bundle.py` (`APP_DATEIEN` um `redaktion.js`, `verdacht.js`), `tools/speedreader_web/test_speedreader_web.py` (bundle-Test)
- Test: `tools/speedreader_web/test_redaktion_js.py` (erweitern)

**Interfaces:**
- Produces in `Redaktion`: `Redaktion.speicher(kv) -> {laden(buchId): Promise<Eintrag[]>, speichern(buchId, eintraege): Promise<void>}` (`kv` = `{get(key), set(key, value)}`; Schlüssel `redaktion:<buchId>`), `Redaktion.sende(eintraege, {adresse, token, buch, geraet}, fetchImpl) -> Promise<{angenommen: string[]}>` (POST `/api/aenderungen`, Header `X-Redaktion-Token`), `Redaktion.stand(buch, {adresse, token}, fetchImpl) -> Promise<Object>` (GET `/api/stand`), `Redaktion.zaehler(eintraege) -> {aenderungen, markierungen, wartend}` (Einträge mit `art: "marke"` zählen als Markierungen, alle anderen als Änderungen; `wartend` = Einträge mit Status `offen`, also noch nicht an APIC gesendet).
- UI-Elemente (Ids): Knopf `#knopf-verbindung` in der Kopfzeile öffnet `<dialog id="verbindung">` mit `#apic-adresse`, `#apic-token`, `#verbindung-testen` (ruft `/api/ping`, zeigt „verbunden“ oder „nicht erreichbar“), Speicherung in `localStorage` (`kverbindung`). Änderungsleiste `#aenderungen-leiste` am unteren Rand der rechten Seite: Text `„{n} Änderungen · {m} Markierungen · {k} warten auf APIC“` bzw. `„alles bei APIC angekommen“` / `„APIC nicht erreichbar“`; Knopf `#aenderungen-sichern` („Änderungen als Datei sichern“, lädt `{geraet, buch, eintraege}` als JSON herunter). Senden: alle 30 s, bei `visibilitychange` zu sichtbar und direkt nach einer neuen Änderung; erfolgreich angenommene Ids erhalten Status `gesendet`; Netzfehler ändern nichts.

- [ ] **Step 1: Failing tests** (Node via pytest, mit Attrappen): `zaehler` zählt `marke` getrennt; `sende` schickt Header und Body korrekt und gibt `angenommen` zurück; bei `fetch`-Fehler wird abgelehnt und der Speicher bleibt unverändert; `speicher` gibt nach `speichern` dasselbe zurück; `test_bundle_enthaelt_redaktion_js` (Paket enthält `redaktion.js`, `verdacht.js`).
- [ ] **Step 2–4:** rot, implementieren, grün. `verdacht.js` wird in Task 8 angelegt; bis dahin enthält `bundle.APP_DATEIEN` nur `redaktion.js` zusätzlich, der Bundle-Test wird in Task 8 erweitert.
- [ ] **Step 5: Browserprüfung** (Playwright, 960×600, Server `redaktion_server.py` mit Testwurzel): Verbindung eintragen und testen → „verbunden“; Eintrag per Konsole anlegen → Leiste zählt, wird gesendet, Datei liegt im Eingang; Server beenden → „APIC nicht erreichbar“, Eintrag bleibt `offen`; Server wieder starten → nach spätestens 30 s gesendet.
- [ ] **Step 6: Commit** `feat: App sendet Redaktionsänderungen zu APIC`.

---

## P1: Chunk-Korrektur

### Task 8: Verdachtserkennung (JavaScript)

**Files:**
- Create: `tools/speedreader_web/verdacht.js`
- Test: `tools/speedreader_web/test_verdacht.py`

**Interfaces:**
- Produces: globales `Verdacht` mit `Verdacht.pruefe(text: string, optionen?: {}) -> Hinweis[]`, `Hinweis = {art, absatz_index, zeile, zeile_bis, anfang, begruendung, vorschlag}`; `art` ∈ `"zeile-bricht-ab"`, `"fragment"`, `"fussnote"`, `"ueberschrift-im-text"`, `"verzeichnis"`, `"glossar"`; `vorschlag` = `{art, parameter}` im Format eines Eintrags aus Task 1 (`verbinden`, `loeschen`, `marke`). Regeln (Schwellen in einem Objekt `SCHWELLEN` oben in der Datei):
  - `zeile-bricht-ab`: Zeile endet ohne `. ! ? : ; …`, `"`, `)` und die nächste Zeile beginnt mit Kleinbuchstabe oder mit einer Fußnotenzahl (`^\d{1,3}\s`); Vorschlag `verbinden`.
  - `fragment`: Zeile ≤ 12 Zeichen oder passend zu `^[—–\-\s]*\d{1,4}[—–\-\s]*$` oder eine Zeile, die in ≥ 3 Absätzen des Chunks wortgleich vorkommt (Kopf-/Fußzeile); Vorschlag `loeschen`.
  - `fussnote`: Marker `[^n]` ohne Definition `[^n]:` im Chunk und umgekehrt; Vorschlag `marke`.
  - `ueberschrift-im-text`: Zeile beginnt mit `#` oder ist ganz in Großbuchstaben (≥ 3 Wörter) mitten in einem Absatz; Vorschlag `marke`.
  - `verzeichnis`: ≥ 4 aufeinanderfolgende Zeilen mit Punktlinien (`\.{3,}`) oder mit Seitenzahl am Zeilenende; `glossar`: ≥ 4 aufeinanderfolgende Zeilen der Form `Begriff: Erklärung`; beide Vorschläge `marke` mit Kategorie.

- [ ] **Step 1: Failing tests** (Node über pytest, Beispieltexte mit Tabs, wie in den Rohchunks): ein Beispiel je `art` mit erwarteter `zeile` und `art`; `test_normaler_text_ergibt_keine_hinweise` (zwei Seiten Fließtext aus einem echten Bestandskapitel, als Datei `testdaten/fliesstext.txt` abgelegt); `test_leistung`: 200 000 Zeichen in unter 300 ms (Messung im Node-Test, großzügige Grenze 1000 ms).
- [ ] **Step 2–4:** rot, implementieren, grün. Danach `APP_DATEIEN` und den Bundle-Test um `verdacht.js` ergänzen.
- [ ] **Step 5: Kalibrierung:** Script `tools/speedreader_web/verdacht_stichprobe.py` (Hilfswerkzeug, kein Test) lässt `Verdacht.pruefe` über 20 zufällige Rohchunks aus `rohdaten\Lektor` laufen und gibt je Art die Trefferzahl aus; Schwellen so anpassen, dass ein Chunk typischerweise < 15 Hinweise hat. Ergebnis (Zahlen) im Commit-Text nennen.
- [ ] **Step 6: Commit** `feat: Verdachtserkennung für Roh-Chunks`.

### Task 9: Chunk-Ansicht A: Verdachtsstellen annehmen oder ablehnen

**Files:**
- Modify: `tools/speedreader_web/korrektur.html`

**Interfaces:**
- Consumes: `Redaktion.spieleAb`, `Redaktion.neuerEintrag`, `Redaktion.speicher`, `Verdacht.pruefe`.
- Produces (UI): Im Modus **Rohchunks** (und im oberen Feld von **Übersetzung**) wird der Text **mit den offenen Einträgen des Chunks abgespielt** angezeigt (`Redaktion.spieleAb`), Zeilen mit Hinweis tragen Hintergrund und Chip (`.verdacht`, Klassen je Art wie in der Skizze: gelb/rot/blau). Chip antippen öffnet kleine Leiste an der Zeile mit **Annehmen** (legt den Eintrag aus `vorschlag` an, `ebene: "chunk-orig"`, `ziel.chunk = pos.chunk`), **Ablehnen** (merkt `anfang`+`art` in `localStorage` `kabgelehnt:<buchId>`, Hinweis verschwindet) und **Markieren** (Eintrag `marke`). Kopfzeile der rechten Seite zeigt `„Verdacht: n offen“` je Chunk; im Chunk-Wähler steht bei Chunks mit offenen Hinweisen ein `●`.
- Konflikte: Einträge mit Status `konflikt` zeigen am Absatz einen roten Chip „Konflikt“ mit **Neu anwenden** (neuer Eintrag mit aktuellem `vorher`) und **Verwerfen**.

- [ ] **Step 1: Failing check** (Playwright gegen ein Paket mit Testbuch, Chunk mit abgerissener Zeile): vor der Implementierung ist kein `.verdacht` im DOM.
- [ ] **Step 2: Implement** gemäß Schnittstelle; Verdachtserkennung läuft nur für den angezeigten Chunk, Ergebnis wird je Chunk zwischengespeichert.
- [ ] **Step 3: Prüfen** (Playwright): Annehmen verbindet die Zeilen sichtbar, Leiste zählt eine Änderung mehr, Rücknahme (Task 11) fehlt noch, Ablehnen lässt den Hinweis auch nach Neuladen verschwinden; echter Chunk aus `rohdaten` mit Fußnote zeigt mindestens einen plausiblen Hinweis; Tabs bleiben im Text erhalten.
- [ ] **Step 4: Commit** `feat: Verdachtsstellen in der Chunk-Ansicht annehmen oder ablehnen`.

### Task 10: Chunk-Ansicht B: frei markieren und Werkzeugleiste

**Files:**
- Modify: `tools/speedreader_web/korrektur.html`

**Interfaces:**
- Consumes: wie Task 9.
- Produces (UI): Nach Auswahl von Text im rechten Feld erscheint `#werkzeugleiste` unter der Auswahl mit den Werkzeugen **Zeilen verbinden**, **Ausschneiden / verschieben** (zweiter Schritt: Zielabsatz antippen), **Löschen**, **Absatz hier trennen**, **Kapitel beginnt hier** (Eintrag `marke` mit `parameter.kategorie = "kapitelgrenze-vermutet"`), **Inhaltsverzeichnis**, **Glossar** (`marke`, Kategorien `"verzeichnis"`, `"glossar"`), **Nur markieren** (`marke`, optionaler Freitext). Auswahl wird auf Zeilen und Absatz abgebildet (`ziel.absatz_index`, `anfang`, `zeile`, `zeile_bis`); Auswahl über mehrere Absätze → Werkzeuge außer „Nur markieren“, „Inhaltsverzeichnis“ und „Glossar“ sind deaktiviert. Alle Schaltflächen ≥ 44 px.

- [ ] **Step 1: Failing check** (Playwright): Auswahl per Skript setzen, `#werkzeugleiste` fehlt.
- [ ] **Step 2: Implement.**
- [ ] **Step 3: Prüfen:** je Werkzeug ein Eintrag mit richtiger `art`, Text ändert sich sichtbar (verbinden, trennen, löschen, verschieben), Markierungen ändern den Text nicht und erscheinen in der Leiste als Markierung; Auswahl über zwei Absätze deaktiviert die falschen Werkzeuge.
- [ ] **Step 4: Commit** `feat: freies Markieren mit Werkzeugleiste in der Chunk-Ansicht`.

### Task 11: Änderungsliste mit Rücknahme

**Files:**
- Modify: `tools/speedreader_web/korrektur.html`, `tools/speedreader_web/redaktion.js` (`Redaktion.zuruecknehmen(eintraege, id) -> Eintrag[]`)
- Test: `tools/speedreader_web/test_redaktion_js.py`

**Interfaces:**
- Produces: `Redaktion.zuruecknehmen(eintraege, id)` entfernt den Eintrag, wenn Status `offen` oder `gesendet`; bei `angewendet` unverändert (Rücknahme nicht möglich); Einträge, die vom entfernten abhängen, werden im Ergebnis als `konflikt` markiert (nicht gelöscht). UI: Knopf in der Änderungsleiste öffnet `<dialog id="aenderungsliste">` mit allen Einträgen des Buchs (Art in Klartext, Chunk, Status, Zeit), je **Rücknehmen** (und bei `gesendet` Hinweis „bereits bei APIC“; Rücknahme dann nur lokal und als Eintrag `ruecknahme` mitgesendet, siehe unten), **Springen** (öffnet den Chunk).
- Rücknahme eines schon gesendeten Eintrags sendet einen Eintrag `art: "ruecknahme"`, `parameter.id = <id>`; `redaktion_anwenden.py` überspringt den Zieleintrag, wenn er noch nicht angewendet ist (Erweiterung von Task 5 in diesem Task, mit Test `test_ruecknahme_verhindert_anwendung`).

- [ ] **Step 1: Failing tests:** `zuruecknehmen` entfernt offenen Eintrag, lässt angewendeten stehen, markiert abhängigen als Konflikt; Python `test_ruecknahme_verhindert_anwendung`.
- [ ] **Step 2–4:** rot, implementieren, grün; Browserprüfung: Verbinden annehmen, in der Liste zurücknehmen, Text ist wieder abgerissen, Zähler sinkt.
- [ ] **Step 5: Commit** `feat: Änderungsliste mit Rücknahme`.

### Task 12: Neu übersetzen auf APIC (Wrapper und Warteschlange)

**Files:**
- Create: `tools/pipeline/chunk-neu-uebersetzen.py`, `tools/redaktion/auftraege.py`
- Modify: `tools/redaktion_server.py` (Endpunkte)
- Test: `tools/pipeline/test_chunk_neu_uebersetzen.py`, `tools/redaktion/test_auftraege.py`, `tools/test_redaktion_server.py` (erweitern)

**Interfaces:**
- Consumes: `ops.spiele_ab`, `protokoll.lade_eingang/lade_stand`, `redaktion_anwenden.chunk_datei` (aus Task 5); vorhandenes `translate_chunk(text, "en", "English", url, model, "de", "German")` aus `ebook-translate.py` (per `importlib` geladen, Dateiname mit Bindestrich; Modell `aya-expanse:32b`, URL `http://localhost:11434/api/chat`).
- Produces:
  - `chunk-neu-uebersetzen.py`: `uebersetze_chunk(root: Path, buch: str, chunk: int, uebersetzer: Callable[[str], str]) -> Path` (liest den Original-Chunk von der Platte, spielt die noch nicht angewendeten Einträge dieses Chunks aus dem Eingang **im Speicher** darauf ab, übersetzt, schreibt `de/chunk_NNN.md.neu`; ersetzt `de/chunk_NNN.md` nie) und `main(argv) -> int` (`--root`, `--buch`, `--chunk`).
  - `auftraege.Warteschlange(root: Path, starte: Callable[[dict], None])`: `reiche_ein(art: str, buch: str, chunk: int) -> str` (Id), `status(id: str) -> dict` (`{"zustand": "wartet"|"laeuft"|"fertig"|"fehler", "meldung": str}`), arbeitet **einzeln nacheinander** in einem Hintergrund-Thread; `starte(job)` führt den Auftrag aus (im Server: Unterprozess mit `chunk-neu-uebersetzen.py`).
  - Server: `POST /api/auftraege` `{"art": "neu-uebersetzen", "buch", "chunk"}` → `{"id"}`; `GET /api/auftraege/<id>` → Status; `GET /api/vorschlag?buch=&chunk=` → `{"alt": str, "neu": str}` (Inhalt von `de/chunk_NNN.md` und `.neu`, 404 ohne `.neu`). Gleiche Token- und IP-Regeln wie in Task 4.

- [ ] **Step 1: Failing tests:** `test_uebersetze_chunk_nimmt_den_korrigierten_text_und_ersetzt_nichts` (Attrappe `lambda t: "DE:" + t`; Eingangseintrag `verbinden` noch `gesendet`; Ergebnisdatei enthält `"DE:"` + korrigierten Text; `de/chunk_NNN.md` byteidentisch); `test_angewendete_eintraege_werden_nicht_doppelt_abgespielt`; `test_warteschlange_arbeitet_einzeln_nacheinander` (zwei Aufträge, `starte` mit Ereignissen: der zweite beginnt erst nach dem Ende des ersten); `test_fehler_im_auftrag_setzt_zustand_fehler`; Serverstests für die drei Endpunkte (mit Attrappe als `starte`).
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Commit** `feat: Einzel-Chunk neu übersetzen als Vorschlag auf APIC`.

### Task 13: Neu übersetzen in der App und Übernehmen

**Files:**
- Modify: `tools/speedreader_web/korrektur.html`, `tools/speedreader_web/redaktion.js` (`Redaktion.auftrag(...)`, `Redaktion.vorschlag(...)`), `tools/redaktion_anwenden.py` (Art `uebersetzung-uebernehmen`)
- Test: `tools/speedreader_web/test_redaktion_js.py`, `tools/test_redaktion_anwenden.py`

**Interfaces:**
- Produces: In `Redaktion`: `auftrag(buch, chunk, {adresse, token}, fetchImpl) -> Promise<{id}>`, `auftragStatus(id, opt, fetchImpl) -> Promise<{zustand, meldung}>`, `vorschlag(buch, chunk, opt, fetchImpl) -> Promise<{alt, neu}>`. UI im Modus **Übersetzung**: Hat der Chunk offene oder gesendete Korrekturen, zeigt der Kopf der Übersetzung „Original geändert, Übersetzung veraltet“ und den Knopf **Neu übersetzen**; Fortschritt je Chunk (wartet, läuft, fertig, Fehler, „APIC nicht erreichbar, Wunsch gemerkt“; der Wunsch bleibt in `localStorage` `kauftraege:<buchId>` und wird bei Erreichbarkeit abgeschickt); bei `fertig` öffnet **Vergleich** alt/neu nebeneinander mit **Übernehmen** (Eintrag `uebersetzung-uebernehmen`, `ebene: "uebersetzung"`) und **Verwerfen**.
- `redaktion_anwenden.py`: `uebersetzung-uebernehmen` kopiert `de/chunk_NNN.md.neu` nach `de/chunk_NNN.md` (Backup, `.neu` danach gelöscht); fehlt `.neu`, Konflikt.

- [ ] **Step 1: Failing tests:** JS: `auftrag` ruft POST mit Token; `vorschlag` gibt `{alt, neu}`; Python: `test_uebernehmen_ersetzt_de_chunk_mit_backup`, `test_uebernehmen_ohne_neu_datei_ist_konflikt`.
- [ ] **Step 2–4:** rot, implementieren, grün.
- [ ] **Step 5: Browserprüfung** (Server mit Attrappe als Übersetzer): Korrektur annehmen → Hinweis „Übersetzung veraltet“ → Neu übersetzen → Status läuft/fertig → Vergleich → Übernehmen → Eintrag erscheint in der Änderungsliste; APIC aus → Wunsch bleibt, geht nach Start hinaus.
- [ ] **Step 6: Commit** `feat: Neu übersetzen und Vergleich in der App`.

### Task 14: Paket, Dokumentation, Gesamtlauf mit echten Daten

**Files:**
- Modify: `tools/speedreader_web/README.md` (Abschnitt „Redaktion“: Start des Empfängers, Verbindung eintragen, Bedienung je Werkzeug, Einarbeiten am PC), `dok/DATENSTRUKTUR.md` (Ordner `hilfsdaten\redaktion\`, `redaktion.json`), `CLAUDE.md` (eine Zeile zu `redaktion_server.py` / `redaktion_anwenden.py`)

- [ ] **Step 1:** `python tools/speedreader_web/export_korrektur.py` und `export_daten.py` laufen; Paket enthält `redaktion.js`, `verdacht.js`.
- [ ] **Step 2: Gesamttest:** `cd tools && python -m pytest -q` → alles grün (Erwartung: bisherige 420 Tests plus die neuen).
- [ ] **Step 3: Durchlauf mit echten Daten (Playwright, Testwurzel mit Kopie eines Buchs, kein Eingriff in `rohdaten`):** Buch öffnen, Chunk mit Fußnote, Verdachtsstelle annehmen, frei markieren und löschen, Leiste zählt, Empfänger gestartet → Einträge im Eingang; `redaktion_anwenden.py` Dry-Run zeigt die Änderungen, `--ausfuehren` schreibt Chunk mit Backup und `redaktion.json`; Neu übersetzen mit Attrappe, Vergleich, Übernehmen; `ebook-translate.py` ohne `--resume` meldet den Schutz.
- [ ] **Step 4: Commit** `docs: Redaktion P0 und P1`.

---

## Selbstprüfung

- **Spec-Abdeckung (P0/P1):** Protokoll und Verankerung (Task 1–3), Rückweg per WLAN mit Token, IP-Filter, Warteschlange auf dem Gerät und Rückfall-Datei (Task 4, 7), Einarbeiten mit Dry-Run und Backup (Task 5), Schutz der Pipeline (Task 6), Verdachtsstellen plus freies Markieren (Task 8–10), Rücknahme und Konflikte (Task 11), Neu übersetzen auf Wunsch mit Vergleich (Task 12–13), Doku (Task 14). **Nicht in diesem Plan:** Volltext-Direktkorrektur und Fußnoten-Zuordnung (P2), Strukturgerüst (P3), KI-Inhalte (P4), Buch-Übersicht (P5), Abgleich der Spezifikation mit Altbeständen nur über den Schutz in Task 6.
- **Lücke bewusst benannt:** Der Schutz in `lektor-zu-episto.py` spielt Einträge der Ebene `volltext` nach, die erst in P2 entstehen; die Funktion ist in Task 6 getestet, wird aber bis P2 praktisch nur mit leerem Protokoll aufgerufen.
- **Typkonsistenz:** `neuer_eintrag`/`neuerEintrag`, `spiele_ab`/`spieleAb`, `lade_stand`/`stand` und `chunk_datei` werden in Task 5, 11, 12 mit denselben Namen und Feldern verwendet; Eintragsfelder stammen aus Spec 5.1.
- **Proportion:** Der Plan beschreibt Schnittstellen, Tests und Prüfpunkte, aber keine Funktionskörper.
