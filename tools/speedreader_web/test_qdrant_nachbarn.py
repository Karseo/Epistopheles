"""Tests fuer qdrant_nachbarn.py: Qdrant nur lesend abfragen und Chunk-Nachbarn zu Kapitelkanten zusammenfassen.
Eine Attrappe auf http.server bildet die benutzten Teile der Qdrant-Schnittstelle (Version 1.18) nach."""
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent))

import qdrant_nachbarn as qn  # noqa: E402


class FakeQdrant:
    """Punkte {id: payload}; `nachbarn` {id: [(id, wert), ...]} absteigend. Schalter fuer Fehlerfaelle."""

    def __init__(self, punkte: dict, nachbarn: dict):
        self.punkte, self.nachbarn = punkte, nachbarn
        self.anfragen: list[tuple[str, str, object]] = []
        self.query_404 = False            # aeltere Version: keine Query-API
        self.batch_500 = False            # Batch-Aufrufe scheitern (Einzelaufrufe gehen)
        self.immer_500: set[int] = set()  # fuer diese Punkt-Ids scheitert jede Abfrage
        self.erste_503 = 0                # so viele Antworten zuerst 503 (Wiederholungstest)
        handler = self._handler()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown(); self.server.server_close()

    def _treffer(self, pid: int, limit: int, filt: dict | None, include: list[str]) -> list[dict]:
        quelle = self.punkte[pid]
        aus = []
        for nid, wert in self.nachbarn.get(pid, []):
            p = self.punkte[nid]
            if filt:                                     # must_not [{must: [autor, buch]}]: dasselbe Werk ausschliessen
                bed = filt["must_not"][0]["must"]
                werte = {b["key"]: b["match"]["value"] for b in bed}
                if all(p.get(k) == v for k, v in werte.items()):
                    continue
            aus.append({"id": nid, "score": wert, "payload": {k: p[k] for k in include if k in p}})
        return aus[:limit]

    def _handler(fake):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def _antwort(self, status, obj):
                roh = json.dumps(obj).encode("utf-8")
                self.send_response(status); self.send_header("Content-Type", "application/json")   # ohne charset, wie Qdrant
                self.send_header("Content-Length", str(len(roh))); self.end_headers(); self.wfile.write(roh)

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(n).decode("utf-8")) if n else None

            def do_GET(self):
                fake.anfragen.append(("GET", self.path, None))
                if re.fullmatch(r"/collections/episto", self.path):
                    return self._antwort(200, {"result": {"points_count": len(fake.punkte)}})
                self._antwort(405, {"status": {"error": "nicht erlaubt"}})

            def do_POST(self):
                body = self._body()
                fake.anfragen.append(("POST", self.path, body))
                if fake.erste_503 > 0:
                    fake.erste_503 -= 1
                    return self._antwort(503, {})
                pfad = self.path
                if pfad == "/collections/episto/points/scroll":
                    ids = sorted(fake.punkte)
                    start = ids.index(body["offset"]) if body.get("offset") is not None else 0
                    seite = ids[start:start + body["limit"]]
                    inc = body["with_payload"]["include"]
                    nxt = ids[start + body["limit"]] if start + body["limit"] < len(ids) else None
                    return self._antwort(200, {"result": {"points": [{"id": i, "payload": {k: fake.punkte[i][k] for k in inc}} for i in seite],
                                                          "next_page_offset": nxt}})
                if pfad in ("/collections/episto/points/query/batch", "/collections/episto/points/query") and fake.query_404:
                    return self._antwort(404, {"status": {"error": "Not found"}})
                if pfad == "/collections/episto/points/query/batch":
                    if fake.batch_500:
                        return self._antwort(500, {})
                    erg = []
                    for s in body["searches"]:
                        if s["query"] in fake.immer_500:
                            return self._antwort(500, {})
                        erg.append({"points": fake._treffer(s["query"], s["limit"], s.get("filter"), s["with_payload"]["include"])})
                    return self._antwort(200, {"result": erg})
                if pfad == "/collections/episto/points/query":
                    if body["query"] in fake.immer_500:
                        return self._antwort(500, {})
                    return self._antwort(200, {"result": {"points": fake._treffer(body["query"], body["limit"], body.get("filter"), body["with_payload"]["include"])}})
                if pfad == "/collections/episto/points/recommend/batch":
                    erg = []
                    for s in body["searches"]:
                        if s["positive"][0] in fake.immer_500:
                            return self._antwort(500, {})
                        erg.append(fake._treffer(s["positive"][0], s["limit"], s.get("filter"), s["with_payload"]["include"]))
                    return self._antwort(200, {"result": erg})
                self._antwort(405, {"status": {"error": "nicht erlaubt"}})

            def do_PUT(self):
                fake.anfragen.append(("PUT", self.path, None)); self._antwort(405, {})

            def do_DELETE(self):
                fake.anfragen.append(("DELETE", self.path, None)); self._antwort(405, {})
        return H


