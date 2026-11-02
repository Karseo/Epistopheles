# Zusammenführung eBooks + !Episto — Konzept

> **Überholt (2026-11):** Der Umbau zu `rohdaten\` / `reader\` / `tools\` / `hilfsdaten\` hat dieses
> Konzept abgelöst; siehe `dok/DATENSTRUKTUR.md`. Der Text unten beschreibt den früheren Plan und die
> Zwischenstände (`Autor\`, `eBooks\`) und bleibt als Verlauf erhalten.

Status: **Pipeline vollständig operativ — 78 Bücher integriert** (Volltext → Tags →
Stränge → Qdrant). Die ursprüngliche Cloud-Sandbox-Einschränkung (kein PowerShell/
Ollama) ist entfallen; alle Schritte laufen lokal auf dem Windows-Rechner. Übersicht:
`dok/README.md` (Werkliste); offene Queue: Auto-Memory `buecher-integrations-queue.md`.

## 1. Ausgangslage

Zwei Systeme sind nebeneinander gewachsen, ohne dass eines das andere ablöst:

| | `eBooks\` | `!Episto\` |
|---|---|---|
| Rolle | Werkstatt: Übersetzung, Rohtagging | kuratierte Bibliothek: Volltext + Metadaten + Vektoren |
| Einheit | fester 8000-Zeichen-Chunk | echtes Kapitel |
| Tagging | chunk-weise, `%%tag%%` inline (`suggest-tags.py`) | kapitel-weise, JSON-Schema (`taggen.ps1`) |
| Stränge | Stichwort-Register + Handkuration (`collect-tags.py`) | kuratierte Taxonomie + String-Matching (`straenge.ps1`) |
| Zweisprachigkeit | immer de+en | nein (nur Originalsprache vorgesehen) |
| Fertige Werke | 15 Bücher übersetzt, 1 davon (*The Populist Delusion*) getaggt+Stränge | Kant ×2 komplett (Text→Tags→Stränge→Qdrant) |

Zwei Bücher hingen bereits **halb migriert** in `!Episto\Autor\`, offenbar aus
einem früheren, abgebrochenen Versuch:

- `Bourdieu, Pierre\The State Nobility\` — nur `en\`-Chunks 1:1 aus Lektor
  kopiert, kein `de\`, kein `quelle\`, `kapitel.json` enthält nur `"Seite N"`
  (PDF ohne Kapitelanker).
- `Kahneman, Daniel\Schnelles Denken...\` — ein leerer `de\txt\`-Ordner, sonst
  nichts.

Beide werden unten in den neuen Ablauf eingeordnet (Abschnitt 8), nicht separat
"repariert" — das neue Brücken-Skript ersetzt den Handumbau ohnehin.

## 2. Zielarchitektur: ein Baum

Entscheidung (siehe Rückfrage): **`eBooks\` wird aufgelöst, alles wandert unter
`!Episto\`.** Zielbild:

```
!Episto\
  Inbox\              (aus eBooks\Inbox — Rohdateien, noch nicht verarbeitet)
  tools\              (aus eBooks\*.py + bisherige !Episto\tools\*.ps1)
  Autor\<Autor>\<Titel>\   (Endzustand je Werk, Schema siehe Abschnitt 4)
  Outbox\             (optional, aus ebook-build.py — Gesamttext-Export)
  dok\                (dieses Dokument + README/NÄCHSTE_SCHRITTE/...)
