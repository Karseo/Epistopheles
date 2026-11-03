"""Browsertests der Ansicht "Verbindungen" in index.html (Plan 2026-11-03, Task 8). Ohne Playwright/Chromium uebersprungen."""
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
from test_verbindungen_js import daten as verb_daten  # noqa: E402

ERSTELLT = "2026-11-03 10:00:00"


def tage():
    return {"erstellt": ERSTELLT, "buecher": [
        {"id": f"b{w:03d}", "autor": f"Nachname{w}, Vorname", "titel": f"Werk {w}",
         "kapitel": [{"nr": k, "titel": f"Kapitel {k} von {w}", "felder": {"zusammenfassung": f"Zusammenfassung {k}."}} for k in range(1, 5)]}
        for w in range(1, 4)]}


def verbindungen(**kw):
    ae = [("b001:1", f"b00{w}:{k}", 0.6 + 0.01 * k) for w in (2, 3) for k in (1, 2, 3, 4)]
    return verb_daten(aehnlich=ae, themen=[("b001#macht", "Macht", [1, 2])], querverweise=[("b001", None, "Fremd", "Buch", "ergänzt")], **kw)


@pytest.fixture()
def start(browser, tmp_path):
    srv = []

    def los(verb="ok", viewport=(960, 600), seiten=None):
        ordner = tmp_path / f"p{len(srv)}"
        bundle.kopiere_app(ordner)
        (ordner / "daten.json").write_text(json.dumps(tage()), encoding="utf-8")
        if verb == "ok":
            v = verbindungen()
        elif verb == "anders":
            v = {**verbindungen(), "erstellt": "2000-01-01 00:00:00"}
        elif verb == "ohne-qdrant":
            v = verbindungen(qdrant=None)
        else:
            v = None
        if v is not None:
            (ordner / "verbindungen.json").write_text(json.dumps(v), encoding="utf-8")
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ordner))
        h.log_message = lambda *a, **k: None
        s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
        threading.Thread(target=s.serve_forever, daemon=True).start()
        srv.append(s)
        ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, has_touch=True)
        srv.append(ctx)
        pg = ctx.new_page()
        pg.goto(f"http://127.0.0.1:{s.server_port}/index.html")
        pg.wait_for_selector("#modus:not([hidden])")
        return pg, ordner

    yield los
    for x in srv:
        (x.shutdown if hasattr(x, "shutdown") else x.close)()


def netz(pg):
    pg.click("button[data-ansicht=verbindungen]")
    pg.wait_for_selector("#netz canvas", state="visible")
    pg.wait_for_function("verb.ans && verb.ans.zustand().fokus !== null")
    pg.wait_for_timeout(150)
    return pg.evaluate("verb.ans.zustand()")


def tippe(pg, z, id):
    r = pg.locator("#netz canvas").bounding_box()
    p = z["positionen"][id]
    pg.touchscreen.tap(r["x"] + p["x"], r["y"] + p["y"])
    pg.wait_for_timeout(450)                                   # die Leiste ignoriert den nachgereichten Klick des Antippens


def test_ansicht_zeigt_netz_mit_fokus_gleich_offenem_kapitel_und_taste_4(start):
    pg, _ = start()
    pg.keyboard.press("4")
    pg.wait_for_selector("#netz canvas", state="visible")
    pg.wait_for_function("verb.ans && verb.ans.zustand().fokus")
    z = pg.evaluate("verb.ans.zustand()")
    assert z["fokus"] == "b001:1" and len(z["ringe"][1]) >= 5
    assert pg.is_hidden("#lesen") and pg.is_hidden("#buehne")


def test_tippen_waehlt_zeigt_beleg_und_zur_mitte_aendert_nur_das_netz(start):
    pg, _ = start()
    z = netz(pg)
    ziel = next(i for i in z["ringe"][1] if i.startswith("b002:"))
    tippe(pg, z, ziel)
    pg.wait_for_selector(".graph-detail:not([hidden])")
    t = pg.inner_text(".graph-detail")
    assert "Beleg" in t and "Ähnlichkeit" in t
    pg.click(".graph-detail button[data-aktion=zurmitte]")
    pg.wait_for_function(f"verb.ans.zustand().fokus === '{ziel}'")
    assert pg.inner_text("#titel-kapitel").startswith("1. Kapitel 1 von 1")            # das offene Kapitel bleibt


def test_oeffnen_springt_in_das_kapitel_im_ki_text(start):
    pg, _ = start()
    z = netz(pg)
    ziel = next(i for i in z["ringe"][1] if i.startswith("b003:"))
    nr = ziel.split(":")[1]
    tippe(pg, z, ziel)
    pg.click(".graph-detail button[data-aktion=oeffnen]")
    assert pg.get_attribute("button[data-ansicht=ki]", "aria-pressed") == "true"
    assert pg.inner_text("#titel-kapitel") == f"{nr}. Kapitel {nr} von 3" and "Werk 3" in pg.inner_text("#titel-buch")
    assert pg.is_hidden("#netz") and pg.is_visible("#lesen")


def test_hohles_werk_hat_keinen_oeffnen_knopf_und_ist_nicht_zur_mitte_setzbar(start):
    pg, _ = start()
    netz(pg)
    pg.evaluate("verb.ans.setzeFokus('b001', { ohneAnimation: true })")
    pg.wait_for_timeout(150)
    z = pg.evaluate("verb.ans.zustand()")
    ext = next(i for i in z["ringe"][1] if i.startswith("x:"))
    tippe(pg, z, ext)
    pg.wait_for_selector(".graph-detail:not([hidden])")
    assert "nicht öffnbar" in pg.inner_text(".graph-detail")
    assert pg.locator(".graph-detail button[data-aktion=oeffnen]").count() == 0
    assert pg.is_disabled(".graph-detail button[data-aktion=zurmitte]")


