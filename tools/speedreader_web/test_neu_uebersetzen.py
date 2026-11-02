"""Browserpruefung von "Neu uebersetzen", Vergleich und Uebernehmen (Task 13) bei 960x600 und 600x960.

Baut je Test eine Testwurzel (`redaktion.testwurzel`), startet den echten Empfaenger (redaktion_server) mit einer
Attrappe als Uebersetzer in einem Thread und liefert die App daraus aus (ein Ursprung). Ohne Playwright/Chromium
uebersprungen."""
import json
import socket
import sys
import threading
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent))

sync_api = pytest.importorskip("playwright.sync_api")

from test_werkzeugleiste import browser, knopf, waehle, zu_chunk  # noqa: E402,F401

import redaktion_anwenden as ra  # noqa: E402
from redaktion import ops, protokoll  # noqa: E402
from redaktion.testwurzel import AUTOR, TITEL, DEUTSCH, baue_testwurzel  # noqa: E402
from redaktion_server import erzeuge_server  # noqa: E402

BUCH = f"{AUTOR}/{TITEL}"
TOKEN = "tok"


def neu_text(chunk: int) -> str:
    return f"Neue Übersetzung von Chunk {chunk}: Größe, Ärger, Straße.\n\nZweiter Absatz, neu übersetzt.\n"


class Apic:
    """Empfaenger mit Attrappe als Uebersetzer. `tor` haelt Auftraege an, bis es gesetzt ist."""

    def __init__(self, root: Path, port: int = 0, token: str = TOKEN):
        self.root = root
        self.tor = threading.Event()
        self.tor.set()
        self.fehler = ""
        self.jobs: list[dict] = []
        paket = root / "reader" / "export-epistopheles"
        self.httpd = erzeuge_server(root, host="127.0.0.1", port=port, paket=paket, token=token, starte=self._starte)
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def _starte(self, job: dict) -> None:
        self.jobs.append(job)
        self.tor.wait(15)
        if self.fehler:
            raise RuntimeError(self.fehler)
        lektor = ra.lektor_ordner(self.root, job["buch"])
        (lektor / "de" / f"chunk_{job['chunk']:03d}.md.neu").write_bytes(neu_text(job["chunk"]).encode("utf-8"))

    def stop(self) -> None:
        self.tor.set()
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(5)

    def de(self, n: int = 1) -> Path:
        return ra.lektor_ordner(self.root, BUCH) / "de" / f"chunk_{n:03d}.md"


@pytest.fixture()
def apic(tmp_path):
    a = Apic(baue_testwurzel(tmp_path / "wurzel"))
    yield a
    a.stop()


def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def neue_seite(browser, url, breite=960, hoehe=600, adresse=None, token=TOKEN):
    ctx = browser.new_context(viewport={"width": breite, "height": hoehe}, has_touch=True)
    ctx.add_init_script("window.KSENDE_INTERVALL_MS = 500; window.KAUFTRAG_POLL_MS = 100;")
    pg = ctx.new_page()
    pg.set_default_timeout(6000)
    pg.fehler = []
    pg.on("pageerror", lambda e: pg.fehler.append(str(e)))
    pg.goto(url + "/korrektur.html")
    pg.wait_for_function("typeof buch !== 'undefined' && buch && eintraegeBuchId === buch.id && gezeigteSig !== null")
    pg.evaluate("v => { verbindung = v; }", {"adresse": adresse or url, "token": token, "geraet": "testgeraet"})
    return ctx, pg


@pytest.fixture()
def seite(browser, apic):
    ctx, pg = neue_seite(browser, apic.url)
    yield pg
    ctx.close()
    assert not pg.fehler, pg.fehler


def korrigiere(pg):
    """Erste Zeile des ersten Absatzes in Chunk 1 mit der zweiten verbinden: genau ein Eintrag."""
    zu_chunk(pg, 1)
    waehle(pg, "Representation", "so")
    knopf(pg, "verbinden").click()
    pg.wait_for_function("eintraege.length === 1")


def zu_uebersetzung(pg):
    pg.locator("#modus-uebersetzung").click()
    pg.wait_for_function("modus === 'uebersetzung' && gezeigteSig !== null")


