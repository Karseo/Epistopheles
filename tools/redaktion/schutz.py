"""Schutz fuer Korrekturen in den Pipeline-Skripten (Spec 5.4).

- `pruefe_neuuebersetzung`: Guard fuer `ebook-translate.py` (Neuuebersetzung wuerde
  Korrekturen auf Chunk-Ebene verwerfen).
- `pruefe_ueberschreiben`: Guard fuer `lektor-zu-episto.py` (Neuaufbau von `quelle\\*.md`).
- `spiele_nach`: spielt Volltext-Korrekturen nach dem Neuaufbau erneut ab.

Nur Standardbibliothek.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from redaktion import ops
from redaktion.protokoll import lade_redaktion

REDAKTION_JSON = "redaktion.json"


def pruefe_neuuebersetzung(buch_ordner: Path, resume: bool, verwerfen: bool) -> str | None:
    """Fehlertext, wenn `buch_ordner/redaktion.json` existiert und weder fortgesetzt
    (`resume`) noch ausdruecklich verworfen (`verwerfen`) wird; sonst `None`."""
    if resume or verwerfen:
        return None
    if not (Path(buch_ordner) / REDAKTION_JSON).exists():
        return None
    return (
        f"[ABBRUCH] Im Buchordner liegt {REDAKTION_JSON} mit Korrekturen: {buch_ordner}\n"
        "Eine Neuübersetzung ohne --resume würde alle Chunks neu übersetzen und diese "
        "Korrekturen verwerfen.\n"
        "  --resume                  führt eine abgebrochene Übersetzung fort (Korrekturen bleiben)\n"
        "  --korrekturen-verwerfen   übersetzt bewusst alles neu und nimmt die Korrekturen in Kauf"
    )


def pruefe_ueberschreiben(quelle_ordner: Path, ueberschreiben: bool, dry_run: bool) -> str | None:
    """Fehlertext, wenn `quelle_ordner` bereits `*.md` enthaelt und weder `ueberschreiben`
    noch `dry_run` gilt; sonst `None` (auch bei fehlendem oder leerem Ordner)."""
    if ueberschreiben or dry_run:
        return None
    ordner = Path(quelle_ordner)
    if not ordner.is_dir() or not any(p.is_file() for p in ordner.glob("*.md")):
        return None
    return (
        f"[ABBRUCH] {ordner} enthält bereits Kapiteldateien (*.md). Ein Neuaufbau würde "
        "sie überschreiben und darin enthaltene Korrekturen vernichten.\n"
        "Mit --ueberschreiben bewusst neu aufbauen (Volltext-Korrekturen aus "
        "notizen\\redaktion.json werden danach erneut eingespielt), mit --dry-run nur ansehen."
    )


def _gueltiger_dateiname(name: object) -> bool:
    return (isinstance(name, str) and name not in ("", ".", "..")
            and "/" not in name and "\\" not in name and "\0" not in name
            and Path(name).name == name)


def _schreibe_atomar(pfad: Path, daten: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=pfad.parent, prefix=pfad.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(daten)
        os.replace(tmp, pfad)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def spiele_nach(reader_buch: Path) -> int:
    """Spielt `volltext`-Eintraege mit Status `angewendet` aus `notizen/redaktion.json`
    auf die (neu erzeugten) `quelle/*.md` ab. Gibt die Zahl der Eintraege zurueck, die
    nicht angewendet werden konnten (Konflikt, Datei fehlt/unlesbar, unzulaessiger Name).

    Verhalten:
    - Fehlt `redaktion.json`: 0. Ist sie kaputt: Anzahl der Eintraege, wenn bestimmbar, sonst 1
      (der Neuaufbau bricht nicht ab; der Aufrufer warnt).
    - Eintraege je Datei in Protokollreihenfolge; zurueckgenommene entfallen vorher.
    - Eine Datei wird nur geschrieben, wenn mindestens ein Eintrag griff (atomar,
      byteexakt, UTF-8); sonst bleibt sie unveraendert.
    - Wiederholter Aufruf auf bereits eingearbeitetem Text: die `vorher`-Pruefsumme
      passt nicht mehr, die Eintraege zaehlen als nicht anwendbar, der Text bleibt."""
    buch = Path(reader_buch)
    pfad = buch / "notizen" / REDAKTION_JSON
    if not pfad.exists():
        return 0
    try:
        roh = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 1
    if not isinstance(roh, dict):
        return 1
    if not isinstance(roh.get("eintraege", []), list):
        return 1
    eintraege = [e for e in lade_redaktion(pfad)["eintraege"] if isinstance(e, dict)]
    aktiv = [e for e in ops.ohne_zurueckgenommene(eintraege)
             if e.get("ebene") == "volltext" and e.get("status") == ops.STATUS_ANGEWENDET]

    je_datei: dict[object, list[dict]] = {}
    for e in aktiv:
        ziel = e.get("ziel") if isinstance(e.get("ziel"), dict) else {}
        je_datei.setdefault(ziel.get("datei"), []).append(e)

    nicht_angewendet = 0
    for name, liste in je_datei.items():
        if not _gueltiger_dateiname(name):
            nicht_angewendet += len(liste)
            continue
        datei = buch / "quelle" / name
        try:
            text = datei.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            nicht_angewendet += len(liste)
            continue
        try:
            neu, ergebnisse = ops.spiele_ab(text, liste)
        except Exception:
            nicht_angewendet += len(liste)
            continue
        angewendet = sum(1 for r in ergebnisse if r.status == ops.STATUS_ANGEWENDET)
        nicht_angewendet += len(liste) - angewendet
        if angewendet:
            try:
                _schreibe_atomar(datei, neu.encode("utf-8"))
            except OSError:
                nicht_angewendet += angewendet
    return nicht_angewendet