```

`eBooks\Lektor\` als *Zwischenstand* (übersetzt, aber noch nicht kapitelweise
aufbereitet) entfällt als eigener Ort — dieser Zwischenstand entsteht künftig
direkt unter `!Episto\Autor\<Autor>\<Titel>\` (Chunks in `de\`/`en\`, bis das
Brücken-Skript daraus `quelle\` baut und die Chunk-Ordner wieder löscht/
archiviert). Das ist ein **schrittweiser Rückbau**, kein Big-Bang-Move: eBooks
bleibt nutzbar, bis jedes seiner 15 Bücher durch den neuen Ablauf gelaufen ist.

## 3. Warum ein festes Skript nicht reicht — drei Belege aus echten Daten

Das war die Grundannahme der Aufgabe; hier die konkreten Funde aus dieser
Session, nicht nur die Vermutung:

**a) Gliederungserkennung schwankt extrem.** Bereits in `konzept-argumente.md`
dokumentiert: 4 von 13 Büchern null Überschriften, *Provoked* 846 Treffer bei
694 Chunks (Pandoc hält Marginalien für Überschriften). `suggest-structure.py`
hat dafür schon eine Heuristik (`braucht_llm()`: nur wenn `kapitel.json` fehlt
oder leer ist, wird das LLM für die TOC-Rekonstruktion gerufen) — das ist
bereits "Orchestrierung", nur bisher nicht mit dem Episto-Schema verbunden.

**b) Die Konvertierungsartefakte sind nicht mal zwischen EPUBs einheitlich.**
Am Pilotbuch (*The Populist Delusion*) gebaut und getestet: Der vorhandene
Bereinigungs-Code (`ebook-build.py::normalize_footnotes`) geht von
Fußnotenankern der Form `(#…footnote-N)` aus — mit `#`. Bei diesem EPUB fehlt
das `#` (`(…footnote-N)` ohne Raute). Ergebnis: 40 von 45 Kapiteln hatten nach
der "Standard"-Bereinigung noch rohe `[[[12](…)]{...}]{.CharOverride-1}`-Reste
im Text. Erst eine angepasste Regel hat das gefangen. **Das ist der Kernbefund:**
zwei EPUBs vom selben Verlag/Pandoc-Lauf können unterschiedlich aussehen — ein
fixes Regelwerk trifft nicht alle Fälle, jemand (oder etwas) muss die Reste
zählen und nachbessern.
Verbleibender Rest nach der Korrektur: 10 Stellen, alle vom Typ "Formatierungs-
Span mit verschachtelten Klammern" (`[etwas [mit] Klammern]{.CharOverride-2}`)
— das sprengt jede nicht-rekursive Regex und bräuchte entweder einen echten
Parser oder eine Einzelfall-Korrektur.

**c) OCR-Fehler (Beispiel: „ii" statt „ü") sind bisher gar nicht adressiert.**
Kein Skript in `eBooks\` behandelt Zeichenfehler aus Scans/Fraktur-OCR — nur
Pandoc-/InDesign-Reste (b) und kaputte Übersetzungs-Chunks (`fix-chunks.py`).
Betrifft vor allem gescannte Quellen ohne Textebene (z.B. Popper, dessen PDF
laut `NÄCHSTE_SCHRITTE.md` genau deshalb noch fehlte) und historische
Frakturtexte. Das ist eine echte Lücke, kein Vereinheitlichungsproblem — siehe
Abschnitt 9.

**Konsequenz:** Die Stellen, an denen ein lokales LLM statt eines Fixskripts
gebraucht wird, sind konkret benennbar:

1. Gliederungsmethode wählen (Anker/Überschrift ausreichend, oder TOC-LLM
   nötig?) — **existiert bereits** (`braucht_llm`), nur nicht ans Episto-Schema
   angebunden.
2. Bereinigungsergebnis beurteilen (Restartefakte zählen, Muster erkennen,
   ggf. Regel ergänzen oder Kapitel einzeln nacharbeiten) — **neu**, siehe
   `restartefakte()` im Brücken-Skript (Abschnitt 6) als Signalgeber.
3. OCR-Bereinigung bei Scan-Quellen — **fehlt komplett**, siehe Abschnitt 9.
4. Gliederungs-Hierarchie prüfen/verfeinern (das Brücken-Skript liefert nur
   eine flache Liste, siehe Abschnitt 6) — Aufgabe der Tagging-/Analysephase.

## 4. Die vereinheitlichte Pipeline

```
Inbox\*                                          (Rohdatei)
  │  ebook-translate.py  [aya-expanse:32b]
  ▼
