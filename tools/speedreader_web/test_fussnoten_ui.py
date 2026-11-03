"""Browserpruefung "Fussnote zuordnen" (P2 Task 12) bei 960x600: Marker und Fussnotentexte im Modus "Bereinigt"
sind antippbar, Dialog #fussnote-zuordnen legt Eintraege der Art "fussnote" an. Ohne Playwright/Chromium uebersprungen."""
import json
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent))

sync_api = pytest.importorskip("playwright.sync_api")

from test_werkzeugleiste import browser  # noqa: E402,F401
from test_neu_uebersetzen import Apic, neue_seite  # noqa: E402
from test_volltext import DATEI, baue, text_im_feld, zu_text, tippe  # noqa: E402

KAP = ("# Kapitel\n\nErster Satz mit Verweis[^1] und noch einer Aussage[^2] hier.\n\n"
       "Zweiter Absatz ohne Verweis hier.\n\n[^1]: Erste Note gehört zu eins.\n[^3]: Dritte Note ohne Verweis.")


@pytest.fixture()
def seite(browser, tmp_path):
    a = Apic(baue(tmp_path, kapitel=KAP))
    ctx, pg = neue_seite(browser, a.url)
    zu_text(pg)
    yield pg
    ctx.close()
    a.stop()
    assert not pg.fehler, pg.fehler


def eintraege(pg):
    return pg.evaluate("eintraege.map(e => ({ebene: e.ebene, art: e.art, ziel: e.ziel, parameter: e.parameter}))")


def tippe_fn(pg, selektor, nr):
    pg.locator(f"#rechts-inhalt {selektor}").nth(nr).click()
    pg.wait_for_selector("#fussnote-zuordnen[open]")


def waehle(pg, text):
    pg.locator("#fn-liste button", has_text=text).first.click()


def test_marker_und_texte_sind_antippbar_ohne_den_text_zu_aendern(seite):
    assert seite.locator("#rechts-inhalt .fn-marker").count() == 2
    assert seite.locator("#rechts-inhalt .fn-def").count() == 2
    assert text_im_feld(seite) == KAP
    # Waisen sind markiert: Marker [^2] ohne Text, Text [^3] ohne Verweis
    assert seite.locator("#rechts-inhalt .fn-marker.fn-orphan").inner_text() == "[^2]"
    assert seite.locator("#rechts-inhalt .fn-def.fn-orphan").inner_text() == "[^3]:"
    for sel in (".fn-marker", ".fn-def"):
        assert seite.locator(f"#rechts-inhalt {sel}").first.bounding_box()["height"] >= 44, sel     # Trefferfläche


def test_dekoration_bleibt_bei_sichtbaren_steuerzeichen_erhalten(seite):
    seite.locator("#steuer").click()
    assert seite.locator("#rechts-inhalt .fn-marker").count() == 2 and seite.locator("#rechts-inhalt .fn-def").count() == 2
    assert seite.evaluate("document.querySelectorAll('#rechts-inhalt [data-leer]').length") >= 0
    seite.locator("#steuer").click()


def test_marker_antippen_zeigt_waisen_zuerst_und_zuordnen_benennt_den_text_um(seite):
    tippe_fn(seite, ".fn-marker", 1)                                            # [^2]
    assert "[^2]" in seite.inner_text("#fn-titel")
    kandidaten = seite.locator("#fn-liste button").all_inner_texts()
    assert "[^3]" in kandidaten[0] and "ohne Verweis" in kandidaten[0]           # Waise zuerst
    waehle(seite, "[^3]")
    seite.locator("#fn-zuordnen").click()
    seite.wait_for_function("eintraege.length === 1")
    (e,) = eintraege(seite)
    assert (e["ebene"], e["art"]) == ("volltext", "fussnote")
    assert e["parameter"] == {"aktion": "definition-umbenennen", "alt": "3", "neu": "2"}
    assert e["ziel"]["datei"] == DATEI and e["ziel"]["zeile"] == 1 and e["ziel"]["absatz_index"] == 3
    assert text_im_feld(seite) == KAP.replace("[^3]: Dritte", "[^2]: Dritte")
    seite.wait_for_function("!document.getElementById('fussnote-zuordnen').open")
    assert "Fußnoten: 0 Hinweise" in seite.inner_text("#rechts-verdacht")


def test_verweis_umbenennen_ist_die_alternative(seite):
    tippe_fn(seite, ".fn-marker", 1)
    waehle(seite, "[^3]")
    seite.locator("#fn-umbenennen").click()
    seite.wait_for_function("eintraege.length === 1")
    (e,) = eintraege(seite)
    assert e["parameter"] == {"aktion": "marker-umbenennen", "alt": "2", "neu": "3", "vorkommen": 0}
    assert text_im_feld(seite) == KAP.replace("Aussage[^2]", "Aussage[^3]")


