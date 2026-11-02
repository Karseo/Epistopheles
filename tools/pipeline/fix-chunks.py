"""
fix-chunks.py  —  defekte Chunks finden und zur Neuuebersetzung freigeben

Sucht in allen Buchordnern nach Chunks, die
  - leer oder verdaechtig kurz sind,
  - in der Zielsprache nicht uebersetzt wirken (Sprachprobe),
  - fehlen (Luecke in der Nummerierung).

Mit --repair werden die betroffenen Dateien geloescht und ihre Indizes aus
.progress.json entfernt. Ein anschliessender Lauf von
    ebook-translate.py "<Quelldatei>" --resume
holt genau diese Chunks nach.

Der uebernommene Quelltext (en\\ bei englischer Quelle) wird nicht angetastet —
dort ist fremdsprachiger Text ja korrekt.

Verwendung:
  python fix-chunks.py                       # alle Buecher pruefen
  python fix-chunks.py "Horton, Scott\\Provoked"
  python fix-chunks.py --repair              # defekte Chunks freigeben
  python fix-chunks.py --min-marker 5        # Empfindlichkeit der Sprachprobe
"""

import argparse
import collections
import json
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ebook_pfade import quelle_aufloesen   # noqa: E402  alte Pfade aus meta.json auf BASE umsetzen
BASE   = Path(os.environ.get("EBOOK_BASE", Path(__file__).resolve().parents[2] / "rohdaten"))
LEKTOR = BASE / "Lektor"
LANGS  = ("de", "en")

MARKERS = {
    "en": re.compile(r'\b(the|and|of|that|with|which|would|there|their|about|between)\b', re.I),
    "de": re.compile(r'\b(der|die|das|und|nicht|eine|einen|wurde|werden|sich|auch|wie)\b', re.I),
}


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
            if buch.is_dir() and any((buch / l).glob("chunk_*.md")
                                     for l in LANGS if (buch / l).is_dir()):
                treffer.append(buch)
    return treffer


def lade_meta(buch: Path) -> dict:
    f = buch / "meta.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}


def ist_apparat(text: str) -> str:
    """
    Erkennt Register, Bibliografien und Endnotenapparate.

    In solchen Abschnitten ist unuebersetztes Englisch das richtige Ergebnis:
    Werktitel, Verlagsnamen und Seitenzahlen werden nicht uebersetzt. Ohne
    diese Unterscheidung meldet die Sprachprobe lauter Falschtreffer.
    Liefert die erkannte Art oder "".
    """
    zeilen = [z for z in text.splitlines() if z.strip()]
    if len(zeilen) < 8:
        return ""
    laengen = sorted(len(z) for z in zeilen)
    med = laengen[len(laengen) // 2]
    ziff = sum(c.isdigit() for c in text) / max(len(text), 1)
    jahr = sum(1 for z in zeilen if re.search(r'\b(1[5-9]\d{2}|20\d{2})\b', z)) / len(zeilen)
    lit  = sum(1 for z in zeilen
               if re.match(r'\s*(—|--|[A-ZÄÖÜ][\w\'-]+,\s+[A-ZÄÖÜ])', z)) / len(zeilen)

    if ziff > 0.15 and med < 60:
        return "Register"
    if lit > 0.3 and jahr > 0.3:
        return "Bibliografie"
    if jahr > 0.7 and med > 150:
        return "Endnoten"
    return ""


def teil_unuebersetzt(text: str, lang: str, min_marker: int) -> int:
    """
    Zaehlt Absaetze, die fremdsprachig geblieben sind, waehrend der Rest des
    Chunks uebersetzt wurde.

    Die Gesamtbilanz eines Chunks verdeckt solche Faelle: bleibt ein Viertel
    des Textes stehen, ueberwiegen in der Summe trotzdem die Marker der
    Zielsprache, und eine reine Chunk-Statistik meldet nichts.
    """
    fremd_sprachen = [l for l in MARKERS if l != lang]
    treffer = 0
    for absatz in re.split(r'\n\s*\n', text):
        a = absatz.strip()
        if len(a) < 200:
            continue                      # zu kurz fuer eine sichere Probe
        if ist_apparat(a):
            continue
        # Kursive oder als Zitat markierte Absaetze: fremdsprachige Zitate
        # bleiben im Original stehen — das ist kein Uebersetzungsfehler.
        if a.count("*") > 4 or re.match(r'^\s*([>„"\'«]|\*{1,2}[„"\'«])', a):
            continue
        eigen = len(MARKERS[lang].findall(a))
        fremd = max(len(MARKERS[l].findall(a)) for l in fremd_sprachen)
        if fremd > min_marker and fremd > eigen * 3:
            treffer += 1
    return treffer


def wiederholungsquote(text: str) -> float:
    """
    Anteil mehrfach vorkommender Saetze.

    Bleibt das Modell in einer Schleife haengen, gibt es dieselben Saetze
    wieder und wieder aus. Das ist das verlaesslichere Merkmal als die blosse
    Laenge: es trifft auch Chunks, die dabei nur maessig wachsen.
    """
    saetze = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text)
              if len(s.strip()) > 40]
    if len(saetze) < 10:
        return 0.0
    norm = [re.sub(r'\W+', '', s.lower())[:60] for s in saetze]
    haeufig = collections.Counter(norm)
    mehrfach = sum(v - 1 for v in haeufig.values() if v > 1)
    return mehrfach / len(saetze)


