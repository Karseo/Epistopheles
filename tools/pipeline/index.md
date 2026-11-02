# eBook-Toolchain

Werkzeuge, um fremdsprachige eBooks lokal ins Deutsche zu übersetzen und daraus
einen strukturierten Obsidian-Vault (Kapitel, Register, Glossar, WikiLinks) zu bauen.
Alles läuft **offline** über Ollama — keine Cloud, keine API-Kosten.

## Überblick

| Schritt | Skript | Eingabe → Ausgabe |
|---|---|---|
| 1. Übersetzen | `ebook-translate.py` | `Inbox\*` → `de\chunk_*.md` **und** `en\chunk_*.md` in `Lektor\<Autor>\<Titel>\` |
| 2a. Tags vorschlagen | `suggest-tags.py` | Chunks → `chunk_NNN.tagged.md` mit `%%tag%%`-Vorschlägen |
| 2b. Korrektur | *(manuell)* | Chunks durchsehen, Tags bestätigen, `==Hervorhebungen==` setzen |
| 2c. Tags einsammeln | `collect-tags.py` | getaggte Absätze → `notizen\tags.md` + Entwurf im Karton-Format |
| 2d. Hervorhebungen einsammeln | `collect-marks.py` | `==…==` → `notizen\hervorhebungen.md` |
| 3. Gesamttext | `ebook-build.py` | korrigierte Chunks → `Outbox\<Autor> - <Titel>_de.md` und `_en.md` |
| (optional) | `build-vault.ps1` | `chunk_*.md` → Obsidian-Vault (MOC, Register, Glossar, Notizen) |
| (vorab) | `check-source.py` | prüft eine Quelldatei gegen den Bestand: Dublette? besseres Format? |
| (vorab) | `detect-chapters.py` | rekonstruiert die Kapitelstruktur → `kapitel.json` |
| (vorab, bei Bedarf) | `suggest-structure.py` | wenn Anker/Überschriften nichts liefern: Kapitelgrenzen per lokalem LLM |
| (vorab) | `check-metadata.py` | prüft Chunks auf InDesign-/Pandoc-Metadatenreste, schlägt Umgang vor |
| (optional) | `build-chapters.py` | `kapitel.json` + Chunks → je Kapitel eine eigene Markdown-Datei |
| (Hilfsmittel) | `isbn_rename.py` | benennt eBook-Dateien anhand ISBN-Metadaten um |
| (Wartung) | `fix-chunks.py` | findet defekte Chunks, gibt sie mit `--repair` zur Neuübersetzung frei |
| (Wartung) | `repair-meta.py` | rekonstruiert fehlende `meta.json` |
| (Wartung) | `extract-footnotes.py` | zieht Fußnotentexte aus dem Quell-EPUB nach, in beide Sprachordner |
| (einmalig) | `migrate-lektor.py` | hebt Bücher vom alten flachen Schema auf `de\` + `en\` |

Alle Schritte laufen unterhalb des Ordners, in dem die Skripte liegen (`D:\Workspace\!Episto\rohdaten\`;
überschreibbar per Env `EBOOK_BASE`):

```
Inbox\                          zu übersetzende Quelldateien
Lektor\<Nachname, Vornamen>\<Titel>\
    de\chunk_NNN.md             deutsche Fassung
    de\<...>_de.epub            deutsches eBook (nur mit --epub)
    de\footnotes.md             gerettete Fußnotentexte (s. extract-footnotes.py)
    en\chunk_NNN.md             englische Fassung
    en\<Quelldatei>             das eBook liegt bei den Chunks seiner Sprache
    en\footnotes.md             dieselben Fußnotentexte, fürs englische Kapitelbauen
    notizen\tags.md             getaggte Absätze, nach Funktion gruppiert
    notizen\tags.json           dieselben Daten maschinenlesbar
    notizen\hervorhebungen.md   markierte Stellen mit offener Frage
    kapitel.json                 Kapitelstruktur (s. detect-chapters.py)
    hinweise-fussnoten.txt        Fußnoten-Konvention laut LLM (nur bei suggest-structure.py)
    Kapitel\<lang>\NN - Titel.md je Kapitel eine Datei (s. build-chapters.py)
    meta.json .progress.json media\