def status(pg):
    return pg.inner_text("#neu-status")


def wunsch(pg):
    return pg.evaluate("auftraegeVon(buch.id)['1'] || null")


def vorbereitet(pg):
    korrigiere(pg)
    zu_uebersetzung(pg)


def eintraege_art(pg, art):
    return pg.evaluate("(a) => eintraege.filter((e) => e.art === a)", art)


def test_ohne_korrektur_kein_hinweis_und_kein_knopf(seite):
    zu_chunk(seite, 1)
    zu_uebersetzung(seite)
    assert not seite.locator("#neu-zeile").is_visible()
    assert not seite.locator("#neu-uebersetzen").is_visible()


def test_hinweis_veraltet_und_knopf_nach_korrektur_deutsch_und_touchgroesse(seite):
    korrigiere(seite)
    assert not seite.locator("#neu-zeile").is_visible()                     # nur im Modus Übersetzung
    zu_uebersetzung(seite)
    assert seite.inner_text("#veraltet-hinweis") == "Original geändert, Übersetzung veraltet"
    knopf_neu = seite.locator("#neu-uebersetzen")
    assert knopf_neu.inner_text() == "Neu übersetzen" and knopf_neu.is_enabled()
    box = knopf_neu.bounding_box()
    assert box["height"] >= 44 and box["width"] >= 44
    zeile = seite.locator("#neu-zeile").bounding_box()
    assert zeile["x"] >= 0 and zeile["x"] + zeile["width"] <= 960 and zeile["y"] + zeile["height"] <= 600
    # anderer Chunk ohne Korrektur: kein Hinweis
    seite.evaluate("rechtsSpringe(0)")
    seite.wait_for_function("gezeigterChunk === 0 && gezeigteSig !== null")
    assert not seite.locator("#neu-zeile").is_visible()


