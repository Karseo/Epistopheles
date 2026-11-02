# Kommentare direkt im Textfenster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kommentare lassen sich im Lesemodus des `ReaderPane` per Klick + Taste anlegen (`c`), ändern (`c` auf einem Kommentarblock) und löschen (`d`); ihr Text steht als Zitat-Block direkt unter dem Absatz. Der Tab "Kommentare" (`KommentarePane`) entfällt.

**Architecture:** `annotate.render_mit_kommentaren()` ersetzt `render_with_markers()` und liefert neben dem anzuzeigenden Markdown-Text eine Segmentliste (Absatz / Kommentar / Überschrift mit Startzeile). Die bestehende zeilenbasierte Klick- und Färbe-Zuordnung im `ReaderPane` arbeitet danach auf Segmenten statt auf reinen Absatz-Startzeilen. Zwei neue `library`-Funktionen (`update_kommentar`, `remove_kommentar`) ergänzen `add_kommentar`; ein `Input` im `ReaderPane` nimmt den Kommentartext entgegen.

**Tech Stack:** Python, Textual 8.2.8 (`Markdown`/`MarkdownBlock`, `Input`, `events.Click`), pytest + pytest-asyncio.

## Global Constraints

- Kommentieren nur im Lesemodus; `c`/`d` tun im Editiermodus (`self.bearbeiten`), ohne vorherigen Klick oder ohne `self.buch` nichts.
- Klick in einen **Absatz**, dann `c` = neuer Kommentar an diesem Absatz. Klick auf einen **Kommentarblock**, dann `c` = Kommentar ändern (Eingabefeld mit bisherigem Text). Klick auf einen Kommentarblock, dann `d` = löschen, ohne Rückfrage. `d` auf einem Absatz tut nichts. Enter speichert, Esc bricht ab, ein leerer Text legt nichts an bzw. ändert nichts.
- Ein Klick auf einen Kommentarblock merkt sich zusätzlich dessen Absatz als aktiven Absatz (Farbtasten `g`/`r`/`b` wirken dann auf diesen Absatz); der Kommentarblock selbst wird nie eingefärbt. Klick auf die Überschrift "Kommentare ohne Absatz" oder auf einen verwaisten Kommentar setzt keinen aktiven Absatz.
- Anzeige: `> 💬 <Text> — <erstellt>` (Zitat-Block, ein Block pro Kommentar, Erstellungsreihenfolge, Blöcke durch Leerzeilen getrennt). Keine hochgestellten Marken `[¹]` mehr.
- Kommentartext und Datum werden als reiner Text behandelt: Backslash, Backtick, Stern, Unterstrich, `[`, `]`, `#`, `>`, `|` werden mit Backslash maskiert; Zeilenumbrüche im Text werden zu Leerzeichen (der Block bleibt einzeilig).
- Kommentare ohne auffindbaren Absatz (`locate_paragraph()` → `None`) stehen am Kapitelende unter `## Kommentare ohne Absatz`, ebenfalls änder- und löschbar.
- Kommentare haben keine ID: `update_kommentar`/`remove_kommentar` identifizieren über alle Felder (`datei`, `absatz_index`, `absatz_anfang`, `text`, `erstellt`), erster exakter Treffer; kein Treffer oder fehlende Datei = nichts tun, kein Backup. Vor jedem echten Schreiben `backup_before_write`.
- `Kommentar` und `notizen/kommentare.json` bleiben unverändert.
- `lade_kapitel()` und `_zeige_lesemodus()` bleiben synchron (bestehende Tests rufen sie ohne `await` auf); Fokus wird beim Laden nur gesetzt, wenn das Pane sichtbar ist (bestehende Regel `_sichtbar_im_baum()`).
- Deutsche Bezeichner/Kommentare wie im restlichen Code; Kommentare nur, wenn das WARUM nicht offensichtlich ist.

---

### Task 1: `library.update_kommentar()` und `library.remove_kommentar()`

**Files:**
- Modify: `tools/episto_tui/library.py` (Import `dataclasses` oben ergänzen; zwei Funktionen + Hilfsfunktion direkt nach `add_kommentar`)
- Test: `tools/episto_tui/tests/test_library_kommentare.py` (anhängen)

**Interfaces:**
- Consumes: `_lade_json_dict`, `_kommentare_pfad`, `backup_before_write` (alle bereits in `library.py`), `Kommentar` (`from_dict`/`to_dict`, Dataclass mit Gleichheit über alle Felder).
- Produces: `update_kommentar(buch: Buch, alt: Kommentar, neuer_text: str) -> None`, `remove_kommentar(buch: Buch, kommentar: Kommentar) -> None` — genutzt in Task 3.

- [ ] **Step 1: Write the failing tests**

An das Ende von `tools/episto_tui/tests/test_library_kommentare.py` anhängen:

```python
def _kommentar(text="Notiz", absatz_index=0, datei="0001_erstes-kapitel.md"):
    return Kommentar(
        datei=datei, absatz_index=absatz_index, absatz_anfang="Anfang",
        text=text, erstellt="2026-09-28 10:00",
    )


def test_update_kommentar_aendert_nur_den_text_des_treffers(temp_buch):
    a = _kommentar("Alt", absatz_index=0)
    b = _kommentar("Anderer", absatz_index=1)
    library.add_kommentar(temp_buch, a)
    library.add_kommentar(temp_buch, b)

    library.update_kommentar(temp_buch, a, "Neu")

    gelesen = library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")
    assert [(k.absatz_index, k.text) for k in gelesen] == [(0, "Neu"), (1, "Anderer")]
    assert gelesen[0].erstellt == "2026-09-28 10:00"
    assert gelesen[0].absatz_anfang == "Anfang"


def test_update_kommentar_ohne_treffer_tut_nichts_und_sichert_nicht(temp_buch):
    library.add_kommentar(temp_buch, _kommentar("Da"))

    library.update_kommentar(temp_buch, _kommentar("Nicht vorhanden"), "X")

    gelesen = library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")
    assert [k.text for k in gelesen] == ["Da"]
    assert list((temp_buch.pfad / "notizen" / "_backup").glob("kommentare.*.json")) == []


def test_update_und_remove_ohne_datei_tun_nichts(temp_buch):
    library.update_kommentar(temp_buch, _kommentar(), "X")  # keine Exception
    library.remove_kommentar(temp_buch, _kommentar())       # keine Exception
    assert not (temp_buch.pfad / "notizen" / "kommentare.json").exists()


def test_remove_kommentar_entfernt_genau_einen_von_zwei_identischen(temp_buch):
    gleich = _kommentar("Gleich")
    library.add_kommentar(temp_buch, gleich)
    library.add_kommentar(temp_buch, gleich)

    library.remove_kommentar(temp_buch, gleich)

    assert len(library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")) == 1


def test_remove_kommentar_laesst_andere_absaetze_und_kapitel_unberuehrt(temp_buch):
    a = _kommentar("A", absatz_index=0)
    b = _kommentar("B", absatz_index=1)
    c = _kommentar("C", absatz_index=0, datei="0002_zweites-kapitel.md")
    for k in (a, b, c):
        library.add_kommentar(temp_buch, k)

    library.remove_kommentar(temp_buch, a)

    assert [k.text for k in library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")] == ["B"]
    assert [k.text for k in library.read_kommentare(temp_buch, "0002_zweites-kapitel.md")] == ["C"]


def test_update_und_remove_sichern_vorherigen_stand(temp_buch):
    a = _kommentar("Eins")
    library.add_kommentar(temp_buch, a)  # Datei existiert noch nicht: kein Backup

    library.update_kommentar(temp_buch, a, "Zwei")
    library.remove_kommentar(temp_buch, _kommentar("Zwei"))

    backups = list((temp_buch.pfad / "notizen" / "_backup").glob("kommentare.*.json"))
    assert len(backups) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools && python -m pytest episto_tui/tests/test_library_kommentare.py -v`
