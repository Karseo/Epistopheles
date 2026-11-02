#!/usr/bin/env python3
r"""EPISTO: Zusammenfassung je Kapitel neu erzeugen (nur das Feld "zusammenfassung").

Problem: "zusammenfassung" und "these" in notizen\tags.json sagen oft dasselbe
(beide stammen aus demselben LLM-Aufruf in taggen.ps1). Dieses Skript erzeugt NUR
die Zusammenfassung neu: ein Satz zu Gegenstand und Gang des Kapitels, ohne die
schon erfassten Thesen zu wiederholen. Alle anderen Felder bleiben unberuehrt.

Zwei Schritte, damit nichts ungeprueft ueberschrieben wird:

  1. Erzeugen  -> schreibt notizen\zusammenfassung_neu.json (alt/neu je Kapitel),
                  tags.json bleibt unveraendert. Resume-faehig.
       python neu-zusammenfassen.py --buch "<Buchordner>" [--limit N]
       python neu-zusammenfassen.py --alle [--plan]

  2. Anwenden  -> sichert tags.json nach notizen\_backup\ und uebernimmt die neuen
                  Zusammenfassungen. Kapitel, deren Zusammenfassung seit dem
                  Erzeugen von Hand geaendert wurde, werden uebersprungen.
       python neu-zusammenfassen.py --buch "<Buchordner>" --anwenden
       python neu-zusammenfassen.py --alle --anwenden

Nur Kapitel mit Zusammenfassung UND These werden angefasst (ohne These gibt es
keine Redundanz).

Abbrechen ohne Fortschrittsverlust (--alle):
  - Nach jedem KAPITEL wird die Nebendatei atomar gespeichert. Ein Abbruch
    (Strg+C, Absturz, Stromausfall) kostet hoechstens das gerade laufende Kapitel.
  - Sauber nach dem laufenden BUCH aufhoeren: in einem zweiten Fenster
        python neu-zusammenfassen.py --stop
    legt tools\neu-zusammenfassen.stop an. Der Lauf beendet das aktuelle Buch,
    entfernt die Datei und hoert auf.
  - Neustart mit demselben Befehl macht dort weiter, wo der Lauf stand.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

OLLAMA_CHAT = "http://127.0.0.1:11434/api/chat"
MIN_WOERTER, MAX_WOERTER = 6, 45
STANDARD_CTX = 32768
CTX_STUFEN = (32768, 65536, 98304, 131072, 196608, 262144)
# Gemessen an einem deutschen Kapitel (7019 Woerter): 2,17 Tokens/Wort und
# 3,36 Zeichen/Token. TOKENS_JE_WORT etwas grosszuegiger, weil englische und
# Fachtexte abweichen koennen.
TOKENS_JE_WORT = 2.3
ZEICHEN_JE_TOKEN = 3.36
OVERHEAD_TOKENS = 3500  # Anweisung, Thesen, Antwort inkl. Denkphase, Puffer
# Gemessen an einem Kapitel mit ~8000 Woertern; kuerzere gehen schneller.
RICHTWERT_SEKUNDEN_JE_KAPITEL = 15
HINWEIS_ANWENDEN = ("Hinweis: Die neuen Saetze stehen nur in notizen\\zusammenfassung_neu.json. tags.json "
                    "(und damit die TUI) aendert sich erst mit:  python neu-zusammenfassen.py --alle --anwenden")

SYSTEM = """Du bist ein Assistent fuer die Analyse philosophischer und sozialwissenschaftlicher Texte. Du liest einen Abschnitt aus dem Werk "{titel}" von {autor}.

Aufgabe: Schreibe EINEN Satz (hoechstens 35 Woerter), der sagt, WORUM es im Abschnitt geht und WIE er vorgeht (Gegenstand und Gang), etwa: "Der Abschnitt untersucht X am Beispiel von Y und stellt es Z gegenueber."

Regeln:
- Nenne KEINE Behauptungen, Ergebnisse oder Schlussfolgerungen des Textes. Die Thesen sind bereits separat erfasst (siehe unten) und duerfen weder wiederholt noch umschrieben werden.
- Keine Wertung, keine Floskeln wie "In diesem Abschnitt wird gezeigt, dass".
- Genau ein Satz.