Autor\<Autor>\<Titel>\{de,en}\chunk_NNN.md        (übersetzt, Chunk-Einheit)
  │  detect-chapters.py         (Anker/Überschrift, kein LLM)
  │    └─ braucht_llm() ⇒ suggest-structure.py  [qwen3.8:27b, TOC-Rekonstruktion]
  ▼
kapitel.json (Lektor-Schema: Chunk+Position je Segment)
  │  check-metadata.py   (Konvertierungsreste diagnostizieren)
  │  extract-footnotes.py (Fußnotentexte aus EPUB nachziehen, falls nötig)
  ▼
  │  ► NEU: tools\lektor-zu-episto.py  (rein mechanisch, kein LLM)
  ▼
Autor\<Autor>\<Titel>\quelle\NNNN_slug.md          (Episto-Schema: Kapitel-Einheit)
  + kapitel.json (gliederung/zuordnung) + _kapitel_index.json
  + <Referenzsprache>\chunk_NNN.md (unverändert kopiert)
  │  tools\taggen.ps1            [qwen3.8:27b, kapitelweise]
  ▼
notizen\tags.json
  │  Taxonomie kuratieren (notizen\strang_taxonomie.json) — Handarbeit,
  │  Rohstoff bei übernommenen Büchern: notizen\_chunkweise-vorarbeit\stichworte.md
  │  tools\straenge.ps1
  ▼
notizen\straenge\*.md
  │  ingest.ps1  [mxbai-embed-large → Qdrant]
  ▼
durchsuchbar
```

Alles bis `check-metadata.py`/`extract-footnotes.py` existiert schon in
`eBooks\` und bleibt unverändert (nur der Ordner wandert). Ab
`lektor-zu-episto.py` ist alles Episto-Seite und ebenfalls unverändert
(`taggen.ps1`, `straenge.ps1`, `ingest.ps1`). **Die einzige echte Lücke war die
Brücke dazwischen — die jetzt existiert.**

## 5. Tagging-System: Episto (kapitelweise) wird Standard

Entscheidung (siehe Rückfrage): `taggen.ps1`/`straenge.ps1` (kapitelweise)
lösen `suggest-tags.py`/`collect-tags.py` (chunkweise) für neue Arbeit ab — das
entspricht der bestehenden `STRUKTUR.md`-Konvention ("keine festen Chunks
mehr, Einheit ist das Kapitel").

Die bereits geleistete Chunk-Arbeit an *The Populist Delusion* (263 Tags, 174
Stichworte, 27 vorläufige Stränge) ist damit nicht verloren — sie liegt jetzt
unter `notizen\_chunkweise-vorarbeit\` im migrierten Buchordner und ist der
**Rohstoff für die Taxonomie-Kuration**: `stichworte.md` (Stichwort-Register
mit Häufigkeiten) und die 30 vorläufigen `straenge\*.md` ersparen das
Neuerfinden der Taxonomie von Null — `notizen\strang_taxonomie.json` kann
direkt daraus abgeleitet werden, statt blind zu raten, welche Stränge das Buch
trägt.

## 6. Die neue Brücke: `tools\lektor-zu-episto.py`

Liegt jetzt unter `!Episto\tools\lektor-zu-episto.py`. Rein mechanisch (kein
LLM-Aufruf, keine Netzabhängigkeit) — bewusst so geschnitten, weil dieser
Schritt deterministisch sein *kann*: Kapitelgrenzen stehen in `kapitel.json`,
die Bereinigungsregeln sind bekannte Muster.

Was es tut:

1. Liest `kapitel.json` (bevorzugt das Feld `segmente` — vollständig inkl.
   Vorspann-Positionen; Fallback `kapitel`).
2. Schneidet den durchgehenden Arbeitssprachtext exakt an den Kapitelgrenzen
   (chunk-übergreifend, Chunks werden an Absatzgrenzen wieder zusammengefügt).
3. Bereinigt dabei Pandoc-/InDesign-Reste — Logik aus `ebook-build.py`
   übernommen und um die `#`-lose Fußnoten-Variante (Fund b) erweitert.
