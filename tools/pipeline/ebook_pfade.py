# -*- coding: utf-8 -*-
"""Pfade aus meta.json auf den aktuellen Ablageort umsetzen.

In den meta.json der Buecher steht die Quelldatei so, wie sie beim Uebersetzen
hiess, z. B. C:\\Users\\Dude\\Tools\\eBooks\\Lektor\\<Autor>\\<Titel>\\en\\x.pdf oder
/mnt/c/Users/Dude/Tools/eBooks/Inbox/x.epub. Seit dem Umbau liegen Quelldateien und Lektor-Ordner
in D:\\Workspace\\!Episto\\rohdaten (Inbox, Lektor, Outbox) und diese Pfade gibt es nicht mehr.
quelle_aufloesen() setzt alles hinter dem letzten Ordner `eBooks` unter dem aktuellen BASE
(= rohdaten) neu auf, sofern die Datei dort existiert. Die meta.json selbst bleiben unveraendert."""
from __future__ import annotations
from pathlib import Path


def quelle_aufloesen(pfad: str | Path, base: Path) -> Path:
    """Existierender Pfad der Quelldatei: der gespeicherte, sonst derselbe Pfad unterhalb von
    `base` (Teil hinter dem Ordner `eBooks`). Findet sich nichts, kommt der gespeicherte Pfad
    unveraendert zurueck, damit Meldungen den urspruenglichen Eintrag zeigen."""
    s = str(pfad or "").replace("\\", "/")
    if not s:
        return Path("")
    if s.startswith("/mnt/") and len(s) > 6 and s[6] == "/":
        s = f"{s[5].upper()}:{s[6:]}"                       # /mnt/c/x -> C:/x
    gespeichert = Path(s)
    if gespeichert.exists():
        return gespeichert
    teile = gespeichert.parts
    for i in range(len(teile) - 1, -1, -1):
        if teile[i].lower() == "ebooks":
            neu = Path(base).joinpath(*teile[i + 1:])
            if neu.exists():
                return neu
            break
    return gespeichert