def test_belegte_kennung_sperrt_das_umbenennen_des_textes(seite):
    tippe_fn(seite, ".fn-marker", 0)                                            # [^1] hat schon einen Text
    waehle(seite, "[^3]")
    assert seite.locator("#fn-zuordnen").is_disabled()
    assert "schon" in seite.inner_text("#fn-meldung") and "[^1]" in seite.inner_text("#fn-meldung")
    assert seite.locator("#fn-umbenennen").is_enabled()
    assert seite.evaluate("eintraege.length") == 0


def test_eigener_text_ist_schon_zugeordnet(seite):
    tippe_fn(seite, ".fn-marker", 0)
    waehle(seite, "[^1]")
    assert "schon zugeordnet" in seite.inner_text("#fn-meldung").lower()
    assert seite.locator("#fn-zuordnen").is_hidden() and seite.locator("#fn-umbenennen").is_hidden()


def test_text_antippen_bietet_die_verweise_an(seite):
    tippe_fn(seite, ".fn-def", 1)                                               # [^3]: Dritte Note …
    assert "[^3]" in seite.inner_text("#fn-titel")
    kandidaten = seite.locator("#fn-liste button").all_inner_texts()
    assert "[^2]" in kandidaten[0] and "ohne Text" in kandidaten[0]              # Waise zuerst
    waehle(seite, "[^2]")
    seite.locator("#fn-zuordnen").click()
    seite.wait_for_function("eintraege.length === 1")
    assert eintraege(seite)[0]["parameter"] == {"aktion": "definition-umbenennen", "alt": "3", "neu": "2"}


def test_verweis_entfernen(seite):
    tippe_fn(seite, ".fn-marker", 1)
    seite.locator("#fn-entfernen").click()
    seite.wait_for_function("eintraege.length === 1")
    (e,) = eintraege(seite)
    assert e["parameter"] == {"aktion": "marker-entfernen", "id": "2", "vorkommen": 0}
    assert "Aussage hier" in text_im_feld(seite) and "[^2]" not in text_im_feld(seite)


def test_ruecknahme_stellt_den_text_wieder_her(seite):
    tippe_fn(seite, ".fn-marker", 1)
    waehle(seite, "[^3]")
    seite.locator("#fn-zuordnen").click()
    seite.wait_for_function("eintraege.length === 1")
    seite.evaluate("nimmZurueck(eintraege[0].id)")
    seite.wait_for_function("document.getElementById('rechts-inhalt').textContent.includes('[^3]: Dritte')")
    assert text_im_feld(seite) == KAP


def test_verweis_setzen_aus_der_absatzleiste(seite):
    tippe(seite, "ohne Verweis hier")                                           # Absatz 3: Zeiger hinter dem ersten Zeichen der Fundstelle
    assert seite.locator("#absatz-verweis").is_visible()
    seite.locator("#absatz-verweis").click()
    seite.wait_for_selector("#fussnote-zuordnen[open]")
    assert "[^3]" in seite.locator("#fn-liste button").all_inner_texts()[0]     # unbezogener Text zuerst
    waehle(seite, "[^3]")
    seite.locator("#fn-setzen").click()
    seite.wait_for_function("eintraege.length === 1")
    (e,) = eintraege(seite)
    assert e["parameter"]["aktion"] == "marker-setzen" and e["parameter"]["id"] == "3"
    assert len(e["parameter"]["nach"]) >= 8 and "Zweiter Absatz o" in e["parameter"]["nach"]
    assert text_im_feld(seite) == KAP.replace("Zweiter Absatz ohne", "Zweiter Absatz o[^3]hne")
    assert "Fußnoten: 1 Hinweis" in seite.inner_text("#rechts-verdacht")           # [^2] hat weiterhin keinen Text
    assert seite.locator("#rechts-inhalt .fn-def.fn-orphan").count() == 0          # [^3] ist jetzt verwiesen


def test_verweis_setzen_zu_wenig_kontext_meldet_ehrlich(seite):
    tippe(seite, "Zweiter")                                                     # Zeiger nach dem 1. Zeichen: weniger als 8 Zeichen davor
    seite.locator("#absatz-verweis").click()
    seite.wait_for_selector("#fussnote-zuordnen[open]")
    waehle(seite, "[^3]")
    seite.locator("#fn-setzen").click()
    assert "mindestens 8" in seite.inner_text("#fn-meldung")
    assert seite.evaluate("eintraege.length") == 0