def test_hauptfluss_neu_uebersetzen_laeuft_fertig_vergleich_uebernehmen_und_am_pc_anwenden(seite, apic):
    apic.tor.clear()                                                         # Auftrag laeuft, bis wir ihn freigeben
    vorbereitet(seite)
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_function("(auftraegeVon(buch.id)['1'] || {}).zustand === 'laeuft'")
    assert "läuft" in status(seite)
    assert seite.locator("#neu-uebersetzen").is_disabled()                   # nur ein Auftrag je Chunk
    assert [(j["buch"], j["chunk"]) for j in apic.jobs] == [(BUCH, 1)]
    assert seite.evaluate("JSON.parse(localStorage.getItem('kauftraege:' + buch.id))['1'].zustand") == "laeuft"
    # Korrektur muss VOR dem Auftrag bei APIC angekommen sein (sonst fehlt sie im Vorschlag)
    assert protokoll.lade_eingang(apic.root, BUCH)[0]["art"] == "verbinden"

    alt = DEUTSCH[1]
    de_vorher = apic.de().read_bytes()
    apic.tor.set()
    seite.wait_for_selector("#vergleich[open]")                              # bei "fertig" öffnet der Vergleich von selbst
    seite.wait_for_function("document.getElementById('vergleich-neu').textContent !== ''")
    assert seite.inner_text("#vergleich-alt") == alt
    assert seite.inner_text("#vergleich-neu") == neu_text(1)
    assert apic.de().read_bytes() == de_vorher                               # nichts überschrieben
    # nebeneinander, im Fenster, Touch-Ziele
    a, n = seite.locator("#vergleich-alt").bounding_box(), seite.locator("#vergleich-neu").bounding_box()
    assert a["x"] + a["width"] <= n["x"] + 1 and abs(a["y"] - n["y"]) < 2 and a["height"] > 60
    dlg = seite.locator("#vergleich").bounding_box()
    assert dlg["x"] >= 0 and dlg["y"] >= 0 and dlg["x"] + dlg["width"] <= 960 and dlg["y"] + dlg["height"] <= 600
    for sel, name in (("#vergleich-uebernehmen", "Übernehmen"), ("#vergleich-verwerfen", "Verwerfen"), ("#vergleich-zu", "Schließen")):
        k = seite.locator(sel)
        assert k.inner_text() == name
        b = k.bounding_box()
        assert b["height"] >= 44 and b["width"] >= 44
        assert b["y"] + b["height"] <= 600
    assert seite.locator("#vergleich-uebernehmen").is_enabled()

    seite.locator("#vergleich-uebernehmen").click()
    seite.wait_for_function("eintraege.some((e) => e.art === 'uebersetzung-uebernehmen')")
    seite.wait_for_function("!document.getElementById('vergleich').open")
    (e,) = eintraege_art(seite, "uebersetzung-uebernehmen")
    assert e["ebene"] == "uebersetzung" and e["ziel"] == {"chunk": 1} and e["buch"] == BUCH
    assert e["parameter"] == {"neu_hash": ops.pruefsumme(neu_text(1))}
    assert e["vorher"]["hash"] == ops.pruefsumme(alt)
    assert seite.evaluate("auftraegeVon(buch.id)['1'] || null") is None      # Wunsch erledigt
    assert apic.de().read_bytes() == de_vorher                               # auch jetzt: kein Text geändert
    assert seite.inner_text("#uebersetzung-inhalt") == alt                   # die App zeigt weiter die alte Übersetzung
    assert "Übernahme vorgemerkt" in status(seite)
    assert seite.locator("#neu-uebersetzen").is_disabled()                   # keine zweite Übernahme / kein Überlappen
    # in der Änderungsliste
    seite.locator("#aenderungen-liste-knopf").click()
    seite.wait_for_selector("#aenderungsliste[open]")
    zeilen = seite.locator("#aenderungsliste li.aenderung")
    assert zeilen.count() == 2
    texte = [zeilen.nth(i).inner_text() for i in range(2)]
    assert any("Übersetzung übernehmen" in t and "Chunk 1" in t and "am PC unter Kontrolle" in t for t in texte)
    seite.locator("#aenderungsliste-zu").click()
    # gesendet -> Eingang bei APIC
    seite.wait_for_function("eintraege.every((x) => x.status === 'gesendet')")
    eingang = protokoll.lade_eingang(apic.root, BUCH)
    assert sorted(x["art"] for x in eingang) == ["uebersetzung-uebernehmen", "verbinden"]

    # am PC: Dry-Run ändert nichts, mit --ausfuehren wird (mit Backup) übernommen
    assert ra.main(["--root", str(apic.root), "--buch", BUCH]) == 0
    assert apic.de().read_bytes() == de_vorher
    assert ra.main(["--root", str(apic.root), "--buch", BUCH, "--ausfuehren"]) == 0
    assert apic.de().read_bytes() == neu_text(1).encode("utf-8")
    assert not apic.de().with_name("chunk_001.md.neu").exists()
    backups = list((ra.lektor_ordner(apic.root, BUCH) / "notizen" / "_backup").glob("chunk_001.*.md"))
    assert any(b.read_bytes() == de_vorher for b in backups)


def test_verwerfen_entfernt_den_wunsch_und_aendert_nichts(seite, apic):
    vorbereitet(seite)
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_selector("#vergleich[open]")
    seite.wait_for_function("document.getElementById('vergleich-neu').textContent !== ''")
    de_vorher = apic.de().read_bytes()
    seite.locator("#vergleich-verwerfen").click()
    seite.wait_for_function("!document.getElementById('vergleich').open")
    assert wunsch(seite) is None
    assert not [e for e in seite.evaluate("eintraege") if e["art"] == "uebersetzung-uebernehmen"]
    assert apic.de().read_bytes() == de_vorher
    assert seite.locator("#neu-uebersetzen").is_enabled()                    # man kann neu anfordern
    assert not seite.locator("#vergleich-zeigen").is_visible()