4. Schreibt `quelle\NNNN_slug.md` + `_kapitel_index.json` + `kapitel.json`
   (Episto-Schema: `gliederung`/`zuordnung`), Vorspann/Anhang automatisch
   erkannt und gruppiert (alles dazwischen bleibt vorerst **flach** — eine
   Hierarchie wie bei Kant ist Handarbeit/Tagging-Aufgabe, keine Annahme, die
   das Skript treffen sollte).
5. Kopiert die Referenzsprache unverändert (Standard: `en\`).
6. Übernimmt `meta.json` (+ leerer `episto`-Block zum Ausfüllen), schreibt
   `.progress.json` im Episto-Format inkl. geschätzter Restartefakt-Zahl.
7. Sichert vorhandene Chunk-Tags/Stränge nach `notizen\_chunkweise-vorarbeit\`
   (Abschnitt 5) — löscht nichts im Quellordner.

Aufruf:

```powershell
python tools\lektor-zu-episto.py --buch "Parvini, Neema/The Populist Delusion"
python tools\lektor-zu-episto.py --buch "..." --dry-run     # nur anzeigen
```

(Standardpfade sind fest auf `D:\Workspace\!Episto\eBooks\Lektor` bzw.
`D:\Workspace\!Episto\Autor` eingestellt, per `--lektor`/`--episto`
überschreibbar. Der Lektor-Ordner wurde nachträglich von
`C:\Users\Dude\Tools\eBooks` nach `D:\Workspace\!Episto\eBooks` verschoben; die Skripte dort
leiten ihr `BASE` aus ihrem Ablageort ab, alte Pfade in `meta.json` werden zur Laufzeit
umgesetzt.)

**Bekannte Grenzen** (bewusst nicht gelöst, siehe Abschnitt 3c/9):
verschachtelte Klammer-Spans in Formatierungsresten (Regex kann nicht
rekursiv), Bild-Alt-Text-Spans, keine OCR-Korrektur.

## 7. Pilot: *The Populist Delusion*

Gewählt, weil am weitesten fortgeschritten (Übersetzung + Chunk-Tagging schon
fertig) und mit sauberer Anker-Gliederung (EPUB, 9 echte Kapitel + Vorspann/
Bibliography — kein Fall, der eine LLM-Struktur-Analyse gebraucht hätte).

Tatsächlich durchgeführt (aus dieser Session heraus, nur mechanische Schritte
— siehe unten, warum nicht mehr):

| Schritt | Ergebnis |
|---|---|
| `lektor-zu-episto.py` (Dry-Run + echt) | 15 Kapitel-Dateien, 12 Gliederungsknoten (1× Vorspann, 9 Sachkapitel, 1× Anhang) |
| Bereinigung | 40→10 Restartefakte (nach Regex-Fix für fehlendes `#`, siehe 3b) |
| Stichprobe Kapitelgrenzen | exakt — Kapitel 5 endet direkt vor der Überschrift von Kapitel 6, keine abgeschnittenen Sätze |
| Referenzsprache `en\` | 45 Chunks kopiert |
| Alte Chunk-Vorarbeit | gesichert unter `notizen\_chunkweise-vorarbeit\` |

Liegt jetzt unter `!Episto\Autor\Parvini, Neema\The Populist Delusion\`.

**Nicht durchgeführt, weil diese Cloud-Session weder PowerShell noch eine
Netzwerkverbindung zum lokalen Ollama hat** (geprüft: `pwsh`/`ollama` nicht
vorhanden, `localhost:11434` nicht erreichbar aus der Sandbox-VM). Das sind
die noch offenen, auf dem Windows-Rechner selbst auszuführenden Schritte:

```powershell
cd D:\Workspace\!Episto
tools\taggen.ps1 -Buch "Autor\Parvini, Neema\The Populist Delusion"
# danach: notizen\strang_taxonomie.json von Hand kuratieren
#         (Rohstoff: notizen\_chunkweise-vorarbeit\stichworte.md)
tools\straenge.ps1 -Buch "Autor\Parvini, Neema\The Populist Delusion"
tools\ingest.ps1
```

## 8. Migrationsplan für die übrigen Bücher

Reihenfolge nach Aufwand/Nutzen, nicht alphabetisch:

1. **Bourdieu, Kahneman** — die zwei angefangenen, inkonsistenten Ordner unter
   `!Episto\Autor\` löschen (nichts Verwertbares drin außer 1:1-kopierten
   Chunks, die auch in `eBooks\Lektor\` liegen) und über `lektor-zu-episto.py`
   neu aufbauen. Bourdieu braucht vorher `detect-chapters.py`/
   `suggest-structure.py` — sein aktuelles `kapitel.json` hat nur
   `"Seite N"`-Platzhalter, keine echten Kapitel. Kahneman hat noch gar keine
   Übersetzung (`de\txt\` ist leer) — ab `ebook-translate.py` starten.
2. **Restliche 13 Bücher aus `eBooks\Lektor\`** — alle übersetzt, aber nur
   *Populist Delusion* mit Tags. Für jedes: `kapitel.json`-Qualität prüfen
   (`braucht_llm`-Logik), ggf. `suggest-structure.py`, dann
   `lektor-zu-episto.py`, dann kapitelweise taggen. *Provoked* (694 Chunks)
   und *Capitalism, Socialism and Democracy* (175 Chunks, noch kein
   `kapitel.json`) sind die aufwändigsten Fälle.
3. **eBooks-Rückbau**: `tools\*.py` nach `!Episto\tools\` verschieben,
   `Inbox\` nach `!Episto\Inbox\`, `eBooks\Lektor\` erst leeren, wenn Punkt 2
   für alle Bücher durch ist — danach `eBooks\` löschen.

## 9. Offene Punkte

- **OCR-Korrektur fehlt als Baustein.** Betrifft Scan-Quellen ohne Textebene
  (Popper) und Fraktur-Digitalisate. Vorschlag: eigener Schritt zwischen
  Extraktion und Übersetzung, der auffällige Zeichenfolgen (z.B. `ii`/`iı` für
  `ü`, `rn` für `m`) per LLM-Durchsicht korrigiert, bevor `aya-expanse:32b`
  darauf läuft — sonst schleppt die Übersetzung den Fehler unsichtbar mit
  (bei deutschsprachigen Quellen ohne Übersetzung sogar unkorrigiert bis in
  `quelle\`). Noch nicht gebaut.
- **Gliederungs-Hierarchie ist nach `lektor-zu-episto.py` flach.** Kant hat
  eine mehrstufige Gliederung (Vorspann → Einleitung → I/II) von Hand/LLM
  bekommen; das Brücken-Skript liefert bewusst nur die sichere Ebene (echte
  Kapitel = flach), keine geratene Hierarchie.
- **Taxonomie-Kuration bleibt Handarbeit** (siehe `konzept-argumente.md`,
  Abschnitt "Stichwort-Varianz") — durch die Übernahme des Stichwort-Registers
  aus der Chunk-Vorarbeit beschleunigt, aber nicht automatisiert.
- **Analysen/Querbezüge** (wie bei Kant: `analysen\thesen.md`, `antithesen.md`,
  `querbezuege\`) sind für migrierte Bücher noch leer — kommt nach dem Tagging.
