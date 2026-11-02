"""Browserpruefung der Volltext-Ansicht (P2 Task 9) bei 960x600: Modus "Bereinigt" mit Eintraegen der Ebene
"volltext", Fussnotenhinweisen und Stand angewendeter Aenderungen (`enthalten`).

Baut je Test eine Testwurzel mit einem Kapitel mit Fussnoten, startet den echten Empfaenger und liefert die App
daraus aus. Ohne Playwright/Chromium uebersprungen."""
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

import export_korrektur  # noqa: E402
from redaktion import protokoll  # noqa: E402
from redaktion.testwurzel import AUTOR, TITEL, baue_testwurzel  # noqa: E402

DATEI = "0001_erstes-kapitel.md"
KAPITEL = ("# Erstes Kapitel\n\nDer Repräsentant[^1] ist nicht bloß Delegierter[^2], wie Pitkin betonte.\n\n"
           "Ein zweiter Absatz folgt hier.\n\n[^1]: Erste Note.")
BUCH = f"{AUTOR}/{TITEL}"


def baue(tmp_path, kapitel=KAPITEL, redaktion=None):
    root = baue_testwurzel(tmp_path / "wurzel")
    buch = root / "reader" / AUTOR / TITEL
    (buch / "quelle" / DATEI).write_bytes(kapitel.encode("utf-8"))
    if redaktion is not None:
        (buch / "notizen").mkdir(exist_ok=True)
        (buch / "notizen" / "redaktion.json").write_text(json.dumps(redaktion), encoding="utf-8")
    export_korrektur.exportiere(root, root / "reader" / "export-epistopheles" / "korrektur",
                                root / "rohdaten" / "Lektor", ebooks=False)
    return root


@pytest.fixture()
def apic(tmp_path):
    a = Apic(baue(tmp_path))
    yield a
    a.stop()


def zu_text(pg):
    pg.locator("#modus-text").click()
    pg.wait_for_function("modus === 'text' && gezeigteSig !== null")


@pytest.fixture()
def seite(browser, apic):
    ctx, pg = neue_seite(browser, apic.url)
    zu_text(pg)
    yield pg
    ctx.close()
    assert not pg.fehler, pg.fehler


def test_kapitel_zeigt_fussnotenhinweis_und_text_bleibt_unveraendert(seite):
    assert seite.locator("#rechts-inhalt .verdacht").count() == 1
    assert seite.locator("#rechts-inhalt button.chip").count() == 1
    assert "Fußnoten: 1 Hinweis" in seite.inner_text("#rechts-verdacht")
    assert seite.evaluate("document.getElementById('rechts-inhalt').textContent") == KAPITEL        # Chips tragen keinen Text
    assert seite.evaluate("document.getElementById('rechts-wahl').options[0].textContent").startswith("● ")
    assert seite.evaluate("daten.kapitel[0].datei") == DATEI


def test_markieren_legt_volltext_eintrag_mit_datei_an_und_hinweis_verschwindet(seite):
    seite.locator("#rechts-inhalt button.chip").click()
    seite.locator("#rechts-inhalt .verdacht-leiste button[data-aktion='markieren']").click()
    seite.wait_for_function("eintraege.length === 1")
    e = seite.evaluate("eintraege[0]")
    assert (e["ebene"], e["art"], e["buch"]) == ("volltext", "marke", BUCH)
    assert e["ziel"]["datei"] == DATEI and e["ziel"]["absatz_index"] == 1 and "chunk" not in e["ziel"]
    assert e["parameter"] == {"kategorie": "fussnote"}
    seite.wait_for_function("document.querySelectorAll('#rechts-inhalt button.chip').length === 0")
    assert "Fußnoten: 0 Hinweise" in seite.inner_text("#rechts-verdacht")
    assert seite.evaluate("window.Redaktion.zaehler(eintraege).markierungen") == 1