Expected: die 6 neuen Tests FAIL mit `AttributeError: module 'episto_tui.library' has no attribute 'update_kommentar'` (bzw. `remove_kommentar`); die 4 bestehenden PASS.

- [ ] **Step 3: Implement**

In `tools/episto_tui/library.py` direkt unter `import json` (Zeile 2) `import dataclasses` einfügen. Nach `add_kommentar` (direkt vor `_highlights_pfad`) einfügen:

```python
def _finde_kommentar(eintraege: list, gesucht: Kommentar) -> int | None:
    for i, eintrag in enumerate(eintraege):
        if isinstance(eintrag, dict) and Kommentar.from_dict(eintrag) == gesucht:
            return i
    return None


def update_kommentar(buch: Buch, alt: Kommentar, neuer_text: str) -> None:
    pfad = _kommentare_pfad(buch)
    daten = _lade_json_dict(pfad)
    if daten is None or not isinstance(daten.get("kommentare"), list):
        return
    i = _finde_kommentar(daten["kommentare"], alt)
    if i is None:
        return
    backup_before_write(buch.pfad, pfad)
    daten["kommentare"][i] = dataclasses.replace(alt, text=neuer_text).to_dict()
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def remove_kommentar(buch: Buch, kommentar: Kommentar) -> None:
    pfad = _kommentare_pfad(buch)
    daten = _lade_json_dict(pfad)
    if daten is None or not isinstance(daten.get("kommentare"), list):
        return
    i = _finde_kommentar(daten["kommentare"], kommentar)
    if i is None:
        return
    backup_before_write(buch.pfad, pfad)
    del daten["kommentare"][i]
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools && python -m pytest episto_tui/tests/test_library_kommentare.py -v`
Expected: alle 10 PASS. Danach volle Suite: `cd tools && python -m pytest episto_tui/tests -q` → 125 passed (119 + 6).

- [ ] **Step 5: Commit**

```bash
git add tools/episto_tui/library.py tools/episto_tui/tests/test_library_kommentare.py
git commit -m "feat: library.update_kommentar()/remove_kommentar() (Treffer über alle Felder, mit Backup)"
```

---

### Task 2: Kommentare als Blöcke im Lesemodus (Renderfunktion + Segment-Zuordnung)

**Files:**
- Modify: `tools/episto_tui/annotate.py` (`render_with_markers` und `_ZIFFERN` ersetzen)
- Modify: `tools/episto_tui/widgets/reader_pane.py` (Zuordnung auf Segmente umstellen)
- Test: `tools/episto_tui/tests/test_annotate.py` (Import und alle `render_with_markers`-Tests ersetzen)
- Test: `tools/episto_tui/tests/test_reader_pane.py` (anhängen)

**Interfaces:**
- Consumes: `annotate.locate_paragraph(paragraphs, absatz_index, absatz_anfang) -> int | None`, `Kommentar`, die bestehenden Helfer `_zeilenbereich`, `_aufgeloeste_highlights` in `reader_pane.py`.
- Produces: `annotate.maskiere_markdown(text: str) -> str`; `annotate.Segment` (Dataclass: `startzeile: int`, `art: str` in `{"absatz", "kommentar", "kopf"}`, `absatz_index: int | None = None`, `kommentar: Kommentar | None = None`); `annotate.render_mit_kommentaren(paragraphs: list[str], kommentare: list[Kommentar]) -> tuple[str, list[Segment]]`; in `ReaderPane`: Attribute `_aktiver_kommentar: Kommentar | None`, `_angezeigte_segmente: list[Segment]` — in Task 3 genutzt. `render_with_markers` und `_absatz_startzeilen` entfallen.

**Verifiziertes Textual-Verhalten (nicht neu prüfen):** Ein Zitat-Block `> 💬 …` nach einer Leerzeile wird ein eigener oberster `MarkdownBlockQuote` mit `source_range` = seine Zeile und einem verschachtelten `MarkdownParagraph`, dessen `str(block.content)` den Klartext liefert (maskierte Zeichen wie `\[LdF\]` erscheinen wörtlich als `[LdF]`); der Zitat-Block selbst hat `str(content) == ""`.

- [ ] **Step 1: Write the failing tests (annotate)**

`tools/episto_tui/tests/test_annotate.py`: Zeile 1 ersetzen durch

```python
from episto_tui.annotate import (
    split_paragraphs, locate_paragraph, maskiere_markdown, render_mit_kommentaren, Segment,
)
```

und alles ab `def test_render_with_markers_haengt_marke_an_richtigen_absatz():` (Zeile 31) bis Dateiende ersetzen durch:

