#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bereinige-translategemma.py — Bereinigt Quelle-Dateien, die mit dem alten
Modell `translategemma:27b` uebersetzt wurden und deshalb Fussnoten-Artefakte
enthalten (Callinicos "Social Theory", Kapitel 0005-0018).

translategemma liess die Markdown-Fussnoten-Marker `[^N]` fallen und rendert
sie stattdessen als blosses `N`:

  - Inline-Referenz  `...argumentierte".1`   -> `...argumentierte".*1`
  - Fussnoten-Text   `1 J. Heilbron, ...`     -> `*1 J. Heilbron, ...`
    (Zeilen, die mit einer Zahl + Leerzeichen beginnen und wie ein Zitat
     aussehen; reine Listenaufzaehlungen wie `1 Sie befasst ...` bleiben stehen)
  - Seitenzahlen-/Running-Header-Zeilen `260 Der Zusammenbruch?` werden
    entfernt (Seitenzahl-Bereich 200-400, darunter sind nur Fussnoten).

Zielformat entspricht der manuellen Bereinigung der Kapitel 0001-0004 und der
Konvention `*N` anderer Werke (Rothbard, Barclay, States of Credit).

Aufruf:
  python bereinige-translategemma.py --quelle "D:\\...\\quelle" --dry-run
  python bereinige-translategemma.py --quelle "D:\\...\\quelle"
