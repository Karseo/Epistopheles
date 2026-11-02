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


# --- P2 Task 10: Absatz bearbeiten -------------------------------------------------------------------------

JS_TIPPE = """(nadel) => {
  const pre = document.getElementById('rechts-inhalt');
  const w = document.createTreeWalker(pre, NodeFilter.SHOW_TEXT);
  let t;
  while ((t = w.nextNode())) {
    const i = t.data.indexOf(nadel);
    if (i >= 0) {
      const r = document.createRange(); r.setStart(t, i + 1); r.collapse(true);
      const s = getSelection(); s.removeAllRanges(); s.addRange(r);
      pre.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      return true;
    }
  }
  throw new Error('nicht gefunden: ' + nadel);
}"""

ZWEITER = "Ein zweiter Absatz folgt hier."


def tippe(pg, nadel):
    pg.evaluate(JS_TIPPE, nadel)


def bearbeite(pg, nadel, neu):
    """Absatz antippen, Bearbeiten, Text setzen (noch nicht speichern)."""
    tippe(pg, nadel)
    pg.locator("#absatz-leiste:not([hidden]) #absatz-bearbeiten").click()
    pg.wait_for_selector("#absatz-dialog[open]")
    pg.locator("#absatz-editor").fill(neu)


def speichern(pg):
    pg.locator("#absatz-speichern").click()


def test_antippen_zeigt_leiste_und_bearbeiten_oeffnet_den_absatz(seite):
    assert seite.locator("#absatz-leiste").is_hidden()
    tippe(seite, ZWEITER)
    assert seite.locator("#absatz-leiste").is_visible()
    assert "Absatz 3" in seite.inner_text("#absatz-leiste")
    seite.locator("#absatz-bearbeiten").click()
    seite.wait_for_selector("#absatz-dialog[open]")
    assert seite.input_value("#absatz-editor") == ZWEITER
    for sel in ("#absatz-speichern", "#absatz-abbrechen", "#absatz-bearbeiten"):
        box = seite.locator(sel).bounding_box()
        assert box["height"] >= 44 and box["width"] >= 44, sel


def test_speichern_legt_ersetzen_eintrag_mit_vorher_hash_an_und_text_ist_sofort_sichtbar(seite):
    bearbeite(seite, ZWEITER, "Ein zweiter Absatz folgt dort.")
    speichern(seite)
    seite.wait_for_function("eintraege.length === 1")
    e = seite.evaluate("eintraege[0]")
    assert (e["ebene"], e["art"], e["buch"]) == ("volltext", "ersetzen", BUCH)
    assert e["parameter"] == {"nachher": "Ein zweiter Absatz folgt dort."}
    assert e["ziel"] == {"datei": DATEI, "anfang": "Ein zweiter Absatz folgt hier.", "absatz_index": 2}
    assert e["vorher"]["hash"] == seite.evaluate(f"window.Redaktion.pruefsumme({json.dumps(ZWEITER)})")
    seite.wait_for_function("!document.getElementById('absatz-dialog').open")
    assert text_im_feld(seite) == KAPITEL.replace("hier.\n\n[^1]", "dort.\n\n[^1]")
    assert seite.locator("#absatz-leiste").is_hidden()
    assert seite.evaluate("window.Redaktion.zaehler(eintraege).aenderungen") == 1


def test_unveraenderter_text_erzeugt_keinen_eintrag(seite):
    bearbeite(seite, ZWEITER, ZWEITER)
    speichern(seite)
    assert "Keine Änderung" in seite.inner_text("#absatz-warnung")
    assert seite.evaluate("eintraege.length") == 0
    assert seite.evaluate("document.getElementById('absatz-dialog').open")


def test_leerzeile_und_leerer_text_werden_abgewiesen(seite):
    bearbeite(seite, ZWEITER, "Erster Teil.\n\nZweiter Teil.")
    speichern(seite)
    assert "Leerzeile" in seite.inner_text("#absatz-warnung") and "trennen" in seite.inner_text("#absatz-warnung")
    seite.locator("#absatz-editor").fill("   ")
    speichern(seite)
    assert "leer" in seite.inner_text("#absatz-warnung")
    assert seite.evaluate("eintraege.length") == 0


