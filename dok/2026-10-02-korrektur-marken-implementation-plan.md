# Korrektur-Marken + Korrektur-Lauf — Implementierungsplan

> **Für agentische Umsetzung:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (empfohlen) oder superpowers:executing-plans. Schritte nutzen `- [ ]`-Checkboxen.

**Goal:** Eine vierte Markierungsfarbe „korrektur" (Taste `k`) in der TUI plus ein interaktiver Korrektur-Lauf, der „korrektur"-markierte Absätze per LLM auf Basis des englischen Originaltexts repariert.

**Architecture:** TUI-Änderungen (vier Dateien) ergänzen die Farbe „korrektur" exklusiv zu gelb/rosa/blau. Der Lauf ist ein Python-Modul `episto_tui/korrektur.py` (Aufruf `python -m episto_tui.korrektur -Buch <pfad>`), das `annotate.split_paragraphs`/`locate_paragraph` und `library` (Highlights + Backup) wiederverwendet. Grounding = kompletter englischer Kapiteltext (`en\chunk_*.md`), interaktiv `[j/n/e]`.

**Tech Stack:** Python 3.12, Textual 8.x, pytest, `requests` (Ollama `http://localhost:11434/api/chat`), Modell `aya-expanse:32b`.

## Global Constraints

- Farbe „korrektur" = `#5c1a1a`; Taste `k`; Knopf-Label `K`.
- Exklusiv zu gelb/rosa/blau (Variante A — ein Absatz hat genau eine Farbe).
- Grounding = kompletter englischer Kapiteltext (Approach A); Grenz-Chunks inklusive.
- Interaktiv `[j/n/e]`; `j` schreibt zurück (mit Backup via `library.write_chapter_text`) und entfernt die Marke.
- Buchweise mit `-Buch`; Fehlerfälle laut Spec (verwaist → überspringen; fehlendes `lektor_pfad` → Abbruch; LLM ungültig → 1 Retry, dann überspringen).

---

## Datei-Struktur

- Modify: `tools/episto_tui/widgets/reader_pane.py` (Farbe + Binding + Action)
- Modify: `tools/episto_tui/widgets/aktionsleiste.py` (Knopf)
- Modify: `tools/episto_tui/app.py` (`_KNOPF_AKTION`)
- Modify: `tools/episto_tui/library.py` (`read_highlights_nach_farbe`)
- Create: `tools/episto_tui/korrektur.py` (Lauf)
- Modify: `tools/episto_tui/tests/test_layout_schmal.py`, `test_library_highlights.py`
- Create: `tools/episto_tui/tests/test_korrektur.py`

---

### Task 1: TUI — Taste `k` und Farbe „korrektur" im ReaderPane

**Files:**
- Modify: `tools/episto_tui/widgets/reader_pane.py:25,91-100,314-321`
- Test: `tools/episto_tui/tests/test_layout_schmal.py`

**Interfaces:**
- Produces: `ReaderPane.action_highlight_korrektur()` (analog zu `action_highlight_gelb`), Binding `k`.

- [ ] **Step 1: Test schreiben (schlägt fehl)**

In `test_layout_schmal.py`, nach `test_farbknopf_faerbt_den_zuletzt_angetippten_absatz`:

```python
@pytest.mark.asyncio
async def test_k_taste_markiert_absatz_als_korrektur(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)
        bloecke = list(app.query_one("#anzeige", Markdown).query_children(MarkdownBlock))
        await pilot.click(bloecke[1])
        await pilot.pause()
        await pilot.press("k")
        await pilot.pause()
        highlights = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
        assert [(h.absatz_index, h.farbe) for h in highlights] == [(1, "korrektur")]
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd tools && python -m pytest episto_tui/tests/test_layout_schmal.py::test_k_taste_markiert_absatz_als_korrektur -v`
Expected: FAIL (Binding `k` existiert nicht, keine `action_highlight_korrektur`).

- [ ] **Step 3: Implementierung**

In `reader_pane.py`:

```python
_HINTERGRUNDFARBE = {"gelb": "#595900", "rosa": "#594347", "blau": "blue", "korrektur": "#5c1a1a"}
```

In `BINDINGS`, nach der `b`-Zeile:

```python
        Binding("k", "highlight_korrektur", "Korrektur"),
```

Nach `action_highlight_blau`:

```python
    def action_highlight_korrektur(self) -> None:
        self._schalte_highlight("korrektur")
```