def laengenverhaeltnis(buch: Path, lang: str, idx: int, quellsprache: str) -> float:
    """
    Verhaeltnis Zielfassung zu Quellfassung. Deutlich ueber 1 deutet darauf
    hin, dass das Modell Text hinzuerfunden oder Passagen doppelt ausgegeben
    hat. Ohne Quellfassung 0.
    """
    if not quellsprache or quellsprache == lang:
        return 0.0
    q = buch / quellsprache / f"chunk_{idx:03d}.md"
    z = buch / lang / f"chunk_{idx:03d}.md"
    if not (q.exists() and z.exists()):
        return 0.0
    ql = len(q.read_text(encoding='utf-8', errors='replace'))
    return (len(z.read_text(encoding='utf-8', errors='replace')) / ql) if ql else 0.0


def pruefe(buch: Path, lang: str, quellsprache: str, min_marker: int,
           max_faktor: float = 1.6) -> dict:
    """Liefert defekte Indizes nach Kategorie."""
    d = buch / lang
    befund = {"leer": [], "kurz": [], "unuebersetzt": [], "fehlend": [],
              "apparat": [], "teilweise": [], "aufgeblaeht": [], "schleife": []}
    if not d.is_dir():
        return befund

    # Uebernommener Quelltext wird nicht auf Uebersetzung geprueft
    ist_quelltext = (lang == quellsprache)

    vorhanden = {}
    for f in d.glob("chunk_*.md"):
        m = re.search(r'chunk_(\d+)\.md$', f.name)
        if m:
            vorhanden[int(m.group(1))] = f

    meta   = lade_meta(buch)
    total  = int(meta.get("chunks") or 0) or (max(vorhanden) + 1 if vorhanden else 0)
    befund["fehlend"] = sorted(set(range(total)) - set(vorhanden))

    for idx, f in sorted(vorhanden.items()):
        text = f.read_text(encoding='utf-8', errors='replace').strip()
        if not text:
            befund["leer"].append(idx)
            continue
        if len(text) < 20:
            befund["kurz"].append(idx)
            continue
        if ist_quelltext:
            continue
        eigen = len(MARKERS[lang].findall(text))
        fremd = max(len(MARKERS[l].findall(text)) for l in MARKERS if l != lang)
        if fremd > min_marker and fremd > eigen * 3:
            art = ist_apparat(text)
            if art:
                # Register/Bibliografie/Endnoten bleiben zu Recht unuebersetzt
                befund["apparat"].append((idx, art))
            else:
                befund["unuebersetzt"].append(idx)
            continue

        # Teilweise stehengebliebene Absaetze — von der Chunk-Bilanz verdeckt
        if not ist_apparat(text) and teil_unuebersetzt(text, lang, min_marker):
            befund["teilweise"].append(idx)
            continue

        # Wiederholungsschleife des Modells
        q = wiederholungsquote(text)
        if q > 0.2:
            befund["schleife"].append((idx, q))
            continue

        # Zielfassung deutlich laenger als die Quelle → Text hinzuerfunden
        v = laengenverhaeltnis(buch, lang, idx, quellsprache)
        if v > max_faktor:
            befund["aufgeblaeht"].append((idx, v))
    return befund


def gib_frei(buch: Path, lang: str, indizes: list[int]) -> int:
    """Loescht die Chunk-Dateien und entfernt die Indizes aus .progress.json."""
    d = buch / lang
    geloescht = 0
    for i in indizes:
        f = d / f"chunk_{i:03d}.md"
        if f.exists():
            f.unlink()
            geloescht += 1

    pf = buch / ".progress.json"
    if pf.exists():
        try:
            p = json.loads(pf.read_text(encoding='utf-8'))
            eintrag = p.setdefault("sprachen", {}).setdefault(lang, {"completed": []})
            eintrag["completed"] = [i for i in eintrag.get("completed", [])
                                    if i not in set(indizes)]
            pf.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as e:
            print(f"    [!] .progress.json nicht aktualisiert: {e}")
    return geloescht


def kurz(indizes: list[int], n: int = 12) -> str:
    s = ", ".join(str(i) for i in indizes[:n])
    return s + (f" … (+{len(indizes)-n})" if len(indizes) > n else "")


