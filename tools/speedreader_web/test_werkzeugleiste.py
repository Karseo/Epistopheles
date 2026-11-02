"""Browserpruefung der Chunk-Ansicht B (freies Markieren, #werkzeugleiste) bei 960x600.

Baut eine Testwurzel, liefert das Epistopheles-Paket per http.server aus und treibt korrektur.html
mit Playwright (Chromium). Ohne Playwright/Chromium uebersprungen."""
import functools
import http.server
import json
import sys
import threading
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

sync_api = pytest.importorskip("playwright.sync_api")

# Hilfen im Browser: Auswahl per Skript setzen (Text-Anfang und -Ende als Fundstellen im angezeigten Text)
JS_AUSWAHL = """([a, b, nachA, nachB]) => {
  const pre = document.getElementById('rechts-inhalt');
  const finde = (nadel, nach) => {
    const w = document.createTreeWalker(pre, NodeFilter.SHOW_TEXT);
    let t;
    while ((t = w.nextNode())) { const i = t.data.indexOf(nadel); if (i >= 0) return [t, i + (nach ? nadel.length : 0)]; }
    throw new Error('nicht gefunden: ' + nadel);
  };
  const [t1, o1] = finde(a, nachA), [t2, o2] = finde(b, nachB);
  const r = document.createRange(); r.setStart(t1, o1); r.setEnd(t2, o2);
  const s = getSelection(); s.removeAllRanges(); s.addRange(r);
}"""


@pytest.fixture(scope="module")
def paket(tmp_path_factory):
    from redaktion.testwurzel import baue_testwurzel
    root = baue_testwurzel(tmp_path_factory.mktemp("w") / "wurzel")
    paket = root / "reader" / "export-epistopheles"
    for f in (paket / "korrektur").glob("k*.json"):                  # Chunk 2 mit Windows-Zeilenenden
        d = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(d.get("chunks"), list) and len(d["chunks"]) > 1:
            d["chunks"].append("Alpha beginnt hier und\r\nsetzt sich fort bis\r\nzum Ende.\r\n\r\nBeta\tbeginnt\r\nmit Tab und\r\nendet.\r\n")
            f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            idx = json.loads((paket / "korrektur" / "index.json").read_text(encoding="utf-8"))
            for b in idx["buecher"]:
                b["chunks"] = len(d["chunks"])
            (paket / "korrektur" / "index.json").write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(paket))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/korrektur.html"
    srv.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:                                         # kein Chromium installiert
            pytest.skip(f"Chromium nicht verfuegbar: {e}")
        yield b
        b.close()


@pytest.fixture()
def seite(browser, paket):
    ctx = browser.new_context(viewport={"width": 960, "height": 600}, has_touch=True)
    pg = ctx.new_page()
    pg.set_default_timeout(5000)
    fehler = []
    pg.on("pageerror", lambda e: fehler.append(str(e)))
    pg.goto(paket)
    pg.wait_for_function("typeof buch !== 'undefined' && buch && eintraegeBuchId === buch.id && gezeigteSig !== null")
    yield pg
    ctx.close()
    assert not fehler, fehler


def zu_chunk(pg, n):
    pg.evaluate(f"rechtsSpringe({n})")
    pg.wait_for_function(f"gezeigterChunk === {n} && gezeigteSig !== null && eintraegeBuchId === buch.id")


def waehle(pg, a, b, nach_a=False, nach_b=True):
    pg.evaluate(JS_AUSWAHL, [a, b, nach_a, nach_b])
    pg.wait_for_timeout(150)


def eintraege(pg):
    return pg.evaluate("eintraege.map(e => ({art: e.art, ziel: e.ziel, parameter: e.parameter, status: e.status}))")


def text(pg):
    return pg.evaluate("document.getElementById('rechts-inhalt').textContent")


def leiste_offen(pg):
    return pg.locator("#werkzeugleiste").is_visible()


def knopf(pg, was):
    return pg.locator(f'#werkzeugleiste button[data-was="{was}"]')


