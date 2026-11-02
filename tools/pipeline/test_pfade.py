"""Die Pipeline-Skripte (tools\\pipeline) muessen ihr BASE aus dem Ablageort ableiten:
<Wurzel>\\rohdaten fuer Inbox/Lektor/Outbox, <Wurzel>\\hilfsdaten fuer themen.json. Gepruft wird der
Quelltext (ohne die Skripte auszufuehren, sie starten sonst Modelle oder aendern Dateien)."""
import ast
import os
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parents[1]
sys.path.insert(0, str(HIER))

import ebook_pfade  # noqa: E402

SKRIPTE = sorted(p for p in HIER.glob("*.py") if not p.name.startswith("test_"))


def _base_zuweisungen(datei: Path):
    baum = ast.parse(datei.read_text(encoding="utf-8"))
    for knoten in baum.body:
        if isinstance(knoten, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "BASE" for t in knoten.targets):
            yield knoten


def test_alle_skripte_kompilieren():
    for datei in SKRIPTE:
        compile(datei.read_text(encoding="utf-8"), str(datei), "exec")


def test_base_zeigt_auf_rohdaten_und_keine_festen_altpfade(monkeypatch):
    monkeypatch.delenv("EBOOK_BASE", raising=False)
    gefunden = {}
    for datei in SKRIPTE:
        for knoten in _base_zuweisungen(datei):
            wert = eval(compile(ast.Expression(knoten.value), str(datei), "eval"),
                        {"os": os, "Path": Path, "__file__": str(datei)})
            gefunden[datei.name] = Path(str(wert)).resolve()
    assert len(gefunden) >= 14                       # ebook-translate, detect-chapters, themen ... alle mit BASE
    assert set(gefunden.values()) == {(WURZEL / "rohdaten").resolve()}
    for datei in SKRIPTE:                              # nur ebook_pfade.py darf den alten Ort erwaehnen (Erklaerung)
        if datei.name != "ebook_pfade.py":
            assert "Dude\\Tools" not in datei.read_text(encoding="utf-8"), datei.name


def test_themen_json_liegt_in_hilfsdaten(monkeypatch):
    monkeypatch.delenv("EBOOK_HILFSDATEN", raising=False)
    quelle = (HIER / "themen.py").read_text(encoding="utf-8")
    assert 'parents[2] / "hilfsdaten"' in quelle and 'HILFSDATEN / "themen.json"' in quelle


def test_alte_quellpfade_werden_unter_rohdaten_aufgesetzt(tmp_path):
    base = tmp_path / "rohdaten"
    (base / "Inbox").mkdir(parents=True)
    (base / "Lektor" / "A" / "T" / "en").mkdir(parents=True)
    (base / "Inbox" / "x.epub").write_bytes(b"PK")
    (base / "Lektor" / "A" / "T" / "en" / "y.pdf").write_bytes(b"%PDF")
    for alt, soll in [
        (r"C:\Users\Dude\Tools\eBooks\Inbox\x.epub", base / "Inbox" / "x.epub"),
        ("/mnt/c/Users/Dude/Tools/eBooks/Inbox/x.epub", base / "Inbox" / "x.epub"),
        (r"D:\Workspace\!Episto\eBooks\Lektor\A\T\en\y.pdf", base / "Lektor" / "A" / "T" / "en" / "y.pdf"),
    ]:
        assert ebook_pfade.quelle_aufloesen(alt, base) == soll
    nirgends = r"C:\Users\Dude\Tools\eBooks\Inbox\gibt-es-nicht.epub"
    assert str(ebook_pfade.quelle_aufloesen(nirgends, base)).replace("\\", "/").endswith("Inbox/gibt-es-nicht.epub")
    assert ebook_pfade.quelle_aufloesen("", base) == Path("")
