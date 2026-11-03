"""Empfaenger fuer Redaktionsaenderungen auf APIC (Spec 5.2).

Kleiner HTTP-Server (nur Standardbibliothek), den man von Hand startet:

    python redaktion_server.py [--root R] [--port 8080] [--host 0.0.0.0] [--paket P]

Er liefert die Epistopheles-App (statische Dateien aus `paket`) und die API aus
einem Ursprung aus, damit der Browser keine Mixed-Content- oder CORS-Huerden hat:

    GET  /api/ping                  -> {"ok": true}
    POST /api/aenderungen           -> {"angenommen": [ids]}
    GET  /api/stand?buch=<A/T>      -> {"stand": {id: {"status", "grund", ...}}}
    POST /api/auftraege             -> {"id"}  (nur {"art": "neu-uebersetzen", "buch", "chunk"})
    GET  /api/auftraege/<id>        -> {"zustand": wartet|laeuft|fertig|fehler, "meldung"}
    GET  /api/vorschlag?buch=&chunk= -> {"alt", "neu"}  (404 ohne Vorschlag)

Schutz: Zuerst die IP-Pruefung (nur private Netze und Loopback), fuer jede
`/api/*`-Anfrage ausser `OPTIONS` danach das Token im Header `X-Redaktion-Token`.
Bei 401/403 wird nichts gelesen, geschrieben oder verraten. Request-Bodies werden
nie protokolliert. Alle Antworten tragen `X-Content-Type-Options: nosniff`. Der Start wird
verweigert bei leerem Token oder wenn `token.txt` im ausgelieferten Paket liegt.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import mimetypes
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, unquote, urlsplit

from redaktion import protokoll
from redaktion.auftraege import ART_NEU_UEBERSETZEN, Warteschlange
import redaktion_anwenden

TOKEN_HEADER = "X-Redaktion-Token"
MAX_BODY = 5 * 1024 * 1024
CHUNK = 64 * 1024
AUFTRAG_TIMEOUT = 2 * 60 * 60  # Sekunden; ein Chunk mit 32b-Modell dauert Minuten
LESE_TIMEOUT = 30  # Sekunden; haelt abgebrochene Anfragen nicht ewig offen

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": f"{TOKEN_HEADER}, Content-Type",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Private-Network": "true",
}

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".pdf": "application/pdf",
    ".epub": "application/epub+zip",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".webmanifest": "application/manifest+json",
}


def ip_privat(client_ip: str) -> bool:
    """Standardpruefung: privates Netz oder Loopback (IPv4-gemappte IPv6 wird entpackt)."""
    try:
        ip = ipaddress.ip_address(client_ip.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip.is_unspecified or ip.is_multicast:
        return False
    return ip.is_private or ip.is_loopback


def token_pfad(root: Path) -> Path:
    return Path(root) / "hilfsdaten" / "redaktion" / "token.txt"


def lade_token(root: Path) -> str:
    """Liest `hilfsdaten/redaktion/token.txt`; fehlt sie (oder ist leer), wird sie mit 16 Hex angelegt."""
    pfad = token_pfad(root)
    try:
        token = pfad.read_text(encoding="utf-8").strip()
    except OSError:
        token = ""
    if not token:
        token = secrets.token_hex(8)
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(token + "\n", encoding="utf-8")
    return token


class _HttpFehler(Exception):
    def __init__(self, status: int, text: str):
        super().__init__(text)
        self.status = status
        self.text = text


# --- API-Handler: (handler, query) -> JSON-faehiges Objekt -----------------------------

def _api_ping(h: "_Handler", query: dict) -> object:
    return {"ok": True}


def _api_aenderungen(h: "_Handler", query: dict) -> object:
    daten = h.lies_json_body()
    if (not isinstance(daten, dict) or not isinstance(daten.get("geraet"), str)
            or not isinstance(daten.get("buch"), str) or not isinstance(daten.get("eintraege"), list)):
        raise _HttpFehler(400, "Erwartet: geraet (Text), buch (Text), eintraege (Liste)")
    try:
        with h.server.schreib_sperre:
            ids = protokoll.schreibe_eingang(h.server.root, daten["geraet"], daten["buch"],
                                             daten["eintraege"])
    except ValueError:
        raise _HttpFehler(400, "Ungültiger Buchname") from None
    return {"angenommen": ids}


def _api_stand(h: "_Handler", query: dict) -> object:
    buch = (query.get("buch") or [""])[0]
    try:
        return {"stand": protokoll.lade_stand(h.server.root, buch)}
    except ValueError:
        raise _HttpFehler(400, "Ungültiger Buchname") from None


def _chunk_zahl(wert: object) -> int:
    if isinstance(wert, bool) or not isinstance(wert, int) or wert < 0:
        raise _HttpFehler(400, "chunk muss eine Zahl ab 0 sein")
    return wert


def _lektor_ziel(lektor: object) -> dict | None:
    """`{"lektor": …}` fuer den Lektor-Schluessel eines Auftrags (None = Buchschluessel gilt)."""
    if lektor is None:
        return None
    if not isinstance(lektor, str):
        raise _HttpFehler(400, "lektor muss ein Text sein")
    return {"lektor": lektor}


def _chunk_pfade(h: "_Handler", buch: object, chunk: int, lektor: object = None) -> Path:
    """Pfad des Original-Chunks (prueft Buch- und Lektor-Schluessel); 400 bei unsicherem Namen."""
    if not isinstance(buch, str):
        raise _HttpFehler(400, "buch muss ein Text sein")
    try:
        return redaktion_anwenden.chunk_datei(h.server.root, buch, chunk, _lektor_ziel(lektor))
    except ValueError:
        raise _HttpFehler(400, "Ungültiger Buch- oder Lektorname") from None


def _api_auftrag_neu(h: "_Handler", query: dict) -> object:
    daten = h.lies_json_body()
    if not isinstance(daten, dict):
        raise _HttpFehler(400, "Erwartet: art, buch, chunk")
    if daten.get("art") != ART_NEU_UEBERSETZEN:
        raise _HttpFehler(400, "Unbekannte Art des Auftrags")
    chunk = _chunk_zahl(daten.get("chunk"))
    lektor = daten.get("lektor")
    datei = _chunk_pfade(h, daten.get("buch"), chunk, lektor)
    if not datei.is_file():
        raise _HttpFehler(404, "Chunk nicht gefunden")
    try:
        return {"id": h.server.auftraege.reiche_ein(daten["art"], daten["buch"], chunk, lektor)}
    except ValueError as e:
        raise _HttpFehler(400, str(e)) from None


_ID = re.compile(r"[0-9a-f]{1,64}\Z")


def _api_auftrag_status(h: "_Handler", query: dict) -> object:
    auftrag_id = (query.get("_rest") or [""])[0]
    if not _ID.match(auftrag_id):
        raise _HttpFehler(404, "Unbekannter Auftrag")
    try:
        return h.server.auftraege.status(auftrag_id)
    except KeyError:
        raise _HttpFehler(404, "Unbekannter Auftrag") from None


def _api_vorschlag(h: "_Handler", query: dict) -> object:
    buch = (query.get("buch") or [""])[0]
    roh = (query.get("chunk") or [""])[0]
    if not roh.isascii() or not roh.isdigit():
        raise _HttpFehler(400, "chunk muss eine Zahl ab 0 sein")
    chunk = _chunk_zahl(int(roh))
    lektor_roh = (query.get("lektor") or [None])[0]
    _chunk_pfade(h, buch, chunk, lektor_roh)   # prueft Buch-/Lektorschluessel und Chunk-Nummer
    lektor = redaktion_anwenden.lektor_ordner(h.server.root, buch, _lektor_ziel(lektor_roh))
    alt = lektor / "de" / f"chunk_{chunk:03d}.md"
    neu = alt.with_name(alt.name + ".neu")
    try:
        neu_text = neu.read_bytes().decode("utf-8")
    except FileNotFoundError:
        raise _HttpFehler(404, "Kein Vorschlag vorhanden") from None
    try:
        alt_text = alt.read_bytes().decode("utf-8")
    except FileNotFoundError:
        alt_text = ""
    return {"alt": alt_text, "neu": neu_text}


# (Methode, Pfad) -> Handler. Weitere Routen hier ergaenzen.
API_ROUTEN: dict[tuple[str, str], Callable[["_Handler", dict], object]] = {
    ("GET", "/api/ping"): _api_ping,
    ("POST", "/api/aenderungen"): _api_aenderungen,
    ("GET", "/api/stand"): _api_stand,
    ("POST", "/api/auftraege"): _api_auftrag_neu,
    ("GET", "/api/vorschlag"): _api_vorschlag,
}

# (Methode, Pfadpraefix) -> Handler; der Rest des Pfads steht in `query["_rest"]`.
API_PRAEFIX_ROUTEN: dict[tuple[str, str], Callable[["_Handler", dict], object]] = {
    ("GET", "/api/auftraege/"): _api_auftrag_status,
}


class _Handler(BaseHTTPRequestHandler):
    server_version = "EpistoRedaktion/1"
    timeout = LESE_TIMEOUT

    # --- Antworten ---------------------------------------------------------------

    def _kopf(self, status: int, content_type: str | None = None,
              laenge: int | None = None) -> None:
        self.send_response(status)
        for k, v in CORS.items():
            self.send_header(k, v)
        if content_type:
            self.send_header("Content-Type", content_type)
        if laenge is not None:
            self.send_header("Content-Length", str(laenge))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def end_headers(self) -> None:
        # Auch bei Fehlern, die die Standardbibliothek selbst sendet (send_error).
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def _json(self, status: int, obj: object) -> None:
        roh = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._kopf(status, "application/json; charset=utf-8", len(roh))
        if self.command != "HEAD":
            self.wfile.write(roh)

    def _fehler(self, status: int, text: str) -> None:
        self.close_connection = True
        self._json(status, {"fehler": text})

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # Nur Anfragezeile und Status; Header (Token) und Bodies stehen nie im Log.
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    # --- Pruefungen --------------------------------------------------------------

    def _ip_ok(self) -> bool:
        return bool(self.server.ip_erlaubt(self.client_address[0]))

    def _token_ok(self) -> bool:
        erwartet = self.server.token
        if not erwartet or not erwartet.strip():
            return False                      # ohne Token wird nie etwas akzeptiert
        gesendet = self.headers.get(TOKEN_HEADER, "")
        return secrets.compare_digest(gesendet.encode("utf-8"),
                                      erwartet.encode("utf-8"))

    def lies_json_body(self) -> object:
        """Liest genau `Content-Length` Bytes (max. 5 MB) und parst JSON; sonst _HttpFehler."""
        roh = self.headers.get("Content-Length")
        if roh is None:
            raise _HttpFehler(411, "Content-Length fehlt")
        try:
            laenge = int(roh)
        except ValueError:
            raise _HttpFehler(400, "Content-Length ungültig") from None
        if laenge < 0:
            raise _HttpFehler(400, "Content-Length ungültig")
        if laenge > MAX_BODY:
            raise _HttpFehler(413, "Anfrage zu groß")
        try:
            body = self.rfile.read(laenge)
        except OSError:
            self.close_connection = True
            raise _HttpFehler(400, "Anfrage abgebrochen") from None
        if len(body) != laenge:
            raise _HttpFehler(400, "Anfrage unvollständig")
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise _HttpFehler(400, "Kein gültiges JSON") from None

    # --- Verteilung --------------------------------------------------------------

    def _bearbeite(self) -> None:
        if not self._ip_ok():
            self.close_connection = True
            self._json(HTTPStatus.FORBIDDEN, {})
            return
        teile = urlsplit(self.path)
        if self.command == "OPTIONS":
            self._kopf(HTTPStatus.NO_CONTENT)
            return
        if teile.path.startswith("/api/"):
            self._api(teile)
        elif self.command in ("GET", "HEAD"):
            self._statisch(teile.path)
        else:
            self._fehler(HTTPStatus.METHOD_NOT_ALLOWED, "Methode nicht erlaubt")

    def _api(self, teile) -> None:
        if not self._token_ok():
            self._fehler(HTTPStatus.UNAUTHORIZED, "Token fehlt oder ist falsch")
            return
        query = parse_qs(teile.query)
        handler = API_ROUTEN.get((self.command, teile.path))
        if handler is None:
            for (methode, praefix), h in API_PRAEFIX_ROUTEN.items():
                if methode == self.command and teile.path.startswith(praefix):
                    handler = h
                    query["_rest"] = [teile.path[len(praefix):]]
                    break
        if handler is None:
            bekannt = any(p == teile.path for _, p in API_ROUTEN) or any(
                teile.path.startswith(pr) for _, pr in API_PRAEFIX_ROUTEN)
            if bekannt:
                self._fehler(HTTPStatus.METHOD_NOT_ALLOWED, "Methode nicht erlaubt")
            else:
                self._fehler(HTTPStatus.NOT_FOUND, "Unbekannter Pfad")
            return
        try:
            ergebnis = handler(self, query)
        except _HttpFehler as e:
            self._fehler(e.status, e.text)
            return
        except Exception as e:  # noqa: BLE001 - nie Verbindungsabbruch oder HTML statt JSON
            sys.stderr.write("Interner Fehler in %s %s: %s\n" % (self.command, teile.path, type(e).__name__))
            self._fehler(HTTPStatus.INTERNAL_SERVER_ERROR, "Interner Fehler")
            return
        self._json(HTTPStatus.OK, ergebnis)

    def _statisch(self, url_pfad: str) -> None:
        datei = self._finde_datei(url_pfad)
        if datei is None:
            self._fehler(HTTPStatus.NOT_FOUND, "Nicht gefunden")
            return
        try:
            groesse = datei.stat().st_size
            f = open(datei, "rb")
        except OSError:
            self._fehler(HTTPStatus.NOT_FOUND, "Nicht gefunden")
            return
        with f:
            typ = _MIME.get(datei.suffix.lower()) or mimetypes.guess_type(datei.name)[0] \
                or "application/octet-stream"
            self._kopf(HTTPStatus.OK, typ, groesse)
            if self.command != "HEAD":
                try:
                    shutil.copyfileobj(f, self.wfile, CHUNK)
                except OSError:
                    self.close_connection = True

    def _finde_datei(self, url_pfad: str) -> Path | None:
        rel = unquote(url_pfad)
        if "\\" in rel or "\0" in rel or ":" in rel:
            return None
        rel = rel.lstrip("/")
        if rel == "":
            rel = "index.html"
        basis = self.server.paket.resolve()
        try:
            ziel = (basis / rel).resolve()
            ziel.relative_to(basis)
            if ziel == token_pfad(self.server.root).resolve():
                return None
        except (ValueError, OSError):
            return None
        return ziel if ziel.is_file() else None

    do_GET = do_HEAD = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _bearbeite


class RedaktionsServer(ThreadingHTTPServer):
    daemon_threads = True
    root: Path
    paket: Path
    token: str
    ip_erlaubt: Callable[[str], bool]
    schreib_sperre: threading.Lock
    auftraege: Warteschlange


_REST = r"""[^"'<>|*?\r\n]*"""          # bis Zeilenende oder Anfuehrungszeichen (Leerzeichen gehoeren zum Pfad)
_PFAD = re.compile(
    r"(?P<ext>\\\\[?.]\\" + _REST + r")"                                      # \\?\C:\... oder \\.\...
    r"|(?P<unc>(?:\\\\|(?<![\w:/\\])//(?=[^\s/]))" + _REST + r")"            # \\server\share\... oder //server/share/...
    r"|(?P<laufwerk>(?<![\w])[A-Za-z]:(?:[\\/]|(?=[^\s\\/:]+[\\/]))" + _REST + r")"   # C:\..., C:/..., D:Relativ\...
    r"|(?P<wurzel>(?<![\w.:/\\…])\\(?=[A-Za-z0-9_.$-])" + _REST + r")"      # \Users\x (ohne Laufwerk)
    r"|(?P<posix>(?<![\w.:/\\…])/(?=[^\s/])" + _REST + r")")        # /root, /etc/x, auch "/…" nach Praefix-Ersatz
MAX_MELDUNG_ZEILE = 200


def _praefix_muster(pfad: str) -> str | None:
    teile = [t for t in re.split(r"[\\/]+", str(pfad)) if t]
    if not teile:
        return None
    anfang = r"[\\/]+" if str(pfad)[:1] in "\\/" else ""
    return anfang + r"[\\/]+".join(re.escape(t) for t in teile) + r"(?![\w-])"


def _kuerze_pfad(m: "re.Match[str]") -> str:
    teile = [re.sub(r"^[A-Za-z]:", "", t) for t in re.split(r"[\\/]+", m.group(0)) if t and t not in ("?", ".")]
    teile = [t for t in teile if t]
    mindest = 3 if m.group("unc") else 2
    return teile[-1] if len(teile) >= mindest else "…"      # Einzelnes (z. B. /root, C:\secret.txt) nie im Klartext


def bereinige_meldung(text: str, root: Path | None = None) -> str:
    """Macht eine Fehlermeldung eines Unterprozesses fuer den Client unbedenklich: bekannte Praefixe
    (Wurzel, Python-, Home-Verzeichnis; Gross-/Kleinschreibung und Slash-Form egal) und jeder absolute
    Pfad (Laufwerk, UNC, POSIX; mit oder ohne Leerzeichen) verschwinden, hoechstens der Dateiname
    bleibt. Lieber zu viel als zu wenig. Zeilen werden gekuerzt."""
    bekannt = [root, sys.prefix, sys.base_prefix, Path(sys.executable).parent, Path.home()]
    for p in bekannt:
        muster = _praefix_muster(str(p)) if p is not None else None
        if muster:
            text = re.sub(muster, "/…", text, flags=re.IGNORECASE)
    text = _PFAD.sub(_kuerze_pfad, text)
    return text[:MAX_MELDUNG_ZEILE] + ("…" if len(text) > MAX_MELDUNG_ZEILE else "")


def starte_unterprozess(job: dict, root: Path) -> None:
    """Standard-Starter: fuehrt `pipeline/chunk-neu-uebersetzen.py` in einem Unterprozess aus.
    `--buch=WERT` in EINEM Argument: ein Buchname mit fuehrendem "-" wird nie als Option gelesen."""
    skript = Path(__file__).resolve().parent / "pipeline" / "chunk-neu-uebersetzen.py"
    cmd = [sys.executable, str(skript), "--root", str(root), f"--buch={job['buch']}",
           "--chunk", str(job["chunk"])]
    if job.get("lektor"):
        cmd.append(f"--lektor={job['lektor']}")
    lauf = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=AUFTRAG_TIMEOUT)
    if lauf.returncode != 0:
        letzte = (lauf.stderr or lauf.stdout or "").strip().splitlines()[-3:]
        raise RuntimeError(f"Übersetzung fehlgeschlagen (Exit {lauf.returncode}): "
                           + " | ".join(bereinige_meldung(z.strip(), root) for z in letzte))