def test_ohne_auswahl_keine_leiste_und_nach_auswahl_da(seite):
    zu_chunk(seite, 1)
    assert not leiste_offen(seite)
    waehle(seite, "Representation", "judge")
    assert leiste_offen(seite)
    seite.evaluate("getSelection().removeAllRanges()")
    seite.wait_for_timeout(200)
    assert not leiste_offen(seite)


def test_alle_knoepfe_mindestens_44px_und_deutsche_namen(seite):
    zu_chunk(seite, 1)
    waehle(seite, "Representation", "judge")
    namen = [seite.locator("#werkzeugleiste button").nth(i).inner_text() for i in range(8)]
    assert namen == ["Zeilen verbinden", "Ausschneiden / verschieben", "Löschen", "Absatz hier trennen",
                     "Kapitel beginnt hier", "Inhaltsverzeichnis", "Glossar", "Nur markieren"]
    for i in range(8):
        box = seite.locator("#werkzeugleiste button").nth(i).bounding_box()
        assert box["height"] >= 44 and box["width"] >= 44, namen[i]
    assert seite.locator("#werkzeug-notiz").bounding_box()["height"] >= 44
    leiste = seite.locator("#werkzeugleiste").bounding_box()
    assert leiste["x"] >= 0 and leiste["y"] >= 0 and leiste["x"] + leiste["width"] <= 960 and leiste["y"] + leiste["height"] <= 600


def test_verbinden_mehrerer_zeilen_aendert_sichtbaren_text(seite):
    zu_chunk(seite, 1)
    vorher = text(seite)
    waehle(seite, "Representation", "name.")                      # Zeilen 0 bis 2 des ersten Absatzes
    knopf(seite, "verbinden").click()
    seite.wait_for_function("eintraege.length === 2")
    e = eintraege(seite)
    assert [x["art"] for x in e] == ["verbinden", "verbinden"] and all(x["ziel"]["zeile"] == 0 for x in e)
    seite.wait_for_function("document.getElementById('rechts-inhalt').textContent !== " + json.dumps(vorher))
    neu = text(seite)
    assert "that the people can judge the actions of those who act in their name." in neu.replace("\t", " ")
    assert neu.count("\n") == vorher.count("\n") - 2
    assert not leiste_offen(seite)


def test_trennen_und_loeschen(seite):
    zu_chunk(seite, 1)
    vorher = text(seite)
    waehle(seite, "that\tthe", "judge")                              # Zeile 1: trennen davor
    assert knopf(seite, "trennen").is_enabled()
    knopf(seite, "trennen").click()
    seite.wait_for_function("eintraege.length === 1")
    assert eintraege(seite)[0]["art"] == "trennen" and eintraege(seite)[0]["ziel"]["zeile"] == 1
    seite.wait_for_function("document.getElementById('rechts-inhalt').textContent.includes('so\\n\\nthat')")
    waehle(seite, "in\ttheir", "name.")                               # jetzt eigener Absatz: loeschen
    knopf(seite, "loeschen").click()
    seite.wait_for_function("eintraege.length === 2")
    assert eintraege(seite)[1]["art"] == "loeschen"
    seite.wait_for_function("!document.getElementById('rechts-inhalt').textContent.includes('their')")
    assert len(text(seite)) < len(vorher)


def test_verschieben_zweiter_schritt_zielabsatz(seite):
    zu_chunk(seite, 1)
    waehle(seite, "Representation", "judge")
    knopf(seite, "verschieben").click()
    assert seite.evaluate("document.getElementById('rechts-inhalt').dataset.verschieben") == "1"
    assert "Zielabsatz" in seite.locator(".werkzeug-status").inner_text()
    assert seite.locator('#werkzeugleiste button[data-was="abbrechen"]').is_visible()
    seite.locator("#rechts-inhalt").get_by_text("Elections", exact=False).first.tap()
    seite.wait_for_function("eintraege.length === 1")
    e = eintraege(seite)[0]
    assert e["art"] == "verschieben" and e["parameter"]["nach_anfang"].startswith("Elections")
    assert e["ziel"]["zeile"] == 0 and e["ziel"]["zeile_bis"] == 1
    neu = text(seite)
    assert neu.index("Elections") < neu.index("Representation")        # Zeilen stehen nun hinter dem Zielabsatz
    assert not leiste_offen(seite)