def payload(autor, buch, nr, idx=0, text="Text"):
    return {"autor": autor, "buch": buch, "kapitel_nr": nr, "chunk_idx": idx, "text": text}


WERKE = {("A, A", "Alpha"): "b001", ("B, B", "Beta"): "b002", ("C, C", "Gamma"): "b003"}
KAPITEL = {"b001:1", "b001:2", "b002:1", "b002:2", "b003:1"}


@pytest.fixture()
def fake():
    punkte = {1: payload("A, A", "Alpha", 1, 0), 2: payload("A, A", "Alpha", 1, 1), 3: payload("A, A", "Alpha", 2, 0),
              10: payload("B, B", "Beta", 1, 0, "Ein langer Text " * 20), 11: payload("B, B", "Beta", 2, 0, "Zweites\n\nKapitel\tmit   Leerraum"),
              12: payload("B, B", "Beta", 1, 1), 20: payload("C, C", "Gamma", 1, 0)}
    nachbarn = {1: [(10, 0.9), (2, 0.85), (12, 0.8), (20, 0.6)], 2: [(10, 0.7), (11, 0.65)], 3: [(20, 0.8)],
                10: [(1, 0.9), (11, 0.88)], 11: [(2, 0.65)], 12: [(1, 0.8)], 20: [(3, 0.8), (1, 0.6)]}
    f = FakeQdrant(punkte, nachbarn)
    yield f
    f.stop()


# --- lese_punkte ------------------------------------------------------------------------------------------

def test_lese_punkte_ueber_mehrere_seiten_nur_payload_ohne_vektoren(fake):
    punkte = qn.lese_punkte(fake.url, "episto", seite=3, pause=0)
    assert set(punkte) == set(fake.punkte)
    assert punkte[10] == {"autor": "B, B", "buch": "Beta", "kapitel_nr": 1, "chunk_idx": 0}      # kein Text, kein Vektor
    scrolls = [a for a in fake.anfragen if a[1].endswith("/scroll")]
    assert len(scrolls) == 3 and all(a[2]["with_vector"] is False for a in scrolls)
    assert scrolls[0][2]["with_payload"] == {"include": ["autor", "buch", "kapitel_nr", "chunk_idx"]}


# --- frage_nachbarn -----------------------------------------------------------------------------------------

def test_frage_nachbarn_filtert_dasselbe_werk_serverseitig_und_kuerzt_den_beleg(fake):
    punkte = qn.lese_punkte(fake.url, "episto", pause=0)
    erg = qn.frage_nachbarn(fake.url, "episto", punkte, [1, 2, 3], je=5, batch=2, pause=0)
    assert erg.fehlend == 0 and erg.abgefragt == 3
    assert [t["id"] for t in erg.treffer[1]] == [10, 12, 20]                    # Punkt 2 (gleiches Werk) fehlt
    t = erg.treffer[1][0]
    assert t["wert"] == 0.9 and (t["autor"], t["buch"], t["kapitel_nr"]) == ("B, B", "Beta", 1)
    assert len(t["text"]) <= 141 and t["text"].endswith("…")
    q = next(a for a in fake.anfragen if a[1].endswith("/query/batch"))
    assert q[2]["searches"][0]["filter"] == {"must_not": [{"must": [{"key": "autor", "match": {"value": "A, A"}}, {"key": "buch", "match": {"value": "Alpha"}}]}]}
    assert q[2]["searches"][0]["query"] == 1 and q[2]["searches"][0]["limit"] == 5            # Punkt-Id als Eingabe: kein Ollama noetig


