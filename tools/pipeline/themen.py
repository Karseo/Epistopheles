"""
themen.py  —  bibliotheksweite Themenliste: Abgleich und Pflege

Stichworte sind der Klammermechanismus der ganzen Erschliessung: Sie bilden
die Straenge innerhalb eines Buchs und verbinden Quellen ueber Buchgrenzen
hinweg. Das funktioniert nur, wenn dieselbe Sache ueberall gleich heisst.

Gemessen am ersten getaggten Buch: 174 Stichworte auf 263 Tags, davon 147 nur
einmal vergeben — ein Grossteil davon Varianten desselben Themas. Ohne
zentrale Liste wiederholt sich das mit jeder neuen Quelle.

Ablage: <Wurzel>\\hilfsdaten\\themen.json (Env EBOOK_HILFSDATEN uebersteuert den Ordner)

    {
      "themen": {
        "elite-herrschaft": {
          "aliase": ["elitenherrschaft", "elite-macht"],
          "quellen": 3,
          "erstmals": "2026-08-20"
        }
      }
    }

Verwendung als Modul:
    import themen
    liste = themen.lade()
    ergebnis = themen.gleiche_ab(["kulturzyklus", "caesarismus"], liste)

Als Skript:
    python themen.py --init          aus vorhandenen tags.json aufbauen
    python themen.py --liste         Themenliste anzeigen
    python themen.py --pruefe a,b,c  Stichworte abgleichen
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE   = Path(os.environ.get("EBOOK_BASE", Path(__file__).resolve().parents[2] / "rohdaten"))
LEKTOR = BASE / "Lektor"
HILFSDATEN = Path(os.environ.get("EBOOK_HILFSDATEN", Path(__file__).resolve().parents[2] / "hilfsdaten"))
DATEI  = HILFSDATEN / "themen.json"

# Ab dieser Aehnlichkeit gilt ein Stichwort als moegliche Variante
AEHNLICH = 0.72


def normiere(s: str) -> str:
    """Kleinschreibung, Umlaute aufgeloest, nur Wortzeichen und Bindestrich."""
    s = (s or "").strip().lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r'[^\w-]+', '-', s).strip('-')


def lade() -> dict:
    if not DATEI.exists():
        return {"themen": {}}
    try:
        d = json.loads(DATEI.read_text(encoding='utf-8'))
        d.setdefault("themen", {})
        return d
    except Exception as e:
        print(f"[!] themen.json unlesbar ({e}) — starte leer.")
        return {"themen": {}}


def speichere(liste: dict) -> Path:
    liste["themen"] = dict(sorted(liste["themen"].items()))
    DATEI.parent.mkdir(parents=True, exist_ok=True)
    DATEI.write_text(json.dumps(liste, ensure_ascii=False, indent=2),
                     encoding='utf-8')
    return DATEI


def _alias_index(liste: dict) -> dict[str, str]:
    """alias -> kanonisches Thema."""
    idx = {}
    for thema, daten in liste["themen"].items():
        idx[thema] = thema
        for a in daten.get("aliase", []):
            idx[normiere(a)] = thema
    return idx


def gleiche_ab(stichworte: list[str], liste: dict) -> dict:
    """
    Ordnet jedes Stichwort einer von drei Kategorien zu:
      bekannt   — exakter Treffer oder bekannter Alias
      aehnlich  — nahe an einem vorhandenen Thema, aber nicht gleich
      neu       — kein Bezug im Bestand

    'aehnlich' ist der wichtige Fall: dort entstehen die Varianten, die
    Straenge zerfasern. Die Entscheidung faellt der Mensch, nicht das Skript.
    """
    idx = _alias_index(liste)
    bekannte = list(liste["themen"].keys())
    ergebnis = {"bekannt": [], "aehnlich": [], "neu": []}

    for roh in stichworte:
        s = normiere(roh)
        if not s:
            continue
        if s in idx:
            ergebnis["bekannt"].append((roh, idx[s]))
            continue

        treffer = []
        for t in bekannte:
            quote = SequenceMatcher(None, s, t).ratio()
            # gleicher erster Wortteil zaehlt staerker als reine Zeichenaehnlichkeit
            if s.split("-")[0] == t.split("-")[0]:
                quote = max(quote, 0.80)
            if quote >= AEHNLICH:
                treffer.append((t, round(quote, 2)))
        if treffer:
            treffer.sort(key=lambda x: -x[1])
            ergebnis["aehnlich"].append((roh, treffer[:3]))
        else:
            ergebnis["neu"].append(roh)
    return ergebnis


def uebernimm(stichworte: list[str], liste: dict, quelle: str = "") -> int:
    """Neue Themen aufnehmen bzw. Zaehler erhoehen. Liefert die Zahl der Neuzugaenge."""
    import time
    idx = _alias_index(liste)
    neu = 0
    for roh in stichworte:
        s = normiere(roh)
        if not s:
            continue
        thema = idx.get(s)
        if thema:
            liste["themen"][thema]["quellen"] = \
                liste["themen"][thema].get("quellen", 0) + 1
        else:
            liste["themen"][s] = {
                "aliase": [],
                "quellen": 1,
                "erstmals": time.strftime("%Y-%m-%d"),
            }
            if quelle:
                liste["themen"][s]["zuerst_in"] = quelle
            neu += 1
    return neu


def aus_bestand() -> Counter:
    """
    Stichworte aus allen vorhandenen notizen/tags.json einsammeln.
    So startet die Themenliste nicht leer, sondern mit dem, was beim Taggen
    bereits entstanden ist.
    """
    zaehler = Counter()
    if not LEKTOR.is_dir():
        return zaehler
    for f in LEKTOR.rglob("notizen/tags.json"):
        try:
            eintraege = json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            continue
        for e in eintraege:
            s = normiere(e.get("stichwort", ""))
            if s:
                zaehler[s] += 1
    return zaehler


def bericht(ergebnis: dict) -> None:
    """Abgleichergebnis ausgeben — knapp, aber mit den Varianten im Klartext."""
    if ergebnis["bekannt"]:
        print(f"  bekannt  ({len(ergebnis['bekannt'])}): "
              + ", ".join(t for _, t in ergebnis["bekannt"]))
    for roh, treffer in ergebnis["aehnlich"]:
        vorschlaege = ", ".join(f"{t} ({q})" for t, q in treffer)
        print(f"  ÄHNLICH  '{roh}' → {vorschlaege}")
    if ergebnis["neu"]:
        print(f"  neu      ({len(ergebnis['neu'])}): " + ", ".join(ergebnis["neu"]))


def main():
    ap = argparse.ArgumentParser(
        description="Bibliotheksweite Themenliste: Abgleich und Pflege"
    )
    ap.add_argument("--init", action="store_true",
                    help="Liste aus vorhandenen notizen/tags.json aufbauen")
    ap.add_argument("--min", type=int, default=2,
                    help="bei --init: ab wie vielen Belegstellen ein Stichwort "
                         "aufgenommen wird (Standard 2)")
    ap.add_argument("--liste", action="store_true", help="Themenliste anzeigen")
    ap.add_argument("--pruefe", default=None,
                    help="Stichworte abgleichen (kommagetrennt)")
    ap.add_argument("--dry-run", action="store_true", help="nichts schreiben")
    args = ap.parse_args()

    liste = lade()

    if args.init:
        import time
        gefunden = aus_bestand()
        aufgenommen = 0
        for s, n in gefunden.items():
            if n < args.min or s in liste["themen"]:
                continue
            liste["themen"][s] = {"aliase": [], "quellen": n,
                                  "erstmals": time.strftime("%Y-%m-%d")}
            aufgenommen += 1
        print(f"Im Bestand gefunden : {len(gefunden)} Stichworte")
        print(f"Aufgenommen (≥{args.min})   : {aufgenommen}")
        print(f"Liste umfasst jetzt : {len(liste['themen'])}")
        if not args.dry_run:
            print(f"-> {speichere(liste)}")
        else:
            print("(DRY-RUN — nichts geschrieben.)")
        return

    if args.liste:
        if not liste["themen"]:
            print("Themenliste ist leer — mit --init aufbauen.")
            return
        print(f"{len(liste['themen'])} Themen\n")
        for t, d in sorted(liste["themen"].items(),
                           key=lambda x: -x[1].get("quellen", 0)):
            alias = f"  (auch: {', '.join(d['aliase'])})" if d.get("aliase") else ""
            print(f"  {d.get('quellen', 0):4d}  {t}{alias}")
        return

    if args.pruefe:
        stichworte = [s.strip() for s in args.pruefe.split(",") if s.strip()]
        print(f"Abgleich von {len(stichworte)} Stichworten "
              f"gegen {len(liste['themen'])} Themen:\n")
        bericht(gleiche_ab(stichworte, liste))
        return

    ap.print_help()


if __name__ == "__main__":
    main()
