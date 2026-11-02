# Design: Redaktion der ganzen Kette auf Epistopheles

Stand 2026-11-02. Entwurf, noch nicht freigegeben.

## 1. Worum es geht und warum

Epistopheles (Chromebook, Chrome, 10,1″ Touch, 4 GB RAM) ist das Gerät, auf dem Bücher **redigiert** werden.
Heute kann die Web-App dort nur **ansehen** (Lesen, Speedreader, geteilte Korrekturansicht). Die
Übersetzungs-Pipeline macht aber Fehler, die man nur beim Lesen bemerkt:

- Zeilen brechen mitten im Satz ab, besonders bei Fußnoten.
- Textfragmente stehen dort, wo sie offensichtlich nicht hingehören (z. B. Seitenzahlen, Kopfzeilen).
- Absatz- und Kapitelgrenzen sind falsch.
- Inhaltsverzeichnis und Glossar sind falsch vom Text abgegrenzt.
- Fußnoten sind falsch zugeordnet. Das ist die häufigste Ursache für schlechte Übersetzungen: Sind die
  Zuordnungen oben in der Kette behoben, ist auch die Übersetzung sauber.

Wer solche Fehler heute findet, muss sich merken, an den PC gehen und dort in Dateien arbeiten. Ziel ist, dass die
Redakteurin / der Redakteur **auf Epistopheles selbst korrigieren oder markieren kann**, und dass die Korrekturen
**automatisch übers WLAN zu APIC zurückfließen** und dort kontrolliert in die Daten eingearbeitet werden.

**Die Kette** (jeder Schritt braucht eine intuitive Bedienung auf Epistopheles):

```
Original-Ebook → Original-Chunks → übersetzte Chunks → Struktur (Kapitel, Fußnoten, Inhaltsverzeichnis, Glossar)
               → fertiger Volltext → KI-Inhalte (Zusammenfassung, Thesen, …)
```

**Rangfolge, falls nur ein Schritt richtig gut werden kann:** Ebook → Original-Chunks (dort entstehen die meisten Fehler).

## 2. Ziele, Nicht-Ziele, Anti-Ziele

**Ziele**
1. Fehler auf Epistopheles **selbst beheben** oder **nur markieren** können, in jedem Schritt der Kette.
2. Verdachtsstellen werden **vorgeschlagen**, man kann aber auch **frei markieren**.
3. Korrekturen laufen **automatisch übers WLAN zu APIC**, auch wenn sie unterwegs offline entstanden sind.
4. Im fertigen Volltext direkt korrigieren, **wahlweise** von dort zur Ursache im früheren Schritt springen.
5. Neuübersetzung und KI-Neuerzeugung **nur auf ausdrücklichen Wunsch**, mit Ergebnis zum Vergleichen.
6. Bedienbar mit dem Finger auf 10,1″ (Touch), ohne Tastatur-Zwang.

**Nicht-Ziele (diese Runde)**
- Das Ebook selbst ändern.
- Übersetzte Chunks von Hand überschreiben. Übersetzungsfehler werden oben in der Kette behoben und neu übersetzt.
- Mehrere Personen gleichzeitig, Benutzerverwaltung.
- Änderungen an der TUI (kommt später), außer dass sie die neuen Dateien nicht stört.
- Das ganze Buch automatisch neu erzeugen. Nur einzelne Chunks und Kapitel.

**Anti-Ziele (ein Misserfolg, auch wenn es technisch läuft)**
- Eine Korrektur geht still verloren (z. B. weil die Pipeline später den fertigen Text neu erzeugt und überschreibt).
- Eine Korrektur landet an der falschen Stelle, weil sich der Text inzwischen geändert hat.
- Am PC wird etwas ohne Kontrolle überschrieben.
- Neuübersetzung oder KI läuft von selbst los und ersetzt Geprüftes.

## 3. Ausgangslage (belegt)

