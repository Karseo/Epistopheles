# Buchübergreifende Sidebar-Ansicht "Begriffe & Definitionen" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die linke Sidebar (`LibraryTree`) bekommt neben "Bibliothek" einen zweiten, gleichrangigen Menüpunkt "Begriffe & Definitionen", der alle Kernbegriffe und Definitionen aus allen Büchern der Bibliothek als eine flache, alphabetisch sortierte Liste zeigt; ein Klick auf einen Eintrag springt ins jeweilige Kapitel.

**Architecture:** Eine neue Funktion `library.read_all_tags(buch)` liest `notizen/tags.json` komplett statt nur ein Kapitel. `LibraryTree` versteckt seinen echten Tree-Root (`show_root = False`) und hängt sowohl den bisherigen Bibliotheks-Baum als auch den neuen flachen Begriffe-Abschnitt als gleichrangige Kinder darunter.

**Tech Stack:** Python, Textual (`Tree`-Widget), pytest + pytest-asyncio (bestehende Muster in `episto_tui/tests/`).

## Global Constraints

- Nur `kern` und `def_` werden buchübergreifend zusammengeführt (siehe Design-Doc `dok/2026-09-27-sidebar-buchuebergreifend-design.md`, Abschnitt "Hintergrund"). `these`, `gegen`, `beleg` bleiben unangetastet.
- Kein Eintrag wird über Bücher/Kapitel hinweg zusammengeführt oder dedupliziert — jedes Vorkommen bleibt ein eigenes, per Klick sprungfähiges Blatt.
- Blatt-Label zeigt nur den vollen Text, keine Buch-/Kapitelangabe (Quelle wird erst nach dem Klick im Lesebereich sichtbar).
- Sortierung: case-insensitive alphabetisch nach dem Eintragstext.
- Die bestehende Tipp-Filterung (`filter_text`) muss weiterhin die gesamte Baumstruktur filtern, inklusive des neuen Abschnitts (Treffer im Eintragstext, Buchtitel oder Autor).
- Bearbeiten bleibt ausschließlich über den bestehenden Weg (Sprung ins Kapitel → Tags-Tab) möglich — die neue Ansicht ist reine Navigation, wie "Stränge"/"Querverweise".
- Rich-Text-Labels müssen als `rich.text.Text(...)` übergeben werden, niemals als blanker `str` (Tree interpretiert `str`-Labels als Rich-Markup; LLM-generierter Text kann `[...]`-Zeichenfolgen enthalten, die sonst crashen oder verschwinden — siehe bestehender Kommentar in `tree_sidebar.py`).

---

### Task 1: `library.read_all_tags()`

**Files:**
- Modify: `tools/episto_tui/library.py` (neue Funktion nach `write_tag`, vor `_parse_kapitel_heading`, d.h. nach der aktuellen Zeile 119)
- Test: `tools/episto_tui/tests/test_library_tags.py` (neue Tests anhängen)

**Interfaces:**
- Consumes: `_lade_json_dict(pfad: Path) -> dict | None`, `_dict_eintraege(daten: dict, schluessel: str) -> list[dict]`, `_tags_pfad(buch: Buch) -> Path` (alle bereits in `library.py` vorhanden), `Tag.from_dict(d: dict) -> Tag` (in `models.py`).
- Produces: `read_all_tags(buch: Buch) -> list[Tag]` — wird in Task 2 von `tree_sidebar.py` genutzt.

- [ ] **Step 1: Write the failing tests**

An das Ende von `tools/episto_tui/tests/test_library_tags.py` anhängen:

```python
def test_read_all_tags_liest_alle_kapitel_eines_buchs(tmp_path):
    import json
    from episto_tui.models import Buch
    buch_pfad = tmp_path / "Autor" / "A" / "B"
    notizen = buch_pfad / "notizen"
    notizen.mkdir(parents=True)
    (notizen / "tags.json").write_text(json.dumps({
        "kapitel": [
            {
                "datei": "0001_erstes-kapitel.md", "kapitel_nr": 1,
                "titel": "Erstes Kapitel", "woerter": 10,
                "these": [], "gegen": [], "kern": ["begriff-eins"],
                "def": ["Begriff eins ist etwas."], "beleg": [], "zusammenfassung": "",
            },
            {
                "datei": "0002_zweites-kapitel.md", "kapitel_nr": 2,
                "titel": "Zweites Kapitel", "woerter": 8,
                "these": [], "gegen": [], "kern": ["begriff-zwei"],
                "def": [], "beleg": [], "zusammenfassung": "",
            },
        ],
    }, ensure_ascii=False), encoding="utf-8")
    buch = Buch(autor="A", titel="B", pfad=buch_pfad)

    alle_tags = library.read_all_tags(buch)

    assert len(alle_tags) == 2
    assert alle_tags[0].kern == ["begriff-eins"]
    assert alle_tags[0].def_ == ["Begriff eins ist etwas."]
    assert alle_tags[1].kern == ["begriff-zwei"]


def test_read_all_tags_ohne_datei_gibt_leere_liste(tmp_path):
    from episto_tui.models import Buch
    buch = Buch(autor="A", titel="B", pfad=tmp_path)
    assert library.read_all_tags(buch) == []


def test_read_all_tags_bei_kaputtem_json_gibt_leere_liste(tmp_path):
    from episto_tui.models import Buch
    buch_pfad = tmp_path / "Autor" / "A" / "B"
    notizen = buch_pfad / "notizen"
    notizen.mkdir(parents=True)
    (notizen / "tags.json").write_text("[]", encoding="utf-8")
    buch = Buch(autor="A", titel="B", pfad=buch_pfad)
    assert library.read_all_tags(buch) == []


def test_read_all_tags_ueberspringt_nicht_dict_eintraege(tmp_path):
    import json
    from episto_tui.models import Buch
    buch_pfad = tmp_path / "Autor" / "A" / "B"
    notizen = buch_pfad / "notizen"
    notizen.mkdir(parents=True)
    (notizen / "tags.json").write_text(json.dumps({
        "kapitel": [
            None,
            "kaputter Eintrag",
            {
                "datei": "0001_erstes-kapitel.md", "kapitel_nr": 1,
                "titel": "Erstes Kapitel", "woerter": 10,
                "these": [], "gegen": [], "kern": ["begriff"],
                "def": [], "beleg": [], "zusammenfassung": "",
            },
        ],
    }, ensure_ascii=False), encoding="utf-8")
    buch = Buch(autor="A", titel="B", pfad=buch_pfad)

    alle_tags = library.read_all_tags(buch)

    assert len(alle_tags) == 1
    assert alle_tags[0].kern == ["begriff"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools && python -m pytest episto_tui/tests/test_library_tags.py -v -k read_all_tags`
Expected: FAIL mit `AttributeError: module 'episto_tui.library' has no attribute 'read_all_tags'`

- [ ] **Step 3: Write minimal implementation**

In `tools/episto_tui/library.py` nach der bestehenden `write_tag`-Funktion (nach Zeile 119, vor `_parse_kapitel_heading`) einfügen:

```python
def read_all_tags(buch: Buch) -> list[Tag]:
    daten = _lade_json_dict(_tags_pfad(buch))
    if daten is None:
        return []
    return [Tag.from_dict(e) for e in _dict_eintraege(daten, "kapitel")]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools && python -m pytest episto_tui/tests/test_library_tags.py -v`
Expected: alle Tests PASS (auch die bereits vorhandenen, unveränderten)

- [ ] **Step 5: Commit**

```bash
git add tools/episto_tui/library.py tools/episto_tui/tests/test_library_tags.py
git commit -m "feat: library.read_all_tags() liest alle Kapitel-Tags eines Buchs auf einmal"
```

---

### Task 2: "Begriffe & Definitionen"-Abschnitt in `LibraryTree`

**Files:**
- Modify: `tools/episto_tui/widgets/tree_sidebar.py` (komplette `rebuild()`-Methode, `__init__`)
- Modify: `tools/episto_tui/tests/test_tree_sidebar.py` (5 bestehende Tests an die neue Baumtiefe anpassen, neue Tests anhängen)
- Modify: `tools/episto_tui/tests/test_app.py` (4 bestehende Tests an die neue Baumtiefe anpassen)

**Interfaces:**
- Consumes: `library.read_all_tags(buch: Buch) -> list[Tag]` (aus Task 1), `library.discover_books(root: Path) -> list[Buch]`, `library.list_chapters(buch: Buch) -> list[Kapitel]` (beide bereits vorhanden), `Tag.kern: list[str]`, `Tag.def_: list[str]`, `Tag.kapitel_nr: int`, `Tag.titel: str`, `Tag.datei: str` (aus `models.py`).
- Produces: keine neuen öffentlichen Schnittstellen — `ChapterSelected` und `on_tree_node_selected` bleiben unverändert; die Baumtiefe unter `LibraryTree.root` ändert sich aber von "Buch-Knoten direkt" zu "Bibliothek-Knoten → Buch-Knoten", was alle Tests betrifft, die `baum.root.children` direkt als Buch-Knoten lesen.