```python
def _k(index, anfang, text="Notiz", erstellt="2026-09-28 10:00"):
    return Kommentar(
        datei="x.md", absatz_index=index, absatz_anfang=anfang,
        text=text, erstellt=erstellt,
    )


def test_maskiere_markdown_maskiert_sonderzeichen():
    roh = "Vgl. [LdF] und [/] *fett* _kursiv_ `code` # > | \\"
    assert maskiere_markdown(roh) == (
        "Vgl. \\[LdF\\] und \\[/\\] \\*fett\\* \\_kursiv\\_ \\`code\\` \\# \\> \\| \\\\"
    )


def test_render_ohne_kommentare_ist_reine_absatzliste():
    text, segmente = render_mit_kommentaren(["Erster Absatz.", "Zweiter Absatz."], [])
    assert text == "Erster Absatz.\n\nZweiter Absatz."
    assert segmente == [Segment(0, "absatz", 0, None), Segment(2, "absatz", 1, None)]


def test_render_haengt_kommentarblock_direkt_unter_den_richtigen_absatz():
    k = _k(1, "Zweiter Absatz")
    text, segmente = render_mit_kommentaren(["Erster Absatz.", "Zweiter Absatz.", "Dritter."], [k])
    assert text == (
        "Erster Absatz.\n\nZweiter Absatz.\n\n> \U0001f4ac Notiz — 2026-09-28 10:00\n\nDritter."
    )
    assert [(s.startzeile, s.art, s.absatz_index) for s in segmente] == [
        (0, "absatz", 0), (2, "absatz", 1), (4, "kommentar", 1), (6, "absatz", 2),
    ]
    assert segmente[2].kommentar == k


def test_render_mehrere_kommentare_je_eigener_block_in_reihenfolge():
    k1, k2 = _k(0, "Erster", "Eins"), _k(0, "Erster", "Zwei")
    text, segmente = render_mit_kommentaren(["Erster Absatz."], [k1, k2])
    assert text == (
        "Erster Absatz.\n\n> \U0001f4ac Eins — 2026-09-28 10:00"
        "\n\n> \U0001f4ac Zwei — 2026-09-28 10:00"
    )
    assert [s.kommentar for s in segmente] == [None, k1, k2]


def test_render_mehrzeiliger_absatz_verschiebt_folgende_startzeilen():
    _text, segmente = render_mit_kommentaren(["Zeile a\nZeile b", "Zweiter."], [_k(0, "Zeile a")])
    assert [(s.startzeile, s.art) for s in segmente] == [
        (0, "absatz"), (3, "kommentar"), (5, "absatz"),
    ]


def test_render_maskiert_kommentartext():
    text, _ = render_mit_kommentaren(["A."], [_k(0, "A.", "Vgl. [LdF] und [/]")])
    assert "Vgl. \\[LdF\\] und \\[/\\]" in text


def test_render_haelt_kommentarblock_einzeilig():
    text, _ = render_mit_kommentaren(["A."], [_k(0, "A.", "eins\nzwei")])
    assert "> \U0001f4ac eins zwei —" in text


def test_render_verwaiste_kommentare_am_kapitelende_unter_eigener_ueberschrift():
    k = _k(9, "Text, der nicht mehr existiert")
    text, segmente = render_mit_kommentaren(["Einziger Absatz."], [k])
    assert text == (
        "Einziger Absatz.\n\n## Kommentare ohne Absatz\n\n> \U0001f4ac Notiz — 2026-09-28 10:00"
    )
    assert [(s.startzeile, s.art, s.absatz_index) for s in segmente] == [
        (0, "absatz", 0), (2, "kopf", None), (4, "kommentar", None),
    ]
    assert segmente[2].kommentar == k
```

- [ ] **Step 2: Implement `annotate.py`**

In `tools/episto_tui/annotate.py` die Importe am Kopf ersetzen durch

```python
from __future__ import annotations
import re
from dataclasses import dataclass
from episto_tui.models import Kommentar
```

`_ZIFFERN` (Zeile 5) und die komplette Funktion `render_with_markers` (Zeile 28 bis Dateiende) ersetzen durch (`split_paragraphs` und `locate_paragraph` bleiben unverändert):

```python
_MD_SONDERZEICHEN = re.compile(r"([\\`*_\[\]#>|])")


def maskiere_markdown(text: str) -> str:
    """Nutzereingabe soll woertlich erscheinen: "[LdF]" oder "[/]" duerfen
    weder verschwinden noch das Markdown-Rendering zerlegen."""
    return _MD_SONDERZEICHEN.sub(r"\\\1", text)


@dataclass
class Segment:
    """Ein Block des angezeigten Markdown-Texts. startzeile bezieht sich auf
    den von render_mit_kommentaren() gelieferten Text. absatz_index ist bei
    "absatz" der eigene, bei "kommentar" der Absatz, an dem er haengt (None
    bei verwaisten Kommentaren und bei "kopf")."""
    startzeile: int
    art: str  # "absatz" | "kommentar" | "kopf"
    absatz_index: int | None = None
    kommentar: Kommentar | None = None


def _kommentar_block(kommentar: Kommentar) -> str:
    text = maskiere_markdown(" ".join(kommentar.text.split()))
    return f"> \U0001f4ac {text} — {maskiere_markdown(kommentar.erstellt)}"


def render_mit_kommentaren(paragraphs: list[str], kommentare: list[Kommentar]) -> tuple[str, list[Segment]]:
    """Baut den anzuzeigenden Markdown-Text: nach jedem Absatz seine
    Kommentare als Zitat-Bloecke, am Ende verwaiste Kommentare unter einer
    Ueberschrift. Alle Bloecke sind durch Leerzeilen getrennt; die
    Segmentliste kennt die Startzeile jedes Blocks (fuer die Klick- und
    Faerbe-Zuordnung im ReaderPane)."""
    je_absatz: dict[int, list[Kommentar]] = {}
    verwaist: list[Kommentar] = []
    for kommentar in kommentare:
        index = locate_paragraph(paragraphs, kommentar.absatz_index, kommentar.absatz_anfang)
        if index is None:
            verwaist.append(kommentar)
        else:
            je_absatz.setdefault(index, []).append(kommentar)

    bloecke: list[tuple[str, str, int | None, Kommentar | None]] = []
    for i, absatz in enumerate(paragraphs):
        bloecke.append((absatz, "absatz", i, None))
        for kommentar in je_absatz.get(i, []):
            bloecke.append((_kommentar_block(kommentar), "kommentar", i, kommentar))
    if verwaist:
        bloecke.append(("## Kommentare ohne Absatz", "kopf", None, None))
        for kommentar in verwaist:
            bloecke.append((_kommentar_block(kommentar), "kommentar", None, kommentar))

    segmente: list[Segment] = []
    zeile = 0
    for text, art, absatz_index, kommentar in bloecke:
        segmente.append(Segment(zeile, art, absatz_index, kommentar))
        zeile += text.count("\n") + 2  # Blockzeilen + Leerzeile dazwischen
    return "\n\n".join(text for text, *_ in bloecke), segmente
