"""Browserpruefung der Aenderungsliste mit Ruecknahme (#aenderungsliste) und von "Neu anwenden" bei 960x600.

Nutzt Paket und Hilfen aus test_werkzeugleiste.py (Testwurzel per `redaktion.testwurzel`, Chromium).
Ohne Playwright/Chromium uebersprungen."""
import json
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))

from test_werkzeugleiste import browser, eintraege, knopf, paket, seite, text, waehle, zu_chunk  # noqa: E402,F401

# Ein Eintrag, dessen vorher-Pruefsumme nicht zum Absatz passt: lokaler Konflikt (Hash stimmt nicht mehr)
JS_KONFLIKT = """async () => {
  const ans = ansichtCache.get(gezeigterChunk).ansicht;
  const t = CA.absatzText(ans, 0);
  const e = Redaktion.neuerEintrag(buchSchluessel(buch), 'chunk-orig',
    {chunk: gezeigterChunk, anfang: Redaktion.ankerVon(t), absatz_index: 0, zeile: 0}, 'verbinden', {}, 'ganz anderer Text', 'Altlast', 'test');
  await neueAenderung(e);
  return e.id;
}"""


def eintraege_voll(pg):
    return pg.evaluate("eintraege.map((e) => ({id: e.id, art: e.art, status: e.status}))")


def leiste_text(pg):
    return pg.inner_text("#aenderungen-text")


def liste_oeffnen(pg):
    pg.locator("#aenderungen-liste-knopf").click()
    pg.wait_for_selector("#aenderungsliste[open]")


def zeilen(pg):
    return pg.locator("#aenderungsliste li.aenderung")


def verbinden(pg):
    """Erste Zeile des ersten Absatzes in Chunk 1 mit der zweiten verbinden: genau ein Eintrag."""
    zu_chunk(pg, 1)
    waehle(pg, "Representation", "so")
    knopf(pg, "verbinden").click()
    pg.wait_for_function("eintraege.length === 1")
    pg.wait_for_function("gezeigteSig.includes(eintraege[0].id)")


def test_knopf_und_liste_deutsch_und_touchgroesse(seite):
    verbinden(seite)
    knopf_box = seite.locator("#aenderungen-liste-knopf").bounding_box()
    assert seite.inner_text("#aenderungen-liste-knopf") == "Änderungen anzeigen"
    assert knopf_box["height"] >= 44 and knopf_box["width"] >= 44
    liste_oeffnen(seite)
    assert zeilen(seite).count() == 1
    zeile = zeilen(seite).first.inner_text()
    assert "Zeilen verbunden" in zeile and "Chunk 1" in zeile and "wartet auf APIC" in zeile
    namen = [seite.locator("#aenderungsliste li button").nth(i).inner_text() for i in range(2)]
    assert namen == ["Zurücknehmen", "Springen"]
    for i in range(2):
        box = seite.locator("#aenderungsliste li button").nth(i).bounding_box()
        assert box["height"] >= 44 and box["width"] >= 44
    assert seite.inner_text("#aenderungsliste-zu") == "Schließen"
    dlg = seite.locator("#aenderungsliste").bounding_box()
    assert dlg["x"] >= 0 and dlg["y"] >= 0 and dlg["x"] + dlg["width"] <= 960 and dlg["y"] + dlg["height"] <= 600


def test_zuruecknehmen_offenen_stellt_text_wieder_her_und_zaehler_sinkt(seite):
    zu_chunk(seite, 1)
    vorher = text(seite)
    verbinden(seite)
    assert text(seite) != vorher
    assert "1 Änderung · 0 Markierungen" in leiste_text(seite)
    liste_oeffnen(seite)
    seite.locator("#aenderungsliste li button", has_text="Zurücknehmen").first.click()
    seite.wait_for_function("eintraege.length === 0")
    seite.wait_for_function("document.querySelectorAll('#aenderungsliste li').length === 0")
    assert "Noch keine Änderungen" in seite.inner_text("#aenderungsliste-inhalt")
    seite.locator("#aenderungsliste-zu").click()
    seite.wait_for_function("document.getElementById('rechts-inhalt').textContent === " + json.dumps(vorher))
    assert "0 Änderungen · 0 Markierungen" in leiste_text(seite)