**Auf Epistopheles vorhanden** (`tools/speedreader_web`): `index.html` (Lesen, Speedreader, KI-Text, Original),
`korrektur.html` (geteilte Ansicht: Ebook links, Rohchunks / bereinigter Text / Übersetzung rechts, Chunk ↔ Kapitel-Sprung),
`epub.js`, `lesetext.js`, `speedreader.js`; Exporte `export_daten.py`, `export_korrektur.py` nach `reader/export-epistopheles/`.
Reines HTML/JS, offline-first (IndexedDB), Python nur Standardbibliothek. **Es gibt keinen Schreibweg zurück.**

**Auf APIC vorhanden:** Ollama (:11434), Qdrant (:6333). Kein eigener Server. Pipeline in `tools/pipeline/`.

**Wichtige Eigenschaften der Pipeline**, die den Entwurf bestimmen:

1. **`ebook-translate.py` liest die Original-Chunks nie wieder.** Es extrahiert bei jedem Lauf die Quelldatei neu und
   zerlegt sie. Eine von Hand korrigierte `en\chunk_NNN.md` wirkt nur, wenn ihr Text selbst an `translate_chunk`
   übergeben wird. Einzelne Chunks neu übersetzen geht nur über `fix-chunks.gib_frei` + `--resume`; `--resume`
   ohne freigegebenen Index tut nichts, ein Lauf ohne `--resume` setzt den ganzen Fortschritt zurück. Einen
   Einzel-Chunk-Aufruf gibt es nicht.
2. **Kapitelgrenzen liegen in `rohdaten\Lektor\<A>\<T>\kapitel.json`** (`segmente`: `chunk`, `position`, `vorspann`),
   gemessen im **übersetzten (de\) Chunk-Text**. Ändert sich die Länge eines Chunks, verschieben sich Positionen.
3. **`lektor-zu-episto.py` überschreibt den fertigen Volltext ohne Schutz und ohne Backup**
   (`reader\…\quelle\*.md`, `_kapitel_index.json`, `kapitel.json`, `meta.json`, `.progress.json`). Von Hand
   gepflegte Änderungen gehen beim nächsten Lauf verloren.
4. **Inhaltsverzeichnis und Glossar haben keinen eigenen Typ.** Es gibt nur „Vorspann“ / „Anhang“ nach Dateinamenregeln.
5. **Fußnoten:** im fertigen Text Marker `[^id]` und Fußnotentext **am Kapitelende**. Das ist das gewünschte Zielbild.
   Verschiedene Bücher haben abweichende Konventionen (`[^id]`, `*N`, nackte Zahl).
6. **KI-Inhalte** liegen je Kapitel in `reader\…\notizen\tags.json`. `taggen.ps1` hat keinen Einzelkapitel-Schalter und
   kein Hinweisfeld; der Prompt steht fest im Skript. `neu-zusammenfassen.py` zeigt das passende Muster:
   erst Vorschlag erzeugen, dann gezielt anwenden, mit Backup.
7. **Bestehende Korrektur-Bausteine** der TUI (wiederverwendbar): Marken als Highlights (`farbe == "korrektur"`),
   Absatzanker (`absatz_index`, `absatz_anfang`, `locate_paragraph`), `ersetze_absatz_exakt`, `backup_before_write`,
   `pruefe_vorschlag` (warnt bei abweichenden Fußnotenmarkern).

## 4. Bedienung je Schritt der Kette

Allgemein: In allen Schritten gilt „Änderung sofort sichtbar, einzeln rücknehmbar, unten immer der Stand
‚3 Änderungen · 1 Markierung · 2 warten auf APIC‘“.

