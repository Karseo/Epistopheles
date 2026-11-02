"""Tests fuer chunkansicht.js (Logik ohne DOM: bereite, entwurf, signatur). Laeuft in Node; ohne Node uebersprungen."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node nicht installiert")

SKRIPT = r"""
const C = require(process.argv[1]);
const R = require(process.argv[2]);
const a = JSON.parse(require("fs").readFileSync(0, "utf8"));
const roh = a.roh;
const ans0 = C.bereite(roh, [], 0, [], true);
const h = ans0.hinweise.find(x => x.art === "zeile-bricht-ab");
const d = C.entwurf(ans0, "annehmen", h);
const e = Object.assign(R.neuerEintrag("A/B", "chunk-orig", d.ziel, d.art, d.parameter, d.vorherText, d.hinweis, "g"), {status: "offen"});
const eintraege = [e];
const ans1 = C.bereite(roh, eintraege, 0, [], true);
const abg = C.bereite(roh, [], 0, [{anfang: h.anfang, art: h.art, zeile: C.zeilenSchluessel("Die Abgeordneten\tsind nicht")}], true);
const e2 = Object.assign({}, e, {id: "zweiter", status: "konflikt", grund: "x"});
const ans2 = C.bereite(roh, [e2], 0, [], true);
const unbereit = C.bereite(roh, [], 0, [], false);
const mk = R.neuerEintrag("A/B", "chunk-orig", {chunk: 0, anfang: h.anfang, absatz_index: h.absatz_index, zeile: h.zeile}, "marke", {kategorie: "x"}, "", "", "g");
const ans3 = C.bereite(roh, [mk], 0, [], true);
// Neu anwenden: Konflikt-Eintrag (Hash passt nicht mehr) -> Entwurf auf dem aktuellen Absatztext
const alt = Object.assign(R.neuerEintrag("A/B", "chunk-orig", {chunk: 0, anfang: h.anfang, absatz_index: h.absatz_index, zeile: h.zeile},
                                          "verbinden", {}, "ganz anderer frueherer Text", "Hinweis", "g"), {status: "offen"});
