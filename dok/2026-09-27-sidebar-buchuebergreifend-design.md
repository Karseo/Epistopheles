# Design: Buchübergreifende Sidebar-Ansichten (Begriffe & Definitionen)

## Ziel

Die linke Sidebar (`LibraryTree`) zeigt heute nur die Baumstruktur
"Buch → Kapitel" unter der Wurzel "Bibliothek". Sie soll einen zweiten,
gleichrangigen Menüpunkt bekommen: eine bibliotheksweite, flache Liste
aller Kernbegriffe und Definitionen aus allen getaggten Büchern, zum
schnellen Nachschlagen und zum direkten Sprung ins jeweilige Kapitel.

## Hintergrund: warum nicht mehr Abschnitte

Ursprünglich waren fünf Abschnitte angedacht (Thesen, Gegenpositionen,
Kernbegriffe, Definitionen, Belege). Eine Sichtung der echten Tagging-Daten
(`notizen/tags.json`, LLM-generiert über `taggen.ps1`) zeigt: `these`,
`gegen`, `kern`, `def` und `beleg` sind pro Kapitel fünf unabhängige
Listen ohne strukturelle Verknüpfung untereinander (unterschiedliche
Längen, keine Index-Zuordnung). Eine sinnvolle "Beleg gehört zu These X"-
oder "These gehört zu Thema Y"-Darstellung würde eine Erweiterung des
Tagging-Schemas plus Neu-Tagging aller Bücher erfordern — das ist ein
eigenes, separates Vorhaben und nicht Teil dieser Änderung.

`kern` und `def` dagegen lassen sich sofort sinnvoll bibliotheksweit
darstellen: `def`-Einträge sind bereits selbsterklärende, in sich
geschlossene Sätze, die den Begriff selbst enthalten (Beispiel aus den
echten Daten: *"Informationskompetenz (Begriff 1974 geprägt): die
Bemühungen von Bibliothekaren, ..."*). Eine gemeinsame alphabetische
Sortierung beider Felder in einer Liste bringt verwandte Kernbegriffe und
Definitionen meist von selbst in die Nähe zueinander, ohne dass eine
echte Verknüpfung in den Daten existieren muss.

## Sidebar-Struktur

Der `Tree`-Widget-Root wird unsichtbar (`show_root = False`) und bekommt
zwei gleichrangige Kinder statt bisher direkt die Bücher:

```
▸ Bibliothek                  (wie heute, aufgeklappt)
▸ Begriffe & Definitionen     (neu, initial eingeklappt)
```

Aufgeklappt zeigt "Begriffe & Definitionen" eine flache, alphabetisch
(case-insensitive) sortierte Liste aller `kern`- und `def`-Einträge aus
allen Büchern der Bibliothek, ungruppiert:

```
▾ Begriffe & Definitionen
  ▸ bibliothek
  ▸ Fake News, Lügen, Gerüchte, Fabeln, Propaganda sind Synonyme für ...
  ▸ Informationskompetenz (Begriff 1974 geprägt): die Bemühungen ...
  ▸ informationskompetenz
  ▸ ...
```

- Jedes Blatt zeigt nur den vollen Text (Begriff oder Definitionssatz),
  keine Buch-/Kapitelangabe im Label — die Quelle wird erst nach dem Klick
  sichtbar, wenn das Kapitel im Lesebereich rechts aufgeht (gleicher
  `ChapterSelected`-Mechanismus wie beim Klick auf ein Kapitel unter
  "Bibliothek", keine Änderung an `on_tree_node_selected` nötig).
- Mehrfachvorkommen desselben Begriffs/derselben Definition in
  verschiedenen Kapiteln werden **nicht** zusammengeführt — jedes
  Vorkommen ist ein eigenes, eindeutig sprungfähiges Blatt.
- Die bestehende Tipp-Filterung (Buchstaben tippen, Escape/Backspace)
  filtert weiterhin die ganze Baumstruktur inklusive dieses neuen
  Abschnitts: ein Eintrag bleibt sichtbar, wenn der Filtertext im
  Eintragstext, im Buchtitel oder im Autor vorkommt.
- Bearbeitet wird weiterhin ausschließlich über den normalen Weg (Sprung
  ins Kapitel → Tags-Tab). Die neue Ansicht ist reine Navigation/
  Nachschlage, wie die bestehenden Stränge-/Querverweise-Panes.

## Datenzugriff

Neue Funktion in `library.py`, nach dem Muster von `read_querbezuege()`:

```python
def read_all_tags(buch: Buch) -> list[Tag]:
    daten = _lade_json_dict(_tags_pfad(buch))
    if daten is None:
        return []
    return [Tag.from_dict(e) for e in _dict_eintraege(daten, "kapitel")]
```

Liest `notizen/tags.json` einmal komplett und robust (ignoriert kaputte
Einträge über `_dict_eintraege`, das bereits an anderer Stelle genutzt
wird). Aus jedem zurückgegebenen `Tag` lässt sich ein `Kapitel`-Objekt für
den Sprung direkt konstruieren (`Kapitel(tag.kapitel_nr, tag.titel,
tag.datei)`) — kein zweiter Dateizugriff über `list_chapters()` nötig.

## Baum-Aufbau (`tree_sidebar.py`)

`rebuild()` wird umstrukturiert:

1. `self.show_root = False` (einmalig, z. B. in `on_mount`).
2. Wurzelkind "Bibliothek" wie heute aufbauen (Bücher → Kapitel-Blätter),
   nur jetzt als Kind von `self.root` statt `self.root` selbst.
3. Für jedes Buch `library.read_all_tags(buch)` aufrufen, alle `kern`- und
   `def_`-Einträge (mit zugehörigem `Kapitel`) in eine gemeinsame Liste
   sammeln, nach Filtertext einschränken, dann case-insensitive nach Text
   sortieren.
4. Wurzelkind "Begriffe & Definitionen" (initial eingeklappt) mit einem
   Blatt pro sortiertem Eintrag anlegen, `data=(buch, kapitel)`.

## Testing

- `library.py`: Test für `read_all_tags()` — mehrere Kapitel-Einträge,
  fehlende Datei (leere Liste), kaputtes JSON (leere Liste), Einträge ohne
  `kern`/`def`-Feld.
- `tree_sidebar.py`: Test, dass "Begriffe & Definitionen" als zweites
  Wurzelkind neben "Bibliothek" erscheint; Test, dass Kernbegriffe und
  Definitionen mehrerer Bücher gemeinsam alphabetisch sortiert erscheinen;
  Test, dass ein Klick auf ein solches Blatt `ChapterSelected` mit dem
  richtigen Buch/Kapitel feuert; Test, dass die Tipp-Filterung auch diesen
  Abschnitt filtert; Test, dass ein Buch ganz ohne `kern`/`def`-Einträge
  keine leeren Blätter erzeugt.