def test_zuruecknehmen_markiert_abhaengige_als_konflikt_und_loescht_sie_nicht(seite):
    zu_chunk(seite, 1)
    vorher = text(seite)
    waehle(seite, "Representation", "name.")                       # zwei Eintraege, der zweite baut auf dem ersten auf
    knopf(seite, "verbinden").click()
    seite.wait_for_function("eintraege.length === 2")
    seite.wait_for_function("gezeigteSig.includes(eintraege[1].id)")
    liste_oeffnen(seite)
    assert zeilen(seite).count() == 2
    zeilen(seite).first.locator("button", has_text="Zurücknehmen").click()
    seite.wait_for_function("eintraege.length === 1")
    e = eintraege(seite)[0]
    assert e["status"] == "konflikt"
    assert zeilen(seite).count() == 1 and zeilen(seite).first.get_attribute("data-status") == "konflikt"
    assert "abhängig vom zurückgenommenen Eintrag" in zeilen(seite).first.inner_text()
    seite.locator("#aenderungsliste-zu").click()
    seite.wait_for_function("document.querySelectorAll('#rechts-inhalt .konflikt').length === 1")
    liste_oeffnen(seite)
    zeilen(seite).first.locator("button", has_text="Zurücknehmen").click()
    seite.wait_for_function("eintraege.length === 0")
    seite.locator("#aenderungsliste-zu").click()
    seite.wait_for_function("document.getElementById('rechts-inhalt').textContent === " + json.dumps(vorher))


def mit_apic(pg, base_url, halte_erste=None, stand_status=None):
    """APIC-Attrappe: nimmt Sendungen an und merkt sich die Koerper. halte_erste (Liste): die erste Antwort
    wird zurueckgehalten (Route landet in der Liste, der Test beantwortet sie spaeter). stand_status: Stand
    meldet diesen Status fuer jede bisher gesendete id."""
    gesendet = []

    def antworte(route, body):
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"angenommen": [e["id"] for e in body["eintraege"]]}))

    def behandle(route):
        body = json.loads(route.request.post_data)
        gesendet.append(body)
        if halte_erste is not None and len(gesendet) == 1:
            halte_erste.append((route, body))
        else:
            antworte(route, body)

    def stand(route):
        ids = [e["id"] for k in gesendet for e in k["eintraege"]]
        st = {i: {"status": stand_status, "grund": ""} for i in ids} if stand_status else {}
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"stand": st}))

    pg.route("**/api/aenderungen", behandle)
    pg.route("**/api/stand**", stand)
    pg.evaluate("v => { verbindung = {adresse: v, token: 'tok', geraet: 'testgeraet'}; }", base_url)
    return gesendet


def test_zuruecknahme_waehrend_des_sendens_wird_nachgemeldet(seite, paket):
    gehalten = []
    gesendet = mit_apic(seite, paket.rsplit("/", 1)[0], halte_erste=gehalten)
    verbinden(seite)
    seite.wait_for_function("sendeLaeuft === true")
    assert len(gehalten) == 1
    liste_oeffnen(seite)
    seite.locator("#aenderungsliste li button", has_text="Zurücknehmen").first.click()      # Eintrag noch offen: wird entfernt
    seite.wait_for_function("eintraege.length === 0")
    route, body = gehalten[0]
    route.fulfill(status=200, content_type="application/json", body=json.dumps({"angenommen": [e["id"] for e in body["eintraege"]]}))
    seite.wait_for_function("eintraege.some((e) => e.art === 'ruecknahme' && e.status === 'gesendet')")
    ziel_id = body["eintraege"][0]["id"]
    assert len(gesendet) == 2
    r = gesendet[1]["eintraege"][0]
    assert r["art"] == "ruecknahme" and r["parameter"] == {"id": ziel_id}


