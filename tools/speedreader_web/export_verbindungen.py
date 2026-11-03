"""Verbindungsdaten fuer die Ansicht "Verbindungen" der Epistopheles-App (Plan 2026-11-03):
`verbindungen.json` neben `daten.json` im Paket <Bibliothek>\\reader\\export-epistopheles\\.

Dieses Modul baut zuerst die Basis aus den Dateien der Buchordner (Werke, Kapitel, Themen = Straenge,
Querverweise); die Aehnlichkeit aus Qdrant kommt aus `qdrant_nachbarn.py`. Die Ids beziehen sich auf
`daten.json` (Buch-Id `b001`, Kapitelnummer): nur Buecher und Kapitel, die dort stehen, sind Knoten.

Id-Schema: Werk `b001`, Kapitel `b001:3`, Thema `b001#strang-slug`.
Nur lesend. Nur Standardbibliothek."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # tools\ fuer episto_tui

from episto_tui import library  # noqa: E402
import bundle  # noqa: E402
import qdrant_nachbarn as qn  # noqa: E402

VERSION = 1
MINDESTWERT = 0.55          # Startwert; nach Kalibrierung auf APIC (verbindungen_stichprobe.py) festlegen
JE_CHUNK = 10               # Nachbarn je Chunk aus Qdrant
JE_KAPITEL = 8              # Zielkapitel je Kapitel im Export
WARNUNG_OHNE_QDRANT = "Ohne Qdrant exportiert: keine ähnlichen Stellen (nur Themen und Querverweise)."


def _text(wert: object) -> str:
    return wert if isinstance(wert, str) else ""


def baue_basis(root: Path, daten: dict) -> dict:
    """`werke`, `kapitel`, `themen`, `querverweise` im Format von verbindungen.json (siehe Plan).

    `daten` ist der Inhalt von daten.json (nur `buecher[].id/autor/titel/kapitel[].nr/titel` werden gelesen).
    Buecher ohne Ordner in der Bibliothek und Ordner ohne Eintrag in daten.json entfallen. Themen verweisen nur
    auf Kapitel aus daten.json und haben mindestens zwei davon; ein Querverweis hat `nach` = Buch-Id, wenn das
    Zielwerk in der Bibliothek UND in daten.json liegt, sonst `nach: None` (Werk ausserhalb: nicht oeffnbar).
    Fehlerhafte Eintraege der Buchdateien werden uebersprungen, nie eine Ausnahme."""
    platte = library.discover_books(root)
    nach_name = {(b.autor, b.titel): b for b in platte}
    eintraege = [(e, nach_name[(e.get("autor"), e.get("titel"))]) for e in daten.get("buecher", [])
                 if isinstance(e, dict) and (e.get("autor"), e.get("titel")) in nach_name and isinstance(e.get("id"), str)]
    id_von_buch = {id(buch): e["id"] for e, buch in eintraege}      # Buch-Objekt -> Buch-Id aus daten.json

    werke, kapitel, themen, querverweise = [], [], [], []
    for e, buch in eintraege:
        wid = e["id"]
        werke.append({"id": wid, "autor": buch.autor, "titel": buch.titel})
        nummern = set()
        for k in e.get("kapitel", []):
            if isinstance(k, dict) and isinstance(k.get("nr"), int):
                nummern.add(k["nr"])
                kapitel.append({"id": f"{wid}:{k['nr']}", "werk": wid, "nr": k["nr"], "titel": _text(k.get("titel"))})
        for s in library.list_straenge(buch):
            vorhanden = [nr for nr in s["kapitel"] if nr in nummern]
            if len(vorhanden) >= 2:
                themen.append({"id": f"{wid}#{s['slug']}", "werk": wid, "name": s["name"], "kapitel": vorhanden})
        gesehen = set()
        try:
            bezuege = library.read_querbezuege(buch)
        except ValueError:                                           # z. B. kein UTF-8 in der Datei
            bezuege = []
        for b in bezuege:
            ziel = b.get("ziel")
            if not isinstance(ziel, str) or not ziel:
                continue
            ziel_buch = library.finde_buch_fuer_ziel(platte, ziel)
            nach = id_von_buch.get(id(ziel_buch)) if ziel_buch is not None else None
            if nach == wid:
                continue                                              # Verweis auf das eigene Werk
            eintrag = {"von": wid, "nach": nach, "autor": _text(b.get("autor")), "titel": _text(b.get("titel")),
                       "relation": _text(b.get("relation")), "notiz": _text(b.get("notiz"))}
            schluessel = (nach, ziel if nach is None else "", eintrag["relation"])
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            querverweise.append(eintrag)
    return {"werke": werke, "kapitel": kapitel, "themen": themen, "querverweise": querverweise}


def _lade_daten_json(ordner: Path) -> dict:
    pfad = ordner / "daten.json"
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"{pfad} fehlt: zuerst export_daten.py ausführen") from None
    except (OSError, ValueError):
        raise ValueError(f"daten.json unlesbar ({pfad}): export_daten.py erneut ausführen") from None
    if not isinstance(daten, dict) or not isinstance(daten.get("erstellt"), str) or not isinstance(daten.get("buecher"), list):
        raise ValueError(f"daten.json hat nicht das erwartete Format ({pfad}): export_daten.py erneut ausführen")
    return daten


def _schreibe_json(pfad: Path, daten: dict) -> None:
    """Atomar: temporaere Datei im selben Ordner, dann `os.replace`; bei einem Fehler bleibt die alte Datei, kein Rest."""
    fd, tmp = tempfile.mkstemp(dir=pfad.parent, prefix=pfad.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(daten, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, pfad)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _aehnlich(basis: dict, qdrant: str, collection: str, mindestwert: float, je: int, je_kapitel: int, fetch, pause: float,
              versuche: int, fortschritt) -> tuple[list[dict], dict | None, list[str]]:
    """Aehnlichkeit aus Qdrant: (Kanten, Zaehler fuer verbindungen.json, Warnungen). Nicht erreichbar -> ([], None, Warnung)."""
    werke = {(w["autor"], w["titel"]): w["id"] for w in basis["werke"]}
    kapitel_ids = {k["id"] for k in basis["kapitel"]}
    try:
        punkte = qn.lese_punkte(qdrant, collection, fetch=fetch, pause=pause, versuche=versuche)
        ids = [pid for pid, p in punkte.items() if f"{werke.get((p['autor'], p['buch']))}:{p['kapitel_nr']}" in kapitel_ids]
        if not ids:
            return [], None, [f"Qdrant ({collection}) enthält keine Punkte zu den exportierten Kapiteln (Namen von Autor und Buch müssen übereinstimmen): "
                              "ähnliche Stellen fehlen."]
        erg = qn.frage_nachbarn(qdrant, collection, punkte, ids, je=je, fetch=fetch, pause=pause, versuche=versuche, fortschritt=fortschritt)
    except qn.QdrantFehler as e:
        return [], None, [f"Qdrant nicht erreichbar oder nicht lesbar ({e}): ähnliche Stellen fehlen."]
    kanten = qn.fasse_zusammen(erg.treffer, punkte, kapitel_ids, werke, mindestwert, je_kapitel=je_kapitel)
    warnungen = []
    if erg.fehlend:
        warnungen.append(f"{erg.fehlend} von {erg.abgefragt} Abfragen an Qdrant sind fehlgeschlagen: die ähnlichen Stellen sind unvollständig.")
    return kanten, {"abgefragt": erg.abgefragt, "fehlend": erg.fehlend, "mindestwert": mindestwert}, warnungen


def exportiere(root: Path, ordner: Path | None = None, qdrant: str | None = "http://127.0.0.1:6333", collection: str = "episto",
               mindestwert: float = MINDESTWERT, je: int = JE_CHUNK, je_kapitel: int = JE_KAPITEL, fetch=None, pause: float = 1.0,
               versuche: int = 3, fortschritt=None) -> dict:
    """Schreibt `verbindungen.json` ins Paket (Standard <Bibliothek>\\reader\\export-epistopheles) und gibt
    {"verbindungen": <Inhalt>, "warnungen": [Text], "pfad": Path} zurueck.

    Voraussetzung ist `daten.json` im selben Ordner (sonst ValueError mit Hinweis); `erstellt` kommt von dort. `qdrant=None`
    oder Qdrant nicht erreichbar: Themen und Querverweise bleiben, `aehnlich` ist leer, `qdrant` ist null, eine Warnung steht
    im Ergebnis. Fehlen einzelne Abfragen, steht `qdrant.fehlend` > 0 und eine Warnung da: die Datei wird nie als vollstaendig
    ausgegeben, wenn sie es nicht ist. Geschrieben wird atomar; bei jedem Fehler davor bleibt eine vorhandene Datei unveraendert."""
    root = Path(root)
    ordner = Path(ordner) if ordner is not None else bundle.standard_paket(root)
    daten = _lade_daten_json(ordner)
    basis = baue_basis(root, daten)
    if qdrant is None:
        kanten, zaehler, warnungen = [], None, [WARNUNG_OHNE_QDRANT]
    else:
        kanten, zaehler, warnungen = _aehnlich(basis, qdrant, collection, mindestwert, je, je_kapitel, fetch, pause, versuche, fortschritt)
    verbindungen = {"version": VERSION, "erstellt": daten["erstellt"], "qdrant": zaehler, **basis, "aehnlich": kanten}
    pfad = ordner / "verbindungen.json"
    _schreibe_json(pfad, verbindungen)
    return {"verbindungen": verbindungen, "warnungen": warnungen, "pfad": pfad}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="verbindungen.json fuer die Ansicht Verbindungen erzeugen (nach export_daten.py)")
    ap.add_argument("--root", help="Wurzelordner der Bibliothek (sonst EPISTO_ROOT / Standard)")
    ap.add_argument("--paket", help="Paketordner mit daten.json (sonst <Bibliothek>\\reader\\export-epistopheles)")
    ap.add_argument("--qdrant", default="http://127.0.0.1:6333")
    ap.add_argument("--collection", default="episto")
    ap.add_argument("--ohne-qdrant", action="store_true", help="nur Themen und Querverweise, keine ähnlichen Stellen")
    ap.add_argument("--mindestwert", type=float, default=MINDESTWERT, help="kleinste Aehnlichkeit eines Chunk-Paars (Kalibrierung: verbindungen_stichprobe.py)")
    ap.add_argument("--je", type=int, default=JE_CHUNK, help="Nachbarn je Chunk aus Qdrant")
    ap.add_argument("--je-kapitel", type=int, default=JE_KAPITEL, help="Zielkapitel je Kapitel im Export")
    ap.add_argument("--versuche", type=int, default=3)
    ap.add_argument("--pause", type=float, default=1.0, help="Wartezeit vor dem ersten Wiederholen (Sekunden)")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    root = library.resolve_root(args.root, os.environ)
    zuletzt = [-1]

    def fortschritt(fertig: int, gesamt: int) -> None:
        zehntel = fertig * 10 // max(1, gesamt)
        if zehntel != zuletzt[0]:
            zuletzt[0] = zehntel
            print(f"  Qdrant: {fertig}/{gesamt} Chunks abgefragt", flush=True)

    try:
        erg = exportiere(root, Path(args.paket) if args.paket else None, None if args.ohne_qdrant else args.qdrant, args.collection,
                         args.mindestwert, args.je, args.je_kapitel, pause=args.pause, versuche=args.versuche, fortschritt=fortschritt)
    except ValueError as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Fehler beim Schreiben: {e}", file=sys.stderr)
        return 1
    v = erg["verbindungen"]
    print(f"{len(v['werke'])} Werke, {len(v['kapitel'])} Kapitel, {len(v['themen'])} Themen, {len(v['aehnlich'])} Ähnlichkeitskanten, "
          f"{len(v['querverweise'])} Querverweise -> {erg['pfad']} ({erg['pfad'].stat().st_size // 1024} KB)")
    warnungen = [w for w in erg["warnungen"] if not (args.ohne_qdrant and w == WARNUNG_OHNE_QDRANT)]
    if args.ohne_qdrant:
        print("Hinweis: ohne ähnliche Stellen exportiert (--ohne-qdrant).")
    for w in warnungen:
        print(f"WARNUNG: {w}")
    return 3 if warnungen else 0


if __name__ == "__main__":
    raise SystemExit(main())
