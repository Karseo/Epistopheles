# Design: Text-Highlighting im Lesemodus

## Ziel

Im Lesemodus des `ReaderPane` (Text-Tab) soll sich ein Absatz mit einer von
drei Farben hervorheben lassen, ohne dafür in den Editiermodus (`TextArea`)
wechseln zu müssen. Das größere Vorhaben — Kommentar-Tab entfernen,
Kommentare direkt beim Editieren hinzufügen — ist ein eigenes, separates
Thema für einen späteren Zeitpunkt und nicht Teil dieser Änderung.

## Datenmodell & Speicherung

Neue Dataclass `Highlight` in `models.py`, strukturell analog zu
`Kommentar`:

```python
@dataclass
class Highlight:
    datei: str
    absatz_index: int
    absatz_anfang: str
    farbe: str  # "gelb" | "rosa" | "blau"

    @staticmethod
    def from_dict(d: dict) -> "Highlight": ...
    def to_dict(self) -> dict: ...
```

Eigene Datei `notizen/highlights.json` pro Buch (gleiches Muster wie
`tags.json`/`kommentare.json`: `{"highlights": [...]}`), mit den
entsprechenden `library.py`-Funktionen `read_highlights(buch, dateiname)`,
`write_highlight(buch, highlight)` (ersetzt einen vorhandenen Eintrag zum
selben `absatz_index`, hängt sonst neu an) und `remove_highlight(buch,
dateiname, absatz_index)` (Toggle-Fall: dieselbe Farbe nochmal gewählt →
Eintrag entfernen statt ersetzen). Backup vor jedem Schreiben wie bei den
bestehenden `write_*`-Funktionen (`backup_before_write`).

Die Verankerung an den Absatz läuft über dieselbe robuste
`annotate.locate_paragraph()`-Logik wie bei Kommentaren (`absatz_index` +
Textanfang-Präfix, verzeiht spätere Bearbeitungen).

## Interaktion

1. **Klick** irgendwo in einen Absatz im gerenderten Markdown-Text bestimmt
   den "aktiven" Absatz (Klick-Event bubbelt bis zum `ReaderPane`, `event.
   widget` verweist auf den getroffenen `MarkdownParagraph`; sein Index unter
   den `MarkdownParagraph`-Kindern von `#anzeige` entspricht dem Index in
   derselben `absaetze`-Liste, die auch die Kommentar-Anker nutzen — beide
   stammen aus demselben `annotate.split_paragraphs()`-Aufruf auf denselben
   Text).
2. **Farbtaste** (`g` Gelb, `r` Rosa, `b` Blau — neue `Binding`s auf
   `ReaderPane`, nur im Lesemodus aktiv) wendet die Farbe auf den zuvor per
   Klick bestimmten Absatz an:
   - Absatz noch ohne Highlight → Highlight in der gedrückten Farbe anlegen.
   - Absatz bereits in genau dieser Farbe → Highlight entfernen (Toggle).
   - Absatz bereits in einer ANDEREN Farbe → Farbe wechseln (ersetzen).
3. Ohne vorherigen Klick (kein aktiver Absatz) tut eine Farbtaste nichts.

## Rendering

Nach jedem `Markdown.update(...)` (in `_zeige_lesemodus()`) werden die
gemounteten `MarkdownParagraph`-Kinder von `#anzeige` durchlaufen und für
jeden Index mit einem Highlight-Eintrag `widget.styles.background` (und bei
Bedarf eine passende Textfarbe für Lesbarkeit) gesetzt — kein
Markdown-Syntax-Hack, sondern direktes Styling der bereits vorhandenen
Absatz-Widgets. Da `Markdown.update()` eine `AwaitComplete` liefert und die
Kind-Widgets erst nach einem Refresh-Zyklus gemountet sind, läuft das
Styling über `self.call_after_refresh(...)`, ohne dass `_zeige_lesemodus()`
selbst (oder ihre Aufrufer `lade_kapitel()`/die `action_*`-Methoden) async
werden müssen — das würde alle bestehenden synchronen Testaufrufe von
`lade_kapitel()` brechen.

Die genauen Farbtöne (Kontrast zu Standard-Vordergrundfarbe im Dark-Mode)
werden beim Implementieren visuell mit einer echten Pilot-Probe gegen die
reale Bibliothek abgestimmt, nicht blind aus Hex-Werten geraten.

## Testing

- `library.py`: `read_highlights`/`write_highlight`/`remove_highlight` —
  Normalfall, fehlende Datei, Toggle (gleiche Farbe zweimal → entfernt),
  Farbwechsel (andere Farbe → ersetzt), Backup vor Schreiben.
- `models.py`: `Highlight.from_dict`/`to_dict` Rundreise, fehlende Felder.
- `reader_pane.py`: Klick auf einen Absatz + Farbtaste färbt genau das
  richtige `MarkdownParagraph`-Widget; zweiter Druck derselben Taste entfernt
  die Färbung wieder; andere Taste wechselt die Farbe; Farbtaste ohne
  vorherigen Klick verändert nichts; Highlight bleibt nach erneutem
  `lade_kapitel()`-Aufruf (Kapitelwechsel + zurück) erhalten, weil es aus
  `notizen/highlights.json` neu geladen wird.
