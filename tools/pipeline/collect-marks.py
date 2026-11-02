"""
collect-marks.py  —  ==Hervorhebungen== aus den Chunks einsammeln

Beim Redigieren gesetzte ==Markierungen== sind kommentarlos: sie halten fest,
DASS an einer Stelle etwas zu klaeren ist, nicht WAS. Dieses Skript sammelt sie
mit Fundstelle und Kontext ein, damit die Frage spaeter erschlossen werden kann.

Eingabe : <Buch>\\de\\chunk_*.md   (bzw. --sprache en)
Ausgabe : <Buch>\\notizen\\hervorhebungen.md

Je Markierung werden festgehalten:
  - Chunk-Nummer und Original-Seitenzahl (aus den page_NN-Ankern im Text)
  - der markierte Text
  - der umgebende Absatz als Kontext
  - Verweis auf dieselbe Stelle in der anderen Sprachfassung

Die Antworten kommen in die Begleitdatei, nie in die Quelle — Rohquellen
bleiben unantastbar.

Grenze der Syntax: Pandoc erkennt ==...== ueber Zeilenumbrueche hinweg, aber
nicht ueber Absatzgrenzen. Mehrere Absaetze deshalb einzeln markieren; dieses
Skript fasst unmittelbar aufeinanderfolgende Markierungen wieder zusammen.

Verwendung:
  python collect-marks.py "Field, G. Lowell\\Elitism (Routledge Revivals)"
  python collect-marks.py --alle
  python collect-marks.py "<Buch>" --suggest      # Frage vom Modell vorschlagen
  python collect-marks.py "<Buch>" --dry-run
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import kapitel_lookup

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests

BASE   = Path(os.environ.get("EBOOK_BASE", Path(__file__).resolve().parents[2] / "rohdaten"))
LEKTOR = BASE / "Lektor"
OLLAMA = "http://localhost:11434"
MODELL = "qwen3.8:27b"

MARK   = re.compile(r'==(.+?)==', re.S)      # ueber Zeilenumbrueche, nicht ueber Absaetze
SEITE  = re.compile(r'page_(\d+)')
KONTEXT_MAX = 700


PROMPT = """Beim Redigieren eines Sachbuchs wurde eine Textstelle markiert, ohne zu
notieren, warum. Erschließe die wahrscheinliche Absicht.

Wähle GENAU EINE Kategorie:
begriff   = ein zentraler oder unklarer Fachbegriff
behauptung= eine starke oder strittige Aussage, die Prüfung verlangt
fakt      = Name, Ereignis, Zahl oder Datum, das Einordnung braucht
verweis   = Bezug auf ein anderes Werk, einen anderen Autor
sprache   = Formulierung wirkt unklar oder nach Übersetzungsfehler

Antworte in genau zwei Zeilen:
kategorie: <eine der fünf>
frage: <eine konkrete Frage in einem Satz, die man dem Text stellen würde>

Keine Erklärungen.

Markierte Stelle:
{marke}