def erzeuge_server(root: Path, host: str = "0.0.0.0", port: int = 8080,
                   paket: Path | None = None, token: str | None = None,
                   ip_erlaubt: Callable[[str], bool] | None = None,
                   starte: Callable[[dict], None] | None = None) -> ThreadingHTTPServer:
    """Baut den Server, startet ihn aber nicht (`serve_forever` ruft der Aufrufer).

    Wirft ValueError (vor dem Binden des Ports) bei leerem Token oder wenn `token.txt` im
    ausgelieferten Paket liegt."""
    root = Path(root)
    paket_pfad = Path(paket) if paket is not None else root / "reader" / "export-epistopheles"
    try:
        token_pfad(root).resolve().relative_to(paket_pfad.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("token.txt liegt im ausgelieferten Paket - Start verweigert")
    token = token if token is not None else lade_token(root)
    if not isinstance(token, str) or not token.strip():
        raise ValueError("Leeres Token - Start verweigert")
    httpd = RedaktionsServer((host, port), _Handler)
    httpd.root = root
    httpd.paket = paket_pfad
    httpd.token = token
    httpd.auftraege = Warteschlange(root, starte if starte is not None
                                    else (lambda job: starte_unterprozess(job, root)),
                                    bereinige=lambda t: bereinige_meldung(t, root))
    httpd.ip_erlaubt = ip_erlaubt if ip_erlaubt is not None else ip_privat
    httpd.schreib_sperre = threading.Lock()
    return httpd


def _lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # sendet nichts; waehlt nur die Route
            ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Empfänger für Redaktionsänderungen (APIC)")
    ap.add_argument("--root", help="Bibliothekswurzel (Standard: EPISTO_ROOT oder D:\\Workspace\\!Episto)")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--paket", help="Epistopheles-Paket (Standard: <root>/reader/export-epistopheles)")
    args = ap.parse_args(argv)

    import os
    from episto_tui.library import resolve_root
    root = resolve_root(args.root, os.environ)
    try:
        httpd = erzeuge_server(root, args.host, args.port,
                               Path(args.paket) if args.paket else None)
    except (OSError, ValueError) as e:
        print(f"Server konnte nicht starten: {e}", file=sys.stderr)
        return 1
    port = httpd.server_address[1]
    adresse = _lan_ip() if args.host in ("0.0.0.0", "::", "") else args.host
    print(f"Empfänger läuft: http://{adresse or 'localhost'}:{port}/")
    print(f"Token: {httpd.token}")
    print("Beenden mit Strg+C.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