def test_lokaler_konflikt_wird_nicht_von_apic_bestaetigt_ueberschrieben(seite, paket):
    gesendet = mit_apic(seite, paket.rsplit("/", 1)[0], stand_status="bestaetigt")
    zu_chunk(seite, 1)
    waehle(seite, "Representation", "name.")                       # zwei verbinden-Eintraege, der zweite haengt vom ersten ab
    knopf(seite, "verbinden").click()
    seite.wait_for_function("eintraege.length === 2 && eintraege.every((e) => e.status === 'bestaetigt')")
    erste, zweite = [e["id"] for e in eintraege_voll(seite)]
    liste_oeffnen(seite)
    zeilen(seite).first.locator("button", has_text="Zurücknehmen").click()
    seite.wait_for_function("eintraege.some((e) => e.art === 'ruecknahme' && e.status !== 'offen')")
    seite.wait_for_function("sendeLaeuft === false")
    rest = {e["id"]: e["status"] for e in eintraege_voll(seite)}
    assert rest[zweite] == "konflikt" and erste not in rest      # Stand meldet bestaetigt, der lokale Konflikt bleibt


def test_zuruecknehmen_gesendeten_sendet_ruecknahme_mit(seite, paket):
    gesendet = mit_apic(seite, paket.rsplit("/", 1)[0])
    verbinden(seite)
    seite.wait_for_function("eintraege[0].status === 'gesendet'")
    liste_oeffnen(seite)
    assert "bereits bei APIC" in zeilen(seite).first.inner_text()
    seite.locator("#aenderungsliste li button", has_text="Zurücknehmen").first.click()
    seite.wait_for_function("eintraege.length === 1 && eintraege[0].art === 'ruecknahme' && eintraege[0].status === 'gesendet'")
    ziel_id = gesendet[0]["eintraege"][0]["id"]
    r = gesendet[-1]["eintraege"][0]
    assert r["art"] == "ruecknahme" and r["parameter"] == {"id": ziel_id} and r["ziel"]["chunk"] == 1
    assert len(gesendet) == 2
    assert zeilen(seite).count() == 0                                   # Rücknahmen sind keine eigene Zeile
    assert "0 Änderungen" in leiste_text(seite) or leiste_text(seite) == "alles bei APIC angekommen"
    seite.locator("#aenderungsliste-zu").click()


def test_angewendeter_eintrag_ist_nicht_zuruecknehmbar(seite):
    verbinden(seite)
    seite.evaluate("aendereEintraege(buch.id, (l) => l.map((e) => Object.assign({}, e, {status: 'angewendet'})))")
    seite.wait_for_function("eintraege[0].status === 'angewendet'")
    liste_oeffnen(seite)
    k = seite.locator("#aenderungsliste li button", has_text="Zurücknehmen").first
    assert k.is_disabled() and "nicht möglich" in k.get_attribute("title")
    k.click(force=True)
    seite.wait_for_timeout(200)
    assert len(eintraege(seite)) == 1


def test_hinweis_neuer_export_nur_bei_angewendeten_textaenderungen(seite):
    verbinden(seite)
    assert seite.locator("#aenderungen-hinweis").is_hidden()
    seite.evaluate("aendereEintraege(buch.id, (l) => l.map((e) => Object.assign({}, e, {status: 'angewendet'})))")
    seite.wait_for_function("eintraege[0].status === 'angewendet'")
    hinweis = seite.locator("#aenderungen-hinweis")
    assert hinweis.is_visible()
    assert "am PC eingearbeitet" in hinweis.inner_text() and "Neuer Export" in hinweis.inner_text()
    # eine Marke zaehlt nicht als eingearbeitete Textaenderung
    seite.evaluate("aendereEintraege(buch.id, (l) => l.map((e) => Object.assign({}, e, {art: 'marke'})))")
    seite.wait_for_function("eintraege[0].art === 'marke'")
    assert seite.locator("#aenderungen-hinweis").is_hidden()


def test_springen_oeffnet_den_chunk(seite):
    verbinden(seite)
    zu_chunk(seite, 2)
    liste_oeffnen(seite)
    seite.locator("#aenderungsliste li button", has_text="Springen").first.click()
    seite.wait_for_function("gezeigterChunk === 1")
    assert not seite.locator("#aenderungsliste").is_visible()