def test_fussnotenverweis_entfernt_warnt_und_braucht_zweite_bestaetigung(seite):
    ALT = "Der Repräsentant[^1] ist nicht bloß Delegierter[^2], wie Pitkin betonte."
    bearbeite(seite, "Der Repr", ALT.replace("[^2]", ""))
    speichern(seite)
    warn = seite.inner_text("#absatz-warnung")
    assert "[^2]" in warn and "1 → 0" in warn
    assert seite.evaluate("eintraege.length") == 0                                  # noch nichts gespeichert
    assert seite.inner_text("#absatz-speichern") == "Trotzdem speichern"
    seite.locator("#absatz-abbrechen").click()
    seite.wait_for_function("!document.getElementById('absatz-dialog').open")
    assert seite.evaluate("eintraege.length") == 0
    bearbeite(seite, "Der Repr", ALT.replace("[^2]", ""))                          # nochmal: jetzt bestätigen
    speichern(seite)
    speichern(seite)
    seite.wait_for_function("eintraege.length === 1")
    assert "[^2]" not in text_im_feld(seite).split("\n\n")[1]


def test_aendern_des_textes_nach_der_warnung_verlangt_die_bestaetigung_neu(seite):
    ALT = "Der Repräsentant[^1] ist nicht bloß Delegierter[^2], wie Pitkin betonte."
    bearbeite(seite, "Der Repr", ALT.replace("[^2]", ""))
    speichern(seite)
    assert seite.inner_text("#absatz-speichern") == "Trotzdem speichern"
    seite.locator("#absatz-editor").fill(ALT.replace("Delegierter[^2]", "Delegierter"))
    assert seite.inner_text("#absatz-speichern") == "Speichern" and seite.locator("#absatz-warnung").is_hidden()


def test_zwei_aenderungen_am_selben_absatz_bauen_aufeinander_auf(seite):
    bearbeite(seite, ZWEITER, "Ein zweiter Absatz folgt dort.")
    speichern(seite)
    seite.wait_for_function("eintraege.length === 1")
    bearbeite(seite, "Ein zweiter Absatz folgt dort.", "Ein zweiter Absatz folgt überall.")
    speichern(seite)
    seite.wait_for_function("eintraege.length === 2")
    erg = seite.evaluate("""() => { const R = window.Redaktion, [a, b] = eintraege;
      const l = R.spieleAb(daten.kapitel[0].text, eintraege);
      return { hashB: b.vorher.hash === R.pruefsumme(a.parameter.nachher), stati: l.ergebnisse.map((e) => e.status), text: l.text }; }""")
    assert erg["hashB"] and erg["stati"] == ["angewendet", "angewendet"]
    assert erg["text"] == KAPITEL.replace("hier.\n\n[^1]", "überall.\n\n[^1]")


def test_abbrechen_und_escape_aendern_nichts(seite):
    bearbeite(seite, ZWEITER, "Ganz anders.")
    seite.locator("#absatz-abbrechen").click()
    seite.wait_for_function("!document.getElementById('absatz-dialog').open")
    bearbeite(seite, ZWEITER, "Ganz anders.")
    seite.keyboard.press("Escape")
    seite.wait_for_function("!document.getElementById('absatz-dialog').open")
    assert seite.evaluate("eintraege.length") == 0 and text_im_feld(seite) == KAPITEL


def test_tippen_auf_leerraum_oder_chip_zeigt_keine_leiste(seite):
    seite.evaluate("""() => { const pre = document.getElementById('rechts-inhalt'), r = document.createRange();
      r.setStart(pre.firstChild, pre.firstChild.data.indexOf('\\n\\n') + 1); r.collapse(true);
      const s = getSelection(); s.removeAllRanges(); s.addRange(r); pre.dispatchEvent(new MouseEvent('click', { bubbles: true })); }""")
    assert seite.locator("#absatz-leiste").is_hidden()


