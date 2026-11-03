"""Qdrant NUR LESEND abfragen und Chunk-Nachbarn zu Kapitelkanten zusammenfassen (Plan 2026-11-03, Task 3).

Fuer die Ansicht "Verbindungen": zu jedem Chunk die aehnlichsten Chunks ANDERER Werke. Die Abfrage nimmt die
Punkt-Id als Eingabe (Query-API, Qdrant >= 1.10, entwickelt gegen 1.18); die Vektoren liegen schon in Qdrant,
es wird also kein Ollama gebraucht. Aeltere Server: Rueckfall auf `recommend`.

Lesend heisst: erlaubt sind nur `scroll`, `query`, `recommend` (jeweils auch `/batch`) und `GET /collections/<name>`;
`abruf` verweigert alles andere, bevor etwas gesendet wird. Nur Standardbibliothek."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlsplit

FELDER = ("autor", "buch", "kapitel_nr", "chunk_idx")      # Payload ohne den (grossen) Text
BELEG_LAENGE = 140
_ERLAUBT = (("GET", re.compile(r"/collections/[^/]+")),
            ("POST", re.compile(r"/collections/[^/]+/points/(scroll|query|query/batch|recommend|recommend/batch)")))


class QdrantFehler(Exception):
    """Eine Anfrage ist gescheitert. `status` 0 = Verbindung/Zeitueberschreitung, sonst der HTTP-Status."""

    def __init__(self, status: int, text: str = ""):
        super().__init__(f"Qdrant: Status {status} {text}".strip())
        self.status = status


def abruf(methode: str, url: str, body: dict | None = None, timeout: float = 120) -> dict:
    """Ein Aufruf an Qdrant, Antwort als UTF-8-JSON. Nicht erlaubte Methoden/Pfade -> ValueError (nichts wird gesendet)."""
    pfad = urlsplit(url).path
    if not any(methode == m and r.fullmatch(pfad) for m, r in _ERLAUBT):
        raise ValueError(f"nur lesende Qdrant-Aufrufe sind erlaubt: {methode} {pfad}")
    daten = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=daten, method=methode, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))        # Qdrant sendet kein charset: Bytes selbst als UTF-8 lesen
    except urllib.error.HTTPError as e:
        raise QdrantFehler(e.code, e.reason if isinstance(e.reason, str) else "") from None
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as e:
        raise QdrantFehler(0, type(e).__name__) from None


def _mit_wiederholung(fn, versuche: int, pause: float):
    """Wiederholt bei Verbindungsfehlern, 429 und 5xx (Wartezeit verdoppelt sich); andere Fehler gehen sofort weiter."""
    for i in range(max(1, versuche)):
        try:
            return fn()
        except QdrantFehler as e:
            if i + 1 >= versuche or not (e.status == 0 or e.status == 429 or e.status >= 500):
                raise
            time.sleep(pause * (2 ** i))


def lese_punkte(qdrant: str, collection: str, fetch=None, seite: int = 1000, pause: float = 1.0, versuche: int = 3) -> dict[int, dict]:
    """Alle Punkte seitenweise (ohne Vektoren, nur `FELDER`): Punkt-Id -> {autor, buch, kapitel_nr, chunk_idx}.
    Punkte mit unvollstaendiger Payload entfallen. Scheitert eine Seite endgueltig: QdrantFehler."""
    fetch = fetch or abruf
    url = f"{qdrant.rstrip('/')}/collections/{collection}/points/scroll"
    punkte: dict[int, dict] = {}
    offset = None
    while True:
        body = {"limit": seite, "with_payload": {"include": list(FELDER)}, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        antwort = _mit_wiederholung(lambda: fetch("POST", url, body), versuche, pause)["result"]
        for p in antwort.get("points", []):
            pl = p.get("payload") or {}
            if all(k in pl for k in FELDER) and isinstance(pl["kapitel_nr"], int):
                punkte[p["id"]] = {k: pl[k] for k in FELDER}
        offset = antwort.get("next_page_offset")
        if offset is None:
            return punkte


@dataclass
class Nachbarn:
    treffer: dict[int, list[dict]] = field(default_factory=dict)    # Punkt-Id -> Treffer (absteigend nach Wert)
    abgefragt: int = 0
    fehlend: int = 0                                                # endgueltig gescheiterte Abfragen (nie verschluckt)
    api: str = "query"                                              # benutzt: "query" oder "recommend" (Rueckfall)


def _kurz(text: object) -> str:
    t = " ".join(text.split()) if isinstance(text, str) else ""
    return t[:BELEG_LAENGE].rstrip() + "…" if len(t) > BELEG_LAENGE else t


def _filter(quelle: dict) -> dict:
    """Dasselbe Werk (Autor UND Buch des Ausgangspunkts) ausschliessen, serverseitig."""
    return {"must_not": [{"must": [{"key": "autor", "match": {"value": quelle["autor"]}},
                                   {"key": "buch", "match": {"value": quelle["buch"]}}]}]}


def _treffer(punkte: list[dict]) -> list[dict]:
    aus = []
    for p in punkte:
        pl = p.get("payload") or {}
        if isinstance(pl.get("autor"), str) and isinstance(pl.get("buch"), str) and isinstance(pl.get("kapitel_nr"), int):
            aus.append({"id": p["id"], "wert": float(p["score"]), "autor": pl["autor"], "buch": pl["buch"],
                        "kapitel_nr": pl["kapitel_nr"], "text": _kurz(pl.get("text"))})
    return aus


def frage_nachbarn(qdrant: str, collection: str, punkte: dict[int, dict], punkt_ids: list[int], je: int = 10, fetch=None,
                   batch: int = 50, pause: float = 1.0, versuche: int = 3, fortschritt=None) -> Nachbarn:
    """Zu jedem Punkt in `punkt_ids` die `je` aehnlichsten Punkte anderer Werke. Batches; scheitert ein Batch, werden seine
    Punkte einzeln abgefragt, nur dort endgueltig Gescheitertes zaehlt als `fehlend`. 404 der Query-API: ab dann `recommend`.
    `fortschritt(fertig, gesamt)` wird nach jedem Batch gerufen."""
    fetch = fetch or abruf
    basis = f"{qdrant.rstrip('/')}/collections/{collection}/points"
    inc = {"include": list(FELDER) + ["text"]}
    erg = Nachbarn(abgefragt=len(punkt_ids))

    def suche(pid: int) -> dict:
        f = _filter(punkte[pid])
        if erg.api == "query":
            return {"query": pid, "limit": je, "filter": f, "with_payload": inc}
        return {"positive": [pid], "limit": je, "filter": f, "with_payload": inc}

    def batch_abfrage(ids: list[int]) -> list[list[dict]]:
        pfad = "/query/batch" if erg.api == "query" else "/recommend/batch"
        r = _mit_wiederholung(lambda: fetch("POST", basis + pfad, {"searches": [suche(i) for i in ids]}), versuche, pause)["result"]
        return [(x["points"] if erg.api == "query" else x) for x in r]

    def einzel_abfrage(pid: int) -> list[dict]:
        pfad = "/query" if erg.api == "query" else "/recommend"
        r = _mit_wiederholung(lambda: fetch("POST", basis + pfad, suche(pid)), versuche, pause)["result"]
        return r["points"] if erg.api == "query" else r

    bekannt = [i for i in punkt_ids if i in punkte]
    erg.fehlend += len(punkt_ids) - len(bekannt)
    for start in range(0, len(bekannt), max(1, batch)):
        ids = bekannt[start:start + batch]
        try:
            try:
                antworten = batch_abfrage(ids)
            except QdrantFehler as e:
                if e.status != 404 or erg.api != "query":
                    raise
                erg.api = "recommend"                              # aeltere Version ohne Query-API
                antworten = batch_abfrage(ids)
            for pid, pts in zip(ids, antworten):
                erg.treffer[pid] = _treffer(pts)
        except QdrantFehler:
            for pid in ids:                                        # ein schlechter Punkt soll nicht den ganzen Batch kosten
                try:
                    erg.treffer[pid] = _treffer(einzel_abfrage(pid))
                except QdrantFehler:
                    erg.fehlend += 1
        if fortschritt:
            fortschritt(start + len(ids), len(bekannt))
    return erg


def fasse_zusammen(nachbarn: dict[int, list[dict]], punkte: dict[int, dict], kapitel_ids: set[str], werke: dict[tuple[str, str], str],
                   mindestwert: float, je_kapitel: int = 8) -> list[dict]:
    """Kapitelkanten im Format `aehnlich` von verbindungen.json: [{von, nach, wert, beleg}] (gerichtet).

    `werke`: (autor, buch) -> Werk-Id (z. B. aus `baue_basis`), `kapitel_ids`: gueltige Kapitel-Ids ("b001:3").
    Je Kapitelpaar zaehlen alle Chunk-Paare ueber `mindestwert`; Rang = Summe der drei besten, `wert` = bestes Paar,
    `beleg` = Text des besten Zielchunks. Je Ausgangskapitel die `je_kapitel` ranghoechsten Ziele (Gleichstand: nach Id).
    Nie eine Kante auf sich selbst oder innerhalb desselben Werks; unbekannte Werke und Kapitel entfallen."""
    paare: dict[tuple[str, str], list[tuple[float, str]]] = {}
    for pid, treffer in nachbarn.items():
        quelle = punkte.get(pid)
        von_werk = werke.get((quelle["autor"], quelle["buch"])) if quelle else None
        if von_werk is None or f"{von_werk}:{quelle['kapitel_nr']}" not in kapitel_ids:
            continue
        von = f"{von_werk}:{quelle['kapitel_nr']}"
        for t in treffer:
            nach_werk = werke.get((t["autor"], t["buch"]))
            nach = f"{nach_werk}:{t['kapitel_nr']}" if nach_werk else None
            if nach is None or nach_werk == von_werk or nach not in kapitel_ids or t["wert"] < mindestwert:
                continue
            paare.setdefault((von, nach), []).append((t["wert"], t["text"]))
    je_von: dict[str, list[tuple[float, str, float, str]]] = {}
    for (von, nach), liste in paare.items():
        liste.sort(key=lambda x: -x[0])
        rang = sum(w for w, _ in liste[:3])
        je_von.setdefault(von, []).append((rang, nach, liste[0][0], liste[0][1]))
    kanten = []
    for von in sorted(je_von):
        for rang, nach, wert, beleg in sorted(je_von[von], key=lambda x: (-x[0], x[1]))[:je_kapitel]:
            kanten.append({"von": von, "nach": nach, "wert": round(wert, 3), "beleg": beleg})
    return kanten