def test_verschieben_abbrechen_aendert_nichts(seite):
    zu_chunk(seite, 1)
    waehle(seite, "Representation", "judge")
    knopf(seite, "verschieben").click()
    seite.locator('#werkzeugleiste button[data-was="abbrechen"]').click()
    assert seite.evaluate("document.getElementById('rechts-inhalt').dataset.verschieben") is None
    assert eintraege(seite) == []


def test_markierungen_aendern_text_nicht_und_zaehlen_als_markierung(seite):
    zu_chunk(seite, 1)
    vorher = text(seite)
    waehle(seite, "Representation", "judge")
    seite.fill("#werkzeug-notiz", "Prüfen: Käse")
    knopf(seite, "markieren").click()
    seite.wait_for_function("eintraege.length === 1")
    waehle(seite, "Elections", "contested", nach_b=True)
    knopf(seite, "kapitel").click()
    seite.wait_for_function("eintraege.length === 2")
    waehle(seite, "Representation", "judge")
    knopf(seite, "verzeichnis").click()
    seite.wait_for_function("eintraege.length === 3")
    waehle(seite, "Representation", "judge")
    knopf(seite, "glossar").click()
    seite.wait_for_function("eintraege.length === 4")
    e = eintraege(seite)
    assert [x["art"] for x in e] == ["marke"] * 4
    assert [x["parameter"]["kategorie"] for x in e] == ["markiert", "kapitelgrenze-vermutet", "verzeichnis", "glossar"]
    assert e[0]["parameter"]["text"] == "Prüfen: Käse"
    assert text(seite) == vorher
    assert "4 Markierungen" in seite.inner_text("#aenderungen-text") and "0 Änderungen" in seite.inner_text("#aenderungen-text")
    assert seite.locator("#rechts-inhalt .markiert[data-marke]").count() >= 2


def test_auswahl_ueber_zwei_absaetze_deaktiviert_textwerkzeuge(seite):
    zu_chunk(seite, 1)
    waehle(seite, "Representation", "Elections")
    assert leiste_offen(seite)
    for was in ("verbinden", "verschieben", "loeschen", "trennen", "kapitel"):
        assert knopf(seite, was).is_disabled(), was
    for was in ("markieren", "verzeichnis", "glossar"):
        assert knopf(seite, was).is_enabled(), was
    knopf(seite, "verzeichnis").click()
    seite.wait_for_function("eintraege.length === 1")
    e = eintraege(seite)[0]
    assert e["art"] == "marke" and e["ziel"]["absatz_index"] == 0 and e["parameter"]["bis_absatz_index"] == 2
    assert e["parameter"]["bis_anfang"].startswith("Elections")


def test_steuerzeichen_an_verschiebt_die_zuordnung_nicht(seite):
    zu_chunk(seite, 1)
    seite.click("#steuer")
    seite.wait_for_function("document.querySelector('#rechts-inhalt [data-leer]') !== null")
    waehle(seite, "people", "judge")                                 # Tab-Pfeile liegen im DOM davor
    knopf(seite, "trennen").click()
    seite.wait_for_function("eintraege.length === 1")
    e = eintraege(seite)[0]
    assert e["art"] == "trennen" and e["ziel"]["zeile"] == 1 and e["ziel"]["absatz_index"] == 0


def test_crlf_und_tabs_bleiben_im_eintrag_byte_treu(seite):
    zu_chunk(seite, 3)
    assert "\r\n" in seite.evaluate("daten.chunks[3]")
    waehle(seite, "Beta", "endet.")
    knopf(seite, "verbinden").click()
    seite.wait_for_function("eintraege.length === 2")
    e = eintraege(seite)
    assert all(x["art"] == "verbinden" and x["ziel"]["absatz_index"] == 1 and x["ziel"]["zeile"] == 0 for x in e)
    neu = text(seite)
    assert neu.startswith("Alpha beginnt hier und\r\nsetzt sich fort bis\r\nzum Ende.\r\n\r\nBeta\tbeginnt mit Tab und endet.")
    assert neu.endswith("\r\n")