def test_vergleich_spaeter_ueber_knopf_oeffnen_und_doppelklick_uebernimmt_einmal(seite, apic):
    vorbereitet(seite)
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_selector("#vergleich[open]")
    seite.locator("#vergleich-zu").click()                                   # Schließen: der Vorschlag bleibt abrufbar
    seite.wait_for_function("!document.getElementById('vergleich').open")
    assert wunsch(seite)["zustand"] == "fertig"
    assert "fertig" in status(seite)
    k = seite.locator("#vergleich-zeigen")
    assert k.inner_text() == "Vergleich ansehen" and k.bounding_box()["height"] >= 44
    k.click()
    seite.wait_for_function("document.getElementById('vergleich-neu').textContent !== ''")
    seite.locator("#vergleich-uebernehmen").dblclick()
    seite.wait_for_function("eintraege.some((e) => e.art === 'uebersetzung-uebernehmen')")
    seite.wait_for_timeout(300)
    assert len(eintraege_art(seite, "uebersetzung-uebernehmen")) == 1


def test_ruecknahme_der_uebernahme_gibt_neu_uebersetzen_wieder_frei(seite, apic):
    vorbereitet(seite)
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_selector("#vergleich[open]")
    seite.wait_for_function("document.getElementById('vergleich-neu').textContent !== ''")
    seite.locator("#vergleich-uebernehmen").click()
    seite.wait_for_function("!document.getElementById('vergleich').open")
    assert seite.locator("#neu-uebersetzen").is_disabled()
    seite.locator("#aenderungen-liste-knopf").click()
    seite.wait_for_selector("#aenderungsliste[open]")
    seite.locator("#aenderungsliste li", has_text="Übersetzung übernehmen").locator("button", has_text="Zurücknehmen").click()
    seite.wait_for_function("!eintraege.some((e) => e.art === 'uebersetzung-uebernehmen' && e.art !== 'ruecknahme' && !eintraege.some((r) => r.art === 'ruecknahme' && r.parameter.id === e.id))")
    seite.locator("#aenderungsliste-zu").click()
    seite.wait_for_function("document.getElementById('neu-uebersetzen').disabled === false")
    assert "Übernahme vorgemerkt" not in status(seite)


# ---- Fehlerzustaende: nie still --------------------------------------------------------------------------------------

def test_apic_nicht_erreichbar_wunsch_bleibt_und_geht_bei_erreichbarkeit_hinaus(seite, apic):
    vorbereitet(seite)
    seite.wait_for_function("eintraege[0].status === 'gesendet'")            # Korrektur ist schon bei APIC
    blockiert = {"an": True}

    def route(r):
        if blockiert["an"]:
            r.abort("connectionrefused")
        else:
            r.continue_()

    seite.route("**/api/auftraege", route)
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_function("((auftraegeVon(buch.id)['1'] || {}).hinweis || '').includes('nicht erreichbar')")
    assert "APIC nicht erreichbar, Wunsch gemerkt" in status(seite)
    assert seite.locator("#neu-status").get_attribute("data-art") == "fehler"
    assert wunsch(seite)["zustand"] == "gemerkt" and apic.jobs == []
    gespeichert = seite.evaluate("JSON.parse(localStorage.getItem('kauftraege:' + buch.id))['1']")
    assert gespeichert["zustand"] == "gemerkt"
    # nach Neuladen der Seite ist der Wunsch noch da
    seite.reload()
    seite.wait_for_function("typeof buch !== 'undefined' && buch && eintraegeBuchId === buch.id && gezeigteSig !== null")
    assert seite.evaluate("auftraegeVon(buch.id)['1'].zustand") == "gemerkt"
    seite.evaluate("v => { verbindung = v; }", {"adresse": apic.url, "token": TOKEN, "geraet": "testgeraet"})
    blockiert["an"] = False                                                  # APIC "startet"
    seite.wait_for_function("['wartet', 'laeuft', 'fertig'].includes((auftraegeVon(buch.id)['1'] || {}).zustand)")
    assert [(j["buch"], j["chunk"]) for j in apic.jobs] == [(BUCH, 1)]


