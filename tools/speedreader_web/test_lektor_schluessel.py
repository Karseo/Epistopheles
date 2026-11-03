"""Browserpruefung (P2 Task 3): Buch, dessen Lektor-Ordner anders heisst als das Bibliotheksbuch (O'Neil, Piano).

Korrekturen und "Neu uebersetzen" muessen `ziel.lektor` / `ziel.sprache` mitschicken, damit APIC den Chunk findet.
Ohne Playwright/Chromium uebersprungen."""
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent))

sync_api = pytest.importorskip("playwright.sync_api")

from test_werkzeugleiste import browser  # noqa: E402,F401
from test_neu_uebersetzen import (Apic, BUCH, neue_seite, korrigiere, zu_uebersetzung,  # noqa: E402,F401
                                  neu_text)

import export_korrektur  # noqa: E402
import redaktion_anwenden as ra  # noqa: E402
from redaktion import protokoll  # noqa: E402
from redaktion.testwurzel import AUTOR, TITEL, baue_testwurzel  # noqa: E402

LEKTOR_TITEL = TITEL + " (Lektor-Ordner)"
LEKTOR_SCHLUESSEL = f"{AUTOR}/{LEKTOR_TITEL}"


class ApicAbweichend(Apic):
    def _starte(self, job: dict) -> None:
        self.jobs.append(job)
        lektor = ra.lektor_ordner(self.root, job["buch"], {"lektor": job["lektor"]} if job.get("lektor") else None)
        (lektor / "de" / f"chunk_{job['chunk']:03d}.md.neu").write_bytes(neu_text(job["chunk"]).encode("utf-8"))


@pytest.fixture()
def apic(tmp_path):
    root = baue_testwurzel(tmp_path / "wurzel")
    alt = root / "rohdaten" / "Lektor" / AUTOR / TITEL
    alt.rename(alt.parent / LEKTOR_TITEL)
    export_korrektur.exportiere(root, root / "reader" / "export-epistopheles" / "korrektur",
                                root / "rohdaten" / "Lektor", ebooks=False)
    a = ApicAbweichend(root)
    yield a
    a.stop()


def test_eintraege_und_auftrag_tragen_den_lektor_schluessel(browser, apic):
    ctx, pg = neue_seite(browser, apic.url)
    try:
        assert pg.evaluate("buch.lektor") == LEKTOR_SCHLUESSEL
        korrigiere(pg)
        ziel = pg.evaluate("eintraege[0].ziel")
        assert ziel["lektor"] == LEKTOR_SCHLUESSEL and ziel["sprache"] == "en"
        pg.wait_for_function("eintraege[0].status === 'gesendet'")
        assert protokoll.lade_eingang(apic.root, BUCH)[0]["ziel"]["lektor"] == LEKTOR_SCHLUESSEL
        zu_uebersetzung(pg)
        pg.locator("#neu-uebersetzen").click()
        pg.wait_for_selector("#vergleich[open]")
        assert pg.inner_text("#vergleich-neu") == neu_text(1)
        assert [j["lektor"] for j in apic.jobs] == [LEKTOR_SCHLUESSEL]
    finally:
        ctx.close()
    assert not pg.fehler, pg.fehler


def test_einarbeiten_schreibt_in_den_abweichenden_lektor_ordner(browser, apic):
    ctx, pg = neue_seite(browser, apic.url)
    try:
        korrigiere(pg)
        pg.wait_for_function("eintraege[0].status === 'gesendet'")
    finally:
        ctx.close()
    assert ra.main(["--root", str(apic.root), "--ausfuehren"]) == 0
    chunk = apic.root / "rohdaten" / "Lektor" / AUTOR / LEKTOR_TITEL / "en" / "chunk_001.md"
    erste = chunk.read_text(encoding="utf-8").split("\n")[0]
    assert "responsiveness,\tso that\tthe" in erste                    # Zeilen 0 und 1 verbunden
    assert (chunk.parent.parent / "redaktion.json").is_file()