def test_beleg_wird_einzeilig(fake):
    punkte = qn.lese_punkte(fake.url, "episto", pause=0)
    erg = qn.frage_nachbarn(fake.url, "episto", punkte, [2], je=5, pause=0)
    assert [t["text"] for t in erg.treffer[2] if t["id"] == 11] == ["Zweites Kapitel mit Leerraum"]


def test_batches_werden_gebildet(fake):
    punkte = qn.lese_punkte(fake.url, "episto", pause=0)
    qn.frage_nachbarn(fake.url, "episto", punkte, [1, 2, 3, 10, 11], je=3, batch=2, pause=0)
    assert len([a for a in fake.anfragen if a[1].endswith("/query/batch")]) == 3


def test_rueckfall_auf_recommend_wenn_die_query_api_fehlt(fake):
    fake.query_404 = True
    punkte = qn.lese_punkte(fake.url, "episto", pause=0)
    erg = qn.frage_nachbarn(fake.url, "episto", punkte, [1, 3], je=5, pause=0)
    assert erg.fehlend == 0 and [t["id"] for t in erg.treffer[1]] == [10, 12, 20]
    assert any(a[1].endswith("/recommend/batch") for a in fake.anfragen)
    rec = next(a for a in fake.anfragen if a[1].endswith("/recommend/batch"))
    assert rec[2]["searches"][0]["positive"] == [1]


def test_netzfehler_werden_wiederholt(fake):
    fake.erste_503 = 2
    punkte = qn.lese_punkte(fake.url, "episto", pause=0)                         # die ersten zwei Anfragen scheitern, danach geht es
    assert set(punkte) == set(fake.punkte)


def test_fehlgeschlagener_batch_faellt_auf_einzelabfragen_zurueck_und_zaehlt_nur_echte_ausfaelle(fake):
    fake.batch_500 = True
    fake.immer_500 = {3}
    punkte = qn.lese_punkte(fake.url, "episto", pause=0)
    erg = qn.frage_nachbarn(fake.url, "episto", punkte, [1, 2, 3], je=5, batch=3, pause=0)
    assert erg.fehlend == 1 and erg.abgefragt == 3
    assert 1 in erg.treffer and 2 in erg.treffer and 3 not in erg.treffer         # der Rest wird trotzdem geliefert


def test_anhaltender_serverfehler_bricht_nicht_ab_sondern_zaehlt(fake):
    fake.immer_500 = {1, 2, 3}
    fake.batch_500 = True
    punkte = qn.lese_punkte(fake.url, "episto", pause=0)
    erg = qn.frage_nachbarn(fake.url, "episto", punkte, [1, 2, 3], je=5, pause=0, versuche=2)
    assert erg.fehlend == 3 and erg.treffer == {}


def test_unbekannter_punkt_ohne_payload_zaehlt_als_fehlend(fake):
    punkte = qn.lese_punkte(fake.url, "episto", pause=0)
    erg = qn.frage_nachbarn(fake.url, "episto", punkte, [999], je=5, pause=0)
    assert erg.fehlend == 1 and erg.treffer == {}


# --- nur lesend ---------------------------------------------------------------------------------------------------

def test_ausschliesslich_lesende_aufrufe(fake):
    punkte = qn.lese_punkte(fake.url, "episto", pause=0)
    qn.frage_nachbarn(fake.url, "episto", punkte, list(punkte), je=5, pause=0)
    erlaubt = (r"/collections/episto/points/scroll", r"/collections/episto/points/query(/batch)?", r"/collections/episto/points/recommend(/batch)?", r"/collections/episto")
    assert fake.anfragen and all(a[0] in ("GET", "POST") and any(re.fullmatch(p, a[1]) for p in erlaubt) for a in fake.anfragen)