| Schritt | Was man sieht | Was man tun kann |
|---|---|---|
| **1. Ebook → Original-Chunks** (Schwerpunkt) | Ebook links, Roh-Chunk rechts, Verdachtsstellen farbig markiert | Vorschlag annehmen / ablehnen; frei markieren und Werkzeug wählen: Zeilen verbinden, verschieben, löschen, Absatz trennen, Kapitel beginnt hier, als Inhaltsverzeichnis / Glossar kennzeichnen, nur markieren |
| **2. Übersetzte Chunks** | Original oben, Übersetzung unten, Warnzeichen (Längenverhältnis, Fußnotenzahl, unübersetzt) | **Keine Bearbeitung.** „Ursache im Original suchen“, **Neu übersetzen** (auf Wunsch) mit Vergleich alt/neu |
| **3. Struktur** | Erkannte Gliederung als Gerüst (Vorspann, Kapitel, Anhang, Inhaltsverzeichnis, Glossar, Fußnoten) neben dem Text | Grenze verschieben, Kapitel teilen / zusammenführen, Bereich als Typ kennzeichnen, **Fußnote zuordnen** (Hochzahl im Text ↔ Fußnotentext am Kapitelende) |
| **4. Fertiger Volltext** | Kapiteltext, Hochzahlen, Fußnotentext am Kapitelende | **Direkt im Text korrigieren**; wahlweise **„Ursache suchen“** (führt zum Chunk / zur Struktur); Markieren |
| **5. KI-Inhalte** | Je Kapitel die Felder (Zusammenfassung, Thesen, Gegenpositionen, Kernbegriffe, Definitionen, Belege) | **Selbst umformulieren** oder **Neu erzeugen mit Korrekturhinweis** (Ergebnis daneben, übernehmen / verwerfen); Hinweis „Text geändert, KI-Inhalt evtl. veraltet“ |

**„Kapitel beginnt hier“ in Schritt 1** ist eine **Markierung mit Typ** („Kapitelgrenze vermutet“), noch keine Änderung
von `kapitel.json`. Die echten Kapitelgrenzen werden in Schritt 3 auf dem **deutschen Text** gesetzt, weil
`kapitel.json` Positionen im übersetzten Text führt. In Schritt 3 erscheinen die Markierungen als vorgemerkte
Stellen, die man bestätigt oder verwirft. Bei deutschen Quellen ist der Original-Chunk selbst deutsch. *(Meine
Entscheidung.)*

**Verdachtsstellen (Schritt 1, 3, 4):** Die App schlägt vor, nichts wird ohne Annahme geändert. Abgelehnte Vorschläge
werden gemerkt und tauchen nicht wieder auf. Ein Vorschlag nennt, **was** und **warum**. Erkannt werden:

- Zeile endet ohne Satzzeichen und die nächste Zeile beginnt klein oder mit einer Fußnotenzahl (abgerissener Satz).
- Kurze, isolierte Zeilen, die wie Seitenzahl oder Kopf- / Fußzeile aussehen (`— 47 —`, wiederkehrende Zeilen).
- Fußnotenmarker ohne Fußnotentext und umgekehrt; Marker in Original und Übersetzung ungleich oft.
- Überschriftenähnliche Zeile mitten im Absatz; auffällig kurze oder lange Kapitel / Absätze.
- Blöcke, die wie Inhaltsverzeichnis (Punktlinien, Zeilen mit Seitenzahlen) oder Glossar (Begriff: Erklärung) aussehen und
  nicht als solche gekennzeichnet sind oder unklar enden.

Die Erkennung ist **regelbasiert (deterministisch)** und läuft auf dem Gerät, ohne APIC.

**Buch-Übersicht:** Je Buch die Kette als Reihe von Schritten, jeweils mit Zählern (offene Verdachtsstellen, Markierungen,
veraltete Übersetzungen, veraltete KI-Inhalte, wartende Änderungen) und Sprung in den Schritt.

## 5. Gemeinsame Bausteine

### 5.1 Änderungsprotokoll (Edit-Log)

Jede Korrektur ist ein **Eintrag** in einem Protokoll je Buch; die Quelldaten werden nie direkt verändert.

