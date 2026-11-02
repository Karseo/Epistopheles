"""ebook-translate.py per Subprozess testen (der Import zieht schwere Pakete)."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

_EBOOK = Path(__file__).resolve().parents[1] / "pipeline" / "ebook-translate.py"


def _lauf_ebook(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess:
    eingabe = tmp_path / "b.txt"
    eingabe.write_text("hallo", encoding="utf-8")
    lektor = tmp_path / "L"
    buch = lektor / "A" / "T"
    buch.mkdir(parents=True, exist_ok=True)
    (buch / "redaktion.json").write_text("{}", encoding="utf-8")
    (buch / ".progress.json").write_text('{"x": 1}', encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(_EBOOK), str(eingabe), "--lektor", str(lektor),
         "--book-dir", str(buch), *extra],
        capture_output=True, text=True, encoding="utf-8", timeout=60)


def test_ebook_translate_bricht_ohne_resume_ab_und_laesst_progress_unberuehrt(tmp_path):
    p = _lauf_ebook(tmp_path)
    assert p.returncode != 0
    assert "--korrekturen-verwerfen" in p.stdout + p.stderr
    assert (tmp_path / "L" / "A" / "T" / ".progress.json").read_text(encoding="utf-8") == '{"x": 1}'


def test_ebook_translate_help_zeigt_schalter():
    p = subprocess.run([sys.executable, str(_EBOOK), "--help"], capture_output=True,
                       text=True, encoding="utf-8", timeout=60)
    assert p.returncode == 0 and "--korrekturen-verwerfen" in p.stdout