Outbox\                         Markdown-Gesamttexte je Sprache
```

**Autorordner** tragen die Sortierform `Nachname, Vornamen` (`Horton, Scott`,
`Henry, William A. III`). Sie wird aus dem Dublin-Core-Feld `opf:file-as`
übernommen, wenn vorhanden, sonst aus dem Creator-Feld umgestellt.

**Die Quelldatei liegt bei den Chunks ihrer Sprache** — ein englisches Original
also in `en\`, ein deutsches in `de\`. Ist die Quelle weder deutsch noch
englisch, liegt sie im Buchordner selbst, da sie zu keiner der beiden Fassungen
gehört. Mit `--epub` erzeugte eBooks landen ebenfalls im jeweiligen
Sprachordner, nicht in der Outbox.

## Zweisprachigkeit

Die Bibliothek ist grundsätzlich **zweisprachig (de + en)**:

| Quellsprache | `de\` | `en\` | Original |
|---|---|---|---|
| Englisch | Übersetzung | Quelltext übernommen | — |
| Deutsch | Quelltext übernommen | Übersetzung | — |
| sonstige | Übersetzung | Übersetzung | bleibt **nur als Datei** erhalten, nicht als Chunks |

Bei nicht-englischer Quelle laufen also zwei Übersetzungen — entsprechend doppelte
Laufzeit. `aya-expanse:32b` ist multilingual (23 Sprachen inkl. Deutsch) und
beherrscht beide Richtungen.

Getaggt und redigiert wird die **deutsche** Fassung — sie wird ohnehin gelesen.
Die englische dient als Rückfallebene: Bei Zweifeln an einer Formulierung liegt
unter derselben Chunk-Nummer der Originaltext bereit, `collect-marks.py`
verweist bei jeder Markierung darauf.

Die Schritte sind entkoppelt. Schritt 1 baut **kein** EPUB mehr — dazwischen liegt
bewusst die Korrekturphase.

**Der vollständige deutsche Markdown-Text** (`Outbox\*.md`) ist der erste Schritt
der Weiterverarbeitung — und beim Quellenstudium der letzte, auf den man zurückgeht.
Die eigentliche Hauptquelle für das LLM entsteht in Schritt 2: die beim
Korrekturlesen getaggten Absätze (`notizen\tags.md`) und die markierten Stellen
(`notizen\hervorhebungen.md`). Das EPUB ist Kosmetik und entsteht nur mit `--epub`.

Der Weg dorthin ist bewusst so gewählt, dass die **Auswahl vom Menschen kommt**:
Das Modell schlägt Tags vor, bestätigt wird beim Lesen. Damit entfällt die
Halluzinationsprüfung — der getaggte Absatz ist der Beleg, mit Chunk-Nummer und
Original-Seitenzahl.

**Ordnerschema:** Autor und Titel kommen aus den Metadaten der Quelldatei
(EPUB Dublin Core, PDF Info-Dictionary). Sind beide eindeutig identifizierbar und
zusammen ≤ 110 Zeichen, wird `Lektor\<Autor>\<Titel>\` verwendet — sonst Fallback
auf `Lektor\<Dateiname>\`. Die Entscheidung wird beim Start ausgegeben und in
`meta.json` unter `ordner_grund` festgehalten.

## Voraussetzungen (einmalig)

- **Ollama** läuft (`http://localhost:11434`) mit dem Modell **`aya-expanse:32b`**
  (`ollama pull aya-expanse:32b`).
- **Pandoc** im PATH — <https://pandoc.org/>
- Python-Pakete: `pip install ebooklib pypdf beautifulsoup4 lxml html2text requests`
- PowerShell 5.1+ (für den optionalen Vault-Schritt).

---

## Schritt 0 — Quelle prüfen (`check-source.py`)

Vor dem Einlesen: Gibt es das Buch schon? Und ist die neue Datei die bessere
Quelle?

```powershell
python check-source.py "buch.epub"        # eine Datei
python check-source.py --inbox            # alles in Inbox\
python check-source.py --inbox --kurz     # eine Zeile je Datei
python check-source.py "buch.epub" --sha  # zusätzlich Dateien vergleichen
```

Identität wird in dieser Reihenfolge geprüft: **ISBN** (aus Metadaten oder
Dateiname), dann **Autor + Titel** normalisiert, dann der **Dateiname**. Mit
`--sha` zusätzlich der SHA-256 der Dateien.

### Formatregel: nicht-EPUB wird durch EPUB ersetzt

Liegt dasselbe Buch bereits in schlechterem Format vor, empfiehlt das Werkzeug
den Austausch. Der Rang der Formate:

| Rang | Formate | warum |
|---|---|---|
| 3 | EPUB, FB2, ODT, DOCX, HTML | tragen Struktur, Metadaten, Fußnoten |
| 2 | MOBI, AZW3, LIT, PRC | werden über Calibre nach EPUB konvertiert |
| 1 | PDF | nur Text-Extraktion, verliert Struktur |

Der Unterschied ist erheblich, gemessen an *The Prophets of Doom*:

| | PDF | EPUB |
|---|---|---|
| extrahierte Zeichen | 494.239 | **656.426** |
| Chunks | 69 | 89 |
| Kapitelmarken | keine (131 Falschtreffer, verworfen) | vorhanden |
| Fußnoten | keine | vorhanden |
| Metadaten | fehlten, Fallback auf Dateinamen | vollständig |

Ein Drittel des Textes fehlte im PDF-Konvertat. Beim Ersetzen den alten Ordner
mit einem Zusatz umbenennen (`… (pdf-ersetzt)`), nicht löschen — dann lässt
sich das Ergebnis vergleichen.

**Ausnahme:** Ist das vorhandene Buch bereits getaggt, wiegt der Verlust der
Redigierarbeit schwerer als der Formatgewinn. Das Werkzeug meldet dann
`VERWERFEN`.

---

## Schritt 1 — Übersetzen (`ebook-translate.py`)