def main():
    ap = argparse.ArgumentParser(
        description="Defekte Chunks finden und zur Neuuebersetzung freigeben"
    )
    ap.add_argument("buch", nargs="?", default=None)
    ap.add_argument("--repair", action="store_true",
                    help="defekte Chunks loeschen und aus .progress.json austragen")
    ap.add_argument("--min-marker", type=int, default=5,
                    help="Mindestzahl fremdsprachiger Marker (Standard 5)")
    ap.add_argument("--max-faktor", type=float, default=1.6,
                    help="ab welchem Laengenverhaeltnis Ziel/Quelle ein Chunk als "
                         "aufgeblaeht gilt (Standard 1.6)")
    ap.add_argument("--zeige-apparat", action="store_true",
                    help="auch Register/Bibliografien/Endnoten auflisten, die "
                         "zu Recht unuebersetzt sind")
    args = ap.parse_args()

    buecher = finde_buecher(args.buch)
    print("=" * 68)
    print(f"Chunk-Pruefung{' + Reparatur' if args.repair else ''}: {len(buecher)} Buch/Buecher")
    print("=" * 68)

    gesamt = 0
    apparat_gesamt = 0
    resume_befehle = []

    for buch in buecher:
        meta = lade_meta(buch)
        quellsprache = meta.get("quellsprache", "") or meta.get("quelle_uebernommen", "")
        kopf_gezeigt = False

        for lang in LANGS:
            b = pruefe(buch, lang, quellsprache, args.min_marker, args.max_faktor)
            defekt = sorted(set(b["leer"] + b["kurz"] + b["unuebersetzt"]
                                + b["teilweise"]
                                + [i for i, _ in b["aufgeblaeht"]]
                                + [i for i, _ in b["schleife"]]))
            if b["apparat"]:
                apparat_gesamt += len(b["apparat"])
            if not (defekt or b["fehlend"] or (b["apparat"] and args.zeige_apparat)):
                continue

            if not kopf_gezeigt:
                print(f"\n{buch.parent.name}\\{buch.name}")
                kopf_gezeigt = True

            teile = []
            if b["unuebersetzt"]:
                teile.append(f"unuebersetzt: {kurz(b['unuebersetzt'])}")
            if b["leer"]:
                teile.append(f"leer: {kurz(b['leer'])}")
            if b["teilweise"]:
                teile.append(f"teilweise unuebersetzt: {kurz(b['teilweise'])}")
            if b["schleife"]:
                teile.append("Wiederholungsschleife: " + ", ".join(
                    f"{i} ({q*100:.0f}%)" for i, q in b["schleife"][:8])
                    + (f" … (+{len(b['schleife'])-8})" if len(b["schleife"]) > 8 else ""))
            if b["aufgeblaeht"]:
                teile.append("aufgeblaeht: " + ", ".join(
                    f"{i} ({v:.1f}x)" for i, v in b["aufgeblaeht"][:8]))
            if b["kurz"]:
                teile.append(f"zu kurz: {kurz(b['kurz'])}")
            if b["fehlend"]:
                teile.append(f"fehlend: {kurz(b['fehlend'])}")
            if args.zeige_apparat and b["apparat"]:
                arten = collections.Counter(a for _, a in b["apparat"])
                teile.append("Apparat (ok): "
                             + ", ".join(f"{n}x {a}" for a, n in arten.items()))
            if not teile:
                continue
            print(f"  [{lang}] " + " | ".join(teile))
            gesamt += len(defekt) + len(b["fehlend"])

            if args.repair and defekt:
                n = gib_frei(buch, lang, defekt)
                print(f"       -> {n} Dateien geloescht und freigegeben")

            q = str(quelle_aufloesen(meta.get("quelldatei", ""), BASE)) if meta.get("quelldatei") else ""
            if q:
                # --book-dir ist noetig: kuratierte Ordnernamen weichen von dem
                # ab, was aus den Dateimetadaten abgeleitet wuerde.
                bd = f"{buch.parent.name}\\{buch.name}"
                resume_befehle.append(
                    f'python ebook-translate.py "{q}" --resume --book-dir "{bd}"')

    if apparat_gesamt:
        print(f"\n{apparat_gesamt} Chunks sind Register/Bibliografie/Endnoten — "
              f"dort ist unuebersetzter Text korrekt (mit --zeige-apparat auflisten).")

    if gesamt == 0:
        print("Keine defekten Chunks gefunden.")
        return

    print(f"\n{gesamt} auffaellige Chunks insgesamt.")
    if args.repair:
        print("\nJetzt nachuebersetzen:")
        for c in sorted(set(resume_befehle)):
            print(f"  {c}")
    else:
        print("Mit --repair werden sie geloescht und zur Neuuebersetzung freigegeben.")


if __name__ == "__main__":
    main()
