# Absatz-Highlighting im Lesemodus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Im Lesemodus des `ReaderPane` lässt sich ein Absatz per Klick + Farbtaste (Gelb/Rosa/Blau) einfärben, ohne in den Editiermodus wechseln zu müssen.

**Architecture:** Ein neues `Highlight`-Datenmodell (analog zu `Kommentar`) wird in einer eigenen `notizen/highlights.json` pro Buch persistiert. `ReaderPane` merkt sich per Mausklick den zuletzt getroffenen Absatz und wendet beim Drücken einer Farbtaste die Farbe direkt auf das entsprechende `MarkdownBlock`-Widget an (kein Markdown-Syntax-Hack, direktes Styling).

**Tech Stack:** Python, Textual 8.2.8 (`Markdown`/`MarkdownBlock`-Widgets, `events.Click`, `Worker`), pytest + pytest-asyncio.

## Global Constraints

- Nur drei Farben: `gelb` (Hintergrund `yellow`), `rosa` (Hintergrund `pink`), `blau` (Hintergrund `blue`); kein Highlight = Hintergrund `transparent`.
- Tastenbelegung: `g` = Gelb, `r` = Rosa, `b` = Blau — neue `Binding`s auf `ReaderPane`, nur wirksam im Lesemodus (nicht während `self.bearbeiten` True ist).
- Verankerung am Absatz läuft über `absatz_index` + `absatz_anfang`-Präfix (erste 80 Zeichen des Absatzes) — exakt das Muster, das `Kommentar`/`annotate.locate_paragraph()` bereits für Kommentare nutzen.
- Farbtaste ohne vorherigen Klick auf einen Absatz (kein `_aktiver_absatz_index` gesetzt) tut nichts.
- Dieselbe Farbtaste auf einem bereits so gefärbten Absatz entfernt das Highlight (Toggle); eine andere Farbtaste auf einem bereits gefärbten Absatz wechselt die Farbe (ersetzt den Eintrag).
- Kein Editor-Wechsel nötig — die gesamte Interaktion läuft im Lesemodus (`Markdown`-Anzeige), nicht in der `TextArea`.
- Backup vor jedem Schreiben von `highlights.json`, wie bei den bestehenden `write_tag`/`add_kommentar`-Funktionen (`backup_before_write`).

---

### Task 1: `Highlight`-Datenmodell + Persistenz

**Files:**
- Modify: `tools/episto_tui/models.py` (neue Dataclass, nach `Kommentar` am Dateiende anhängen)
- Modify: `tools/episto_tui/library.py` (neue Funktionen nach `add_kommentar`, am Dateiende anhängen; Import-Zeile 5 erweitern)
- Test: `tools/episto_tui/tests/test_models.py` (anhängen)
- Test: `tools/episto_tui/tests/test_library_highlights.py` (neu)

**Interfaces:**
- Consumes: `_lade_json_dict(pfad: Path) -> dict | None`, `_dict_eintraege(daten: dict, schluessel: str) -> list[dict]`, `backup_before_write(buch_root: Path, original_path: Path) -> Path | None` (alle bereits in `library.py`).
- Produces: `Highlight` (Dataclass mit `datei: str`, `absatz_index: int`, `absatz_anfang: str`, `farbe: str`, plus `from_dict`/`to_dict`), `library.read_highlights(buch: Buch, dateiname: str) -> list[Highlight]`, `library.write_highlight(buch: Buch, highlight: Highlight) -> None`, `library.remove_highlight(buch: Buch, dateiname: str, absatz_index: int) -> None` — alle in Task 2 von `reader_pane.py` genutzt.

- [ ] **Step 1: Write the failing tests**

An das Ende von `tools/episto_tui/tests/test_models.py` anhängen:

```python
def test_highlight_round_trip():
    from episto_tui.models import Highlight
    highlight = Highlight(
        datei="0001_vorwort.md", absatz_index=2, absatz_anfang="Der erste Satz",
        farbe="gelb",
    )
    wiederhergestellt = Highlight.from_dict(highlight.to_dict())
    assert wiederhergestellt == highlight
```

Neue Datei `tools/episto_tui/tests/test_library_highlights.py`:

```python
from episto_tui import library
from episto_tui.models import Highlight


def test_read_highlights_ohne_datei_gibt_leere_liste(temp_buch):
    assert library.read_highlights(temp_buch, "0001_erstes-kapitel.md") == []


def test_write_highlight_und_wieder_lesen(temp_buch):
    highlight = Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=0,
        absatz_anfang="Erster Absatz", farbe="gelb",
    )
    library.write_highlight(temp_buch, highlight)

    gelesen = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
    assert len(gelesen) == 1
    assert gelesen[0].farbe == "gelb"


def test_write_highlight_ersetzt_vorhandene_farbe_am_selben_absatz(temp_buch):
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=0,
        absatz_anfang="Erster Absatz", farbe="gelb",
    ))
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=0,
        absatz_anfang="Erster Absatz", farbe="blau",
    ))

    gelesen = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
    assert len(gelesen) == 1
    assert gelesen[0].farbe == "blau"


def test_read_highlights_filtert_nach_datei(temp_buch):
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=0, absatz_anfang="X", farbe="gelb",
    ))
    library.write_highlight(temp_buch, Highlight(
        datei="0002_zweites-kapitel.md", absatz_index=0, absatz_anfang="Y", farbe="rosa",
    ))

    nur_kapitel_2 = library.read_highlights(temp_buch, "0002_zweites-kapitel.md")
    assert len(nur_kapitel_2) == 1
    assert nur_kapitel_2[0].farbe == "rosa"


def test_remove_highlight_entfernt_genau_diesen_absatz(temp_buch):
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=0, absatz_anfang="X", farbe="gelb",
    ))
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=1, absatz_anfang="Y", farbe="rosa",
    ))

    library.remove_highlight(temp_buch, "0001_erstes-kapitel.md", 0)

    gelesen = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
    assert len(gelesen) == 1
    assert gelesen[0].absatz_index == 1


def test_remove_highlight_ohne_datei_tut_nichts(temp_buch):
    library.remove_highlight(temp_buch, "0001_erstes-kapitel.md", 0)  # keine Exception
    assert library.read_highlights(temp_buch, "0001_erstes-kapitel.md") == []


def test_write_highlight_sichert_vorherigen_stand(temp_buch):
    erster = Highlight(datei="a.md", absatz_index=0, absatz_anfang="A", farbe="gelb")
    library.write_highlight(temp_buch, erster)
    zweiter = Highlight(datei="a.md", absatz_index=1, absatz_anfang="B", farbe="rosa")
    library.write_highlight(temp_buch, zweiter)

    backups = list((temp_buch.pfad / "notizen" / "_backup").glob("highlights.*.json"))
    assert len(backups) == 1  # beim ersten Anlegen existierte die Datei noch nicht
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools && python -m pytest episto_tui/tests/test_models.py episto_tui/tests/test_library_highlights.py -v`
Expected: FAIL mit `ImportError: cannot import name 'Highlight'`

- [ ] **Step 3: Implement `Highlight` in `models.py`**

An das Ende von `tools/episto_tui/models.py` anhängen:

```python
@dataclass
class Highlight:
    datei: str
    absatz_index: int
    absatz_anfang: str
    farbe: str

    @staticmethod
    def from_dict(d: dict) -> "Highlight":
        return Highlight(
            datei=d.get("datei", ""),
            absatz_index=d.get("absatz_index", 0),
            absatz_anfang=d.get("absatz_anfang", ""),
            farbe=d.get("farbe", ""),
        )

    def to_dict(self) -> dict:
        return {
            "datei": self.datei,
            "absatz_index": self.absatz_index,
            "absatz_anfang": self.absatz_anfang,
            "farbe": self.farbe,
        }
```

- [ ] **Step 4: Implement die drei Funktionen in `library.py`**

Zeile 5 von `from episto_tui.models import Buch, Kapitel, Tag, Kommentar` zu
`from episto_tui.models import Buch, Kapitel, Tag, Kommentar, Highlight` ändern.

An das Ende von `tools/episto_tui/library.py` (nach `add_kommentar`) anhängen:

```python
def _highlights_pfad(buch: Buch) -> Path:
    return buch.pfad / "notizen" / "highlights.json"


def read_highlights(buch: Buch, dateiname: str) -> list[Highlight]:
    daten = _lade_json_dict(_highlights_pfad(buch))
    if daten is None:
        return []
    return [
        Highlight.from_dict(eintrag)
        for eintrag in _dict_eintraege(daten, "highlights")
        if eintrag.get("datei") == dateiname
    ]


def write_highlight(buch: Buch, highlight: Highlight) -> None:
    pfad = _highlights_pfad(buch)
    # Backup zuerst: macht den Frisch-Geruest-Fallback bei kaputter Datei sicher.
    backup_before_write(buch.pfad, pfad)
    daten = _lade_json_dict(pfad)
    if daten is None:
        daten = {"werk": buch.titel, "highlights": []}
    if not isinstance(daten.get("highlights"), list):
        daten["highlights"] = []
    eintraege = daten["highlights"]
    ersetzt = False
    for i, eintrag in enumerate(eintraege):
        if (
            isinstance(eintrag, dict)
            and eintrag.get("datei") == highlight.datei
            and eintrag.get("absatz_index") == highlight.absatz_index
        ):
            eintraege[i] = highlight.to_dict()
            ersetzt = True
            break
    if not ersetzt:
        eintraege.append(highlight.to_dict())
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def remove_highlight(buch: Buch, dateiname: str, absatz_index: int) -> None:
    pfad = _highlights_pfad(buch)
    daten = _lade_json_dict(pfad)
    if daten is None or not isinstance(daten.get("highlights"), list):
        return
    backup_before_write(buch.pfad, pfad)
    daten["highlights"] = [
        eintrag for eintrag in daten["highlights"]
        if not (
            isinstance(eintrag, dict)
            and eintrag.get("datei") == dateiname
            and eintrag.get("absatz_index") == absatz_index
        )
    ]
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd tools && python -m pytest episto_tui/tests/test_models.py episto_tui/tests/test_library_highlights.py -v`
Expected: alle PASS

- [ ] **Step 6: Commit**

```bash
git add tools/episto_tui/models.py tools/episto_tui/library.py tools/episto_tui/tests/test_models.py tools/episto_tui/tests/test_library_highlights.py
git commit -m "feat: Highlight-Datenmodell und Persistenz (notizen/highlights.json)"
```

---

### Task 2: Klick + Farbtaste in `ReaderPane`

**Files:**
- Modify: `tools/episto_tui/widgets/reader_pane.py` (komplette Datei, siehe Step 3)
- Test: `tools/episto_tui/tests/test_reader_pane.py` (anhängen)

**Interfaces:**
- Consumes: `library.read_highlights`, `library.write_highlight`, `library.remove_highlight` (aus Task 1), `Highlight` (aus Task 1), `textual.widgets.markdown.MarkdownBlock` (öffentliche Reexport-Klasse, NICHT `textual.widgets._markdown.MarkdownParagraph` — jeder Markdown-Block, nicht nur Absätze, damit die Reihenfolge exakt der von `annotate.split_paragraphs()` erzeugten Liste entspricht, ohne einen privaten Importpfad zu brauchen), `events.Click` (aus `textual`, `event.widget` = das tatsächlich angeklickte Widget, da `Click` bubbelt).
- Produces: keine neuen öffentlichen Schnittstellen — `lade_kapitel()`/`fokus_lesebereich()` bleiben signaturkompatibel.

**Hintergrund — warum ein Worker statt eines einfachen Funktionsaufrufs:**
`Markdown.update(text)` gibt ein `AwaitComplete` zurück; seine `MarkdownBlock`-Kindwidgets existieren erst, NACHDEM dieses Awaitable abgeschlossen ist (asynchrones Neu-Mounten). `_zeige_lesemodus()` selbst ist aber bewusst weiterhin eine normale synchrone Methode — würde sie (oder ihre Aufrufer `lade_kapitel()`/die `action_*`-Methoden) `async` werden, würden alle bestehenden Testaufrufe wie `pane.lade_kapitel(temp_buch, kapitel)` (ohne `await`, siehe bestehende Tests) zu nie ausgeführten Coroutinen. Lösung: das Einfärben läuft in einem `self.run_worker(...)`, der intern das `AwaitComplete` abwartet, bevor er die Kind-Widgets stylt.