**Wichtiger Kontext — warum bestehende Tests kaputtgehen:** Aktuell ist `LibraryTree`s Tree-Root selbst sichtbar und trägt das Label "Bibliothek"; Bücher sind direkte Kinder von `self.root`. Nach dieser Änderung ist der echte Tree-Root unsichtbar (`show_root = False`), und "Bibliothek" wird zu einem eigenen, sichtbaren Kind-Knoten davon — Bücher hängen jetzt eine Ebene tiefer, unter diesem "Bibliothek"-Knoten. Jeder Test, der bisher `list(baum.root.children)` als Liste der Buch-Knoten gelesen hat, muss jetzt zuerst `list(baum.root.children)[0]` (den "Bibliothek"-Knoten) nehmen und dessen `.children` verwenden.

- [ ] **Step 1: Write the failing tests (neuer Abschnitt)**

An das Ende von `tools/episto_tui/tests/test_tree_sidebar.py` anhängen:

```python
def _schreibe_tags(buch_pfad, kapitel_eintraege) -> None:
    import json
    notizen = buch_pfad / "notizen"
    notizen.mkdir(parents=True, exist_ok=True)
    (notizen / "tags.json").write_text(
        json.dumps({"kapitel": kapitel_eintraege}, ensure_ascii=False), encoding="utf-8")


@pytest.mark.asyncio
async def test_baum_zeigt_begriffe_und_definitionen_abschnitt_bibliotheksweit(tmp_path):
    buch_a = tmp_path / "Autor" / "Autor A" / "Buch A"
    buch_b = tmp_path / "Autor" / "Autor B" / "Buch B"
    (buch_a / "quelle").mkdir(parents=True)
    (buch_b / "quelle").mkdir(parents=True)
    (buch_a / "quelle" / "0001_kap.md").write_text("Text A.", encoding="utf-8")
    (buch_b / "quelle" / "0001_kap.md").write_text("Text B.", encoding="utf-8")
    _schreibe_tags(buch_a, [{
        "datei": "0001_kap.md", "kapitel_nr": 1, "titel": "Kapitel A", "woerter": 1,
        "these": [], "gegen": [], "kern": ["zebra"], "def": ["Anton ist der erste Begriff."],
        "beleg": [], "zusammenfassung": "",
    }])
    _schreibe_tags(buch_b, [{
        "datei": "0001_kap.md", "kapitel_nr": 1, "titel": "Kapitel B", "woerter": 1,
        "these": [], "gegen": [], "kern": ["mitte"], "def": [],
        "beleg": [], "zusammenfassung": "",
    }])

    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        wurzel_kinder = list(baum.root.children)
        assert len(wurzel_kinder) == 2
        assert "Bibliothek" in str(wurzel_kinder[0].label)
        begriffe_knoten = wurzel_kinder[1]
        assert "Begriffe" in str(begriffe_knoten.label)
        assert begriffe_knoten.is_expanded is False

        texte = [str(kind.label) for kind in begriffe_knoten.children]
        # Erwartete alphabetische (case-insensitive) Reihenfolge ueber BEIDE
        # Buecher hinweg, ohne Buch-Zwischenknoten: die Definition beginnt
        # mit "Anton" und steht daher vor "mitte" und "zebra".
        assert texte == ["Anton ist der erste Begriff.", "mitte", "zebra"]


@pytest.mark.asyncio
async def test_klick_auf_begriff_feuert_chapter_selected(tmp_path):
    buch_a = tmp_path / "Autor" / "Autor A" / "Buch A"
    (buch_a / "quelle").mkdir(parents=True)
    (buch_a / "quelle" / "0001_kap.md").write_text("Text A.", encoding="utf-8")
    _schreibe_tags(buch_a, [{
        "datei": "0001_kap.md", "kapitel_nr": 1, "titel": "Kapitel A", "woerter": 1,
        "these": [], "gegen": [], "kern": ["einzelbegriff"], "def": [],
        "beleg": [], "zusammenfassung": "",
    }])

    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        begriffe_knoten = list(baum.root.children)[1]
        begriff_blatt = list(begriffe_knoten.children)[0]
        baum.select_node(begriff_blatt)
        await pilot.pause()
        assert app.letztes_ereignis is not None
        assert app.letztes_ereignis.kapitel.datei == "0001_kap.md"
        assert app.letztes_ereignis.buch.titel == "Buch A"


@pytest.mark.asyncio
async def test_buch_ohne_kern_oder_def_erzeugt_keine_leeren_eintraege(tmp_path, temp_buch):
    # temp_buch (aus conftest) hat kern=["testbegriff"], def=[] fuer Kapitel 1
    # und gar keinen Tag-Eintrag fuer Kapitel 2 - beides darf nicht crashen
    # und darf keine leeren Bl\u00e4tter erzeugen.
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        begriffe_knoten = list(baum.root.children)[1]
        texte = [str(kind.label) for kind in begriffe_knoten.children]
        assert texte == ["testbegriff"]


@pytest.mark.asyncio
async def test_tippfilterung_filtert_auch_begriffe_abschnitt(tmp_path):
    buch_a = tmp_path / "Autor" / "Autor A" / "Buch A"
    (buch_a / "quelle").mkdir(parents=True)
    (buch_a / "quelle" / "0001_kap.md").write_text("Text A.", encoding="utf-8")
    _schreibe_tags(buch_a, [{
        "datei": "0001_kap.md", "kapitel_nr": 1, "titel": "Kapitel A", "woerter": 1,
        "these": [], "gegen": [], "kern": ["passend", "anderswert"], "def": [],
        "beleg": [], "zusammenfassung": "",
    }])

    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        baum.focus()
        await pilot.press("p", "a", "s", "s")  # "pass" -> nur "passend"
        begriffe_knoten = list(baum.root.children)[1]
        texte = [str(kind.label) for kind in begriffe_knoten.children]
        assert texte == ["passend"]
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `cd tools && python -m pytest episto_tui/tests/test_tree_sidebar.py -v -k "begriff or klick_auf_begriff or ohne_kern"`
Expected: FAIL (`IndexError` oder `AssertionError`, da `list(baum.root.children)` heute nur Buch-Knoten enthält und es keinen "Begriffe & Definitionen"-Knoten gibt)

- [ ] **Step 3: Restructure `LibraryTree`**

`tools/episto_tui/widgets/tree_sidebar.py` komplett durch folgenden Inhalt ersetzen:

```python
from __future__ import annotations
from pathlib import Path
from rich.text import Text
from textual.widgets import Tree
from textual.message import Message
from episto_tui import library
from episto_tui.models import Buch, Kapitel