def test_filter_aehnlich_aus_entfernt_aehnliche_knoten_und_liste_zeigt_dasselbe(start):
    pg, _ = start()
    z = netz(pg)
    assert any(i.startswith("b002:") for i in z["ringe"][1])
    pg.click("button[data-art=aehnlich]")
    pg.wait_for_timeout(500)
    z = pg.evaluate("verb.ans.zustand()")
    assert not any(i.startswith(("b002:", "b003:")) for i in z["ringe"][1])
    pg.click("button[data-art=aehnlich]")
    pg.wait_for_timeout(500)
    pg.click("button[data-aktion=liste]")
    ids = pg.eval_on_selector_all(".graph-liste button.waehle", "e => e.map(x => x.dataset.id)")
    z = pg.evaluate("verb.ans.zustand()")
    assert ids and all(i in z["ringe"][1] or i in z["ringe"][2] or i.startswith("x:") for i in ids)
    pg.click(".graph-liste button.waehle:not([disabled])")
    pg.wait_for_function("verb.ans.zustand().fokus !== 'b001:1'")


def test_kapitelwechsel_in_anderer_ansicht_verschiebt_den_fokus(start):
    pg, _ = start()
    netz(pg)
    pg.click("button[data-ansicht=ki]")
    pg.click("#kap-vor")
    pg.keyboard.press("4")
    pg.wait_for_function("verb.ans.zustand().fokus === 'b001:2'")
    pg.keyboard.press("p")
    pg.wait_for_function("verb.ans.zustand().fokus === 'b001:1'")


@pytest.mark.parametrize("verb,text", [("fehlt", "Noch keine Verbindungsdaten"), ("anders", "anderen Export")])
def test_fehlende_oder_fremde_datei_zeigt_hinweis_statt_netz(start, verb, text):
    pg, _ = start(verb)
    pg.click("button[data-ansicht=verbindungen]")
    pg.wait_for_function("verb.status !== 'laedt'")
    pg.wait_for_selector("#netz-hinweis:not([hidden])")
    assert text in pg.inner_text("#netz-hinweis") and pg.locator("#netz canvas").count() == 0
    assert pg.locator("#netz-import").is_visible()


def test_ohne_qdrant_zeigt_netz_mit_sichtbarem_hinweis(start):
    pg, _ = start("ohne-qdrant")
    netz(pg)
    assert "Ähnliche Stellen fehlen" in pg.inner_text("#netz-info")


def test_import_ueber_dialog_und_zwischenspeicher_ueberlebt_neuladen_ohne_netz(start, tmp_path):
    pg, ordner = start("fehlt")
    pg.click("button[data-ansicht=verbindungen]")
    pg.wait_for_selector("#netz-hinweis:not([hidden])")
    datei = tmp_path / "verbindungen.json"
    datei.write_text(json.dumps(verbindungen()), encoding="utf-8")
    pg.set_input_files("#verb-datei", str(datei))
    pg.wait_for_selector("#netz canvas", state="visible")
    (ordner / "daten.json").unlink()                                           # Server liefert nichts mehr: nur der Zwischenspeicher
    pg.reload()
    pg.wait_for_selector("#modus:not([hidden])")
    pg.wait_for_function("verb.status === 'ok'")
    z = netz(pg)
    assert z["fokus"] == "b001:1"


@pytest.mark.parametrize("viewport", [(960, 600), (600, 960)])
def test_bedienelemente_haben_mindestens_44_px(start, viewport):
    pg, _ = start(viewport=viewport)
    netz(pg)
    for sel in ("button[data-art=aehnlich]", "button[data-art=thema]", "button[data-aktion=plus]", "button[data-aktion=minus]", "button[data-aktion=mitte]", "button[data-aktion=liste]"):
        b = pg.locator(sel).bounding_box()
        assert b["height"] >= 44 and b["width"] >= 44, (sel, b)
        assert 0 <= b["x"] and b["x"] + b["width"] <= viewport[0], sel
    f = pg.locator(".graph-flaeche").bounding_box()
    assert f["height"] >= 200 and f["x"] + f["width"] <= viewport[0]


def test_antippen_verschiebt_weder_netz_noch_trifft_der_nachgereichte_klick_die_leiste(start):
    """Regression: die Detailleiste ueberlagert die Flaeche; Tippen auf einen Knoten am unteren Rand darf die Auswahl nicht sofort wieder aufheben."""
    pg, _ = start()
    netz(pg)
    pg.evaluate("verb.ans.setzeFokus('b001', { ohneAnimation: true })")
    pg.wait_for_timeout(200)
    z = pg.evaluate("verb.ans.zustand()")
    ext = next(i for i in z["ringe"][1] if i.startswith("x:"))
    tippe_ohne_warten = pg.locator("#netz canvas").bounding_box()
    p = z["positionen"][ext]
    pg.touchscreen.tap(tippe_ohne_warten["x"] + p["x"], tippe_ohne_warten["y"] + p["y"])
    pg.wait_for_timeout(300)
    z2 = pg.evaluate("verb.ans.zustand()")
    assert z2["ausgewaehlt"] == ext and z2["positionen"][ext] == p