```
{ id, buch: "<Autor>/<Titel>", ebene: "chunk-orig" | "volltext" | "struktur" | "ki" | "uebersetzung",
  ziel: { datei | chunk, absatz_index, anfang },      // anfang = erste ~40 Zeichen, normalisiert (wie locate_paragraph)
  art: "ersetzen" | "verbinden" | "trennen" | "loeschen" | "verschieben" | "kapitelgrenze" | "typ" | "fussnote" |
       "marke" | "neu-uebersetzen" | "ki-ersetzen" | "ki-neu-mit-hinweis",
  parameter, vorher: { hash, ausschnitt }, nachher, hinweis, erstellt, geraet,
  status: "offen" | "gesendet" | "bestaetigt" | "angewendet" | "abgelehnt" | "konflikt" }
```

- **Verankerung am Text, nicht an Zeilennummern**, mit `vorher`-Prüfsumme. Beim Einarbeiten gilt: Stimmt `vorher`
  nicht mehr, wird nicht geschrieben, sondern ein **Konflikt** gemeldet.
- Rücknahme eines Eintrags ist möglich, solange er nicht `angewendet` ist.
- **Einträge dürfen aufeinander aufbauen.** Mehrere Einträge am selben Absatz werden in der Reihenfolge ihrer
  Entstehung angewendet; das `vorher` des nächsten ist das `nachher` des vorigen. Scheitert einer, werden die von ihm
  abhängigen Einträge als `konflikt` (abhängig) gemeldet, nicht still übersprungen. *(Meine Entscheidung.)*
- **Ebenen und Konflikte.** Eine Korrektur weiter oben in der Kette (z. B. am Original-Chunk mit anschließender
  Neuübersetzung) kann Korrekturen weiter unten (am fertigen Volltext) entwerten, weil deren `vorher` nicht mehr passt. Es
  gibt **keine automatische Rangfolge**: Die App zeigt den Konflikt am betroffenen Absatz mit „Neu anwenden / Verwerfen /
  Bearbeiten“, die Person entscheidet. *(Meine Entscheidung.)*
- **Anwendung der Einträge ist doppelt vorhanden**, in JavaScript (Gerät, Vorschau) und Python (APIC, Einarbeiten,
  Wrapper). Beide werden mit denselben Testfällen gegeneinander geprüft (Paritätstest wie beim Speedreader). *(Meine Entscheidung.)*
- **Markierung** („nur merken“) ist ein normaler Eintrag (`art: "marke"`) mit Kategorie und Freitext.
- Auf dem Gerät in IndexedDB; Ids sind zufällig (12 Hex), damit Geräte zusammenführbar bleiben.

### 5.2 Rückweg zu APIC (Empfänger)

- Neuer kleiner Dienst auf APIC (`tools/redaktion_server.py`, nur Standardbibliothek). Er liefert dieselbe App und
  dieselben Daten aus wie bisher `http.server` (der Ordner `reader\export-epistopheles`) **und** nimmt Änderungen an.
- **Offline-first:** Die App sammelt auf dem Gerät. Sobald APIC erreichbar ist, gehen offene Einträge von selbst hinaus.
  Anzeige: „12 warten“, „alles bei APIC angekommen“, „APIC nicht erreichbar“.
- **Absicherung:** Nur Anfragen aus privaten Netzbereichen, dazu ein gemeinsames Kennwort (Token in
  `hilfsdaten\redaktion\token.txt`, auf Epistopheles einmal eingetragen).
- **Start des Dienstes:** Du startest ihn mit einem Befehl (oder richtest ihn als Autostart auf APIC ein); er läuft nicht
  von selbst. Solange er nicht läuft, **warten die Änderungen auf dem Gerät** und die App versucht es regelmäßig wieder
  (alle 30 Sekunden bei geöffneter App und beim Zurückkehren in den Tab). „Automatisch“ heißt also: kein Zutun der Person
  beim Senden, sobald der Dienst erreichbar ist. *(Meine Entscheidung; löst den scheinbaren Widerspruch.)*
