"""Verbindungsdaten fuer die Ansicht "Verbindungen" der Epistopheles-App (Plan 2026-11-03):
`verbindungen.json` neben `daten.json` im Paket <Bibliothek>\\reader\\export-epistopheles\\.

Dieses Modul baut zuerst die Basis aus den Dateien der Buchordner (Werke, Kapitel, Themen = Straenge,
Querverweise); die Aehnlichkeit aus Qdrant kommt aus `qdrant_nachbarn.py`. Die Ids beziehen sich auf
`daten.json` (Buch-Id `b001`, Kapitelnummer): nur Buecher und Kapitel, die dort stehen, sind Knoten.

Id-Schema: Werk `b001`, Kapitel `b001:3`, Thema `b001#strang-slug`.
Nur lesend. Nur Standardbibliothek."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # tools\ fuer episto_tui

from episto_tui import library  # noqa: E402


def _text(wert: object) -> str:
    return wert if isinstance(wert, str) else ""


def baue_basis(root: Path, daten: dict) -> dict:
    """`werke`, `kapitel`, `themen`, `querverweise` im Format von verbindungen.json (siehe Plan).

    `daten` ist der Inhalt von daten.json (nur `buecher[].id/autor/titel/kapitel[].nr/titel` werden gelesen).
    Buecher ohne Ordner in der Bibliothek und Ordner ohne Eintrag in daten.json entfallen. Themen verweisen nur
    auf Kapitel aus daten.json und haben mindestens zwei davon; ein Querverweis hat `nach` = Buch-Id, wenn das
    Zielwerk in der Bibliothek UND in daten.json liegt, sonst `nach: None` (Werk ausserhalb: nicht oeffnbar).
    Fehlerhafte Eintraege der Buchdateien werden uebersprungen, nie eine Ausnahme."""
    platte = library.discover_books(root)
    nach_name = {(b.autor, b.titel): b for b in platte}
    eintraege = [(e, nach_name[(e.get("autor"), e.get("titel"))]) for e in daten.get("buecher", [])
                 if isinstance(e, dict) and (e.get("autor"), e.get("titel")) in nach_name and isinstance(e.get("id"), str)]
    id_von_buch = {id(buch): e["id"] for e, buch in eintraege}      # Buch-Objekt -> Buch-Id aus daten.json

    werke, kapitel, themen, querverweise = [], [], [], []
    for e, buch in eintraege:
        wid = e["id"]
        werke.append({"id": wid, "autor": buch.autor, "titel": buch.titel})
        nummern = set()
        for k in e.get("kapitel", []):
            if isinstance(k, dict) and isinstance(k.get("nr"), int):
                nummern.add(k["nr"])
                kapitel.append({"id": f"{wid}:{k['nr']}", "werk": wid, "nr": k["nr"], "titel": _text(k.get("titel"))})
        for s in library.list_straenge(buch):
            vorhanden = [nr for nr in s["kapitel"] if nr in nummern]
            if len(vorhanden) >= 2:
                themen.append({"id": f"{wid}#{s['slug']}", "werk": wid, "name": s["name"], "kapitel": vorhanden})
        gesehen = set()
        try:
            bezuege = library.read_querbezuege(buch)
        except ValueError:                                           # z. B. kein UTF-8 in der Datei
            bezuege = []
        for b in bezuege:
            ziel = b.get("ziel")
            if not isinstance(ziel, str) or not ziel:
                continue
            ziel_buch = library.finde_buch_fuer_ziel(platte, ziel)
            nach = id_von_buch.get(id(ziel_buch)) if ziel_buch is not None else None
            if nach == wid:
                continue                                              # Verweis auf das eigene Werk
            eintrag = {"von": wid, "nach": nach, "autor": _text(b.get("autor")), "titel": _text(b.get("titel")),
                       "relation": _text(b.get("relation")), "notiz": _text(b.get("notiz"))}
            schluessel = (nach, ziel if nach is None else "", eintrag["relation"])
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            querverweise.append(eintrag)
    return {"werke": werke, "kapitel": kapitel, "themen": themen, "querverweise": querverweise}
