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
import shutil
import tempfile
from datetime import datetime, timezone
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


def gueltiger_kapitelname(name: object) -> bool:
    """Reiner Dateiname einer Kapiteldatei `quelle/*.md`: kein Pfad, nicht `_…` (Index-/Technikdateien),
    kein Syncthing-Konfliktexemplar."""
    return (_gueltiger_dateiname(name) and name.endswith(".md") and not name.startswith("_")
            and ".sync-conflict-" not in name)


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


NACHSPIEL = "redaktion-nachspiel.json"


def lade_nachspiel(reader_buch: Path) -> dict | None:
    """Bericht des letzten Nachspiels (`notizen/redaktion-nachspiel.json`) oder None (fehlt / unlesbar)."""
    try:
        daten = json.loads((Path(reader_buch) / "notizen" / NACHSPIEL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return daten if isinstance(daten, dict) else None


def _schreibe_bericht(buch: Path, angewendet: int, konflikte: list[dict], basis_geaendert: list[str]) -> None:
    """Schreibt den Bericht, solange es etwas zu melden gibt (Konflikt oder geaenderte Basis); sonst wird ein
    alter Bericht entfernt. Fehler hier brechen das Nachspiel nie ab."""
    pfad = buch / "notizen" / NACHSPIEL
    try:
        if konflikte or basis_geaendert:
            pfad.parent.mkdir(parents=True, exist_ok=True)
            bericht = {"zeit": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "angewendet": angewendet,
                       "konflikte": konflikte, "basis_geaendert": basis_geaendert}
            _schreibe_atomar(pfad, json.dumps(bericht, ensure_ascii=False, indent=2).encode("utf-8"))
        elif pfad.exists():
            pfad.unlink()
    except OSError:
        pass


def sichere_quelle(reader_buch: Path) -> Path | None:
    """Kopiert die vorhandenen `quelle/*.md` nach `notizen/_backup/quelle-<Zeit>/`, wenn `notizen/redaktion.json`
    Eintraege der Ebene `volltext` enthaelt (oder nicht lesbar ist: im Zweifel sichern), und gibt den Ordner
    zurueck; sonst None. Gedacht fuer `lektor-zu-episto.py --ueberschreiben`: ab P2 steckt Handarbeit in diesen Dateien."""
    buch = Path(reader_buch)
    pfad = buch / "notizen" / REDAKTION_JSON
    if not pfad.exists():
        return None
    try:
        roh = json.loads(pfad.read_text(encoding="utf-8"))
        liste = roh.get("eintraege") if isinstance(roh, dict) else None
        volltext = True if not isinstance(liste, list) else any(
            isinstance(e, dict) and e.get("ebene") == "volltext" for e in liste)
    except (OSError, ValueError):
        volltext = True
    if not volltext:
        return None
    dateien = sorted(p for p in (buch / "quelle").glob("*.md") if p.is_file())
    if not dateien:
        return None
    zeit = datetime.now().strftime("%Y%m%dT%H%M%S")
    basis = buch / "notizen" / "_backup"
    ziel, n = basis / f"quelle-{zeit}", 1
    while ziel.exists():
        ziel = basis / f"quelle-{zeit}-{n}"
        n += 1
    ziel.mkdir(parents=True)
    for p in dateien:
        shutil.copy2(p, ziel / p.name)
    return ziel


def spiele_nach(reader_buch: Path) -> int:
    """Spielt `volltext`-Eintraege mit Status `angewendet` aus `notizen/redaktion.json`
    auf die (neu erzeugten) `quelle/*.md` ab. Gibt die Zahl der Eintraege zurueck, die
    nicht angewendet werden konnten (Konflikt, Datei fehlt/unlesbar, unzulaessiger Name).

    Verhalten:
    - Fehlt `redaktion.json`: 0 (ein vorhandener Bericht bleibt unberuehrt). Ist sie kaputt: 1
      (der Neuaufbau bricht nicht ab; der Aufrufer warnt).
    - Eintraege je Datei in Protokollreihenfolge; zurueckgenommene entfallen vorher.
    - Eine Datei wird nur geschrieben, wenn mindestens ein Eintrag griff (atomar,
      byteexakt, UTF-8); sonst bleibt sie unveraendert.
    - Wiederholter Aufruf auf bereits eingearbeitetem Text: die `vorher`-Pruefsumme
      passt nicht mehr, die Eintraege zaehlen als nicht anwendbar, der Text bleibt.
    - Bericht `notizen/redaktion-nachspiel.json`: jeder nicht anwendbare Eintrag einzeln mit `id`, `datei`
      und `grund`; `basis_geaendert` nennt Dateien, deren Ausgangstext nicht mehr dem entspricht, auf dem die
      Korrekturen entstanden (`dateien[name].hash_original`). Ohne beides wird der Bericht entfernt."""
    buch = Path(reader_buch)
    pfad = buch / "notizen" / REDAKTION_JSON

    def kaputt(grund: str, anzahl: int) -> int:
        _schreibe_bericht(buch, 0, [{"id": None, "datei": None, "grund": grund}], [])
        return anzahl

    if not pfad.exists():
        return 0
    try:
        roh = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return kaputt("redaktion.json unlesbar", 1)
    if not isinstance(roh, dict):
        return kaputt("redaktion.json unlesbar (falscher Aufbau)", 1)
    if not isinstance(roh.get("eintraege", []), list):
        return kaputt("redaktion.json unlesbar (eintraege ist keine Liste)", 1)
    eintraege = [e for e in lade_redaktion(pfad)["eintraege"] if isinstance(e, dict)]
    aktiv = [e for e in ops.ohne_zurueckgenommene(eintraege)
             if e.get("ebene") == "volltext" and e.get("status") == ops.STATUS_ANGEWENDET]
    dateien_info = roh.get("dateien") if isinstance(roh.get("dateien"), dict) else {}

    je_datei: dict[object, list[dict]] = {}
    for e in aktiv:
        ziel = e.get("ziel") if isinstance(e.get("ziel"), dict) else {}
        je_datei.setdefault(ziel.get("datei"), []).append(e)

    konflikte: list[dict] = []
    basis_geaendert: list[str] = []
    angewendet_gesamt = 0

    def melde(liste: list[dict], name: object, grund: str) -> None:
        for e in liste:
            konflikte.append({"id": e.get("id"), "datei": name if isinstance(name, str) else None, "grund": grund})

    for name, liste in je_datei.items():
        if not gueltiger_kapitelname(name):
            melde(liste, name, "Dateiname (ziel.datei) fehlt oder ist unzulässig")
            continue
        datei = buch / "quelle" / name
        try:
            text = datei.read_bytes().decode("utf-8")
        except FileNotFoundError:
            melde(liste, name, "Kapiteldatei fehlt (Neuaufbau mit anderem Dateinamen?)")
            continue
        except (OSError, UnicodeDecodeError) as exc:
            melde(liste, name, f"Kapiteldatei nicht lesbar ({type(exc).__name__})")
            continue
        info = dateien_info.get(name)
        h = info.get("hash_original") if isinstance(info, dict) else None
        if isinstance(h, str) and h and h != ops.pruefsumme(text):
            basis_geaendert.append(name)
        try:
            neu, ergebnisse = ops.spiele_ab(text, liste)
        except Exception as exc:  # noqa: BLE001
            melde(liste, name, f"Anwendung fehlgeschlagen ({type(exc).__name__})")
            continue
        griffen = [e for e, r in zip(liste, ergebnisse) if r.status == ops.STATUS_ANGEWENDET]
        for e, r in zip(liste, ergebnisse):
            if r.status != ops.STATUS_ANGEWENDET:
                melde([e], name, r.grund or "nicht angewendet")
        if griffen:
            try:
                _schreibe_atomar(datei, neu.encode("utf-8"))
                angewendet_gesamt += len(griffen)
            except OSError as exc:
                melde(griffen, name, f"Datei nicht geschrieben ({type(exc).__name__})")
    _schreibe_bericht(buch, angewendet_gesamt, konflikte, basis_geaendert)
    return len(konflikte)