def test_ablehnen_bleibt_nach_neuladen_verschwunden(seite):
    seite.locator("#rechts-inhalt button.chip").click()
    seite.locator("#rechts-inhalt .verdacht-leiste button[data-aktion='ablehnen']").click()
    seite.wait_for_function("document.querySelectorAll('#rechts-inhalt button.chip').length === 0")
    seite.reload()
    seite.wait_for_function("typeof buch !== 'undefined' && buch && eintraegeBuchId === buch.id")
    zu_text(seite)
    assert seite.locator("#rechts-inhalt .verdacht").count() == 0
    assert seite.evaluate("eintraege.length") == 0                           # ablehnen ändert keine Daten


def test_chunk_ansicht_sieht_volltext_eintraege_nicht(seite):
    seite.locator("#rechts-inhalt button.chip").click()
    seite.locator("#rechts-inhalt .verdacht-leiste button[data-aktion='markieren']").click()
    seite.wait_for_function("eintraege.length === 1")
    seite.locator("#modus-chunks").click()
    seite.wait_for_function("modus === 'chunks' && gezeigteSig !== null")
    assert "Verdacht:" in seite.inner_text("#rechts-verdacht")
    assert seite.evaluate("ansichtCache.get(gezeigterChunk).ansicht.markierungen.length") == 0


def eintrag_im_browser(pg, art, parameter, status, ziel_extra=None):
    """Legt einen Volltext-Eintrag auf dem Absatz 1 direkt im Speicher der Seite an (wie ihn APIC zurückmeldet)."""
    return pg.evaluate("""async ([art, parameter, status]) => {
      const R = window.Redaktion, a = R.absatzSpannen(daten.kapitel[0].text)[1];
      const absatz = daten.kapitel[0].text.slice(a[0], a[1]);
      const e = Object.assign(R.neuerEintrag(buchSchluessel(buch), 'volltext',
        { datei: daten.kapitel[0].datei, anfang: R.ankerVon(absatz), absatz_index: 1 }, art, parameter, absatz, '', 't'), { status: status });
      await aendereEintraege(buch.id, (liste) => liste.concat([e]));
      return e.id;
    }""", [art, parameter, status])


UMBENENNEN = {"aktion": "marker-umbenennen", "alt": "2", "neu": "7", "vorkommen": 0}


def text_im_feld(pg):
    return pg.evaluate("document.getElementById('rechts-inhalt').textContent")


def test_offener_eintrag_wird_abgespielt(seite):
    eintrag_im_browser(seite, "fussnote", UMBENENNEN, "offen")
    seite.wait_for_function("document.getElementById('rechts-inhalt').textContent.includes('Delegierter[^7]')")
    assert text_im_feld(seite) == KAPITEL.replace("Delegierter[^2]", "Delegierter[^7]")
    assert seite.locator("#rechts-inhalt button.chip").count() == 1              # [^7] hat weiter keinen Fußnotentext


def test_angewendet_und_nicht_im_export_wird_abgespielt_sonst_nicht(seite):
    """Review Focus 5: der Export ist älter als die Einarbeitung am PC."""
    eid = eintrag_im_browser(seite, "fussnote", UMBENENNEN, "angewendet")
    seite.wait_for_function("document.getElementById('rechts-inhalt').textContent.includes('Delegierter[^7]')")
    assert text_im_feld(seite) == KAPITEL.replace("Delegierter[^2]", "Delegierter[^7]")
    assert "Neuer Export nötig" not in seite.inner_text("#aenderungen-hinweis")        # Volltext wird kompensiert
    # Export enthält den Eintrag inzwischen: Text im Export schon [^7], nichts wird doppelt angewendet
    seite.evaluate("""(id) => { daten.kapitel[0].text = daten.kapitel[0].text.replace('Delegierter[^2]', 'Delegierter[^7]');
      daten.enthalten.push(id); daten._enthaltenSet = null; kapitelCache.clear(); zeigeRechts(); }""", eid)
    assert text_im_feld(seite) == KAPITEL.replace("Delegierter[^2]", "Delegierter[^7]")
    assert seite.evaluate("kapitelCache.get(0).ansicht.luecke.length") == 0
    assert seite.evaluate("kapitelCache.get(0).ansicht.konflikte.length") == 0


