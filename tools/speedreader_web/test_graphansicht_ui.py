"""Browser-Rauchtest der DOM-Schicht von graphansicht.js (Berührung, Filter, Liste, Zoom, Detailleiste). Ohne Playwright/Chromium uebersprungen."""
import json
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
pytest.importorskip("playwright.sync_api")

from test_werkzeugleiste import browser  # noqa: E402,F401
from test_verbindungen_js import daten  # noqa: E402

SEITE = "<!doctype html><meta charset=utf-8><body style='margin:0;background:#14130f'><div id=h style='position:fixed;inset:0;display:flex;flex-direction:column'></div>"


def d():
    ae = [("b001:1", f"b00{w}:{k}", 0.6 + 0.01 * k) for w in (2, 3) for k in (1, 2, 3, 4)]
    return daten(aehnlich=ae, themen=[("b001#macht", "Macht", [1, 2])], querverweise=[("b001:1", None, "Fremd", "Buch", "ergänzt")])


@pytest.fixture()
def pg(browser):
    ctx = browser.new_context(viewport={"width": 960, "height": 600}, has_touch=True)
    p = ctx.new_page()
    p.set_content(SEITE)
    for f in ("verbindungen.js", "graphlayout.js", "graphansicht.js"):
        p.add_script_tag(content=(HIER / f).read_text(encoding="utf-8"))
    p.evaluate("""(daten) => { const h = document.getElementById('h'); h.style.cssText += ';--bg:#14130f';
        window.opened = []; window.ans = Graphansicht.installiere(h, { oeffnen: (id) => window.opened.push(id) });
        window.ans.setzeDaten(Verbindungen.baue(daten)); window.ans.setzeFokus('b001:1', { ohneAnimation: true }); }""", d())
    p.wait_for_timeout(100)
    yield p
    ctx.close()


def zs(pg):
    return pg.evaluate("ans.zustand()")


def test_netz_hat_ringe_und_tippen_waehlt_mit_detailleiste(pg):
    z = zs(pg)
    assert z["fokus"] == "b001:1" and z["ringe"][0] == ["b001:1"] and len(z["ringe"][1]) >= 5
    ziel = next(i for i in z["ringe"][1] if i.startswith("b002:"))
    r = pg.locator("canvas").bounding_box()
    x, y = z["positionen"][ziel]["x"], z["positionen"][ziel]["y"]
    pg.touchscreen.tap(r["x"] + x, r["y"] + y)
    pg.wait_for_timeout(450)
    assert zs(pg)["ausgewaehlt"] == ziel and pg.locator(".graph-detail").is_visible()
    pg.click(".graph-detail button[data-aktion=oeffnen]")
    assert pg.evaluate("opened") == [ziel]
    pg.click(".graph-detail button[data-aktion=zurmitte]")
    pg.wait_for_timeout(500)
    assert zs(pg)["fokus"] == ziel


def test_filter_zoom_und_liste(pg):
    n0 = len(zs(pg)["ringe"][1])
    pg.click("button[data-art=aehnlich]")
    pg.wait_for_timeout(500)
    assert pg.get_attribute("button[data-art=aehnlich]", "aria-pressed") == "false" and len(zs(pg)["ringe"][1]) < n0
    pg.click("button[data-aktion=plus]")
    k = zs(pg)["transform"]["k"]
    assert k > 1
    pg.click("button[data-aktion=mitte]")
    assert zs(pg)["transform"]["k"] == 1
    pg.click("button[data-aktion=liste]")
    assert pg.locator(".graph-liste").is_visible() and not pg.locator("canvas").is_visible()
    assert pg.locator(".graph-liste button.waehle").count() >= 1
    pg.click("button[data-aktion=liste]")
    assert pg.locator("canvas").is_visible()


def test_knoepfe_sind_mindestens_44_px(pg):
    for sel in ("button[data-aktion=plus]", "button[data-aktion=liste]", "button[data-art=aehnlich]"):
        b = pg.locator(sel).bounding_box()
        assert b["height"] >= 44 and b["width"] >= 44, sel