def test_apic_gar_nicht_gestartet_dann_gestartet_wunsch_geht_hinaus(browser, tmp_path):
    root = baue_testwurzel(tmp_path / "wurzel")
    erster = Apic(root)                                                      # liefert die App aus
    port = freier_port()                                                     # hier laeuft (noch) nichts
    ctx, pg = neue_seite(browser, erster.url, adresse=f"http://127.0.0.1:{port}")
    zweiter = None
    try:
        korrigiere(pg)
        zu_uebersetzung(pg)
        pg.locator("#neu-uebersetzen").click()
        pg.wait_for_function("((auftraegeVon(buch.id)['1'] || {}).hinweis || '').includes('APIC nicht erreichbar')")
        assert "APIC nicht erreichbar, Wunsch gemerkt" in status(pg)
        assert pg.locator("#aenderungen-leiste").get_attribute("data-zustand") == "fehler"   # auch die Korrektur wartet sichtbar
        assert erster.jobs == []
        zweiter = Apic(root, port=port)                                      # APIC wird gestartet
        pg.wait_for_function("eintraege[0].status === 'gesendet'")
        pg.wait_for_function("['wartet', 'laeuft', 'fertig'].includes((auftraegeVon(buch.id)['1'] || {}).zustand)")
        pg.wait_for_selector("#vergleich[open]")
        assert [(j["buch"], j["chunk"]) for j in zweiter.jobs] == [(BUCH, 1)]
        assert erster.jobs == []
    finally:
        ctx.close()
        erster.stop()
        if zweiter:
            zweiter.stop()
    assert not pg.fehler, pg.fehler


def test_token_abgelehnt_ist_sichtbar_und_nichts_wird_beauftragt(browser, apic):
    ctx, pg = neue_seite(browser, apic.url, token="falsch")
    try:
        vorbereitet(pg)
        pg.locator("#neu-uebersetzen").click()
        pg.wait_for_function("((auftraegeVon(buch.id)['1'] || {}).hinweis || '').includes('Token abgelehnt')")
        assert "Token abgelehnt, Wunsch gemerkt" in status(pg)
        assert pg.locator("#neu-status").get_attribute("data-art") == "fehler"
        assert apic.jobs == [] and protokoll.lade_eingang(apic.root, BUCH) == []
        # richtiges Token nachtragen: alles geht hinaus
        pg.evaluate("v => { verbindung = v; }", {"adresse": apic.url, "token": TOKEN, "geraet": "testgeraet"})
        pg.wait_for_selector("#vergleich[open]")
        assert [(j["chunk"]) for j in apic.jobs] == [1]
    finally:
        ctx.close()
    assert not pg.fehler, pg.fehler


def test_nicht_eingerichtet_ist_sichtbar(browser, apic):
    ctx, pg = neue_seite(browser, apic.url)
    try:
        pg.evaluate("verbindung = {adresse: '', token: '', geraet: 'testgeraet'}")
        vorbereitet(pg)
        pg.locator("#neu-uebersetzen").click()
        pg.wait_for_function("((auftraegeVon(buch.id)['1'] || {}).hinweis || '').includes('nicht eingerichtet')")
        assert "APIC nicht eingerichtet, Wunsch gemerkt" in status(pg)
        assert apic.jobs == []
    finally:
        ctx.close()


def test_auftrag_fehlgeschlagen_zeigt_meldung_und_erlaubt_neuen_versuch(seite, apic):
    apic.fehler = "Ollama nicht erreichbar"
    vorbereitet(seite)
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_function("(auftraegeVon(buch.id)['1'] || {}).zustand === 'fehler'")
    assert "Fehler: Ollama nicht erreichbar" in status(seite)
    assert seite.locator("#neu-status").get_attribute("data-art") == "fehler"
    assert not seite.locator("#vergleich").is_visible()
    assert seite.locator("#neu-uebersetzen").is_enabled()
    apic.fehler = ""
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_selector("#vergleich[open]")
    seite.wait_for_function("document.getElementById('vergleich-neu').textContent !== ''")


def test_apic_kennt_den_auftrag_nicht_mehr_ist_sichtbarer_fehler(seite, apic):
    apic.tor.clear()
    vorbereitet(seite)
    seite.route("**/api/auftraege/*", lambda r: r.fulfill(status=404, content_type="application/json", body='{"fehler": "Unbekannter Auftrag"}'))
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_function("(auftraegeVon(buch.id)['1'] || {}).zustand === 'fehler'")
    assert "APIC kennt den Auftrag nicht mehr" in status(seite)
    apic.tor.set()


