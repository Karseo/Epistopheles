"""Einmaliger Umzug der Bibliothekswurzel auf die Struktur rohdaten / reader / tools / hilfsdaten.

Der Umbau hat zwei Teile: Der Branch `worktree-datenstruktur` ordnet alles VERSIONIERTE um (git mv
Autor -> reader usw.). Dieses Skript verschiebt, was nicht in Git liegt oder ignoriert ist
(eBooks\\Inbox/Lektor/Outbox/Transfer, Wurzel-Inbox, en-Chunks, ignorierte Notizen, ...). Reihenfolge:

    1. Syncthing pausieren, getrackte Aenderungen committen.
    2. python tools\\umbau_datenstruktur.py vorher   [--ausfuehren]     (Dry-Run ohne --ausfuehren)
    3. git merge worktree-datenstruktur                                (benennt Autor -> reader um)
    4. python tools\\umbau_datenstruktur.py nachher  [--ausfuehren]
    5. python tools\\umbau_datenstruktur.py pruefen

Regeln: Nie etwas ueberschreiben. Identische Dateien werden zusammengefuehrt, abweichende bleiben an ihrem
alten Ort liegen und werden gemeldet (Exit-Code 2). `vorher` KOPIERT die en-Chunks (der Merge loescht die
getrackten Dateien aus Autor\\), alles andere wird verschoben."""
from __future__ import annotations
import argparse
import filecmp
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT = Path(r"D:\Workspace\!Episto")
ROHDATEN_UNTER = ("Inbox", "Lektor", "Outbox", "Transfer")


@dataclass
class Aktion:
    art: str                  # "kopiere" | "verschiebe"
    quelle: Path
    ziel: Path
    beschreibung: str = ""


@dataclass
class Ergebnis:
    verschoben: int = 0
    kopiert: int = 0
    zusammengefuehrt: int = 0      # identische Datei am Ziel, Quelle entfernt bzw. uebersprungen
    konflikte: list[tuple[Path, Path]] = None

    def __post_init__(self):
        if self.konflikte is None:
            self.konflikte = []


def _dateien(ordner: Path):
    return sorted(p for p in ordner.rglob("*") if p.is_file())


def _leere_ordner_entfernen(ordner: Path) -> None:
    """Entfernt `ordner` und leere Unterordner (von unten), laesst nicht Leeres stehen."""
    for p in sorted((d for d in ordner.rglob("*") if d.is_dir()), key=lambda d: len(d.parts), reverse=True):
        try:
            p.rmdir()
        except OSError:
            pass
    try:
        ordner.rmdir()
    except OSError:
        pass


def fuehre_aus(aktion: Aktion, ergebnis: Ergebnis) -> None:
    quelle, ziel = aktion.quelle, aktion.ziel
    verschiebe = aktion.art == "verschiebe"
    if not quelle.exists():
        return
    if verschiebe and not ziel.exists():                      # ganzer Ordner, Ziel frei: Umbenennen (schnell, atomar)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        zahl = sum(1 for _ in _dateien(quelle)) if quelle.is_dir() else 1
        quelle.rename(ziel)
        ergebnis.verschoben += zahl
        return
    if quelle.is_file():
        paare = [(quelle, ziel)]
    else:
        paare = [(f, ziel / f.relative_to(quelle)) for f in _dateien(quelle)]
    for src, dst in paare:
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            if verschiebe:
                shutil.move(str(src), str(dst)); ergebnis.verschoben += 1
            else:
                shutil.copy2(src, dst); ergebnis.kopiert += 1
        elif filecmp.cmp(src, dst, shallow=False):
            ergebnis.zusammengefuehrt += 1
            if verschiebe:
                src.unlink()
        else:
            ergebnis.konflikte.append((src, dst))           # bleibt liegen
    if verschiebe and quelle.is_dir():
        _leere_ordner_entfernen(quelle)


def plan_vorher(root: Path) -> list[Aktion]:
    aktionen: list[Aktion] = []
    autor = root / "Autor"
    for en in sorted(autor.glob("*/*/en")) if autor.is_dir() else []:
        if en.is_dir() and any(en.iterdir()):
            ziel = root / "rohdaten" / "en-chunks" / en.parent.parent.name / en.parent.name
            aktionen.append(Aktion("kopiere", en, ziel, "en-Chunks eines Buchs (Kopie, der Merge loescht die getrackten)"))
    ebooks = root / "eBooks"
    for name in ROHDATEN_UNTER:
        if (ebooks / name).is_dir():
            aktionen.append(Aktion("verschiebe", ebooks / name, root / "rohdaten" / name, f"eBooks\\{name}"))
    if (root / "Inbox").is_dir():
        aktionen.append(Aktion("verschiebe", root / "Inbox", root / "rohdaten" / "Inbox", "Wurzel-Inbox (Dubletten werden zusammengefuehrt)"))
    return aktionen