# Nur diese beiden Felder werden bibliotheksweit zusammengefuehrt: these/
# gegen/beleg haben in den Tagging-Daten keine feste Laenge/Zuordnung
# zueinander (siehe dok/2026-09-27-sidebar-buchuebergreifend-design.md).
_BEGRIFF_FELDER = ["kern", "def_"]


class ChapterSelected(Message):
    def __init__(self, buch: Buch, kapitel: Kapitel) -> None:
        self.buch = buch
        self.kapitel = kapitel
        super().__init__()


class LibraryTree(Tree):
    def __init__(self, root: Path) -> None:
        super().__init__("Wurzel")
        # Der echte Tree-Root ist nur ein unsichtbarer Behaelter: "Bibliothek"
        # und "Begriffe & Definitionen" haengen als gleichrangige, sichtbare
        # Kinder darunter, statt dass Buecher direkt am Root haengen.
        self.show_root = False
        self.root_pfad = root
        self.filter_text = ""

    def on_mount(self) -> None:
        self.rebuild()

    def rebuild(self) -> None:
        self.root.remove_children()
        buecher = library.discover_books(self.root_pfad)
        filter_lower = self.filter_text.lower()
        self._baue_bibliothek_knoten(buecher, filter_lower)
        self._baue_begriffe_knoten(buecher, filter_lower)
        self.root.expand()

    def _baue_bibliothek_knoten(self, buecher: list[Buch], filter_lower: str) -> None:
        bibliothek_knoten = self.root.add(Text("Bibliothek"), expand=True)
        for buch in buecher:
            kapitel_liste = library.list_chapters(buch)
            passende = [
                k for k in kapitel_liste
                if not filter_lower
                or filter_lower in buch.titel.lower()
                or filter_lower in buch.autor.lower()
                or filter_lower in k.titel.lower()
            ]
            if not passende:
                continue
            # Text(...) statt str: Tree liest str-Labels als Rich-Markup; Titel
            # sind Daten und sollen woertlich erscheinen ("[/]" wuerde crashen).
            buch_knoten = bibliothek_knoten.add(Text(f"{buch.autor} — {buch.titel}"), expand=True)
            for kapitel in passende:
                buch_knoten.add_leaf(Text(f"{kapitel.nr}. {kapitel.titel}"), data=(buch, kapitel))

    def _baue_begriffe_knoten(self, buecher: list[Buch], filter_lower: str) -> None:
        # Flach und bibliotheksweit, bewusst OHNE Buch-Zwischenknoten (siehe
        # Design-Doc): Kernbegriffe und Definitionen werden nicht verknuepft
        # oder zusammengefuehrt, jedes Vorkommen bleibt ein eigenes Blatt.
        eintraege: list[tuple[str, Buch, Kapitel]] = []
        for buch in buecher:
            for tag in library.read_all_tags(buch):
                kapitel = Kapitel(tag.kapitel_nr, tag.titel, tag.datei)
                for feld in _BEGRIFF_FELDER:
                    for text in getattr(tag, feld):
                        if (
                            not filter_lower
                            or filter_lower in text.lower()
                            or filter_lower in buch.titel.lower()
                            or filter_lower in buch.autor.lower()
                        ):
                            eintraege.append((text, buch, kapitel))
        eintraege.sort(key=lambda eintrag: eintrag[0].lower())
        begriffe_knoten = self.root.add(Text("Begriffe & Definitionen"), expand=False)
        for text, buch, kapitel in eintraege:
            begriffe_knoten.add_leaf(Text(text), data=(buch, kapitel))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.filter_text = ""
            self.rebuild()
            event.stop()
        elif event.key == "backspace":
            self.filter_text = self.filter_text[:-1]
            self.rebuild()
            event.stop()
        elif event.character and len(event.character) == 1 and event.character.isprintable():
            self.filter_text += event.character
            self.rebuild()
            event.stop()

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        if event.node.data is not None:
            buch, kapitel = event.node.data
            self.post_message(ChapterSelected(buch, kapitel))
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `cd tools && python -m pytest episto_tui/tests/test_tree_sidebar.py -v`
Expected: die 4 neuen Tests PASS; die 5 bestehenden (`test_baum_zeigt_buch_und_kapitel`, `test_tippfilterung_grenzt_kapitel_ein`, `test_escape_setzt_filter_zurueck`, `test_auswahl_eines_kapitels_feuert_chapter_selected`, `test_baum_zeigt_titel_mit_eckigen_klammern_woertlich`) schlagen jetzt fehl — das wird im naechsten Schritt behoben.