Umgebender Absatz:
{kontext}"""


def seitenzahl(text: str, pos: int) -> str:
    """Letzte page_NN-Marke vor der Fundstelle — das ist die Originalseite."""
    treffer = [m.group(1) for m in SEITE.finditer(text, 0, pos)]
    return treffer[-1] if treffer else ""


def absatz_um(text: str, start: int, ende: int) -> str:
    """Umgebender Absatz, auf KONTEXT_MAX Zeichen begrenzt."""
    a = text.rfind("\n\n", 0, start)
    b = text.find("\n\n", ende)
    a = 0 if a < 0 else a + 2
    b = len(text) if b < 0 else b
    roh = text[a:b].strip()
    roh = re.sub(r'^:::+.*$', '', roh, flags=re.M)          # Div-Marker
    roh = re.sub(r'\[\]\{#[^}]*\}', '', roh)                # Anker
    roh = re.sub(r'\s+', ' ', roh).strip()
    if len(roh) > KONTEXT_MAX:
        roh = roh[:KONTEXT_MAX].rsplit(" ", 1)[0] + " …"
    return roh


def saeubere(s: str) -> str:
    s = re.sub(r'\[\]\{#[^}]*\}', '', s)
    s = re.sub(r'\{[^}]*\}', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def am_rand(text: str, pos: int, vorwaerts: bool) -> bool:
    """
    Steht zwischen dieser Stelle und der Absatzgrenze nur noch Leerraum
    (bzw. ein Pandoc-Div-Marker)? Dann ist die Markierung dort abgeschnitten.
    """
    if vorwaerts:
        rest = text[pos:text.find("\n\n", pos) if "\n\n" in text[pos:] else len(text)]
    else:
        start = text.rfind("\n\n", 0, pos)
        rest = text[0 if start < 0 else start + 2:pos]
    rest = re.sub(r'(?m)^:::+.*$', '', rest)
    return not rest.strip(" \t\r\n.,;:")


def sammle(buch: Path, lang: str) -> list[dict]:
    """Alle Markierungen eines Buchs, in Lesereihenfolge."""
    d = buch / lang
    if not d.is_dir():
        return []
    struktur = kapitel_lookup.lade(buch)
    funde = []
    for f in sorted(d.glob("chunk_*.md")):
        if f.name.endswith(".tagged.md"):
            continue
        text = f.read_text(encoding='utf-8', errors='replace')
        nr = re.search(r'chunk_(\d+)', f.name)
        for m in MARK.finditer(text):
            marke = saeubere(m.group(1))
            if not marke:
                continue
            chunk_nr = int(nr.group(1)) if nr else -1
            kap = kapitel_lookup.bestimme(struktur, chunk_nr, m.start())
            funde.append({
                "chunk": chunk_nr,
                "datei": f.name,
                "seite": seitenzahl(text, m.start()),
                "kapitel": kapitel_lookup.bezeichnung(kap),
                "marke": marke,
                "kontext": absatz_um(text, m.start(), m.end()),
                "pos": m.start(),
                # Nur Markierungen, die eine Absatzgrenze streifen, gehoeren
                # moeglicherweise zusammen — reine Naehe genuegt nicht.
                "am_absatzende": am_rand(text, m.end(), vorwaerts=True),
                "am_absatzanfang": am_rand(text, m.start(), vorwaerts=False),
            })
    return funde


def fasse_zusammen(funde: list[dict]) -> list[dict]:
    """
    Markierungen, die im selben Chunk unmittelbar aufeinanderfolgen, gehoeren
    inhaltlich zusammen — die Absatzgrenze hat sie nur getrennt.
    """
    if not funde:
        return []
    ergebnis = [funde[0]]
    for f in funde[1:]:
        vor = ergebnis[-1]
        # Zusammengehoerig nur, wenn die erste Markierung am Absatzende
        # abbricht und die naechste am Absatzanfang wieder aufsetzt.
        nah = (f["chunk"] == vor["chunk"]
               and vor.get("am_absatzende")
               and f.get("am_absatzanfang")
               and f["pos"] - vor["pos"] < 1200)
        if nah:
            vor["marke"] += " […] " + f["marke"]
            vor["fortsetzung"] = vor.get("fortsetzung", 1) + 1
        else:
            ergebnis.append(f)
    return ergebnis


def frage_modell(marke: str, kontext: str, modell: str, ollama: str) -> tuple[str, str]:
    """Kategorie und Frage vorschlagen. Fehler sind nicht fatal."""
    try:
        r = requests.post(f"{ollama}/api/generate", json={
            "model": modell,
            "prompt": PROMPT.format(marke=marke, kontext=kontext),
            "stream": False,
            "options": {"temperature": 0.0, "num_ctx": 8192},
        }, timeout=180)
        r.raise_for_status()
        a = re.sub(r'<think>.*?</think>', '', r.json().get("response", ""),
                   flags=re.S | re.I)
        kat = re.search(r'kategorie:\s*(\w+)', a, re.I)
        frg = re.search(r'frage:\s*(.+)', a, re.I)
        return (kat.group(1).lower() if kat else "",
                frg.group(1).strip() if frg else "")
    except Exception as e:
        print(f"    [Modell: {str(e)[:60]}]")
        return "", ""


def schreibe(buch: Path, lang: str, funde: list[dict], meta: dict) -> Path:
    andere = "en" if lang == "de" else "de"
    zeilen = [
        "---",
        f'buch: "{meta.get("titel_voll") or meta.get("titel", buch.name)}"',
        f'autor: "{meta.get("autor_voll") or meta.get("autor", buch.parent.name)}"',
        f'sprache: "{lang}"',
        f"markierungen: {len(funde)}",
        f'erstellt: "{time.strftime("%Y-%m-%d %H:%M:%S")}"',
        "---",
        "",
        f"# Hervorhebungen — {buch.name}",
        "",
        "Beim Redigieren markierte Stellen. Die Frage ist erschlossen, nicht",
        "notiert — sie kann danebenliegen. Antworten hier eintragen, nicht in",
        "die Quelle.",
        "",
    ]
    for i, f in enumerate(funde, 1):
        teile = []
        if f.get("kapitel"):
            teile.append(f["kapitel"])
        teile.append(f"chunk_{f['chunk']:03d}")
        if f["seite"]:
            teile.append(f"S. {f['seite']}")
        if f.get("fortsetzung"):
            teile.append(f"{f['fortsetzung']} Absätze")
        ort = " · ".join(teile)
        zeilen += [
            f"## {i}. {ort}",
            "",
            f"> {f['marke']}",
            "",
        ]
        if f.get("kategorie"):
            zeilen.append(f"**Kategorie:** {f['kategorie']}")
        zeilen += [
            f"**Frage:** {f.get('frage') or '_(offen)_'}",
            "",
            f"**Kontext:** {f['kontext']}",
            "",
            f"**Original:** `{andere}/{f['datei']}`",
            "",
            "**Antwort:**",
            "",
            "---",
            "",
        ]
    ziel = buch / "notizen" / "hervorhebungen.md"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text("\n".join(zeilen), encoding='utf-8')
    return ziel


def lade_meta(buch: Path) -> dict:
    f = buch / "meta.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}


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
            if buch.is_dir() and (buch / "de").is_dir():
                treffer.append(buch)
    return treffer


def main():
    ap = argparse.ArgumentParser(
        description="==Hervorhebungen== einsammeln und als Begleitdatei ablegen"
    )
    ap.add_argument("buch", nargs="?", default=None,
                    help="Buchordner ('<Autor>\\<Titel>' oder Pfad)")
    ap.add_argument("--alle", action="store_true", help="alle Buecher durchgehen")
    ap.add_argument("--sprache", default="de", choices=["de", "en"])
    ap.add_argument("--suggest", action="store_true",
                    help="Kategorie und Frage vom Modell vorschlagen lassen")
    ap.add_argument("--model", default=MODELL)
    ap.add_argument("--ollama-url", default=OLLAMA)
    ap.add_argument("--dry-run", action="store_true", help="nur zaehlen")
    args = ap.parse_args()

    if not args.buch and not args.alle:
        raise SystemExit("[FEHLER] Buch angeben oder --alle verwenden.")

    buecher = finde_buecher(None if args.alle else args.buch)
    print("=" * 62)
    print(f"Hervorhebungen einsammeln{' (DRY-RUN)' if args.dry_run else ''} "
          f"| Sprache: {args.sprache}")
    print("=" * 62)

    gesamt = 0
    for buch in buecher:
        roh = sammle(buch, args.sprache)
        funde = fasse_zusammen(roh)
        if not funde:
            if not args.alle:
                print(f"\n{buch.name}: keine Markierungen gefunden.")
            continue

        print(f"\n{buch.parent.name}\\{buch.name}")
        print(f"  Markierungen: {len(roh)}"
              + (f" → {len(funde)} nach Zusammenfassung" if len(funde) != len(roh) else ""))
        gesamt += len(funde)

        if args.suggest and not args.dry_run:
            for n, f in enumerate(funde, 1):
                kat, frage = frage_modell(f["marke"], f["kontext"],
                                          args.model, args.ollama_url)
                f["kategorie"], f["frage"] = kat, frage
                print(f"    [{n}/{len(funde)}] {kat or '?'}")

        if not args.dry_run:
            ziel = schreibe(buch, args.sprache, funde, lade_meta(buch))
            print(f"  -> {ziel}")

    print(f"\n{gesamt} Markierungen insgesamt.")
    if args.dry_run:
        print("(DRY-RUN — nichts geschrieben.)")


if __name__ == "__main__":
    main()
