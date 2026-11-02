"""
collect-tags.py  —  %%Tags%% einsammeln und zur Arbeitsgrundlage buendeln

Gegenstueck zu suggest-tags.py: sammelt die beim Korrekturlesen bestaetigten
Tags samt zugehoerigem Absatz ein und gruppiert sie nach Funktion.

Eingabe : <Buch>\\de\\chunk_*.md   (bzw. --sprache en)
Ausgabe : <Buch>\\notizen\\tags.md          nach Tag gruppiert, mit Fundstelle
          <Buch>\\notizen\\tags.json        maschinenlesbar (fuer Karton-Bau)
          <Buch>\\notizen\\_Zusammenfassung_Entwurf.md   mit --zusammenfassung

Je Eintrag werden festgehalten:
  - Tag und Stichwort
  - Chunk-Nummer und Original-Seitenzahl (aus den page_NN-Ankern)
  - der vollstaendige Absatz — er ist der Beleg, nicht eine Paraphrase

Der Entwurf folgt dem Format aus Abschnitt 4 der Buecherkarton-Spec
(Kernthesen, Gegenpositionen, Tags im Frontmatter). Er ist Rohmaterial fuer
den Dialog, keine fertige Zusammenfassung.

Verwendung:
  python collect-tags.py "Field, G. Lowell\\Elitism (Routledge Revivals)"
  python collect-tags.py --alle
  python collect-tags.py "<Buch>" --zusammenfassung
  python collect-tags.py "<Buch>" --dry-run
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import kapitel_lookup

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE   = Path(os.environ.get("EBOOK_BASE", Path(__file__).resolve().parents[2] / "rohdaten"))
LEKTOR = BASE / "Lektor"

TAGS = ("these", "beleg", "gegen", "def", "kern", "frag")
TAG_ZEILE = re.compile(r'^%%(' + "|".join(TAGS) + r')(?:\s+([^%]*))?%%\s*$')
SEITE = re.compile(r'page_(\d+)')

# Ein einzelner Absatz ist kein Strang — darunter lohnt keine eigene Datei.
MIN_STRANG = 2

UEBERSCHRIFT = {
    "these": "Kernthesen",
    "beleg": "Belege",
    "gegen": "Gegenpositionen",
    "def":   "Begriffe",
    "kern":  "Schlüsselstellen",
    "frag":  "Offene Fragen",
}


def seitenzahl(text: str, pos: int, block: str = "") -> str:
    """
    Originalseite der Fundstelle.

    Steht ein page_NN-Anker im Absatz selbst, gilt dessen Seite — der
    Seitenwechsel faellt dann in diesen Absatz. Sonst die letzte Marke davor.
    """
    im_block = SEITE.search(block)
    if im_block:
        return im_block.group(1)
    treffer = [m.group(1) for m in SEITE.finditer(text, 0, pos)]
    return treffer[-1] if treffer else ""


def saeubere(s: str) -> str:
    """Div-Marker, Anker und Attribut-Suffixe entfernen, Zeilen zusammenziehen."""
    s = re.sub(r'(?m)^:::+.*$', '', s)
    s = re.sub(r'\[\]\{#[^}]*\}', '', s)
    s = re.sub(r'(?<=\))\{[^}]*\}', '', s)
    s = re.sub(r'\{\.[^}]*\}', '', s)
    return re.sub(r'[ \t]*\n[ \t]*', ' ', s).strip()


def block_nach(zeilen: list[str], i: int) -> tuple[str, int]:
    """
    Text des Blocks, der auf die Tag-Zeile(n) folgt.
    Beruecksichtigt Pandoc-Divs (::: para ... :::) und einfache Absaetze.
    Liefert (Text, Index der ersten Zeile nach dem Block).
    """
    # weitere Tag-Zeilen und Leerzeilen ueberspringen
    while i < len(zeilen) and (not zeilen[i].strip() or TAG_ZEILE.match(zeilen[i].strip())):
        i += 1
    if i >= len(zeilen):
        return "", i

    if re.match(r'^:::+\s*\S', zeilen[i]):          # Div-Beginn
        i += 1
        inhalt = []
        while i < len(zeilen) and not re.match(r'^:::+\s*$', zeilen[i]):
            inhalt.append(zeilen[i])
            i += 1
        return "\n".join(inhalt), i + 1

    inhalt = []
    while i < len(zeilen) and zeilen[i].strip():
        inhalt.append(zeilen[i])
        i += 1
    return "\n".join(inhalt), i


def lade_synonyme(buch: Path) -> dict[str, str]:
    """
    Optionale Zusammenfuehrung von Stichwort-Varianten.
    Format: {"peripherie-entwicklung": "peripherie-mechanismus", ...}
    Von Hand gepflegt — deterministisch und nachvollziehbar.
    """
    f = buch / "synonyme.json"
    if not f.exists():
        return {}
    try:
        return {k.lower(): v.lower()
                for k, v in json.loads(f.read_text(encoding='utf-8')).items()}
    except Exception as e:
        print(f"  [!] synonyme.json unlesbar: {e}")
        return {}


def sammle(buch: Path, lang: str, tagged: bool = False) -> list[dict]:
    """Alle getaggten Absaetze eines Buchs, in Lesereihenfolge."""
    d = buch / lang
    if not d.is_dir():
        return []
    synonyme = lade_synonyme(buch)
    struktur = kapitel_lookup.lade(buch)
    funde = []
    muster = "chunk_*.tagged.md" if tagged else "chunk_*.md"
    for f in sorted(d.glob(muster)):
        if not tagged and f.name.endswith(".tagged.md"):
            continue
        text = f.read_text(encoding='utf-8', errors='replace')
        if "%%" not in text:
            continue
        zeilen = text.splitlines()
        nr = re.search(r'chunk_(\d+)', f.name)
        chunk = int(nr.group(1)) if nr else -1

        i = 0
        while i < len(zeilen):
            m = TAG_ZEILE.match(zeilen[i].strip())
            if not m:
                i += 1
                continue
            # mehrere Tags koennen uebereinander stehen
            marken = []
            while i < len(zeilen):
                mm = TAG_ZEILE.match(zeilen[i].strip())
                if not mm:
                    break
                marken.append((mm.group(1), (mm.group(2) or "").strip()))
                i += 1

            roh, i = block_nach(zeilen, i)
            absatz = saeubere(roh)
            if not absatz:
                continue
            pos = text.find(roh[:60]) if roh[:60] else 0
            kap = kapitel_lookup.bestimme(struktur, chunk, max(pos, 0))
            for tag, stichwort in marken:
                s = stichwort.lower()
                funde.append({
                    "tag": tag,
                    "stichwort": synonyme.get(s, s),
                    "stichwort_roh": stichwort,
                    "chunk": chunk,
                    "datei": f.name,
                    "seite": seitenzahl(text, max(pos, 0), roh),
                    "kapitel": kapitel_lookup.bezeichnung(kap),
                    "kapitel_nr": (kap or {}).get("nr", ""),
                    "absatz": absatz,
                })
    return funde


def fundstelle(e: dict, mit_kapitel: bool = True) -> str:
    """Einheitliche Ortsangabe: Kapitel · Chunk · Seite."""
    teile = []
    if mit_kapitel and e.get("kapitel"):
        teile.append(e["kapitel"])
    teile.append(f"chunk_{e['chunk']:03d}")
    if e.get("seite"):
        teile.append(f"S. {e['seite']}")
    return " · ".join(teile)


def lade_meta(buch: Path) -> dict:
    f = buch / "meta.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}


def schreibe_sammlung(buch: Path, lang: str, funde: list[dict], meta: dict) -> Path:
    """Vollstaendige Sammlung, nach Tag gruppiert — die Arbeitsgrundlage."""
    nach_tag = defaultdict(list)
    for f in funde:
        nach_tag[f["tag"]].append(f)

    zeilen = [
        "---",
        f'buch: "{meta.get("titel_voll") or meta.get("titel", buch.name)}"',
        f'autor: "{meta.get("autor_voll") or meta.get("autor", buch.parent.name)}"',
        f'sprache: "{lang}"',
        f"eintraege: {len(funde)}",
        f'erstellt: "{time.strftime("%Y-%m-%d %H:%M:%S")}"',
        "---",
        "",
        f"# Getaggte Stellen — {buch.name}",
        "",
        "Beim Korrekturlesen bestätigte Markierungen. Der Absatz steht",
        "vollständig hier: er ist der Beleg, nicht eine Paraphrase.",
        "",
    ]
    for tag in TAGS:
        eintraege = nach_tag.get(tag)
        if not eintraege:
            continue
        zeilen += [f"## {UEBERSCHRIFT[tag]} ({len(eintraege)})", ""]
        for e in eintraege:
            kopf = f"**{e['stichwort']}**" if e["stichwort"] else "**(ohne Stichwort)**"
            zeilen += [f"### {kopf} — {fundstelle(e)}", "", e["absatz"], ""]
    ziel = buch / "notizen" / "tags.md"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text("\n".join(zeilen), encoding='utf-8')
    return ziel


def schreibe_entwurf(buch: Path, lang: str, funde: list[dict], meta: dict) -> Path:
    """
    Entwurf im Karton-Format (Spec Abschnitt 4). Bewusst knapp: er nennt die
    Fundstellen, formuliert aber nichts aus — das geschieht im Dialog.
    """
    nach_tag = defaultdict(list)
    for f in funde:
        nach_tag[f["tag"]].append(f)

    stichworte = [s for s, _ in Counter(
        f["stichwort"] for f in funde if f["stichwort"]).most_common(12)]

    autor = meta.get("autor_voll") or meta.get("autor", buch.parent.name)
    werk  = meta.get("titel_voll") or meta.get("titel", buch.name)

    zeilen = [
        "---",
        "tags: [" + ", ".join(stichworte) + "]",
        f"autor: {autor}",
        f"werk: {werk}",
    ]
    if meta.get("jahr"):
        zeilen.append(f"jahr: {meta['jahr']}")
    zeilen += ["status: entwurf", "---", "",
               f"# {werk}", "",
               "> Entwurf aus den getaggten Stellen. Die Thesen sind noch nicht",
               "> formuliert — hier stehen die Fundstellen, aus denen sie entstehen.",
               ""]

    zeilen += ["## Kernthesen", ""]
    for i, e in enumerate(nach_tag.get("these", []), 1):
        kurz = e["absatz"][:200].rsplit(" ", 1)[0] + " …" if len(e["absatz"]) > 200 else e["absatz"]
        zeilen += [f"{i}. **{e['stichwort'] or 'ohne Stichwort'}** ({fundstelle(e)})",
                   f"   > {kurz}", ""]
    if not nach_tag.get("these"):
        zeilen += ["_(keine these-Tags gesetzt)_", ""]

    zeilen += ["## Gegenpositionen", ""]
    for e in nach_tag.get("gegen", []):
        zeilen += [f"- **{e['stichwort'] or 'ohne Stichwort'}** ({fundstelle(e)})", ""]
    if not nach_tag.get("gegen"):
        zeilen += ["_(keine gegen-Tags gesetzt — Kontroversen entstehen im Cluster)_", ""]

    if nach_tag.get("def"):
        zeilen += ["## Begriffe", ""]
        for e in nach_tag["def"]:
            zeilen.append(f"- **{e['stichwort'] or 'ohne Stichwort'}** ({fundstelle(e)})")
        zeilen.append("")

    if nach_tag.get("frag"):
        zeilen += ["## Zu prüfen", ""]
        for e in nach_tag["frag"]:
            zeilen.append(f"- {e['stichwort'] or 'ohne Stichwort'} ({fundstelle(e)})")
        zeilen.append("")

    zeilen += ["---", "", f"Belege vollständig in `notizen/tags.md`."]
    ziel = buch / "notizen" / "_Zusammenfassung_Entwurf.md"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text("\n".join(zeilen), encoding='utf-8')
    return ziel


def schreibe_register(buch: Path, funde: list[dict]) -> tuple[Path, Counter]:
    """
    Stichwort-Register mit Haeufigkeit — Grundlage fuer das Zusammenfuehren
    von Varianten. Der Durchgang hier ist der wichtigste Schritt vor der
    Verdichtung: zerfaserte Stichworte ergeben zerfaserte Straenge.
    """
    haeufig = Counter(f["stichwort"] for f in funde if f["stichwort"])
    ohne = sum(1 for f in funde if not f["stichwort"])

    # Verdachtsfaelle: gleicher erster Wortteil, aber verschiedene Stichworte
    nach_stamm = defaultdict(list)
    for s in haeufig:
        nach_stamm[s.split("-")[0]].append(s)
    varianten = {k: v for k, v in nach_stamm.items() if len(v) > 1}

    zeilen = [
        f"# Stichwort-Register — {buch.name}", "",
        f"{len(haeufig)} Stichworte, {sum(haeufig.values())} Zuordnungen"
        + (f", {ohne} Tags ohne Stichwort" if ohne else ""), "",
        f"Stränge ab {MIN_STRANG} Belegstellen: "
        f"{sum(1 for n in haeufig.values() if n >= MIN_STRANG)}", "",
    ]
    if varianten:
        zeilen += ["## Mögliche Varianten", "",
                   "Gleicher Wortstamm, verschiedene Stichworte — hier lohnt der Blick.",
                   "Zusammenführen über `synonyme.json` im Buchordner.", ""]
        for stamm, liste in sorted(varianten.items()):
            teile = ", ".join(f"`{s}` ({haeufig[s]})" for s in sorted(liste))
            zeilen.append(f"- **{stamm}**: {teile}")
        zeilen.append("")

    zeilen += ["## Alle Stichworte", "", "| Stichwort | Stellen | Tags |", "|---|---|---|"]
    for s, n in haeufig.most_common():
        tags = ", ".join(sorted({f["tag"] for f in funde if f["stichwort"] == s}))
        zeilen.append(f"| `{s}` | {n} | {tags} |")

    ziel = buch / "notizen" / "stichworte.md"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text("\n".join(zeilen), encoding='utf-8')
    return ziel, haeufig


def schreibe_straenge(buch: Path, funde: list[dict], meta: dict) -> tuple[int, int]:
    """
    Je Stichwort mit genug Belegstellen eine Strang-Datei — chunkuebergreifend,
    in Lesereihenfolge. Liefert (geschrieben, uebersprungen).
    """
    nach_stichwort = defaultdict(list)
    for f in funde:
        if f["stichwort"]:
            nach_stichwort[f["stichwort"]].append(f)

    d = buch / "notizen" / "straenge"
    d.mkdir(parents=True, exist_ok=True)
    geschrieben = klein = 0

    for stichwort, eintraege in sorted(nach_stichwort.items()):
        if len(eintraege) < MIN_STRANG:
            klein += 1
            continue
        eintraege.sort(key=lambda e: (e["chunk"], e["tag"]))
        tags = sorted({e["tag"] for e in eintraege})
        kapitel = sorted({e["kapitel"] for e in eintraege if e.get("kapitel")})
        zeilen = [
            "---",
            f"strang: {stichwort}",
            f'buch: "{meta.get("titel_voll") or meta.get("titel", buch.name)}"',
            f'autor: "{meta.get("autor_voll") or meta.get("autor", buch.parent.name)}"',
            f"belegstellen: {len(eintraege)}",
            "tags: [" + ", ".join(tags) + "]",
            "kapitel: [" + ", ".join(f'"{k}"' for k in kapitel) + "]",
            "status: unverdichtet",
            "---",
            "",
            f"# {stichwort}",
            "",
            "> Noch nicht verdichtet — hier stehen die Belegstellen in",
            "> Lesereihenfolge, wörtlich aus der Quelle.",
            "",
            "## Verlauf",
            "",
        ]
        for e in eintraege:
            zeilen.append(f"- **{e['tag']}** ({fundstelle(e)})")
        zeilen += ["", "## Belegstellen", ""]
        for e in eintraege:
            zeilen += [f"### {e['tag']} — {fundstelle(e)}", "", e["absatz"], ""]

        name = re.sub(r'[<>:"/\\|?*]', '_', stichwort)[:60]
        (d / f"{name}.md").write_text("\n".join(zeilen), encoding='utf-8')
        geschrieben += 1
    return geschrieben, klein


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
        description="%%Tags%% einsammeln, nach Funktion gruppieren, Entwurf erzeugen"
    )
    ap.add_argument("buch", nargs="?", default=None,
                    help="Buchordner ('<Autor>\\<Titel>' oder Pfad)")
    ap.add_argument("--alle", action="store_true", help="alle Buecher durchgehen")
    ap.add_argument("--sprache", default="de", choices=["de", "en"])
    ap.add_argument("--zusammenfassung", action="store_true",
                    help="zusaetzlich einen Entwurf im Karton-Format schreiben")
    ap.add_argument("--register", action="store_true",
                    help="Stichwort-Register schreiben (Varianten sichtbar machen)")
    ap.add_argument("--straenge", action="store_true",
                    help="je Stichwort eine chunkuebergreifende Strang-Datei")
    ap.add_argument("--tagged", action="store_true",
                    help="chunk_*.tagged.md lesen statt der Originale")
    ap.add_argument("--dry-run", action="store_true", help="nur zaehlen")
    args = ap.parse_args()

    if not args.buch and not args.alle:
        raise SystemExit("[FEHLER] Buch angeben oder --alle verwenden.")

    buecher = finde_buecher(None if args.alle else args.buch)
    print("=" * 62)
    print(f"Tags einsammeln{' (DRY-RUN)' if args.dry_run else ''} | Sprache: {args.sprache}")
    print("=" * 62)

    gesamt = Counter()
    for buch in buecher:
        funde = sammle(buch, args.sprache, args.tagged)
        if not funde:
            if not args.alle:
                print(f"\n{buch.name}: keine Tags gefunden.")
            continue

        verteilung = Counter(f["tag"] for f in funde)
        gesamt.update(verteilung)
        ohne_stichwort = sum(1 for f in funde if not f["stichwort"])

        print(f"\n{buch.parent.name}\\{buch.name}")
        print("  " + ", ".join(f"{t}={verteilung[t]}" for t in TAGS if verteilung[t]))
        print(f"  Einträge: {len(funde)}"
              + (f", davon {ohne_stichwort} ohne Stichwort" if ohne_stichwort else ""))

        if args.dry_run:
            continue
        meta = lade_meta(buch)
        print(f"  -> {schreibe_sammlung(buch, args.sprache, funde, meta)}")
        (buch / "notizen" / "tags.json").write_text(
            json.dumps(funde, ensure_ascii=False, indent=2), encoding='utf-8')
        if args.zusammenfassung:
            print(f"  -> {schreibe_entwurf(buch, args.sprache, funde, meta)}")
        if args.register:
            ziel, haeufig = schreibe_register(buch, funde)
            straenge = sum(1 for n in haeufig.values() if n >= MIN_STRANG)
            print(f"  Stichworte: {len(haeufig)}, davon {straenge} mit "
                  f"≥{MIN_STRANG} Stellen")
            print(f"  -> {ziel}")
        if args.straenge:
            n, klein = schreibe_straenge(buch, funde, meta)
            print(f"  Stränge: {n} geschrieben"
                  + (f", {klein} Einzelfunde übersprungen" if klein else ""))

    if gesamt:
        print(f"\nInsgesamt: " + ", ".join(f"{t}={gesamt[t]}" for t in TAGS if gesamt[t]))
    else:
        print("\nKeine Tags gefunden.")
    if args.dry_run:
        print("(DRY-RUN — nichts geschrieben.)")


if __name__ == "__main__":
    main()