def test_abfrage_bricht_ab_hinweis_wird_gezeigt_und_spaeter_wieder_aufgenommen(seite, apic):
    apic.tor.clear()
    vorbereitet(seite)
    zustand = {"aus": True}

    def route(r):
        if zustand["aus"]:
            r.abort("connectionrefused")
        else:
            r.continue_()

    seite.route("**/api/auftraege/*", route)
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_function("((auftraegeVon(buch.id)['1'] || {}).hinweis || '').includes('nicht erreichbar')")
    assert wunsch(seite)["zustand"] == "wartet"                              # Zustand bleibt, nichts verloren
    assert seite.locator("#neu-status").get_attribute("data-art") == "fehler"
    zustand["aus"] = False
    apic.tor.set()
    seite.wait_for_selector("#vergleich[open]")


def test_vorschlag_nicht_abrufbar_zeigt_fehler_und_kann_wiederholt_werden(seite, apic):
    vorbereitet(seite)
    seite.wait_for_function("eintraege[0].status === 'gesendet'")
    seite.route("**/api/vorschlag**", lambda r: r.fulfill(status=401, content_type="application/json", body="{}"))
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_selector("#vergleich[open]")
    seite.wait_for_function("document.getElementById('vergleich-status').dataset.art === 'fehler'")
    assert "Vorschlag nicht abrufbar: Token abgelehnt" in seite.inner_text("#vergleich-status")
    assert seite.locator("#vergleich-uebernehmen").is_disabled()
    assert seite.locator("#vergleich-nochmal").is_visible() and seite.locator("#vergleich-nochmal").inner_text() == "Erneut laden"
    seite.unroute("**/api/vorschlag**")
    seite.locator("#vergleich-nochmal").click()
    seite.wait_for_function("document.getElementById('vergleich-neu').textContent !== ''")
    assert seite.locator("#vergleich-uebernehmen").is_enabled()


def test_kein_vorschlag_bei_apic_404_zeigt_hinweis(seite, apic):
    vorbereitet(seite)
    seite.wait_for_function("eintraege[0].status === 'gesendet'")
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_selector("#vergleich[open]")
    seite.wait_for_function("document.getElementById('vergleich-neu').textContent !== ''")
    seite.locator("#vergleich-zu").click()
    apic.de().with_name("chunk_001.md.neu").unlink()                         # Vorschlag ist weg
    seite.locator("#vergleich-zeigen").click()
    seite.wait_for_function("document.getElementById('vergleich-status').dataset.art === 'fehler'")
    assert "kein Vorschlag" in seite.inner_text("#vergleich-status")
    assert seite.locator("#vergleich-uebernehmen").is_disabled() and seite.locator("#vergleich-verwerfen").is_enabled()


# ---- Races ---------------------------------------------------------------------------------------------------------------------

def test_spaete_antwort_nach_schliessen_fuellt_den_vergleich_nicht_mehr(seite, apic):
    vorbereitet(seite)
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_selector("#vergleich[open]")
    seite.wait_for_function("document.getElementById('vergleich-neu').textContent !== ''")
    seite.locator("#vergleich-zu").click()
    gehalten = []
    seite.route("**/api/vorschlag**", lambda r: gehalten.append(r))
    seite.locator("#vergleich-zeigen").click()
    seite.wait_for_function("document.getElementById('vergleich').open")
    seite.wait_for_timeout(200)
    assert len(gehalten) == 1
    seite.locator("#vergleich-zu").click()                                    # Person schließt, bevor APIC antwortet
    gehalten[0].fulfill(status=200, content_type="application/json", body=json.dumps({"alt": "A", "neu": "SPAET"}))
    seite.wait_for_timeout(300)
    assert seite.evaluate("vergleich") is None
    assert seite.inner_text("#vergleich-neu") != "SPAET"
    assert seite.locator("#vergleich-uebernehmen").is_disabled()
    seite.evaluate("() => { const k = document.getElementById('vergleich-uebernehmen'); k.disabled = false; k.click(); }")   # erzwungen: kein Eintrag
    seite.wait_for_timeout(200)
    assert eintraege_art(seite, "uebersetzung-uebernehmen") == []


