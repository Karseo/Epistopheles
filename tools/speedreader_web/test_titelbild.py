"""Titelbild beim Start der App mit Versionsnummer (Browser). Ohne Playwright/Chromium uebersprungen."""
import functools
import http.server
import json
import re
import sys
import threading
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
pytest.importorskip("playwright.sync_api")

import bundle  # noqa: E402
from test_werkzeugleiste import browser  # noqa: E402,F401

VERSION = re.search(r'EPISTO_VERSION = "([^"]+)"', (HIER / "version.js").read_text(encoding="utf-8")).group(1)


@pytest.fixture()
def start(browser, tmp_path):
    res = []

    def los(**ctx_args):
        ordner = tmp_path / f"p{len(res)}"
        bundle.kopiere_app(ordner)
        (ordner / "daten.json").write_text(json.dumps({"erstellt": "E", "buecher": [{"id": "b001", "autor": "A, A", "titel": "W", "kapitel": [
            {"nr": 1, "titel": "Eins", "felder": {"zusammenfassung": "Ein Satz."}}]}]}), encoding="utf-8")
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ordner))
        h.log_message = lambda *a, **k: None
        s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
        threading.Thread(target=s.serve_forever, daemon=True).start()
        ctx = browser.new_context(viewport={"width": 960, "height": 600}, has_touch=True, **ctx_args)
        res.extend([s, ctx])
        pg = ctx.new_page()
        pg.goto(f"http://127.0.0.1:{s.server_port}/index.html")
        return pg

    yield los
    for x in res:
        (x.shutdown if hasattr(x, "shutdown") else x.close)()


def test_titelbild_zeigt_version_blockiert_nichts_und_verschwindet(start):
    pg = start()
    assert pg.is_visible("#titelbild")
    t = pg.inner_text("#titelbild")
    assert "EPISTO" in t and "Epistopheles" in t and f"Version {VERSION}" in t
    assert pg.get_attribute("#titelbild", "aria-hidden") == "true"
    pg.wait_for_selector("#modus:not([hidden])")
    # faengt keine Eingaben ab: ein Klick auf den Kapitelknopf funktioniert sofort
    pg.click("#knopf-wahl", timeout=2000)
    assert pg.is_visible("#wahl")
    assert f"App {VERSION}" in pg.inner_text("#wahl-fuss")
    pg.wait_for_selector("#titelbild", state="detached", timeout=4000)


def test_titelbild_bei_reduzierter_bewegung_verschwindet_ebenfalls(start):
    pg = start(reduced_motion="reduce")
    pg.wait_for_selector("#titelbild", state="detached", timeout=4000)