```

- [ ] **Step 3: Write the failing tests (reader_pane)**

An das Ende von `tools/episto_tui/tests/test_reader_pane.py` anhängen (`_oberste_bloecke` ist weiter oben in der Datei bereits definiert):

```python
# --- Kommentare als Bloecke im Lesemodus ------------------------------------

def _klartext(block) -> str:
    from textual.widgets.markdown import MarkdownBlock
    teile = [str(b.content) for b in (block, *block.query(MarkdownBlock))]
    return " ".join(t for t in teile if t)


def _kommentar(anfang, text="Notiz", absatz_index=0):
    from episto_tui.models import Kommentar
    return Kommentar(
        datei="0001_erstes-kapitel.md", absatz_index=absatz_index,
        absatz_anfang=anfang, text=text, erstellt="2026-09-28 10:00",
    )


_ANFANG_1 = "Erster Absatz des ersten Kapitels."
_ANFANG_2 = "Zweiter Absatz mit mehr Inhalt zum Testen."
_ANFANG_3 = "Dritter Absatz, der letzte hier."


async def _lade_kapitel_1(app, pilot, temp_buch):
    from episto_tui.models import Kapitel
    pane = app.query_one(ReaderPane)
    pane.lade_kapitel(temp_buch, Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md"))
    await pilot.pause()
    await pilot.pause()
    return pane


@pytest.mark.asyncio
async def test_kommentar_wird_als_block_unter_dem_absatz_angezeigt(temp_buch):
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1, "Vgl. Popper [LdF] S. 12 und [/]"))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        texte = [_klartext(b) for b in _oberste_bloecke(app)]
        assert len(texte) == 4  # drei Absaetze + ein Kommentarblock
        assert texte[0] == _ANFANG_1
        assert texte[1] == "\U0001f4ac Vgl. Popper [LdF] S. 12 und [/] — 2026-09-28 10:00"
        assert texte[2] == _ANFANG_2


@pytest.mark.asyncio
async def test_farbtaste_faerbt_den_absatz_nicht_den_kommentarblock(temp_buch):
    from textual.color import Color
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[0])
        await pilot.press("g")
        await pilot.pause()
        await pilot.pause()
        bloecke = _oberste_bloecke(app)
        assert bloecke[0].styles.background == Color.parse("#595900")
        assert bloecke[1].styles.background == Color.parse("transparent")
        assert bloecke[2].styles.background == Color.parse("transparent")


@pytest.mark.asyncio
async def test_klick_auf_letzten_absatz_trifft_trotz_kommentarbloecken_den_richtigen_index(temp_buch):
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1, "Eins", 0))
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1, "Zwei", 0))
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_2, "Drei", 1))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        bloecke = _oberste_bloecke(app)
        assert len(bloecke) == 6
        await pilot.click(bloecke[-1])
        await pilot.press("b")
        await pilot.pause()
        await pilot.pause()
        gelesen = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
        assert [(h.absatz_index, h.farbe) for h in gelesen] == [(2, "blau")]


@pytest.mark.asyncio
async def test_klick_auf_kommentarblock_merkt_kommentar_und_absatz(temp_buch):
    k = _kommentar(_ANFANG_2, "Notiz", 1)
    library.add_kommentar(temp_buch, k)
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[2])  # Kommentarblock unter Absatz 2
        assert pane._aktiver_kommentar == k
        assert pane._aktiver_absatz_index == 1
        await pilot.click(_oberste_bloecke(app)[0])  # ein Absatz loest den Kommentar wieder
        assert pane._aktiver_kommentar is None
        assert pane._aktiver_absatz_index == 0


@pytest.mark.asyncio
async def test_farbtaste_nach_klick_auf_kommentarblock_faerbt_dessen_absatz(temp_buch):
    from textual.color import Color
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[1])
        await pilot.press("r")
        await pilot.pause()
        await pilot.pause()
        bloecke = _oberste_bloecke(app)
        assert bloecke[0].styles.background == Color.parse("#594347")
        assert bloecke[1].styles.background == Color.parse("transparent")


@pytest.mark.asyncio
async def test_verwaister_kommentar_steht_am_kapitelende_und_ist_anklickbar(temp_buch):
    k = _kommentar("Text, der nicht mehr existiert", "Waise", 9)
    library.add_kommentar(temp_buch, k)
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = await _lade_kapitel_1(app, pilot, temp_buch)
        bloecke = _oberste_bloecke(app)
        texte = [_klartext(b) for b in bloecke]
        assert len(texte) == 5  # drei Absaetze, Ueberschrift, verwaister Kommentar
        assert texte[3] == "Kommentare ohne Absatz"
        assert texte[4].startswith("\U0001f4ac Waise")

        await pilot.click(bloecke[0])
        await pilot.click(bloecke[3])  # Ueberschrift: loest alles
        assert pane._aktiver_kommentar is None and pane._aktiver_absatz_index is None
        await pilot.click(bloecke[4])
        assert pane._aktiver_kommentar == k and pane._aktiver_absatz_index is None
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd tools && python -m pytest episto_tui/tests/test_annotate.py episto_tui/tests/test_reader_pane.py -v`
Expected: Vor Step 2 scheitert `test_annotate.py` schon beim Import (`ImportError: cannot import name 'maskiere_markdown'`); in `test_reader_pane.py` schlagen die 6 neuen Tests fehl (Kommentarblöcke fehlen bzw. `_aktiver_kommentar` existiert nicht). Falls Step 2 schon erledigt ist, müssen nur noch die 6 `test_reader_pane.py`-Tests fehlschlagen.

- [ ] **Step 5: Implement `reader_pane.py`**

Alle Änderungen in `tools/episto_tui/widgets/reader_pane.py`:

(a) Import: `from episto_tui.models import Buch, Kapitel, Highlight` → `from episto_tui.models import Buch, Kapitel, Highlight, Kommentar`.

(b) Den Kommentar `# Stattdessen zeilenbasiert: ...` (die Zeilen von `# Stattdessen zeilenbasiert:` bis `# kennt seine Quellzeilen ... ergibt sich daraus der Absatz.`) ersetzen durch:

```python
# Stattdessen zeilenbasiert: an Markdown.update() geht der Text von
# annotate.render_mit_kommentaren() (Absaetze und Kommentarbloecke, durch
# Leerzeilen getrennt); dessen Segmentliste kennt die Startzeile jedes
# Absatzes bzw. Kommentarblocks. Jeder MarkdownBlock kennt seine Quellzeilen
# (source_range, absolut, auch fuer verschachtelte Bloecke) - per Bisektion
# ergibt sich daraus das Segment.
```

(c) Die Funktionen `_absatz_startzeilen` und `_absatz_zu_zeile` (Zeilen 43-54) komplett ersetzen durch:

```python
def _segment_zu_zeile(startzeilen: list[int], zeile: int) -> int:
    # Leerzeilen zwischen zwei Segmenten fallen dem vorigen Segment zu.
    return max(0, bisect.bisect_right(startzeilen, zeile) - 1)
```

(d) In `__init__` den Block ab `# Absatz-Startzeilen des zuletzt an #anzeige uebergebenen Texts` (drei Zeilen inkl. `self._angezeigte_startzeilen: list[int] = []`) ersetzen durch:

```python
        # Zuletzt per Klick getroffener Kommentarblock (None bei einem Klick
        # auf einen Absatz): Ziel von "c" (aendern) und "d" (loeschen).
        self._aktiver_kommentar: Kommentar | None = None
        # Segmente des zuletzt an #anzeige uebergebenen Texts - die
        # Klick-Zuordnung muss sich auf genau den ANGEZEIGTEN Text beziehen.
        self._angezeigte_segmente: list[annotate.Segment] = []
        self._angezeigte_startzeilen: list[int] = []
```

(e) In `lade_kapitel` nach `self._aktiver_absatz_index = None` einfügen: `self._aktiver_kommentar = None`.

(f) In `_zeige_lesemodus` die Zeile
```python
        annotiert, _verwaist = annotate.render_with_markers(absaetze, kommentare)
```
ersetzen durch
```python
        annotiert, segmente = annotate.render_mit_kommentaren(absaetze, kommentare)
```
die Zeile
```python
        self._angezeigte_startzeilen = _absatz_startzeilen(absaetze)
```
ersetzen durch
```python
        self._angezeigte_segmente = segmente
        self._angezeigte_startzeilen = [s.startzeile for s in segmente]
```
und im `run_worker`-Aufruf `self._faerbe_absaetze(update_abschluss, absaetze, highlights)` durch `self._faerbe_absaetze(update_abschluss, absaetze, segmente, highlights)` ersetzen.

(g) `_faerbe_absaetze` und `_faerbe_knoten` (komplett, inkl. Docstring) ersetzen durch:

```python
    async def _faerbe_absaetze(
        self, update_abschluss, absaetze: list[str], segmente: list[annotate.Segment],
        highlights: list[Highlight],
    ) -> None:
        await update_abschluss
        farbe_je_absatz: dict[int, str] = {}
        # Exakte Treffer (gespeicherter == aufgeloester Index) zuletzt, damit
        # sie gewinnen, falls zwei Highlights auf denselben Absatz zeigen.
        for index, h in sorted(
            _aufgeloeste_highlights(absaetze, highlights),
            key=lambda paar: paar[0] == paar[1].absatz_index,
        ):
            if index is not None:
                farbe_je_absatz[index] = h.farbe
        self._faerbe_knoten(
            self.query_one("#anzeige", Markdown), segmente,
            [s.startzeile for s in segmente], farbe_je_absatz,
        )

    def _faerbe_knoten(
        self, container: Widget, segmente: list[annotate.Segment],
        startzeilen: list[int], farbe_je_absatz: dict[int, str],
    ) -> None:
        """Faerbt jeweils den groessten Knoten ein, der vollstaendig in EINEM
        Segment liegt: normalerweise die obersten Bloecke (direkte Kinder von
        #anzeige - verschachtelte Listenpunkte/Zitatinhalte bleiben
        transparent und wirken durch ihren gefaerbten Eltern-Block trotzdem
        einfarbig). Nur Absatz-Segmente werden gefaerbt; Kommentarbloecke und
        die Ueberschrift verwaister Kommentare bleiben transparent. Ein Block,
        der mehrere Segmente ueberspannt (z.B. eine Liste mit Leerzeilen
        zwischen den Punkten), wird selbst nicht gefaerbt, sondern in seine
        Kinder zerlegt; ein solcher Block ohne innere Bloecke (z.B. Codeblock
        mit Leerzeile) folgt seiner Startzeile - genau wie die Klick-Zuordnung
        in on_click()."""

        def farbe_von(segment_index: int) -> str:
            segment = segmente[segment_index]
            if segment.art != "absatz":
                return "transparent"
            return _HINTERGRUNDFARBE.get(farbe_je_absatz.get(segment.absatz_index), "transparent")

        for kind in container.children:
            bereich = _zeilenbereich(kind)
            if bereich is None:
                continue
            start, ende = bereich
            erster = _segment_zu_zeile(startzeilen, start)
            letzter = _segment_zu_zeile(startzeilen, max(start, ende - 1))
            ist_blatt = isinstance(kind, MarkdownBlock) and not kind.query(MarkdownBlock)
            if erster == letzter or ist_blatt:
                kind.styles.background = farbe_von(erster)
            else:
                kind.styles.background = "transparent"
                self._faerbe_knoten(kind, segmente, startzeilen, farbe_je_absatz)
```

(h) In `on_click` den Block
```python
            if bereich is not None:
                if self._angezeigte_startzeilen:
                    self._aktiver_absatz_index = _absatz_zu_zeile(self._angezeigte_startzeilen, bereich[0])
                return
```
ersetzen durch
```python
            if bereich is not None:
                if self._angezeigte_segmente:
                    segment = self._angezeigte_segmente[
                        _segment_zu_zeile(self._angezeigte_startzeilen, bereich[0])
                    ]
                    self._aktiver_absatz_index = segment.absatz_index
                    self._aktiver_kommentar = segment.kommentar
                return
```
und im Kommentar in `on_click` den Verweis `siehe _absatz_startzeilen()` durch `siehe _segment_zu_zeile()` ersetzen.