def test_alte_antwort_ueberschreibt_keinen_neueren_vergleich(seite, apic):
    vorbereitet(seite)
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_selector("#vergleich[open]")
    seite.wait_for_function("document.getElementById('vergleich-neu').textContent !== ''")
    seite.locator("#vergleich-zu").click()
    gehalten = []
    seite.route("**/api/vorschlag**", lambda r: gehalten.append(r))
    seite.locator("#vergleich-zeigen").click()
    seite.wait_for_function("document.getElementById('vergleich').open")
    seite.wait_for_function("true")
    seite.wait_for_timeout(150)
    seite.locator("#vergleich-zu").click()
    seite.locator("#vergleich-zeigen").click()                                # zweiter Abruf
    seite.wait_for_timeout(200)
    assert len(gehalten) == 2
    gehalten[1].fulfill(status=200, content_type="application/json", body=json.dumps({"alt": "ALT2", "neu": "NEU2"}))
    seite.wait_for_function("document.getElementById('vergleich-neu').textContent === 'NEU2'")
    gehalten[0].fulfill(status=200, content_type="application/json", body=json.dumps({"alt": "ALT1", "neu": "NEU1"}))
    seite.wait_for_timeout(300)
    assert seite.inner_text("#vergleich-neu") == "NEU2" and seite.evaluate("vergleich.neu") == "NEU2"


def test_chunkwechsel_waehrend_auftrag_zeigt_status_je_chunk(seite, apic):
    apic.tor.clear()
    vorbereitet(seite)
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_function("(auftraegeVon(buch.id)['1'] || {}).zustand === 'laeuft'")
    seite.evaluate("rechtsSpringe(0)")
    seite.wait_for_function("gezeigterChunk === 0 && gezeigteSig !== null")
    assert not seite.locator("#neu-zeile").is_visible()                       # Chunk 0: weder Hinweis noch Status von Chunk 1
    apic.tor.set()
    seite.wait_for_function("(auftraegeVon(buch.id)['1'] || {}).zustand === 'fertig'")
    assert not seite.locator("#vergleich").is_visible()                       # Person ist woanders: der Vergleich drängt sich nicht auf
    seite.evaluate("rechtsSpringe(1)")
    seite.wait_for_function("gezeigterChunk === 1 && gezeigteSig !== null")
    assert seite.locator("#vergleich-zeigen").is_visible()
    assert "fertig" in status(seite)


def test_buchwechsel_waehrend_abfrage_aendert_nur_das_alte_buch(seite, apic):
    apic.tor.clear()
    vorbereitet(seite)
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_function("(auftraegeVon(buch.id)['1'] || {}).zustand === 'laeuft'")
    erg = seite.evaluate("""async () => {
      const b = buch, id = b.id;
      buch = Object.assign({}, b, {id: 'fremd', titel: 'Fremdes Buch'});     // Buch wechselt, während die Abfrage läuft
      await new Promise((r) => setTimeout(r, 400));
      const fremd = auftraegeVon('fremd');
      buch = b;
      return {fremd: Object.keys(fremd), eigenes: (auftraegeVon(id)['1'] || {}).zustand};
    }""")
    assert erg["fremd"] == [] and erg["eigenes"] == "laeuft"
    apic.tor.set()
    seite.wait_for_function("(auftraegeVon(buch.id)['1'] || {}).zustand === 'fertig'")


def test_verwerfen_waehrend_abfrage_belebt_den_wunsch_nicht_wieder(seite, apic):
    vorbereitet(seite)
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_selector("#vergleich[open]")
    seite.wait_for_function("document.getElementById('vergleich-neu').textContent !== ''")
    erg = seite.evaluate("""async () => {
      const key = '1', w = auftraegeVon(buch.id)[key];
      entferneAuftrag(buch.id, key);
      const spaet = setzeAuftrag(buch.id, key, w, {zustand: 'laeuft'});     // späte Antwort zum verworfenen Wunsch
      return {spaet, da: auftraegeVon(buch.id)[key] || null};
    }""")
    assert erg == {"spaet": None, "da": None}