def test_standard_abruf_verweigert_schreibende_und_fremde_aufrufe(fake):
    for methode, pfad in (("PUT", "/collections/episto/points"), ("DELETE", "/collections/episto"),
                          ("POST", "/collections/episto/points/delete"), ("POST", "/collections/episto/points/payload"),
                          ("POST", "/collections/episto/snapshots"), ("GET", "/cluster")):
        with pytest.raises(ValueError):
            qn.abruf(methode, fake.url + pfad, {})
    assert fake.anfragen == []                                                    # nichts wurde gesendet


# --- fasse_zusammen -----------------------------------------------------------------------------------------------

def _t(id, wert, autor, buch, nr, text="beleg"):
    return {"id": id, "wert": wert, "autor": autor, "buch": buch, "kapitel_nr": nr, "text": text}


def _punkte():
    return {1: {"autor": "A, A", "buch": "Alpha", "kapitel_nr": 1, "chunk_idx": 0}, 2: {"autor": "A, A", "buch": "Alpha", "kapitel_nr": 1, "chunk_idx": 1},
            3: {"autor": "A, A", "buch": "Alpha", "kapitel_nr": 1, "chunk_idx": 2}, 4: {"autor": "A, A", "buch": "Alpha", "kapitel_nr": 1, "chunk_idx": 3},
            5: {"autor": "A, A", "buch": "Alpha", "kapitel_nr": 2, "chunk_idx": 0}}


def test_rang_ist_die_summe_der_drei_besten_paare_und_wert_das_beste_paar():
    nb = {1: [_t(10, 0.9, "B, B", "Beta", 1, "bester Beleg")], 2: [_t(11, 0.6, "B, B", "Beta", 1)], 3: [_t(12, 0.6, "B, B", "Beta", 1)],
          4: [_t(13, 0.6, "B, B", "Beta", 1)], 5: [_t(14, 0.95, "B, B", "Beta", 2, "x")]}
    kanten = qn.fasse_zusammen(nb, _punkte(), KAPITEL, WERKE, mindestwert=0.5)
    # Alpha 1 -> Beta 1: beste drei 0.9+0.6+0.6 = 2.1 (das vierte Paar zaehlt nicht); Alpha 2 -> Beta 2: 0.95
    assert [(k["von"], k["nach"]) for k in kanten] == [("b001:1", "b002:1"), ("b001:2", "b002:2")]
    k = kanten[0]
    assert k["wert"] == 0.9 and k["beleg"] == "bester Beleg"


def test_ein_zielkapitel_mit_vielen_guten_paaren_schlaegt_ein_einzelnes_sehr_gutes():
    nb = {1: [_t(10, 0.95, "B, B", "Beta", 2)], 2: [_t(11, 0.7, "C, C", "Gamma", 1)], 3: [_t(12, 0.7, "C, C", "Gamma", 1)], 4: [_t(13, 0.7, "C, C", "Gamma", 1)]}
    kanten = qn.fasse_zusammen(nb, _punkte(), KAPITEL, WERKE, mindestwert=0.5, je_kapitel=1)
    assert [(k["von"], k["nach"]) for k in kanten] == [("b001:1", "b003:1")]                  # 2.1 gegen 0.95


def test_mindestwert_hoechstens_je_kapitel_und_deterministische_reihenfolge():
    nb = {1: [_t(10, 0.9, "B, B", "Beta", 1), _t(11, 0.9, "B, B", "Beta", 2), _t(20, 0.9, "C, C", "Gamma", 1), _t(12, 0.4, "C, C", "Gamma", 1)]}
    kanten = qn.fasse_zusammen(nb, _punkte(), KAPITEL, WERKE, mindestwert=0.5, je_kapitel=2)
    assert [(k["von"], k["nach"]) for k in kanten] == [("b001:1", "b002:1"), ("b001:1", "b002:2")]     # Gleichstand: nach Id; Rest faellt weg
    assert kanten == qn.fasse_zusammen(nb, _punkte(), KAPITEL, WERKE, mindestwert=0.5, je_kapitel=2)


