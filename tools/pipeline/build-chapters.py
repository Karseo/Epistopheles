"""
build-chapters.py  —  Chunks zu kapitelbasierten Markdown-Dateien verarbeiten

ebook-build.py fuegt ein Buch zu EINEM Gesamttext zusammen (Schritt 3). Fuer
manche Zwecke — ein Kapitel gezielt einer KI vorlegen, eines allein lesen,
eines an jemanden schicken — ist das zu grob. Dieses Skript schneidet
stattdessen an den von detect-chapters.py gefundenen Kapitelgrenzen
(kapitel.json) und schreibt je Segment (Kapitel wie Titelei/Anhang) eine
eigene Datei.

Vorbedingung: detect-chapters.py muss fuer das Buch bereits gelaufen sein.

Geschnitten wird am RAW-Text jedes Chunks, an der in kapitel.json
gespeicherten Zeichenposition — nicht an der Chunkgrenze (die liegt
mechanisch bei 8000 Zeichen und faellt oft mitten in ein Kapitel). Erst nach
dem Schneiden laeuft je Segment normalize_footnotes()/--clean aus
ebook-build.py — vorher wuerden sich die gespeicherten Positionen verschieben.

Fussnoten und Querverweise:
  - Referenzen im InDesign-Muster werden wie in ebook-build.py zu [^Kap-Nr]
    gekuerzt. Existiert <lang>\\footnotes.md (extract-footnotes.py), werden
    die im jeweiligen Segment tatsaechlich referenzierten Definitionen als
    eigener Abschnitt "## Fussnoten" ans Ende der Kapiteldatei gehaengt —
    nicht alle auf einmal, sondern nur die, die im Segment auch vorkommen.
  - Bei Verlagen, die Fussnotentexte als eigene Absaetze im Fliesstext lassen
    (kein footnotes.md noetig), bleiben sie automatisch im richtigen Segment:
    sie stehen im Quelltext vor der naechsten Kapitelueberschrift und werden
    darum mit dem vorigen Kapitel geschnitten, nicht mit dem naechsten.
  - Interne Links, deren Ziel nach dem Schneiden nicht mehr im selben
    Segment liegt (Verweise auf andere Kapitel), werden zu reinem Text —
    ein Link ins Leere ist schlimmer als gar keiner. Ist das Zielkapitel
    ermittelbar, wird es in Klammern vermerkt.

Ausgabe: <Buch>\\Kapitel\\<lang>\\NN - Titel.md

Verwendung:
  python build-chapters.py "Parvini, Neema\\The Prophets of Doom"
  python build-chapters.py "<Autor>\\<Titel>" --sprache de
  python build-chapters.py "<Autor>\\<Titel>" --clean
  python build-chapters.py --alle
"""

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE   = Path(os.environ.get("EBOOK_BASE", Path(__file__).resolve().parents[2] / "rohdaten"))
LEKTOR = BASE / "Lektor"
LANGS  = ("de", "en")