Danach `grep -rn "_absatz_startzeilen\|_absatz_zu_zeile\|render_with_markers" tools` ausführen: keine Treffer mehr erlaubt.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd tools && python -m pytest episto_tui/tests -v`
Expected: alle PASS. Erwartete Gesamtzahl: 125 (nach Task 1) − 4 (alte `render_with_markers`-Tests) + 8 (neue annotate-Tests) + 6 (neue reader_pane-Tests) = 135. Suite mindestens dreimal laufen lassen; die Klick-Tests dürfen nicht flackern (bei Bedarf in genau dem betroffenen Test ein weiteres `await pilot.pause()` ergänzen).

- [ ] **Step 7: Sichtprüfung gegen die echte Bibliothek**

Wegwerf-Skript im Scratchpad (nicht ins Repo): `EpistoApp(root=Path(r"D:\Workspace\!Episto"))` mit `run_test(size=(120, 40))`, ein echtes Kapitel öffnen, per `library.add_kommentar` einen Kommentar auf den ersten Absatz legen (danach mit `library.remove_kommentar` wieder entfernen und entstandene `kommentare.json`/`_backup`-Reste der echten Bibliothek löschen), `app.export_screenshot()` speichern und prüfen, dass der Kommentarblock lesbar unter dem Absatz steht. Skript und Screenshot danach löschen; die echte Bibliothek muss danach unverändert sein (`git status` im Hauptrepo ohne neue Dateien).

- [ ] **Step 8: Commit**

```bash
git add tools/episto_tui/annotate.py tools/episto_tui/widgets/reader_pane.py tools/episto_tui/tests/test_annotate.py tools/episto_tui/tests/test_reader_pane.py
git commit -m "feat: Kommentare als Zitat-Blöcke unter dem Absatz, Segment-Zuordnung statt Absatz-Marken"
```

---

### Task 3: Kommentar anlegen, ändern, löschen (`c` / `d`) im `ReaderPane`

**Files:**
- Modify: `tools/episto_tui/widgets/reader_pane.py`
- Test: `tools/episto_tui/tests/test_reader_pane.py` (anhängen)

**Interfaces:**
- Consumes: `library.add_kommentar`, `library.update_kommentar`, `library.remove_kommentar` (Task 1), `ReaderPane._aktiver_kommentar`, `_aktiver_absatz_index`, `_zeige_lesemodus()`, `fokus_lesebereich()` (Task 2 bzw. bestehend), `Kommentar`.
- Produces: `ReaderPane.action_kommentieren()`, `action_kommentar_loeschen()`, Widget `Input#kommentar-eingabe`.

- [ ] **Step 1: Write the failing tests**

An das Ende von `tools/episto_tui/tests/test_reader_pane.py` anhängen (Helfer `_klartext`, `_kommentar`, `_ANFANG_*`, `_lade_kapitel_1` stammen aus Task 2):

```python
# --- Kommentare anlegen / aendern / loeschen --------------------------------

@pytest.mark.asyncio
async def test_klick_c_text_enter_legt_kommentar_an_und_zeigt_ihn(temp_buch):
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[1])
        await pilot.press("c")
        await pilot.pause()
        eingabe = app.query_one("#kommentar-eingabe")
        assert eingabe.display is True
        assert app.focused is eingabe

        # c, d, q und Ziffern sind hier ganz normale Zeichen im Eingabefeld.
        await pilot.press("N", "o", "t", "i", "z", "space", "c", "d", "space", "q", "5")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        gelesen = library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")
        assert [(k.absatz_index, k.text) for k in gelesen] == [(1, "Notiz cd q5")]
        assert gelesen[0].absatz_anfang == _ANFANG_2
        assert eingabe.display is False
        assert app.focused is app.query_one("#anzeige-scroll", VerticalScroll)
        texte = [_klartext(b) for b in _oberste_bloecke(app)]
        assert texte[2].startswith("\U0001f4ac Notiz cd q5")


@pytest.mark.asyncio
async def test_escape_bricht_das_kommentieren_ab(temp_buch):
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[0])
        await pilot.press("c")
        await pilot.press("V", "e", "r", "w")
        await pilot.press("escape")
        await pilot.pause()
        assert library.read_kommentare(temp_buch, "0001_erstes-kapitel.md") == []
        assert app.query_one("#kommentar-eingabe").display is False
        assert app.query_one("#kommentar-eingabe").value == ""
        assert pane.bearbeiten is False
        assert app.focused is app.query_one("#anzeige-scroll", VerticalScroll)


@pytest.mark.asyncio
async def test_leerer_text_legt_keinen_kommentar_an(temp_buch):
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[0])
        await pilot.press("c")
        await pilot.press("space", "space", "enter")
        await pilot.pause()
        assert library.read_kommentare(temp_buch, "0001_erstes-kapitel.md") == []
        assert app.query_one("#kommentar-eingabe").display is False


@pytest.mark.asyncio
async def test_kommentar_mit_markup_zeichen_wird_woertlich_angezeigt(temp_buch):
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[0])
        await pilot.press("c")
        app.query_one("#kommentar-eingabe").value = "Vgl. [LdF] und [/] *stern*"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        erstellt = library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")[0].erstellt
        texte = [_klartext(b) for b in _oberste_bloecke(app)]
        assert texte[1] == "\U0001f4ac Vgl. [LdF] und [/] *stern* — " + erstellt


@pytest.mark.asyncio
async def test_klick_auf_kommentarblock_c_aendert_den_text(temp_buch):
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1, "Alt"))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[1])
        await pilot.press("c")
        await pilot.pause()
        eingabe = app.query_one("#kommentar-eingabe")
        assert eingabe.display is True
        assert eingabe.value == "Alt"
        eingabe.value = "Neu"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        gelesen = library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")
        assert [(k.text, k.erstellt) for k in gelesen] == [("Neu", "2026-09-28 10:00")]
        assert _klartext(_oberste_bloecke(app)[1]).startswith("\U0001f4ac Neu")


@pytest.mark.asyncio
async def test_klick_auf_kommentarblock_d_loescht_den_kommentar(temp_buch):
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1, "Weg damit"))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        assert len(_oberste_bloecke(app)) == 4
        await pilot.click(_oberste_bloecke(app)[1])
        await pilot.press("d")
        await pilot.pause()
        await pilot.pause()
        assert library.read_kommentare(temp_buch, "0001_erstes-kapitel.md") == []
        assert len(_oberste_bloecke(app)) == 3


@pytest.mark.asyncio
async def test_verwaister_kommentar_laesst_sich_loeschen(temp_buch):
    library.add_kommentar(temp_buch, _kommentar("Text, der nicht mehr existiert", "Waise", 9))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[4])
        await pilot.press("d")
        await pilot.pause()
        await pilot.pause()
        assert library.read_kommentare(temp_buch, "0001_erstes-kapitel.md") == []
        assert len(_oberste_bloecke(app)) == 3


@pytest.mark.asyncio
async def test_c_und_d_ohne_klick_tun_nichts(temp_buch):
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1, "Bleibt"))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.press("c")
        await pilot.press("d")
        await pilot.pause()
        assert app.query_one("#kommentar-eingabe").display is False
        assert len(library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")) == 1


@pytest.mark.asyncio
async def test_d_auf_einem_absatz_loescht_nichts(temp_buch):
    library.add_kommentar(temp_buch, _kommentar(_ANFANG_1, "Bleibt"))
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[0])
        await pilot.press("d")
        await pilot.pause()
        assert len(library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")) == 1


@pytest.mark.asyncio
async def test_c_im_editiermodus_oeffnet_kein_kommentarfeld(temp_buch):
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[0])
        await pilot.press("e")
        await pilot.pause()
        assert pane.bearbeiten is True
        await pilot.press("c", "d")
        await pilot.pause()
        assert app.query_one("#kommentar-eingabe").display is False
        assert library.read_kommentare(temp_buch, "0001_erstes-kapitel.md") == []


@pytest.mark.asyncio
async def test_kapitelwechsel_schliesst_offenes_kommentarfeld(temp_buch):
    from episto_tui.models import Kapitel
    app = _LeseTestApp()
    async with app.run_test(size=(80, 40)) as pilot:
        pane = await _lade_kapitel_1(app, pilot, temp_buch)
        await pilot.click(_oberste_bloecke(app)[0])
        await pilot.press("c")
        await pilot.pause()
        pane.lade_kapitel(temp_buch, Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md"))
        await pilot.pause()
        assert app.query_one("#kommentar-eingabe").display is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools && python -m pytest episto_tui/tests/test_reader_pane.py -v`