- **Adresse:** Einmal in den Einstellungen der App eintragbar (IP oder Rechnername im Heimnetz) mit „Verbindung testen“.
  Der Empfänger liefert die App selbst aus; über diese Adresse (`http://<APIC>:<Port>/`) gibt es keine
  Cross-Origin-Probleme. Wird die lokal gespeicherte Kopie (`file://`) benutzt, setzt der Dienst die nötigen
  CORS-Header (inkl. der Zusage für Zugriffe auf private Adressen). *(Meine Entscheidung; die Browser-Einschränkungen
  sind beim Bauen am Gerät zu prüfen.)*
- **Rückfall:** „Änderungen als Datei sichern“ in der App erzeugt eine Datei mit den offenen Einträgen, die man von Hand
  zum PC bringen und mit `redaktion_anwenden.py --eingang <Datei>` einlesen kann. Gedacht als Notnagel, falls das
  WLAN-Senden unter ChromeOS nicht wie vorgesehen funktioniert. *(Meine Entscheidung.)*
- Eingehende Einträge landen unverändert in `hilfsdaten\redaktion\eingang\<Buch>\<Gerät>-<Zeit>.json` und gelten als
  `gesendet`. Der Dienst meldet der App je Eintrag den Stand zurück (`bestaetigt` / `angewendet` / `konflikt`).
- Die App muss auch aus einer **lokal gespeicherten Kopie** (`file://`) laufen und trotzdem zu APIC senden
  können (CORS-Header am Dienst).

### 5.3 Aufträge auf APIC (nur auf Wunsch)

- **Neu übersetzen (Chunk):** Ein Eintrag `neu-uebersetzen` startet auf APIC einen dünnen Wrapper
  (`tools/pipeline/chunk-neu-uebersetzen.py`, neu): Er nimmt den **korrigierten Original-Chunk** (nicht die Quelldatei),
  ruft `translate_chunk` auf und schreibt das Ergebnis als **Vorschlag** neben den bisherigen de-Chunk. Nichts wird
  ersetzt. **Quelle des korrigierten Chunks ist das Protokoll:** Der Wrapper nimmt den Chunk von der Platte und
  spielt die noch nicht angewendeten Einträge dieses Chunks im Speicher darauf ab (gleiche Logik wie in 5.1). Dadurch
  braucht „Neu übersetzen“ **kein vorheriges Einarbeiten am PC**. *(Meine Entscheidung.)* Die App zeigt alt / neu; „übernehmen“ ist wieder ein Eintrag, der erst am PC angewendet wird.
- **KI neu erzeugen (Kapitel):** Neues Skript (Vorbild `neu-zusammenfassen.py`), das **ein Kapitel** mit dem Prompt aus
  `taggen.ps1` erzeugt, optional mit Korrekturhinweis, Ergebnis als Vorschlag. Der Tagging-Prompt wird dazu aus dem
  Skript in eine Datei ausgelagert, die beide nutzen, damit es keine zwei Fassungen gibt.
- Aufträge laufen **einzeln nacheinander**, mit Zustand (wartet, läuft, fertig, Fehler) in der App.
- Ist APIC nicht erreichbar, bleibt der Wunsch in der Warteschlange.

### 5.4 Einarbeiten am PC

- `tools/redaktion_anwenden.py`: liest den Eingang, zeigt je Buch **vorab**, was sich ändern würde (Dry-Run ist Standard),
  schreibt erst auf `--ausfuehren`. Vor jedem Schreiben `backup_before_write`. Konflikte bleiben liegen und werden gemeldet.
- **Angewendete Änderungen werden dauerhaft protokolliert** (`reader\…\notizen\redaktion.json`, versioniert und
  synchronisiert) und sind **wiederholbar**. So kann eine neu erzeugte Datei die Korrekturen erneut bekommen.
