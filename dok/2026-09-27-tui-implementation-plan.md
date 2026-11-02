# EPISTO TUI (V1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eine Python/Textual-TUI (`episto_tui`), die die !Episto-Bibliothek zum
Lesen aufbereitet (gerendertes Markdown statt Rohtext) und dabei den
Kapiteltext, die Tag-Metadaten und Absatz-Kommentare direkt editierbar macht;
Stränge und Querverweise werden angezeigt (nur Anzeige in V1).

**Architecture:** Eine einzige Dateizugriffs-Schicht (`library.py`) kennt alle
Episto-Dateikonventionen; Widgets (ein Tab je Datenart) rufen ausschließlich
diese Schicht auf, nie das Dateisystem direkt. Persistentes Split-Layout:
Baum-Sidebar (Autor→Buch→Kapitel, Tippfilterung) links, `TabbedContent`
rechts. Kein Cache — jede Kapitelauswahl liest frisch von der Platte.

**Tech Stack:** Python 3.12, Textual (TUI-Framework), pytest (Tests). Beide
bereits installiert (`textual==8.2.8`, `pytest==9.0.2`), siehe Task 1 für die
`requirements.txt`.

**Spec:** [dok/2026-09-27-tui-design.md](2026-09-27-tui-design.md)

## Global Constraints

- Python 3.12, Textual >= 8.2, pytest >= 9.0 (siehe Tech Stack).
- Vor jedem Schreiben von `quelle\*.md` **oder** `notizen\tags.json` **oder**
  `notizen\kommentare.json`: Backup nach `notizen\_backup\<name>.<YYYYMMDD-HHMMSS><ext>`
  (siehe Spec Abschnitt 3).
- Alle geschriebenen Textdateien: UTF-8, LF-Zeilenenden (bestehende Episto-
  Konvention, siehe `ebook-build.py`/`lektor-zu-episto.py`).
- Kein Datei-Locking — Einzelnutzer-Tool, direkter Dateizugriff ohne Cache
  (Spec Abschnitt 2/5).
- Fehlende/kaputte Metadaten-Dateien führen zu einem Platzhalter-Hinweis in
  der UI, nie zu einem Absturz (Spec Abschnitt 5).
- Basisverzeichnis des neuen Codes: `D:\Workspace\!Episto\tools\episto_tui\`.

---

## Task 1: Projekt-Grundgerüst, Datenmodelle, Test-Fixtures

**Files:**
- Create: `D:\Workspace\!Episto\tools\episto_tui\__init__.py`
- Create: `D:\Workspace\!Episto\tools\episto_tui\models.py`
- Create: `D:\Workspace\!Episto\tools\episto_tui\requirements.txt`
- Create: `D:\Workspace\!Episto\tools\episto_tui\tests\__init__.py`
- Create: `D:\Workspace\!Episto\tools\episto_tui\tests\conftest.py`
- Test: `D:\Workspace\!Episto\tools\episto_tui\tests\test_models.py`

**Interfaces:**
- Produces: `Buch(autor: str, titel: str, pfad: Path)`,
  `Kapitel(nr: int, titel: str, datei: str)`,
  `Tag(datei, kapitel_nr, titel, woerter, these, gegen, kern, def_, beleg, zusammenfassung)`
  mit `.to_dict()`/`Tag.from_dict(d)`,
  `Kommentar(datei, absatz_index, absatz_anfang, text, erstellt)` mit
  `.to_dict()`/`Kommentar.from_dict(d)`.
- Produces: Pytest-Fixture `temp_buch(tmp_path)` → liefert ein
  `episto_tui.models.Buch`, dessen `pfad` auf ein frisch angelegtes
  Verzeichnis mit realistischer Episto-Struktur zeigt (siehe Fixture-Code
  unten) — wird von allen späteren Tasks wiederverwendet.

- [ ] **Step 1: Verzeichnisse und leere `__init__.py` anlegen**

```bash
mkdir -p "D:\Workspace\!Episto\tools\episto_tui\widgets"
mkdir -p "D:\Workspace\!Episto\tools\episto_tui\tests"
```
Dann `episto_tui\__init__.py` und `episto_tui\widgets\__init__.py` und
`episto_tui\tests\__init__.py` als leere Dateien anlegen.

- [ ] **Step 2: `requirements.txt` schreiben**

```
textual>=8.2
pytest>=9.0
```

- [ ] **Step 3: Fehlschlagenden Test für `Tag`/`Kommentar` Round-Trip schreiben**

`episto_tui\tests\test_models.py`:
```python
from episto_tui.models import Tag, Kommentar


def test_tag_round_trip():
    tag = Tag(
        datei="0001_vorwort.md", kapitel_nr=1, titel="Vorwort", woerter=100,
        these=["These 1"], gegen=[], kern=["kern1", "kern2"], def_=[],
        beleg=["Beleg 1"], zusammenfassung="Kurz.",
    )
    wiederhergestellt = Tag.from_dict(tag.to_dict())
    assert wiederhergestellt == tag


def test_tag_from_dict_mit_fehlenden_feldern():
    tag = Tag.from_dict({"datei": "x.md"})
    assert tag.these == []
    assert tag.zusammenfassung == ""


def test_kommentar_round_trip():
    kommentar = Kommentar(
        datei="0001_vorwort.md", absatz_index=2, absatz_anfang="Der erste Satz",
        text="Nachfragen bei Popper", erstellt="2026-09-27 14:00",
    )
    wiederhergestellt = Kommentar.from_dict(kommentar.to_dict())
    assert wiederhergestellt == kommentar
```

- [ ] **Step 2: Test ausführen, Fehlschlag bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_models.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'episto_tui.models'`

- [ ] **Step 3: `models.py` implementieren**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Buch:
    autor: str
    titel: str
    pfad: Path


@dataclass
class Kapitel:
    nr: int
    titel: str
    datei: str


@dataclass
class Tag:
    datei: str
    kapitel_nr: int
    titel: str
    woerter: int
    these: list[str] = field(default_factory=list)
    gegen: list[str] = field(default_factory=list)
    kern: list[str] = field(default_factory=list)
    def_: list[str] = field(default_factory=list)  # "def" ist ein Python-Schluesselwort
    beleg: list[str] = field(default_factory=list)
    zusammenfassung: str = ""

    @staticmethod
    def from_dict(d: dict) -> "Tag":
        return Tag(
            datei=d.get("datei", ""),
            kapitel_nr=d.get("kapitel_nr", 0),
            titel=d.get("titel", ""),
            woerter=d.get("woerter", 0),
            these=list(d.get("these", [])),
            gegen=list(d.get("gegen", [])),
            kern=list(d.get("kern", [])),
            def_=list(d.get("def", [])),
            beleg=list(d.get("beleg", [])),
            zusammenfassung=d.get("zusammenfassung", ""),
        )

    def to_dict(self) -> dict:
        return {
            "datei": self.datei,
            "kapitel_nr": self.kapitel_nr,
            "titel": self.titel,
            "woerter": self.woerter,
            "these": list(self.these),
            "gegen": list(self.gegen),
            "kern": list(self.kern),
            "def": list(self.def_),
            "beleg": list(self.beleg),
            "zusammenfassung": self.zusammenfassung,
        }


@dataclass
class Kommentar:
    datei: str
    absatz_index: int
    absatz_anfang: str
    text: str
    erstellt: str

    @staticmethod
    def from_dict(d: dict) -> "Kommentar":
        return Kommentar(
            datei=d.get("datei", ""),
            absatz_index=d.get("absatz_index", 0),
            absatz_anfang=d.get("absatz_anfang", ""),
            text=d.get("text", ""),
            erstellt=d.get("erstellt", ""),
        )

    def to_dict(self) -> dict:
        return {
            "datei": self.datei,
            "absatz_index": self.absatz_index,
            "absatz_anfang": self.absatz_anfang,
            "text": self.text,
            "erstellt": self.erstellt,
        }
```

- [ ] **Step 4: Test ausführen, Erfolg bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_models.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Gemeinsame Test-Fixture `conftest.py` schreiben**

Wird von allen späteren Tasks wiederverwendet — baut eine realistische
Episto-Buchstruktur unter einem temporären Verzeichnis.

`episto_tui\tests\conftest.py`:
```python
from __future__ import annotations
import json
import pytest
from episto_tui.models import Buch


