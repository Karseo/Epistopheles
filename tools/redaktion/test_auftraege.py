"""Tests fuer die Auftrags-Warteschlange (Task 12)."""
from __future__ import annotations

import threading
import time

import pytest

from redaktion.auftraege import Warteschlange

BUCH = "Autor, Eins/Titel"


def warte_bis(bedingung, sek=5.0):
    ende = time.time() + sek
    while time.time() < ende:
        if bedingung():
            return True
        time.sleep(0.01)
    return False


def test_warteschlange_arbeitet_einzeln_nacheinander(tmp_path):
    log, erstes_laeuft, erstes_ende = [], threading.Event(), threading.Event()

    def starte(job):
        log.append(("start", job["chunk"]))
        if job["chunk"] == 1:
            erstes_laeuft.set()
            assert erstes_ende.wait(5)
        log.append(("ende", job["chunk"]))

    w = Warteschlange(tmp_path, starte)
    a = w.reiche_ein("neu-uebersetzen", BUCH, 1)
    b = w.reiche_ein("neu-uebersetzen", BUCH, 2)
    assert a != b
    assert erstes_laeuft.wait(5)
    time.sleep(0.2)
    assert w.status(a)["zustand"] == "laeuft"
    assert w.status(b)["zustand"] == "wartet"
    assert log == [("start", 1)]                      # der zweite hat nicht begonnen
    erstes_ende.set()
    assert warte_bis(lambda: w.status(b)["zustand"] == "fertig")
    assert log == [("start", 1), ("ende", 1), ("start", 2), ("ende", 2)]
    assert w.status(a) == {"zustand": "fertig", "meldung": ""}


def test_fehler_im_auftrag_setzt_zustand_fehler_und_naechster_laeuft_weiter(tmp_path):
    def starte(job):
        if job["chunk"] == 1:
            raise RuntimeError("Ollama nicht erreichbar")

    w = Warteschlange(tmp_path, starte)
    a = w.reiche_ein("neu-uebersetzen", BUCH, 1)
    assert warte_bis(lambda: w.status(a)["zustand"] == "fehler")
    assert "Ollama nicht erreichbar" in w.status(a)["meldung"]
    b = w.reiche_ein("neu-uebersetzen", BUCH, 2)
    assert warte_bis(lambda: w.status(b)["zustand"] == "fertig")


def test_gleicher_offener_auftrag_wird_nicht_doppelt_eingereiht(tmp_path):
    frei = threading.Event()
    w = Warteschlange(tmp_path, lambda job: frei.wait(5))
    a = w.reiche_ein("neu-uebersetzen", BUCH, 3)
    assert w.reiche_ein("neu-uebersetzen", BUCH, 3) == a
    frei.set()
    assert warte_bis(lambda: w.status(a)["zustand"] == "fertig")
    assert w.reiche_ein("neu-uebersetzen", BUCH, 3) != a      # beendet -> neuer Auftrag erlaubt


def test_ungueltige_auftraege_und_unbekannte_id(tmp_path):
    aufgerufen = []
    w = Warteschlange(tmp_path, aufgerufen.append)
    for args in [("loeschen", BUCH, 0), ("neu-uebersetzen", "../../x/y", 0),
                 ("neu-uebersetzen", "A/CON", 0), ("neu-uebersetzen", BUCH, -1),
                 ("neu-uebersetzen", BUCH, True), ("neu-uebersetzen", BUCH, "1")]:
        with pytest.raises(ValueError):
            w.reiche_ein(*args)
    with pytest.raises(KeyError):
        w.status("gibtsnicht")
    assert aufgerufen == []


def test_lektor_schluessel_gehoert_zum_auftrag_und_zur_doppelpruefung(tmp_path):
    gesehen, frei = [], threading.Event()

    def starte(job):
        gesehen.append((job["buch"], job.get("lektor")))
        assert frei.wait(5)

    w = Warteschlange(tmp_path, starte)
    a = w.reiche_ein("neu-uebersetzen", BUCH, 1, "Lektor A/Ordner")
    b = w.reiche_ein("neu-uebersetzen", BUCH, 1, "Lektor B/Ordner")
    c = w.reiche_ein("neu-uebersetzen", BUCH, 1, "Lektor A/Ordner")
    assert a != b and a == c                      # gleicher Auftrag nicht doppelt, anderes Ziel schon
    frei.set()
    assert warte_bis(lambda: w.status(b)["zustand"] == "fertig")
    assert gesehen == [(BUCH, "Lektor A/Ordner"), (BUCH, "Lektor B/Ordner")]


@pytest.mark.parametrize("lektor", ["../x/y", "A", "/abs/y", 5])
def test_unsicherer_lektor_schluessel_wird_abgelehnt(tmp_path, lektor):
    w = Warteschlange(tmp_path, lambda job: None)
    with pytest.raises(ValueError):
        w.reiche_ein("neu-uebersetzen", BUCH, 1, lektor)