Expected: die 11 neuen Tests FAIL (`NoMatches` für `#kommentar-eingabe`), alle älteren PASS.

- [ ] **Step 3: Implement**

Änderungen in `tools/episto_tui/widgets/reader_pane.py`:

(a) Importe: nach `import dataclasses` einfügen `from datetime import datetime`; `from textual.widgets import Markdown, TextArea` → `from textual.widgets import Input, Markdown, TextArea`.

(b) `BINDINGS` um zwei Einträge erweitern (nach dem `b`-Binding):

```python
        Binding("c", "kommentieren", "Kommentar"),
        Binding("d", "kommentar_loeschen", "Kommentar löschen"),
```

Im Klassenkommentar über `BINDINGS` die Aufzählung `(e / ctrl+s / escape / g / r / b)` um `/ c / d` ergänzen.

(c) In `__init__` nach `self._aktiver_kommentar: ...` einfügen:

```python
        # Was das offene Kommentarfeld bei Enter tut: ("neu", absatz_index)
        # oder ("aendern", Kommentar); None = Feld geschlossen.
        self._kommentar_ziel: tuple[str, int | Kommentar] | None = None
```

(d) `compose`: nach `yield TextArea(id="editor")` einfügen:

```python
        yield Input(placeholder="Kommentar eintippen, Enter speichert, Esc bricht ab", id="kommentar-eingabe")
```

(e) `on_mount`: nach der `editor`-Zeile einfügen:

```python
        self.query_one("#kommentar-eingabe", Input).display = False
```

(f) In `lade_kapitel` nach `self._aktiver_kommentar = None` einfügen (ohne Fokus, siehe Global Constraints — `lade_kapitel` läuft auch für ein verstecktes Pane):

```python
        self._schliesse_kommentar_eingabe(fokus=False)
```

(g) Neue Methoden direkt vor `def action_toggle_edit`:

```python
    def _schliesse_kommentar_eingabe(self, fokus: bool = True) -> None:
        self._kommentar_ziel = None
        eingabe = self.query_one("#kommentar-eingabe", Input)
        eingabe.value = ""
        eingabe.display = False
        if fokus:
            self.fokus_lesebereich()

    def action_kommentieren(self) -> None:
        if self.bearbeiten or self.buch is None:
            return
        if self._aktiver_kommentar is not None:
            ziel: tuple[str, int | Kommentar] = ("aendern", self._aktiver_kommentar)
            vorbelegung = self._aktiver_kommentar.text
        elif self._aktiver_absatz_index is not None:
            ziel = ("neu", self._aktiver_absatz_index)
            vorbelegung = ""
        else:
            return
        self._kommentar_ziel = ziel
        eingabe = self.query_one("#kommentar-eingabe", Input)
        eingabe.value = vorbelegung
        eingabe.display = True
        eingabe.focus()

    def action_kommentar_loeschen(self) -> None:
        if self.bearbeiten or self.buch is None or self._aktiver_kommentar is None:
            return
        library.remove_kommentar(self.buch, self._aktiver_kommentar)
        self._aktiver_kommentar = None
        self._zeige_lesemodus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "kommentar-eingabe":
            return
        event.stop()
        ziel = self._kommentar_ziel
        text = event.value.strip()
        self._schliesse_kommentar_eingabe()
        if ziel is None or not text or self.buch is None:
            return
        art, wert = ziel
        if art == "neu":
            absaetze = annotate.split_paragraphs(
                library.read_chapter_text(self.buch, self.kapitel.datei)
            )
            if not (0 <= wert < len(absaetze)):
                return
            library.add_kommentar(self.buch, Kommentar(
                datei=self.kapitel.datei, absatz_index=wert,
                absatz_anfang=absaetze[wert][:80], text=text,
                erstellt=datetime.now().strftime("%Y-%m-%d %H:%M"),
            ))
        else:
            library.update_kommentar(self.buch, wert, text)
            self._aktiver_kommentar = None
        self._zeige_lesemodus()
```

