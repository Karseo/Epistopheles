"""Fussnotenanalyse fuer den fertigen Volltext (P2 Task 6): Marker `[^id]` im Text, Definitionen
`[^id]: Text` (Zeilenanfang, meist am Kapitelende), Hinweise bei fehlender Zuordnung.

Reine Funktionen, nur Standardbibliothek. Gegenstueck in JavaScript: speedreader_web/fussnoten.js
(gleiche Vektoren in testvektoren_fussnoten.json). Die Angaben `absatz_index` / `zeile` /
`vorkommen` sind genau die Ziele, die `ops.py` (Art `fussnote`) versteht.

- marker: {id, absatz_index, zeile, vorkommen, in_definition}; `vorkommen` zaehlt je Absatz und Kennung
  (wie `marker-umbenennen`); `in_definition` = im Absatz steht davor (oder in dieser Zeile) schon
  eine Definition, der Marker gehoert also zum Definitionsblock.
- definitionen: {id, absatz_index, zeile}
- hinweise (in Textreihenfolge): marker-ohne-definition (am ersten Marker der Kennung),
  definition-ohne-marker (an der ersten Definition), doppelte-definition (an jeder weiteren),
  andere-konvention (nur ohne jede [^id]:-Definition).
Andere Fussnotenkonventionen werden nur gemeldet, nie bearbeitet.
"""
from __future__ import annotations

import re

from episto_tui.korrektur import absatz_spannen
from redaktion.ops import _KENNUNG_ZEICHEN, _MARKER

_DEFINITION = re.compile(r"\[\^(" + _KENNUNG_ZEICHEN + r"+)\]:")
_NUMMERZEILE = re.compile(r"\*?\d{1,3}[.)]?[ \t ]+\S")
_ZEILENENDE = re.compile(r"\r?\n")
LETZTE_ABSAETZE = 10          # andere-konvention: so viele Absaetze am Kapitelende werden angesehen
MIN_NUMMERZEILEN = 3

TEXTE = {
    "marker-ohne-definition": "Verweis [^{id}] hat keinen Fußnotentext",
    "definition-ohne-marker": "Fußnotentext [^{id}] wird nirgends verwiesen",
    "doppelte-definition": "Fußnotentext [^{id}] ist mehrfach vorhanden",
    "andere-konvention": "Fußnoten scheinen nicht als [^Nr] ausgezeichnet zu sein (Zeilen mit Nummer am Kapitelende)",
}


def _hinweis(art: str, kennung: str, absatz: int, zeile: int) -> dict:
    return {"art": art, "id": kennung, "absatz_index": absatz, "zeile": zeile,
            "begruendung": TEXTE[art].format(id=kennung)}


def analysiere(text: str) -> dict:
    absaetze: list[list[str]] = [_ZEILENENDE.split(text[a:b]) for a, b in absatz_spannen(text)]
    marker: list[dict] = []
    definitionen: list[dict] = []
    for ai, zeilen in enumerate(absaetze):
        gezaehlt: dict[str, int] = {}
        in_def = False
        for zi, zeile in enumerate(zeilen):
            d = _DEFINITION.match(zeile)
            if d:
                in_def = True
                definitionen.append({"id": d.group(1), "absatz_index": ai, "zeile": zi})
            for m in _MARKER.finditer(zeile):
                k = m.group(1)
                marker.append({"id": k, "absatz_index": ai, "zeile": zi, "vorkommen": gezaehlt.get(k, 0),
                               "in_definition": in_def})
                gezaehlt[k] = gezaehlt.get(k, 0) + 1

    mit_marker = {m["id"] for m in marker}
    mit_definition = {d["id"] for d in definitionen}
    ereignisse: list[tuple[int, int, int, dict]] = []     # (absatz, zeile, laufende Nr., Hinweis) in Textreihenfolge
    gesehen_marker: set[str] = set()
    for m in marker:
        if m["id"] not in mit_definition and m["id"] not in gesehen_marker:
            ereignisse.append((m["absatz_index"], m["zeile"], len(ereignisse),
                               _hinweis("marker-ohne-definition", m["id"], m["absatz_index"], m["zeile"])))
        gesehen_marker.add(m["id"])
    gesehen_def: set[str] = set()
    for d in definitionen:
        if d["id"] in gesehen_def:
            art = "doppelte-definition"
        elif d["id"] not in mit_marker:
            art = "definition-ohne-marker"
        else:
            art = None
        gesehen_def.add(d["id"])
        if art:
            ereignisse.append((d["absatz_index"], d["zeile"], len(ereignisse), _hinweis(art, d["id"], d["absatz_index"], d["zeile"])))
    ereignisse.sort(key=lambda e: (e[0], e[1], e[2]))
    hinweise = [e[3] for e in ereignisse]

    if not definitionen:
        treffer = [(ai, zi) for ai in range(max(0, len(absaetze) - LETZTE_ABSAETZE), len(absaetze))
                   for zi, zeile in enumerate(absaetze[ai]) if not zeile.startswith("#") and _NUMMERZEILE.match(zeile)]
        if len(treffer) >= MIN_NUMMERZEILEN:
            hinweise.append(_hinweis("andere-konvention", "", treffer[0][0], treffer[0][1]))

    return {"marker": marker, "definitionen": definitionen, "hinweise": hinweise,
            "bilanz": {"marker": len(marker), "definitionen": len(definitionen)}}


def _zaehle(eintraege: list[dict]) -> dict[str, int]:
    z: dict[str, int] = {}
    for e in eintraege:
        z[e["id"]] = z.get(e["id"], 0) + 1
    return z


def bilanz(vorher: str, nachher: str) -> dict:
    """Unterschied der Fussnoten zwischen zwei Fassungen eines Kapitels:
    {marker: {id: [vorher, nachher]}, definitionen: {...}, neue_hinweise: [...]}; nur geaenderte
    Kennungen, `neue_hinweise` = Hinweise der neuen Fassung, die es vorher (gleiche Art und Kennung) nicht gab."""
    a, b = analysiere(vorher), analysiere(nachher)

    def diff(x: list[dict], y: list[dict]) -> dict:
        zx, zy = _zaehle(x), _zaehle(y)
        return {k: [zx.get(k, 0), zy.get(k, 0)] for k in {*zx, *zy} if zx.get(k, 0) != zy.get(k, 0)}

    bekannt = {(h["art"], h["id"]) for h in a["hinweise"]}
    return {"marker": diff(a["marker"], b["marker"]), "definitionen": diff(a["definitionen"], b["definitionen"]),
            "neue_hinweise": [h for h in b["hinweise"] if (h["art"], h["id"]) not in bekannt]}