def test_leiste_zaehlt_ruecknahme_nicht_als_aenderung_und_neu_anwenden_ist_atomar(seite):
    zu_chunk(seite, 1)
    seite.evaluate("() => { window.speicherAufrufe = []; const orig = eintragsSpeicher.speichern; "
                   "eintragsSpeicher.speichern = async (id, l) => { window.speicherAufrufe.push(l.map((e) => e.art)); return orig(id, l); }; }")
    alt_id = seite.evaluate(JS_KONFLIKT)
    seite.wait_for_function("document.querySelectorAll('#rechts-inhalt .konflikt').length === 1")
    assert eintraege(seite)[0]["status"] == "offen"                     # lokaler Konflikt: Status bleibt, Block erscheint
    seite.evaluate("window.speicherAufrufe = []")
    # Abbruch beim Speichern: weder neuer Eintrag noch Rücknahme
    seite.evaluate("() => { window.echtSpeichern = eintragsSpeicher.speichern; eintragsSpeicher.speichern = async () => { throw new Error('Platte voll'); }; }")
    seite.locator("#rechts-inhalt .konflikt button[data-aktion='neu']").click()
    seite.wait_for_function("chunkBusy === false")
    assert len(eintraege(seite)) == 1 and eintraege(seite)[0]["art"] == "verbinden"
    assert "Änderung nicht gespeichert" in seite.inner_text("#rechts-verdacht")
    seite.evaluate("() => { eintragsSpeicher.speichern = window.echtSpeichern; }")
    assert len(seite.evaluate("eintragsSpeicher.laden(buch.id)")) == 1
    # Erfolg: genau EIN Speichervorgang mit beiden Eintraegen
    seite.evaluate("window.speicherAufrufe = []")
    seite.locator("#rechts-inhalt .konflikt button[data-aktion='neu']").click()
    seite.wait_for_function("eintraege.length === 3")
    seite.wait_for_function("chunkBusy === false")
    assert seite.evaluate("window.speicherAufrufe") == [["verbinden", "verbinden", "ruecknahme"]]
    e = eintraege(seite)
    r = seite.evaluate("eintraege[2].parameter")
    assert r == {"id": alt_id}
    assert e[1]["status"] == "offen" and e[1]["art"] == "verbinden"
    assert "1 Änderung · 0 Markierungen · 3 warten auf APIC" in leiste_text(seite)      # Rücknahme zählt nicht als Änderung
    seite.wait_for_function("document.querySelectorAll('#rechts-inhalt .konflikt').length === 0")
    # Liste: nur der neue Eintrag, die Rücknahme und der alte Eintrag sind verschwunden
    liste_oeffnen(seite)
    assert zeilen(seite).count() == 1


def test_neu_anwenden_buchwechsel_trennt_die_beiden_eintraege_nicht(seite):
    zu_chunk(seite, 1)
    alt_id = seite.evaluate(JS_KONFLIKT)
    seite.wait_for_function("document.querySelectorAll('#rechts-inhalt .konflikt').length === 1")
    buch_id = seite.evaluate("buch.id")
    # chunkAktion legt beide Eintraege fuer das Buch an, das beim Klick offen war, auch wenn danach gewechselt wird
    ergebnis = seite.evaluate("""async () => {
      const b = buch, c = ansichtCache.get(gezeigterChunk);
      const k = c.ansicht.konflikte[0];
      const lauf = chunkAktion('neu', k, c.ansicht);
      buch = Object.assign({}, b, {id: 'fremd', titel: 'Fremdes Buch'});
      await lauf;
      buch = b;
      return {eigenes: (await eintragsSpeicher.laden(b.id)).map((e) => e.art), fremdes: await eintragsSpeicher.laden('fremd')};
    }""")
    assert ergebnis["eigenes"] == ["verbinden", "verbinden", "ruecknahme"] and ergebnis["fremdes"] == []
    assert buch_id and alt_id


def test_indexeddb_verbindung_wird_wiederverwendet_und_nach_versionchange_neu_geoeffnet(seite):
    erg = seite.evaluate("""async () => {
      const a = dbOffen(), b = dbOffen();
      const gleich = a === b;
      const db = await a;
      db.onversionchange();
      const c = dbOffen();
      return { gleich, neu: c !== a, offen: !!(await c).name };
    }""")
    assert erg["gleich"] is True and erg["neu"] is True and erg["offen"] is True