- [ ] **Step 1: Write the failing tests**

An das Ende von `tools/episto_tui/tests/test_reader_pane.py` anhängen:

```python
@pytest.mark.asyncio
async def test_klick_und_farbtaste_faerbt_den_absatz(temp_buch):
    from episto_tui.models import Kapitel
    from textual.widgets.markdown import MarkdownBlock
    from textual.color import Color
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        await pilot.pause()  # Worker (faerbt nach dem Markdown-Update) braucht eine zweite Pause

        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        assert len(bloecke) == 3  # temp_buch: Kapitel 1 hat drei Absaetze

        await pilot.click(bloecke[1])
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        assert bloecke[1].styles.background == Color.parse("yellow")
        assert bloecke[0].styles.background == Color.parse("transparent")
        assert bloecke[2].styles.background == Color.parse("transparent")


@pytest.mark.asyncio
async def test_gleiche_farbtaste_nochmal_entfernt_das_highlight(temp_buch):
    from episto_tui.models import Kapitel
    from textual.widgets.markdown import MarkdownBlock
    from textual.color import Color
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        await pilot.pause()

        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        await pilot.click(bloecke[0])
        await pilot.press("r")
        await pilot.pause()
        await pilot.pause()
        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        assert bloecke[0].styles.background == Color.parse("pink")

        await pilot.click(bloecke[0])
        await pilot.press("r")
        await pilot.pause()
        await pilot.pause()
        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        assert bloecke[0].styles.background == Color.parse("transparent")


@pytest.mark.asyncio
async def test_andere_farbtaste_wechselt_die_farbe(temp_buch):
    from episto_tui.models import Kapitel
    from textual.widgets.markdown import MarkdownBlock
    from textual.color import Color
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        await pilot.pause()

        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        await pilot.click(bloecke[0])
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        await pilot.click(bloecke[0])
        await pilot.press("b")
        await pilot.pause()
        await pilot.pause()

        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        assert bloecke[0].styles.background == Color.parse("blue")


@pytest.mark.asyncio
async def test_farbtaste_ohne_vorherigen_klick_tut_nichts(temp_buch):
    from episto_tui.models import Kapitel
    from textual.widgets.markdown import MarkdownBlock
    from textual.color import Color
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        await pilot.pause()

        pane.focus()
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()

        gelesen = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
        assert gelesen == []
        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        for block in bloecke:
            assert block.styles.background == Color.parse("transparent")


@pytest.mark.asyncio
async def test_highlight_bleibt_nach_erneutem_laden_des_kapitels_erhalten(temp_buch):
    from episto_tui.models import Kapitel
    from textual.widgets.markdown import MarkdownBlock
    from textual.color import Color
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        kapitel = Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md")
        pane.lade_kapitel(temp_buch, kapitel)
        await pilot.pause()
        await pilot.pause()

        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        await pilot.click(bloecke[2])
        await pilot.press("b")
        await pilot.pause()
        await pilot.pause()

        # Anderes Kapitel oeffnen und zurueck - simuliert einen Tab-/Kapitelwechsel.
        pane.lade_kapitel(temp_buch, Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md"))
        await pilot.pause()
        await pilot.pause()
        pane.lade_kapitel(temp_buch, kapitel)
        await pilot.pause()
        await pilot.pause()

        bloecke = list(app.query_one("#anzeige", Markdown).query(MarkdownBlock))
        assert bloecke[2].styles.background == Color.parse("blue")
```

Am Dateianfang von `tools/episto_tui/tests/test_reader_pane.py` prüfen, ob
`from episto_tui import library` und `from textual.widgets import Markdown`
schon importiert sind (für `library.read_highlights` bzw. `Markdown` in den
neuen Tests) — falls nicht, ergänzen.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools && python -m pytest episto_tui/tests/test_reader_pane.py -v -k "farbtaste or highlight"`
Expected: FAIL (`AttributeError` beim Drücken von "g"/"r"/"b", da diese Bindings noch nicht existieren)

- [ ] **Step 3: `reader_pane.py` komplett ersetzen**

`tools/episto_tui/widgets/reader_pane.py` komplett durch folgenden Inhalt ersetzen:

```python
from __future__ import annotations
from textual import events
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Markdown, TextArea
from textual.widgets.markdown import MarkdownBlock
from textual.binding import Binding
from episto_tui import library, annotate
from episto_tui.models import Buch, Kapitel, Highlight