def test_crlf_absatz_mehrzeilig_bearbeitet_bleibt_crlf_und_rest_byteidentisch(browser, tmp_path):
    kapitel = "# Titel\r\n\r\nErste Zeile\tmit Tab\r\nzweite Zeile\r\n\r\nSchluss ohne Newline"
    a = Apic(baue(tmp_path, kapitel=kapitel))
    try:
        ctx, pg = neue_seite(browser, a.url)
        zu_text(pg)
        bearbeite(pg, "Erste Zeile", "Neue erste Zeile\tmit Tab\nneue zweite Zeile")
        speichern(pg)
        pg.wait_for_function("eintraege.length === 1")
        text = pg.evaluate("window.Redaktion.spieleAb(daten.kapitel[0].text, eintraege).text")
        assert text == "# Titel\r\n\r\nNeue erste Zeile\tmit Tab\r\nneue zweite Zeile\r\n\r\nSchluss ohne Newline"
        ctx.close()
        assert not pg.fehler, pg.fehler
    finally:
        a.stop()


def test_altes_datenpaket_zeigt_keine_leiste(browser, tmp_path):
    root = baue(tmp_path)
    f = root / "reader" / "export-epistopheles" / "korrektur" / "k001.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    d.pop("enthalten", None)
    f.write_text(json.dumps(d), encoding="utf-8")
    a = Apic(root)
    try:
        ctx, pg = neue_seite(browser, a.url)
        pg.locator("#modus-text").click()
        pg.wait_for_function("modus === 'text'")
        tippe(pg, ZWEITER)
        assert pg.locator("#absatz-leiste").is_hidden()
        ctx.close()
    finally:
        a.stop()


# --- P2 Task 11: Strukturwerkzeuge im Volltext -------------------------------------------------------------

from test_werkzeugleiste import knopf, waehle, leiste_offen, zu_chunk  # noqa: E402

UMBRUCH = ("# Titel\n\nErste Zeile bricht\nmitten im Satz ab und\nsetzt sich fort.\n\nZweiter Absatz folgt hier.\n\n"
           "Dritter Absatz folgt dort.\n\n[^1]: Eine Note.")


@pytest.fixture()
def seite_umbruch(browser, tmp_path):
    a = Apic(baue(tmp_path, kapitel=UMBRUCH))
    ctx, pg = neue_seite(browser, a.url)
    zu_text(pg)
    yield pg
    ctx.close()
    a.stop()
    assert not pg.fehler, pg.fehler


def eintrag_liste(pg):
    return pg.evaluate("eintraege.map(e => ({ebene: e.ebene, art: e.art, ziel: e.ziel, parameter: e.parameter}))")


def test_werkzeugleiste_erscheint_im_volltext_ohne_kapitel_verzeichnis_glossar(seite_umbruch):
    pg = seite_umbruch
    assert not leiste_offen(pg)
    waehle(pg, "Erste Zeile", "setzt sich")
    assert leiste_offen(pg)
    for was in ("verbinden", "verschieben", "loeschen", "trennen", "markieren"):
        assert knopf(pg, was).is_visible(), was
        assert knopf(pg, was).bounding_box()["height"] >= 44, was
    for was in ("kapitel", "verzeichnis", "glossar"):
        assert knopf(pg, was).is_hidden(), was


def test_zeilen_verbinden_im_volltext(seite_umbruch):
    pg = seite_umbruch
    waehle(pg, "Erste Zeile", "mitten im")
    knopf(pg, "verbinden").click()
    pg.wait_for_function("eintraege.length === 1")
    (e,) = eintrag_liste(pg)
    assert (e["ebene"], e["art"]) == ("volltext", "verbinden") and e["ziel"]["datei"] == DATEI and "chunk" not in e["ziel"]
    assert text_im_feld(pg) == UMBRUCH.replace("bricht\nmitten", "bricht mitten")
    assert not leiste_offen(pg)