Übersetzt ein Buch chunk-weise (8000 Zeichen) via `aya-expanse:32b`.
Die Eingabe darf ein voller Pfad oder nur ein Dateiname sein — letzterer wird in
`Inbox\` gesucht (und, für `--resume`, auch unterhalb von `Lektor\`).

```powershell
python ebook-translate.py "Barclay-Fake News.epub"
python ebook-translate.py "C:\pfad\input.pdf" --source-lang en
python ebook-translate.py "Barclay-Fake News.epub" --resume       # Chunks überspringen
python ebook-translate.py "Barclay-Fake News.epub" --dry-run      # nur Extraktion zeigen
python ebook-translate.py "Barclay-Fake News.epub" --keep-source  # Quelldatei nicht verschieben
```

**Ausgabe** in `Lektor\<Autor>\<Titel>\`:

| Datei | Inhalt |
|---|---|
| `de\chunk_NNN.md`, `en\chunk_NNN.md` | die Abschnitte je Sprache — **hier wird korrigiert** |
| `.progress.json` | Fortschritt **je Sprache** → jederzeit `--resume` |
| `meta.json` | Autor, Titel, Jahr, Quelle, Modell, Status — Schnittstelle zu Schritt 3 |
| `media\` | Bilder aus der Quelldatei (Pandoc extrahiert sie nicht selbst) |

`meta.json` und `media\` werden **sofort beim Start** angelegt, nicht erst am Ende —
so sind sie auch nach einem Abbruch vorhanden. Das Feld `status` steht während des
Laufs auf `in_arbeit` und danach auf `fertig` bzw. `unvollstaendig`.

**Formate:** EPUB, ODT, DOCX, HTML, RTF, FB2 und Markdown liest Pandoc direkt, PDF
läuft über einen pypdf-Fallback. MOBI, AZW3, LIT und Verwandte werden automatisch
per Calibre `ebook-convert` nach EPUB konvertiert (das konvertierte EPUB landet
neben dem Original und liefert zugleich die besseren Metadaten).

Nach vollständiger Übersetzung wird die Quelldatei in den Ordner ihrer Sprache
verschoben (`en\` bei englischem Original), abschaltbar mit `--keep-source`.
Das Verschieben geschieht bewusst erst am Ende — vorher braucht `--resume` die
Datei noch.

**Es entsteht kein EPUB.** Das ist Schritt 3.

---

## Schritt 2 — Korrektur und Erschließung

Der Durchgang durch die deutschen Chunks findet ohnehin statt. Er wird hier
zugleich zur Erschließung genutzt: Tags klassifizieren Absätze nach ihrer
Funktion, Hervorhebungen markieren Stellen mit offener Frage. Beides ist
Vorarbeit für die Kernthesen (Bücherkarton-Spec, Abschnitt 4).

**Reihenfolge beachten:** Erst muss das Qualitäts-Gate für das Buch sauber sein
(`fix-chunks.py`). Ein späterer `--repair`-Lauf überschreibt Chunks — gesetzte
Tags und Hervorhebungen wären verloren.

```powershell
python ebook-build.py "<Titel>" --check      # Stand prüfen
python fix-chunks.py "<Autor>\<Titel>"       # Defekte finden
python check-metadata.py "<Autor>\<Titel>"   # Metadatenreste im Rohtext pruefen
```

### Metadaten prüfen (`check-metadata.py`)

```powershell
python check-metadata.py                                    # alle Buecher, de+en
python check-metadata.py "<Autor>\<Titel>"
python check-metadata.py "<Autor>\<Titel>" --sprache de
python check-metadata.py "<Autor>\<Titel>" --beispiele 5
python check-metadata.py "<Autor>\<Titel>" --normalize-footnotes
```

InDesign-EPUBs hinterlassen in den Chunks Reste, die weder Fehler noch Fließtext
sind — ärgerlich werden sie erst, wenn ausgerechnet der zitierte Beleg mittendrin
steckt. `collect-tags.py` übernimmt den Absatz wörtlich ("der Absatz ist der
Beleg, keine Paraphrase"); eine solche Klammerkette macht daraus kein brauchbares
Zitat mehr. Beispiel aus `Parvini, Neema\The Populist Delusion\de\chunk_003.md`:

```
[[[2](#02_-_The_Rulers_and_the_Ruled.xhtml_footnote-046){._idFootnoteLink
._idGenColorInherit}]{#02_-_The_Rulers_and_the_Ruled.xhtml_footnote-046-backlink}]
{.CharOverride-2}
```

`check-metadata.py` meldet je Buch zwei Kategorien und schlägt dazu den Umgang vor:

| Kategorie | Beispiel | Vorschlag |
|---|---|---|
| `fussnoten` | die Klammerkette oben | kein Fehler — `ebook-build.py` kürzt sie beim Bauen ohnehin zu `[^Kapitel-Nr]` (`--footnotes`/`--clean`). Stört aber jedes Zitat, solange nicht gebaut wurde. Fehlt `<lang>\footnotes.md` noch, zuerst `extract-footnotes.py` laufen lassen; danach optional mit `--normalize-footnotes` direkt in den Chunks auf die kurze Form kürzen |
| `zeichenformat` | `[offensichtlich]{.CharOverride-1}`, `[Provoked]{.class_sdk}` | verlorene Zeichenauszeichnung der Quelle (meist kursiv, fett, Kapitälchen) oder ein Register-/Verweiselement — keine automatische Korrektur; an den Beispielen reicht meist ein Blick, ob Fließtext oder Apparat betroffen ist |

Reine Anker ohne sichtbaren Text (Kapitelmarken, Seitenzahlen, Calibre- und
Index-Anker) werden bewusst nicht gemeldet — sie sind der Grund, warum die
Chunks laut Konzept roh bleiben, und tauchen in einem zitierten Absatz ohnehin
nicht auf.

### 2a. Tags vorschlagen (`suggest-tags.py`)

```powershell
python suggest-tags.py "<Autor>\<Titel>" --limit 5     # erst kalibrieren
python suggest-tags.py "<Autor>\<Titel>" --resume
python suggest-tags.py "<Autor>\<Titel>" --in-place    # direkt in die Chunks
python suggest-tags.py "<Pfad>\de\chunk_034.md"        # einzelne Datei
```

Ein Modellaufruf je Chunk (nicht je Absatz) bewertet alle Absätze zugleich und
setzt Vorschläge als Obsidian-Kommentar in eigener Zeile über den Absatz:

```
%%these peripherie-mechanismus%%
::: para
Jenseits der Kern- und Semi-Peripherie-Länder …
:::
```

Vokabular — bewusst klein, damit es beim Lesen im Kopf bleibt:

| Tag | Bedeutung |
|---|---|
| `these` | Kernbehauptung, die der Autor belegen will |
| `beleg` | Daten, Studie, Quelle, die eine These stützt |
| `gegen` | Position, die der Autor bestreitet oder referiert |
| `def` | Begriffsbestimmung — Kandidat fürs Karton-Glossar |
| `kern` | Schlüsselstelle |
| `frag` | zweifelhaft, nachprüfen |

Höchstens zwei Tags je Absatz; das Stichwort dahinter (`%%these vermoegen%%`)
erlaubt später, gleiche Themen über mehrere Bücher zusammenzuziehen. Umlaute
werden zu `ae/oe/ue` aufgelöst, damit Stichworte in Dateinamen taugen.

Standardmäßig entsteht `chunk_NNN.tagged.md` neben dem Original; das Original
bleibt unangetastet. `--in-place` schreibt direkt.

**Modellwahl:** `qwen3.8:27b` (Standard) trifft dieselben Stellen wie
`qwen3.6:27b`, braucht aber ein Drittel der Zeit — rund 20 s je Chunk.
`qwen3:8b` ist ungeeignet: es markiert fast jeden Absatz und entwertet damit
die Auswahl. Für den Gesamtbestand sind etwa zehn Stunden zu veranschlagen,
also ein Lauf über Nacht.

### 2b. Korrekturlesen

Tags bestätigen, ändern oder löschen — die Auswahl bleibt beim Menschen, das
Modell hat nur die mechanische Vorarbeit gemacht. Dabei zusätzlich
`==Hervorhebungen==` setzen: kommentarlose Markierungen für Stellen, bei denen
später nachgefragt werden soll. Sie halten fest, **dass** etwas zu klären ist,
nicht was.

Pandoc erkennt `==…==` über Zeilenumbrüche hinweg, **nicht** über
Absatzgrenzen. Mehrere Absätze deshalb einzeln markieren — `collect-marks.py`
fügt sie wieder zusammen.

### 2c. Tags einsammeln (`collect-tags.py`)

```powershell
python collect-tags.py "<Autor>\<Titel>"
python collect-tags.py "<Autor>\<Titel>" --zusammenfassung
python collect-tags.py --alle --dry-run
```

Erzeugt in `notizen\`:

| Datei | Inhalt |
|---|---|
| `tags.md` | nach Funktion gruppiert, mit Stichwort, Chunk und Original-Seitenzahl |
| `tags.json` | dieselben Daten maschinenlesbar — Grundlage für den Karton-Bau |
| `_Zusammenfassung_Entwurf.md` | mit `--zusammenfassung`: Karton-Format (Spec Abschnitt 4) |

Der Absatz steht vollständig in `tags.md` — er **ist** der Beleg, keine
Paraphrase. Der Entwurf nennt bewusst nur die Fundstellen und formuliert nichts
aus; das geschieht im Dialog.

### 2d. Hervorhebungen einsammeln (`collect-marks.py`)

```powershell
python collect-marks.py "<Autor>\<Titel>"
python collect-marks.py "<Autor>\<Titel>" --suggest    # Frage vom Modell
python collect-marks.py --alle --dry-run
```

Sammelt die `==…==` nach `notizen\hervorhebungen.md`, je Markierung mit Chunk,
Original-Seitenzahl, umgebendem Absatz und Verweis auf dieselbe Stelle in der
anderen Sprachfassung — bei Übersetzungszweifeln die schnellste Klärung.

Mit `--suggest` erschließt das Modell Kategorie (`begriff`, `behauptung`,
`fakt`, `verweis`, `sprache`) und formuliert eine Frage. Ohne das Flag bleibt
das Feld offen.

**Antworten gehören in die Begleitdatei, nie in die Quelle** — Rohquellen
bleiben unantastbar.

### Kapitelzuordnung (`detect-chapters.py`)

```powershell
python detect-chapters.py "<Autor>\<Titel>"
python detect-chapters.py --alle
python detect-chapters.py --alle --dry-run
```

Pandoc setzt beim Zusammenführen der EPUB-Kapiteldateien Anker der Form
`[]{#02_-_The_Rulers_and_the_Ruled.xhtml}` — dort, wo das Kapitel beginnt,
auch **mitten in einem Chunk**. Markdown-Überschriften (`##`) fehlen dagegen
bei vielen Büchern; wer nur danach sucht, hält die Gliederung fälschlich für
nicht vorhanden.

Ergebnis ist `kapitel.json` im Buchordner: Kapitelliste und je Chunk die
Zuordnung (welches Kapitel am Anfang gilt, welche mittendrin beginnen und an
welcher Position). `collect-tags.py` und `collect-marks.py` lesen sie und
weisen jede Fundstelle als **Kapitel · Chunk · Seite** aus — mit korrekter
Zuordnung auch dort, wo die Kapitelgrenze mitten im Chunk liegt.

**Zweites Merkmal — calibre-Konvertierungen ohne sprechenden Anker:** manche
Verlage tragen im Anker selbst nur einen technischen Dateinamen
(`part0005.html`), Kapitelnummer und -titel stehen stattdessen in der
Überschrift direkt danach:

```
[]{#part0005.html}

# [2: Giambattista Vico]{.italic1} {#part0005.html_toc_marker-2-2 .level}
```

Gefunden an *The Prophets of Doom*, `de\chunk_010.md`: der Anker allein hätte
nur „part0005" als Titel hergegeben. Die Anker-ID vor `_toc_marker` verweist
auf denselben Anker; ob die Überschrift ein `N: Titel`-Muster trägt,
unterscheidet echte Kapitel von Titelei/Anhang zuverlässiger als Level oder
Dateiname — beide vergeben Verlage gelegentlich auch an die Titelseite. Fehlt
selbst die Überschrift (Titelseite, Impressum ohne eigenen Text), greift als
letzter Versuch das gedruckte Inhaltsverzeichnis des Buchs, das jeden Anker
mit lesbarem Titel verlinkt. Fortsetzungsseiten derselben Datei
(`_split_001`, `_split_002`, … bei mehrseitigen Registern/Bibliografien)
zählen nicht als eigene Kapitelgrenze.

**Plausibilitätsgrenze:** Fehlen Anker, greift der Überschriften-Fallback —
aber nur, wenn höchstens ein Kapitel auf zwei Chunks kommt (`--max-anteil`,
Standard 0.5). Bei PDF-Konvertaten interpretiert Pandoc regelmäßig Marginalien
als Überschriften: *The State Nobility* lieferte 329 „Kapitel" bei 214 Chunks.
Solche Ergebnisse werden mit Begründung verworfen, statt unbrauchbare Daten zu
schreiben. Von 13 Büchern haben 10 eine verwertbare Struktur.

`kapitel.json` trägt neben `kapitel`/`chunk_zuordnung` (fürs Zitieren, s.o.)
zusätzlich `segmente`: die vollständige, geordnete Liste aller Marken
einschließlich Titelei/Anhang mit Position — Grundlage für
`build-chapters.py`.

### Wenn nichts davon greift — LLM-Kapitelerkennung (`suggest-structure.py`)

```powershell
python suggest-structure.py "Schumpeter, Joseph A\Capitalism, Socialism and Democracy"
python suggest-structure.py "<Autor>\<Titel>" --sprache en
python suggest-structure.py "<Buch>" --dry-run
python suggest-structure.py --alle
```

Anker und Überschriften-Fallback setzen voraus, dass der Konverter eines von
beiden erzeugt hat — bei manchen Quellen (vor allem PDF-Konvertate ohne
editorische Struktur) liefert keins von beidem etwas Brauchbares. Jedes
Verlagsschema von Hand nachzubauen skaliert nicht auf eine wachsende
Bibliothek — genau dafür ist dieses Skript da: für **genau die Bücher**, bei
denen `detect-chapters.py` nichts oder Unplausibles findet, übernimmt das
lokale Modell (`qwen3.8:27b`, wie `suggest-tags.py`) die Mustererkennung.

**Erster Ansatz, verworfen:** das Modell chunkweise fragen, ob genau hier
eine Gliederungsgrenze beginnt. Live getestet an *Capitalism, Socialism and
Democracy* (175 Chunks, ~85 echte Kapitelmarken laut Inhaltsverzeichnis):
nur 5 gefunden, mit erfundenen Nummern für die ersten beiden Kapitel,
riesige unentdeckte Lücken. Isoliert je Chunk gefragt ist die Trefferquote
auf einem dicht gegliederten Buch zu niedrig — das Modell übersieht die
meisten Grenzen, statt bei Unsicherheit lieber zu viele zu melden.

**Zweiter Ansatz, aktuell:** nicht raten lassen, wo eine Grenze ist, sondern
auswerten, was jedes Buch bereits selbst verrät — das gedruckte
Inhaltsverzeichnis. Das Modell liest nur den Buchanfang (`--toc-chunks`,
Standard 6 Chunks / `--toc-max-chars`, Standard 12000 Zeichen — dort steht
das Inhaltsverzeichnis) und extrahiert daraus die vollständige Liste der
Gliederungspunkte der **obersten Ebene** (Nummer/Titel/Art; tiefer
verschachtelte, neu bei I. beginnende Unterabschnitte werden übersprungen,
und Teile bekommen als Titel nur "Teil `<Nummer>`" ohne Untertitel — der
wird im Fließtext oft anders formuliert). Die eigentliche Platzierung im
Buch übernimmt danach reine Textsuche, kein LLM mehr: jeder Titel wird ab
dem Ende des TOC-Textfensters gesucht, groß-/kleinschreibungs- und
leerraumtolerant, aber nur als **zeilenisolierter** Treffer akzeptiert —
Pandoc-Anker auf derselben Zeile zählen nicht mit, ein Kolumnentitel
(Kapitelname, den manche PDF-Konvertate als Fragment mitten in einen Satz
streuen) dagegen schon, das würde sonst mitten im Fließtext zuschlagen. Ein
Titel, der im Fließtext nirgends isoliert vorkommt, gilt als nicht
gefunden — es wird nichts geraten, kein Fallback auf den ersten
Fließtext-Treffer: genau der hätte bei diesem Buch einen falschen Treffer
als sicheren Fund ausgegeben (Inhaltsverzeichnis nennt Kapitel XV
„Vorbereitung", die echte Überschrift lautet „VORBEREITENDE MASSNAHMEN" —
„Vorbereitung" kommt sonst nur beiläufig in normalem Fließtext vor).

Das Ergebnis durchläuft danach dieselbe Zusammenbau-Funktion aus
`detect-chapters.py` wie Anker und Überschriften-Fallback — `kapitel.json`
ist ununterscheidbar von einem anker-basierten Lauf, nur `quelle` steht auf
`"llm-toc"`. Zwei Qualitätsgrenzen schützen vor einem zu lückenhaften oder
zu üppigen Ergebnis: `--min-recall` (Standard 0.5 — so viel Anteil der
Inhaltsverzeichnis-Einträge muss im Fließtext wiedergefunden werden, sonst
verworfen) und `--max-anteil` (Standard 0.5, wie beim Überschriften-Fallback
— Obergrenze gegen ein missratenes/zu langes Inhaltsverzeichnis). Beim
Testlauf an *Capitalism, Socialism and Democracy* wurden so 11 von 16
Einträgen wiedergefunden (69 %) — die restlichen 5 unterscheiden sich im
Wortlaut zwischen Inhaltsverzeichnis und Fließtext (z.B. „Vorwort zur
ersten Auflage" vs. eine andere Formulierung im Text selbst) und wurden zu
Recht als nicht gefunden gemeldet statt geraten. `--alle` überspringt
Bücher, die bereits eine brauchbare Struktur haben (`--force` erzwingt
trotzdem eine LLM-Erkennung, zum Vergleich).

**Fußnoten/Querverweise:** `build-chapters.py`s Querverweis-Logik ist bereits
konventionsunabhängig (löst Markdown-Links generisch über Anker-IDs auf) und
braucht kein LLM. Für die Fußnoten-*Definition* dagegen kennt das Skript
bisher nur zwei Konventionen (InDesign, calibre, s.o.) — eine dritte,
unbekannte würde stillschweigend falsch behandelt. Darum legt
`suggest-structure.py` dem Modell zusätzlich eine Textprobe vor und lässt es
in eigenen Worten beschreiben, wie Fußnoten dort markiert sind. Das ist reine
Diagnose in `hinweise-fussnoten.txt` — nichts wird deswegen automatisch
geändert. Weicht die Beschreibung von den beiden bekannten Konventionen ab,
verdient das denselben Blick, den die beiden anderen beim Einbau bekommen
haben, nicht eine vom Modell selbst erfundene Regel.

### Original-Seitenzahlen

Die Chunks enthalten Anker der Form `page_97`. Beide Einsammel-Skripte ziehen
daraus die Seitenzahl der Fundstelle: Steht ein Anker im Absatz selbst, gilt
dessen Seite, sonst die letzte davor. Damit ist jeder Beleg seitengenau
zitierbar, ohne ins EPUB zurückzugehen.

---

## Schritt 3 — Gesamttext bauen (`ebook-build.py`)

Fügt die Chunks zu **einem** Markdown-Dokument zusammen — das ist das
eigentliche Ergebnis der Kette.

```powershell
python ebook-build.py "Fake News"                      # Suche unterhalb Lektor\
python ebook-build.py "Scott Horton\Provoked"          # eindeutiger
python ebook-build.py "Provoked" --sprache de          # nur deutsche Fassung
python ebook-build.py "Provoked" --epub                # zusätzlich EPUB
python ebook-build.py "Provoked" --clean               # glatter Lesetext
python ebook-build.py "Provoked" --check               # nur prüfen
python ebook-build.py "Provoked" --force               # trotz Problemen bauen
```

| Option | Wirkung |
|---|---|
| `--sprache` | `de`, `en` oder `beide` (Standard) |
| `--epub` | baut zusätzlich ein EPUB (braucht Pandoc) |
| `--clean` | Konvertierungsreste entfernen — nur wenn ein glatter Lesetext gebraucht wird |
| `--check` | nur Vollständigkeitsprüfung, schreibt nichts |
| `--force` | baut trotz gemeldeter Probleme |
| `--no-cover` | kein Cover ins EPUB einbetten |
| `--output` | abweichender Zielpfad für das Markdown (nur mit `--sprache de` oder `en`) |

Die Markdown-Gesamttexte gehen in die `Outbox\`, die mit `--epub` erzeugten
eBooks dagegen in den jeweiligen Sprachordner des Buchs.

Ohne `--sprache` werden beide Fassungen gebaut. Die Vollständigkeitsprüfung läuft
je Sprache; schlägt sie für eine an, wird nur diese übersprungen. Die
Sprachheuristik prüft passend zur Zielsprache — in `en\` gilt englischer Text als
korrekt, nicht als unübersetzt.

Das Markdown trägt **YAML-Frontmatter** (Titel, Autor, Jahr, Quellsprache,
Übersetzungsmodell, Chunk-/Zeichen-/Wortzahl, `roh`) und bleibt standardmäßig
**roh**: Anker, Div-Marker und Attribut-Suffixe der Quelle bleiben stehen, weil
sie bei der Analyse der Textstruktur helfen. `--clean` entfernt sie (Calibre-Anker,
SVG-Titelblöcke, Fußnoten-Reste, `{.unnumbered}`) und setzt Leerzeilen vor
Überschriften CommonMark-konform — für den glatten Lesetext.
Ausgabe als UTF-8 ohne BOM mit LF-Zeilenenden; Zeichen-, Wort- und grobe
Tokenzahl werden beim Bauen angezeigt.

Ohne `--force` bricht der Build bei Lücken ab. Cover und Bilder kommen aus
`media\`; Verweise auf fehlende Bilddateien werden entfernt, statt Pandoc
scheitern zu lassen.

---

## Kapitel-Dateien bauen (`build-chapters.py`)

```powershell
python build-chapters.py "Parvini, Neema\The Prophets of Doom"
python build-chapters.py "<Autor>\<Titel>" --sprache de
python build-chapters.py "<Autor>\<Titel>" --clean
python build-chapters.py --alle
```

Alternative zu Schritt 3 für Bücher, bei denen ein einzelnes Kapitel gebraucht
wird statt des ganzen Buchs — einer KI vorgelegt, allein gelesen, verschickt.
Voraussetzung ist `kapitel.json` (`detect-chapters.py`). Geschnitten wird am
Rohtext jedes Chunks, an der dort gespeicherten Zeichenposition — nicht an
der Chunkgrenze, die mechanisch bei 8000 Zeichen liegt und oft mitten in ein
Kapitel fällt. Ausgabe: `<Buch>\Kapitel\<lang>\NN - Titel.md`, je Segment
eine Datei (Kapitel wie Titelei/Anhang), `--clean` entfernt wie in
`ebook-build.py` die Konvertierungsreste.

**Fußnoten wandern mit ihrem Kapitel:**

| Quellenkonvention | Beispiel | Verfahren |
|---|---|---|
| Fußnotentext im EPUB verloren (InDesign) | *The Populist Delusion* | Referenz wird zu `[^Kap-Nr]` gekürzt; existiert `<lang>\footnotes.md` (`extract-footnotes.py`), werden nur die im jeweiligen Kapitel tatsächlich referenzierten Definitionen als eigener Abschnitt „## Fußnoten" ans Kapitelende gehängt |
| Fußnotentext bleibt im Fließtext (calibre) | *The Prophets of Doom* | kein footnotes.md nötig — der Text steht im Quelltext vor der nächsten Kapitelüberschrift und wird darum automatisch mit dem vorigen Kapitel geschnitten |

Referenzierte Fußnoten ohne auffindbare Definition meldet das Skript, statt
sie stillschweigend zu verlieren.

**Andere Querverweise:** interne Links, deren Ziel nach dem Schneiden nicht
mehr im selben Segment liegt (z.B. ein Registereintrag, der auf ein anderes
Kapitel zeigt), werden zu reinem Text — ein Link ins Leere ist schlimmer als
gar keiner. Ist das Zielkapitel ermittelbar, steht es in Klammern dabei:
`Aran, R. 56 (→ Kapitel 4)`.

---

## Optional — Vault bauen (`build-vault.ps1`)

Baut aus den übersetzten Chunks einen kompletten Obsidian-Vault:
Chunks kopieren → Kapitel aus `##`-Überschriften → Kapitel-Anker-Notizen →
`MOC.md` (Inhaltsverzeichnis) + `Ueber das Buch.md` → `Register.md` (alphabetisch) →
Glossar-Notizen → Calibre-Anker säubern → Fußnoten/TOC/WikiLinks reparieren.

```powershell
.\build-vault.ps1 -SourceDir "D:\Workspace\!Episto\rohdaten\Lektor\Scott Horton\Provoked" `
                  -VaultPath "D:\Obsidian\LokalVault\Provoked" `
                  -Buch "Provoked" -Autor "Scott Horton" -Jahr 2024 `
                  -Untertitel "How Washington Started the New Cold War..."
```

**Parameter:**

| Parameter | Pflicht | Bedeutung |
|---|---|---|
| `-SourceDir` | ja | Ordner mit `chunk_*.md` (Ausgabe aus Schritt 1) |
| `-VaultPath` | ja | Ziel-Vault-Ordner (wird angelegt) |
| `-Buch` | ja | Buchtitel |
| `-Autor` | – | Autor (Default `Unbekannt`) |
| `-Untertitel` | – | optionaler Untertitel/Volltitel |
| `-Jahr` | – | Erscheinungsjahr |
| `-Sprache` | – | Sprachvermerk für Metadaten |
| `-ErstesKapitel` | – | Kapitelname für Chunks vor der 1. Überschrift (Default „Vorwort und Einleitung") |
| `-MinGlossar` | – | Mindest-Vorkommen für eine eigene Glossar-Notiz (Default 3) |

**Erzeugte Vault-Struktur:**
```
<VaultPath>\
  MOC.md                 Inhaltsverzeichnis mit Kapitel-Navigation
  Register.md            alphabetisches Register aller Begriffe
  Ueber das Buch.md      Metadaten-Tabelle
  Notizen\
    chunk_000.md …       Text-Chunks (mit WikiLinks)
    Kapitel: <Name>.md   Kapitel-Anker-Notizen
    Glossar\<Term>.md    Glossar-Notizen (ab -MinGlossar Vorkommen)
```

---

## Kompletter Ablauf (Beispiel)

```powershell
# 0) Quelldatei nach Inbox\ legen

# 1) Übersetzen  →  Lektor\Horton, Scott\Provoked\{de,en}\
python ebook-translate.py "Provoked.epub" --source-lang en

# 2) Qualität sichern, bevor getaggt wird
python fix-chunks.py "Horton, Scott\Provoked"

# 3) Metadatenreste im Rohtext pruefen
python check-metadata.py "Horton, Scott\Provoked"

# 4) Tags vorschlagen (Lauf über Nacht)
python suggest-tags.py "Horton, Scott\Provoked" --in-place --resume

# 5) Korrekturlesen: Tags bestätigen, ==Hervorhebungen== setzen

# 6) Erschließung einsammeln
python collect-tags.py "Horton, Scott\Provoked" --zusammenfassung
python collect-marks.py "Horton, Scott\Provoked" --suggest

# 7) Gesamttexte  →  Outbox\Horton, Scott - Provoked_{de,en}.md
python ebook-build.py "Provoked"

# 8) optional: Obsidian-Vault (aus der deutschen Fassung)
.\build-vault.ps1 -SourceDir "D:\Workspace\!Episto\rohdaten\Lektor\Horton, Scott\Provoked\de" `
                  -VaultPath  "D:\Obsidian\LokalVault\Provoked" `
                  -Buch "Provoked" -Autor "Horton, Scott" -Jahr 2024
```

Danach den Vault-Ordner in Obsidian öffnen. Startpunkt: `MOC.md`.

---

## Wartung

### Defekte Chunks (`fix-chunks.py`)

```powershell
python fix-chunks.py                    # alle Bücher prüfen
python fix-chunks.py --zeige-apparat    # auch Register/Bibliografien anzeigen
python fix-chunks.py --repair           # defekte Chunks zur Neuübersetzung freigeben
```

Meldet leere, zu kurze, fehlende und unübersetzt gebliebene Chunks. Mit
`--repair` werden sie gelöscht und aus `.progress.json` ausgetragen; das
Skript gibt anschließend die passenden `--resume`-Befehle aus (jeweils mit
`--book-dir`, weil kuratierte Ordnernamen von den Metadaten abweichen).

**Register, Bibliografien und Endnotenapparate werden erkannt und nicht als
Defekt gemeldet** — dort ist unübersetztes Englisch das richtige Ergebnis,
weil Werktitel, Verlagsnamen und Seitenzahlen nicht übersetzt gehören.
Die Erkennung stützt sich auf Ziffernanteil, Zeilenlänge, Dichte von
Jahreszahlen und das Muster „Nachname, V.".

Erfahrungswert: Passagen, die beim ersten Lauf unübersetzt bleiben, bleiben es
bei `temperature 0.1` meist auch beim zweiten Versuch. Wiederholen lohnt nur
einmal; danach ist Handarbeit oder ein anderes Modell nötig.

### Fußnoten (`extract-footnotes.py`)

```powershell
python extract-footnotes.py "Parvini, Neema\The Populist Delusion"
python extract-footnotes.py --alle --dry-run
```

Pandoc verliert bei InDesign-EPUBs die Fußnoten**texte** — im Chunk-Bestand
stehen nur die Referenzen, die Ziele fehlen. Das Skript liest die Fußnoten
direkt aus dem EPUB und legt sie als `<lang>\footnotes.md` mit Zeilen der Form
`[^01-011]: Text` ab. `ebook-build.py` hängt bei `--footnotes` bzw. `--clean`
genau die Definitionen an, die im Text auch referenziert werden.

Der Bezeichner setzt sich aus Kapitelnummer und Fußnotennummer zusammen
(`01-011`), weil die Zählung je Kapitel neu beginnt.

## Hinweise

- **Generisch:** `build-vault.ps1` ist parametrisiert und funktioniert für **jedes**
  übersetzte Buch. Es ersetzt die früheren buchspezifischen FIMI-Einmalskripte
  (`build-vault-part1..5`, `create-glossary`, `fix-vault-*`) — diese liegen jetzt in
  `D:\Workspace\!FIMI\_archive\`.
- **Abbruch/Fortsetzen:** Schritt 1 ist resume-fähig; ein abgebrochener Lauf wird mit
  `--resume` genau dort fortgesetzt.
- **Encoding:** `build-vault.ps1` ist ASCII/BOM-sicher und läuft unter Windows
  PowerShell 5.1.
- **Modell:** `aya-expanse:32b` ist ein multilinguales Modell (23 Sprachen inkl. Deutsch);
  für andere Zielsprachen müsste der Prompt in `ebook-translate.py` angepasst werden
  (aktuell fest auf Deutsch als Ziel).