def test_zuordnung_unsicher_sperrt_neu_uebersetzen(seite, apic):
    vorbereitet(seite)
    seite.evaluate("pos.deVerschub = 1; zeigeRechts();")
    assert seite.locator("#neu-uebersetzen").is_disabled()
    assert "Zuordnung" in (seite.locator("#neu-uebersetzen").get_attribute("title") or "")
    assert "Zuordnung" in status(seite)
    seite.locator("#neu-uebersetzen").click(force=True)
    seite.wait_for_timeout(200)
    assert wunsch(seite) is None and apic.jobs == []


def test_offene_korrektur_wird_vor_dem_auftrag_gesendet(browser, apic):
    ctx, pg = neue_seite(browser, apic.url)
    try:
        sperre = {"an": True}

        def route(r):
            if sperre["an"]:
                r.abort("connectionrefused")
            else:
                r.continue_()

        pg.route("**/api/aenderungen", route)
        vorbereitet(pg)
        pg.locator("#neu-uebersetzen").click()
        pg.wait_for_function("((auftraegeVon(buch.id)['1'] || {}).hinweis || '').includes('Wunsch gemerkt')")
        assert apic.jobs == []                                                # Korrektur offen -> noch kein Auftrag
        assert pg.evaluate("eintraege[0].status") == "offen"
        sperre["an"] = False
        pg.wait_for_function("eintraege[0].status === 'gesendet'")
        pg.wait_for_selector("#vergleich[open]")
        assert protokoll.lade_eingang(apic.root, BUCH)[0]["art"] == "verbinden"
        assert [j["chunk"] for j in apic.jobs] == [1]
    finally:
        ctx.close()


# ---- Darstellung --------------------------------------------------------------------------------------------------------------

PROBE = """(sel) => {
  const probe = document.createElement('div');
  probe.style.cssText = 'color: var(--warn); background: var(--flaeche); border-color: var(--linie);';
  document.body.append(probe);
  const p = getComputedStyle(probe), e = getComputedStyle(document.querySelector(sel));
  const r = {warn: p.color, flaeche: p.backgroundColor, farbe: e.color, hintergrund: e.backgroundColor};
  probe.remove();
  return r;
}"""


@pytest.mark.parametrize("thema", ["hell", "dunkel"])
def test_farben_kommen_aus_den_variablen_der_seite(seite, apic, thema):
    seite.evaluate("t => setzeThema(t)", thema)
    apic.fehler = "kaputt"
    vorbereitet(seite)
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_function("(auftraegeVon(buch.id)['1'] || {}).zustand === 'fehler'")
    r = seite.evaluate(PROBE, "#neu-status")
    assert r["farbe"] == r["warn"]                                           # Fehlertext in --warn
    apic.fehler = ""
    seite.locator("#neu-uebersetzen").click()
    seite.wait_for_selector("#vergleich[open]")
    r = seite.evaluate(PROBE, "#vergleich")
    assert r["hintergrund"] == r["flaeche"]
    seite.wait_for_function("document.getElementById('vergleich-neu').textContent !== ''")
    assert seite.evaluate(PROBE, "#vergleich-neu")["hintergrund"] != "rgba(0, 0, 0, 0)"


def test_hochformat_vergleich_untereinander_und_im_fenster(browser, apic):
    ctx, pg = neue_seite(browser, apic.url, breite=600, hoehe=960)
    try:
        vorbereitet(pg)
        pg.locator("#neu-uebersetzen").click()
        pg.wait_for_selector("#vergleich[open]")
        pg.wait_for_function("document.getElementById('vergleich-neu').textContent !== ''")
        a, n = pg.locator("#vergleich-alt").bounding_box(), pg.locator("#vergleich-neu").bounding_box()
        assert a["y"] + a["height"] <= n["y"] + 1 and a["height"] > 60 and n["height"] > 60
        dlg = pg.locator("#vergleich").bounding_box()
        assert dlg["x"] >= 0 and dlg["y"] >= 0 and dlg["x"] + dlg["width"] <= 600 and dlg["y"] + dlg["height"] <= 960
        for sel in ("#vergleich-uebernehmen", "#vergleich-verwerfen", "#vergleich-zu"):
            b = pg.locator(sel).bounding_box()
            assert b["height"] >= 44 and b["width"] >= 44 and b["y"] + b["height"] <= 960
    finally:
        ctx.close()
    assert not pg.fehler, pg.fehler
