"""Browserpruefung "Ursache suchen" (P2 Task 13) bei 960x600: vom Absatz im Volltext zum Chunk. Ohne Playwright/Chromium uebersprungen."""
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
from test_volltext import baue, zu_text, tippe  # noqa: E402
from redaktion.testwurzel import DEUTSCH  # noqa: E402

# Absatz 1 steht (mit Fußnotenmarker) in Chunk 0 der Übersetzung, Absatz 2 in Chunk 1, Absatz 3 nirgends
KAPITEL = ("# Erstes Kapitel\n\n"
           "Der Repräsentant[^1] ist nicht bloß ein Delegierter der Wähler, wie Pitkin in ihrer Studie betonte, dass die Abgeordneten ihr Urteil nicht bloß weitergeben.\n\n"
           "Repräsentation erfordert Distanz und Responsivität, damit das Volk das Handeln derer beurteilen kann, die in seinem Namen handeln.\n\n"
           "Dieser Absatz steht in keinem Chunk und wurde frei erfunden von jemandem.\n\n[^1]: Eine Note.")


@pytest.fixture()
def seite(browser, tmp_path):
    a = Apic(baue(tmp_path, kapitel=KAPITEL))
    ctx, pg = neue_seite(browser, a.url)
    zu_text(pg)
    yield pg
    ctx.close()
    a.stop()
    assert not pg.fehler, pg.fehler


def hervorgehoben(pg):
    return pg.evaluate("""() => { const h = CSS.highlights.get('ursache'); if (!h || !h.size) return null;
      return [...h][0].toString(); }""")


def suche(pg, nadel):
    tippe(pg, nadel)
    assert pg.locator("#absatz-ursache").is_visible()
    pg.locator("#absatz-ursache").click()


def test_eindeutig_springt_in_die_uebersetzung_und_hebt_die_stelle_hervor(seite):
    suche(seite, "Der Repr")
    seite.wait_for_function("modus === 'uebersetzung' && gezeigteSig !== null")
    assert seite.evaluate("uebersetzungsIndex(pos.chunk)") == 0
    assert seite.evaluate("document.getElementById('uebersetzung-titel').textContent").startswith("Übersetzung (de) · Chunk 0")
    assert hervorgehoben(seite).startswith("Der Repräsentant ist nicht bloß ein")
    assert seite.evaluate("eintraege.length") == 0                               # sucht nur, ändert nichts


def test_zweiter_absatz_fuehrt_zu_chunk_1(seite):
    suche(seite, "Repräsentation erfordert")
    seite.wait_for_function("modus === 'uebersetzung' && gezeigteSig !== null")
    assert seite.evaluate("uebersetzungsIndex(pos.chunk)") == 1
    assert hervorgehoben(seite).startswith("Repräsentation erfordert Distanz")


def test_keine_stelle_wird_ehrlich_gemeldet_und_nichts_wechselt(seite):
    suche(seite, "Dieser Absatz steht")
    assert "Keine eindeutige Stelle" in seite.inner_text("#absatz-leiste")
    assert seite.evaluate("modus") == "text"


def test_mehrdeutig_zeigt_kandidaten_zur_auswahl(seite):
    seite.evaluate("() => { daten.uebersetzung[2] = daten.uebersetzung[0]; }")     # derselbe Satz in zwei Chunks
    suche(seite, "Der Repr")
    seite.wait_for_selector("#ursache-dialog[open]")
    kandidaten = seite.locator("#ursache-liste button").all_inner_texts()
    assert len(kandidaten) == 2 and "Chunk 0" in kandidaten[0] and "Chunk 2" in kandidaten[1]
    assert seite.evaluate("modus") == "text"                                       # nichts geraten
    seite.locator("#ursache-liste button").nth(1).click()
    seite.wait_for_function("modus === 'uebersetzung' && gezeigteSig !== null")
    assert seite.evaluate("uebersetzungsIndex(pos.chunk)") == 2
    assert seite.evaluate("!document.getElementById('ursache-dialog').open")


def test_deutsche_quelle_springt_in_die_rohchunks(seite):
    seite.evaluate("""(chunks) => { buch.uebersetzung = 0; daten.uebersetzung = []; daten.chunks = chunks; zeigeRechts(); }""", DEUTSCH)
    suche(seite, "Repräsentation erfordert")
    seite.wait_for_function("modus === 'chunks' && gezeigteSig !== null")
    assert seite.evaluate("pos.chunk") == 1
    assert hervorgehoben(seite).startswith("Repräsentation erfordert Distanz")


def test_knopf_nur_wenn_chunks_vorhanden_und_ziele_gross_genug(seite):
    tippe(seite, "Der Repr")
    box = seite.locator("#absatz-ursache").bounding_box()
    assert box["height"] >= 44 and box["width"] >= 44


def test_ohne_chunks_kein_knopf(browser, tmp_path):
    a = Apic(baue(tmp_path, kapitel=KAPITEL))
    try:
        ctx, pg = neue_seite(browser, a.url)
        zu_text(pg)
        pg.evaluate("() => { buch.chunks = 0; buch.uebersetzung = 0; daten.chunks = []; daten.uebersetzung = []; }")
        tippe(pg, "Der Repr")
        assert pg.locator("#absatz-ursache").is_hidden()
        ctx.close()
    finally:
        a.stop()


def test_suche_ist_auf_das_kapitel_begrenzt_wenn_segmente_passen(seite):
    """Gleich viele Kapitelgrenzen wie Kapitel: Treffer ausserhalb des Chunk-Bereichs des Kapitels zaehlen nicht mit."""
    erg = seite.evaluate("""() => { buch.kapitel = buch.kapitel.concat([{ nr: 2, titel: 'Zweites' }]);   // Testwurzel: 2 Grenzen
      daten.uebersetzung[3] = daten.uebersetzung[0]; buch.uebersetzung = 4;                           // derselbe Satz hinter dem Kapitel
      return { bereich: ursacheBereich(0), letzter: ursacheBereich(1) }; }""")
    assert erg["bereich"] == [0, 2] and erg["letzter"][0] == 2
    suche(seite, "Der Repr")
    seite.wait_for_function("modus === 'uebersetzung' && gezeigteSig !== null")      # eindeutig: Chunk 3 liegt ausserhalb
    assert seite.evaluate("uebersetzungsIndex(pos.chunk)") == 0


def test_ausserhalb_des_bereichs_gefundenes_wird_nur_zur_auswahl_angeboten(seite):
    seite.evaluate("""() => { buch.kapitel = buch.kapitel.concat([{ nr: 2, titel: 'Zweites' }]);
      daten.uebersetzung[0] = 'ganz anderer Text'; daten.uebersetzung[3] = 'Der Repräsentant ist nicht bloß ein Delegierter der Wähler, wie Pitkin in ihrer Studie betonte, dass die Abgeordneten ihr Urteil nicht bloß weitergeben.';
      buch.uebersetzung = 4; }""")
    suche(seite, "Der Repr")
    seite.wait_for_selector("#ursache-dialog[open]")
    assert "außerhalb" in seite.inner_text("#ursache-dialog").lower()
    assert seite.evaluate("modus") == "text"
