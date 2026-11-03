"""Gesamtlauf Querverbindungen (Task 9), Ende zu Ende auf einer Testwurzel mit Qdrant-Attrappe, ohne Eingriff in echte Daten:
daten.json -> export_verbindungen (Exit 0) -> App im Browser -> Ansicht -> Nachbar antippen -> Oeffnen -> richtiges Kapitel;
danach Export mit ausgefallenem Qdrant (Exit 3): App zeigt den Hinweis, Themen und Querverweise bleiben; Leistung mit 950 Kapiteln."""
import functools
import http.server
import json
import sys
import threading
import time
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent))
pytest.importorskip("playwright.sync_api")

import bundle  # noqa: E402
import export_verbindungen as ev  # noqa: E402
from test_werkzeugleiste import browser  # noqa: E402,F401
from test_export_verbindungen import welt  # noqa: E402,F401


def serve(ordner: Path):
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ordner))
    h.log_message = lambda *a, **k: None
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_port}/index.html"


def tippe(pg, id):
    z = pg.evaluate("verb.ans.zustand()")
    r = pg.locator("#netz canvas").bounding_box()
    p = z["positionen"][id]
    pg.touchscreen.tap(r["x"] + p["x"], r["y"] + p["y"])
    pg.wait_for_timeout(450)


def test_gesamtlauf_export_app_oeffnen_und_ausfall(browser, welt, capsys):
    root, paket, _, fake = welt
    assert ev.main(["--root", str(root), "--qdrant", fake.url, "--pause", "0"]) == 0
    bundle.kopiere_app(paket)
    srv, url = serve(paket)
    ctx = browser.new_context(viewport={"width": 960, "height": 600}, has_touch=True)
    try:
        pg = ctx.new_page()
        pg.goto(url)
        pg.wait_for_selector("#modus:not([hidden])")
        pg.click("button[data-ansicht=verbindungen]")
        pg.wait_for_selector("#netz canvas", state="visible")
        pg.wait_for_function("verb.ans && verb.ans.zustand().fokus === 'b001:1'")
        z = pg.evaluate("verb.ans.zustand()")
        assert {"b002:1", "b002:2", "b001#macht"} <= set(z["ringe"][1]) and pg.inner_text("#netz-info") == ""
        tippe(pg, "b002:2")
        assert "Ähnlichkeit" in pg.inner_text(".graph-detail")
        pg.click(".graph-detail button[data-aktion=oeffnen]")
        assert pg.inner_text("#titel-kapitel") == "2. Zwei" and "Beta" in pg.inner_text("#titel-buch")
        assert pg.get_attribute("button[data-ansicht=ki]", "aria-pressed") == "true"
        pg.close()

        # Qdrant faellt aus: Exit 3, Datei mit Themen und Querverweisen, App zeigt den Hinweis
        assert ev.main(["--root", str(root), "--qdrant", "http://127.0.0.1:9", "--versuche", "1", "--pause", "0"]) == 3
        pg = ctx.new_page()
        pg.goto(url)
        pg.wait_for_selector("#modus:not([hidden])")
        pg.click("button[data-ansicht=verbindungen]")
        pg.wait_for_selector("#netz canvas", state="visible")
        pg.wait_for_function("verb.ans && verb.ans.zustand().fokus === 'b002:2'")          # die App merkt sich das zuletzt geoeffnete Kapitel
        assert "Ähnliche Stellen" in pg.inner_text("#netz-info")
        pg.evaluate("verb.ans.setzeFokus('b001:1', { ohneAnimation: true })")
        pg.wait_for_timeout(200)
        ring1 = pg.evaluate("verb.ans.zustand().ringe[1]")
        assert "b001#macht" in ring1 and not any(i.startswith("b002:") for i in ring1)
        pg.evaluate("verb.ans.setzeFokus('b001', { ohneAnimation: true })")
        pg.wait_for_timeout(200)
        assert any(i.startswith("b002") for i in pg.evaluate("verb.ans.zustand().ringe[1]"))      # Querverweis b001 -> b002 bleibt
    finally:
        ctx.close()
        srv.shutdown()


def test_leistung_950_kapitel_laedt_und_zeichnet_schnell(browser, tmp_path):
    n_werke, je = 80, 12
    paket = tmp_path / "p"
    bundle.kopiere_app(paket)
    tage = {"erstellt": "E1", "buecher": [{"id": f"b{w:03d}", "autor": f"Autor{w}, A", "titel": f"Werk {w}",
                                            "kapitel": [{"nr": k, "titel": f"Kapitel {k} über Größe", "felder": {}} for k in range(1, je + 1)]}
                                           for w in range(1, n_werke + 1)]}
    kap = [{"id": f"b{w:03d}:{k}", "werk": f"b{w:03d}", "nr": k, "titel": f"Kapitel {k} über Größe"} for w in range(1, n_werke + 1) for k in range(1, je + 1)]
    ids = [k["id"] for k in kap]
    beleg = ("Ärger über Größe und Übung " * 7)[:140]
    ae = [{"von": ids[i], "nach": ids[(i * 7 + j * 13 + 5) % len(ids)], "wert": round(0.55 + (i * j % 40) / 100, 3), "beleg": beleg}
          for i in range(len(ids)) for j in range(1, 9) if ids[i].split(":")[0] != ids[(i * 7 + j * 13 + 5) % len(ids)].split(":")[0]]
    v = {"version": 1, "erstellt": "E1", "qdrant": {"abgefragt": len(ids), "fehlend": 0, "mindestwert": 0.55},
         "werke": [{"id": b["id"], "autor": b["autor"], "titel": b["titel"]} for b in tage["buecher"]], "kapitel": kap,
         "themen": [], "aehnlich": ae, "querverweise": []}
    (paket / "daten.json").write_text(json.dumps(tage), encoding="utf-8")
    (paket / "verbindungen.json").write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
    srv, url = serve(paket)
    ctx = browser.new_context(viewport={"width": 960, "height": 600}, has_touch=True)
    try:
        pg = ctx.new_page()
        pg.goto(url)
        pg.wait_for_selector("#modus:not([hidden])")
        t0 = time.time()
        pg.click("button[data-ansicht=verbindungen]")
        pg.wait_for_function("verb.ans && verb.ans.zustand().fokus === 'b001:1' && verb.ans.zustand().ringe[1].length >= 10")
        assert time.time() - t0 < 2.0
        heap = pg.evaluate("performance.memory ? performance.memory.usedJSHeapSize : 0")
        assert heap < 200 * 1024 * 1024
    finally:
        ctx.close()
        srv.shutdown()