@pytest.fixture
def temp_buch(tmp_path) -> Buch:
    buch_pfad = tmp_path / "Autor" / "Testautor, Theo" / "Testbuch"
    quelle = buch_pfad / "quelle"
    notizen = buch_pfad / "notizen"
    quelle.mkdir(parents=True)
    notizen.mkdir(parents=True)
    (notizen / "straenge").mkdir()
    (buch_pfad / "querbezuege").mkdir()

    (quelle / "0001_erstes-kapitel.md").write_text(
        "Erster Absatz des ersten Kapitels.\n\n"
        "Zweiter Absatz mit mehr Inhalt zum Testen.\n\n"
        "Dritter Absatz, der letzte hier.",
        encoding="utf-8",
    )
    (quelle / "0002_zweites-kapitel.md").write_text(
        "Einziger Absatz des zweiten Kapitels.",
        encoding="utf-8",
    )
    (quelle / "_kapitel_index.json").write_text(
        json.dumps([
            {"nr": 1, "titel": "Erstes Kapitel", "datei": "0001_erstes-kapitel.md"},
            {"nr": 2, "titel": "Zweites Kapitel", "datei": "0002_zweites-kapitel.md"},
        ], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (notizen / "tags.json").write_text(
        json.dumps({
            "werk": "Testbuch", "autor": "Testautor, Theo", "sprache": "de",
            "eintraege": 1, "erstellt": "2026-09-27 10:00",
            "kapitel": [{
                "datei": "0001_erstes-kapitel.md", "kapitel_nr": 1,
                "titel": "Erstes Kapitel", "woerter": 12,
                "these": ["Testthese"], "gegen": [], "kern": ["testbegriff"],
                "def": [], "beleg": [], "zusammenfassung": "Kurze Zusammenfassung.",
            }],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (notizen / "straenge" / "test-strang.md").write_text(
        "---\n"
        "strang: Test-Strang\n"
        "slug: test-strang\n"
        "werk: Testbuch\n"
        "treffer: 1\n"
        "---\n\n"
        "# Strang: Test-Strang\n\n"
        "Definition des Test-Strangs.\n\n"
        "## Fundstellen (1)\n\n"
        "### Kapitel 1 · Erstes Kapitel\n"
        "- Testthese\n",
        encoding="utf-8",
    )

    (buch_pfad / "querbezuege" / "querbezuege.json").write_text(
        json.dumps({
            "werk": "testbuch", "autor": "testautor",
            "bezuege": [{
                "ziel": "extern_werk", "autor": "Externer Autor",
                "titel": "Externes Werk", "relation": "ergaenzt",
                "notiz": "Testnotiz.",
            }],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return Buch(autor="Testautor, Theo", titel="Testbuch", pfad=buch_pfad)
```

- [ ] **Step 6: Commit**

```bash
git -C "D:\Workspace\!Episto" add tools/episto_tui 2>&1 || echo "kein Git-Repo - Commit uebersprungen (siehe dok/2026-09-27-tui-design.md)"
```
(`!Episto` ist kein Git-Repo — dieser Schritt ist ein No-Op, in jedem
folgenden Task identisch. Falls das Archiv später versioniert wird, kann
dieser Befehl dann tatsächlich committen.)

---

## Task 2: Backup-Modul

**Files:**
- Create: `D:\Workspace\!Episto\tools\episto_tui\backup.py`
- Test: `D:\Workspace\!Episto\tools\episto_tui\tests\test_backup.py`

**Interfaces:**
- Consumes: nichts (reine `pathlib`/`shutil`-Logik).
- Produces: `backup_before_write(buch_root: Path, original_path: Path) -> Path | None`

- [ ] **Step 1: Fehlschlagenden Test schreiben**

`episto_tui\tests\test_backup.py`:
```python
from episto_tui.backup import backup_before_write


def test_backup_kopiert_vorhandene_datei(tmp_path):
    original = tmp_path / "quelle" / "kapitel.md"
    original.parent.mkdir(parents=True)
    original.write_text("Originalinhalt", encoding="utf-8")

    ziel = backup_before_write(tmp_path, original)

    assert ziel is not None
    assert ziel.exists()
    assert ziel.read_text(encoding="utf-8") == "Originalinhalt"
    assert ziel.parent == tmp_path / "notizen" / "_backup"
    assert original.read_text(encoding="utf-8") == "Originalinhalt"


def test_backup_gibt_none_zurueck_wenn_datei_fehlt(tmp_path):
    original = tmp_path / "quelle" / "nicht-vorhanden.md"
    ziel = backup_before_write(tmp_path, original)
    assert ziel is None


def test_backup_dateiname_enthaelt_zeitstempel(tmp_path):
    original = tmp_path / "notizen" / "tags.json"
    original.parent.mkdir(parents=True)
    original.write_text("{}", encoding="utf-8")

    ziel = backup_before_write(tmp_path, original)

    assert ziel.name.startswith("tags.")
    assert ziel.name.endswith(".json")
    assert ziel.name != "tags.json"
```

- [ ] **Step 2: Test ausführen, Fehlschlag bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_backup.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'episto_tui.backup'`

- [ ] **Step 3: `backup.py` implementieren**

```python
from __future__ import annotations
import shutil
from datetime import datetime
from pathlib import Path


def backup_before_write(buch_root: Path, original_path: Path) -> Path | None:
    """Sichert `original_path` nach notizen\\_backup\\<name>.<Zeitstempel><ext>,
    bevor die Datei ueberschrieben wird. Gibt None zurueck, wenn die Datei
    noch nicht existiert (nichts zu sichern)."""
    if not original_path.exists():
        return None
    backup_dir = buch_root / "notizen" / "_backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    zeitstempel = datetime.now().strftime("%Y%m%d-%H%M%S")
    ziel = backup_dir / f"{original_path.stem}.{zeitstempel}{original_path.suffix}"
    shutil.copy2(original_path, ziel)
    return ziel
```

- [ ] **Step 4: Test ausführen, Erfolg bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_backup.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git -C "D:\Workspace\!Episto" add tools/episto_tui/backup.py tools/episto_tui/tests/test_backup.py 2>&1 || true
```

---

## Task 3: Absatz- & Kommentar-Textlogik (`annotate.py`)

**Files:**
- Create: `D:\Workspace\!Episto\tools\episto_tui\annotate.py`
- Test: `D:\Workspace\!Episto\tools\episto_tui\tests\test_annotate.py`

**Interfaces:**
- Consumes: `episto_tui.models.Kommentar`
- Produces: `split_paragraphs(text: str) -> list[str]`,
  `locate_paragraph(paragraphs: list[str], absatz_index: int, absatz_anfang: str) -> int | None`,
  `render_with_markers(paragraphs: list[str], kommentare: list[Kommentar]) -> tuple[str, list[Kommentar]]`

- [ ] **Step 1: Fehlschlagenden Test schreiben**

`episto_tui\tests\test_annotate.py`:
```python
from episto_tui.annotate import split_paragraphs, locate_paragraph, render_with_markers
from episto_tui.models import Kommentar


def test_split_paragraphs_trennt_an_leerzeilen():
    text = "Erster Absatz.\n\nZweiter Absatz.\n\n\nDritter Absatz."
    assert split_paragraphs(text) == [
        "Erster Absatz.", "Zweiter Absatz.", "Dritter Absatz.",
    ]


def test_locate_paragraph_per_index_wenn_text_passt():
    absaetze = ["Erster Absatz.", "Zweiter Absatz."]
    treffer = locate_paragraph(absaetze, 1, "Zweiter Absatz")
    assert treffer == 1


def test_locate_paragraph_fallback_bei_verschobenem_index():
    absaetze = ["Neuer Absatz davor.", "Erster Absatz.", "Zweiter Absatz."]
    # absatz_index zeigt noch auf die alte Position (0), aber der Text ist jetzt an Position 1
    treffer = locate_paragraph(absaetze, 0, "Erster Absatz")
    assert treffer == 1


def test_locate_paragraph_gibt_none_bei_verwaistem_kommentar():
    absaetze = ["Ganz anderer Text."]
    treffer = locate_paragraph(absaetze, 5, "Text, der nicht mehr vorkommt")
    assert treffer is None


def test_render_with_markers_haengt_marke_an_richtigen_absatz():
    absaetze = ["Erster Absatz.", "Zweiter Absatz."]
    kommentare = [Kommentar(
        datei="x.md", absatz_index=1, absatz_anfang="Zweiter Absatz",
        text="Notiz", erstellt="2026-09-27",
    )]
    ergebnis, verwaist = render_with_markers(absaetze, kommentare)
    assert "Erster Absatz.\n\nZweiter Absatz.[¹]" == ergebnis
    assert verwaist == []


def test_render_with_markers_meldet_verwaiste_kommentare():
    absaetze = ["Einziger Absatz."]
    kommentare = [Kommentar(
        datei="x.md", absatz_index=9, absatz_anfang="Text, der nicht mehr existiert",
        text="Notiz", erstellt="2026-09-27",
    )]
    ergebnis, verwaist = render_with_markers(absaetze, kommentare)
    assert ergebnis == "Einziger Absatz."
    assert len(verwaist) == 1
```

- [ ] **Step 2: Test ausführen, Fehlschlag bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_annotate.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'episto_tui.annotate'`

- [ ] **Step 3: `annotate.py` implementieren**

```python
from __future__ import annotations
import re
from episto_tui.models import Kommentar

_ZIFFERN = "¹²³⁴⁵⁶⁷⁸⁹"


def split_paragraphs(text: str) -> list[str]:
    rohabsaetze = re.split(r"\n\s*\n", text.strip())
    return [a.strip() for a in rohabsaetze if a.strip()]


def locate_paragraph(paragraphs: list[str], absatz_index: int, absatz_anfang: str) -> int | None:
    """Findet den Absatz zu einem Kommentar. Bevorzugt absatz_index, wenn der
    Text dort noch passt; sucht sonst nach dem Textanfang im ganzen Kapitel
    (robust gegen kleine Verschiebungen durch Edits). None = verwaist."""
    praefix = absatz_anfang[:40].strip()
    if not praefix:
        return None
    if 0 <= absatz_index < len(paragraphs) and paragraphs[absatz_index].startswith(praefix[:20]):
        return absatz_index
    for i, absatz in enumerate(paragraphs):
        if absatz.startswith(praefix):
            return i
    return None


def render_with_markers(paragraphs: list[str], kommentare: list[Kommentar]) -> tuple[str, list[Kommentar]]:
    """Haengt an jeden kommentierten Absatz eine hochgestellte Marke [¹][²]...
    Reihenfolge der Marken folgt der Lesereihenfolge der Absaetze, nicht der
    Erstellungsreihenfolge der Kommentare. Gibt (annotierter Text, verwaiste
    Kommentare) zurueck."""
    treffer: list[tuple[int, Kommentar]] = []
    verwaist: list[Kommentar] = []
    for kommentar in kommentare:
        index = locate_paragraph(paragraphs, kommentar.absatz_index, kommentar.absatz_anfang)
        if index is None:
            verwaist.append(kommentar)
        else:
            treffer.append((index, kommentar))
    treffer.sort(key=lambda paar: paar[0])

    marken_je_absatz: dict[int, str] = {}
    for zaehler, (index, _kommentar) in enumerate(treffer):
        ziffer = _ZIFFERN[zaehler % len(_ZIFFERN)] if zaehler < len(_ZIFFERN) else str(zaehler + 1)
        marken_je_absatz[index] = marken_je_absatz.get(index, "") + f"[{ziffer}]"

    zeilen = [absatz + marken_je_absatz.get(i, "") for i, absatz in enumerate(paragraphs)]
    return "\n\n".join(zeilen), verwaist
```

- [ ] **Step 4: Test ausführen, Erfolg bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_annotate.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git -C "D:\Workspace\!Episto" add tools/episto_tui/annotate.py tools/episto_tui/tests/test_annotate.py 2>&1 || true
```

---

## Task 4: Library — Bücher & Kapitel entdecken

**Files:**
- Create: `D:\Workspace\!Episto\tools\episto_tui\library.py`
- Test: `D:\Workspace\!Episto\tools\episto_tui\tests\test_library_discover.py`

**Interfaces:**
- Consumes: `episto_tui.models.Buch`, `episto_tui.models.Kapitel`
- Produces: `DEFAULT_ROOT: Path`, `discover_books(root: Path) -> list[Buch]`,
  `list_chapters(buch: Buch) -> list[Kapitel]`

- [ ] **Step 1: Fehlschlagenden Test schreiben**

`episto_tui\tests\test_library_discover.py`:
```python
from episto_tui import library
from episto_tui.models import Buch


def test_discover_books_findet_buecher_mit_quelle_ordner(tmp_path, temp_buch):
    gefunden = library.discover_books(tmp_path)
    assert len(gefunden) == 1
    assert gefunden[0].autor == "Testautor, Theo"
    assert gefunden[0].titel == "Testbuch"


def test_discover_books_ignoriert_ordner_ohne_quelle(tmp_path):
    (tmp_path / "Autor" / "X" / "OhneQuelle").mkdir(parents=True)
    gefunden = library.discover_books(tmp_path)
    assert gefunden == []


def test_discover_books_leeres_root_gibt_leere_liste(tmp_path):
    assert library.discover_books(tmp_path) == []


def test_list_chapters_liest_kapitel_index(temp_buch):
    kapitel = library.list_chapters(temp_buch)
    assert [k.datei for k in kapitel] == ["0001_erstes-kapitel.md", "0002_zweites-kapitel.md"]
    assert kapitel[0].nr == 1
    assert kapitel[0].titel == "Erstes Kapitel"


def test_list_chapters_fallback_ohne_index(tmp_path):
    buch = Buch(autor="A", titel="B", pfad=tmp_path / "Autor" / "A" / "B")
    (buch.pfad / "quelle").mkdir(parents=True)
    (buch.pfad / "quelle" / "0001_irgendwas.md").write_text("x", encoding="utf-8")
    kapitel = library.list_chapters(buch)
    assert len(kapitel) == 1
    assert kapitel[0].datei == "0001_irgendwas.md"
```

- [ ] **Step 2: Test ausführen, Fehlschlag bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_library_discover.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'episto_tui.library'`

- [ ] **Step 3: `library.py` anlegen (Grundgerüst + Entdeckungsfunktionen)**

```python
from __future__ import annotations
import json
from pathlib import Path
from episto_tui.models import Buch, Kapitel

DEFAULT_ROOT = Path(r"D:\Workspace\!Episto")


def discover_books(root: Path) -> list[Buch]:
    buecher: list[Buch] = []
    autor_root = root / "Autor"
    if not autor_root.is_dir():
        return buecher
    for autor_dir in sorted(autor_root.iterdir()):
        if not autor_dir.is_dir():
            continue
        for buch_dir in sorted(autor_dir.iterdir()):
            if not buch_dir.is_dir():
                continue
            if (buch_dir / "quelle").is_dir():
                buecher.append(Buch(autor=autor_dir.name, titel=buch_dir.name, pfad=buch_dir))
    return buecher


def list_chapters(buch: Buch) -> list[Kapitel]:
    index_pfad = buch.pfad / "quelle" / "_kapitel_index.json"
    if index_pfad.exists():
        try:
            eintraege = json.loads(index_pfad.read_text(encoding="utf-8"))
            return [Kapitel(nr=e["nr"], titel=e["titel"], datei=e["datei"]) for e in eintraege]
        except (json.JSONDecodeError, KeyError, OSError):
            pass  # kaputte Index-Datei -> Fallback auf Glob, nie Absturz
    dateien = sorted(
        p for p in (buch.pfad / "quelle").glob("*.md") if not p.name.startswith("_")
    )
    return [Kapitel(nr=i, titel=p.stem, datei=p.name) for i, p in enumerate(dateien, start=1)]
```

- [ ] **Step 4: Test ausführen, Erfolg bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_library_discover.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git -C "D:\Workspace\!Episto" add tools/episto_tui/library.py tools/episto_tui/tests/test_library_discover.py 2>&1 || true
```

---

## Task 5: Library — Kapiteltext lesen & schreiben

**Files:**
- Modify: `D:\Workspace\!Episto\tools\episto_tui\library.py`
- Test: `D:\Workspace\!Episto\tools\episto_tui\tests\test_library_text.py`

**Interfaces:**
- Consumes: `backup_before_write` aus Task 2
- Produces: `read_chapter_text(buch: Buch, dateiname: str) -> str`,
  `write_chapter_text(buch: Buch, dateiname: str, text: str) -> None`

- [ ] **Step 1: Fehlschlagenden Test schreiben**

`episto_tui\tests\test_library_text.py`:
```python
from episto_tui import library


def test_read_chapter_text(temp_buch):
    text = library.read_chapter_text(temp_buch, "0002_zweites-kapitel.md")
    assert text == "Einziger Absatz des zweiten Kapitels."


def test_write_chapter_text_schreibt_und_sichert(temp_buch):
    library.write_chapter_text(temp_buch, "0002_zweites-kapitel.md", "Neuer Inhalt.")

    assert library.read_chapter_text(temp_buch, "0002_zweites-kapitel.md") == "Neuer Inhalt."

    backups = list((temp_buch.pfad / "notizen" / "_backup").glob("0002_zweites-kapitel.*.md"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "Einziger Absatz des zweiten Kapitels."
```

- [ ] **Step 2: Test ausführen, Fehlschlag bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_library_text.py -v`
Expected: FAIL mit `AttributeError: module 'episto_tui.library' has no attribute 'read_chapter_text'`

- [ ] **Step 3: Funktionen in `library.py` ergänzen**

Import am Dateianfang ergänzen: `from episto_tui.backup import backup_before_write`

Am Ende der Datei anfügen:
```python
def read_chapter_text(buch: Buch, dateiname: str) -> str:
    return (buch.pfad / "quelle" / dateiname).read_text(encoding="utf-8")


def write_chapter_text(buch: Buch, dateiname: str, text: str) -> None:
    pfad = buch.pfad / "quelle" / dateiname
    backup_before_write(buch.pfad, pfad)
    pfad.write_text(text, encoding="utf-8", newline="\n")
```

- [ ] **Step 4: Test ausführen, Erfolg bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_library_text.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git -C "D:\Workspace\!Episto" add tools/episto_tui/library.py tools/episto_tui/tests/test_library_text.py 2>&1 || true
```

---

## Task 6: Library — Tags lesen & schreiben

**Files:**
- Modify: `D:\Workspace\!Episto\tools\episto_tui\library.py`
- Test: `D:\Workspace\!Episto\tools\episto_tui\tests\test_library_tags.py`

**Interfaces:**
- Consumes: `episto_tui.models.Tag`, `backup_before_write`
- Produces: `read_tags(buch: Buch, dateiname: str) -> Tag | None`,
  `write_tag(buch: Buch, tag: Tag) -> None`

- [ ] **Step 1: Fehlschlagenden Test schreiben**

`episto_tui\tests\test_library_tags.py`:
```python
from episto_tui import library
from episto_tui.models import Tag


def test_read_tags_findet_vorhandenes_kapitel(temp_buch):
    tag = library.read_tags(temp_buch, "0001_erstes-kapitel.md")
    assert tag is not None
    assert tag.these == ["Testthese"]
    assert tag.kern == ["testbegriff"]


def test_read_tags_gibt_none_fuer_ungetaggtes_kapitel(temp_buch):
    tag = library.read_tags(temp_buch, "0002_zweites-kapitel.md")
    assert tag is None


def test_read_tags_gibt_none_wenn_datei_fehlt(tmp_path):
    from episto_tui.models import Buch
    buch = Buch(autor="A", titel="B", pfad=tmp_path)
    assert library.read_tags(buch, "irgendwas.md") is None


def test_write_tag_ersetzt_vorhandenes_kapitel(temp_buch):
    neuer_tag = Tag(
        datei="0001_erstes-kapitel.md", kapitel_nr=1, titel="Erstes Kapitel",
        woerter=99, these=["Neue These"], gegen=[], kern=["neu"], def_=[],
        beleg=[], zusammenfassung="Neu.",
    )
    library.write_tag(temp_buch, neuer_tag)

    wieder_gelesen = library.read_tags(temp_buch, "0001_erstes-kapitel.md")
    assert wieder_gelesen.these == ["Neue These"]

    backups = list((temp_buch.pfad / "notizen" / "_backup").glob("tags.*.json"))
    assert len(backups) == 1


def test_write_tag_haengt_neues_kapitel_an(temp_buch):
    neuer_tag = Tag(
        datei="0002_zweites-kapitel.md", kapitel_nr=2, titel="Zweites Kapitel",
        woerter=5, these=["These 2"], gegen=[], kern=[], def_=[], beleg=[],
        zusammenfassung="",
    )
    library.write_tag(temp_buch, neuer_tag)

    assert library.read_tags(temp_buch, "0001_erstes-kapitel.md") is not None
    assert library.read_tags(temp_buch, "0002_zweites-kapitel.md").these == ["These 2"]
```

- [ ] **Step 2: Test ausführen, Fehlschlag bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_library_tags.py -v`
Expected: FAIL mit `AttributeError: module 'episto_tui.library' has no attribute 'read_tags'`

- [ ] **Step 3: Funktionen in `library.py` ergänzen**

Import ergänzen: `from episto_tui.models import Buch, Kapitel, Tag` (bestehende
`Buch, Kapitel`-Zeile erweitern) und `from datetime import datetime`.

Am Ende der Datei anfügen:
```python
def _tags_pfad(buch: Buch) -> Path:
    return buch.pfad / "notizen" / "tags.json"


def read_tags(buch: Buch, dateiname: str) -> Tag | None:
    pfad = _tags_pfad(buch)
    if not pfad.exists():
        return None
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    for eintrag in daten.get("kapitel", []):
        if eintrag.get("datei") == dateiname:
            return Tag.from_dict(eintrag)
    return None


def write_tag(buch: Buch, tag: Tag) -> None:
    pfad = _tags_pfad(buch)
    backup_before_write(buch.pfad, pfad)
    if pfad.exists():
        try:
            daten = json.loads(pfad.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            daten = {"werk": buch.titel, "autor": buch.autor, "sprache": "de", "kapitel": []}
    else:
        daten = {"werk": buch.titel, "autor": buch.autor, "sprache": "de", "kapitel": []}

    kapitel_liste = daten.get("kapitel", [])
    ersetzt = False
    for i, eintrag in enumerate(kapitel_liste):
        if eintrag.get("datei") == tag.datei:
            kapitel_liste[i] = tag.to_dict()
            ersetzt = True
            break
    if not ersetzt:
        kapitel_liste.append(tag.to_dict())

    daten["kapitel"] = kapitel_liste
    daten["eintraege"] = len(kapitel_liste)
    daten["erstellt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
```

- [ ] **Step 4: Test ausführen, Erfolg bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_library_tags.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git -C "D:\Workspace\!Episto" add tools/episto_tui/library.py tools/episto_tui/tests/test_library_tags.py 2>&1 || true
```

---

## Task 7: Library — Stränge & Querverweise lesen (nur Anzeige)

**Files:**
- Modify: `D:\Workspace\!Episto\tools\episto_tui\library.py`
- Test: `D:\Workspace\!Episto\tools\episto_tui\tests\test_library_readonly.py`

**Interfaces:**
- Produces: `read_straenge_for_chapter(buch: Buch, kapitel_nr: int) -> list[dict]`
  (jedes dict: `{"strang": str, "abschnitt": str, "inhalt": str}`),
  `read_querbezuege(buch: Buch) -> list[dict]` (Rohdaten aus `bezuege`)

- [ ] **Step 1: Fehlschlagenden Test schreiben**

`episto_tui\tests\test_library_readonly.py`:
```python
from episto_tui import library


def test_read_straenge_for_chapter_findet_treffer(temp_buch):
    treffer = library.read_straenge_for_chapter(temp_buch, 1)
    assert len(treffer) == 1
    assert treffer[0]["strang"] == "Test-Strang"
    assert treffer[0]["abschnitt"] == "Erstes Kapitel"
    assert "Testthese" in treffer[0]["inhalt"]


def test_read_straenge_for_chapter_ohne_treffer(temp_buch):
    assert library.read_straenge_for_chapter(temp_buch, 2) == []


def test_read_straenge_for_chapter_ohne_ordner(tmp_path):
    from episto_tui.models import Buch
    buch = Buch(autor="A", titel="B", pfad=tmp_path)
    assert library.read_straenge_for_chapter(buch, 1) == []


def test_read_querbezuege_liest_bezuege(temp_buch):
    bezuege = library.read_querbezuege(temp_buch)
    assert len(bezuege) == 1
    assert bezuege[0]["autor"] == "Externer Autor"


def test_read_querbezuege_ohne_datei(tmp_path):
    from episto_tui.models import Buch
    buch = Buch(autor="A", titel="B", pfad=tmp_path)
    assert library.read_querbezuege(buch) == []
```

- [ ] **Step 2: Test ausführen, Fehlschlag bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_library_readonly.py -v`
Expected: FAIL mit `AttributeError: module 'episto_tui.library' has no attribute 'read_straenge_for_chapter'`

- [ ] **Step 3: Funktionen in `library.py` ergänzen**

Am Ende der Datei anfügen:
```python
def _parse_kapitel_heading(zeile: str) -> tuple[int, str] | None:
    """Erkennt Zeilen der Form '### Kapitel 3 · Abschnittstitel', wie sie
    tools\\straenge.ps1 erzeugt (Trennzeichen ist ein Mittelpunkt · 0x00B7,
    aber diese Funktion akzeptiert jedes einzelne Trennzeichen)."""
    praefix = "### Kapitel "
    if not zeile.startswith(praefix):
        return None
    rest = zeile[len(praefix):].strip()
    teile = rest.split(None, 1)
    if not teile or not teile[0].isdigit():
        return None
    nr = int(teile[0])
    abschnitt = teile[1].strip() if len(teile) > 1 else ""
    # Genau EIN fuehrendes Trennzeichen abstreifen (nicht alphanumerisch),
    # nicht nur eine feste Zeichen-Auswahl - straenge.ps1 nutzt "·", andere
    # Trennzeichen sollen ebenso funktionieren.
    if abschnitt and not abschnitt[0].isalnum():
        abschnitt = abschnitt[1:].strip()
    return nr, abschnitt


def _parse_strang_datei(pfad: Path) -> tuple[str, list[dict]]:
    text = pfad.read_text(encoding="utf-8")
    name = pfad.stem
    if text.startswith("---"):
        ende = text.find("\n---", 3)
        if ende != -1:
            frontmatter = text[3:ende]
            for zeile in frontmatter.splitlines():
                if zeile.startswith("strang:"):
                    name = zeile.split(":", 1)[1].strip()
            text = text[ende + 4:]

    treffer: list[dict] = []
    aktuell: dict | None = None
    for zeile in text.splitlines():
        erkannt = _parse_kapitel_heading(zeile.strip())
        if erkannt is not None:
            if aktuell is not None:
                treffer.append(aktuell)
            nr, abschnitt = erkannt
            aktuell = {"nr": nr, "abschnitt": abschnitt, "inhalt": []}
        elif aktuell is not None:
            aktuell["inhalt"].append(zeile)
    if aktuell is not None:
        treffer.append(aktuell)
    for eintrag in treffer:
        eintrag["inhalt"] = "\n".join(eintrag["inhalt"]).strip()
    return name, treffer


def read_straenge_for_chapter(buch: Buch, kapitel_nr: int) -> list[dict]:
    ordner = buch.pfad / "notizen" / "straenge"
    ergebnisse: list[dict] = []
    if not ordner.is_dir():
        return ergebnisse
    for pfad in sorted(ordner.glob("*.md")):
        name, treffer = _parse_strang_datei(pfad)
        for eintrag in treffer:
            if eintrag["nr"] == kapitel_nr:
                ergebnisse.append({
                    "strang": name,
                    "abschnitt": eintrag["abschnitt"],
                    "inhalt": eintrag["inhalt"],
                })
    return ergebnisse


def read_querbezuege(buch: Buch) -> list[dict]:
    pfad = buch.pfad / "querbezuege" / "querbezuege.json"
    if not pfad.exists():
        return []
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(daten, dict):
        return []
    return daten.get("bezuege", [])
```

- [ ] **Step 4: Test ausführen, Erfolg bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_library_readonly.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git -C "D:\Workspace\!Episto" add tools/episto_tui/library.py tools/episto_tui/tests/test_library_readonly.py 2>&1 || true
```

---

## Task 8: Library — Kommentare lesen & schreiben

**Files:**
- Modify: `D:\Workspace\!Episto\tools\episto_tui\library.py`
- Test: `D:\Workspace\!Episto\tools\episto_tui\tests\test_library_kommentare.py`

**Interfaces:**
- Consumes: `episto_tui.models.Kommentar`
- Produces: `read_kommentare(buch: Buch, dateiname: str) -> list[Kommentar]`,
  `add_kommentar(buch: Buch, kommentar: Kommentar) -> None`

- [ ] **Step 1: Fehlschlagenden Test schreiben**

`episto_tui\tests\test_library_kommentare.py`:
```python
from episto_tui import library
from episto_tui.models import Kommentar


def test_read_kommentare_ohne_datei_gibt_leere_liste(temp_buch):
    assert library.read_kommentare(temp_buch, "0001_erstes-kapitel.md") == []


def test_add_kommentar_und_wieder_lesen(temp_buch):
    kommentar = Kommentar(
        datei="0001_erstes-kapitel.md", absatz_index=0,
        absatz_anfang="Erster Absatz", text="Testkommentar",
        erstellt="2026-09-27 15:00",
    )
    library.add_kommentar(temp_buch, kommentar)

    gelesen = library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")
    assert len(gelesen) == 1
    assert gelesen[0].text == "Testkommentar"


def test_read_kommentare_filtert_nach_datei(temp_buch):
    library.add_kommentar(temp_buch, Kommentar(
        datei="0001_erstes-kapitel.md", absatz_index=0, absatz_anfang="X",
        text="Kapitel 1", erstellt="2026-09-27",
    ))
    library.add_kommentar(temp_buch, Kommentar(
        datei="0002_zweites-kapitel.md", absatz_index=0, absatz_anfang="Y",
        text="Kapitel 2", erstellt="2026-09-27",
    ))

    nur_kapitel_2 = library.read_kommentare(temp_buch, "0002_zweites-kapitel.md")
    assert len(nur_kapitel_2) == 1
    assert nur_kapitel_2[0].text == "Kapitel 2"


def test_add_kommentar_sichert_vorherigen_stand(temp_buch):
    erster = Kommentar(datei="a.md", absatz_index=0, absatz_anfang="A", text="Erst", erstellt="t")
    library.add_kommentar(temp_buch, erster)
    zweiter = Kommentar(datei="a.md", absatz_index=1, absatz_anfang="B", text="Zweit", erstellt="t")
    library.add_kommentar(temp_buch, zweiter)

    backups = list((temp_buch.pfad / "notizen" / "_backup").glob("kommentare.*.json"))
    assert len(backups) == 1  # beim ersten Anlegen existierte die Datei noch nicht
```

- [ ] **Step 2: Test ausführen, Fehlschlag bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_library_kommentare.py -v`
Expected: FAIL mit `AttributeError: module 'episto_tui.library' has no attribute 'read_kommentare'`

- [ ] **Step 3: Funktionen in `library.py` ergänzen**

Import ergänzen: `from episto_tui.models import Buch, Kapitel, Tag, Kommentar`

Am Ende der Datei anfügen:
```python
def _kommentare_pfad(buch: Buch) -> Path:
    return buch.pfad / "notizen" / "kommentare.json"


def read_kommentare(buch: Buch, dateiname: str) -> list[Kommentar]:
    pfad = _kommentare_pfad(buch)
    if not pfad.exists():
        return []
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(daten, dict):
        return []
    return [
        Kommentar.from_dict(eintrag)
        for eintrag in daten.get("kommentare", [])
        if eintrag.get("datei") == dateiname
    ]


def add_kommentar(buch: Buch, kommentar: Kommentar) -> None:
    pfad = _kommentare_pfad(buch)
    backup_before_write(buch.pfad, pfad)
    if pfad.exists():
        try:
            daten = json.loads(pfad.read_text(encoding="utf-8"))
            if not isinstance(daten, dict):
                daten = {"werk": buch.titel, "kommentare": []}
        except (json.JSONDecodeError, OSError):
            daten = {"werk": buch.titel, "kommentare": []}
    else:
        daten = {"werk": buch.titel, "kommentare": []}
    daten.setdefault("kommentare", []).append(kommentar.to_dict())
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
```

- [ ] **Step 4: Test ausführen, Erfolg bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_library_kommentare.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Alle Library-Tests zusammen laufen lassen (Regressionscheck)**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests -v`
Expected: alle bisherigen Tests aus Task 1–8 PASSED (kein Widget existiert noch, das ist erwartet)

- [ ] **Step 6: Commit**

```bash
git -C "D:\Workspace\!Episto" add tools/episto_tui/library.py tools/episto_tui/tests/test_library_kommentare.py 2>&1 || true
```

---

## Task 9: Widget — Baum-Sidebar mit Tippfilterung

**Files:**
- Create: `D:\Workspace\!Episto\tools\episto_tui\widgets\tree_sidebar.py`
- Test: `D:\Workspace\!Episto\tools\episto_tui\tests\test_tree_sidebar.py`

**Interfaces:**
- Consumes: `library.discover_books`, `library.list_chapters`
- Produces: `ChapterSelected(Message)` mit Feldern `.buch: Buch`, `.kapitel: Kapitel`;
  `LibraryTree(Tree)` mit `__init__(self, root: Path)`, Methode `rebuild()`

- [ ] **Step 1: Fehlschlagenden Test schreiben**

Textual-Widgets werden über eine winzige Test-App mit `run_test()` geprüft.

`episto_tui\tests\test_tree_sidebar.py`:
```python
import pytest
from textual.app import App, ComposeResult
from episto_tui.widgets.tree_sidebar import LibraryTree, ChapterSelected


class _BaumTestApp(App):
    def __init__(self, root):
        super().__init__()
        self.root = root
        self.letztes_ereignis: ChapterSelected | None = None

    def compose(self) -> ComposeResult:
        yield LibraryTree(self.root)

    def on_chapter_selected(self, event: ChapterSelected) -> None:
        self.letztes_ereignis = event


@pytest.mark.asyncio
async def test_baum_zeigt_buch_und_kapitel(tmp_path, temp_buch):
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        # ein Buch-Knoten mit zwei Kapitel-Blaettern
        buch_knoten = list(baum.root.children)
        assert len(buch_knoten) == 1
        assert "Testbuch" in str(buch_knoten[0].label)
        assert len(buch_knoten[0].children) == 2


@pytest.mark.asyncio
async def test_tippfilterung_grenzt_kapitel_ein(tmp_path, temp_buch):
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        baum.focus()
        await pilot.press("z", "w", "e", "i")  # "zwei" -> nur "Zweites Kapitel"
        buch_knoten = list(baum.root.children)
        assert len(buch_knoten) == 1
        assert len(buch_knoten[0].children) == 1
        assert "Zweites" in str(buch_knoten[0].children[0].label)


@pytest.mark.asyncio
async def test_escape_setzt_filter_zurueck(tmp_path, temp_buch):
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        baum.focus()
        await pilot.press("z", "w", "e", "i")
        await pilot.press("escape")
        buch_knoten = list(baum.root.children)
        assert len(buch_knoten[0].children) == 2


@pytest.mark.asyncio
async def test_auswahl_eines_kapitels_feuert_chapter_selected(tmp_path, temp_buch):
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        buch_knoten = list(baum.root.children)[0]
        kapitel_knoten = buch_knoten.children[0]
        baum.select_node(kapitel_knoten)
        await pilot.pause()
        assert app.letztes_ereignis is not None
        assert app.letztes_ereignis.kapitel.datei == "0001_erstes-kapitel.md"
```

Hinweis: Falls `pytest-asyncio` nicht installiert ist, meldet der erste
Testlauf das in Step 2 als Fehlschlag — dann `pip install pytest-asyncio`
ausführen und in `requirements.txt` (Task 1) ergänzen, bevor mit Step 3
weitergemacht wird.

- [ ] **Step 2: Test ausführen, Fehlschlag bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_tree_sidebar.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'episto_tui.widgets.tree_sidebar'`
(oder, falls `pytest-asyncio` fehlt: Fehlermeldung dazu — dann wie im Hinweis
oben installieren und Step 2 wiederholen)

- [ ] **Step 3: `tree_sidebar.py` implementieren**

```python
from __future__ import annotations
from pathlib import Path
from textual.widgets import Tree
from textual.message import Message
from episto_tui import library
from episto_tui.models import Buch, Kapitel


class ChapterSelected(Message):
    def __init__(self, buch: Buch, kapitel: Kapitel) -> None:
        self.buch = buch
        self.kapitel = kapitel
        super().__init__()


class LibraryTree(Tree):
    def __init__(self, root: Path) -> None:
        super().__init__("Bibliothek")
        self.root_pfad = root
        self.filter_text = ""

    def on_mount(self) -> None:
        self.rebuild()

    def rebuild(self) -> None:
        self.root.remove_children()
        buecher = library.discover_books(self.root_pfad)
        filter_lower = self.filter_text.lower()
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
            buch_knoten = self.root.add(f"{buch.autor} — {buch.titel}", expand=True)
            for kapitel in passende:
                buch_knoten.add_leaf(f"{kapitel.nr}. {kapitel.titel}", data=(buch, kapitel))
        self.root.expand()

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

- [ ] **Step 4: Test ausführen, Erfolg bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_tree_sidebar.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git -C "D:\Workspace\!Episto" add tools/episto_tui/widgets/tree_sidebar.py tools/episto_tui/tests/test_tree_sidebar.py 2>&1 || true
```

---

## Task 10: Widget — Lese-/Editierbereich (Text-Tab)

**Files:**
- Create: `D:\Workspace\!Episto\tools\episto_tui\widgets\reader_pane.py`
- Test: `D:\Workspace\!Episto\tools\episto_tui\tests\test_reader_pane.py`

**Interfaces:**
- Consumes: `library.read_chapter_text`, `library.write_chapter_text`,
  `library.read_kommentare`, `annotate.split_paragraphs`, `annotate.render_with_markers`
- Produces: `ReaderPane(Vertical)` mit Methode `lade_kapitel(buch: Buch, kapitel: Kapitel)`,
  Actions `toggle_edit` (Taste `e`) und `speichern` (Taste `ctrl+s`)

- [ ] **Step 1: Fehlschlagenden Test schreiben**

`episto_tui\tests\test_reader_pane.py`:
```python
import pytest
from textual.app import App, ComposeResult
from textual.widgets import Markdown, TextArea
from episto_tui.widgets.reader_pane import ReaderPane


class _LeseTestApp(App):
    def compose(self) -> ComposeResult:
        yield ReaderPane()


@pytest.mark.asyncio
async def test_lade_kapitel_zeigt_text_im_lesemodus(temp_buch):
    from episto_tui.models import Kapitel
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        assert app.query_one("#anzeige", Markdown).display is True
        assert app.query_one("#editor", TextArea).display is False


@pytest.mark.asyncio
async def test_escape_verwirft_aenderungen_ohne_speichern(temp_buch):
    from episto_tui.models import Kapitel
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        kapitel = Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md")
        pane.lade_kapitel(temp_buch, kapitel)
        await pilot.pause()

        pane.focus()
        await pilot.press("e")
        await pilot.pause()
        app.query_one("#editor", TextArea).text = "Verworfener Text."

        await pilot.press("escape")
        await pilot.pause()

        from episto_tui import library
        assert library.read_chapter_text(temp_buch, "0002_zweites-kapitel.md") == "Einziger Absatz des zweiten Kapitels."
        assert app.query_one("#anzeige", Markdown).display is True
        assert app.query_one("#editor", TextArea).display is False


@pytest.mark.asyncio
async def test_editieren_und_speichern_schreibt_datei(temp_buch):
    from episto_tui.models import Kapitel
    app = _LeseTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        kapitel = Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md")
        pane.lade_kapitel(temp_buch, kapitel)
        await pilot.pause()

        pane.focus()
        await pilot.press("e")
        await pilot.pause()
        editor = app.query_one("#editor", TextArea)
        assert editor.display is True
        editor.text = "Komplett neuer Kapiteltext."

        await pilot.press("ctrl+s")
        await pilot.pause()

        from episto_tui import library
        assert library.read_chapter_text(temp_buch, "0002_zweites-kapitel.md") == "Komplett neuer Kapiteltext."
        assert app.query_one("#anzeige", Markdown).display is True

        backups = list((temp_buch.pfad / "notizen" / "_backup").glob("0002_zweites-kapitel.*.md"))
        assert len(backups) == 1
```

- [ ] **Step 2: Test ausführen, Fehlschlag bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_reader_pane.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'episto_tui.widgets.reader_pane'`

- [ ] **Step 3: `reader_pane.py` implementieren**

Vereinfachung gegenüber der Spec: `Esc` verwirft ungesicherte Änderungen
sofort, ohne Rückfrage-Dialog (ein Bestätigungsdialog bräuchte einen eigenen
modalen Screen — für V1 bewusst zurückgestellt; das automatische Backup vor
jedem `Strg+S` bleibt die eigentliche Absicherung gegen Datenverlust).

```python
from __future__ import annotations
from textual.containers import Vertical
from textual.widgets import Markdown, TextArea
from textual.binding import Binding
from episto_tui import library, annotate
from episto_tui.models import Buch, Kapitel


class ReaderPane(Vertical, can_focus=True):
    # can_focus=True ist notwendig: ohne es fokussiert Textuals AUTO_FOCUS
    # standardmaessig die (unsichtbare) TextArea, deren eigene Tastatur-
    # behandlung jeden Tastendruck als Text abfaengt, bevor er die
    # Bindings dieser Klasse (e/ctrl+s/escape) je erreicht.
    BINDINGS = [
        Binding("e", "toggle_edit", "Editieren"),
        Binding("ctrl+s", "speichern", "Speichern"),
        Binding("escape", "verwerfen", "Verwerfen"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.buch: Buch | None = None
        self.kapitel: Kapitel | None = None
        self.bearbeiten = False

    def compose(self):
        yield Markdown(id="anzeige")
        yield TextArea(id="editor")

    def on_mount(self) -> None:
        self.query_one("#editor", TextArea).display = False

    def lade_kapitel(self, buch: Buch, kapitel: Kapitel) -> None:
        self.buch = buch
        self.kapitel = kapitel
        self.bearbeiten = False
        self._zeige_lesemodus()

    def _zeige_lesemodus(self) -> None:
        text = library.read_chapter_text(self.buch, self.kapitel.datei)
        kommentare = library.read_kommentare(self.buch, self.kapitel.datei)
        absaetze = annotate.split_paragraphs(text)
        annotiert, _verwaist = annotate.render_with_markers(absaetze, kommentare)
        self.query_one("#anzeige", Markdown).update(annotiert)
        self.query_one("#anzeige", Markdown).display = True
        self.query_one("#editor", TextArea).display = False

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
            self.query_one("#anzeige", Markdown).display = False
            self.bearbeiten = True

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

- [ ] **Step 4: Test ausführen, Erfolg bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_reader_pane.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git -C "D:\Workspace\!Episto" add tools/episto_tui/widgets/reader_pane.py tools/episto_tui/tests/test_reader_pane.py 2>&1 || true
```

---

## Task 11: Widget — Tags-Tab

**Files:**
- Create: `D:\Workspace\!Episto\tools\episto_tui\widgets\tags_pane.py`
- Test: `D:\Workspace\!Episto\tools\episto_tui\tests\test_tags_pane.py`

**Interfaces:**
- Consumes: `library.read_tags`, `library.write_tag`
- Produces: `TagsPane(ScrollableContainer)` mit `lade_kapitel(buch, kapitel)`,
  Action `speichern` (Taste `ctrl+s`)

- [ ] **Step 1: Fehlschlagenden Test schreiben**

`episto_tui\tests\test_tags_pane.py`:
```python
import pytest
from textual.app import App, ComposeResult
from textual.widgets import TextArea, Static
from episto_tui.widgets.tags_pane import TagsPane
from episto_tui.models import Kapitel


class _TagsTestApp(App):
    def compose(self) -> ComposeResult:
        yield TagsPane()


@pytest.mark.asyncio
async def test_lade_kapitel_zeigt_vorhandene_tags(temp_buch):
    app = _TagsTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(TagsPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        assert app.query_one("#feld-these", TextArea).text == "Testthese"
        assert app.query_one("#hinweis", Static).content == ""


@pytest.mark.asyncio
async def test_lade_kapitel_zeigt_hinweis_ohne_tags(temp_buch):
    app = _TagsTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(TagsPane)
        pane.lade_kapitel(temp_buch, Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md"))
        await pilot.pause()
        hinweis = str(app.query_one("#hinweis", Static).content)
        assert "taggen.ps1" in hinweis


@pytest.mark.asyncio
async def test_speichern_schreibt_geaenderte_these(temp_buch):
    app = _TagsTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(TagsPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()

        feld = app.query_one("#feld-these", TextArea)
        feld.text = "Geaenderte These 1\nGeaenderte These 2"

        pane.focus()
        await pilot.press("ctrl+s")
        await pilot.pause()

        from episto_tui import library
        tag = library.read_tags(temp_buch, "0001_erstes-kapitel.md")
        assert tag.these == ["Geaenderte These 1", "Geaenderte These 2"]
```

- [ ] **Step 2: Test ausführen, Fehlschlag bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_tags_pane.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'episto_tui.widgets.tags_pane'`

- [ ] **Step 3: `tags_pane.py` implementieren**

```python
from __future__ import annotations
from textual.containers import ScrollableContainer
from textual.widgets import TextArea, Label, Static
from textual.binding import Binding
from episto_tui import library
from episto_tui.models import Buch, Kapitel, Tag

_FELDER = ["these", "gegen", "kern", "def_", "beleg"]
_LABELS = {
    "these": "These", "gegen": "Gegenpositionen", "kern": "Kernbegriffe",
    "def_": "Definitionen", "beleg": "Belege",
}


class TagsPane(ScrollableContainer):
    BINDINGS = [Binding("ctrl+s", "speichern", "Speichern")]

    def __init__(self) -> None:
        super().__init__()
        self.buch: Buch | None = None
        self.kapitel: Kapitel | None = None
        self.tag: Tag | None = None

    def compose(self):
        yield Static("", id="hinweis")
        for feld in _FELDER:
            yield Label(_LABELS[feld])
            yield TextArea(id=f"feld-{feld}")
        yield Label("Zusammenfassung")
        yield TextArea(id="feld-zusammenfassung")

    def lade_kapitel(self, buch: Buch, kapitel: Kapitel) -> None:
        self.buch = buch
        self.kapitel = kapitel
        gefundener_tag = library.read_tags(buch, kapitel.datei)
        hinweis = self.query_one("#hinweis", Static)
        if gefundener_tag is None:
            hinweis.update("Noch nicht getaggt — tools\\taggen.ps1 ausführen.")
            self.tag = Tag(datei=kapitel.datei, kapitel_nr=kapitel.nr, titel=kapitel.titel, woerter=0)
        else:
            hinweis.update("")
            self.tag = gefundener_tag
        for feld in _FELDER:
            self.query_one(f"#feld-{feld}", TextArea).text = "\n".join(getattr(self.tag, feld))
        self.query_one("#feld-zusammenfassung", TextArea).text = self.tag.zusammenfassung

    def action_speichern(self) -> None:
        if self.buch is None or self.tag is None:
            return
        for feld in _FELDER:
            zeilen = [
                zeile.strip()
                for zeile in self.query_one(f"#feld-{feld}", TextArea).text.splitlines()
                if zeile.strip()
            ]
            setattr(self.tag, feld, zeilen)
        self.tag.zusammenfassung = self.query_one("#feld-zusammenfassung", TextArea).text
        library.write_tag(self.buch, self.tag)
```

- [ ] **Step 4: Test ausführen, Erfolg bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_tags_pane.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git -C "D:\Workspace\!Episto" add tools/episto_tui/widgets/tags_pane.py tools/episto_tui/tests/test_tags_pane.py 2>&1 || true
```

---

## Task 12: Widgets — Stränge-Tab & Querverweise-Tab (nur Anzeige)

**Files:**
- Create: `D:\Workspace\!Episto\tools\episto_tui\widgets\straenge_pane.py`
- Create: `D:\Workspace\!Episto\tools\episto_tui\widgets\querbezuege_pane.py`
- Test: `D:\Workspace\!Episto\tools\episto_tui\tests\test_readonly_panes.py`

**Interfaces:**
- Consumes: `library.read_straenge_for_chapter`, `library.read_querbezuege`
- Produces: `StraengePane(VerticalScroll)` und `QuerbezuegePane(VerticalScroll)`,
  beide mit `lade_kapitel(buch: Buch, kapitel: Kapitel)`

- [ ] **Step 1: Fehlschlagenden Test schreiben**

`episto_tui\tests\test_readonly_panes.py`:
```python
import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static
from episto_tui.widgets.straenge_pane import StraengePane
from episto_tui.widgets.querbezuege_pane import QuerbezuegePane
from episto_tui.models import Kapitel


class _AnzeigeTestApp(App):
    def compose(self) -> ComposeResult:
        yield StraengePane()
        yield QuerbezuegePane()


@pytest.mark.asyncio
async def test_straenge_pane_zeigt_treffer(temp_buch):
    app = _AnzeigeTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(StraengePane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        inhalt = str(app.query_one(StraengePane).query_one("#inhalt", Static).content)
        assert "Test-Strang" in inhalt


@pytest.mark.asyncio
async def test_straenge_pane_zeigt_platzhalter_ohne_treffer(temp_buch):
    app = _AnzeigeTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(StraengePane)
        pane.lade_kapitel(temp_buch, Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md"))
        await pilot.pause()
        inhalt = str(app.query_one(StraengePane).query_one("#inhalt", Static).content)
        assert "Keine Stränge" in inhalt


@pytest.mark.asyncio
async def test_querbezuege_pane_zeigt_bezuege(temp_buch):
    app = _AnzeigeTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(QuerbezuegePane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        inhalt = str(app.query_one(QuerbezuegePane).query_one("#inhalt", Static).content)
        assert "Externer Autor" in inhalt
```

- [ ] **Step 2: Test ausführen, Fehlschlag bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_readonly_panes.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'episto_tui.widgets.straenge_pane'`

- [ ] **Step 3: `straenge_pane.py` implementieren**

```python
from __future__ import annotations
from textual.containers import VerticalScroll
from textual.widgets import Static
from episto_tui import library
from episto_tui.models import Buch, Kapitel


class StraengePane(VerticalScroll):
    def compose(self):
        yield Static("", id="inhalt")

    def lade_kapitel(self, buch: Buch, kapitel: Kapitel) -> None:
        treffer = library.read_straenge_for_chapter(buch, kapitel.nr)
        anzeige = self.query_one("#inhalt", Static)
        if not treffer:
            anzeige.update("Keine Stränge für dieses Kapitel gefunden.")
            return
        zeilen = [f"## {t['strang']}\n{t['inhalt']}\n" for t in treffer]
        anzeige.update("\n".join(zeilen))
```

- [ ] **Step 4: `querbezuege_pane.py` implementieren**

```python
from __future__ import annotations
from textual.containers import VerticalScroll
from textual.widgets import Static
from episto_tui import library
from episto_tui.models import Buch, Kapitel


class QuerbezuegePane(VerticalScroll):
    def compose(self):
        yield Static("", id="inhalt")

    def lade_kapitel(self, buch: Buch, kapitel: Kapitel) -> None:
        bezuege = library.read_querbezuege(buch)
        anzeige = self.query_one("#inhalt", Static)
        if not bezuege:
            anzeige.update("Keine Querverweise für dieses Werk erfasst.")
            return
        zeilen = [
            f"**{b.get('autor', '')}** — {b.get('titel', '')}  ({b.get('relation', '')})\n{b.get('notiz', '')}\n"
            for b in bezuege
        ]
        anzeige.update("\n".join(zeilen))
```

- [ ] **Step 5: Test ausführen, Erfolg bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_readonly_panes.py -v`
Expected: 3 PASSED

- [ ] **Step 6: Commit**

```bash
git -C "D:\Workspace\!Episto" add tools/episto_tui/widgets/straenge_pane.py tools/episto_tui/widgets/querbezuege_pane.py tools/episto_tui/tests/test_readonly_panes.py 2>&1 || true
```

---

## Task 13: Widget — Kommentare-Tab

**Files:**
- Create: `D:\Workspace\!Episto\tools\episto_tui\widgets\kommentare_pane.py`
- Test: `D:\Workspace\!Episto\tools\episto_tui\tests\test_kommentare_pane.py`

**Interfaces:**
- Consumes: `library.read_chapter_text`, `library.read_kommentare`,
  `library.add_kommentar`, `annotate.split_paragraphs`, `annotate.locate_paragraph`
- Produces: `KommentarePane(Vertical)` mit `lade_kapitel(buch, kapitel)`,
  Action `kommentieren` (Taste `c`)

Vereinfachung gegenüber der Spec: Da freie Textauswahl in einem reinen
Anzeige-Widget in Textual nicht ohne Weiteres unterstützt wird, wählt man den
Absatz über eine Liste (nummeriert, mit Vorschau) statt durch Markieren im
Fließtext. Trifft dieselbe Absatz-Granularität wie im Design festgelegt.

- [ ] **Step 1: Fehlschlagenden Test schreiben**

`episto_tui\tests\test_kommentare_pane.py`:
```python
import pytest
from textual.app import App, ComposeResult
from textual.widgets import ListView
from episto_tui.widgets.kommentare_pane import KommentarePane
from episto_tui.models import Kapitel


class _KommentareTestApp(App):
    def compose(self) -> ComposeResult:
        yield KommentarePane()


@pytest.mark.asyncio
async def test_lade_kapitel_zeigt_alle_absaetze(temp_buch):
    app = _KommentareTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(KommentarePane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        liste = app.query_one("#absatzliste", ListView)
        assert len(liste.children) == 3  # drei Absaetze im Fixture-Kapitel


@pytest.mark.asyncio
async def test_kommentar_anlegen_erscheint_in_liste(temp_buch):
    app = _KommentareTestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(KommentarePane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()

        liste = app.query_one("#absatzliste", ListView)
        liste.index = 0
        pane.focus()
        await pilot.press("c")
        await pilot.pause()

        eingabe = app.query_one("#kommentar-eingabe")
        eingabe.value = "Testkommentar ueber die TUI"
        await pilot.press("enter")
        await pilot.pause()

        from episto_tui import library
        gespeichert = library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")
        assert len(gespeichert) == 1
        assert gespeichert[0].text == "Testkommentar ueber die TUI"
```

- [ ] **Step 2: Test ausführen, Fehlschlag bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_kommentare_pane.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'episto_tui.widgets.kommentare_pane'`

- [ ] **Step 3: `kommentare_pane.py` implementieren**

```python
from __future__ import annotations
from datetime import datetime
from textual.containers import Vertical
from textual.widgets import ListView, ListItem, Label, Input
from textual.binding import Binding
from episto_tui import library, annotate
from episto_tui.models import Buch, Kapitel, Kommentar


class KommentarePane(Vertical):
    BINDINGS = [Binding("c", "kommentieren", "Kommentieren")]

    def __init__(self) -> None:
        super().__init__()
        self.buch: Buch | None = None
        self.kapitel: Kapitel | None = None
        self.absaetze: list[str] = []

    def compose(self):
        yield ListView(id="absatzliste")
        yield Input(placeholder="Kommentar eintippen, Enter zum Speichern", id="kommentar-eingabe")

    def on_mount(self) -> None:
        self.query_one("#kommentar-eingabe", Input).display = False

    def lade_kapitel(self, buch: Buch, kapitel: Kapitel) -> None:
        self.buch = buch
        self.kapitel = kapitel
        text = library.read_chapter_text(buch, kapitel.datei)
        self.absaetze = annotate.split_paragraphs(text)
        kommentare = library.read_kommentare(buch, kapitel.datei)

        zuordnung: dict[int, list[Kommentar]] = {}
        for kommentar in kommentare:
            index = annotate.locate_paragraph(self.absaetze, kommentar.absatz_index, kommentar.absatz_anfang)
            if index is not None:
                zuordnung.setdefault(index, []).append(kommentar)

        liste = self.query_one("#absatzliste", ListView)
        liste.clear()
        for i, absatz in enumerate(self.absaetze):
            vorschau = absatz[:60].replace("\n", " ")
            eintrag_text = f"Absatz {i + 1}: {vorschau}..."
            for kommentar in zuordnung.get(i, []):
                eintrag_text += f"\n    💬 {kommentar.text}"
            liste.append(ListItem(Label(eintrag_text)))

    def action_kommentieren(self) -> None:
        eingabe = self.query_one("#kommentar-eingabe", Input)
        eingabe.display = True
        eingabe.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        liste = self.query_one("#absatzliste", ListView)
        if liste.index is None or self.buch is None:
            return
        absatz_index = liste.index
        text = event.value.strip()
        event.input.value = ""
        event.input.display = False
        if not text:
            return
        kommentar = Kommentar(
            datei=self.kapitel.datei,
            absatz_index=absatz_index,
            absatz_anfang=self.absaetze[absatz_index][:80],
            text=text,
            erstellt=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        library.add_kommentar(self.buch, kommentar)
        self.lade_kapitel(self.buch, self.kapitel)
```

- [ ] **Step 4: Test ausführen, Erfolg bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_kommentare_pane.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git -C "D:\Workspace\!Episto" add tools/episto_tui/widgets/kommentare_pane.py tools/episto_tui/tests/test_kommentare_pane.py 2>&1 || true
```

---

## Task 14: App-Zusammenbau (Layout, Wiring, Entry Point)

**Files:**
- Create: `D:\Workspace\!Episto\tools\episto_tui\app.py`
- Create: `D:\Workspace\!Episto\tools\episto_tui\__main__.py`
- Test: `D:\Workspace\!Episto\tools\episto_tui\tests\test_app.py`

**Interfaces:**
- Consumes: alle Widgets aus Task 9–13, `library.DEFAULT_ROOT`
- Produces: `EpistoApp(App)` mit `__init__(self, root: Path | None = None)`

- [ ] **Step 1: Fehlschlagenden Test schreiben**

`episto_tui\tests\test_app.py`:
```python
import pytest
from episto_tui.app import EpistoApp
from episto_tui.widgets.reader_pane import ReaderPane
from episto_tui.widgets.tags_pane import TagsPane
from episto_tui.widgets.tree_sidebar import LibraryTree


@pytest.mark.asyncio
async def test_app_zeigt_baum_und_kann_kapitel_oeffnen(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        buch_knoten = list(baum.root.children)[0]
        kapitel_knoten = buch_knoten.children[0]
        baum.select_node(kapitel_knoten)
        await pilot.pause()

        from textual.widgets import Markdown
        anzeige = app.query_one(ReaderPane).query_one("#anzeige", Markdown)
        assert anzeige.display is True

        from textual.widgets import TextArea
        these_feld = app.query_one(TagsPane).query_one("#feld-these", TextArea)
        assert these_feld.text == "Testthese"


@pytest.mark.asyncio
async def test_zifferntasten_wechseln_tabs(tmp_path, temp_buch):
    from textual.widgets import TabbedContent
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("2")
        await pilot.pause()
        assert app.query_one(TabbedContent).active == "tab-tags"
        await pilot.press("1")
        await pilot.pause()
        assert app.query_one(TabbedContent).active == "tab-text"
```

- [ ] **Step 2: Test ausführen, Fehlschlag bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_app.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'episto_tui.app'`

- [ ] **Step 3: `app.py` implementieren**

```python
from __future__ import annotations
from pathlib import Path
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import TabbedContent, TabPane
from textual.binding import Binding
from episto_tui import library
from episto_tui.widgets.tree_sidebar import LibraryTree, ChapterSelected
from episto_tui.widgets.reader_pane import ReaderPane
from episto_tui.widgets.tags_pane import TagsPane
from episto_tui.widgets.straenge_pane import StraengePane
from episto_tui.widgets.querbezuege_pane import QuerbezuegePane
from episto_tui.widgets.kommentare_pane import KommentarePane


class EpistoApp(App):
    BINDINGS = [
        Binding("q", "quit", "Beenden"),
        Binding("1", "tab_text", "Text"),
        Binding("2", "tab_tags", "Tags"),
        Binding("3", "tab_straenge", "Stränge"),
        Binding("4", "tab_querbezuege", "Querverweise"),
        Binding("5", "tab_kommentare", "Kommentare"),
    ]
    # HINWEIS (Session vom 2026-09-27): Ein Implementierungsversuch hat hier
    # `priority=True` ergaenzt, um Ziffern/"q" auch bei fokussierter
    # LibraryTree (die diese Zeichen fuer die Tippfilterung abfaengt) global
    # wirken zu lassen. Verworfen: `priority=True`-Bindings werden VOR jedem
    # fokussierten Widget geprueft (Textual App.on_event), wodurch "q" und
    # Ziffern 1-5 in KEINEM Textfeld der App (TextArea/Input) mehr eingetippt
    # werden koennten - eine schwerere Regression als das urspruengliche,
    # auf die fokussierte LibraryTree begrenzte Verhalten. Bindings bleiben
    # bewusst ohne priority: Solange die Bibliothek den Fokus haelt, gehen
    # Tastendruecke an die Tippfilterung (konsistentes "Eingabe geht an den
    # fokussierten Bedienbereich"-Verhalten); Tab wechselt den Fokus in einen
    # Pane, danach greifen die Ziffern-Shortcuts normal.

    def __init__(self, root: Path | None = None) -> None:
        super().__init__()
        self.root_pfad = root if root is not None else library.DEFAULT_ROOT

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield LibraryTree(self.root_pfad)
            with TabbedContent(initial="tab-text"):
                with TabPane("Text", id="tab-text"):
                    yield ReaderPane()
                with TabPane("Tags", id="tab-tags"):
                    yield TagsPane()
                with TabPane("Stränge", id="tab-straenge"):
                    yield StraengePane()
                with TabPane("Querverweise", id="tab-querbezuege"):
                    yield QuerbezuegePane()
                with TabPane("Kommentare", id="tab-kommentare"):
                    yield KommentarePane()

    def on_chapter_selected(self, event: ChapterSelected) -> None:
        self.query_one(ReaderPane).lade_kapitel(event.buch, event.kapitel)
        self.query_one(TagsPane).lade_kapitel(event.buch, event.kapitel)
        self.query_one(StraengePane).lade_kapitel(event.buch, event.kapitel)
        self.query_one(QuerbezuegePane).lade_kapitel(event.buch, event.kapitel)
        self.query_one(KommentarePane).lade_kapitel(event.buch, event.kapitel)

    def action_tab_text(self) -> None:
        self.query_one(TabbedContent).active = "tab-text"

    def action_tab_tags(self) -> None:
        self.query_one(TabbedContent).active = "tab-tags"

    def action_tab_straenge(self) -> None:
        self.query_one(TabbedContent).active = "tab-straenge"

    def action_tab_querbezuege(self) -> None:
        self.query_one(TabbedContent).active = "tab-querbezuege"

    def action_tab_kommentare(self) -> None:
        self.query_one(TabbedContent).active = "tab-kommentare"
```

- [ ] **Step 4: `__main__.py` implementieren**

```python
from episto_tui.app import EpistoApp

if __name__ == "__main__":
    EpistoApp().run()
```

- [ ] **Step 5: Test ausführen, Erfolg bestätigen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests\test_app.py -v`
Expected: 2 PASSED

- [ ] **Step 6: Gesamte Test-Suite laufen lassen**

Run: `cd D:\Workspace\!Episto\tools; python -m pytest episto_tui\tests -v`
Expected: alle Tests aus Task 1–14 PASSED (keine Regressionen)

- [ ] **Step 7: App manuell starten und Grundfunktionen von Hand prüfen**

Run: `cd D:\Workspace\!Episto\tools; python -m episto_tui`

Manuell prüfen: Baum zeigt alle 7 Bücher, Kapitel öffnen zeigt Text, `e` +
Bearbeiten + `Strg+S` speichert (Backup-Datei prüfen), Tasten `1`–`5`
wechseln Tabs, `q` beendet die App.

- [ ] **Step 8: Commit**

```bash
git -C "D:\Workspace\!Episto" add tools/episto_tui/app.py tools/episto_tui/__main__.py tools/episto_tui/tests/test_app.py 2>&1 || true
```