- [ ] **Step 5: Fix breaking existing tests in `test_tree_sidebar.py`**

In `tools/episto_tui/tests/test_tree_sidebar.py` genau diese fünf Stellen ändern (jeweils wird ein zusätzlicher Zugriff auf den "Bibliothek"-Knoten vor die Buch-Knoten-Liste eingeschoben):

```python
# test_baum_zeigt_buch_und_kapitel: ersetze
        buch_knoten = list(baum.root.children)
        assert len(buch_knoten) == 1
        assert "Testbuch" in str(buch_knoten[0].label)
        assert len(buch_knoten[0].children) == 2
# durch
        bibliothek_knoten = list(baum.root.children)[0]
        buch_knoten = list(bibliothek_knoten.children)
        assert len(buch_knoten) == 1
        assert "Testbuch" in str(buch_knoten[0].label)
        assert len(buch_knoten[0].children) == 2
```

```python
# test_tippfilterung_grenzt_kapitel_ein: ersetze
        buch_knoten = list(baum.root.children)
        assert len(buch_knoten) == 1
        assert len(buch_knoten[0].children) == 1
        assert "Zweites" in str(buch_knoten[0].children[0].label)
# durch
        bibliothek_knoten = list(baum.root.children)[0]
        buch_knoten = list(bibliothek_knoten.children)
        assert len(buch_knoten) == 1
        assert len(buch_knoten[0].children) == 1
        assert "Zweites" in str(buch_knoten[0].children[0].label)
```

```python
# test_escape_setzt_filter_zurueck: ersetze
        buch_knoten = list(baum.root.children)
        assert len(buch_knoten[0].children) == 2
# durch
        bibliothek_knoten = list(baum.root.children)[0]
        buch_knoten = list(bibliothek_knoten.children)
        assert len(buch_knoten[0].children) == 2
```