_HINTERGRUNDFARBE = {"gelb": "yellow", "rosa": "pink", "blau": "blue"}


class ReaderPane(Vertical, can_focus=True):
    # can_focus=True: Vertical ist standardmaessig nicht fokussierbar, aber die
    # BINDINGS (e / ctrl+s / escape / g / r / b) muessen auf einem fokussierten
    # Widget sitzen, damit sie ueberhaupt in die Tastatur-Dispatch-Kette
    # gelangen (siehe Tests, die pane.focus() explizit aufrufen).
    #
    # Im Lesemodus fokussiert fokus_lesebereich() trotzdem NICHT das Pane
    # selbst, sondern #anzeige-scroll: Textuals Bindings-Kette laeuft vom
    # fokussierten Widget aus nach OBEN durch dessen Vorfahren. Waere das
    # Pane fokussiert, kaeme VerticalScrolls eigene up/down/pageup/pagedown-
    # Bindings (fuer echtes Scrollen per Tastatur) nie zum Zug, weil
    # VerticalScroll ein Kind des Pane ist, nicht ein Vorfahre. Mit Fokus
    # auf #anzeige-scroll gilt beides: dessen eigene Scroll-Bindings UND die
    # Bindings dieser Klasse (Vorfahre) werden beide geprüft (empirisch
    # verifiziert, siehe Session vom 2026-09-27 - "kann nicht scrollen").
    BINDINGS = [
        Binding("e", "toggle_edit", "Editieren"),
        Binding("ctrl+s", "speichern", "Speichern"),
        Binding("escape", "verwerfen", "Verwerfen"),
        Binding("g", "highlight_gelb", "Gelb"),
        Binding("r", "highlight_rosa", "Rosa"),
        Binding("b", "highlight_blau", "Blau"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.buch: Buch | None = None
        self.kapitel: Kapitel | None = None
        self.bearbeiten = False
        # Zuletzt per Klick getroffener Absatz - Ziel der naechsten
        # Farbtaste. None, solange noch nicht (oder nicht auf einen
        # MarkdownBlock) geklickt wurde.
        self._aktiver_absatz_index: int | None = None

    def compose(self):
        # Markdown selbst waechst mit height:auto auf volle Inhaltshoehe und
        # hat kein eigenes Scrolling (overflow-y: hidden in seinem
        # DEFAULT_CSS); erst der umgebende VerticalScroll gibt einen
        # Viewport mit tatsaechlichem Scroll vor (Bug: laengere Kapitel
        # liessen sich gar nicht scrollen, ueberstehender Text wurde vom
        # Vertical-Pane selbst nur abgeschnitten).
        with VerticalScroll(id="anzeige-scroll"):
            yield Markdown(id="anzeige")
        yield TextArea(id="editor")

    def on_mount(self) -> None:
        self.query_one("#editor", TextArea).display = False

    def lade_kapitel(self, buch: Buch, kapitel: Kapitel) -> None:
        self.buch = buch
        self.kapitel = kapitel
        self.bearbeiten = False
        self._aktiver_absatz_index = None
        self._zeige_lesemodus()

    def _zeige_lesemodus(self) -> None:
        text = library.read_chapter_text(self.buch, self.kapitel.datei)
        kommentare = library.read_kommentare(self.buch, self.kapitel.datei)
        absaetze = annotate.split_paragraphs(text)
        annotiert, _verwaist = annotate.render_with_markers(absaetze, kommentare)
        anzeige = self.query_one("#anzeige", Markdown)
        update_abschluss = anzeige.update(annotiert)
        highlights = library.read_highlights(self.buch, self.kapitel.datei)
        # Markdown.update() mountet seine MarkdownBlock-Kinder asynchron;
        # erst nach dem zurueckgegebenen Awaitable existieren die NEUEN
        # Bloecke, die hier eingefaerbt werden sollen. Ueber einen Worker
        # statt eines await, damit diese Methode (und ihre synchronen
        # Aufrufer lade_kapitel()/die action_*-Methoden) nicht async werden
        # muss - das wuerde jeden bestehenden synchronen
        # lade_kapitel()-Testaufruf zu einer nie ausgefuehrten Coroutine
        # machen. exclusive=True verhindert, dass ein spaeterer, schnellerer
        # Aufruf von einem noch laufenden aelteren Worker ueberschrieben wird.
        self.run_worker(
            self._faerbe_absaetze(update_abschluss, highlights),
            group="highlight-render", exclusive=True,
        )
        self.query_one("#anzeige-scroll", VerticalScroll).display = True
        self.query_one("#editor", TextArea).display = False
        # Fokus nur setzen, wenn dieses Pane gerade wirklich sichtbar ist:
        # app.py.on_chapter_selected() ruft lade_kapitel() fuer ALLE Panes
        # auf, auch fuer das Pane eines gerade NICHT aktiven Tabs. Wuerde ein
        # verstecktes Pane trotzdem fokussiert, kann Textuals verzoegerte
        # Hide-Kaskade (ContentSwitcher versteckt eine TabPane -> Hide-Events
        # an alle Kind-Widgets, teils erst nach einem spaeteren Refresh
        # zugestellt) den kurz zuvor korrekt gesetzten Fokus des WIRKLICH
        # aktiven Tabs wieder zerstoeren (siehe dritte Scroll-Bug-Runde,
        # 2026-09-27: TagsPane bekam nach dem Kapitel-Wechsel trotz aktivem
        # Tags-Tab ein verspaetetes Hide-Event und wurde geblurred, weil
        # zuvor kurzzeitig das versteckte ReaderPane fokussiert worden war).
        if self._sichtbar_im_baum():
            self.fokus_lesebereich()

    async def _faerbe_absaetze(self, update_abschluss, highlights: list[Highlight]) -> None:
        await update_abschluss
        farbe_je_index = {h.absatz_index: h.farbe for h in highlights}
        bloecke = list(self.query_one("#anzeige", Markdown).query(MarkdownBlock))
        for index, block in enumerate(bloecke):
            farbe = farbe_je_index.get(index)
            block.styles.background = _HINTERGRUNDFARBE.get(farbe, "transparent")

    def _sichtbar_im_baum(self) -> bool:
        """Ob dieses Widget und alle Vorfahren aktuell display=True haben
        (anders als is_on_screen synchron und ohne Compositor-Verzoegerung,
        da ContentSwitcher display beim Tab-Wechsel sofort umschaltet)."""
        knoten = self
        while knoten is not None:
            if not knoten.display:
                return False
            knoten = knoten.parent
        return True

    def fokus_lesebereich(self) -> None:
        """Fuer app.py: legt den Fokus in das gerade sichtbare innere
        Widget dieses Panes (Editor beim Bearbeiten, sonst die scrollbare
        Anzeige) - z.B. beim Wechsel auf den Text-Tab per Zifferntaste, wo
        kein lade_kapitel()-Aufruf stattfindet."""
        if self.bearbeiten:
            self.query_one("#editor", TextArea).focus()
        else:
            self.query_one("#anzeige-scroll", VerticalScroll).focus()

    def on_click(self, event: events.Click) -> None:
        # Bestimmt nur, WELCHER Absatz von der naechsten Farbtaste betroffen
        # waere - faerbt hier noch nichts ein (Design: Klick + Taste, nicht
        # Klick allein). Ein Klick daneben (z.B. auf #anzeige-scroll selbst,
        # wenn der Text nicht die ganze Hoehe ausfuellt) laesst die zuvor
        # per Klick getroffene Auswahl unveraendert stehen.
        if self.bearbeiten or self.buch is None:
            return
        geklickt = event.widget
        if not isinstance(geklickt, MarkdownBlock):
            return
        bloecke = list(self.query_one("#anzeige", Markdown).query(MarkdownBlock))
        if geklickt not in bloecke:
            return
        self._aktiver_absatz_index = bloecke.index(geklickt)

    def action_highlight_gelb(self) -> None:
        self._schalte_highlight("gelb")

    def action_highlight_rosa(self) -> None:
        self._schalte_highlight("rosa")

    def action_highlight_blau(self) -> None:
        self._schalte_highlight("blau")

    def _schalte_highlight(self, farbe: str) -> None:
        if self.bearbeiten or self.buch is None or self._aktiver_absatz_index is None:
            return
        text = library.read_chapter_text(self.buch, self.kapitel.datei)
        absaetze = annotate.split_paragraphs(text)
        index = self._aktiver_absatz_index
        if not (0 <= index < len(absaetze)):
            return
        vorhandene = library.read_highlights(self.buch, self.kapitel.datei)
        bestehend = next((h for h in vorhandene if h.absatz_index == index), None)
        if bestehend is not None and bestehend.farbe == farbe:
            library.remove_highlight(self.buch, self.kapitel.datei, index)
        else:
            library.write_highlight(self.buch, Highlight(
                datei=self.kapitel.datei, absatz_index=index,
                absatz_anfang=absaetze[index][:80], farbe=farbe,
            ))
        self._zeige_lesemodus()

    def action_toggle_edit(self) -> None:
        if self.buch is None:
            return
        if self.bearbeiten:
            self._zeige_lesemodus()
            self.bearbeiten = False
        else:
            text = library.read_chapter_text(self.buch, self.kapitel.datei)
            editor = self.query_one("#editor", TextArea)
            editor.text = text
            editor.display = True
            self.query_one("#anzeige-scroll", VerticalScroll).display = False
            self.bearbeiten = True
            # Tastendruecke muessen im Editor landen -- bliebe der Fokus auf
            # dem Pane, wuerde schon das naechste getippte "e" (Pane-Binding)
            # zurueck in den Lesemodus schalten und die Eingabe verwerfen.
            editor.focus()

    def action_speichern(self) -> None:
        if not self.bearbeiten or self.buch is None:
            return
        neuer_text = self.query_one("#editor", TextArea).text
        library.write_chapter_text(self.buch, self.kapitel.datei, neuer_text)
        self.bearbeiten = False
        self._zeige_lesemodus()

    def action_verwerfen(self) -> None:
        if not self.bearbeiten:
            return
        self.bearbeiten = False
        self._zeige_lesemodus()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools && python -m pytest episto_tui/tests/test_reader_pane.py -v`
Expected: alle PASS. Falls eine der neuen Farb-Tests trotz zweifachem
`await pilot.pause()` noch mit falscher/transparenter Farbe fehlschlägt
(Worker war noch nicht fertig), einen dritten `await pilot.pause()` in genau
diesem Test ergänzen — das ist kein Zeichen für einen Fehler in
`reader_pane.py`, sondern reine Testtiming-Feinjustierung.

- [ ] **Step 5: Volle Suite laufen lassen**

Run: `cd tools && python -m pytest episto_tui/tests -v`
Expected: alle bisherigen Tests weiterhin PASS (keine Regression durch die
neuen Bindings `g`/`r`/`b` oder den neuen `on_click`-Handler), plus die 5
neuen Tests aus diesem Task.

- [ ] **Step 6: Manuelle Farbkontrolle gegen die echte Bibliothek**

Kurzes Wegwerf-Skript im Scratchpad-Verzeichnis (nicht Teil des Commits):
`EpistoApp(root=Path(r"D:\Workspace\!Episto"))` in `run_test()` starten, ein
echtes Kapitel öffnen, einen Absatz anklicken, `g`/`r`/`b` drücken und
`app.export_screenshot()` speichern — prüfen, ob der Text auf der
Hintergrundfarbe noch lesbar ist (Vordergrundfarbe unverändert, nur
Hintergrund gesetzt). Falls `yellow`/`pink`/`blue` zu kräftig/unlesbar
wirken, in `_HINTERGRUNDFARBE` durch gedämpftere Töne ersetzen (z.B. Hex-Werte
statt Namen) — das ist eine reine Werteänderung an einer Stelle, keine
Strukturänderung. Screenshot danach wieder löschen.

- [ ] **Step 7: Commit**

```bash
git add tools/episto_tui/widgets/reader_pane.py tools/episto_tui/tests/test_reader_pane.py
git commit -m "feat: Absatz-Highlighting per Klick + Farbtaste (g/r/b) im Lesemodus"
```