const ansK = C.bereite(roh, [alt], 0, [], true);
const kf = ansK.konflikte[0];
const neuEntwurf = kf && C.entwurf(ansK, "neu", kf);
const neuEntwurfEintrag = neuEntwurf && R.neuerEintrag("A/B", "chunk-orig", neuEntwurf.ziel, neuEntwurf.art, neuEntwurf.parameter, neuEntwurf.vorherText, neuEntwurf.hinweis, "g");
const ansN = C.bereite(roh, [alt, Object.assign(neuEntwurfEintrag, {status: "offen"}), R.ruecknahmeFuer(alt, "g", "Konflikt verworfen", "A/B")], 0, [], true);
const neuOhneAbsatz = C.entwurf(ansK, "neu", {eintrag: alt, absatz_index: null});
process.stdout.write(JSON.stringify({
  konfliktGrund: kf && kf.grund, konfliktAbsatz: kf && kf.absatz_index, nachNeu: {konflikte: ansN.konflikte.length, text: ansN.text},
  absatzText: kf && C.absatzText(ansK, kf.absatz_index),
  vorher: ans0.hinweise.length, nachher: ans1.hinweise.length, text1: ans1.text, roh: ans0.text,
  abgelehnt: abg.hinweise.length, konflikt: ans2.konflikte.length, konfAbsatz: ans2.konflikte[0] && ans2.konflikte[0].absatz_index,
  unbereit: unbereit.hinweise.length, marke: ans3.hinweise.length, erledigt: ans3.erledigt.length,
  entwurf: d, neuEntwurf: neuEntwurf, neuOhneAbsatz: neuOhneAbsatz, sigA: C.signatur(eintraege, 0, 0, true), sigB: C.signatur([], 0, 0, true), sigC: C.signatur(eintraege, 1, 0, true),
}));
"""

ROH = "Erster Absatz endet sauber.\r\n\r\nDie Abgeordneten\tsind nicht\r\nbloss Delegierte der\r\nwaehler. Ende."


def lauf():
    r = subprocess.run([NODE, "-e", SKRIPT, str(HIER / "chunkansicht.js"), str(HIER / "redaktion.js")],
                       input=json.dumps({"roh": ROH}), capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(r.stdout)


def test_annehmen_verbindet_ohne_andere_bytes_zu_aendern():
    e = lauf()
    assert e["roh"] == ROH and e["vorher"] == 2 and e["nachher"] == 1
    assert e["text1"].startswith("Erster Absatz endet sauber.\r\n\r\nDie Abgeordneten\tsind nicht bloss Delegierte der\r\n")
    assert e["entwurf"]["art"] == "verbinden" and e["entwurf"]["ziel"]["chunk"] == 0


def test_abgelehnt_marke_konflikt_und_unbereit():
    e = lauf()
    assert e["abgelehnt"] == 1                 # der zweite Hinweis (Zeile 1) bleibt
    assert e["konflikt"] == 1 and e["konfAbsatz"] == 1
    assert e["unbereit"] == 0                  # vor dem Laden der Eintraege keine Hinweise
    assert e["marke"] == 1 and e["erledigt"] == 1


def test_neu_anwenden_entwurf_nimmt_aktuellen_absatz_und_loest_den_konflikt():
    e = lauf()
    assert "geändert" in e["konfliktGrund"] and e["konfliktAbsatz"] == 1
    d = e["neuEntwurf"]
    assert d["art"] == "verbinden" and d["hinweis"] == "Hinweis"
    assert d["ziel"]["chunk"] == 0 and d["ziel"]["absatz_index"] == 1 and d["ziel"]["zeile"] == 0
    assert d["vorherText"] == e["absatzText"] != "ganz anderer frueherer Text"      # Hash des heutigen Absatzes, nicht des alten
    assert e["neuOhneAbsatz"] is None                                              # ohne gefundenen Absatz kein Entwurf
    # neuer Eintrag + Rücknahme des alten: kein Konflikt mehr, der Absatz ist verbunden
    assert e["nachNeu"]["konflikte"] == 0
    assert "Die Abgeordneten\tsind nicht bloss Delegierte der\r\n" in e["nachNeu"]["text"]


def test_signatur_haengt_nur_von_eigenem_chunk_ab():
    e = lauf()
    assert e["sigA"] != e["sigB"] and e["sigC"] == e["sigB"]


SKRIPT_B = r"""
const C = require(process.argv[1]);
const R = require(process.argv[2]);
const roh = "Ab-\r\ncd\r\nEf gh\r\n\r\nZweiter\tAbsatz mit einem gemeinsamen langen\r\nhier.\r\n\r\nZweiter\tAbsatz mit einem gemeinsamen langen\r\nanders.";
const ans = C.bereite(roh, [], 0, [], true);
const at = (s) => roh.indexOf(s);
const a = C.auswahlAbbilden(ans, at("Ab"), at("Ef gh") + 5);              // Zeilen 0 bis 2, Absatz 0
const v = C.entwuerfe(ans, "verbinden", a, {});
const eintraege = v.liste.map((d) => Object.assign(R.neuerEintrag("A/B", "chunk-orig", d.ziel, d.art, d.parameter, d.vorherText, d.hinweis, "g"), {status: "offen"}));
const lauf = R.spieleAb(roh, eintraege);
const rand = C.auswahlAbbilden(ans, at("Ab"), at("Ab") + 2);                // nur "Ab"
const blank = C.auswahlAbbilden(ans, at("Ef gh") + 5, at("Zweiter"));        // nur Leerraum
const zwei = C.auswahlAbbilden(ans, at("Ef"), at("hier"));                  // ueber zwei Absaetze
const z2 = C.auswahlAbbilden(ans, at("hier"), at("hier") + 4);              // Absatz 1, letzte Zeile
const ver = C.entwuerfe(ans, "verschieben", z2, {ziel_absatz: 0});
const verDoppelt = C.entwuerfe(ans, "verschieben", a, {ziel_absatz: 2});
const verSelbst = C.entwuerfe(ans, "verschieben", a, {ziel_absatz: 0});
const verMehr = C.entwuerfe(ans, "verschieben", zwei, {ziel_absatz: 2});
const mk = C.entwuerfe(ans, "kapitel", z2, {});
const mkZwei = C.entwuerfe(ans, "glossar", zwei, {text: "  Notiz  "});
const letzte = C.auswahlAbbilden(ans, at("Ef"), at("Ef") + 2);
process.stdout.write(JSON.stringify({
  a: a, v: v, text: lauf.text, status: lauf.ergebnisse.map((r) => r.status),
  rand: rand && [rand.zeile, rand.zeile_bis], blank: blank, zwei: zwei && {m: zwei.mehrere, i: zwei.absatz_index, b: zwei.absatz_bis},
  z2: z2 && [z2.absatz_index, z2.zeile, z2.zeile_bis], ver: ver, verDoppelt: verDoppelt, verSelbst: verSelbst, verMehr: verMehr,
  mk: mk, mkZwei: mkZwei, werkZwei: C.werkzeuge(zwei), werkLetzte: C.werkzeuge(letzte), werkErste: C.werkzeuge(rand),
}));
"""


def lauf_b():
    r = subprocess.run([NODE, "-e", SKRIPT_B, str(HIER / "chunkansicht.js"), str(HIER / "redaktion.js")],
                       capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(r.stdout)


def test_auswahl_wird_auf_absatz_und_zeilen_abgebildet():
    e = lauf_b()
    assert (e["a"]["absatz_index"], e["a"]["zeile"], e["a"]["zeile_bis"], e["a"]["mehrere"]) == (0, 0, 2, False)
    assert e["rand"] == [0, 0] and e["blank"] is None
    assert e["zwei"] == {"m": True, "i": 0, "b": 1}
    assert e["z2"] == [1, 1, 1]


def test_verbinden_kette_passt_nacheinander_auch_wenn_der_anker_sich_aendert():
    e = lauf_b()
    assert len(e["v"]["liste"]) == 2 and [x["ziel"]["zeile"] for x in e["v"]["liste"]] == [0, 0]
    assert e["v"]["liste"][0]["ziel"]["anfang"] != e["v"]["liste"][1]["ziel"]["anfang"]     # Anker aus dem abgespielten Text
    assert e["status"] == ["angewendet", "angewendet"]
    assert e["text"] == "Abcd Ef gh\r\n\r\nZweiter\tAbsatz mit einem gemeinsamen langen\r\nhier.\r\n\r\nZweiter\tAbsatz mit einem gemeinsamen langen\r\nanders."   # sonst kein Byte veraendert


def test_verschieben_markieren_und_werkzeugwahl():
    e = lauf_b()
    assert e["ver"]["liste"][0]["art"] == "verschieben" and e["ver"]["liste"][0]["parameter"]["nach_anfang"] == "Ab- cd Ef gh"
    assert "fehler" in e["verDoppelt"]                                                   # Zielabsatz 2 beginnt wie Absatz 1: nicht eindeutig
    assert "Quellabsatz" in e["verSelbst"]["fehler"] and "fehler" in e["verMehr"]
    assert e["mk"]["liste"][0]["parameter"] == {"kategorie": "kapitelgrenze-vermutet"} and e["mk"]["liste"][0]["art"] == "marke"
    p = e["mkZwei"]["liste"][0]["parameter"]
    assert p["kategorie"] == "glossar" and p["text"] == "Notiz" and p["bis_absatz_index"] == 1
    assert [e["werkZwei"][k] for k in ("verbinden", "verschieben", "loeschen", "trennen", "kapitel")] == [False] * 5
    assert [e["werkZwei"][k] for k in ("verzeichnis", "glossar", "markieren")] == [True] * 3
    assert e["werkLetzte"]["verbinden"] is False and e["werkErste"]["trennen"] is False and e["werkErste"]["verbinden"] is True
