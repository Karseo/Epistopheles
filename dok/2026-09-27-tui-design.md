# EPISTO TUI — Design (V1)

Stand: 2026-09-27. Ersetzt langfristig `tools\episto-tui.ps1`. Diese Spec deckt
**Version 1** ab: Lesen, Editieren, Kommentieren, Metadaten-Ansicht. Pipeline-
Steuerung (Tagging/Stränge/Ingest auslösen) und semantische Suche folgen in
einer späteren Version 2 — bis dahin bleibt `episto-tui.ps1` für diese
Schritte parallel nutzbar.

## 1. Ziel

Eine Python/Textual-TUI, die die !Episto-Bibliothek (`Autor\<Autor>\<Titel>\`)
zum Lesen aufbereitet — mit gerendertem Markdown statt Rohtext — und dabei
direktes Editieren des Kapiteltexts, Korrigieren der Tag-Metadaten und
Kommentieren einzelner Absätze erlaubt. Stränge und Querverweise werden
angezeigt, aber in V1 nicht editiert.

## 2. Architektur

```
episto_tui/
  app.py              # Einstiegspunkt, Textual App-Klasse, Layout
  library.py          # Einzige Dateizugriffs-Schicht: Autor/Buch/Kapitel
                       #   scannen, quelle\*.md, tags.json, straenge\*.md,
                       #   querbezuege.json, kommentare.json lesen+schreiben
  models.py           # Datenklassen: Buch, Kapitel, Tag, Kommentar
  backup.py           # Sicherungskopie vor jedem Überschreiben
  widgets/
    tree_sidebar.py    # Autor→Buch→Kapitel-Baum, Tippfilterung
    reader_pane.py     # Text-Tab: Markdown-Render ↔ Edit-Umschaltung
    tags_pane.py       # Tags-Tab: these/gegen/kern/def/beleg editierbar
    straenge_pane.py   # Stränge-Tab: nur Anzeige
    querbezuege_pane.py# Querverweise-Tab: nur Anzeige
    kommentare_pane.py # Kommentare-Tab: Liste + neuer Kommentar an Absatz
```

`library.py` kennt als einzige Stelle die Episto-Dateikonventionen (Pfade,
JSON-Schemata). Widgets greifen nie direkt aufs Dateisystem zu — das macht sie
mit einer Fake-Library testbar und hält V2 (Pipeline-Trigger, Suche)
anschlussfähig, ohne die Widgets zu ändern.

**Layout:** `Horizontal` Root → links `tree_sidebar` (fest, ~30 Spalten),
rechts `TabbedContent` mit den fünf Panes (Text/Tags/Stränge/Querverweise/
Kommentare). Auswahl im Baum lädt das Kapitel neu in alle Panes.

**Tippfilterung:** Buchstaben tippen im Baum grenzt sichtbare Knoten direkt
ein (kein separates Suchfeld), `Esc` setzt zurück.

**Datenzugriff:** direkt von der Platte bei jeder Kapitelauswahl (kein Cache,
kein Zwischenzustand) — passt zur bestehenden Episto-Philosophie, dass der
Zustand vollständig auf Disk liegt. Wichtig, weil parallel weiterhin
PowerShell-Pipeline-Skripte laufen können.

## 3. Datenmodell & Speicherformate

### Kommentare (neu, pro Buch): `notizen\kommentare.json`

```json
{
  "werk": "Fake News",
  "kommentare": [
    {
      "datei": "0003_glaubwuerdige-informationen.md",
      "absatz_index": 4,
      "absatz_anfang": "Die Glaubwürdigkeit von Informationen existiert auf einem Kontinuum...",
      "text": "Vergleich mit Poppers Falsifikationskriterium prüfen",
      "erstellt": "2026-09-27 14:00"
    }
  ]
}
```

Anker-Einheit ist der **Absatz** (getrennt durch Leerzeilen, wie überall sonst
in der Pipeline, z. B. `ingest.ps1`), nicht das Zeichen. `absatz_index` ist die
Position beim Anlegen; `absatz_anfang` (erste ~80 Zeichen) dient als Fallback,
um den Kommentar auch nach kleinen Textänderungen wiederzufinden (gleiche
Idee wie die Seitenzahl-Anker in der eBooks-Toolchain). Lässt sich der Absatz
nicht mehr eindeutig zuordnen, zeigt die TUI den Kommentar als „verwaist" am
Kapitelende, statt ihn zu verlieren.

Kommentare erscheinen im Text-Tab als hochgestellte Marke `[¹]` am
Absatzende und vollständig im Kommentare-Tab.

### Tags-Editor

Formularfelder für `these`/`gegen`/`kern`/`def`/`beleg` als mehrzeilige
Listen (eine Zeile = ein Listenelement), `zusammenfassung` als Fließtext.
Speichern schreibt `notizen\tags.json` komplett neu, im selben Schema, das
`taggen.ps1` erzeugt — die TUI-Bearbeitung ist damit austauschbar mit einem
erneuten LLM-Lauf.

### Backup

Vor jedem Schreiben von `quelle\*.md` **oder** `tags.json`: Kopie nach
`notizen\_backup\<dateiname>.<YYYYMMDD-HHMMSS>.md` (bzw. `.json`). Kein
automatisches Aufräumen alter Backups in V1.

## 4. Bedienung

| Taste | Wirkung |
|---|---|
| `↑`/`↓`, `j`/`k` | Im Baum navigieren |
| Buchstaben tippen | Baum filtern (Typeahead) |
| `Enter` | Kapitel öffnen (lädt alle Tabs) |
| `Tab` / `1`–`5` | Zwischen Text/Tags/Stränge/Querverweise/Kommentare wechseln |
| `e` | Text-Tab: Lesemodus ↔ Editiermodus umschalten |
| `Strg+S` | Speichern (Backup + Schreiben), zurück in Lesemodus |
| `Esc` | Editiermodus verwerfen (Rückfrage bei ungesicherten Änderungen) / Baumfilter zurücksetzen |
| `c` | Kommentare-Tab: aktuellen Absatz markieren, Kommentar eintippen |
| `q` | Beenden |

## 5. Fehlerbehandlung

- **Fehlende/kaputte Dateien** (kein `tags.json`, ungültiges JSON): Tab zeigt
  einen Platzhalter („Noch nicht getaggt — `tools\taggen.ps1` ausführen")
  statt Absturz.
- **Gleichzeitiger externer Zugriff:** kein Locking; die TUI liest bei jeder
  Auswahl frisch von der Platte, das Backup fängt versehentliches
  Überschreiben ab. Realistisches Risiko gering (Einzelnutzer-Tool).
- **Ungültige Nutzereingabe** (leeres Pflichtfeld im Tag-Editor): keine harte
  Validierung — die Datenstruktur bleibt so tolerant wie das, was
  `taggen.ps1` selbst erzeugen könnte (leere Listen erlaubt).

## 6. Nicht in V1 (verschoben auf V2)

- Pipeline-Aktionen auslösen (Tagging/Stränge/Ingest) — `episto-tui.ps1`
  bleibt dafür bis V2 parallel nutzbar
- Semantische Suche (Qdrant)
- Editieren von Strängen/Taxonomie und Querverweisen (nur Anzeige)
- Mehrsprachigkeit (nur Arbeitssprache `de`, kein Umschalten auf `en`)

## 7. Testing

- **`library.py`** (Dateizugriff, Parsing, Backup-Logik): Unit-Tests mit
  temporärem Verzeichnis, das die Episto-Ordnerstruktur nachbildet — deckt
  Lesen/Schreiben/Backup/Fehlerfälle ab, ohne die echte Bibliothek zu
  berühren.
- **TUI-Ablauf:** Textuals `App.run_test()` mit `Pilot` zum Simulieren von
  Tastendrücken — ein bis zwei Kernabläufe: Baum navigieren → Kapitel öffnen
  → editieren → speichern → Backup-Datei existiert; Kommentar an Absatz
  anlegen → erscheint im Kommentare-Tab. Kein Anspruch auf vollständige
  Snapshot-Tests aller Widgets in V1.