def test_nie_selbstkante_gleiches_werk_oder_unbekanntes_kapitel_oder_werk():
    nb = {1: [_t(2, 0.99, "A, A", "Alpha", 2),                   # gleiches Werk
              _t(10, 0.9, "B, B", "Beta", 99),                    # Kapitel nicht in daten.json
              _t(11, 0.9, "Fremd, F", "Fremdwerk", 1),            # Werk nicht in der Bibliothek
              _t(12, 0.9, "B, B", "Beta", 1)]}
    kanten = qn.fasse_zusammen(nb, _punkte(), KAPITEL, WERKE, mindestwert=0.5)
    assert [(k["von"], k["nach"]) for k in kanten] == [("b001:1", "b002:1")]


def test_ausgangskapitel_ausserhalb_von_daten_json_entfaellt():
    punkte = {1: {"autor": "A, A", "buch": "Alpha", "kapitel_nr": 77, "chunk_idx": 0}}
    assert qn.fasse_zusammen({1: [_t(10, 0.9, "B, B", "Beta", 1)]}, punkte, KAPITEL, WERKE, mindestwert=0.5) == []


def test_beleg_ist_der_text_des_besten_zielchunks_und_leer_wenn_keiner_da_ist():
    nb = {1: [_t(10, 0.8, "B, B", "Beta", 1, "schwach"), _t(12, 0.9, "B, B", "Beta", 1, "stark")]}
    assert qn.fasse_zusammen(nb, _punkte(), KAPITEL, WERKE, mindestwert=0.5)[0]["beleg"] == "stark"
    nb = {1: [_t(10, 0.8, "B, B", "Beta", 1, "")]}
    assert qn.fasse_zusammen(nb, _punkte(), KAPITEL, WERKE, mindestwert=0.5)[0]["beleg"] == ""


def test_ende_zu_ende_mit_der_attrappe(fake):
    punkte = qn.lese_punkte(fake.url, "episto", pause=0)
    erg = qn.frage_nachbarn(fake.url, "episto", punkte, list(punkte), je=5, pause=0)
    kanten = qn.fasse_zusammen(erg.treffer, punkte, KAPITEL, WERKE, mindestwert=0.5)
    paare = {(k["von"], k["nach"]) for k in kanten}
    assert ("b001:1", "b002:1") in paare and ("b002:1", "b001:1") in paare and ("b001:2", "b003:1") in paare
    assert all(k["von"].split(":")[0] != k["nach"].split(":")[0] for k in kanten)


def test_stichprobenwerkzeug_laeuft_gegen_die_attrappe(fake, capsys):
    import verbindungen_stichprobe as vs
    assert vs.main(["--qdrant", fake.url, "--anzahl", "3", "--je", "5", "--mindestwerte", "0.5,0.7"]) == 0
    out = capsys.readouterr().out
    assert "7 Punkte" in out and "Verteilung der Werte" in out and "Beste Belege" in out and "0.50:" in out and "0.70:" in out
    assert all(a[0] in ("GET", "POST") and "delete" not in a[1] for a in fake.anfragen)


def test_stichprobenwerkzeug_ohne_qdrant_meldet_und_endet_mit_1(capsys):
    import verbindungen_stichprobe as vs
    assert vs.main(["--qdrant", "http://127.0.0.1:9"]) == 1
    assert "Qdrant nicht lesbar" in capsys.readouterr().err


def test_fortschrittsmeldung_je_batch(fake):
    punkte = qn.lese_punkte(fake.url, "episto", pause=0)
    gemeldet = []
    qn.frage_nachbarn(fake.url, "episto", punkte, [1, 2, 3, 10, 11], je=3, batch=2, pause=0, fortschritt=lambda fertig, gesamt: gemeldet.append((fertig, gesamt)))
    assert gemeldet == [(2, 5), (4, 5), (5, 5)]