"""

import argparse
import json
import re
from pathlib import Path

# Seitenzahl-/Running-Header-Zeile: 3-stellige Seitenzahl + Laufzeile (Titel).
# Nur im Bereich 200-400 — Fussnoten gehen hier bis max. ~116, Jahreszahlen
# (z.B. "1817") sind 4-stellig und fallen nicht in den 3-stelligen Treffer.
PAGE_HEADER = re.compile(r'^(\d{3})\s+([A-ZÄÖÜ][A-Za-zäöüßÄÖÜ][A-Za-zäöüßÄÖÜ \-–,.:?\'’]*)$')

# Fussnoten-Block: Zahl + Leerzeichen + Rest (kein 4-stelliges Jahr, da
# \\d{1,3} vor dem Leerzeichen nicht auf "1817 schlossen ..." passt).
FN_BLOCK = re.compile(r'^(\d{1,3})\s+(.+)$')

# Inline-Fussnoten-Referenz: 1-3 Ziffern, unmittelbar nach schliessender
# Interpunktion, und diese Interpunktion steht NICHT hinter einer Ziffer
# (schliesst Abschnittsnummern "1.2" aus). Kein Match hinter "S. 88" etc.,
# da dort ein Leerzeichen vor der Zahl steht. Enthaelt auch die deutschen
# typografischen Schlusszeichen: „…“ (U+201C) und ‚…‘ (U+2018).
INLINE = re.compile(r'(?<![\d])(["“”’‘)\]!?:;.])(\d{1,3})(?!\d)')


def ist_fussnote(rest: str) -> bool:
    """Heuristik: sieht der Rest einer '^N '-Zeile nach einem Zitat/Fussnote
    aus (im Gegensatz zu einer Listenaufzaehlung wie '1 Sie befasst ...')?"""
    return bool(
        re.search(r'\b(?:Ebd|Zitiert|Siehe|Brief|Vgl|Hrsg|ders|Ibid|Zum Beispiel)\b', rest)
        or re.search(r'\bS\.\s', rest)            # Seitenangabe "S. 88"
        or re.search(r'\b\d{4}\b', rest)          # Jahreszahl
        or re.search(r'\(\d{3}', rest)            # "(1995"
        or re.search(r'\b[A-ZÄÖÜ]\.\s', rest)     # Autor-Initiale "J. "
        or re.search(r'\)\s*[:–]', rest)          # Bio-Doppelpunkt "(1712–78):"
    )


def bereinige(text: str):
    """Liefert (neuer_text, stats-dict)."""
    stats = {"header_entfernt": 0, "fussnote_block": 0, "fussnote_inline": 0}

    fn_numbers = set()
    out_lines = []
    for line in text.split("\n"):
        m = PAGE_HEADER.match(line)
        if m and 200 <= int(m.group(1)) <= 400:
            stats["header_entfernt"] += 1
            continue
        m = FN_BLOCK.match(line)
        if m and ist_fussnote(m.group(2)):
            fn_numbers.add(int(m.group(1)))
            out_lines.append(f"*{m.group(1)} {m.group(2)}")
            stats["fussnote_block"] += 1
            continue
        out_lines.append(line)
    text = "\n".join(out_lines)

    def _repl(m):
        if int(m.group(2)) in fn_numbers:
            stats["fussnote_inline"] += 1
            return f"{m.group(1)}*{m.group(2)}"
        return m.group(0)

    text = INLINE.sub(_repl, text)
    return text, stats


# ── Absatz-Reflow ────────────────────────────────────────────────────────────
# translategemma hat beim PDF-Import nicht nur Fussnoten-Marker verloren,
# sondern auch Absatzgrenzen: Haerter Zeilenumbruch (fortgesetzte Zeile) und
# echtes Absatzende sind beide nur noch als einfaches '\n' sichtbar. Der Reflow
# rekonstruiert Absaetze nach der Regel: eine Zeile, die auf Satzzeichen/
# schliessende Klammer/Ziffer endet, beendet den Absatz; alles andere ist ein
# fortgesetzter Zeilenumbruch. Ueberschriften (Abschnittsnummern `N.N` und
# Kapiteltitel aus kapitel.json) bleiben eigene Zeilen. Anschliessend werden
# versehentlich getrennte Absaetze, deren Folgezeile klein beginnt, wieder mit
# dem vorherigen verbunden. Ziel: ein Absatz pro Zeile, Leerzeile dazwischen.

ABSCHNITT = re.compile(r'^\d+\.\d+\s')

# Gedruckte Seitenzahl auf eigener Zeile (PDF-Laufzeile), z.B. "-35-" — bei
# gescannten/konvertierten PDFs ueblich. Nur ganze Zeile, keine Listen/Ranges.
SEITENZAHL = re.compile(r'^-\d+-\s*$')


def lade_titel(kapitel_pfad: Path) -> set:
    """Alle Abschnittstitel aus kapitel.json (fuer die Heading-Erkennung)."""
    if not kapitel_pfad.exists():
        return set()
    titel = set()

    def walk(knoten):
        if isinstance(knoten, dict):
            if knoten.get("titel"):
                titel.add(str(knoten["titel"]).strip())
            for kind in knoten.get("kinder", []):
                walk(kind)
        elif isinstance(knoten, list):
            for x in knoten:
                walk(x)

    try:
        walk(json.loads(kapitel_pfad.read_text(encoding="utf-8")).get("gliederung", []))
    except (OSError, json.JSONDecodeError):
        pass
    return titel


def _absatzende(zeile: str, titel: set) -> bool:
    s = zeile.rstrip()
    if not s:
        return True
    if ABSCHNITT.match(s):
        return True
    if s.strip() in titel:
        return True
    return bool(re.search(r'[.!?:;)\]""”’“‘]$|\d$', s))


def reflow_absaetze(text: str, titel: set):
    """Liefert (neuer_text, stats-dict)."""
    # Seitenzahlen ("-35-") vorab entfernen — sonst haetten sie als
    # Nicht-Satzzeichen-Zeile den Absatz zusammengeklebt.
    text = "\n".join(l for l in text.split("\n") if not SEITENZAHL.match(l))
    paras = []
    cur = []
    for zeile in text.split("\n"):
        cur.append(zeile)
        if _absatzende(zeile, titel):
            paras.append(" ".join(x.strip() for x in cur if x.strip()))
            cur = []
    if cur:
        paras.append(" ".join(x.strip() for x in cur if x.strip()))

    # Versehentlich getrennte Absaetze (Folgezeile beginnt klein) wieder verbinden.
    merged = []
    last = -1
    for p in paras:
        if p and p[0].islower() and last >= 0:
            merged[last] += " " + p
        else:
            merged.append(p)
            if p:
                last = len(merged) - 1

    nonempty = [p for p in merged if p.strip()]
    return ("\n\n".join(nonempty) + "\n" if nonempty else ""), {"absaetze": len(nonempty)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quelle", required=True, help="Pfad zum quelle/-Ordner des Buches")
    ap.add_argument("--dry-run", action="store_true", help="nur berichten, nichts schreiben")
    ap.add_argument("--reflow", action="store_true", help="zusätzlich Absaetze rekonstruieren (Seitenzahlen + harte Umbrueche)")
    ap.add_argument("--ohne-fussnoten", action="store_true", help="Fussnoten-Reformatierung ueberspringen (z.B. bei Endnoten-Listen)")
    args = ap.parse_args()

    quelle = Path(args.quelle)
    dateien = sorted(
        p for p in quelle.glob("*.md")
        if re.fullmatch(r"00\d\d_.+\.md", p.name)
    )
    titel = lade_titel(quelle.parent / "kapitel.json") if args.reflow else set()

    gesamt = {"header_entfernt": 0, "fussnote_block": 0, "fussnote_inline": 0, "absaetze": 0}
    for f in dateien:
        alt = f.read_text(encoding="utf-8")
        if args.ohne_fussnoten:
            neu, st = alt, {"header_entfernt": 0, "fussnote_block": 0, "fussnote_inline": 0}
        else:
            neu, st = bereinige(alt)
        ref_nr = int(f.name[:4])
        if args.reflow:
            neu, st2 = reflow_absaetze(neu, titel)
            st["absaetze"] = st2["absaetze"]
        if not args.dry_run and neu != alt:
            f.write_text(neu, encoding="utf-8", newline="\n")
        aenderung = " (geaendert)" if neu != alt else ""
        print(f"{f.name}: Header {st['header_entfernt']:3d} | Block {st['fussnote_block']:3d} "
              f"| Inline {st['fussnote_inline']:3d} | Absaetze {st.get('absaetze', 0):3d}{aenderung}")
        for k in gesamt:
            gesamt[k] += st.get(k, 0)

    print("\nGesamt:")
    print(f"  Seitenzahlen/Header entfernt : {gesamt['header_entfernt']}")
    print(f"  Fussnoten-Bloecke (*N)       : {gesamt['fussnote_block']}")
    print(f"  Inline-Referenzen (.*N)      : {gesamt['fussnote_inline']}")
    if args.reflow:
        print(f"  Absaetze nach Reflow         : {gesamt['absaetze']}")
    print(("\n(Dry-Run: nichts geschrieben)" if args.dry_run else "\nGeschrieben."))


if __name__ == "__main__":
    main()