def test_zweite_operation_baut_auf_abgespieltem_text_auf(seite):
    zu_chunk(seite, 1)
    waehle(seite, "Representation", "so")                              # erste Zeile mit der zweiten verbinden
    knopf(seite, "verbinden").click()
    seite.wait_for_function("eintraege.length === 1")
    seite.wait_for_function("gezeigteSig.includes(eintraege[0].id)")
    waehle(seite, "in\ttheir", "name.")
    knopf(seite, "loeschen").click()
    seite.wait_for_function("eintraege.length === 2")
    # beide Eintraege passen nacheinander auf den Roh-Chunk (kein Konflikt)
    seite.wait_for_function("document.querySelectorAll('#rechts-inhalt .konflikt').length === 0")
    assert eintraege(seite)[1]["ziel"]["zeile"] == 1


def test_hochformat_leiste_verdeckt_die_auswahl_nicht(browser, paket):
    ctx = browser.new_context(viewport={"width": 600, "height": 960}, has_touch=True)
    pg = ctx.new_page()
    pg.set_default_timeout(5000)
    pg.goto(paket)
    pg.wait_for_function("typeof buch !== 'undefined' && buch && eintraegeBuchId === buch.id && gezeigteSig !== null")
    zu_chunk(pg, 1)
    for a, b in (("people", "judge"), ("Representation", "so"), ("Elections", "contested")):
        waehle(pg, a, b)
        assert leiste_offen(pg)
        sel = pg.evaluate("(() => { const r = getSelection().getRangeAt(0).getBoundingClientRect(); return {t: r.top, b: r.bottom}; })()")
        box = pg.locator("#werkzeugleiste").bounding_box()
        assert box["y"] >= sel["b"] - 1 or box["y"] + box["height"] <= sel["t"] + 1, (a, sel, box)
        for i in range(8):
            kb = pg.locator("#werkzeugleiste button").nth(i).bounding_box()
            assert kb["height"] >= 44 and kb["width"] >= 44
    ctx.close()


def test_verschieben_modus_endet_beim_chunkwechsel(seite):
    zu_chunk(seite, 1)
    waehle(seite, "Representation", "judge")
    knopf(seite, "verschieben").click()
    assert seite.evaluate("document.getElementById('rechts-inhalt').dataset.verschieben") == "1"
    zu_chunk(seite, 2)
    assert not leiste_offen(seite)
    assert seite.evaluate("document.getElementById('rechts-inhalt').dataset.verschieben") is None
    assert seite.evaluate("werkzeugLeiste.zustand().modus") is None
    assert eintraege(seite) == []


def test_offsets_bei_aktivem_steuerzeichenschalter_stimmen(seite):
    zu_chunk(seite, 1)
    seite.click("#steuer")
    seite.wait_for_function("document.querySelector('#rechts-inhalt [data-leer]') !== null")
    waehle(seite, "judge", "actions")                                # hinter mehreren Tab-Pfeilen
    r = seite.evaluate("""() => {
      const pre = document.getElementById('rechts-inhalt'), rg = getSelection().getRangeAt(0);
      const von = Chunkansicht.offsetIn(pre, rg.startContainer, rg.startOffset), bis = Chunkansicht.offsetIn(pre, rg.endContainer, rg.endOffset);
      const t = ansichtCache.get(gezeigterChunk).ansicht.text;
      return {text: t.slice(von, bis), a: Chunkansicht.auswahlAbbilden(ansichtCache.get(gezeigterChunk).ansicht, von, bis)};
    }""")
    assert r["text"] == "judge\tthe\tactions" and r["a"]["text"] == "judge\tthe\tactions"


def test_hinweis_ganze_zeilen(seite):
    zu_chunk(seite, 1)
    waehle(seite, "people", "judge")
    assert "ganze Zeilen" in seite.locator(".werkzeug-status").inner_text()


def test_stale_ansicht_wird_nicht_gespeichert(seite):
    zu_chunk(seite, 1)
    waehle(seite, "Representation", "judge")
    seite.evaluate("ansichtCache.get(gezeigterChunk).sig = 'alt'")
    knopf(seite, "markieren").click()
    seite.wait_for_timeout(300)
    assert eintraege(seite) == []
