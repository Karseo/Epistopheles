"""Tests fuer verbindungen.js (Kern der Ansicht "Verbindungen"): Index, Fokusausschnitt, Filter, Liste, Pruefung. Node; ohne Node uebersprungen."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node nicht installiert")

SKRIPT = r"""
const U = require(process.argv[1]);
const eingabe = JSON.parse(require("fs").readFileSync(0, "utf8"));
const d = eingabe.daten, extra = eingabe.extra;
const t0 = Date.now();
const f = new Function("U", "d", "extra", "return (async () => {" + eingabe.code + "})();");
f(U, d, extra).then((r) => process.stdout.write(JSON.stringify({ r: r, ms: Date.now() - t0 })));
"""


def js(code: str, daten: dict | None = None, extra=None):
    lauf = subprocess.run([NODE, "-e", SKRIPT, str(HIER / "verbindungen.js")], input=json.dumps({"code": code, "daten": daten, "extra": extra}),
                          capture_output=True, text=True, encoding="utf-8", check=True)
    erg = json.loads(lauf.stdout)
    return erg["r"], erg["ms"]


def daten(werke=3, kapitel=4, aehnlich=(), themen=(), querverweise=(), qdrant=...):
    """Werke b001.., je `kapitel` Kapitel b001:1..; aehnlich = [(von, nach, wert)]."""
    ws = [{"id": f"b{w:03d}", "autor": f"Nachname{w}, Vorname", "titel": f"Werk {w}"} for w in range(1, werke + 1)]
    ks = [{"id": f"b{w:03d}:{k}", "werk": f"b{w:03d}", "nr": k, "titel": f"Kapitel {k} von {w}"} for w in range(1, werke + 1) for k in range(1, kapitel + 1)]
    return {"version": 1, "erstellt": "2026-11-03 10:00:00",
            "qdrant": {"abgefragt": 10, "fehlend": 0, "mindestwert": 0.55} if qdrant is ... else qdrant,
            "werke": ws, "kapitel": ks,
            "themen": [{"id": i, "werk": i.split("#")[0], "name": n, "kapitel": nrs} for i, n, nrs in themen],
            "aehnlich": [{"von": v, "nach": n, "wert": w, "beleg": f"Beleg {v}->{n}"} for v, n, w in aehnlich],
            "querverweise": [{"von": v, "nach": n, "autor": a, "titel": t, "relation": r, "notiz": "Notiz"} for v, n, a, t, r in querverweise]}


def ids(knoten, ring=None):
    return [k["id"] for k in knoten if ring is None or k["ring"] == ring]


def test_aehnlichkeit_beider_richtungen_wird_zu_einer_kante_mit_dem_maximum():
    d = daten(aehnlich=[("b001:1", "b002:1", 0.7), ("b002:1", "b001:1", 0.8)])
    r, _ = js('const g = U.baue(d); const f = U.fokus(g, "b001:1"); return f.kanten.filter(k => k.art === "aehnlich");', d)
    assert len(r) == 1 and r[0]["wert"] == 0.8
    assert r[0]["beleg"] == "Beleg b002:1->b001:1"                                  # der Beleg der besseren Richtung


def test_selbstkanten_unbekannte_knoten_und_dubletten_werden_ignoriert():
    d = daten(aehnlich=[("b001:1", "b001:1", 0.9), ("b001:1", "b999:1", 0.9), ("b999:9", "b001:1", 0.9), ("b001:1", "b002:1", 0.6), ("b001:1", "b002:1", 0.6)])
    r, _ = js('const f = U.fokus(U.baue(d), "b001:1"); return f.kanten.filter(k => k.art === "aehnlich").map(k => [k.von, k.nach]);', d)
    assert r == [["b001:1", "b002:1"]]


def test_fokus_kapitel_hat_werk_themen_und_aehnliche_in_ring_1():
    d = daten(aehnlich=[("b001:1", "b002:1", 0.9), ("b003:2", "b001:1", 0.7)], themen=[("b001#macht", "Macht", [1, 2])])
    r, _ = js('const f = U.fokus(U.baue(d), "b001:1"); return { ring0: f.knoten.filter(k => k.ring === 0).map(k => k.id), ring1: f.knoten.filter(k => k.ring === 1).map(k => [k.id, k.typ, k.label]) };', d)
    assert r["ring0"] == ["b001:1"]
    assert sorted(i for i, _, _ in r["ring1"]) == ["b001", "b001#macht", "b002:1", "b003:2"]
    assert [i for i, _, _ in r["ring1"]][:2] == ["b002:1", "b003:2"]                  # aehnliche zuerst, nach Wert
    labels = {i: [t, l] for i, t, l in r["ring1"]}
    assert labels["b002:1"] == ["kapitel", "Nachname2 · Kapitel 1 von 2"] and labels["b001#macht"] == ["thema", "Macht"]
    assert labels["b001"] == ["werk", "Nachname1 · Werk 1"]


def test_obergrenze_ring_1_reserviert_plaetze_fuer_werk_und_themen():
    d = daten(werke=3, kapitel=12, themen=[("b001#a", "A", [1, 2]), ("b001#b", "B", [1, 3])],
              aehnlich=[(f"b002:{k}", "b001:1", 0.9 - k / 100) for k in range(1, 13)] + [(f"b003:{k}", "b001:1", 0.6 - k / 100) for k in range(1, 13)])
    r, _ = js('const f = U.fokus(U.baue(d), "b001:1"); return f.knoten.filter(k => k.ring === 1).map(k => k.id);', d)
    assert len(r) == 14 and {"b001", "b001#a", "b001#b"} <= set(r)               # Struktur bleibt, auch wenn es mehr Aehnliche gibt
    aehnliche = [i for i in r if ":" in i]
    assert aehnliche == [f"b002:{k}" for k in range(1, 12)]                       # die besten 11 nach Wert


def test_ring_2_ist_verblasst_hat_ueber_und_keine_kanten_zur_mitte():
    d = daten(aehnlich=[("b001:1", "b002:1", 0.9), ("b002:1", "b003:1", 0.8), ("b002:1", "b003:2", 0.7)],
              querverweise=[("b001", None, "Weber", "Wirtschaft und Gesellschaft", "ergaenzt")])
    r, _ = js('''const f = U.fokus(U.baue(d), "b001:1");
      return { ring2: f.knoten.filter(k => k.ring === 2).map(k => [k.id, k.ueber]), kanten: f.kanten.map(k => [k.von, k.nach, k.art]),
               ring1: f.knoten.filter(k => k.ring === 1).map(k => k.id) };''', d)
    ring2 = {i: u for i, u in r["ring2"]}
    assert ring2["b003:1"] == "b002:1" and ring2["b003:2"] == "b002:1"
    assert any(i.startswith("x:") for i in ring2) and ring2[[i for i in ring2 if i.startswith("x:")][0]] == "b001"       # Querverweis ueber das Werk
    sichtbar = set(r["ring1"]) | {"b001:1"}
    assert all(v in sichtbar and n in sichtbar for v, n, _ in r["kanten"])          # Kanten nur zwischen Mitte und Ring 1 (und Ring 1 untereinander)


def test_kanten_zwischen_ring_1_knoten_bleiben():
    d = daten(aehnlich=[("b001:1", "b002:1", 0.9), ("b001:1", "b003:1", 0.8), ("b002:1", "b003:1", 0.7)])
    r, _ = js('const f = U.fokus(U.baue(d), "b001:1"); return f.kanten.filter(k => k.art === "aehnlich").map(k => [k.von, k.nach]);', d)
    assert sorted(r) == [["b001:1", "b002:1"], ["b001:1", "b003:1"], ["b002:1", "b003:1"]]


def test_filter_nach_kantenart_gilt_auch_fuer_ring_2():
    d = daten(aehnlich=[("b001:1", "b002:1", 0.9), ("b002:1", "b003:1", 0.8)], themen=[("b001#macht", "Macht", [1, 2])])
    r, _ = js('''const g = U.baue(d);
      const ohneA = U.fokus(g, "b001:1", { arten: { aehnlich: false } }), ohneT = U.fokus(g, "b001:1", { arten: { thema: false } });
      return { ohneA: ohneA.knoten.map(k => k.id).sort(), ohneT: ohneT.knoten.map(k => k.id).sort(), artenA: [...new Set(ohneA.kanten.map(k => k.art))].sort() };''', d)
    assert "b002:1" not in r["ohneA"] and "b003:1" not in r["ohneA"] and "b001#macht" in r["ohneA"] and "aehnlich" not in r["artenA"]
    assert "b001#macht" not in r["ohneT"] and "b002:1" in r["ohneT"]


def test_fokus_thema_und_werk_und_hohles_werk():
    d = daten(themen=[("b001#macht", "Macht", [1, 3])], querverweise=[("b001", "b002", "N2", "Werk 2", "ergaenzt"), ("b001", None, "Weber", "Wirtschaft und Gesellschaft", "bezieht-sich-auf")])
    r, _ = js('''const g = U.baue(d);
      const t = U.fokus(g, "b001#macht"), w = U.fokus(g, "b001"), hohl = g.knoten.get([...g.knoten.keys()].find(k => k.startsWith("x:")));
      return { thema: t.knoten.filter(k => k.ring === 1).map(k => k.id), werk: w.knoten.filter(k => k.ring === 1).map(k => k.id),
               querLabels: w.kanten.filter(k => k.art === "querverweis").map(k => k.label).sort(),
               hohl: [hohl.typ, hohl.offen, hohl.label], hohlFokus: U.fokus(g, hohl.id), };''', d)
    assert r["thema"] == ["b001:1", "b001:3"]
    extern = [i for i in r["werk"] if i.startswith("x:")][0]
    assert r["werk"][:2] == ["b002", extern]                                        # Querverweise vor den eigenen Kapiteln, Gleichstand nach Id
    assert r["querLabels"] == ["bezieht sich auf", "ergänzt"]
    assert r["hohl"] == ["werk", False, "Weber · Wirtschaft und Gesellschaft"]
    assert r["hohlFokus"]["knoten"] == [] and r["hohlFokus"]["fehler"]


def test_unbekannter_fokus_ist_leer_ohne_ausnahme():
    r, _ = js('return U.fokus(U.baue(d), "gibt-es-nicht");', daten())
    assert r["knoten"] == [] and r["kanten"] == [] and r["fehler"]


def test_ausgabe_ist_deterministisch_und_unabhaengig_von_der_eingabereihenfolge():
    kanten = [("b001:1", "b002:1", 0.8), ("b001:1", "b003:1", 0.8), ("b001:1", "b002:2", 0.8), ("b003:2", "b001:1", 0.8)]
    a, _ = js('return U.fokus(U.baue(d), "b001:1");', daten(aehnlich=kanten))
    b, _ = js('return U.fokus(U.baue(d), "b001:1");', daten(aehnlich=list(reversed(kanten))))
    assert a == b                                                                   # Gleichstand entscheidet die Id


def test_liste_gruppiert_dieselben_daten():
    d = daten(aehnlich=[("b001:1", "b002:1", 0.9)], themen=[("b001#macht", "Macht", [1, 2])],
              querverweise=[("b001", None, "Weber", "WuG", "ergaenzt")])
    r, _ = js('''const g = U.baue(d);
      const l = (id) => U.liste(g, id).map(x => [x.gruppe, x.eintraege.map(e => e.id)]);
      return { kapitel: l("b001:1"), werk: l("b001"), thema: l("b001#macht"), beleg: U.liste(g, "b001:1")[0].eintraege[0] };''', d)
    assert [g for g, _ in r["kapitel"]] == ["Ähnliche Stellen", "Themen", "Werk"]
    assert r["beleg"]["wert"] == 0.9 and r["beleg"]["beleg"] == "Beleg b001:1->b002:1" and r["beleg"]["label"].startswith("Nachname2")
    assert [g for g, _ in r["werk"]] == ["Querverweise", "Kapitel"] and r["werk"][1][1] == ["b001:1", "b001:2", "b001:3", "b001:4"]
    assert [g for g, _ in r["thema"]] == ["Kapitel in diesem Thema"] and r["thema"][0][1] == ["b001:1", "b001:2"]


def test_pruefe_ok_bei_gleichem_export_und_bekannten_kapiteln():
    d = daten()
    tage = {"erstellt": d["erstellt"], "buecher": [{"id": f"b{w:03d}", "kapitel": [{"nr": k} for k in range(1, 5)]} for w in range(1, 4)]}
    r, _ = js("return U.pruefe(d, extra);", d, tage)
    assert r["ok"] is True and r["grund"] == "" and r["hinweise"] == []


def test_pruefe_meldet_anderen_export_unbekannte_kapitel_und_fehlende_aehnlichkeit():
    d = daten()
    tage = {"erstellt": d["erstellt"], "buecher": [{"id": "b001", "kapitel": [{"nr": 1}]}]}
    r, _ = js("return U.pruefe(d, extra);", d, tage)
    assert r["ok"] is False and "daten.json" in r["grund"] and r["fehlend"][0] == "b001:2"
    r, _ = js("return U.pruefe(d, extra);", d, {"erstellt": "anderer", "buecher": []})
    assert r["ok"] is False and "anderen Export" in r["grund"]
    ok = {"erstellt": d["erstellt"], "buecher": [{"id": f"b{w:03d}", "kapitel": [{"nr": k} for k in range(1, 5)]} for w in range(1, 4)]}
    r, _ = js("return U.pruefe(d, extra);", daten(qdrant=None), ok)
    assert r["ok"] is True and any("fehlen" in h for h in r["hinweise"])
    r, _ = js("return U.pruefe(d, extra);", daten(qdrant={"abgefragt": 10, "fehlend": 3, "mindestwert": 0.55}), ok)
    assert r["ok"] is True and any("unvollständig" in h and "3" in h for h in r["hinweise"])
    r, _ = js("return U.pruefe(d, extra);", {**d, "version": 2}, ok)
    assert r["ok"] is False and "Version" in r["grund"]


def test_pruefe_und_baue_vertragen_kaputte_eingaben():
    r, _ = js("return [U.pruefe(null, extra).ok, U.pruefe({}, null).ok, U.pruefe({version: 1}, {}).ok];", None, None)
    assert r == [False, False, False]
    r, _ = js('const g = U.baue({ version: 1, kapitel: "x", werke: null, aehnlich: [null, 5, {}], themen: [{}], querverweise: [{ von: "b1" }] }); return U.fokus(g, "b1:1").knoten;', None)
    assert r == []


def test_leistung_950_kapitel_7600_kanten():
    n_werke, je = 80, 12
    d = daten(werke=n_werke, kapitel=je)
    ids_ = [k["id"] for k in d["kapitel"]]
    d["aehnlich"] = [{"von": ids_[i], "nach": ids_[(i * 7 + j * 13 + 5) % len(ids_)], "wert": 0.55 + (i * j % 40) / 100, "beleg": "Beleg"} for i in range(len(ids_)) for j in range(1, 9)]
    d["themen"] = [{"id": f"b{w:03d}#t{t}", "werk": f"b{w:03d}", "name": f"Thema {t}", "kapitel": [1, 2, 3, 4, 5]} for w in range(1, n_werke + 1) for t in range(3)]
    r, ms = js('const t0 = Date.now(); const g = U.baue(d); const t1 = Date.now(); const f = U.fokus(g, "b010:3"); return [t1 - t0, Date.now() - t1, f.knoten.length];', d)
    bauen, fokus, knoten = r
    assert bauen < 1000 and fokus < 50 and 1 < knoten <= 29                         # Plan: Ziel 300 ms und 10 ms, grosszuegige Grenzen
