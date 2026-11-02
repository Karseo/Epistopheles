"""Tests fuer den Hilfsbau einer kleinen Testbibliothek (fuer Browserpruefungen der App)."""
import json
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

from redaktion.testwurzel import baue_testwurzel  # noqa: E402


def test_testwurzel_hat_ein_buch_mit_drei_chunks_und_das_paket(tmp_path):
    root = baue_testwurzel(tmp_path / "wurzel")
    paket = root / "reader" / "export-epistopheles"
    index = json.loads((paket / "korrektur" / "index.json").read_text(encoding="utf-8"))
    (buch,) = index["buecher"]
    assert (buch["autor"], buch["titel"]) == ("Test, Autor", "Testbuch")
    assert buch["chunks"] == 3 and buch["uebersetzung"] == 3 and len(buch["kapitel"]) == 1
    assert (paket / "korrektur.html").is_file() and (paket / "redaktion.js").is_file()


def test_testwurzel_rohchunks_haben_tabs_und_gebrochenen_satz(tmp_path):
    root = baue_testwurzel(tmp_path / "wurzel")
    chunk = (root / "rohdaten" / "Lektor" / "Test, Autor" / "Testbuch" / "en" / "chunk_000.md").read_text(encoding="utf-8")
    assert "\t" in chunk and "— 47 —" in chunk and "betonte¹" in chunk and "12 Vgl. Pitkin (1967), S. 8." in chunk