def test_loeschen_und_trennen_im_volltext(seite_umbruch):
    pg = seite_umbruch
    waehle(pg, "setzt sich", "fort.")
    knopf(pg, "loeschen").click()
    pg.wait_for_function("eintraege.length === 1")
    assert text_im_feld(pg) == UMBRUCH.replace("\nsetzt sich fort.", "")
    waehle(pg, "mitten im Satz", "ab und")
    knopf(pg, "trennen").click()
    pg.wait_for_function("eintraege.length === 2")
    assert [e["art"] for e in eintrag_liste(pg)] == ["loeschen", "trennen"]
    assert text_im_feld(pg) == UMBRUCH.replace("\nsetzt sich fort.", "").replace("bricht\nmitten", "bricht\n\nmitten")


def test_verschieben_im_volltext_zweiter_schritt_zielabsatz(browser, tmp_path):
    """Hohe Seite: die Verschiebe-Leiste liegt unten im Textfenster und darf den kurzen Testtext nicht verdecken."""
    a = Apic(baue(tmp_path, kapitel=UMBRUCH))
    ctx, pg = neue_seite(browser, a.url, 960, 900)
    try:
        zu_text(pg)
        _verschieben_im_volltext(pg)
    finally:
        ctx.close()
        a.stop()
    assert not pg.fehler, pg.fehler


def _verschieben_im_volltext(pg):
    waehle(pg, "Zweiter Absatz", "hier.")
    knopf(pg, "verschieben").click()
    xy = pg.evaluate("""() => { const pre = document.getElementById('rechts-inhalt'), w = document.createTreeWalker(pre, NodeFilter.SHOW_TEXT);
      let t; while ((t = w.nextNode())) { const i = t.data.indexOf('Dritter Absatz'); if (i >= 0) {
        const r = document.createRange(); r.setStart(t, i); r.setEnd(t, i + 6); const b = r.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; } } }""")
    pg.touchscreen.tap(xy[0], xy[1])
    pg.wait_for_function("eintraege.length === 1")
    (e,) = eintrag_liste(pg)
    assert e["art"] == "verschieben" and e["parameter"]["nach_anfang"].startswith("Dritter") and e["ziel"]["datei"] == DATEI
    neu = text_im_feld(pg)
    assert neu.index("Dritter Absatz") < neu.index("Zweiter Absatz")
    assert pg.locator("#absatz-leiste").is_hidden()                                 # der Tipp aufs Ziel öffnet keine Absatzleiste


def test_markieren_im_volltext_aendert_den_text_nicht(seite_umbruch):
    pg = seite_umbruch
    waehle(pg, "Erste Zeile", "mitten im")
    pg.fill("#werkzeug-notiz", "Umbruch prüfen")
    knopf(pg, "markieren").click()
    pg.wait_for_function("eintraege.length === 1")
    (e,) = eintrag_liste(pg)
    assert (e["ebene"], e["art"], e["ziel"]["datei"]) == ("volltext", "marke", DATEI)
    assert e["parameter"] == {"kategorie": "markiert", "text": "Umbruch prüfen"}
    assert text_im_feld(pg) == UMBRUCH
    assert pg.evaluate("window.Redaktion.zaehler(eintraege)") == {"aenderungen": 0, "markierungen": 1, "wartend": pg.evaluate("window.Redaktion.zaehler(eintraege).wartend")}


def test_auswahl_ueber_zwei_absaetze_erlaubt_nur_markieren(seite_umbruch):
    pg = seite_umbruch
    waehle(pg, "setzt sich", "Zweiter Absatz")
    for was in ("verbinden", "verschieben", "loeschen", "trennen"):
        assert knopf(pg, was).is_disabled(), was
    assert knopf(pg, "markieren").is_enabled()


def test_chunk_modus_behaelt_alle_werkzeuge(seite_umbruch):
    pg = seite_umbruch
    pg.locator("#modus-chunks").click()
    pg.wait_for_function("modus === 'chunks' && gezeigteSig !== null")
    zu_chunk(pg, 1)
    waehle(pg, "Representation", "judge")
    for was in ("kapitel", "verzeichnis", "glossar"):
        assert knopf(pg, was).is_visible(), was
