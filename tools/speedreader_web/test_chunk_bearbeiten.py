"""Browserpruefung: freies Bearbeiten eines Absatzes im Roh-Chunk (Modus "Chunks"), ohne Verdachtsvorschlag.
Ohne Playwright/Chromium uebersprungen."""
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent))

sync_api = pytest.importorskip("playwright.sync_api")

from test_werkzeugleiste import browser  # noqa: E402,F401
from test_neu_uebersetzen import Apic, neue_seite  # noqa: E402
from test_volltext import JS_TIPPE, baue  # noqa: E402


ZWEITER = "A	second	paragraph"          # die Testchunks trennen Wörter mit Tabs


@pytest.fixture()
def seite(browser, tmp_path):
    apic = Apic(baue(tmp_path))
    ctx, pg = neue_seite(browser, apic.url)
    pg.locator("#modus-chunks").click()
    pg.wait_for_function("modus === 'chunks' && gezeigteSig !== null")
    yield pg
    ctx.close()
    apic.stop()
    assert not pg.fehler, pg.fehler


def test_antippen_im_rohchunk_zeigt_nur_bearbeiten_und_speichert_ersetzen_auf_chunk_ebene(seite):
    seite.evaluate(JS_TIPPE, ZWEITER)
    assert seite.locator("#absatz-leiste").is_visible()
    for knopf in ("absatz-verweis", "absatz-ursache", "absatz-trennen"):
        assert seite.locator("#" + knopf).is_hidden(), knopf          # nur im Volltext
    seite.locator("#absatz-bearbeiten").click()
    seite.wait_for_selector("#absatz-dialog[open]")
    roh = seite.input_value("#absatz-editor")
    assert roh.startswith(ZWEITER) and "Absatz 4 · Chunk 0" in seite.inner_text("#absatz-titel")
    neu = "A second paragraph follows here, joined into one line."
    seite.locator("#absatz-editor").fill(neu)
    seite.locator("#absatz-speichern").click()
    seite.wait_for_function("eintraege.length === 1")
    e = seite.evaluate("eintraege[0]")
    assert (e["ebene"], e["art"]) == ("chunk-orig", "ersetzen")
    assert e["parameter"] == {"nachher": neu}
    assert e["ziel"]["chunk"] == 0 and "datei" not in e["ziel"]
    seite.wait_for_function("!document.getElementById('absatz-dialog').open")
    assert neu in seite.evaluate("document.getElementById('rechts-inhalt').textContent")


def test_unveraenderter_text_wird_nicht_gespeichert(seite):
    seite.evaluate(JS_TIPPE, ZWEITER)
    seite.locator("#absatz-bearbeiten").click()
    seite.wait_for_selector("#absatz-dialog[open]")
    seite.locator("#absatz-speichern").click()
    assert "Keine Änderung" in seite.inner_text("#absatz-warnung")
    assert seite.evaluate("eintraege.length") == 0