def test_folgekorrektur_auf_veraltetem_export_hat_passenden_vorzustand(seite):
    """Eintrag A am PC angewendet (Export alt), Eintrag B baut darauf auf: B ist abspielbar, kein Konflikt."""
    eintrag_im_browser(seite, "fussnote", UMBENENNEN, "angewendet")
    seite.wait_for_function("document.getElementById('rechts-inhalt').textContent.includes('Delegierter[^7]')")
    seite.evaluate("""async () => {
      const R = window.Redaktion, t = kapitelCache.get(0).ansicht, a = t.spannen[1], absatz = t.text.slice(a[0], a[1]);
      const e = Object.assign(R.neuerEintrag(buchSchluessel(buch), 'volltext', { datei: daten.kapitel[0].datei, anfang: R.ankerVon(absatz), absatz_index: 1 },
        'fussnote', { aktion: 'marker-umbenennen', alt: '7', neu: '1', vorkommen: 0 }, absatz, '', 't'), { status: 'offen' });
      await aendereEintraege(buch.id, (liste) => liste.concat([e]));
    }""")
    seite.wait_for_function("document.getElementById('rechts-inhalt').textContent.includes('Delegierter[^1]')")
    assert seite.evaluate("kapitelCache.get(0).ansicht.konflikte.length") == 0


def test_konflikt_wird_am_absatz_gezeigt(seite):
    eid = eintrag_im_browser(seite, "fussnote", UMBENENNEN, "offen")
    seite.evaluate("""async (id) => { await aendereEintraege(buch.id, (l) => l.map((e) => e.id === id ? Object.assign({}, e, { status: 'konflikt', grund: 'Absatz geändert' }) : e)); }""", eid)
    seite.wait_for_selector("#rechts-inhalt .konflikt")
    assert "Fußnoten: 1 Hinweis · 1 Konflikt" in seite.inner_text("#rechts-verdacht")


def test_aenderungsliste_nennt_kapitel_und_springt_in_den_volltext(seite):
    eintrag_im_browser(seite, "fussnote", UMBENENNEN, "offen")
    seite.locator("#modus-chunks").click()
    seite.wait_for_function("modus === 'chunks'")
    seite.locator("#aenderungen-liste-knopf").click()
    li = seite.locator("#aenderungsliste-inhalt li.aenderung").first
    assert "Kapitel 1" in li.inner_text() and "Fußnote geändert" in li.inner_text()
    li.locator("button[data-aktion='springen']").click()
    seite.wait_for_function("modus === 'text' && gezeigteSig !== null")
    assert not seite.locator("#aenderungsliste").evaluate("d => d.open")


def test_altes_datenpaket_sperrt_das_bearbeiten_und_zeigt_den_text_unveraendert(browser, tmp_path):
    root = baue(tmp_path)
    f = root / "reader" / "export-epistopheles" / "korrektur" / "k001.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    for k in d["kapitel"]:
        k.pop("datei", None)
    d.pop("enthalten", None)
    f.write_text(json.dumps(d), encoding="utf-8")
    a = Apic(root)
    try:
        ctx, pg = neue_seite(browser, a.url)
        pg.locator("#modus-text").click()
        pg.wait_for_function("modus === 'text'")
        pg.wait_for_function("document.getElementById('rechts-verdacht').textContent.includes('Daten neu exportieren')")
        assert pg.locator("#rechts-inhalt .verdacht").count() == 0
        assert pg.evaluate("document.getElementById('rechts-inhalt').textContent") == KAPITEL
        ctx.close()
        assert not pg.fehler, pg.fehler
    finally:
        a.stop()
