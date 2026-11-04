"""Browsertests: der Speedreader liest auch den Originaltext (Quelle KI-Felder / Originaltext). Ohne Playwright/Chromium uebersprungen."""
import functools
import http.server
import json
import sys
import threading
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
pytest.importorskip("playwright.sync_api")

import bundle  # noqa: E402
from test_werkzeugleiste import browser  # noqa: E402,F401

ERSTELLT = "2026-11-04 09:00:00"
TEXT1 = "Vorspann mit drei Wörtern.\n\n# Erster Abschnitt\n\nDer Text beginnt hier.[^1] Er geht weiter.\n\n## Seite 7\n\n- Ein Punkt\n\n[^1]: Fußnote nie lesen\n\n# Zweiter Abschnitt\n\nUnd schließt ab.\n"
TEXT2 = "# Anderes Kapitel\n\nAndere Wörter stehen hier.\n"


def daten(mit_id=True):
    ks = [{"nr": n, "titel": f"Kapitel {n}", "felder": {"zusammenfassung": f"Kurzfassung {n}."}} for n in (1, 2)]
    return {"erstellt": ERSTELLT, "buecher": [{"id": "b001", "autor": "A, A", "titel": "Werk", "kapitel": ks}]}


@pytest.fixture()
def start(browser, tmp_path):
    res = []

    def los(volltext=True, viewport=(960, 600)):
        ordner = tmp_path / f"p{len(res)}"
        bundle.kopiere_app(ordner)
        (ordner / "daten.json").write_text(json.dumps(daten()), encoding="utf-8")
        if volltext:
            (ordner / "buecher").mkdir()
            (ordner / "buecher" / "b001.json").write_text(json.dumps({"id": "b001", "erstellt": ERSTELLT, "kapitel": {"1": TEXT1, "2": TEXT2}}), encoding="utf-8")
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ordner))
        h.log_message = lambda *a, **k: None
        s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
        threading.Thread(target=s.serve_forever, daemon=True).start()
        ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, has_touch=True)
        res.extend([s, ctx])
        pg = ctx.new_page()
        pg.goto(f"http://127.0.0.1:{s.server_port}/index.html")
        pg.wait_for_selector("#modus:not([hidden])")
        pg.wait_for_function("woerter.length > 0")
        return pg, f"http://127.0.0.1:{s.server_port}/index.html"

    yield los
    for x in res:
        (x.shutdown if hasattr(x, "shutdown") else x.close)()


def texte(pg):
    return pg.evaluate("woerter.map(w => w.text)")


def test_standard_ist_ki_und_umschalten_laedt_den_originaltext(start):
    pg, _ = start()
    assert pg.get_attribute("[data-quelle=ki]", "aria-pressed") == "true" and texte(pg)[0] == "Zusammenfassung"
    pg.click("[data-quelle=original]")
    pg.wait_for_function("woerter.length > 0 && woerter[0].text === 'Vorspann'")
    t = texte(pg)
    assert t[:4] == ["Vorspann", "mit", "drei", "Wörtern."] and "Fußnote" not in t and "Seite" not in t and "Ein" in t
    assert pg.evaluate("namen") == ["Kapitel 1", "Erster Abschnitt", "Zweiter Abschnitt"]
    assert "Kapitel 1 · Wort 1/" in pg.inner_text("#status")
    pg.click("[data-quelle=ki]")
    pg.wait_for_function("woerter.length && woerter[0].text === 'Zusammenfassung'")


def test_ablauf_und_abschnittssprung_im_originaltext(start):
    pg, _ = start()
    pg.click("[data-quelle=original]")
    pg.wait_for_function("woerter.length && woerter[0].text === 'Vorspann'")
    pg.click("[data-aktion=abschnitt_vor]")
    assert pg.evaluate("woerter[i].text") == "Erster" and "Erster Abschnitt" in pg.inner_text("#status")
    pg.click("[data-aktion=satz_vor]")
    pg.click("#pause")
    pg.wait_for_function("i > 3")
    pg.click("#pause")


def test_lesestelle_und_quelle_bleiben_nach_neuladen_und_gelten_je_kapitel(start):
    pg, url = start()
    pg.click("[data-quelle=original]")
    pg.wait_for_function("woerter.length && woerter[0].text === 'Vorspann'")
    pg.fill("#balken", "6")
    pg.dispatch_event("#balken", "input")
    pg.wait_for_function("i === 6")
    pg.click("#kap-vor")
    pg.wait_for_function("woerter.length && woerter[0].text === 'Anderes'")
    pg.click("#kap-zurueck")
    pg.wait_for_function("woerter.length && woerter[0].text === 'Vorspann' && i === 6")
    pg.reload()
    pg.wait_for_function("woerter.length > 0 && woerter[0].text === 'Vorspann'")
    assert pg.evaluate("i") == 6 and pg.get_attribute("[data-quelle=original]", "aria-pressed") == "true"


def test_fehlender_volltext_zeigt_meldung_mit_import_und_ki_bleibt_nutzbar(start):
    pg, _ = start(volltext=False)
    pg.click("[data-quelle=original]")
    pg.wait_for_function("() => { const e = document.querySelector('#leer'); return e && !e.hidden && e.innerText.includes('nicht auf diesem Gerät'); }")
    assert "nicht auf diesem Gerät" in pg.inner_text("#leer") and pg.is_visible("#leer-import")
    pg.click("[data-quelle=ki]")
    pg.wait_for_function("woerter.length > 0")
    assert pg.is_hidden("#leer")


def test_wechsel_aus_ki_text_und_zurueck_funktioniert_mit_originalquelle(start):
    pg, _ = start()
    pg.click("[data-quelle=original]")
    pg.wait_for_function("woerter.length && woerter[0].text === 'Vorspann'")
    pg.click("button[data-ansicht=ki]")
    pg.click("#kap-vor")
    pg.click("button[data-ansicht=speed]")
    pg.wait_for_function("woerter.length && woerter[0].text === 'Anderes'")


@pytest.mark.parametrize("viewport", [(960, 600), (600, 960)])
def test_quellenknoepfe_haben_mindestens_44_px(start, viewport):
    pg, _ = start(viewport=viewport)
    for sel in ("[data-quelle=ki]", "[data-quelle=original]"):
        b = pg.locator(sel).bounding_box()
        assert b["height"] >= 44 and b["width"] >= 44 and b["x"] + b["width"] <= viewport[0], (sel, b)
