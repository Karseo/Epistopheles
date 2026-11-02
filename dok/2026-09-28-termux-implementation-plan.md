# EPISTO-TUI unter Termux Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Textual-TUI `tools/episto_tui` läuft unter Termux auf Android: Wurzelpfad einstellbar, schmales Layout mit Baum-Schublade und tippbare Aktionsleiste, dazu Startskript, Syncthing-Ignore-Liste und Anleitung.

**Architecture:** `library.resolve_root` bestimmt die Wurzel (Argument, Umgebung, Plattform-Standard); `EpistoApp` setzt bei Terminalbreite unter 80 Spalten die CSS-Klasse `schmal` auf dem Screen (Baum ausgeblendet, Aktionsleiste sichtbar) und `baum-offen`, wenn der Baum die Tabs vorübergehend ersetzt. Die neue `Aktionsleiste` besteht aus nicht fokussierbaren Knöpfen, sendet nur eine Nachricht (`AktionGewaehlt`), und die App ruft damit die vorhandenen `action_*`-Methoden des aktiven Panes auf. `ReaderPane` meldet Moduswechsel (Lesen/Bearbeiten) per Nachricht, damit die Leiste ihre Knöpfe wechseln kann.

**Tech Stack:** Python 3, Textual 8.2.x (`textual>=8.2`), pytest, pytest-asyncio (Tests mit `@pytest.mark.asyncio`).

## Global Constraints