def plan_nachher(root: Path) -> list[Aktion]:
    aktionen: list[Aktion] = []
    autor = root / "Autor"
    if autor.is_dir():
        for en in sorted(autor.glob("*/*/en")):                  # Reste (ignoriert/untracked): nach rohdaten, nicht nach reader
            if en.is_dir():
                ziel = root / "rohdaten" / "en-chunks" / en.parent.parent.name / en.parent.name
                aktionen.append(Aktion("verschiebe", en, ziel, "en-Reste aus Autor\\"))
        aktionen.append(Aktion("verschiebe", autor, root / "reader", "Reste aus Autor\\ (ignorierte/neue Dateien) nach reader\\"))
    if (root / "Autor.mov").is_dir():
        aktionen.append(Aktion("verschiebe", root / "Autor.mov", root / "hilfsdaten" / "archiv" / "Autor.mov", "Altbestand"))
    if (root / "notizen").is_dir():
        aktionen.append(Aktion("verschiebe", root / "notizen", root / "hilfsdaten" / "notizen", "Buch-Queue"))
    if (root / "eBooks").is_dir():
        aktionen.append(Aktion("verschiebe", root / "eBooks", root / "hilfsdaten" / "archiv" / "eBooks-vor-umbau",
                               "alte Skripte (die Kopien liegen in tools\\pipeline)"))
    return aktionen


def git_sauber(root: Path) -> bool:
    lauf = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
                          capture_output=True, text=True, encoding="utf-8")
    return lauf.returncode == 0 and not lauf.stdout.strip()


def pruefen(root: Path) -> list[str]:
    """Liste der Beanstandungen (leer = alles in Ordnung)."""
    probleme = []
    for pfad, name in [(root / "Autor", "Autor\\ existiert noch"), (root / "eBooks", "eBooks\\ existiert noch"),
                       (root / "Inbox", "Wurzel-Inbox existiert noch"), (root / "notizen", "Wurzel-notizen existiert noch"),
                       (root / "Autor.mov", "Autor.mov existiert noch")]:
        if pfad.exists():
            probleme.append(name)
    for pfad in [root / "reader", root / "rohdaten" / "Inbox", root / "rohdaten" / "Lektor", root / "tools" / "pipeline",
                 root / "hilfsdaten"]:
        if not pfad.is_dir():
            probleme.append(f"fehlt: {pfad.relative_to(root)}")
    reader = root / "reader"
    buecher = [b for a in sorted(reader.iterdir()) if a.is_dir() and a.name != "export-epistopheles" for b in sorted(a.iterdir())
               if (b / "quelle").is_dir()] if reader.is_dir() else []
    if not buecher:
        probleme.append("reader\\ enthaelt keine Buecher (quelle\\)")
    for b in buecher:
        if (b / "en").exists():
            probleme.append(f"en\\ liegt noch im Buchordner: {b.relative_to(root)}")
    return probleme


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("schritt", choices=["vorher", "nachher", "pruefen"])
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="Bibliothekswurzel")
    ap.add_argument("--ausfuehren", action="store_true", help="wirklich verschieben/kopieren (ohne: nur Plan anzeigen)")
    ap.add_argument("--trotz-aenderungen", action="store_true", help="vorher: auch bei uncommitteten getrackten Aenderungen")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    root = Path(args.root)

    if args.schritt == "pruefen":
        probleme = pruefen(root)
        print("OK: Struktur stimmt." if not probleme else "Beanstandungen:\n  - " + "\n  - ".join(probleme))
        return 0 if not probleme else 1

    if args.schritt == "vorher":
        if not git_sauber(root) and not args.trotz_aenderungen:
            print("Abbruch: getrackte Dateien haben uncommittete Aenderungen. Erst committen oder stashen "
                  "(der Merge in Schritt 3 wuerde sonst scheitern), oder --trotz-aenderungen.")
            return 3
        aktionen = plan_vorher(root)
    else:
        if not (root / "reader").is_dir():
            print("Abbruch: reader\\ fehlt. Erst den Branch mergen (git merge worktree-datenstruktur).")
            return 3
        aktionen = plan_nachher(root)

    if not aktionen:
        print("Nichts zu tun.")
        return 0
    for a in aktionen:
        print(f"{a.art:10} {a.quelle}  ->  {a.ziel}   ({a.beschreibung})")
    if not args.ausfuehren:
        print("\nDry-Run: nichts veraendert. Mit --ausfuehren starten.")
        return 0
    ergebnis = Ergebnis()
    for a in aktionen:
        fuehre_aus(a, ergebnis)
    print(f"\nverschoben {ergebnis.verschoben}, kopiert {ergebnis.kopiert}, zusammengefuehrt (identisch) {ergebnis.zusammengefuehrt}, "
          f"Konflikte {len(ergebnis.konflikte)}")
    for src, dst in ergebnis.konflikte:
        print(f"  KONFLIKT (Datei bleibt liegen): {src}  !=  {dst}")
    return 2 if ergebnis.konflikte else 0


if __name__ == "__main__":
    raise SystemExit(main())