- **`lektor-zu-episto.py` darf Korrekturen nie still vernichten:** Existiert `redaktion.json`, spielt es sie nach dem
  Neuerzeugen wieder ein oder bricht vorher mit einem klaren Hinweis ab.
- Kein automatisches Einarbeiten. Die Entscheidung trifft die Person am PC (Kommandozeile; Oberfläche später, mit der TUI).
- **Ebene Original-Chunk:** Angewendete Korrekturen schreiben den korrigierten Text in
  `rohdaten\Lektor\<A>\<T>\en\chunk_NNN.md` (bei deutschen Quellen in `de\`), mit Backup, und tragen die Chunk-Nummer samt
  Prüfsumme des ursprünglichen Texts in `rohdaten\Lektor\<A>\<T>\redaktion.json` ein. Die Pipeline darf diese Chunks nicht still
  überschreiben: **`ebook-translate.py` ohne `--resume` bricht ab, wenn `redaktion.json` existiert** (außer mit einem
  ausdrücklichen `--korrekturen-verwerfen`). Mit `--resume` bleiben fertige Chunks ohnehin unangetastet. *(Meine Entscheidung;
  ändert das Verhalten der Pipeline.)*
- **Schutz für alle Bücher:** `lektor-zu-episto.py` überschreibt vorhandene `quelle\*.md` künftig **nur noch mit
  `--ueberschreiben`** (auch bei Büchern ohne `redaktion.json`, auch bei von Hand gepflegten Altbeständen). Gibt es
  `redaktion.json`, werden die Einträge nach dem Neuerzeugen wieder eingespielt. Das Protokoll fängt erst bei der ersten
  Korrektur an; für Altbestände gibt es keine nachträgliche Basis. *(Meine Entscheidung; ändert das Verhalten der Pipeline.)*

### 5.5 Was die App zusätzlich als Daten braucht

Das Paket `reader\export-epistopheles` enthält bereits Rohchunks, übersetzte Chunks, Kapitelgrenzen, bereinigte Kapitel und
Ebooks. Neu: die **KI-Felder je Kapitel** im Redaktionsformat (mit Prüfsumme des Kapiteltexts, damit „veraltet“
erkannt wird), die Kapitel-Fußnotenzuordnung, und der Stand angewendeter Änderungen.

## 6. Entscheidungen

**Von dir getroffen**
- Epistopheles korrigiert selbst, Änderungen fließen später zum PC zurück.
- Der Rückweg läuft **automatisch übers gemeinsame WLAN zu APIC**.
- Schwerpunkt ist Ebook → Original-Chunks.
- Bedienung dort: **Verdachtsstellen vorschlagen und frei markieren können** (A + B kombiniert).
- Neuübersetzung nach einer Korrektur: **du entscheidest jedes Mal selbst**.
- Übersetzungsfehler werden **oben in der Kette** behoben; keine Bearbeitung der Übersetzung selbst.
- Fußnoten: **Hochzahl im Text, Fußnotentext am Ende des Kapitels**.
- Fertiger Volltext: **direkt im Text korrigieren, wahlweise zur Ursache führen**.
- KI-Inhalte: **selbst umformulieren oder mit Korrekturhinweis neu erzeugen lassen**.
- Die technischen Entscheidungen überlässt du mir mit sinnvollen Voreinstellungen.

**Meine Entscheidungen (Voreinstellungen, bitte gegenlesen)**
1. **Bestehende App erweitern, nicht neu anfangen:** `korrektur.html` wird zur Redaktionsansicht; neue gemeinsame Logik in
   `redaktion.js` (reine Funktionen, mit Node testbar: Verdachtserkennung, Protokoll, Verankerung).
2. **Protokoll statt Direktänderung** (siehe 5.1) und **Wiederholbarkeit** nach Neuerzeugung (5.4). Das ist die Antwort
   auf den Befund, dass `lektor-zu-episto.py` den fertigen Text überschreibt.
3. **Empfänger auf APIC in Python mit der Standardbibliothek**, ohne neue Abhängigkeit, mit Token und Netzfilter.
4. **Einarbeiten am PC per Kommandozeile mit Dry-Run**, nicht automatisch.
5. **Kapitelgrenzen im fertigen Volltext werden auf Absatzebene bearbeitet** (Absatz zum Nachbarkapitel schieben,
   Kapitel teilen / zusammenführen), nicht über Zeichenpositionen. Beim Einarbeiten wird `kapitel.json` des Lektors
   entsprechend nachgeführt oder die Korrektur über das Protokoll wieder eingespielt (Entscheidung beim Bauen,
   siehe 8).
6. **Verdachtserkennung regelbasiert, ohne KI**, damit sie schnell ist, auf dem Gerät läuft und erklärbar bleibt.
7. **Aufträge einzeln nacheinander** (Ollama ist ohnehin ausgelastet), kein paralleler Lauf.
8. **Reihenfolge der Umsetzung** (jede Phase einzeln planbar und benutzbar):
   - **P0 Grundlage:** Protokoll, Rückweg (Empfänger), Einarbeiten mit Wiederholbarkeit, Schutz in `lektor-zu-episto.py`.
   - **P1 Chunk-Korrektur** (Schwerpunkt): Verdachtsstellen + freies Markieren auf Original-Chunks, Neu übersetzen.
   - **P2 Fertiger Volltext:** direkte Korrektur, Fußnote zuordnen, „Ursache suchen“.
   - **P3 Struktur:** Gerüst, Grenzen, Typen (Inhaltsverzeichnis, Glossar).
   - **P4 KI-Inhalte:** Bearbeiten, Neu erzeugen mit Hinweis, „veraltet“.
   - **P5 Buch-Übersicht** und Feinschliff.

## 7. Randbedingungen

- Epistopheles: 4 GB RAM, Chrome / ChromeOS, Touch, 960×600 (Querformat) bis 600×960; Bedienelemente mindestens 44 px.
- Pro Buch wird nur das geöffnete Buch im Speicher gehalten (bisheriges Verhalten beibehalten).
- Alles muss ohne Netz funktionieren, Senden und Aufträge ausgenommen.
- Alle Texte der Oberfläche deutsch.
- Keine Fremdbibliotheken in der App (bisherige Linie); auf APIC nur Standardbibliothek plus die schon genutzten Pipeline-Pakete.
- Tests: Verdachtserkennung, Protokoll und Verankerung mit Node-Tests; Empfänger, Einarbeiten und Wrapper mit pytest
  (mit Modell-Aufruf ersetzt durch Attrappen); Oberfläche per Browser-Durchlauf mit echten Daten.

## 8. Dem Bauenden überlassen

- Genaues Format der Verdachtsvorschläge und Schwellenwerte (einstellbar, mit Beispieldaten aus den 84 Büchern abstimmen).
- Technische Umsetzung von „Kapitel teilen / zusammenführen“ inkl. Nummerierung der Dateien `NNNN_*.md` und Kopplung der
  KI-Inhalte (`tags.json` hängt am Dateinamen).
- Ob Kapitelgrenzen am PC in `kapitel.json` des Lektors zurückgeschrieben oder nur über das Protokoll wiederholt werden.
- Wie PDF-Quellen unterstützt werden, bei denen das Ebook keine Textsuche zulässt (heute nur Seitensprung).
- Gestaltung der Bildschirme im Einzelnen. Vorgabe sind die Bedienkonzepte **A (Hinweise an den Zeilen) + B (frei markieren,
  Werkzeugleiste)** aus `dok/2026-11-02-redaktion-mockups-chunk-bearbeiten.html` (nur Skizzen zur Orientierung, keine fertige
  Gestaltung), Touch-tauglich.
- Name und Aufbau der Dateien im Eingangsordner, solange das Format von 5.1 gilt.
