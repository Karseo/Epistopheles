"""Tests fuer den Redaktions-Empfaenger (Task 4)."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

from redaktion.auftraege import Warteschlange
from redaktion_server import erzeuge_server

TOKEN = "0123456789abcdef"
BUCH = "Autor, Eins/Titel"


def eintrag(i: str) -> dict:
    return {"id": i, "buch": BUCH, "ebene": "geraet", "ziel": {}, "art": "ersetzen",
            "parameter": {}, "vorher": {}, "nachher": {}, "hinweis": "",
            "erstellt": "2026-11-02T10:00:00Z", "geraet": "tab", "status": "offen"}


class Server:
    def __init__(self, root, paket, **kw):
        self.root = root
        self.httpd = erzeuge_server(root, host="127.0.0.1", port=0, paket=paket,
                                    token=kw.pop("token", TOKEN), **kw)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url(self, pfad: str) -> str:
        return f"http://127.0.0.1:{self.port}{pfad}"

    def anfrage(self, pfad, methode="GET", daten=None, token=TOKEN, header=None):
        h = dict(header or {})
        if token is not None:
            h["X-Redaktion-Token"] = token
        body = None
        if daten is not None:
            body = daten if isinstance(daten, bytes) else json.dumps(daten).encode("utf-8")
            h.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(self.url(pfad), data=body, headers=h, method=methode)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def eingang_dateien(self):
        basis = self.root / "hilfsdaten" / "redaktion" / "eingang"
        return sorted(p for p in basis.rglob("*") if p.is_file()) if basis.exists() else []

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(5)


@pytest.fixture
def paket(tmp_path):
    p = tmp_path / "paket"
    p.mkdir()
    (p / "index.html").write_text("<html>EPISTO</html>", encoding="utf-8")
    (p / "app.js").write_text("var a=1;", encoding="utf-8")
    (p / "daten.json").write_text("{}", encoding="utf-8")
    (p / "style.css").write_text("a{}", encoding="utf-8")
    (p / "buch.epub").write_bytes(b"PK" + b"x" * (3 * 1024 * 1024))
    (p / "sub").mkdir()
    (p / "sub" / "x.txt").write_text("innen", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("GEHEIM", encoding="utf-8")
    return p


@pytest.fixture
def srv(tmp_path, paket):
    s = Server(tmp_path / "root", paket)
    yield s
    s.stop()


def test_ping_mit_token_ok_ohne_token_401_mit_falschem_401(srv):
    status, _, body = srv.anfrage("/api/ping")
    assert status == 200 and json.loads(body) == {"ok": True}
    status, _, body = srv.anfrage("/api/ping", token=None)
    assert status == 401 and "ok" not in json.loads(body)
    status, _, _ = srv.anfrage("/api/ping", token="falsch")
    assert status == 401
    assert srv.eingang_dateien() == []


def test_401_verraet_nichts_und_schreibt_nichts(srv):
    status, _, body = srv.anfrage("/api/aenderungen", "POST",
                                  {"geraet": "t", "buch": BUCH, "eintraege": [eintrag("a")]},
                                  token="falsch")
    assert status == 401
    assert BUCH.encode() not in body
    status, _, _ = srv.anfrage("/api/stand?buch=" + "Autor%2C%20Eins/Titel", token=None)
    assert status == 401
    assert srv.eingang_dateien() == []


def test_fremde_ip_wird_abgewiesen(tmp_path, paket):
    s = Server(tmp_path / "root", paket, ip_erlaubt=lambda ip: False)
    try:
        status, _, _ = s.anfrage("/api/aenderungen", "POST",
                                 {"geraet": "t", "buch": BUCH, "eintraege": [eintrag("a")]})
        assert status == 403
        assert s.anfrage("/api/ping")[0] == 403
        assert s.anfrage("/")[0] == 403
        assert s.anfrage("/api/aenderungen", "OPTIONS", token=None)[0] == 403
        assert s.eingang_dateien() == []
    finally:
        s.stop()


def test_aenderungen_werden_gespeichert_und_wiederholung_ist_idempotent(srv):
    body = {"geraet": "tab", "buch": BUCH, "eintraege": [eintrag("a"), eintrag("b")]}
    status, _, antwort = srv.anfrage("/api/aenderungen", "POST", body)
    assert status == 200 and json.loads(antwort) == {"angenommen": ["a", "b"]}
    status, _, antwort = srv.anfrage("/api/aenderungen", "POST", body)
    assert status == 200 and json.loads(antwort) == {"angenommen": []}
    assert len(srv.eingang_dateien()) == 1


def test_gleichzeitige_gleiche_posts_speichern_jede_id_einmal(srv):
    body = {"geraet": "tab", "buch": BUCH, "eintraege": [eintrag(f"i{n}") for n in range(20)]}
    ergebnisse = []

    def sende():
        ergebnisse.append(json.loads(srv.anfrage("/api/aenderungen", "POST", body)[2]))

    ts = [threading.Thread(target=sende) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    angenommen = [i for e in ergebnisse for i in e["angenommen"]]
    assert sorted(angenommen) == sorted(f"i{n}" for n in range(20))
    assert len(srv.eingang_dateien()) == 1


def roh_senden(srv, kopf: bytes, body: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", srv.port), timeout=10) as s:
        s.sendall(kopf + body)
        s.shutdown(socket.SHUT_WR)
        antwort = b""
        try:
            while True:
                teil = s.recv(4096)
                if not teil:
                    break
                antwort += teil
        except OSError:
            pass
    return antwort


def test_kaputter_body_und_abgebrochene_anfrage_aendern_nichts(srv):
    status, _, _ = srv.anfrage("/api/aenderungen", "POST", b"{kaputt")
    assert status == 400
    status, _, _ = srv.anfrage("/api/aenderungen", "POST", b"\xff\xfe")
    assert status == 400
    for falsch in ([1, 2], {"geraet": 1, "buch": BUCH, "eintraege": []},
                   {"geraet": "t", "buch": BUCH, "eintraege": "x"},
                   {"geraet": "t", "eintraege": []}):
        assert srv.anfrage("/api/aenderungen", "POST", falsch)[0] == 400
    ganz = json.dumps({"geraet": "t", "buch": BUCH, "eintraege": [eintrag("a")]}).encode()
    kopf = (f"POST /api/aenderungen HTTP/1.1\r\nHost: x\r\nX-Redaktion-Token: {TOKEN}\r\n"
            f"Content-Length: {len(ganz)}\r\n\r\n").encode()
    roh_senden(srv, kopf, ganz[: len(ganz) // 2])
    assert srv.eingang_dateien() == []


def test_content_length_fehlt_ungueltig_oder_zu_gross(srv):
    kopf = f"POST /api/aenderungen HTTP/1.1\r\nHost: x\r\nX-Redaktion-Token: {TOKEN}\r\n"
    assert b" 411 " in roh_senden(srv, (kopf + "\r\n").encode(), b"")
    assert b" 400 " in roh_senden(srv, (kopf + "Content-Length: abc\r\n\r\n").encode(), b"")
    assert b" 400 " in roh_senden(srv, (kopf + "Content-Length: -5\r\n\r\n").encode(), b"")
    gross = kopf + f"Content-Length: {5 * 1024 * 1024 + 1}\r\n\r\n"
    assert b" 413 " in roh_senden(srv, gross.encode(), b"")
    assert srv.eingang_dateien() == []


def test_buchname_mit_pfadangriff_wird_abgelehnt(srv, tmp_path):
    for buch in ("../../x/y", "..\\..\\x/y", "/abs/pfad", "A/..", "nur-einer"):
        body = {"geraet": "t", "buch": buch, "eintraege": [eintrag("a")]}
        assert srv.anfrage("/api/aenderungen", "POST", body)[0] == 400
    assert srv.anfrage("/api/stand?buch=..%2F..%2Fx%2Fy")[0] == 400
    assert not (tmp_path / "root" / "x").exists()
    assert not (tmp_path / "x").exists()
    assert srv.eingang_dateien() == []


def test_statische_auslieferung_und_cors_preflight(srv):
    status, h, body = srv.anfrage("/", token=None)
    assert status == 200 and body == b"<html>EPISTO</html>"
    assert h["Content-Type"].startswith("text/html")
    assert h["Access-Control-Allow-Origin"] == "*"
    status, h, _ = srv.anfrage("/app.js", token=None)
    assert status == 200 and "javascript" in h["Content-Type"]
    assert "json" in srv.anfrage("/daten.json", token=None)[1]["Content-Type"]
    assert "css" in srv.anfrage("/style.css", token=None)[1]["Content-Type"]
    assert srv.anfrage("/buch.epub", token=None)[1]["Content-Type"] == "application/epub+zip"
    status, h, body = srv.anfrage("/api/aenderungen", "OPTIONS", token=None)
    assert status == 204 and body == b""
    assert h["Access-Control-Allow-Private-Network"] == "true"
    assert "X-Redaktion-Token" in h["Access-Control-Allow-Headers"]
    assert "POST" in h["Access-Control-Allow-Methods"]


def test_grosse_datei_wird_vollstaendig_geliefert_und_head(srv, paket):
    status, h, body = srv.anfrage("/buch.epub", token=None)
    assert status == 200 and len(body) == 3 * 1024 * 1024 + 2
    status, h, body = srv.anfrage("/buch.epub", "HEAD", token=None)
    assert status == 200 and body == b""
    assert int(h["Content-Length"]) == 3 * 1024 * 1024 + 2


def test_statische_pfadangriffe_und_verzeichnisse_geben_404(srv):
    for pfad in ("/../secret.txt", "/../../secret.txt", "/%2e%2e/secret.txt",
                 "/%2e%2e%2fsecret.txt", "/..%5csecret.txt", "/sub/..%5c..%5csecret.txt",
                 "/sub/", "/sub", "/gibtsnicht.html", "/C:/Windows/win.ini",
                 "/%252e%252e/secret.txt"):
        status, _, body = srv.anfrage(pfad, token=None)
        assert status == 404, pfad
        assert b"GEHEIM" not in body
    # Roh gesendet, damit der Client den Pfad nicht normalisiert.
    for pfad in ("/../secret.txt", "/sub/../../secret.txt", "/..\\secret.txt"):
        antwort = roh_senden(srv, f"GET {pfad} HTTP/1.1\r\nHost: x\r\n\r\n".encode(), b"")
        assert b"GEHEIM" not in antwort
        assert b" 404 " in antwort or b" 400 " in antwort


def test_stand_liefert_status_der_ids(srv):
    from redaktion.protokoll import setze_stand
    srv.anfrage("/api/aenderungen", "POST",
                {"geraet": "t", "buch": BUCH, "eintraege": [eintrag("a")]})
    setze_stand(srv.root, BUCH, "a", "angewendet", "")
    status, _, body = srv.anfrage("/api/stand?buch=Autor%2C%20Eins%2FTitel")
    assert status == 200
    stand = json.loads(body)["stand"]
    assert stand["a"]["status"] == "angewendet"
    assert srv.anfrage("/api/stand")[0] == 400


def test_unbekannter_api_pfad_und_falsche_methode(srv):
    assert srv.anfrage("/api/gibtsnicht")[0] == 404
    assert srv.anfrage("/api/ping", "POST", b"{}")[0] == 405


def test_cors_header_auf_fehlerantworten(srv):
    _, h, _ = srv.anfrage("/api/ping", token=None)
    assert h["Access-Control-Allow-Origin"] == "*"
    assert h["Content-Type"] == "application/json; charset=utf-8"


def test_token_wird_angelegt_und_nicht_geloggt(tmp_path, paket, capsys):
    root = tmp_path / "root2"
    httpd = erzeuge_server(root, host="127.0.0.1", port=0, paket=paket)
    datei = root / "hilfsdaten" / "redaktion" / "token.txt"
    token = datei.read_text(encoding="utf-8").strip()
    assert len(token) == 16 and int(token, 16) >= 0
    httpd.server_close()
    # Zweiter Start liest dasselbe Token.
    httpd = erzeuge_server(root, host="127.0.0.1", port=0, paket=paket)
    assert httpd.token == token
    s = Server.__new__(Server)
    s.root, s.httpd = root, httpd
    s.port = httpd.server_address[1]
    s.thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    s.thread.start()
    try:
        assert s.anfrage("/api/ping", token=token)[0] == 200
        assert s.anfrage("/api/ping", token="x" * 16)[0] == 401
    finally:
        s.stop()
    gesehen = capsys.readouterr()
    assert token not in gesehen.err and token not in gesehen.out


def test_token_argument_schreibt_keine_datei(tmp_path, paket):
    httpd = erzeuge_server(tmp_path / "r3", host="127.0.0.1", port=0, paket=paket, token="abc")
    httpd.server_close()
    assert not (tmp_path / "r3" / "hilfsdaten" / "redaktion" / "token.txt").exists()


# --- Task 12: Auftraege, Vorschlag und Haertung --------------------------------------------

import redaktion_server  # noqa: E402
from redaktion_server import ip_privat  # noqa: E402


@pytest.fixture
def lektor_root(tmp_path):
    root = tmp_path / "root"
    lektor = root / "rohdaten" / "Lektor" / "Autor, Eins" / "Titel"
    (lektor / "en").mkdir(parents=True)
    (lektor / "de").mkdir()
    (lektor / "en" / "chunk_000.md").write_text("Original", encoding="utf-8")
    (lektor / "de" / "chunk_000.md").write_text("Alt", encoding="utf-8")
    (lektor / "de" / "chunk_001.md").write_text("Alt1", encoding="utf-8")
    return root


@pytest.fixture
def asrv(lektor_root, paket):
    jobs = []
    s = Server(lektor_root, paket, starte=jobs.append)
    s.jobs = jobs
    yield s
    s.stop()


def warte(bedingung, sek=5.0):
    import time
    ende = time.time() + sek
    while time.time() < ende:
        if bedingung():
            return True
        time.sleep(0.01)
    return False


def test_auftrag_einreichen_und_status_abfragen(asrv):
    status, _, body = asrv.anfrage("/api/auftraege", "POST",
                                   {"art": "neu-uebersetzen", "buch": BUCH, "chunk": 0})
    assert status == 200
    jid = json.loads(body)["id"]
    assert warte(lambda: json.loads(asrv.anfrage(f"/api/auftraege/{jid}")[2])["zustand"] == "fertig")
    assert [(j["id"], j["art"], j["buch"], j["chunk"]) for j in asrv.jobs] == [
        (jid, "neu-uebersetzen", BUCH, 0)]
    assert asrv.anfrage("/api/auftraege/ffffffffffffffff")[0] == 404
    assert asrv.anfrage("/api/auftraege/..%2Fping")[0] == 404
    assert asrv.anfrage("/api/auftraege/" + jid, "POST", b"{}")[0] == 405


def test_fehlgeschlagener_auftrag_zeigt_fehler(lektor_root, paket):
    def kaputt(job):
        raise RuntimeError("kaputt")
    s = Server(lektor_root, paket, starte=kaputt)
    try:
        jid = json.loads(s.anfrage("/api/auftraege", "POST",
                                   {"art": "neu-uebersetzen", "buch": BUCH, "chunk": 0})[2])["id"]
        assert warte(lambda: json.loads(s.anfrage(f"/api/auftraege/{jid}")[2])["zustand"] == "fehler")
        assert json.loads(s.anfrage(f"/api/auftraege/{jid}")[2])["meldung"] == "kaputt"
    finally:
        s.stop()


def test_auftraege_ungueltige_angaben(asrv):
    for body in ({"art": "loeschen", "buch": BUCH, "chunk": 0},
                 {"art": "neu-uebersetzen", "buch": BUCH, "chunk": -1},
                 {"art": "neu-uebersetzen", "buch": BUCH, "chunk": True},
                 {"art": "neu-uebersetzen", "buch": BUCH, "chunk": "0"},
                 {"art": "neu-uebersetzen", "buch": 5, "chunk": 0},
                 {"art": "neu-uebersetzen", "buch": "../../x/y", "chunk": 0},
                 {"art": "neu-uebersetzen", "buch": "Autor, Eins/CON", "chunk": 0},
                 [1], {}):
        assert asrv.anfrage("/api/auftraege", "POST", body)[0] == 400, body
    # gueltiger Name, aber Chunk existiert nicht
    assert asrv.anfrage("/api/auftraege", "POST",
                        {"art": "neu-uebersetzen", "buch": BUCH, "chunk": 9})[0] == 404
    assert asrv.jobs == []


def test_vorschlag_liefert_alt_und_neu_und_404_ohne_neu(asrv, lektor_root):
    pfad = "/api/vorschlag?buch=Autor%2C%20Eins%2FTitel&chunk=0"
    assert asrv.anfrage(pfad)[0] == 404
    (lektor_root / "rohdaten" / "Lektor" / "Autor, Eins" / "Titel" / "de" / "chunk_000.md.neu"
     ).write_text("Neu äöü", encoding="utf-8")
    status, _, body = asrv.anfrage(pfad)
    assert status == 200 and json.loads(body) == {"alt": "Alt", "neu": "Neu äöü"}
    assert asrv.anfrage("/api/vorschlag?buch=Autor%2C%20Eins%2FTitel&chunk=1")[0] == 404
    for q in ("buch=..%2F..%2Fx%2Fy&chunk=0", "buch=Autor%2C%20Eins%2FTitel&chunk=-1",
              "buch=Autor%2C%20Eins%2FTitel&chunk=abc", "buch=Autor%2C%20Eins%2FTitel", "chunk=0"):
        assert asrv.anfrage("/api/vorschlag?" + q)[0] == 400, q


def test_neue_endpunkte_brauchen_token_und_ip(lektor_root, paket):
    jobs = []
    body = {"art": "neu-uebersetzen", "buch": BUCH, "chunk": 0}
    s = Server(lektor_root, paket, starte=jobs.append)
    try:
        assert s.anfrage("/api/auftraege", "POST", body, token=None)[0] == 401
        assert s.anfrage("/api/auftraege/abc", token="falsch")[0] == 401
        assert s.anfrage("/api/vorschlag?buch=x&chunk=0", token=None)[0] == 401
        assert jobs == []
    finally:
        s.stop()
    s = Server(lektor_root, paket, ip_erlaubt=lambda ip: False, starte=jobs.append)
    try:
        assert s.anfrage("/api/auftraege", "POST", body)[0] == 403
        assert s.anfrage("/api/auftraege/abc")[0] == 403
        assert s.anfrage("/api/vorschlag?buch=x&chunk=0")[0] == 403
        assert jobs == []
    finally:
        s.stop()


# --- Haertung aus dem Task-4-Review ----------------------------------------------------------

@pytest.mark.parametrize("ip,erlaubt", [
    ("8.8.8.8", False), ("10.0.0.1", True), ("192.168.1.5", True), ("172.16.0.1", True),
    ("127.0.0.1", True), ("::1", True), ("::ffff:127.0.0.1", True), ("::ffff:8.8.8.8", False),
    ("fe80::1%eth0", True), ("2001:4860:4860::8888", False), ("0.0.0.0", False),
    ("224.0.0.1", False),
    ("", False), ("müll", False), ("999.1.1.1", False), ("1.2.3", False), ("%", False),
    ("fe80::1%", True), ("10.0.0.1%eth0", True), ("\x00", False), ("10.0.0.1\n", False),
])
def test_ip_privat(ip, erlaubt):
    assert ip_privat(ip) is erlaubt


def test_leeres_token_verhindert_den_start(tmp_path, paket):
    for token in ("", "   ", "\n"):
        with pytest.raises(ValueError):
            erzeuge_server(tmp_path / "r", host="127.0.0.1", port=0, paket=paket, token=token)


def test_server_mit_leerem_token_lehnt_jede_anfrage_ab(tmp_path, paket):
    s = Server(tmp_path / "r", paket)
    try:
        s.httpd.token = ""
        assert s.anfrage("/api/ping", token="")[0] == 401
        assert s.anfrage("/api/ping", token=None)[0] == 401
    finally:
        s.stop()


def test_unerwarteter_fehler_gibt_json_500(srv, monkeypatch):
    def boom(h, q):
        raise KeyError("geheim-im-fehler")
    monkeypatch.setitem(redaktion_server.API_ROUTEN, ("GET", "/api/boom"), boom)
    status, h, body = srv.anfrage("/api/boom")
    assert status == 500
    assert h["Content-Type"].startswith("application/json")
    assert json.loads(body) == {"fehler": "Interner Fehler"}
    assert b"geheim" not in body
    assert srv.anfrage("/api/ping")[0] == 200          # Server laeuft weiter


def test_nosniff_auf_allen_antworten(srv):
    for status, h, _ in (srv.anfrage("/api/ping"), srv.anfrage("/api/ping", token=None),
                         srv.anfrage("/api/gibtsnicht"), srv.anfrage("/", token=None),
                         srv.anfrage("/gibtsnicht", token=None),
                         srv.anfrage("/api/ping", "OPTIONS", token=None),
                         srv.anfrage("/index.html", "HEAD", token=None)):
        assert h.get("X-Content-Type-Options") == "nosniff", status
    antwort = roh_senden(srv, b"GET / HTTP/1.1\r\nX: " + b"a" * 70000 + b"\r\n\r\n", b"")
    assert b" 431 " in antwort
    assert b"nosniff" in antwort.lower()               # auch send_error der Standardbibliothek


def test_start_verweigert_wenn_token_im_paket_liegt(tmp_path):
    root = tmp_path / "root"
    with pytest.raises(ValueError):                    # Paket = Wurzel enthaelt token.txt
        erzeuge_server(root, host="127.0.0.1", port=0, paket=root, token="abc")
    with pytest.raises(ValueError):                    # Paket = Elternordner von token.txt
        erzeuge_server(root, host="127.0.0.1", port=0, paket=root / "hilfsdaten", token="abc")
    httpd = erzeuge_server(root, host="127.0.0.1", port=0, paket=tmp_path / "anderes", token="abc")
    httpd.server_close()


def test_token_datei_wird_nie_ausgeliefert(tmp_path, paket):
    root = tmp_path / "root4"
    httpd = erzeuge_server(root, host="127.0.0.1", port=0, paket=paket)
    httpd.server_close()
    assert (root / "hilfsdaten" / "redaktion" / "token.txt").is_file()
    s = Server(root, paket)
    try:
        assert s.anfrage("/hilfsdaten/redaktion/token.txt", token=None)[0] == 404
    finally:
        s.stop()


# --- Task 13: Haertung des Unterprozess-Starters -------------------------------------------

class _Lauf:
    def __init__(self, code=1, stderr="", stdout=""):
        self.returncode, self.stderr, self.stdout = code, stderr, stdout


def test_unterprozess_buch_als_eine_option_auch_mit_fuehrendem_bindestrich(tmp_path, monkeypatch):
    aufrufe = []
    monkeypatch.setattr(redaktion_server.subprocess, "run",
                        lambda cmd, **kw: aufrufe.append(cmd) or _Lauf(0))
    redaktion_server.starte_unterprozess({"buch": "-x, Autor/Titel", "chunk": 3}, tmp_path)
    (cmd,) = aufrufe
    assert "--buch=-x, Autor/Titel" in cmd
    assert "--buch" not in cmd and "-x, Autor/Titel" not in cmd       # nie als eigenes Argument


WURZEL = "D:\\Arbeit Geheim\\Wurzel"


@pytest.mark.parametrize("text, verboten", [
    ("Fehler: C:\\Program Files\\Python\\python.exe", ["Program", "Files\\", "C:\\"]),
    ("Fehler: C:\\secret.txt", ["C:", "secret"]),
    ("Fehler: C:/Users/Dude/a b/c.md fehlt", ["Users", "Dude", "C:/", "a b"]),
    ("Fehler: \\\\server\\share\\ordner\\datei.txt", ["server", "share", "\\\\"]),
    ("Fehler: \\\\server\\share", ["server", "share"]),
    ("Fehler: /root", ["/root"]),
    ("Fehler: /etc", ["/etc"]),
    ("Fehler: /home/dude/mein ordner/x.txt", ["dude", "/home", "mein"]),
    ('File "/usr/lib/python3/x.py", line 3', ["/usr", "lib"]),
    ("Fehler: d:/arbeit geheim/wurzel/rohdaten/Lektor/A/T/en/chunk_000.md", ["arbeit", "Geheim", "rohdaten", "Lektor", "d:/"]),
    ("Fehler: D:/ARBEIT GEHEIM/WURZEL/rohdaten/x.md", ["ARBEIT", "rohdaten", "D:/"]),
    ("Fehler: D:\\Arbeit Geheim\\Wurzel\\tools\\x.py", ["Arbeit", "Geheim", "tools", "D:\\"]),
    ("Fehler: D:\\Arbeit Geheim/Wurzel\\gemischt/x.py", ["Arbeit", "gemischt"]),
    ('File "D:\\Arbeit Geheim\\Wurzel\\x.py", line 1', ["Arbeit", "D:\\"]),
    ("Fehler: //nas/share/privat/x.md fehlt", ["nas", "share", "privat", "//"]),
    ("Fehler: \\Users\\Dude\\geheim\\x", ["Users", "Dude", "geheim"]),
    ("Fehler: D:Relativ\\foo\\bar", ["Relativ", "foo", "D:"]),
    ("Fehler: \\\\?\\C:\\Users\\Dude\\privat\\a.md", ["Users", "Dude", "privat", "C:", "\\\\?"]),
    ("Fehler: \\\\?\\UNC\\srv\\freigabe\\ordner\\f.md", ["srv", "freigabe", "UNC", "ordner"]),
])
def test_bereinige_meldung_entfernt_pfade_und_wurzel(text, verboten):
    aus = redaktion_server.bereinige_meldung(text, WURZEL)
    for v in verboten:
        assert v not in aus, (v, aus)
    assert aus.startswith(text[:8]) or "Fehler" in aus or "File" in aus      # bleibt lesbar


def _wirft(exc):
    def starte(job):
        raise exc
    return starte


def _warte_fehler(w, jid):
    ende = time.time() + 5
    while time.time() < ende and w.status(jid)["zustand"] != "fehler":
        time.sleep(0.01)
    return w.status(jid)["meldung"]


@pytest.mark.parametrize("exc, verboten, erwartet", [
    (subprocess.TimeoutExpired([sys.executable, "D:\\Arbeit\\Geheim\\x.py", "--buch=A/T"], 7200),
     ["Geheim", "x.py", "--buch", "python"], "Zeitüberschreitung beim Übersetzen"),
    (FileNotFoundError(2, "Datei nicht gefunden: 'D:\\Arbeit\\Geheim\\python.exe'"),
     ["Geheim", "Arbeit", "D:"], "FileNotFoundError"),
    (OSError("kann /home/dude/privat/x nicht starten"), ["dude", "privat"], "OSError"),
])
def test_auftrag_meldung_bei_ausnahme_von_subprocess_ist_pfadfrei(tmp_path, exc, verboten, erwartet):
    w = Warteschlange(tmp_path, _wirft(exc), bereinige=lambda t: redaktion_server.bereinige_meldung(t, tmp_path))
    meldung = _warte_fehler(w, w.reiche_ein("neu-uebersetzen", "A, B/T", 0))
    assert erwartet in meldung
    for v in verboten:
        assert v not in meldung, (v, meldung)


def test_server_verdrahtet_bereinigung_der_auftragsmeldung(tmp_path):
    s = erzeuge_server(tmp_path, host="127.0.0.1", port=0, token="t",
                       starte=_wirft(OSError(f"nicht lesbar: {tmp_path}\\geheim\\x.md")))
    try:
        meldung = _warte_fehler(s.auftraege, s.auftraege.reiche_ein("neu-uebersetzen", "A, B/T", 0))
        assert "geheim" not in meldung and str(tmp_path) not in meldung
    finally:
        s.server_close()


def test_bereinige_meldung_laesst_normalen_text_unveraendert():
    t = "Fehler: Quelle ist deutsch (Exit 1) 5/3 http://x"
    assert redaktion_server.bereinige_meldung(t, WURZEL) == t


def test_unterprozess_fehlermeldung_enthaelt_keine_absoluten_pfade(tmp_path, monkeypatch):
    root = tmp_path / "geheim" / "wurzel"
    stderr = (f"Traceback (most recent call last):\n"
              f'  File "{root}\\tools\\pipeline\\x.py", line 3, in main\n'
              f"FileNotFoundError: {root / 'rohdaten' / 'Lektor' / 'A' / 'T' / 'en' / 'chunk_000.md'}\n"
              "OSError: C:\\Users\\Dude\\Dokumente\\privat.txt und /home/dude/privat/datei.txt " + "x" * 400)
    monkeypatch.setattr(redaktion_server.subprocess, "run", lambda cmd, **kw: _Lauf(1, stderr))
    with pytest.raises(RuntimeError) as e:
        redaktion_server.starte_unterprozess({"buch": "A/T", "chunk": 0}, root)
    meldung = str(e.value)
    for verboten in ("geheim", "Dude", "dude", "Users", "home", str(tmp_path), "rohdaten"):
        assert verboten not in meldung, (verboten, meldung)
    assert "Exit 1" in meldung                                      # Nutzbares bleibt
    assert len(meldung) < 3 * (redaktion_server.MAX_MELDUNG_ZEILE + 5) + 120      # gekuerzt


# ----------------------------------------------------------------- P2 Task 3: Lektor-Schlüssel

LEKTOR_ALT = "Cathy O'Neil/Weapons of Math Destruction"


def _lektor_abweichend(root):
    d = root / "rohdaten" / "Lektor" / "Cathy O'Neil" / "Weapons of Math Destruction"
    (d / "en").mkdir(parents=True)
    (d / "de").mkdir()
    (d / "en" / "chunk_000.md").write_text("Original", encoding="utf-8")
    (d / "de" / "chunk_000.md").write_text("Alt O'Neil", encoding="utf-8")
    return d


def test_auftrag_mit_lektor_schluessel_findet_den_chunk_und_gibt_ihn_an_den_starter(asrv, lektor_root):
    _lektor_abweichend(lektor_root)
    body = {"art": "neu-uebersetzen", "buch": "O'Neil, Cathy/Weapons", "chunk": 0}
    assert asrv.anfrage("/api/auftraege", "POST", body)[0] == 404                    # ohne lektor: Ordner fehlt
    status, _, antwort = asrv.anfrage("/api/auftraege", "POST", {**body, "lektor": LEKTOR_ALT})
    assert status == 200
    jid = json.loads(antwort)["id"]
    assert warte(lambda: json.loads(asrv.anfrage(f"/api/auftraege/{jid}")[2])["zustand"] == "fertig")
    assert [(j["buch"], j["lektor"]) for j in asrv.jobs] == [("O'Neil, Cathy/Weapons", LEKTOR_ALT)]


@pytest.mark.parametrize("lektor", ["../x/y", "A/../B", "/abs/y", "A", "A/B/C", 5, ["a", "b"]])
def test_auftrag_mit_unsicherem_lektor_schluessel_ist_400(asrv, lektor):
    body = {"art": "neu-uebersetzen", "buch": BUCH, "chunk": 0, "lektor": lektor}
    assert asrv.anfrage("/api/auftraege", "POST", body)[0] == 400
    assert asrv.jobs == []


def test_vorschlag_mit_lektor_schluessel(asrv, lektor_root):
    d = _lektor_abweichend(lektor_root)
    (d / "de" / "chunk_000.md.neu").write_text("Neu O'Neil", encoding="utf-8")
    q = "/api/vorschlag?buch=O%27Neil%2C%20Cathy%2FWeapons&chunk=0"
    assert asrv.anfrage(q)[0] == 404
    status, _, body = asrv.anfrage(q + "&lektor=" + urllib.parse.quote(LEKTOR_ALT))
    assert status == 200 and json.loads(body) == {"alt": "Alt O'Neil", "neu": "Neu O'Neil"}
    assert asrv.anfrage(q + "&lektor=..%2F..%2Fx%2Fy")[0] == 400