(h) `action_verwerfen` — am Anfang der Methode einfügen (Esc im Kommentarfeld erreicht diese Methode, weil `Input` Esc nicht selbst verarbeitet und die Bindings-Kette bis `ReaderPane` läuft):

```python
        if self._kommentar_ziel is not None:
            self._schliesse_kommentar_eingabe()
            return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools && python -m pytest episto_tui/tests -v`
Expected: alle PASS; Gesamtzahl 135 + 11 = 146. Suite dreimal laufen lassen (keine Flakiness).

Falls `test_klick_c_text_enter_...` an `assert app.focused is eingabe` scheitert, weil der Fokus erst nach einem weiteren Zyklus umspringt: in diesem Test ein zusätzliches `await pilot.pause()` nach `pilot.press("c")` ergänzen (reines Timing, kein Implementierungsfehler).

- [ ] **Step 5: Commit**

```bash
git add tools/episto_tui/widgets/reader_pane.py tools/episto_tui/tests/test_reader_pane.py
git commit -m "feat: Kommentare im Lesemodus anlegen, ändern und löschen (c/d)"
```

---

### Task 4: Kommentare-Tab entfernen

**Files:**
- Modify: `tools/episto_tui/app.py`
- Delete: `tools/episto_tui/widgets/kommentare_pane.py`, `tools/episto_tui/tests/test_kommentare_pane.py`
- Modify: `tools/episto_tui/tests/test_app.py`

**Interfaces:**
- Consumes: Task 3 (Kommentare sind ohne den Tab vollständig bedienbar).
- Produces: keine.

- [ ] **Step 1: Write the failing test**

In `tools/episto_tui/tests/test_app.py` nach `test_footer_zeigt_tastenkuerzel` einfügen:

```python
@pytest.mark.asyncio
async def test_kein_kommentare_tab_mehr_und_taste_5_tut_nichts(tmp_path, temp_buch):
    from textual.widgets import TabbedContent, TabPane
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        assert [pane.id for pane in app.query(TabPane)] == [
            "tab-text", "tab-tags", "tab-straenge", "tab-querbezuege",
        ]
        await _oeffne_erstes_kapitel_per_tastatur(pilot)
        await pilot.press("5")
        await pilot.pause()
        assert app.is_running
        assert app.query_one(TabbedContent).active == "tab-text"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools && python -m pytest episto_tui/tests/test_app.py::test_kein_kommentare_tab_mehr_und_taste_5_tut_nichts -v`
Expected: FAIL (Liste enthält noch `"tab-kommentare"`).

- [ ] **Step 3: Implement**

`tools/episto_tui/app.py`:
- Zeile 5: `from textual.widgets import Footer, ListView, TabbedContent, TabPane` → `from textual.widgets import Footer, TabbedContent, TabPane`.
- Zeile 13 (`from episto_tui.widgets.kommentare_pane import KommentarePane`) löschen.
- In `BINDINGS` die Zeile `Binding("5", "tab_kommentare", "Kommentare"),` löschen.
- In `compose` die zwei Zeilen `with TabPane("Kommentare", id="tab-kommentare"):` / `yield KommentarePane()` löschen.
- In `on_chapter_selected`: `for pane_typ in (ReaderPane, TagsPane, StraengePane, QuerbezuegePane, KommentarePane):` → `for pane_typ in (ReaderPane, TagsPane, StraengePane, QuerbezuegePane):`.
- In `_fokussiere_aktiven_tab` den kompletten Zweig
```python
        if aktiv == "tab-kommentare":
            # KommentarePane ist ...
            ziel = self.query_one(KommentarePane).query_one("#absatzliste", ListView)
        else:
            ziel = self.query_one(_FOKUS_JE_TAB.get(aktiv, ReaderPane))
        ziel.focus()
```
ersetzen durch
```python
        self.query_one(_FOKUS_JE_TAB.get(aktiv, ReaderPane)).focus()
```
- Die Methode `action_tab_kommentare` löschen.

`tools/episto_tui/tests/test_app.py`, Test `test_fehler_in_einem_pane_legt_app_nicht_lahm`:
- Die Zeile `from textual.widgets import Markdown, ListView, Static` → `from textual.widgets import Static`.
- Die Zeile `from episto_tui.widgets.kommentare_pane import KommentarePane` löschen.
- Die Zeile `assert len(app.query_one(KommentarePane).query_one("#absatzliste", ListView).children) == 3` löschen; der Kommentar davor (`# Panes NACH dem kaputten TagsPane wurden trotzdem geladen:`) bleibt und gilt weiter für `StraengePane`.

Dateien löschen:

```bash
git rm tools/episto_tui/widgets/kommentare_pane.py tools/episto_tui/tests/test_kommentare_pane.py
```

Danach `grep -rn "kommentare_pane\|KommentarePane\|tab-kommentare\|tab_kommentare" tools` ausführen: keine Treffer mehr erlaubt.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools && python -m pytest episto_tui/tests -v`
Expected: alle PASS. Erwartete Gesamtzahl: 146 − 3 (gelöschte `test_kommentare_pane.py`-Tests) + 1 (neuer Test) = 144. Dreimal laufen lassen.

- [ ] **Step 5: Ende-zu-Ende-Sichtprüfung gegen die echte Bibliothek**

Wegwerf-Skript im Scratchpad (nicht ins Repo): `EpistoApp(root=Path(r"D:\Workspace\!Episto"))`, ein echtes Kapitel per `select_node` öffnen, Absatz anklicken, `c` drücken, Text setzen, Enter; prüfen, dass der Kommentarblock erscheint, dann Kommentarblock anklicken, `d` drücken und prüfen, dass er wieder weg ist. Danach die dabei entstandene `kommentare.json` und `_backup`-Dateien der echten Bibliothek entfernen, sodass `git status` im Hauptrepo nichts Neues zeigt; Skript löschen.

- [ ] **Step 6: Commit**

```bash
git add tools/episto_tui/app.py tools/episto_tui/tests/test_app.py
git commit -m "feat: Kommentare-Tab entfernt (Kommentare jetzt direkt im Textfenster)"
```

---

## Nicht Teil dieses Plans

- Kommentare im Editiermodus (TextArea) anlegen — bewusst nur Lesemodus.
- Sichtbare Markierung, welcher Absatz gerade angeklickt ist (gilt auch fürs Highlighting, eigenes Thema).
- Stabile Kommentar-IDs statt Identifikation über alle Felder.