```python
# test_auswahl_eines_kapitels_feuert_chapter_selected: ersetze
        buch_knoten = list(baum.root.children)[0]
        kapitel_knoten = buch_knoten.children[0]
# durch
        bibliothek_knoten = list(baum.root.children)[0]
        buch_knoten = list(bibliothek_knoten.children)[0]
        kapitel_knoten = buch_knoten.children[0]
```

```python
# test_baum_zeigt_titel_mit_eckigen_klammern_woertlich: ersetze
        buch_knoten = list(baum.root.children)[0]
        assert buch_knoten.children[0].label.plain == "1. Kapitel [b]eins[/b] [/]"
# durch
        bibliothek_knoten = list(baum.root.children)[0]
        buch_knoten = list(bibliothek_knoten.children)[0]
        assert buch_knoten.children[0].label.plain == "1. Kapitel [b]eins[/b] [/]"
```

- [ ] **Step 6: Fix breaking existing tests in `test_app.py`**

In `tools/episto_tui/tests/test_app.py` genau diese vier Stellen ändern:

```python
# test_app_zeigt_baum_und_kann_kapitel_oeffnen (Zeile 29-30): ersetze
        buch_knoten = list(baum.root.children)[0]
        kapitel_knoten = buch_knoten.children[0]
# durch
        bibliothek_knoten = list(baum.root.children)[0]
        buch_knoten = list(bibliothek_knoten.children)[0]
        kapitel_knoten = buch_knoten.children[0]
```

```python
# test_q_und_ziffern_werden_normal_in_editor_getippt (Zeile 122-123): ersetze
        buch_knoten = list(baum.root.children)[0]
        kapitel_knoten = buch_knoten.children[0]
# durch
        bibliothek_knoten = list(baum.root.children)[0]
        buch_knoten = list(bibliothek_knoten.children)[0]
        kapitel_knoten = buch_knoten.children[0]
```

```python
# test_fehler_in_einem_pane_legt_app_nicht_lahm (Zeile 184): ersetze
        baum.select_node(list(baum.root.children)[0].children[0])
# durch
        baum.select_node(list(baum.root.children)[0].children[0].children[0])
```

```python
# test_app_mit_echten_kaputten_dateien (Zeile 210-212): ersetze
        buch_knoten = list(baum.root.children)[0]
        assert len(buch_knoten.children) == 2  # Glob-Fallback
        baum.select_node(buch_knoten.children[0])
# durch
        bibliothek_knoten = list(baum.root.children)[0]
        buch_knoten = list(bibliothek_knoten.children)[0]
        assert len(buch_knoten.children) == 2  # Glob-Fallback
        baum.select_node(buch_knoten.children[0])
```

- [ ] **Step 7: Run the full suite to verify everything passes**

Run: `cd tools && python -m pytest episto_tui/tests -v`
Expected: alle Tests PASS (Gesamtzahl = bisherige 92 + 4 neue = 96)

- [ ] **Step 8: Manuelle Verifikation gegen die echte Bibliothek**

Kurzes Python-Skript im Scratchpad-Verzeichnis ausführen (nicht Teil des Repos), das `EpistoApp(root=Path(r"D:\Workspace\!Episto"))` in `run_test()` startet, den Baum aufbaut und prüft: `list(baum.root.children)` hat 2 Einträge ("Bibliothek", "Begriffe & Definitionen"), der zweite ist eingeklappt und enthält mehrere hundert alphabetisch sortierte Blätter aus den bereits getaggten Büchern (Kant, Popper, Bourdieu, Kahneman, Parvini, Barclay). Danach die Skriptdatei wieder löschen.

- [ ] **Step 9: Commit**

```bash
git add tools/episto_tui/widgets/tree_sidebar.py tools/episto_tui/tests/test_tree_sidebar.py tools/episto_tui/tests/test_app.py
git commit -m "feat: bibliotheksweite Sidebar-Ansicht 'Begriffe & Definitionen' neben 'Bibliothek'"
```

---

## Nicht Teil dieses Plans

Thesen, Gegenpositionen und Belege bibliotheksweit darzustellen (thematisch gruppiert bzw. einer These zugeordnet) erfordert eine Erweiterung des Tagging-Schemas (`taggen.ps1`) und Neu-Tagging aller Bücher — das ist ein eigenes, separates Vorhaben (siehe Design-Doc, Abschnitt "Hintergrund").