Du antwortest AUSSCHLIESSLICH mit gueltigem JSON, ohne Markdown-Codeblock, ohne Erklaerung:
{{"zusammenfassung": "..."}}"""


# ---------------------------------------------------------------- Dateien ----

def lese_json(pfad: Path):
    return json.loads(pfad.read_text(encoding="utf-8-sig"))


def schreibe_json(pfad: Path, daten) -> None:
    """Atomar: erst in eine Nebendatei, dann ersetzen. Ein Abbruch mitten im
    Schreiben (Strg+C, Stromausfall) laesst die alte Datei heil."""
    tmp = pfad.with_name(pfad.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(daten, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, pfad)


def standard_root() -> Path:
    return Path(__file__).resolve().parent.parent


def stopdatei(root: Path) -> Path:
    return root / "tools" / "neu-zusammenfassen.stop"


def finde_buecher(root: Path):
    autor_root = root / "reader"
    if not autor_root.is_dir():
        return
    for autor in sorted(autor_root.iterdir()):
        if not autor.is_dir():
            continue
        for buch in sorted(autor.iterdir()):
            if (buch / "notizen" / "tags.json").is_file():
                yield buch


def lade_tags(buch: Path) -> dict | None:
    """None, wenn nicht lesbar oder nicht im erwarteten Format."""
    try:
        tags = lese_json(buch / "notizen" / "tags.json")
    except (OSError, ValueError):
        return None
    return tags if isinstance(tags, dict) and isinstance(tags.get("kapitel"), list) else None


def lade_neu(buch: Path, modell: str) -> dict:
    pfad = buch / "notizen" / "zusammenfassung_neu.json"
    if pfad.exists():
        try:
            return lese_json(pfad)
        except ValueError:
            sys.exit(f"{pfad} ist kaputt - bitte pruefen oder loeschen.")
    return {"modell": modell, "eintraege": {}}


def kandidaten(tags: dict) -> list[dict]:
    return [k for k in tags["kapitel"]
            if isinstance(k, dict) and k.get("zusammenfassung") and k.get("these")]


# -------------------------------------------------------------- Auswertung ----

def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zäöüß0-9]{4,}", text.lower()))


def ueberdeckung(thesen: list[str], zusammenfassung: str) -> float:
    """Mittlerer Anteil der Inhaltswoerter einer These, die schon in der
    Zusammenfassung stehen (0..1). Grobes Mass: zaehlt nur gemeinsame Woerter."""
    z = tokens(zusammenfassung)
    anteile = [len(tokens(t) & z) / len(tokens(t)) for t in thesen if tokens(t)]
    return sum(anteile) / len(anteile) if anteile else 0.0


def dauer(sekunden: float) -> str:
    sekunden = int(sekunden)
    return f"{sekunden // 3600}h{sekunden % 3600 // 60:02d}m"


def vergleich(neu: dict, ausfuehrlich: bool = True) -> None:
    eintraege = list(neu["eintraege"].items())
    if not eintraege:
        return
    alt_u = [ueberdeckung(e["thesen"], e["alt"]) for _, e in eintraege]
    neu_u = [ueberdeckung(e["thesen"], e["neu"]) for _, e in eintraege]
    kopf = "Vergleich (%d Kapitel)" % len(eintraege)
    stat = "Woerter alt/neu (Mittel): %.0f / %.0f | Ueberdeckung mit den Thesen alt/neu: %.0f%% / %.0f%%" % (
        sum(len(e["alt"].split()) for _, e in eintraege) / len(eintraege),
        sum(len(e["neu"].split()) for _, e in eintraege) / len(eintraege),
        100 * sum(alt_u) / len(alt_u), 100 * sum(neu_u) / len(neu_u))
    if not ausfuehrlich:
        print(f"{kopf}: {stat}", flush=True)
        return
    print(f"\n=== {kopf} ===\n{stat}")
    for (datei, e), a, n in zip(eintraege, alt_u, neu_u):
        print(f"\n--- {datei} | {e['titel'][:60]}  (Ueberdeckung {a:.0%} -> {n:.0%})")
        print("ALT:", e["alt"])
        print("NEU:", e["neu"])


# ------------------------------------------------------------------- LLM -----

def kontext_fuer(woerter: int, max_ctx: int = 131072, mindest: int = STANDARD_CTX) -> int | None:
    """Kleinster Kontext, in den Kapitel und Anweisung passen; None, wenn selbst
    max_ctx nicht reicht. Wichtig, weil Ollama zu lange Prompts STILL kuerzt: es
    behaelt nur die ersten 4 Tokens und das Ende, die Anweisung und die Thesen
    gehen verloren, und das Modell antwortet frei statt mit JSON."""
    benoetigt = int(woerter * TOKENS_JE_WORT) + OVERHEAD_TOKENS
    for stufe in CTX_STUFEN:
        if max(benoetigt, mindest) <= stufe <= max_ctx:
            return stufe
    return None


def pruefe_nicht_gekuerzt(antwort: dict, system: str, user: str) -> None:
    """Zweite Sicherung neben kontext_fuer: Hat Ollama deutlich weniger Tokens
    gesehen, als der Prompt haben muesste, wurde gekuerzt."""
    gesehen = (antwort.get("prompt_eval_count") or 0) + (antwort.get("prompt_eval_cached_count") or 0)
    erwartet = (len(system) + len(user)) / ZEICHEN_JE_TOKEN
    if gesehen and gesehen < 0.6 * erwartet:
        raise RuntimeError(f"Ollama hat den Prompt gekuerzt ({gesehen} statt ca. {erwartet:.0f} Tokens)")


def frage(modell: str, num_ctx: int, system: str, user: str) -> str:
    body = json.dumps({
        "model": modell,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "options": {"temperature": 0.2, "num_ctx": num_ctx},
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA_CHAT, data=body,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=1800) as antwort:
        daten = json.loads(antwort.read().decode("utf-8"))
    pruefe_nicht_gekuerzt(daten, system, user)
    return daten["message"]["content"]


def parse_antwort(roh: str) -> str:
    s = re.sub(r"(?s)<think>.*?</think>", "", roh).strip()
    s = re.sub(r"(?s)^```(?:json)?\s*|\s*```$", "", s).strip()
    try:
        d = json.loads(s)
    except json.JSONDecodeError:
        a, b = s.find("{"), s.rfind("}")
        if a < 0 or b <= a:
            raise ValueError(f"keine JSON-Antwort, Anfang: {s[:80]!r}") from None
        d = json.loads(s[a:b + 1])
    return re.sub(r"\s+", " ", str(d.get("zusammenfassung", "")).strip())


# ---------------------------------------------------------------- Erzeugen ----

def erzeuge(args, buch: Path, tags: dict, ausfuehrlich: bool = True) -> int:
    """Erzeugt die offenen Kapitel eines Buchs; gibt die Zahl neu erzeugter zurueck."""
    neu_pfad = buch / "notizen" / "zusammenfassung_neu.json"
    neu = lade_neu(buch, args.model)
    meta_pfad = buch / "meta.json"
    meta = lese_json(meta_pfad) if meta_pfad.exists() else {}
    titel = meta.get("titel") or tags.get("werk") or buch.name
    autor = meta.get("autor") or tags.get("autor") or ""
    system = SYSTEM.format(titel=titel, autor=autor)

    kand = kandidaten(tags)
    todo = [k for k in kand if k["datei"] not in neu["eintraege"]]
    if args.limit:
        todo = todo[: args.limit]
    print(f"Werk: {titel} | Modell: {args.model} | Kandidaten: {len(kand)} | "
          f"schon neu: {len(neu['eintraege'])} | jetzt: {len(todo)}", flush=True)

    erzeugt = 0
    for i, k in enumerate(todo, 1):
        quelle = buch / "quelle" / k["datei"]
        if not quelle.exists():
            print(f"[{i}/{len(todo)}] {k['datei']}: Quelldatei fehlt - uebersprungen", flush=True)
            continue
        text = quelle.read_text(encoding="utf-8-sig")
        woerter_text = len(text.split())
        max_ctx = getattr(args, "max_ctx", 131072)
        ctx = kontext_fuer(woerter_text, max_ctx, args.num_ctx)
        if ctx is None:
            print(f"[{i}/{len(todo)}] {k['datei']}: {woerter_text} Woerter passen nicht in --max-ctx {max_ctx} "
                  f"- uebersprungen", flush=True)
            continue
        thesen = "\n".join(f"- {t}" for t in k["these"])
        user = (f'Kapitel {k.get("kapitel_nr", "")}: "{k.get("titel", "")}"\n\n'
                f"BEREITS ERFASSTE THESEN (nicht wiederholen, nicht umschreiben):\n{thesen}\n\nTEXT:\n{text}")
        ergebnis = None
        for versuch in range(1, 4):
            try:
                satz = parse_antwort(frage(args.model, ctx, system, user))
            except Exception as exc:  # Netz, JSON, Timeout (Strg+C ist keine Exception)
                print(f"    Fehler (Versuch {versuch}): {exc}", flush=True)
                continue
            woerter = len(satz.split())
            if MIN_WOERTER <= woerter <= MAX_WOERTER:
                ergebnis = satz
                break
            print(f"    verworfen (Versuch {versuch}): {woerter} Woerter", flush=True)
        if ergebnis is None:
            print(f"[{i}/{len(todo)}] {k['datei']}: kein brauchbares Ergebnis", flush=True)
            continue
        neu["eintraege"][k["datei"]] = {
            "titel": k.get("titel", ""), "alt": k["zusammenfassung"], "neu": ergebnis, "thesen": k["these"],
        }
        neu["modell"] = args.model
        schreibe_json(neu_pfad, neu)  # nach jedem Kapitel: atomar, resume-faehig
        erzeugt += 1
        print(f"[{i}/{len(todo)}] {k['datei']}  {len(k['zusammenfassung'].split())} -> "
              f"{len(ergebnis.split())} Woerter" + (f"  [Kontext {ctx}]" if ctx != args.num_ctx else ""), flush=True)

    vergleich(neu, ausfuehrlich)
    return erzeugt


def alle_erzeugen(args) -> None:
    root = Path(args.root) if args.root else standard_root()
    stop = stopdatei(root)
    if stop.exists():
        stop.unlink()
        print("Alte Stopp-Datei entfernt.", flush=True)

    plan = []  # (buch, kandidaten, offen)
    uebersprungen = []
    for buch in finde_buecher(root):
        tags = lade_tags(buch)
        if tags is None:
            uebersprungen.append(buch)
            continue
        neu = lade_neu(buch, args.model)
        kand = kandidaten(tags)
        offen = [k for k in kand if k["datei"] not in neu["eintraege"]]
        plan.append((buch, len(kand), len(offen)))
    mit_arbeit = [p for p in plan if p[2] > 0]
    gesamt_offen = sum(p[2] for p in mit_arbeit)
    print(f"Buecher mit tags.json: {len(plan)} | mit offenen Kapiteln: {len(mit_arbeit)} | "
          f"offene Kapitel: {gesamt_offen} | tags.json nicht lesbar/anderes Format: {len(uebersprungen)}")
    for buch in uebersprungen:
        print(f"  uebersprungen: {buch.parent.name} / {buch.name}")
    print(f"Richtwert: {RICHTWERT_SEKUNDEN_JE_KAPITEL} s/Kapitel -> ca. "
          f"{dauer(gesamt_offen * RICHTWERT_SEKUNDEN_JE_KAPITEL)} (kuerzere Kapitel gehen schneller)", flush=True)
    if args.plan or not mit_arbeit:
        return
    print("Sauber stoppen nach dem laufenden Buch: python neu-zusammenfassen.py --stop  (oder Strg+C)", flush=True)
    print(HINWEIS_ANWENDEN + "\n", flush=True)

    start = time.time()
    erledigt = 0
    try:
        for nr, (buch, _kand, offen) in enumerate(mit_arbeit, 1):
            print(f"\n##### Buch {nr}/{len(mit_arbeit)}: {buch.parent.name} / {buch.name} "
                  f"({offen} offene Kapitel)", flush=True)
            erledigt += erzeuge(args, buch, lade_tags(buch), ausfuehrlich=False)
            print(f"Buch erzeugt (noch NICHT in tags.json uebernommen). In diesem Lauf: {erledigt}/{gesamt_offen} Kapitel, "
                  f"{dauer(time.time() - start)}", flush=True)
            if stop.exists():
                stop.unlink()
                print(f"Stopp-Datei gefunden - Lauf nach Buch {nr}/{len(mit_arbeit)} beendet. "
                      f"Fortsetzen mit demselben Befehl.", flush=True)
                return
    except KeyboardInterrupt:
        print(f"\nAbgebrochen (Strg+C) nach {dauer(time.time() - start)}. Fortschritt ist gespeichert "
              f"(hoechstens das gerade laufende Kapitel fehlt). Fortsetzen mit demselben Befehl.", flush=True)
        sys.exit(130)
    print(f"\nFertig: {erledigt} Kapitel in {dauer(time.time() - start)} erzeugt.\n{HINWEIS_ANWENDEN}", flush=True)


# ---------------------------------------------------------------- Anwenden ----

def anwende(buch: Path, tags: dict, tags_pfad: Path, still: bool = False):
    """Uebernimmt die neuen Zusammenfassungen. Gibt (uebernommen, von_hand_geaendert)
    zurueck oder None, wenn nichts anzuwenden ist."""
    neu_pfad = buch / "notizen" / "zusammenfassung_neu.json"
    if not neu_pfad.exists() or not lese_json(neu_pfad)["eintraege"]:
        if still:
            return None
        sys.exit("Keine neuen Zusammenfassungen - erst ohne --anwenden erzeugen.")
    neu = lese_json(neu_pfad)

    # Erst entscheiden, dann sichern: ohne Aenderung entsteht kein Backup.
    aenderungen, geaendert = [], 0
    for k in tags["kapitel"]:
        e = neu["eintraege"].get(k["datei"])
        if not e:
            continue
        if k.get("zusammenfassung") == e["alt"]:
            aenderungen.append((k, e["neu"]))
        elif k.get("zusammenfassung") != e["neu"]:
            geaendert += 1  # seit dem Erzeugen von Hand geaendert -> nicht ueberschreiben
        # sonst: schon uebernommen

    ziel = None
    if aenderungen:
        backup_dir = buch / "notizen" / "_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stempel = f"{datetime.now():%Y%m%d-%H%M%S}"
        ziel = backup_dir / f"tags.{stempel}.json"
        nr = 1
        while ziel.exists():  # nie ein vorhandenes Backup ueberschreiben
            nr += 1
            ziel = backup_dir / f"tags.{stempel}-{nr}.json"
        shutil.copy2(tags_pfad, ziel)
        for k, text in aenderungen:
            k["zusammenfassung"] = text
        schreibe_json(tags_pfad, tags)
    if not still:
        print(f"Backup: {ziel if ziel else '(keins, nichts geaendert)'}\n"
              f"Uebernommen: {len(aenderungen)} | von Hand geaendert (uebersprungen): {geaendert}")
    return len(aenderungen), geaendert


def alle_anwenden(args) -> None:
    root = Path(args.root) if args.root else standard_root()
    buecher = gesamt = von_hand = 0
    for buch in finde_buecher(root):
        tags = lade_tags(buch)
        if tags is None:
            continue
        ergebnis = anwende(buch, tags, buch / "notizen" / "tags.json", still=True)
        if ergebnis is None:
            continue
        uebernommen, geaendert = ergebnis
        if uebernommen or geaendert:
            buecher += 1
            gesamt += uebernommen
            von_hand += geaendert
            print(f"{buch.parent.name} / {buch.name}: {uebernommen} uebernommen, {geaendert} von Hand geaendert")
    print(f"\nFertig: {gesamt} Kapitel in {buecher} Buechern uebernommen | von Hand geaendert (uebersprungen): {von_hand}")


# -------------------------------------------------------------------- main ----

def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    ap = argparse.ArgumentParser(description="Zusammenfassung je Kapitel neu erzeugen (siehe Modul-Docstring).")
    modus = ap.add_mutually_exclusive_group(required=True)
    modus.add_argument("--buch", help="ein Buchordner (Autor\\<Autor>\\<Buch>)")
    modus.add_argument("--alle", action="store_true", help="alle Buecher mit tags.json")
    modus.add_argument("--stop", action="store_true", help="laufenden --alle-Lauf nach dem aktuellen Buch beenden")
    ap.add_argument("--root", help="Wurzelordner der Bibliothek (Standard: Elternordner dieses Skripts)")
    ap.add_argument("--plan", action="store_true", help="mit --alle: nur anzeigen, was getan wuerde")
    ap.add_argument("--limit", type=int, default=0, help="nur die ersten N offenen Kapitel (je Buch)")
    ap.add_argument("--model", default="qwen3.8:27b")
    ap.add_argument("--num-ctx", type=int, default=STANDARD_CTX, help="Standard-Kontext (waechst bei langen Kapiteln)")
    ap.add_argument("--max-ctx", type=int, default=131072, help="groesster erlaubter Kontext; laengere Kapitel werden uebersprungen")
    ap.add_argument("--anwenden", action="store_true", help="neue Zusammenfassungen in tags.json uebernehmen")
    args = ap.parse_args()

    root = Path(args.root) if args.root else standard_root()
    if args.stop:
        stop = stopdatei(root)
        stop.parent.mkdir(parents=True, exist_ok=True)
        stop.touch()
        print(f"Stopp angefordert ({stop}). Der Lauf endet nach dem aktuellen Buch.")
        return
    if args.alle:
        alle_anwenden(args) if args.anwenden else alle_erzeugen(args)
        return

    buch = Path(args.buch)
    tags_pfad = buch / "notizen" / "tags.json"
    if not tags_pfad.exists():
        sys.exit(f"Keine tags.json: {tags_pfad}")
    tags = lade_tags(buch)
    if tags is None:
        sys.exit("tags.json hat nicht das erwartete Format (Objekt mit 'kapitel') - uebersprungen.")
    try:
        if args.anwenden:
            anwende(buch, tags, tags_pfad)
        else:
            erzeuge(args, buch, tags)
    except KeyboardInterrupt:
        print("\nAbgebrochen (Strg+C). Fortschritt ist gespeichert.", flush=True)
        sys.exit(130)


if __name__ == "__main__":
    main()