"""Tests fuer verdacht.js (Verdachtserkennung in Roh-Chunks). Laeuft in Node; ohne Node uebersprungen."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node nicht installiert")

SKRIPT = r"""
const V = require(process.argv[1]);
const R = require(process.argv[2]);
const a = JSON.parse(require("fs").readFileSync(0, "utf8"));
if (a.messen) {
  const t0 = process.hrtime.bigint();
  const h = V.pruefe(a.text);
  const ms = Number(process.hrtime.bigint() - t0) / 1e6;
  process.stdout.write(JSON.stringify({ ms, n: h.length }));
} else {
  const h = V.pruefe(a.text);
  const ankerOk = h.every(x => R.ankerVon(a.text.split(/\n[ \t\r]*\n/).filter(s => s.trim())[x.absatz_index]) === x.anfang);
  process.stdout.write(JSON.stringify({ h, ankerOk }));
}
"""


def lauf(text, **extra):
    r = subprocess.run([NODE, "-e", SKRIPT, str(HIER / "verdacht.js"), str(HIER / "redaktion.js")],
                       input=json.dumps({"text": text, **extra}), capture_output=True, text=True,
                       encoding="utf-8", check=True)
    return json.loads(r.stdout)


def hinweise(text):
    return lauf(text)["h"]


def arten(text):
    return [(h["art"], h["absatz_index"], h["zeile"]) for h in hinweise(text)]


def test_zeile_bricht_ab_tabs_und_crlf():
    text = "Erster Absatz endet sauber.\r\n\r\nDie Abgeordneten\tsind nicht\r\nbloss Delegierte der\r\nwaehler. Ende."
    assert arten(text) == [("zeile-bricht-ab", 1, 0), ("zeile-bricht-ab", 1, 1)]
    h = hinweise(text)[0]
    assert h["vorschlag"]["art"] == "verbinden" and h["zeile_bis"] == 0
    assert h["anfang"] == "Die Abgeordneten sind nicht bloss Delegi"


def test_zeile_bricht_ab_vor_fussnotenzahl():
    text = "Er betonte damals nachdruecklich\n12 Vgl. Pitkin, S. 8.\nDer Satz geht weiter."
    assert ("zeile-bricht-ab", 0, 0) in arten(text)


def test_satzende_bricht_nicht_ab():
    assert arten("Das ist ein ganzer Satz.\nund hier klein weiter.\nNoch einer, oder nicht?\nja doch klein") == []


def test_fragment_kurze_zeile_und_seitenzahl():
    text = "Ein langer vollstaendiger Satz steht hier am Anfang des Absatzes.\n— 47 —\nund weiter geht der Absatz hier."
    h = hinweise(text)
    assert [(x["art"], x["zeile"]) for x in h if x["art"] == "fragment"] == [("fragment", 1)]
    assert h[0]["vorschlag"] == {"art": "loeschen", "parameter": {}}


def test_fragment_seitenzahl_als_eigener_absatz():
    text = "Ein langer Absatz mit genug Text, der sauber endet.\n\n123\n\nNoch ein langer Absatz mit genug Text."
    assert arten(text) == [("fragment", 1, 0)]


def test_fragment_kopfzeile_in_drei_absaetzen():
    kopf = "Elemente und Urspruenge totaler Herrschaft"
    absaetze = [f"{kopf}\nText von Absatz {i} der lang genug ist und sauber endet." for i in range(3)]
    f = [x for x in hinweise("\n\n".join(absaetze)) if x["art"] == "fragment"]
    assert [(x["absatz_index"], x["zeile"]) for x in f] == [(0, 0), (1, 0), (2, 0)]


def test_kopfzeile_nur_in_zwei_absaetzen_ist_kein_fragment():
    kopf = "Eine wiederkehrende aber nur zweimal vorkommende Zeile."
    text = f"{kopf}\nText eins endet hier.\n\n{kopf}\nText zwei endet hier."
    assert [x for x in hinweise(text) if x["art"] == "fragment"] == []


def test_fussnote_marker_ohne_definition_und_umgekehrt():
    text = "Ein Satz mit Marker[^1] und noch einem[^2] hier.\n\n[^2]: Definition zwei.\n\n[^7]: Verwaiste Definition hier."
    f = [(x["absatz_index"], x["zeile"], x["vorschlag"]["parameter"]["kategorie"]) for x in hinweise(text) if x["art"] == "fussnote"]
    assert f == [(0, 0, "fussnote"), (2, 0, "fussnote")]
    assert all(x["vorschlag"]["art"] == "marke" for x in hinweise(text) if x["art"] == "fussnote")


def test_fussnote_vollstaendig_ist_unauffaellig():
    assert arten("Satz mit Marker[^1] im Text hier.\n\n[^1]: Die Definition steht auch da.") == []


def test_ueberschrift_im_text():
    text = "Ein Satz am Anfang des Absatzes endet hier.\n# Kapitel Zwei\nDER ZWEITE TEIL DES BUCHES\nWeiter im Satz hier."
    u = [(x["art"], x["zeile"]) for x in hinweise(text)]
    assert ("ueberschrift-im-text", 1) in u and ("ueberschrift-im-text", 2) in u
    assert [x for x in hinweise(text) if x["art"] == "ueberschrift-im-text"][0]["vorschlag"]["art"] == "marke"


def test_ueberschrift_als_eigener_absatz_ist_in_ordnung():
    assert arten("# Kapitel Eins ist hier\n\nText des ersten Absatzes endet hier.") == []


def test_verzeichnis():
    text = "Inhalt\n" + "\n".join(f"Kapitel {i} .......... {i * 10}" for i in range(1, 6))
    h = [x for x in hinweise(text) if x["art"] == "verzeichnis"]
    assert len(h) == 1 and (h[0]["zeile"], h[0]["zeile_bis"]) == (1, 5)
    assert h[0]["vorschlag"] == {"art": "marke", "parameter": {"kategorie": "verzeichnis"}}
    assert [x for x in hinweise(text) if x["art"] == "fragment" and x["zeile"] > 0] == []


def test_verzeichnis_mit_seitenzahl_am_ende():
    text = "\n".join(f"Das ist Kapitel Nummer {i} {i * 7}" for i in range(1, 5))
    assert [x["art"] for x in hinweise(text)] == ["verzeichnis"]


def test_drei_zeilen_sind_noch_kein_verzeichnis():
    text = "\n".join(f"Kapitel Nummer {i} .......... {i}" for i in range(1, 4))
    assert [x for x in hinweise(text) if x["art"] == "verzeichnis"] == []


def test_glossar():
    text = ("Begriffe\nMacht: die Faehigkeit gemeinsam zu handeln\nGewalt: Mittel der Zwingung\n"
            "Autoritaet: anerkannte Fuehrung\nTerror: Wesen totaler Herrschaft")
    g = [x for x in hinweise(text) if x["art"] == "glossar"]
    assert len(g) == 1 and (g[0]["zeile"], g[0]["zeile_bis"]) == (1, 4)
    assert g[0]["vorschlag"] == {"art": "marke", "parameter": {"kategorie": "glossar"}}


def test_anker_stimmt_mit_redaktion_js_ueberein():
    text = "Kopf\tmit  Tabs und\r\nzweiter Zeile\r\n\r\nzweiter Absatz\nfaengt hier an."
    r = lauf(text)
    assert r["h"] and r["ankerOk"]


def test_leerer_text():
    assert hinweise("") == []
    assert hinweise("\n\n  \n") == []


def test_normaler_text_ergibt_keine_hinweise():
    text = (HIER / "testdaten" / "fliesstext.txt").read_text(encoding="utf-8")
    assert len(text) > 3000
    assert hinweise(text) == []


def test_leistung():
    absatz = ("Der Satz laeuft bis zum Ende und hat etliche Woerter\tmit Tabs,\r\n"
              "bricht aber hart um und\r\n12 Fussnote mitten drin.\r\nKopfzeile\r\n")
    text = (absatz + "\r\n") * (200_000 // (len(absatz) + 2) + 1)
    text = text[:200_000]
    r = lauf(text, messen=True)
    assert r["n"] > 0
    assert r["ms"] < 1000, r["ms"]


def test_leistung_ein_langer_absatz_mit_vielen_hinweisen():
    # 20 000 kurze Zeilen ohne Leerzeile: jede Zeile ein Hinweis; der Anker darf nur einmal je Absatz berechnet werden.
    text = "\n".join(f"z{i % 1000}" for i in range(20_000))
    r = lauf(text, messen=True)
    assert r["n"] >= 20_000
    assert r["ms"] < 2000, r["ms"]


def umbrueche(text):
    return [x for x in arten(text) if x[0] == "zeile-bricht-ab"]


def test_lange_zeile_ohne_satzende_vor_grossem_anfang_ist_umbruch_deutsche_substantive():
    text = "Der amerikanische Film ist das größte unterschwellige\nPropagandamedium unserer Zeit."
    assert arten(text) == [("zeile-bricht-ab", 0, 0)]
    assert "beginnt groß" in hinweise(text)[0]["begruendung"]


def test_grossanfang_ohne_umbruch_bei_kurzer_zeile_ueberschrift_tabelle_liste():
    assert umbrueche("Kurze Zeile ohne Ende\nNeuer Anfang gross.") == []
    assert umbrueche("Eine lange Zeile ohne Satzzeichen am Ende hier\n# Neue Ueberschrift") == []
    assert umbrueche("Eine lange Zeile ohne Satzzeichen am Ende hier\n| Tabelle | Zelle |") == []
    assert umbrueche("Eine lange Zeile ohne Satzzeichen am Ende hier\n- Listenpunkt") == []
    assert umbrueche("EINE LANGE UEBERSCHRIFT OHNE PUNKT AM ENDE HIER\nNeuer Anfang gross.") == []


def test_schwaches_satzende_vor_kleinem_anfang_ist_umbruch():
    for ende in ("der auf der Hut war;", "als Papst Gregor XV.", "im Sinne der Sache (siehe oben)", "sagte er in »Der Feind«"):
        assert arten(f"Er schrieb damals {ende}\nimmer weiter.") == [("zeile-bricht-ab", 0, 0)], ende
    assert arten("Das ist ein ganzer Satz.\nund hier klein weiter.") == []