def _lade_build():
    """ebook-build.py als Modul laden — normalize_footnotes()/clean_markdown()
    sollen nur an einer Stelle implementiert sein (s. check-metadata.py)."""
    pfad = Path(__file__).parent / "ebook-build.py"
    spec = importlib.util.spec_from_file_location("ebook_build", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul

_eb = _lade_build()

FN_REF     = re.compile(r'\[\^([^\]]+)\]')
FN_DEF     = re.compile(r'(?m)^\[\^([^\]]+)\]:\s*(.+)$')
LINK       = re.compile(r'\[([^\]\[]{1,300})\]\((#[^)\s]+)\)')
ANKER_ZIEL = re.compile(r'\{#([^}\s]+)')


def finde_buecher(ziel: str | None) -> list[Path]:
    if ziel:
        p = Path(ziel)
        if not p.is_dir():
            p = LEKTOR / ziel
        if not p.is_dir():
            raise SystemExit(f"[FEHLER] Nicht gefunden: {ziel}")
        return [p.resolve()]
    treffer = []
    for autor in sorted(LEKTOR.iterdir()):
        if not autor.is_dir():
            continue
        for buch in sorted(autor.iterdir()):
            if buch.is_dir() and (buch / "kapitel.json").exists():
                treffer.append(buch)
    return treffer


def lade_kapitel(buch: Path) -> dict:
    f = buch / "kapitel.json"
    if not f.exists():
        raise SystemExit(
            f"[FEHLER] {f.name} fehlt fuer {buch.name} — "
            f"zuerst 'python detect-chapters.py \"{buch.parent.name}\\{buch.name}\"'.")
    struktur = json.loads(f.read_text(encoding='utf-8'))
    if not struktur.get("segmente"):
        raise SystemExit(f"[FEHLER] {buch.name}: keine Kapitelgrenzen in kapitel.json.")
    return struktur


def lade_footnotes(buch: Path, lang: str) -> dict[str, str]:
    f = buch / lang / "footnotes.md"
    if not f.exists():
        return {}
    text = f.read_text(encoding='utf-8', errors='replace')
    return {m.group(1): m.group(2).strip() for m in FN_DEF.finditer(text)}


def schneide(d: Path, struktur: dict) -> list[dict]:
    """
    Teilt die Chunks an den Positionen aus kapitel.json['segmente'].
    Liefert die Segmente in Lesereihenfolge, jedes mit seinem Rohtext.
    """
    je_chunk: dict[int, list[dict]] = {}
    for s in struktur["segmente"]:
        je_chunk.setdefault(s["chunk"], []).append(s)
    for lst in je_chunk.values():
        lst.sort(key=lambda s: s["position"])

    dateien = sorted(
        (f for f in d.glob("chunk_*.md") if not f.name.endswith(".tagged.md")),
        key=lambda f: int(re.search(r'chunk_(\d+)', f.name).group(1)))

    ausgabe: list[dict] = []
    aktuelles = {"id": "", "nr": "", "titel": "Vorspann", "vorspann": True, "teile": []}
    for f in dateien:
        c = int(re.search(r'chunk_(\d+)', f.name).group(1))
        text = f.read_text(encoding='utf-8', errors='replace')
        cursor = 0
        for s in je_chunk.get(c, []):
            pos = s["position"]
            aktuelles["teile"].append(text[cursor:pos])
            ausgabe.append(aktuelles)
            aktuelles = {"id": s["id"], "nr": s["nr"], "titel": s["titel"],
                         "vorspann": s["vorspann"], "teile": []}
            cursor = pos
        aktuelles["teile"].append(text[cursor:])
    ausgabe.append(aktuelles)

    for seg in ausgabe:
        seg["text"] = "".join(seg.pop("teile"))
    return ausgabe


def haenge_fussnoten_an(text: str, noten: dict[str, str]) -> tuple[str, list[str]]:
    """Haengt nur die in DIESEM Segment referenzierten Definitionen an."""
    gebraucht, gesehen = [], set()
    for m in FN_REF.finditer(text):
        fid = m.group(1)
        if fid in noten and fid not in gesehen:
            gesehen.add(fid)
            gebraucht.append(fid)
    fehlend = sorted({m.group(1) for m in FN_REF.finditer(text)} - set(noten))
    if not gebraucht:
        return text, fehlend
    block = "\n\n## Fussnoten\n\n" + "\n\n".join(
        f"[^{i}]: {noten[i]}" for i in gebraucht)
    return text.rstrip() + block + "\n", fehlend


def entschaerfe_querverweise(text: str, eigene_id: str,
                              zielkarte: list[tuple[str, str, str, bool]]) -> tuple[str, int]:
    """
    Interne Links, deren Ziel nicht mehr im selben Segment liegt, werden zu
    reinem Text. `zielkarte` bildet Anker-ID-Praefixe auf (nr, titel, vorspann)
    anderer Segmente ab, laengste ID zuerst — damit laesst sich meist sagen,
    in welches Kapitel ein Verweis eigentlich zeigt. Bei Vorspann-Zielen zaehlt
    'nr' nur die TOC-Reihenfolge der Titelei, nicht die Kapitelnummer — dort
    wird darum immer der Titel genannt, nie 'Kapitel N'.
    """
    lokale_ziele = set(ANKER_ZIEL.findall(text))
    entfernt = 0

    def ersetze(m: re.Match) -> str:
        nonlocal entfernt
        sichtbar, ziel = m.group(1), m.group(2)[1:]  # '#' abschneiden
        if ziel in lokale_ziele:
            return m.group(0)
        entfernt += 1
        for praefix, nr, titel, vorspann in zielkarte:
            if ziel.startswith(praefix) and praefix != eigene_id:
                bez = titel if (vorspann or not nr.isdigit()) else f"Kapitel {int(nr)}"
                return f"{sichtbar} (→ {bez})" if bez else sichtbar
        return sichtbar

    return LINK.sub(ersetze, text), entfernt


def dateiname(seq: int, nr: str, titel: str, vorspann: bool) -> str:
    bez = f"{int(nr)}. {titel}" if (nr.isdigit() and not vorspann) else (titel or "Segment")
    bez = re.sub(r'[\\/:*?"<>|]', '_', bez)
    bez = re.sub(r'\s+', ' ', bez).strip(" .")[:80]
    return f"{seq:02d} - {bez}.md"


def schreibe_datei(pfad: Path, text: str, meta: dict, seg: dict, lang: str) -> None:
    fm = [
        "---",
        f'buch: "{_eb.yaml_escape(meta.get("titel_voll") or meta.get("titel", ""))}"',
        f'autor: "{_eb.yaml_escape(meta.get("autor_voll") or meta.get("autor", ""))}"',
        f'kapitel: "{_eb.yaml_escape(seg["titel"])}"',
    ]
    if seg["nr"]:
        fm.append(f'nummer: "{_eb.yaml_escape(seg["nr"])}"')
    fm += [f'vorspann: {"true" if seg["vorspann"] else "false"}',
           f'sprache: "{lang}"', "---", "", ""]
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with open(pfad, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(fm))
        f.write(text.strip("\n"))
        f.write("\n")


def verarbeite(buch: Path, lang: str, clean: bool) -> None:
    d = buch / lang
    if not d.is_dir() or not any(d.glob("chunk_*.md")):
        return
    struktur = lade_kapitel(buch)
    meta = _eb.load_meta(buch)
    noten = lade_footnotes(buch, lang)

    segmente = schneide(d, struktur)
    # Positionsloses "Vorspann" ohne Inhalt (z.B. kein Text vor der ersten
    # Marke) nicht als eigene Datei ausgeben.
    segmente = [s for i, s in enumerate(segmente)
                if not (i == 0 and not s["nr"] and len(s["text"].strip()) < 30)]
    if not segmente:
        print(f"  [{lang}] keine Segmente nach dem Schneiden.")
        return

    # Zielkarte fuer Querverweise: Anker-ID-Praefix -> (Nummer, Titel),
    # laengste ID zuerst, damit z.B. 'part0006.html_split_2' vor 'part0006.html'
    # geprueft wird.
    zielkarte = sorted(
        ((s["id"], s["nr"], s["titel"], s["vorspann"]) for s in segmente if s["id"]),
        key=lambda t: -len(t[0]))

    ziel_dir = buch / "Kapitel" / lang
    fehlende_fn: set[str] = set()
    quer_entfernt = 0
    geschrieben = 0

    for seq, seg in enumerate(segmente):
        text = _eb.normalize_footnotes(seg["text"])
        if clean:
            text = _eb.clean_markdown(text)
        text, entfernt = entschaerfe_querverweise(text, seg["id"], zielkarte)
        quer_entfernt += entfernt
        text, fehlend = haenge_fussnoten_an(text, noten)
        fehlende_fn.update(fehlend)

        if len(text.strip()) < 20:
            continue
        name = dateiname(seq, seg["nr"], seg["titel"], seg["vorspann"])
        schreibe_datei(ziel_dir / name, text, meta, seg, lang)
        geschrieben += 1

    print(f"  [{lang}] {geschrieben} Datei(en) -> {ziel_dir}")
    if quer_entfernt:
        print(f"        {quer_entfernt}x interner Verweis auf ein anderes Kapitel entschaerft")
    if fehlende_fn:
        bsp = ', '.join(sorted(fehlende_fn)[:6])
        mehr = ' …' if len(fehlende_fn) > 6 else ''
        print(f"        {len(fehlende_fn)}x referenzierte Fussnote ohne Definition "
              f"({bsp}{mehr}) — footnotes.md unvollstaendig oder fehlt "
              f"(extract-footnotes.py)")


def main():
    ap = argparse.ArgumentParser(
        description="Chunks an den Kapitelgrenzen aus kapitel.json in einzelne "
                     "Markdown-Dateien schneiden"
    )
    ap.add_argument("buch", nargs="?", default=None)
    ap.add_argument("--alle", action="store_true")
    ap.add_argument("--sprache", default="de", choices=["de", "en", "beide"])
    ap.add_argument("--clean", action="store_true",
                    help="Konvertierungsreste entfernen (wie ebook-build.py --clean)")
    args = ap.parse_args()

    if not args.buch and not args.alle:
        raise SystemExit("[FEHLER] Buch angeben oder --alle verwenden.")

    sprachen = LANGS if args.sprache == "beide" else (args.sprache,)
    buecher = finde_buecher(None if args.alle else args.buch)

    print("=" * 68)
    print(f"Kapitel bauen: {len(buecher)} Buch/Buecher")
    print("=" * 68)

    for buch in buecher:
        if not (buch / "kapitel.json").exists():
            if not args.alle:
                raise SystemExit(
                    f"[FEHLER] kapitel.json fehlt — zuerst "
                    f"'python detect-chapters.py \"{buch.parent.name}\\{buch.name}\"'.")
            continue
        print(f"\n{buch.parent.name}\\{buch.name}")
        try:
            for lang in sprachen:
                verarbeite(buch, lang, args.clean)
        except SystemExit as e:
            # Unter --alle ein einzelnes Buch nicht den ganzen Lauf abbrechen
            # lassen (z.B. veraltete kapitel.json ohne 'segmente' aus einer
            # aelteren detect-chapters.py-Version).
            if not args.alle:
                raise
            print(f"  [uebersprungen] {e}")


if __name__ == "__main__":
    main()
