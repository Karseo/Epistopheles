"""Protokolldateien der Redaktion und sichere Buchpfade (Spec 5.1, 5.2).

Ablage auf dem Empfaenger (APIC):
    <root>/hilfsdaten/redaktion/eingang/<Autor>/<Titel>/<geraet>-<yyyymmddTHHMMSS>.json
    <root>/hilfsdaten/redaktion/eingang/<Autor>/<Titel>/_stand.json

Buchschluessel kommen ueber das Netz und gelten als nicht vertrauenswuerdig:
`eingang_ordner` laesst nur genau zwei saubere Namensteile zu und prueft zusaetzlich
am aufgeloesten Pfad, dass das Ergebnis im Eingang bleibt. Alle Schreibvorgaenge sind
atomar (temporaere Datei im selben Ordner, dann `os.replace`). Nur Standardbibliothek.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

STAND_DATEI = "_stand.json"
_VERBOTENE_ZEICHEN = set('/\\:*?"<>|')
_RESERVIERT = {"CON", "PRN", "AUX", "NUL",
               *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_GERAET_UNGUELTIG = re.compile(r"[^A-Za-z0-9_.-]")


def buch_schluessel(autor: str, titel: str) -> str:
    return f"{autor}/{titel}"


def _pruefe_teil(teil: object) -> str:
    """Prueft einen Namensteil (Autor oder Titel); wirft ValueError."""
    if not isinstance(teil, str) or not teil:
        raise ValueError("leerer Buchnamensteil")
    if teil != teil.strip():
        raise ValueError(f"Leerraum am Rand: {teil!r}")
    if set(teil) & _VERBOTENE_ZEICHEN:
        raise ValueError(f"unzulaessiges Zeichen im Buchnamen: {teil!r}")
    if any(ord(c) < 32 or ord(c) == 127 for c in teil):
        raise ValueError(f"Steuerzeichen im Buchnamen: {teil!r}")
    if teil.endswith("."):
        raise ValueError(f"Punkt am Ende (auch . und ..): {teil!r}")
    if teil.split(".")[0].rstrip().upper() in _RESERVIERT:
        raise ValueError(f"reservierter Name: {teil!r}")
    return teil


def _eingang_basis(root: Path) -> Path:
    return Path(root) / "hilfsdaten" / "redaktion" / "eingang"


def pruefe_schluessel(wert: object) -> str:
    """Prueft einen Buchschluessel `"Autor/Titel"` (auch den Lektor-Schluessel eines Eintrags);
    gibt ihn unveraendert zurueck oder wirft ValueError. Nie 'reparieren'."""
    if not isinstance(wert, str):
        raise ValueError("Buchschluessel ist kein Text")
    teile = wert.split("/")
    if len(teile) != 2:
        raise ValueError(f"Buchschluessel braucht genau zwei Teile: {wert!r}")
    for t in teile:
        _pruefe_teil(t)
    return wert


def reader_ordner(root: Path, buch: str) -> Path:
    """Buchordner der Bibliothek `root/reader/<Autor>/<Werk>`; wirft ValueError bei unsicheren Namen."""
    autor, titel = pruefe_schluessel(buch).split("/")
    return Path(root) / "reader" / autor / titel


def eingang_ordner(root: Path, buch: str) -> Path:
    """Eingangsordner eines Buchs `"Autor/Titel"`; wirft ValueError bei unsicheren Namen."""
    autor, titel = pruefe_schluessel(buch).split("/")
    basis = _eingang_basis(root)
    ziel = basis / autor / titel
    try:
        ziel.resolve().relative_to(basis.resolve())
    except ValueError:
        raise ValueError(f"Pfad verlaesst den Eingang: {buch!r}") from None
    return ziel


def _atomar_schreiben(pfad: Path, daten: object) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=pfad.parent, prefix=pfad.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(daten, f, ensure_ascii=False, indent=2)
        os.replace(tmp, pfad)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _lies_json(pfad: Path) -> object | None:
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _eintragsdateien(ordner: Path) -> list[Path]:
    if not ordner.is_dir():
        return []
    return sorted(p for p in ordner.glob("*.json") if p.is_file() and p.name != STAND_DATEI)


def _geraet_bereinigt(geraet: object) -> str:
    name = _GERAET_UNGUELTIG.sub("_", str(geraet)).lstrip(".")
    return name or "geraet"


_OHNE_MS = re.compile(r"(\d{2}:\d{2}:\d{2})Z\Z")


def _zeitschluessel(erstellt: object) -> str:
    """Sortierschluessel fuer `erstellt`: Zeiten ohne Millisekunden (aeltere Geraete) zaehlen als `.000`, damit sie
    sich mit Zeiten mit Millisekunden richtig mischen (sonst sortiert `…:05Z` hinter `…:05.123Z`)."""
    return _OHNE_MS.sub(r"\1.000Z", str(erstellt if erstellt is not None else ""))


def lade_eingang(root: Path, buch: str) -> list[dict]:
    """Alle Eintraege des Buchs, nach `erstellt` sortiert, je `id` einmal.

    Kaputte oder unlesbare Dateien werden uebersprungen."""
    gesehen: dict[str, dict] = {}
    for datei in _eintragsdateien(eingang_ordner(root, buch)):
        daten = _lies_json(datei)
        if not isinstance(daten, list):
            continue
        for e in daten:
            if isinstance(e, dict) and isinstance(e.get("id"), str):
                gesehen.setdefault(e["id"], e)
    return sorted(gesehen.values(), key=lambda e: _zeitschluessel(e.get("erstellt")))


def schreibe_eingang(root: Path, geraet: str, buch: str, eintraege: list[dict]) -> list[str]:
    """Speichert neue Eintraege in einer neuen Datei; gibt die neu angenommenen Ids zurueck.

    Bekannte Ids (in irgendeiner Datei des Buchs) werden uebersprungen, ebenso Eintraege
    ohne Text-`id`. Das Argument `buch` gilt vor dem Feld `buch` des Eintrags."""
    ordner = eingang_ordner(root, buch)
    bekannt = {e["id"] for e in lade_eingang(root, buch)}
    neu: list[dict] = []
    for e in eintraege:
        if not isinstance(e, dict) or not isinstance(e.get("id"), str) or e["id"] in bekannt:
            continue
        bekannt.add(e["id"])
        neu.append({**e, "buch": buch})
    if not neu:
        return []
    stempel = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    basis = f"{_geraet_bereinigt(geraet)}-{stempel}"
    pfad = ordner / f"{basis}.json"
    zaehler = 1
    while pfad.exists():
        zaehler += 1
        pfad = ordner / f"{basis}-{zaehler}.json"
    _atomar_schreiben(pfad, neu)
    return [e["id"] for e in neu]


def liste_buecher(root: Path) -> list[str]:
    """Alle Buchschluessel `"Autor/Titel"` mit Eingangsordner (genau zwei Ebenen), sortiert."""
    basis = _eingang_basis(root)
    if not basis.is_dir():
        return []
    schluessel = []
    for autor in basis.iterdir():
        if not autor.is_dir():
            continue
        for titel in autor.iterdir():
            if titel.is_dir():
                schluessel.append(f"{autor.name}/{titel.name}")
    return sorted(schluessel)


def lade_stand(root: Path, buch: str) -> dict[str, dict]:
    """Stand je Eintrags-Id (`_stand.json`); fehlt oder kaputt -> leer."""
    daten = _lies_json(eingang_ordner(root, buch) / STAND_DATEI)
    return daten if isinstance(daten, dict) else {}


def setze_stand(root: Path, buch: str, id: str, status: str, grund: str = "") -> None:
    pfad = eingang_ordner(root, buch) / STAND_DATEI
    stand = lade_stand(root, buch)
    stand[id] = {"status": status, "grund": grund,
                 "zeit": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    _atomar_schreiben(pfad, stand)


def lade_redaktion(pfad: Path) -> dict:
    """Liest `redaktion.json` eines Buchs; fehlt oder kaputt -> leere Struktur."""
    daten = _lies_json(Path(pfad))
    if not isinstance(daten, dict):
        daten = {}
    daten.setdefault("eintraege", [])
    daten.setdefault("chunks", {})
    return daten


def speichere_redaktion(pfad: Path, daten: dict) -> None:
    _atomar_schreiben(Path(pfad), daten)
