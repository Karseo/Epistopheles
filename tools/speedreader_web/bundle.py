"""Das Epistopheles-Paket: der Ordner <Wurzel>\\reader\\export-epistopheles enthaelt die erzeugten
Daten (daten.json, buecher\\, korrektur\\) UND die App-Dateien, also alles, was auf das Chromebook
kopiert oder per `python -m http.server` ausgeliefert wird. Die App-Dateien stammen aus diesem Ordner
(tools\\speedreader_web) und werden bei jedem Export mitkopiert."""
from __future__ import annotations
import shutil
from pathlib import Path

APP_DATEIEN = ("index.html", "korrektur.html", "speedreader.js", "lesetext.js", "epub.js", "redaktion.js",
               "verdacht.js", "chunkansicht.js")
PAKET_ORDNER = ("reader", "export-epistopheles")          # relativ zur Bibliothekswurzel


def standard_paket(root: Path) -> Path:
    return Path(root).joinpath(*PAKET_ORDNER)


def kopiere_app(ziel: Path) -> list[str]:
    """Kopiert die App-Dateien nach `ziel` (legt den Ordner an), gibt die Namen zurueck."""
    quelle = Path(__file__).resolve().parent
    ziel = Path(ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    kopiert = []
    for name in APP_DATEIEN:
        shutil.copyfile(quelle / name, ziel / name)
        kopiert.append(name)
    return kopiert