- [ ] **Step 4: Test laufen lassen, grün bestätigen**

Run: `cd tools && python -m pytest episto_tui/tests/test_layout_schmal.py::test_k_taste_markiert_absatz_als_korrektur -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/episto_tui/widgets/reader_pane.py tools/episto_tui/tests/test_layout_schmal.py
git commit -m "feat: Taste k markiert Absatz als korrektur"
```

---

### Task 2: TUI — Knopf „Korr" in der Aktionsleiste

**Files:**
- Modify: `tools/episto_tui/widgets/aktionsleiste.py:9-26`
- Modify: `tools/episto_tui/app.py:30-40`
- Test: `tools/episto_tui/tests/test_layout_schmal.py`

**Interfaces:**
- Consumes: `action_highlight_korrektur` (Task 1).
- Produces: Knopf `#knopf-korrektur` (Label „Korr"), sichtbar im Kontext `lesen`, dispatcht `AktionGewaehlt("korrektur")` → `_KNOPF_AKTION["korrektur"]`.

- [ ] **Step 1: Test schreiben (schlägt fehl)**

In `test_layout_schmal.py`:

```python
@pytest.mark.asyncio
async def test_korrektur_knopf_faerbt_den_zuletzt_angetippten_absatz(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        await _waehle_erstes_kapitel(app, pilot)
        bloecke = list(app.query_one("#anzeige", Markdown).query_children(MarkdownBlock))
        await pilot.click(bloecke[1])
        await pilot.pause()
        await pilot.click("#knopf-korrektur")
        await pilot.pause()
        highlights = library.read_highlights(temp_buch, "0001_erstes-kapitel.md")
        assert [(h.absatz_index, h.farbe) for h in highlights] == [(1, "korrektur")]
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd tools && python -m pytest episto_tui/tests/test_layout_schmal.py::test_korrektur_knopf_faerbt_den_zuletzt_angetippten_absatz -v`
Expected: FAIL (`#knopf-korrektur` existiert nicht).

- [ ] **Step 3: Implementierung**

In `aktionsleiste.py`, `_KNOEPFE` (nach `("blau", "Blau")`):

```python
    ("korrektur", "K"),
```

In `aktionsleiste.py`, `KONTEXTE["lesen"]` (nach `"blau"`):

```python
    "lesen": frozenset({"baum", "bearbeiten", "gelb", "rosa", "blau", "korrektur", "kommentar", "loeschen"}),
```

In `app.py`, `_KNOPF_AKTION` (nach `"blau"`):

```python
    "korrektur": "highlight_korrektur",
```

- [ ] **Step 4: Test laufen lassen, grün bestätigen**

Run: `cd tools && python -m pytest episto_tui/tests/test_layout_schmal.py::test_korrektur_knopf_faerbt_den_zuletzt_angetippten_absatz -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/episto_tui/widgets/aktionsleiste.py tools/episto_tui/app.py tools/episto_tui/tests/test_layout_schmal.py
git commit -m "feat: Korr-Knopf in der Aktionsleiste"
```

---

### Task 3: library.py — `read_highlights_nach_farbe`

**Files:**
- Modify: `tools/episto_tui/library.py` (nach `read_highlights`)
- Test: `tools/episto_tui/tests/test_library_highlights.py`

**Interfaces:**
- Produces: `library.read_highlights_nach_farbe(buch: Buch, farbe: str) -> list[Highlight]` (alle Highlights einer Farbe, unabhängig von `datei`).

- [ ] **Step 1: Test schreiben (schlägt fehl)**

In `test_library_highlights.py`:

```python
def test_read_highlights_nach_farbe_filtert_ueber_alle_dateien(temp_buch):
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=0, absatz_anfang="X", farbe="korrektur"))
    library.write_highlight(temp_buch, Highlight(
        datei="0002_zweites-kapitel.md", absatz_index=0, absatz_anfang="Y", farbe="korrektur"))
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=1, absatz_anfang="Z", farbe="gelb"))

    nur_korrektur = library.read_highlights_nach_farbe(temp_buch, "korrektur")
    assert {h.datei for h in nur_korrektur} == {"0001_erstes-kapitel.md", "0002_zweites-kapitel.md"}
    assert all(h.farbe == "korrektur" for h in nur_korrektur)
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd tools && python -m pytest episto_tui/tests/test_library_highlights.py::test_read_highlights_nach_farbe_filtert_ueber_alle_dateien -v`
Expected: FAIL (Attribut existiert nicht).

- [ ] **Step 3: Implementierung**

In `library.py`, direkt nach `read_highlights`:

```python
def read_highlights_nach_farbe(buch: Buch, farbe: str) -> list[Highlight]:
    daten = _lade_json_dict(_highlights_pfad(buch))
    if daten is None:
        return []
    return [
        Highlight.from_dict(eintrag)
        for eintrag in _dict_eintraege(daten, "highlights")
        if eintrag.get("farbe") == farbe
    ]
```

- [ ] **Step 4: Test laufen lassen, grün bestätigen**

Run: `cd tools && python -m pytest episto_tui/tests/test_library_highlights.py -v`
Expected: PASS (alle bestehenden + neuer Test).

- [ ] **Step 5: Commit**

```bash
git add tools/episto_tui/library.py tools/episto_tui/tests/test_library_highlights.py
git commit -m "feat: read_highlights_nach_farbe fuer den Korrektur-Lauf"
```

---

### Task 4: korrektur.py — Kernlogik (sammeln, grounden, ersetzen)

**Files:**
- Create: `tools/episto_tui/korrektur.py`
- Test: `tools/episto_tui/tests/test_korrektur.py`

**Interfaces:**
- Consumes: `read_highlights_nach_farbe` (Task 3), `annotate.split_paragraphs`, `library.read_chapter_text`, `Buch`/`Highlight` aus `models`.
- Produces:
  - `sammle_marken(buch) -> list[Highlight]`
  - `englischer_kapiteltext(buch, nr, segmente=None) -> str`
  - `ersetze_absatz(text, index, neuer_absatz) -> str`
  - `_lade_segmente(buch) -> list[dict]`

- [ ] **Step 1: Test schreiben (schlägt fehl)**

`test_korrektur.py`:

```python
import json
from pathlib import Path
import episto_tui.korrektur as korrektur
from episto_tui import library
from episto_tui.models import Highlight


def _buch_mit_grounding(temp_buch):
    """Legt meta.json + en\chunk_*.md an, damit englischer_kapiteltext greift."""
    # meta.json mit lektor_pfad (zeigt auf einen Lektor-Ordner mit kapitel.json)
    lektor = temp_buch.pfad / "_lektor"
    (lektor).mkdir()
    (lektor / "kapitel.json").write_text(json.dumps({"segmente": [
        {"id": "s1", "titel": "Einleitung", "chunk": 0, "position": 0, "vorspann": False},
        {"id": "s2", "titel": "Kap1", "chunk": 2, "position": 0, "vorspann": False},
    ]}, ensure_ascii=False), encoding="utf-8")
    (temp_buch.pfad / "meta.json").write_text(json.dumps({
        "lektor_pfad": str(lektor), "chunks": 4,
    }), encoding="utf-8")
    en = temp_buch.pfad / "en"
    en.mkdir()
    for i in range(4):
        (en / f"chunk_{i:03d}.md").write_text(f"EN{i}\n\n", encoding="utf-8")
    return temp_buch


def test_ersetze_absatz_ersetzt_nur_den_zielabsatz():
    text = "Absatz eins.\n\nAbsatz zwei.\n\nAbsatz drei."
    neu = korrektur.ersetze_absatz(text, 1, "Korrigiert.")
    assert neu == "Absatz eins.\n\nKorrigiert.\n\nAbsatz drei.\n"


def test_englischer_kapiteltext_liefert_chunks_des_kapitels(temp_buch):
    buch = _buch_mit_grounding(temp_buch)
    # Kapitel 1 (nr=1) = segmente[0] (chunk 0) bis segmente[1] (chunk 2) inklusive
    text = korrektur.englischer_kapiteltext(buch, 1)
    assert "EN0" in text and "EN2" in text and "EN3" not in text


def test_sammle_marken_findet_nur_korrektur(temp_buch):
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=0, absatz_anfang="A", farbe="korrektur"))
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=1, absatz_anfang="B", farbe="gelb"))
    marken = korrektur.sammle_marken(temp_buch)
    assert [h.farbe for h in marken] == ["korrektur"]
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd tools && python -m pytest episto_tui/tests/test_korrektur.py -v`
Expected: FAIL (Modul `episto_tui.korrektur` fehlt).

- [ ] **Step 3: Implementierung**

`tools/episto_tui/korrektur.py`:

```python
from __future__ import annotations
import json
from pathlib import Path
from episto_tui import library
from episto_tui.annotate import split_paragraphs, locate_paragraph
from episto_tui.models import Buch, Highlight


def sammle_marken(buch: Buch) -> list[Highlight]:
    return library.read_highlights_nach_farbe(buch, "korrektur")


def _lade_segmente(buch: Buch) -> list[dict]:
    meta = json.loads((buch.pfad / "meta.json").read_text(encoding="utf-8"))
    lektor_pfad = Path(meta["lektor_pfad"])
    kap = json.loads((lektor_pfad / "kapitel.json").read_text(encoding="utf-8"))
    return sorted(kap["segmente"], key=lambda s: (int(s["chunk"]), int(s["position"])))


def englischer_kapiteltext(buch: Buch, nr: int, segmente: list[dict] | None = None) -> str:
    if segmente is None:
        segmente = _lade_segmente(buch)
    meta = json.loads((buch.pfad / "meta.json").read_text(encoding="utf-8"))
    start = int(segmente[nr - 1]["chunk"])
    ende = int(segmente[nr]["chunk"]) if nr < len(segmente) else int(meta["chunks"]) - 1
    return "\n\n".join(
        (buch.pfad / "en" / f"chunk_{i:03d}.md").read_text(encoding="utf-8")
        for i in range(start, ende + 1)
    )


def ersetze_absatz(text: str, index: int, neuer_absatz: str) -> str:
    absaetze = split_paragraphs(text)
    if not (0 <= index < len(absaetze)):
        raise ValueError(f"Absatz {index} ausserhalb 0..{len(absaetze) - 1}")
    absaetze[index] = neuer_absatz.strip()
    return "\n\n".join(absaetze) + "\n"
```

- [ ] **Step 4: Test laufen lassen, grün bestätigen**

Run: `cd tools && python -m pytest episto_tui/tests/test_korrektur.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/episto_tui/korrektur.py tools/episto_tui/tests/test_korrektur.py
git commit -m "feat: Korrektur-Lauf-Kernlogik (sammeln, grounden, ersetzen)"
```

---

### Task 5: korrektur.py — LLM-Korrektur + interaktive `main()`

**Files:**
- Modify: `tools/episto_tui/korrektur.py` (ergänzen)
- Test: `tools/episto_tui/tests/test_korrektur.py`

**Interfaces:**
- Consumes: Kernlogik (Task 4), `library.write_chapter_text`, `library.remove_highlight`.
- Produces:
  - `korrigiere(absatz, englisch, model="aya-expanse:32b", ollama_url="http://localhost:11434/api/chat") -> str`
  - `main(argv=None) -> None` (argparse `-Buch`, `-Model`, `-Limit`; interaktive `[j/n/e]`-Schleife)

- [ ] **Step 1: Test schreiben (schlägt fehl)**

In `test_korrektur.py`:

```python
import requests

def test_korrigiere_schickt_absatz_und_original_ans_llm(monkeypatch):
    gesendet = {}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"message": {"content": "korrigierter absatz"}}

    def fake_post(url, json, timeout):
        gesendet["url"] = url
        gesendet["body"] = json
        return FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)
    out = korrektur.korrigiere("kaputt [^12]", "The original chapter", model="m", ollama_url="http://x")
    assert out == "korrigierter absatz"
    assert gesendet["body"]["model"] == "m"
    assert "kaputt [^12]" in gesendet["body"]["messages"][1]["content"]
    assert "The original chapter" in gesendet["body"]["messages"][1]["content"]
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd tools && python -m pytest episto_tui/tests/test_korrektur.py::test_korrigiere_schickt_absatz_und_original_ans_llm -v`
Expected: FAIL (`korrigiere` fehlt).

- [ ] **Step 3: Implementierung**

In `korrektur.py` ergänzen (oben `import requests`):

```python
import argparse
import requests

_SYSTEM = (
    "Du bist ein Lektor für ein übersetztes Buch. Der folgende deutsche Absatz ist "
    "fehlerhaft (z. B. Abbruch mitten im Satz oder fehlerhafte Fußnotenzuordnung). "
    "Nutze den englischen Originaltext des Kapitels, um den deutschen Absatz korrekt "
    "zu reparieren. Antworte ausschließlich mit dem korrigierten deutschen Absatz "
    "(Markdown bleibt erhalten)."
)


def korrigiere(absatz: str, englisch: str, model: str = "aya-expanse:32b",
               ollama_url: str = "http://localhost:11434/api/chat") -> str:
    body = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0.2},
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Deutscher Absatz (fehlerhaft):\n{absatz}\n\nEnglisches Original (Kapitel):\n{englisch}"},
        ],
    }
    resp = requests.post(ollama_url, json=body, timeout=600)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="episto_tui.korrektur")
    parser.add_argument("-Buch", required=True)
    parser.add_argument("-Model", default="aya-expanse:32b")
    parser.add_argument("-Limit", type=int, default=0)
    args = parser.parse_args(argv)

    buch = Buch(autor="", titel="", pfad=Path(args.Buch))
    marken = sammle_marken(buch)
    if not marken:
        print("Keine korrektur-Marken.")
        return
    if args.Limit > 0:
        marken = marken[:args.Limit]

    try:
        segmente = _lade_segmente(buch)
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"Abbruch: Grounding nicht verfuegbar ({exc}).")
        return

    gesamt = len(marken)
    for i, h in enumerate(marken, 1):
        text = library.read_chapter_text(buch, h.datei)
        absaetze = split_paragraphs(text)
        index = locate_paragraph(absaetze, h.absatz_index, h.absatz_anfang)
        if index is None:
            print(f"[{i}/{gesamt}] {h.datei}: Absatz nicht gefunden, ueberspringe.")
            continue
        kaputt = absaetze[index]
        nr = int(h.datei.split("_")[0])
        englisch = englischer_kapiteltext(buch, nr, segmente)
        try:
            korrigiert = korrigiere(kaputt, englisch, args.Model)
        except Exception as exc:  # 1 Retry, dann ueberspringen
            try:
                korrigiert = korrigiere(kaputt, englisch, args.Model)
            except Exception as exc2:
                print(f"[{i}/{gesamt}] {h.datei}: LLM fehlgeschlagen ({exc2}), ueberspringe.")
                continue
        print(f"[{i}/{gesamt}] {h.datei}, Absatz {index}")
        print(f"  fehlerhaft: {kaputt[:120]}")
        print(f"  korrigiert: {korrigiert[:120]}")
        antwort = input("  Uebernehmen? [j/n/e] ").strip().lower()
        if antwort == "e":
            print("Lauf beendet.")
            return
        if antwort == "j":
            library.write_chapter_text(buch, h.datei, ersetze_absatz(text, index, korrigiert))
            library.remove_highlight(buch, h.datei, h.absatz_index)
            print("  uebernommen.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Test laufen lassen, grün bestätigen**

Run: `cd tools && python -m pytest episto_tui/tests/test_korrektur.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/episto_tui/korrektur.py tools/episto_tui/tests/test_korrektur.py
git commit -m "feat: Korrektur-Lauf mit LLM und interaktiver Anwendung"
```

---

## Selbst-Review

- **Spec-Abdeckung:** Teil 1 (Farbe/Taste/Knopf) → Tasks 1–2; `read_highlights_nach_farbe` → Task 3; Grounding (Approach A, Grenz-Chunks inklusive) → Task 4 `englischer_kapiteltext`; LLM + `[j/n/e]` + Zurückschreiben/Backup/Marke entfernen → Task 5. Fehlerfälle (verwaist → überspringen, Grounding fehlt → Abbruch, LLM ungültig → Retry/überspringen) → Task 5 `main()`.
- **Konsistenz:** `sammle_marken`/`englischer_kapiteltext`/`ersetze_absatz`/`korrigiere` werden in Task 4/5 definiert und in `main()` (Task 5) genutzt; Signaturen deckungsgleich. Farbe `#5c1a1a`, Label `Korr`, Taste `k` überall gleich.
- **Abweichung vom Spec:** Lauf als `episto_tui/korrektur.py` (`python -m episto_tui.korrektur`) statt `korrektur.ps1` — Wiederverwendung von `annotate`/`library`.



Zum Ausprobieren: ein Buch in der TUI öffnen → Absatz anklicken → k (oder Knopf „K") markiert ihn als korrekturbedürftig → danach cd tools && python -m episto_tui.korrektur -Buch "D:\Workspace\!Episto\Autor\<Autor>\<Buch>" (lädt je Marke den englischen Originaltext als Anker und fragt interaktiv [j/n/e]).