- Umfang: nur die TUI. Keine semantische Suche, keine Pipeline-Skripte, kein Qdrant, kein Ollama, kein Git-Remote (Spec, Abschnitt Nicht-Ziele).
- Schmal ist Terminalbreite **unter 80 Spalten**; die Schwelle ist die Konstante `SCHMAL_BREITE = 80` (entspricht der Standardgröße der bestehenden Tests, die dadurch unverändert im breiten Modus laufen).
- Breit: `LibraryTree { width: 60; max-width: 40%; }` (`width: 60` bleibt der Sollwert).
- Bestehende Tastenkürzel bleiben unverändert; neu ist nur die Taste `0` (Baum umschalten).
- Aktionsleiste: nur im schmalen Modus sichtbar; Knöpfe nehmen keinen Fokus (`can_focus = False`) und rufen die vorhandenen Aktionen des aktiven Panes auf, es gibt keine zweite Logik.
- Syncthing-Konfliktkopien (`<name>.sync-conflict-<datum>-<id>.<ext>`) erscheinen nie als Kapitel.
- `.stignore` im Repo-Wurzelordner enthält genau: `**/_backup`, `.git`, `**/__pycache__`, `.worktrees`, `.superpowers`, `Autor.mov`.
- Bezeichner ohne Umlaute wie im Bestand (`aktionsleiste`, `baum_umschalten`); Kommentare, Docstrings und Doku deutsch mit korrekten Umlauten in Fließtext.
- Bestehende Tests müssen grün bleiben (Stand vor diesem Plan: 156). Testbefehl im Ordner `tools/episto_tui`: `python -m pytest tests -q`.
- Commit-Nachrichten enden mit der eigenen Zeile `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

## Dateiübersicht

| Datei | Aktion | Zweck |
|---|---|---|
| `tools/episto_tui/library.py` | ändern | `resolve_root`; Konfliktkopien im Glob-Fallback von `list_chapters` ignorieren |
| `tools/episto_tui/__main__.py` | ändern | `--root` per argparse, `bestimme_root`, `main` |
| `tools/episto_tui/widgets/reader_pane.py` | ändern | `bearbeiten` wird reaktiv, `ModusGeaendert`-Nachricht |
| `tools/episto_tui/widgets/aktionsleiste.py` | neu | `TippKnopf`, `Aktionsleiste`, Kontexte |
| `tools/episto_tui/app.py` | ändern | CSS, Klassen `schmal`/`baum-offen`, Taste `0`, Leiste einbauen, Dispatch |
| `tools/episto-tui.sh` | neu | Startskript für Termux/Linux |
| `.stignore` | neu | Syncthing-Ignore-Liste |
| `dok/TERMUX.md` | neu | Einrichtung, Bedienung, manuelle Testliste |
| `tools/episto_tui/tests/test_root_und_konflikte.py` | neu | Tests zu Task 1 |
| `tools/episto_tui/tests/test_reader_pane_modus.py` | neu | Tests zu Task 2 |
| `tools/episto_tui/tests/test_aktionsleiste.py` | neu | Tests zu Task 3 |
| `tools/episto_tui/tests/test_layout_schmal.py` | neu | Tests zu Task 4 |

Abgrenzung zur Spec, bewusst festgelegt: (1) Im breiten Modus fokussiert die Taste `0` den Baum (auf dem PC gibt es sonst keinen Tastaturweg zurück in den Baum); im schmalen Modus schaltet sie die Baum-Ansicht um. (2) Im schmalen Modus startet die App mit **offenem Baum**, solange noch kein Kapitel gewählt wurde: sonst hätte ein unsichtbarer Baum den Fokus und würde Tastendrücke in seinen Filter schlucken. (3) Beim Wechsel zurück in den breiten Modus wird `baum-offen` zurückgesetzt.

---

### Task 1: Wurzelpfad und Konfliktkopien

**Files:**
- Modify: `tools/episto_tui/library.py` (Imports oben, `list_chapters` bei Zeile 62–64, neue Funktion nach `DEFAULT_ROOT`)
- Modify: `tools/episto_tui/__main__.py`
- Test: `tools/episto_tui/tests/test_root_und_konflikte.py`

**Interfaces:**
- Consumes: `library.DEFAULT_ROOT: Path`, `library.list_chapters(buch: Buch) -> list[Kapitel]`, `EpistoApp(root: Path | None)`.
- Produces: `library.resolve_root(arg: str | None, env: Mapping[str, str], plattform: str | None = None) -> Path`; `episto_tui.__main__.bestimme_root(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> Path`; `episto_tui.__main__.main(argv: Sequence[str] | None = None) -> None`.

- [ ] **Step 1: Failing tests schreiben**

`tools/episto_tui/tests/test_root_und_konflikte.py`:

```python
from pathlib import Path

from episto_tui import library
from episto_tui.__main__ import bestimme_root


def test_argument_hat_vorrang_vor_umgebung_und_standard():
    assert library.resolve_root("/a/b", {"EPISTO_ROOT": "/c"}, plattform="linux") == Path("/a/b")


def test_umgebungsvariable_hat_vorrang_vor_standard():
    assert library.resolve_root(None, {"EPISTO_ROOT": "/c"}, plattform="linux") == Path("/c")


def test_standard_unter_windows_ist_default_root():
    assert library.resolve_root(None, {}, plattform="win32") == library.DEFAULT_ROOT


def test_standard_sonst_ist_home_episto(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert library.resolve_root(None, {}, plattform="linux") == tmp_path / "episto"


def test_leere_werte_zaehlen_nicht():
    assert library.resolve_root("", {"EPISTO_ROOT": ""}, plattform="win32") == library.DEFAULT_ROOT


def test_tilde_wird_aufgeloest(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert library.resolve_root("~/lib", {}, plattform="linux") == tmp_path / "lib"


def test_bestimme_root_liest_root_argument():
    assert bestimme_root(["--root", "x"], {}) == Path("x")


def test_bestimme_root_faellt_auf_umgebung_zurueck():
    assert bestimme_root([], {"EPISTO_ROOT": "y"}) == Path("y")


def test_glob_fallback_ignoriert_syncthing_konfliktkopien(temp_buch):
    quelle = temp_buch.pfad / "quelle"
    (quelle / "_kapitel_index.json").unlink()
    (quelle / "0001_erstes-kapitel.sync-conflict-20260928-101010-ABCDEFG.md").write_text(
        "Konflikt", encoding="utf-8")
    dateien = [k.datei for k in library.list_chapters(temp_buch)]
    assert dateien == ["0001_erstes-kapitel.md", "0002_zweites-kapitel.md"]


def test_kapitelliste_mit_index_zeigt_keine_konfliktkopien(temp_buch):
    quelle = temp_buch.pfad / "quelle"
    (quelle / "0001_erstes-kapitel.sync-conflict-20260928-101010-ABCDEFG.md").write_text(
        "Konflikt", encoding="utf-8")
    dateien = [k.datei for k in library.list_chapters(temp_buch)]
    assert dateien == ["0001_erstes-kapitel.md", "0002_zweites-kapitel.md"]
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run (in `tools/episto_tui`): `python -m pytest tests/test_root_und_konflikte.py -q`
Expected: FAIL beim Import (`cannot import name 'bestimme_root'`).

- [ ] **Step 3: `library.py` ändern**

Imports ergänzen (zu den bestehenden `import json` / `import dataclasses` / `from pathlib import Path` gehören zusätzlich):

```python
import sys
from collections.abc import Mapping
```

Direkt unter `DEFAULT_ROOT = Path(r"D:\Workspace\!Episto")` einfügen:

```python
def resolve_root(arg: str | None, env: Mapping[str, str], plattform: str | None = None) -> Path:
    """Wurzelordner der Bibliothek: --root, dann EPISTO_ROOT, sonst der
    Standard der Plattform (Windows: DEFAULT_ROOT, sonst ~/episto, so wie
    Syncthing ihn unter Termux anlegt). Leere Werte zaehlen als nicht gesetzt."""
    if arg:
        return Path(arg).expanduser()
    aus_umgebung = env.get("EPISTO_ROOT")
    if aus_umgebung:
        return Path(aus_umgebung).expanduser()
    if (plattform or sys.platform) == "win32":
        return DEFAULT_ROOT
    return Path.home() / "episto"
```

In `list_chapters` den Glob-Fallback ersetzen durch:

```python
    dateien = sorted(
        p for p in (buch.pfad / "quelle").glob("*.md")
        if not p.name.startswith("_") and ".sync-conflict-" not in p.name
    )
```

- [ ] **Step 4: `__main__.py` ersetzen**

```python
from __future__ import annotations
import argparse
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from episto_tui import library
from episto_tui.app import EpistoApp


def bestimme_root(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> Path:
    parser = argparse.ArgumentParser(
        prog="episto_tui",
        description="EPISTO-Bibliothek in der Konsole lesen und bearbeiten.",
    )
    parser.add_argument(
        "--root", default=None,
        help="Wurzelordner der Bibliothek (sonst EPISTO_ROOT, sonst Standard je Plattform)",
    )
    args = parser.parse_args(argv)
    return library.resolve_root(args.root, os.environ if env is None else env)


def main(argv: Sequence[str] | None = None) -> None:
    EpistoApp(root=bestimme_root(argv)).run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Tests laufen lassen**

Run: `python -m pytest tests -q`
Expected: alle Tests grün (156 bisherige plus 10 neue).

- [ ] **Step 6: Commit**

```bash
git add tools/episto_tui/library.py tools/episto_tui/__main__.py tools/episto_tui/tests/test_root_und_konflikte.py
git commit -m "feat(tui): Wurzelpfad per --root/EPISTO_ROOT, Konfliktkopien ausblenden" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: ReaderPane meldet Moduswechsel

**Files:**
- Modify: `tools/episto_tui/widgets/reader_pane.py` (Imports, Klassenkopf, `__init__`)
- Test: `tools/episto_tui/tests/test_reader_pane_modus.py`

**Interfaces:**
- Consumes: `ReaderPane.action_toggle_edit()`, `ReaderPane.action_verwerfen()`, `ReaderPane.lade_kapitel(buch, kapitel)`.
- Produces: `ReaderPane.bearbeiten` bleibt ein bool-Attribut, wird aber Textual-`reactive`; `ReaderPane.ModusGeaendert(bearbeiten: bool)` (Nachricht, `bearbeiten` als Attribut); Handlername für Empfänger: `on_reader_pane_modus_geaendert`. Beim Einhängen des Panes wird einmal `ModusGeaendert(False)` gesendet (Textual ruft Watcher mit dem Startwert).

- [ ] **Step 1: Failing test schreiben**

`tools/episto_tui/tests/test_reader_pane_modus.py`:

```python
import pytest
from textual.app import App, ComposeResult

from episto_tui.models import Kapitel
from episto_tui.widgets.reader_pane import ReaderPane


class _ModusApp(App):
    def __init__(self) -> None:
        super().__init__()
        self.moduse: list[bool] = []

    def compose(self) -> ComposeResult:
        yield ReaderPane()

    def on_reader_pane_modus_geaendert(self, nachricht: ReaderPane.ModusGeaendert) -> None:
        self.moduse.append(nachricht.bearbeiten)


@pytest.mark.asyncio
async def test_reader_pane_meldet_wechsel_zwischen_lesen_und_bearbeiten(temp_buch):
    app = _ModusApp()
    async with app.run_test() as pilot:
        pane = app.query_one(ReaderPane)
        pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
        await pilot.pause()
        app.moduse.clear()

        pane.action_toggle_edit()
        await pilot.pause()
        assert app.moduse == [True]

        pane.action_verwerfen()
        await pilot.pause()
        assert app.moduse == [True, False]
        assert pane.bearbeiten is False
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag prüfen**

Run: `python -m pytest tests/test_reader_pane_modus.py -q`
Expected: FAIL (`AttributeError: type object 'ReaderPane' has no attribute 'ModusGeaendert'`).

- [ ] **Step 3: Implementieren**

In `reader_pane.py` die Imports um zwei Zeilen ergänzen (bei den übrigen `textual`-Imports):

```python
from textual.message import Message
from textual.reactive import reactive
```

Im Klassenkopf von `ReaderPane` direkt nach der `BINDINGS`-Liste einfügen:

```python
    # Reaktiv, damit die Aktionsleiste (Touch) ihre Knoepfe wechseln kann,
    # egal ob der Modus per Taste "e" oder per Knopf umgeschaltet wurde.
    bearbeiten = reactive(False)

    class ModusGeaendert(Message):
        def __init__(self, bearbeiten: bool) -> None:
            self.bearbeiten = bearbeiten
            super().__init__()

    def watch_bearbeiten(self, wert: bool) -> None:
        self.post_message(self.ModusGeaendert(wert))
```

In `__init__` die Zeile `self.bearbeiten = False` **löschen** (der Startwert `False` kommt aus `reactive(False)`; eine Zuweisung vor dem Einhängen soll vermieden werden).

- [ ] **Step 4: Tests laufen lassen**

Run: `python -m pytest tests -q`
Expected: alle grün (bestehende `reader.bearbeiten is False`-Prüfungen gelten weiter, weil `bearbeiten` ein normales bool-Attribut bleibt).

- [ ] **Step 5: Commit**

```bash
git add tools/episto_tui/widgets/reader_pane.py tools/episto_tui/tests/test_reader_pane_modus.py
git commit -m "feat(tui): ReaderPane meldet Moduswechsel per Nachricht" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```


### Task 3: Aktionsleiste (Touch-Knöpfe)

**Files:**
- Create: `tools/episto_tui/widgets/aktionsleiste.py`
- Test: `tools/episto_tui/tests/test_aktionsleiste.py`

**Interfaces:**
- Consumes: nichts aus früheren Tasks.
- Produces: `TippKnopf(Button, can_focus=False)`; `KONTEXTE: dict[str, frozenset[str]]` mit den Schlüsseln `"lesen"`, `"bearbeiten"`, `"felder"`, `"nur_baum"`; `Aktionsleiste(Horizontal)` mit Attribut `kontext: str | None` und Methode `setze_kontext(kontext: str) -> None`; Nachricht `Aktionsleiste.AktionGewaehlt(aktion: str)`, Empfänger-Handler `on_aktionsleiste_aktion_gewaehlt`. Die Aktionsnamen (Knopf-`name`) sind: `baum`, `bearbeiten`, `gelb`, `rosa`, `blau`, `kommentar`, `loeschen`, `speichern`, `verwerfen`; die Knopf-IDs lauten `knopf-<aktion>`. Die Leiste zeigt nichts von sich aus ein oder aus (das macht die App per CSS), sie schaltet nur Knöpfe je Kontext sichtbar.

- [ ] **Step 1: Failing tests schreiben**

`tools/episto_tui/tests/test_aktionsleiste.py`:

```python
import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input

from episto_tui.widgets.aktionsleiste import Aktionsleiste, TippKnopf


class _LeisteApp(App):
    def __init__(self) -> None:
        super().__init__()
        self.aktionen: list[str] = []

    def compose(self) -> ComposeResult:
        yield Input(id="eingabe")
        yield Aktionsleiste()

    def on_aktionsleiste_aktion_gewaehlt(self, nachricht: Aktionsleiste.AktionGewaehlt) -> None:
        self.aktionen.append(nachricht.aktion)


def _sichtbar(app: App) -> list[str]:
    return [knopf.name for knopf in app.query(TippKnopf) if knopf.display]


@pytest.mark.asyncio
async def test_startkontext_zeigt_nur_den_baum_knopf():
    app = _LeisteApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert _sichtbar(app) == ["baum"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kontext, erwartet", [
    ("lesen", ["baum", "bearbeiten", "gelb", "rosa", "blau", "kommentar", "loeschen"]),
    ("bearbeiten", ["speichern", "verwerfen"]),
    ("felder", ["baum", "speichern"]),
    ("nur_baum", ["baum"]),
])
async def test_kontext_bestimmt_die_sichtbaren_knoepfe(kontext, erwartet):
    app = _LeisteApp()
    async with app.run_test() as pilot:
        app.query_one(Aktionsleiste).setze_kontext(kontext)
        await pilot.pause()
        assert _sichtbar(app) == erwartet


@pytest.mark.asyncio
async def test_knopf_sendet_seine_aktion_und_nimmt_keinen_fokus():
    app = _LeisteApp()
    async with app.run_test() as pilot:
        app.query_one("#eingabe", Input).focus()
        app.query_one(Aktionsleiste).setze_kontext("lesen")
        await pilot.pause()
        await pilot.click("#knopf-gelb")
        await pilot.pause()
        assert app.aktionen == ["gelb"]
        assert app.focused is app.query_one("#eingabe", Input)


@pytest.mark.asyncio
async def test_lese_knoepfe_passen_in_45_spalten():
    app = _LeisteApp()
    async with app.run_test(size=(45, 10)) as pilot:
        app.query_one(Aktionsleiste).setze_kontext("lesen")
        await pilot.pause()
        sichtbare = [knopf for knopf in app.query(TippKnopf) if knopf.display]
        assert max(k.region.x + k.region.width for k in sichtbare) <= 45
        assert all(k.region.width > 0 for k in sichtbare)
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run (in `tools/episto_tui`): `python -m pytest tests/test_aktionsleiste.py -q`
Expected: FAIL beim Import (`No module named 'episto_tui.widgets.aktionsleiste'`).

- [ ] **Step 3: Widget schreiben**

`tools/episto_tui/widgets/aktionsleiste.py`:

```python
from __future__ import annotations
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Button

# Reihenfolge = Reihenfolge in der Leiste. Alle Knoepfe existieren von Anfang
# an; je Kontext werden nur die passenden sichtbar geschaltet (kein Neuaufbau
# der Leiste, also keine Wettlaeufe mit noch nicht entfernten Widgets).
_KNOEPFE = [
    ("baum", "Baum"),
    ("bearbeiten", "Edit"),
    ("gelb", "Gelb"),
    ("rosa", "Rosa"),
    ("blau", "Blau"),
    ("kommentar", "Komm"),
    ("loeschen", "Lösch"),
    ("speichern", "Speichern"),
    ("verwerfen", "Verwerfen"),
]

KONTEXTE: dict[str, frozenset[str]] = {
    "lesen": frozenset({"baum", "bearbeiten", "gelb", "rosa", "blau", "kommentar", "loeschen"}),
    "bearbeiten": frozenset({"speichern", "verwerfen"}),
    "felder": frozenset({"baum", "speichern"}),
    "nur_baum": frozenset({"baum"}),
}


class TippKnopf(Button, can_focus=False):
    """Knopf der Aktionsleiste. Nimmt bewusst keinen Fokus: der zuletzt
    angetippte Absatz (ReaderPane) und ein offenes Kommentarfeld muessen
    erhalten bleiben, wenn man auf einen Knopf tippt."""


class Aktionsleiste(Horizontal):
    DEFAULT_CSS = """
    Aktionsleiste {
        height: 1;
        width: 1fr;
        overflow-x: auto;
        scrollbar-size-horizontal: 0;
    }
    Aktionsleiste TippKnopf { min-width: 6; }
    """

    class AktionGewaehlt(Message):
        def __init__(self, aktion: str) -> None:
            self.aktion = aktion
            super().__init__()

    def __init__(self) -> None:
        super().__init__(id="aktionsleiste")
        self.kontext: str | None = None

    def compose(self):
        for aktion, beschriftung in _KNOEPFE:
            yield TippKnopf(beschriftung, compact=True, name=aktion, id=f"knopf-{aktion}")

    def on_mount(self) -> None:
        # Hat die App den Kontext schon vor dem Einhaengen gesetzt, gilt der.
        self._wende_kontext_an()

    def setze_kontext(self, kontext: str) -> None:
        self.kontext = kontext
        self._wende_kontext_an()

    def _wende_kontext_an(self) -> None:
        sichtbar = KONTEXTE[self.kontext or "nur_baum"]
        for knopf in self.query(TippKnopf):
            knopf.display = knopf.name in sichtbar

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.post_message(self.AktionGewaehlt(event.button.name))
```

- [ ] **Step 4: Tests laufen lassen**

Run: `python -m pytest tests/test_aktionsleiste.py -q` und danach `python -m pytest tests -q`
Expected: alle grün. Falls `test_lese_knoepfe_passen_in_45_spalten` knapp scheitert, die Beschriftungen in `_KNOEPFE` kürzen, nicht die Schwelle im Test ändern (Ziel: sieben Lese-Knöpfe in 45 Spalten).

- [ ] **Step 5: Commit**

```bash
git add tools/episto_tui/widgets/aktionsleiste.py tools/episto_tui/tests/test_aktionsleiste.py
git commit -m "feat(tui): Aktionsleiste mit nicht fokussierbaren Touch-Knoepfen" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 4: Schmales Layout, Baum-Schublade und Aktionsleiste in der App

**Files:**
- Modify: `tools/episto_tui/app.py` (komplett ersetzen, siehe Step 3)
- Test: `tools/episto_tui/tests/test_layout_schmal.py`

**Interfaces:**
- Consumes: `Aktionsleiste`, `Aktionsleiste.setze_kontext(kontext: str)`, `Aktionsleiste.AktionGewaehlt.aktion: str`, `TippKnopf` (Task 3); `ReaderPane.bearbeiten: bool`, `ReaderPane.ModusGeaendert` (Task 2); `ChapterSelected`, `LibraryTree`, die `action_*`-Methoden `toggle_edit`, `highlight_gelb`, `highlight_rosa`, `highlight_blau`, `kommentieren`, `kommentar_loeschen`, `speichern`, `verwerfen` von `ReaderPane` und `speichern` von `TagFelderPane`.
- Produces: Konstante `episto_tui.app.SCHMAL_BREITE = 80`; CSS-Klassen `schmal` und `baum-offen` auf dem Screen; App-Aktion `baum_umschalten` (Taste `0`); Methoden `EpistoApp._passe_layout_an(breite: int)`, `_aktives_pane()`, `_aktualisiere_aktionsleiste()`.

- [ ] **Step 1: Failing tests schreiben**

`tools/episto_tui/tests/test_layout_schmal.py`:

```python
import pytest
from textual.widgets import Markdown, TabbedContent, TextArea
from textual.widgets.markdown import MarkdownBlock

from episto_tui import library
from episto_tui.app import EpistoApp
from episto_tui.widgets.aktionsleiste import Aktionsleiste, TippKnopf
from episto_tui.widgets.reader_pane import ReaderPane
from episto_tui.widgets.tree_sidebar import LibraryTree

_LESEN = ["baum", "bearbeiten", "gelb", "rosa", "blau", "kommentar", "loeschen"]


def _sichtbare_knoepfe(app) -> list[str]:
    return [knopf.name for knopf in app.query(TippKnopf) if knopf.display]


async def _waehle_erstes_kapitel(app, pilot) -> None:
    baum = app.query_one(LibraryTree)
    kapitel_knoten = list(baum.root.children)[0].children[0].children[0]
    baum.select_node(kapitel_knoten)
    for _ in range(3):
        await pilot.pause()


@pytest.mark.asyncio
async def test_breit_zeigt_baum_neben_den_tabs_ohne_aktionsleiste(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert not app.screen.has_class("schmal")
        assert 0 < app.query_one(LibraryTree).region.width <= 40
        assert app.query_one(TabbedContent).region.width > 0
        assert app.query_one(Aktionsleiste).region.height == 0


@pytest.mark.asyncio
async def test_schmal_startet_mit_offenem_baum_und_verborgenen_tabs(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        assert app.screen.has_class("schmal")
        assert app.screen.has_class("baum-offen")
        assert app.query_one(LibraryTree).region.width >= 40
        assert app.query_one(TabbedContent).region.height == 0
        assert app.query_one(Aktionsleiste).region.height == 1


@pytest.mark.asyncio
async def test_kapitelwahl_schliesst_die_baum_ansicht(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)
        assert not app.screen.has_class("baum-offen")
        assert app.query_one(ReaderPane).kapitel.nr == 1
        assert app.query_one(TabbedContent).region.height > 0
        assert app.query_one(LibraryTree).region.width == 0


@pytest.mark.asyncio
async def test_baum_knopf_und_taste_null_schalten_die_ansicht_um(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)

        await pilot.click("#knopf-baum")
        await pilot.pause()
        assert app.screen.has_class("baum-offen")
        assert app.query_one(TabbedContent).region.height == 0

        await pilot.click("#knopf-baum")
        await pilot.pause()
        await pilot.pause()
        assert not app.screen.has_class("baum-offen")

        await pilot.press("0")
        await pilot.pause()
        assert app.screen.has_class("baum-offen")
        assert app.focused is app.query_one(LibraryTree)


@pytest.mark.asyncio
async def test_taste_null_fokussiert_im_breiten_modus_den_baum(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)
        assert app.focused is not app.query_one(LibraryTree)
        await pilot.press("0")
        await pilot.pause()
        assert app.focused is app.query_one(LibraryTree)
        assert not app.screen.has_class("baum-offen")


@pytest.mark.asyncio
async def test_wechsel_in_den_breiten_modus_setzt_baum_offen_zurueck(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        assert app.screen.has_class("baum-offen")
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        assert not app.screen.has_class("schmal")
        assert not app.screen.has_class("baum-offen")
        assert app.query_one(TabbedContent).region.width > 0


@pytest.mark.asyncio
async def test_leiste_wechselt_kontext_mit_tab_und_modus(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)
        assert _sichtbare_knoepfe(app) == _LESEN

        await pilot.press("2")
        await pilot.pause()
        assert _sichtbare_knoepfe(app) == ["baum", "speichern"]

        await pilot.press("5")
        await pilot.pause()
        assert _sichtbare_knoepfe(app) == ["baum"]

        await pilot.press("1")
        await pilot.pause()
        assert _sichtbare_knoepfe(app) == _LESEN

        await pilot.click("#knopf-bearbeiten")
        await pilot.pause()
        assert app.query_one(ReaderPane).bearbeiten is True
        assert _sichtbare_knoepfe(app) == ["speichern", "verwerfen"]

        await pilot.click("#knopf-verwerfen")
        await pilot.pause()
        assert app.query_one(ReaderPane).bearbeiten is False
        assert _sichtbare_knoepfe(app) == _LESEN


@pytest.mark.asyncio
async def test_farbknopf_faerbt_den_zuletzt_angetippten_absatz(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)
        bloecke = list(app.query_one("#anzeige", Markdown).query_children(MarkdownBlock))
        await pilot.click(bloecke[1])
        await pilot.pause()
        await pilot.click("#knopf-gelb")
        await pilot.pause()
        highlights = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
        assert [(h.absatz_index, h.farbe) for h in highlights] == [(1, "gelb")]


@pytest.mark.asyncio
async def test_speichern_knopf_im_fazit_reiter_schreibt_die_zusammenfassung(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)
        await pilot.press("2")
        await pilot.pause()
        app.query_one("#feld-zusammenfassung", TextArea).text = "Per Knopf gespeichert."
        await pilot.click("#knopf-speichern")
        await pilot.pause()
        tag = library.read_tags(temp_buch, "0001_erstes-kapitel.md")
        assert tag.zusammenfassung == "Per Knopf gespeichert."
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run (in `tools/episto_tui`): `python -m pytest tests/test_layout_schmal.py -q`
Expected: FAIL (`NoMatches` für `Aktionsleiste`, weil die App sie noch nicht einbindet).

- [ ] **Step 3: `app.py` durch diese Fassung ersetzen**

Die vorhandenen langen Kommentare zu `CSS` und `BINDINGS` bleiben inhaltlich erhalten; der Rest ist neu bzw. ergänzt.

```python
from __future__ import annotations
from pathlib import Path
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, TabbedContent, TabPane
from textual.binding import Binding
from episto_tui import library
from episto_tui.widgets.aktionsleiste import Aktionsleiste
from episto_tui.widgets.tree_sidebar import LibraryTree, ChapterSelected
from episto_tui.widgets.reader_pane import ReaderPane
from episto_tui.widgets.tags_pane import TagsPane, ThesenPane, ZusammenfassungPane
from episto_tui.widgets.straenge_pane import StraengePane
from episto_tui.widgets.querbezuege_pane import QuerbezuegePane

# Unter dieser Terminalbreite (Spalten) gilt das schmale Handy-Layout. 80 ist
# zugleich die Standardgroesse der Tests: sie laufen damit im breiten Modus.
SCHMAL_BREITE = 80

_FOKUS_JE_TAB = {
    "tab-key": ZusammenfassungPane,
    "tab-thesen": ThesenPane,
    "tab-tags": TagsPane,
    "tab-straenge": StraengePane,
    "tab-querbezuege": QuerbezuegePane,
}

_FELDER_TABS = ("tab-key", "tab-thesen", "tab-tags")

# Knopf der Aktionsleiste -> Aktion des aktiven Panes (action_<name>).
_KNOPF_AKTION = {
    "bearbeiten": "toggle_edit",
    "gelb": "highlight_gelb",
    "rosa": "highlight_rosa",
    "blau": "highlight_blau",
    "kommentar": "kommentieren",
    "loeschen": "kommentar_loeschen",
    "speichern": "speichern",
    "verwerfen": "verwerfen",
}


class EpistoApp(App):
    # Ohne dieses CSS beansprucht TabbedContent implizit fast die gesamte
    # Breite des Horizontal-Containers (sein DEFAULT_CSS setzt keine width),
    # wodurch LibraryTree auf 1 Spalte zusammengedrueckt wird - unlesbar und
    # unbedienbar (Bug gefunden nach dem Merge: "TUI zeigt keinen Content",
    # weil sich ohne lesbaren Baum nie ein Kapitel auswaehlen liess).
    #
    # Schmal (Klasse "schmal" auf dem Screen, siehe _passe_layout_an): der
    # Baum ist ausgeblendet und die Aktionsleiste sichtbar; "baum-offen" laesst
    # den Baum voruebergehend die Tabs ersetzen (Schublade fuers Handy).
    CSS = """
    LibraryTree { width: 60; max-width: 40%; margin-right: 1; }
    TabbedContent { width: 1fr; }
    Aktionsleiste { display: none; }
    Screen.schmal LibraryTree { display: none; }
    Screen.schmal Aktionsleiste { display: block; }
    Screen.schmal.baum-offen LibraryTree { display: block; width: 1fr; max-width: 100%; margin-right: 0; }
    Screen.schmal.baum-offen TabbedContent { display: none; }
    """

    # Bewusst KEIN priority=True: waehrend LibraryTree fokussiert ist (Start-
    # zustand), faengt ihr eigenes on_key jedes einzelne druckbare Zeichen --
    # also auch Ziffern und "q" -- fuer die Tippfilterung ab (siehe
    # tree_sidebar.py). Das ist gewolltes Verhalten, wie bei jedem
    # fokussierten Eingabefeld. Damit die Bindings trotzdem praktisch
    # erreichbar sind, verschiebt on_chapter_selected den Fokus nach dem
    # Oeffnen eines Kapitels ausdruecklich in das Pane des aktiven Tabs (der
    # Baum selbst gibt ihn beim Enter NICHT ab); danach greifen Ziffern und
    # "q" normal. Auch die Tab-Aktionen legen den Fokus in das neue Pane,
    # weil Textual den Fokus sonst auf None faellt, sobald das bisher
    # fokussierte Pane mit seinem Tab ausgeblendet wird.
    # (priority=True wurde kurz erprobt, aber wieder verworfen -- siehe
    # Task-14-Review: Textual filtert Tasten, die ein fokussiertes Eingabe-
    # feld selbst konsumieren will (Tree.check_consume_key), ohnehin aus
    # jeder Bindings-Ebene inkl. priority heraus, das Problem bestand also
    # nur bei LibraryTree, nicht bei TextArea/Input. priority=True war damit
    # unnoetig und haette die Angriffsflaeche unnoetig vergroessert.)
    # Aus demselben Grund schaltet "0" nur ausserhalb des Baums um; im
    # schmalen Modus ist der Knopf "Baum" der verlaessliche Weg zurueck.
    BINDINGS = [
        Binding("q", "quit", "Beenden"),
        Binding("0", "baum_umschalten", "Baum"),
        Binding("1", "tab_text", "Text"),
        Binding("2", "tab_key", "Fazit"),
        Binding("3", "tab_thesen", "Thesen"),
        Binding("4", "tab_tags", "Tags"),
        Binding("5", "tab_straenge", "Stränge"),
        Binding("6", "tab_querbezuege", "Querverweise"),
    ]

    def __init__(self, root: Path | None = None) -> None:
        super().__init__()
        self.root_pfad = root if root is not None else library.DEFAULT_ROOT
        self._kapitel_geladen = False

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield LibraryTree(self.root_pfad)
            with TabbedContent(initial="tab-text"):
                with TabPane("Text", id="tab-text"):
                    yield ReaderPane()
                with TabPane("Fazit", id="tab-key"):
                    yield ZusammenfassungPane()
                with TabPane("Thesen", id="tab-thesen"):
                    yield ThesenPane()
                with TabPane("Tags", id="tab-tags"):
                    yield TagsPane()
                with TabPane("Stränge", id="tab-straenge"):
                    yield StraengePane()
                with TabPane("Querverweise", id="tab-querbezuege"):
                    yield QuerbezuegePane()
        yield Aktionsleiste()
        yield Footer()

    def on_mount(self) -> None:
        self._passe_layout_an(self.size.width)
        self.call_after_refresh(self._aktualisiere_aktionsleiste)

    def on_resize(self, event: events.Resize) -> None:
        self._passe_layout_an(event.size.width)

    def _passe_layout_an(self, breite: int) -> None:
        schmal = breite < SCHMAL_BREITE
        self.screen.set_class(schmal, "schmal")
        if not schmal:
            self.screen.set_class(False, "baum-offen")
        elif not self._kapitel_geladen:
            # Ohne gewaehltes Kapitel gibt es nichts zu lesen: der Baum ist
            # der Einstieg. Ein unsichtbarer, aber fokussierter Baum wuerde
            # ausserdem Tastendruecke in seinen Filter schlucken.
            self.screen.set_class(True, "baum-offen")

    def on_chapter_selected(self, event: ChapterSelected) -> None:
        # Jedes Pane einzeln absichern: kaputte Daten in einem Pane (z.B. eine
        # unlesbare Datei) sollen nur dieses Pane betreffen, nicht die ganze
        # App beenden oder die uebrigen Panes am Aktualisieren hindern.
        for pane_typ in (ReaderPane, ZusammenfassungPane, ThesenPane, TagsPane,
                         StraengePane, QuerbezuegePane):
            try:
                self.query_one(pane_typ).lade_kapitel(event.buch, event.kapitel)
            except Exception as exc:
                self.notify(f"Fehler beim Laden: {exc}", severity="error")
        self._kapitel_geladen = True
        if self.screen.has_class("baum-offen"):
            # Schublade schliessen; der Fokus darf erst in das Pane, wenn dessen
            # Tab wieder sichtbar ist (sonst fiele er auf None zurueck).
            self.screen.set_class(False, "baum-offen")
            self.call_after_refresh(self._fokussiere_aktiven_tab)
        else:
            self._fokussiere_aktiven_tab()
        self._aktualisiere_aktionsleiste()

    def _fokussiere_aktiven_tab(self) -> None:
        """Legt den Fokus in das Pane des gerade aktiven Tabs, damit dessen
        Tasten (e / ctrl+s / c) und die App-Bindings (Ziffern, q) greifen.
        Bewusst das AKTIVE Pane statt immer ReaderPane: ein verstecktes, aber
        fokussiertes ReaderPane wuerde "e" unsichtbar in den Editiermodus
        schalten, und ctrl+s auf dem Tags-Tab kaeme nicht bei TagsPane an."""
        aktiv = self.query_one(TabbedContent).active
        if aktiv == "tab-text":
            # ReaderPane hat eine eigene Fokus-Logik (Editor beim Bearbeiten,
            # sonst der scrollbare Anzeige-Bereich - siehe dortigen
            # Klassen-Kommentar zu VerticalScroll/Bindings-Kette).
            self.query_one(ReaderPane).fokus_lesebereich()
            return
        self.query_one(_FOKUS_JE_TAB.get(aktiv, ReaderPane)).focus()

    def _aktives_pane(self):
        aktiv = self.query_one(TabbedContent).active
        return self.query_one(_FOKUS_JE_TAB.get(aktiv, ReaderPane))

    def _aktualisiere_aktionsleiste(self) -> None:
        tabs = self.query(TabbedContent)
        leisten = self.query(Aktionsleiste)
        if not tabs or not leisten:
            return
        aktiv = tabs.first().active
        if aktiv == "tab-text":
            reader = self.query(ReaderPane)
            bearbeiten = bool(reader) and reader.first().bearbeiten
            kontext = "bearbeiten" if bearbeiten else "lesen"
        elif aktiv in _FELDER_TABS:
            kontext = "felder"
        else:
            kontext = "nur_baum"
        leisten.first().setze_kontext(kontext)

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        self._aktualisiere_aktionsleiste()

    def on_reader_pane_modus_geaendert(self, event: ReaderPane.ModusGeaendert) -> None:
        self._aktualisiere_aktionsleiste()

    def on_aktionsleiste_aktion_gewaehlt(self, event: Aktionsleiste.AktionGewaehlt) -> None:
        if event.aktion == "baum":
            self.action_baum_umschalten()
            return
        methode = getattr(self._aktives_pane(), f"action_{_KNOPF_AKTION[event.aktion]}", None)
        if methode is not None:
            methode()

    def action_baum_umschalten(self) -> None:
        if not self.screen.has_class("schmal"):
            # Breit steht der Baum immer daneben; "0" bringt nur den Fokus zurueck.
            self.query_one(LibraryTree).focus()
            return
        offen = not self.screen.has_class("baum-offen")
        self.screen.set_class(offen, "baum-offen")
        if offen:
            self.query_one(LibraryTree).focus()
        else:
            self.call_after_refresh(self._fokussiere_aktiven_tab)

    def action_tab_text(self) -> None:
        self.query_one(TabbedContent).active = "tab-text"
        self._fokussiere_aktiven_tab()

    def action_tab_key(self) -> None:
        self.query_one(TabbedContent).active = "tab-key"
        self._fokussiere_aktiven_tab()

    def action_tab_thesen(self) -> None:
        self.query_one(TabbedContent).active = "tab-thesen"
        self._fokussiere_aktiven_tab()

    def action_tab_tags(self) -> None:
        self.query_one(TabbedContent).active = "tab-tags"
        self._fokussiere_aktiven_tab()

    def action_tab_straenge(self) -> None:
        self.query_one(TabbedContent).active = "tab-straenge"
        self._fokussiere_aktiven_tab()

    def action_tab_querbezuege(self) -> None:
        self.query_one(TabbedContent).active = "tab-querbezuege"
        self._fokussiere_aktiven_tab()
```

- [ ] **Step 4: Tests laufen lassen**

Run: `python -m pytest tests/test_layout_schmal.py -q`, danach `python -m pytest tests -q`
Expected: alle grün (die bestehenden Tests laufen bei 80 Spalten im breiten Modus). Scheitert ein Layout-Test knapp an einer Breite oder Höhe, zuerst mit den `region`-Werten prüfen, welcher Container die Größe bestimmt; die Schwellen der Spec (unter 80 Spalten schmal, Baum höchstens 40 %) nicht ändern.

- [ ] **Step 5: Commit**

```bash
git add tools/episto_tui/app.py tools/episto_tui/tests/test_layout_schmal.py
git commit -m "feat(tui): schmales Layout mit Baum-Schublade und Aktionsleiste" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 5: Startskript, Syncthing-Ignore-Liste und Anleitung

**Files:**
- Create: `.gitattributes`
- Create: `.stignore`
- Create: `tools/episto-tui.sh`
- Create: `dok/TERMUX.md`
- Test: `tools/episto_tui/tests/test_termux_dateien.py`

**Interfaces:**
- Consumes: `python -m episto_tui` mit `--root` und `EPISTO_ROOT` (Task 1).
- Produces: nichts, worauf spätere Tasks bauen.

Hintergrund zu `.gitattributes`: Das Repo läuft unter Windows mit `core.autocrlf=true`; die Arbeitskopie hat dort CRLF-Zeilenenden, und Syncthing überträgt die Arbeitskopie unverändert aufs Handy. Ein Shell-Skript mit CRLF bricht in Termux ab, und Syncthing könnte eine `.stignore` mit CRLF falsch lesen. Deshalb erzwingt `.gitattributes` LF für beide.

- [ ] **Step 1: Failing tests schreiben**

`tools/episto_tui/tests/test_termux_dateien.py`:

```python
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_stignore_enthaelt_die_vorgesehenen_muster():
    zeilen = (REPO / ".stignore").read_text(encoding="utf-8").split()
    for muster in ["**/_backup", ".git", "**/__pycache__", ".worktrees", ".superpowers", "Autor.mov"]:
        assert muster in zeilen


def test_startskript_hat_shebang_und_unix_zeilenenden():
    daten = (REPO / "tools" / "episto-tui.sh").read_bytes()
    assert daten.startswith(b"#!/usr/bin/env sh\n")
    assert b"\r" not in daten


def test_gitattributes_erzwingt_lf_fuer_skript_und_stignore():
    inhalt = (REPO / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in inhalt
    assert ".stignore text eol=lf" in inhalt
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run (in `tools/episto_tui`): `python -m pytest tests/test_termux_dateien.py -q`
Expected: FAIL (`FileNotFoundError` für `.stignore`).

- [ ] **Step 3: Dateien anlegen**

`.gitattributes` (Repo-Wurzel):

```
*.sh text eol=lf
.stignore text eol=lf
```

`.stignore` (Repo-Wurzel; Syncthing-Muster, eine je Zeile):

```
**/_backup
.git
**/__pycache__
.worktrees
.superpowers
Autor.mov
```

`tools/episto-tui.sh` (mit LF-Zeilenenden speichern):

```sh
#!/usr/bin/env sh
# Startet die EPISTO-TUI (Termux, Linux, macOS).
# Ohne EPISTO_ROOT gilt das Elternverzeichnis dieses Skripts, also der
# Wurzelordner der Bibliothek, als Bibliothek. Weitere Argumente (z. B.
# --root PFAD) gehen unveraendert an die TUI.
hier="$(cd "$(dirname "$0")" && pwd)"
: "${EPISTO_ROOT:=$(dirname "$hier")}"
export EPISTO_ROOT
cd "$hier" || exit 1
exec python -m episto_tui "$@"
```

`dok/TERMUX.md` (deutscher Text, wie hier):

````markdown
# EPISTO unter Termux (Android)

Stand 2026-09-28. Diese Anleitung ist **nicht auf einem Gerät geprüft**; die
Testliste am Ende ist dafür da.

EPISTO läuft auf dem Handy als Textual-TUI im Terminal-Programm Termux. Die
Bibliothek wird per Syncthing zwischen PC und Handy abgeglichen, in beide
Richtungen. Nicht dabei: semantische Suche, Übersetzen, Taggen, Ingest.

## Voraussetzungen

- Termux aus F-Droid oder von GitHub (die Play-Store-Fassung ist veraltet).
- Rund 150 MB freier Speicher (Bibliothek ca. 42 MB plus Python-Pakete).
- Syncthing auf dem PC, der Ordner `!Episto` ist der Bibliotheksordner.

## Installation in Termux

```
pkg update
pkg install python syncthing
pip install textual
```

## Abgleich mit Syncthing

1. In Termux `syncthing` starten. Die Oberfläche öffnet man im Handy-Browser
   unter `http://127.0.0.1:8384`.
2. PC und Handy koppeln (Geräte-ID des jeweils anderen eintragen, am anderen
   Gerät bestätigen).
3. Am PC den Ordner `!Episto` für das Handy freigeben. Auf dem Handy als
   Zielordner `~/episto` wählen (das ist `/data/data/com.termux/files/home/episto`).
4. Die Datei `.stignore` gehört zum Ordner und kommt mit: Backups
   (`notizen/_backup`), `.git`, `__pycache__` und Ähnliches bleiben je Gerät
   lokal.
5. Die TUI erst nach dem ersten vollständigen Abgleich starten.

Der komplette Ordner wird abgeglichen, also auch `tools/episto_tui`: das Handy
braucht dadurch keinen zweiten Weg für den Programmcode.

## Start

```
sh ~/episto/tools/episto-tui.sh
```

Oder von Hand:

```
cd ~/episto/tools
EPISTO_ROOT=~/episto python -m episto_tui
```

Der Wurzelordner lässt sich auch mit `--root PFAD` angeben.

## Bedienung am Handy

- **Hochformat (unter 80 Spalten):** Beim Start ist der Baum offen. Ein Kapitel
  antippen öffnet es und schließt den Baum. Der Knopf **Baum** unten öffnet ihn
  wieder.
- **Querformat (ab 80 Spalten):** wie am PC, Baum links neben dem Text.
- **Reiter:** antippen, oder die Tasten 1 bis 6.
- **Text-Reiter:** einen Absatz antippen, dann **Gelb**, **Rosa** oder
  **Blau** zum Hervorheben. **Komm** legt einen Kommentar am angetippten Absatz
  an; einen Kommentarblock antippen und **Komm** ändert ihn, **Lösch** löscht
  ihn. **Edit** öffnet den Editor, **Speichern** und **Verwerfen** beenden ihn.
- **Fazit, Thesen, Tags:** Text ändern, dann **Speichern**.
- Mit Bluetooth-Tastatur gelten die Tastenkürzel wie am PC. Strg gibt es über
  die Zusatzzeile von Termux.

## Konflikte

Ändern PC und Handy dieselbe Datei gleichzeitig, legt Syncthing eine Kopie
`<name>.sync-conflict-<datum>-<id>.<endung>` an. Die TUI zeigt solche Dateien
nicht als Kapitel an. Die beiden Fassungen von Hand vergleichen und die
überflüssige löschen.

## Wenn Wischen das Terminal statt der App scrollt

Termux ersetzt dann das Scrollen der App. Abhilfe: die Zusatzzeile um
Bildtasten erweitern. In `~/.termux/termux.properties`:

```
extra-keys = [['ESC','CTRL','PGUP','PGDN','UP','DOWN','LEFT','RIGHT']]
```

Danach `termux-reload-settings` ausführen.

## Testliste für das Gerät

Diese Punkte lassen sich unter Windows nicht prüfen:

- [ ] `pip install textual` läuft durch, `python -m episto_tui --help` zeigt die Hilfe.
- [ ] Im Hochformat startet die TUI mit offenem Baum.
- [ ] Tippen auf ein Kapitel öffnet es (Tippen zählt als Mausklick).
- [ ] Wischen scrollt den Text (sonst siehe oben).
- [ ] Die Knopfleiste ist vollständig sichtbar, die Reiterleiste scrollt oder passt.
- [ ] Absatz antippen, **Gelb** färbt ihn.
- [ ] Kommentar: Absatz antippen, **Komm**, Text mit der Softtastatur, Enter.
- [ ] Editor: **Edit**, Text ändern, **Speichern**.
- [ ] Fazit-Reiter: Text ändern, **Speichern**, die Änderung erscheint nach dem Abgleich am PC.
- [ ] Ein am PC angelegter Kommentar erscheint nach dem Abgleich am Handy.
- [ ] Im Querformat (ab 80 Spalten) steht der Baum neben dem Text.
````

- [ ] **Step 4: Tests und Skript prüfen**

Run (in `tools/episto_tui`): `python -m pytest tests/test_termux_dateien.py -q` und `python -m pytest tests -q`
Expected: alle grün.

Run (im Repo-Wurzelordner): `sh tools/episto-tui.sh --help`
Expected: die argparse-Hilfe von `episto_tui` (Zeile `usage: episto_tui [-h] [--root ROOT]`), kein Fehler wegen `\r`.

- [ ] **Step 5: Commit**

```bash
git add .gitattributes .stignore tools/episto-tui.sh dok/TERMUX.md tools/episto_tui/tests/test_termux_dateien.py
git update-index --chmod=+x tools/episto-tui.sh
git commit -m "docs(tui): Termux-Startskript, Syncthing-Ignore-Liste und Anleitung" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Abschluss und Spec-Abgleich

**Files:**
- Modify: keine Programmdateien; nur Prüfung und Dokumentation.

**Interfaces:**
- Consumes: alles aus Task 1 bis 5.
- Produces: bestätigter, gemergter Stand.

- [ ] **Step 1: Spec und Plan committen (falls noch nicht geschehen)**

```bash
git add dok/2026-09-28-termux-design.md dok/2026-09-28-termux-implementation-plan.md
git commit -m "docs: Design und Implementierungsplan fuer EPISTO unter Termux" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

- [ ] **Step 2: Gesamtlauf**

Run (in `tools/episto_tui`): `python -m pytest tests -q`
Expected: alles grün, mehr Tests als die 156 des Ausgangsstands (Task 1: 10, Task 2: 1, Task 3: 7, Task 4: 9, Task 5: 3, zusammen 30 neue).

- [ ] **Step 3: Spec-Abgleich**

Jeden Punkt der Spec `dok/2026-09-28-termux-design.md` gegen den Code halten und abhaken:

- [ ] `resolve_root`: Argument, Umgebung, Plattform-Standard (Task 1)
- [ ] `--root` in `__main__.py` (Task 1)
- [ ] Startskript, `.stignore`, `TERMUX.md` (Task 5)
- [ ] Breit: `max-width: 40%`, `width: 60` (Task 4, `CSS`)
- [ ] Schmal unter 80 Spalten, Baum-Schublade, Taste `0` und Knopf (Task 4)
- [ ] Reiterleiste scrollt bei Platzmangel (bewusst nicht automatisch getestet, steht in der Testliste in `TERMUX.md`)
- [ ] Aktionsleiste mit den Kontexten aus der Spec-Tabelle, Knöpfe ohne Fokus (Task 3)
- [ ] Konfliktkopien nie als Kapitel (Task 1)
- [ ] Nicht-Ziele unangetastet: keine Änderung an Suche, Pipeline, Qdrant, Ollama

- [ ] **Step 4: Sichtprüfung des schmalen Layouts**

Run (in `tools/episto_tui`):

```bash
python - <<'EOF'
import asyncio
from pathlib import Path
from episto_tui.app import EpistoApp

async def main():
    app = EpistoApp(root=Path(r"D:\Workspace\!Episto"))
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        Path("schmal-baum.svg").write_text(app.export_screenshot(), encoding="utf-8")
        baum = app.query_one("LibraryTree")
        baum.select_node(list(baum.root.children)[0].children[0].children[0])
        await pilot.pause(); await pilot.pause()
        Path("schmal-text.svg").write_text(app.export_screenshot(), encoding="utf-8")

asyncio.run(main())
EOF
```

Expected: zwei SVG-Dateien; auf `schmal-baum.svg` steht der Baum in voller Breite und unten die Aktionsleiste mit dem Knopf „Baum“, auf `schmal-text.svg` der Text mit den Knöpfen Baum, Edit, Gelb, Rosa, Blau, Komm, Lösch. Beide Dateien danach löschen (nicht committen).

- [ ] **Step 5: Übergabe**

Nach dem finalen Review folgt `superpowers:finishing-a-development-branch`. Vom Nutzer auf dem Handy zu prüfen bleibt die Testliste in `dok/TERMUX.md`.
