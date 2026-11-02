"""Redaktionsänderungen am PC einarbeiten (Spec 5.1, 5.4) - Ebene Original-Chunk.

    python tools/redaktion_anwenden.py [--root PFAD] [--buch "Autor/Titel"]
                                       [--eingang DATEI] [--ausfuehren]

Standard ist ein Dry-Run: es wird nur gezeigt, was sich ändern würde. Mit --ausfuehren
wird je Chunk zuerst ein Backup angelegt (<Lektor-Buchordner>\\notizen\\_backup), dann der
neue Text atomar geschrieben, der Stand im Eingang gesetzt und `redaktion.json` im
Lektor-Buchordner fortgeschrieben.

Exit-Codes: 0 in Ordnung (auch wenn Rücknahmen als "nicht möglich" in der Summenzeile stehen),
1 ungültige Eingabe, 2 mindestens ein Konflikt, 3 nur Warnungen (Zeilen "WARNUNG: ...", etwa
Chunk geschrieben, aber Stand/redaktion.json nicht fortgeschrieben). Konflikt (2) hat Vorrang vor 3.

--eingang DATEI liest die Datei "Änderungen als Datei sichern" der App
({"geraet", "buch", "eintraege"}) und legt sie zuerst (idempotent) im Eingang ab.

`uebersetzung-uebernehmen` (Ebene `uebersetzung`) kopiert `de\\chunk_NNN.md.neu` nach
`de\\chunk_NNN.md` (Backup, `.neu` danach gelöscht). Konflikt, wenn `.neu` fehlt, die Übersetzung
(`vorher.hash`) oder der Vorschlag (`parameter.neu_hash`) nicht mehr der im Vergleich gesehenen ist.
Nur Standardbibliothek.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # tools\ fuer redaktion, episto_tui

from episto_tui.backup import backup_before_write  # noqa: E402
from redaktion import ops, protokoll  # noqa: E402

EBENE_CHUNK = "chunk-orig"
ART_UEBERNEHMEN = "uebersetzung-uebernehmen"
OFFENE_STAENDE = ("offen", "gesendet")


# --------------------------------------------------------------------------- Datenmodell

@dataclass
class EintragErgebnis:
    eintrag: dict
    status: str            # ops.STATUS_ANGEWENDET | STATUS_KONFLIKT | STATUS_UEBERSPRUNGEN
    grund: str = ""


@dataclass
class ChunkPlan:
    chunk: int
    datei: Path
    alt: str
    neu: str
    ergebnisse: list[EintragErgebnis] = field(default_factory=list)
    sprache: str = ""        # "en" | "de": Unterordner des Lektors, in dem der Chunk liegt

    @property
    def geaendert(self) -> bool:
        return self.neu != self.alt and any(
            r.status == ops.STATUS_ANGEWENDET for r in self.ergebnisse)


@dataclass
class UebernahmePlan:
    """`uebersetzung-uebernehmen`: `de/chunk_NNN.md.neu` ersetzt `de/chunk_NNN.md`."""
    chunk: int
    datei: Path                  # de/chunk_NNN.md
    neu_datei: Path              # de/chunk_NNN.md.neu
    alt: str                     # Inhalt von datei bei der Planung ("" wenn sie fehlt)
    neu: str                     # Inhalt von neu_datei bei der Planung
    ergebnis: EintragErgebnis
    bereits: bool = False        # schon übernommen (Wiederholung nach Teilausfall): nur noch Stand setzen


@dataclass
class BuchPlan:
    buch: str
    lektor: Path | None = None
    lektor_key: str = ""                               # Schlüssel des Lektor-Ordners (Eintrag `ziel.lektor` oder Buch)
    hinweis: str | None = None                         # z. B. ungültiger Ordnername
    chunks: list[ChunkPlan] = field(default_factory=list)
    uebernahmen: list[UebernahmePlan] = field(default_factory=list)
    konflikte: list[EintragErgebnis] = field(default_factory=list)   # ohne Chunk-Zuordnung
    uebersprungen: list[tuple[dict, str]] = field(default_factory=list)
    # Rücknahme-Einträge: übersprungen (Ziel nicht angewendet, wird nie angewendet) oder konflikt
    # (Ziel war schon angewendet: Rücknahme nicht möglich). Zählen nicht als Textkonflikt.
    ruecknahmen: list[EintragErgebnis] = field(default_factory=list)

    @property
    def anzahl_konflikte(self) -> int:
        return len(self.konflikte) + sum(
            1 for c in self.chunks for r in c.ergebnisse if r.status == ops.STATUS_KONFLIKT) + sum(
            1 for u in self.uebernahmen if u.ergebnis.status == ops.STATUS_KONFLIKT)

    @property
    def anzahl_angewendet(self) -> int:
        return sum(1 for c in self.chunks for r in c.ergebnisse if r.status == ops.STATUS_ANGEWENDET) + sum(
            1 for u in self.uebernahmen if u.ergebnis.status == ops.STATUS_ANGEWENDET)


# --------------------------------------------------------------------------- Pfade

SPRACHEN = ("en", "de")


def lektor_schluessel(buch: str, ziel: dict | None = None) -> str:
    """Schlüssel des Lektor-Ordners: `ziel["lektor"]`, wenn der Eintrag ihn nennt (O'Neil, Piano:
    Lektor-Ordner heißt anders als das Bibliotheksbuch), sonst `buch`. ValueError bei unsicherem Schlüssel."""
    if isinstance(ziel, dict) and "lektor" in ziel:
        try:
            return protokoll.pruefe_schluessel(ziel["lektor"])
        except ValueError as exc:
            raise ValueError(f"Lektor-Schlüssel ungültig: {exc}") from None
    return buch


def chunk_sprache(ziel: dict | None) -> str | None:
    """`ziel["sprache"]` (nur `en`/`de`), `None` wenn der Eintrag keine nennt; sonst ValueError."""
    if isinstance(ziel, dict) and "sprache" in ziel:
        s = ziel["sprache"]
        if isinstance(s, str) and s in SPRACHEN:
            return s
        raise ValueError(f"Sprache ungültig: {s!r} (erlaubt: en, de)")
    return None


def lektor_ordner(root: Path, buch: str, ziel: dict | None = None) -> Path:
    protokoll.eingang_ordner(root, buch)      # prüft den Schlüssel (ValueError)
    autor, titel = lektor_schluessel(buch, ziel).split("/")
    return Path(root) / "rohdaten" / "Lektor" / autor / titel


def quellsprache(lektor: Path) -> str:
    try:
        meta = json.loads((lektor / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "en"
    return "de" if isinstance(meta, dict) and meta.get("quellsprache") == "de" else "en"


def chunk_datei(root: Path, buch: str, chunk: int, ziel: dict | None = None) -> Path:
    lektor = lektor_ordner(root, buch, ziel)
    return lektor / (chunk_sprache(ziel) or quellsprache(lektor)) / f"chunk_{chunk:03d}.md"


def en_chunks_datei(root: Path, buch: str, chunk: int, ziel: dict | None = None) -> Path:
    autor, titel = lektor_schluessel(buch, ziel).split("/")
    return Path(root) / "rohdaten" / "en-chunks" / autor / titel / f"chunk_{chunk:03d}.md"


# --------------------------------------------------------------------------- Dateien

def _lies_text(pfad: Path) -> str:
    return pfad.read_bytes().decode("utf-8")       # Zeilenenden bleiben unverändert


def _schreibe_text(pfad: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=pfad.parent, prefix=pfad.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(text.encode("utf-8"))
        os.replace(tmp, pfad)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def lade_lektor_redaktion(lektor: Path) -> dict:
    """`redaktion.json` des Buchs. Fehlt sie, leere Struktur; existiert sie, aber ist sie nicht
    lesbar oder falsch aufgebaut, ValueError (sie wird dann nie überschrieben)."""
    pfad = lektor / "redaktion.json"
    if not pfad.exists():
        return {"eintraege": [], "chunks": {}}
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("redaktion.json unlesbar") from None
    if (not isinstance(daten, dict) or not isinstance(daten.get("chunks", {}), dict)
            or not isinstance(daten.get("eintraege", []), list)):
        raise ValueError("redaktion.json unlesbar (falscher Aufbau)")
    daten.setdefault("chunks", {})
    daten.setdefault("eintraege", [])
    return daten


def _jetzt() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- Eingangsdatei

def lade_eingangsdatei(datei: Path) -> tuple[str, str, list[dict]]:
    """Liest die App-Sicherungsdatei; wirft ValueError mit verständlicher Meldung."""
    try:
        daten = json.loads(Path(datei).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Datei nicht lesbar: {datei} ({exc.strerror or exc})") from None
    except ValueError:
        raise ValueError(f"Keine gültige JSON-Datei: {datei}") from None
    if not isinstance(daten, dict):
        raise ValueError("Erwartet ein Objekt mit geraet, buch und eintraege")
    geraet, buch, eintraege = daten.get("geraet"), daten.get("buch"), daten.get("eintraege")
    if not isinstance(geraet, str) or not geraet:
        raise ValueError("Feld „geraet“ fehlt oder ist kein Text")
    if not isinstance(eintraege, list):
        raise ValueError("Feld „eintraege“ fehlt oder ist keine Liste")
    try:
        protokoll.eingang_ordner(Path("."), buch)
    except ValueError as exc:
        raise ValueError(f"Feld „buch“ ungültig: {exc}") from None
    return geraet, buch, eintraege


# --------------------------------------------------------------------------- Planung

def _chunk_nummer(eintrag: dict) -> int | None:
    ziel = eintrag.get("ziel")
    n = ziel.get("chunk") if isinstance(ziel, dict) else None
    return n if isinstance(n, int) and not isinstance(n, bool) and n >= 0 else None


def _pruefe_ruecknahme(e: dict, stand: dict) -> EintragErgebnis:
    """Eine Rücknahme wirkt nur, solange das Ziel nicht angewendet ist (Spec 5.1). Das Ziel selbst
    wird in `ops.ohne_zurueckgenommene` aus der Planung genommen, egal in welcher Reihenfolge die
    Einträge eintrafen."""
    p = e.get("parameter")
    ziel_id = p.get("id") if isinstance(p, dict) else None
    s = stand.get(ziel_id) if isinstance(ziel_id, str) else None
    if isinstance(s, dict) and s.get("status") == "angewendet":
        return EintragErgebnis(e, ops.STATUS_KONFLIKT,
                               f"Rücknahme nicht möglich: Eintrag {ziel_id} ist schon angewendet")
    return EintragErgebnis(e, ops.STATUS_UEBERSPRUNGEN, f"Rücknahme von Eintrag {ziel_id}: wird nicht angewendet")


def _plane_uebernahme(lektor: Path, e: dict) -> UebernahmePlan | EintragErgebnis:
    """Prüft einen Eintrag `uebersetzung-uebernehmen` (liest nur). Ohne Chunk-Nummer: EintragErgebnis
    (Konflikt ohne Chunk-Zuordnung). Sonst ein Plan, dessen Ergebnis angewendet oder konflikt ist.
    Übernommen wird nur, was die Person im Vergleich gesehen hat: `vorher.hash` = Prüfsumme der
    Übersetzung, `parameter.neu_hash` = Prüfsumme des Vorschlags. Stimmt eines nicht mehr, Konflikt."""
    n = _chunk_nummer(e)
    if n is None:
        return EintragErgebnis(e, ops.STATUS_KONFLIKT, "Chunk-Nummer fehlt im Eintrag")
    datei = lektor / "de" / f"chunk_{n:03d}.md"
    neu_datei = datei.with_name(datei.name + ".neu")

    def konflikt(grund: str, alt: str = "", neu: str = "") -> UebernahmePlan:
        return UebernahmePlan(n, datei, neu_datei, alt, neu, EintragErgebnis(e, ops.STATUS_KONFLIKT, grund))

    if quellsprache(lektor) == "de":
        return konflikt("Quelle ist deutsch: es gibt keine Übersetzung zu übernehmen")
    try:
        neu = _lies_text(neu_datei)
    except FileNotFoundError:
        # Wiederholung nach Teilausfall: Übernahme wurde geschrieben (.neu schon gelöscht), nur der Stand fehlt noch
        p = e.get("parameter")
        neu_hash = p.get("neu_hash") if isinstance(p, dict) else None
        try:
            jetzt = _lies_text(datei)
        except (OSError, UnicodeDecodeError):
            jetzt = None
        if isinstance(neu_hash, str) and neu_hash and jetzt is not None and ops.pruefsumme(jetzt) == neu_hash:
            return UebernahmePlan(n, datei, neu_datei, jetzt, jetzt, EintragErgebnis(e, ops.STATUS_ANGEWENDET),
                                  bereits=True)
        return konflikt("Kein Vorschlag (.neu) vorhanden - bitte neu übersetzen")
    except (OSError, UnicodeDecodeError) as exc:
        return konflikt(f"Vorschlag (.neu) nicht lesbar ({type(exc).__name__})")
    try:
        alt = _lies_text(datei)
    except FileNotFoundError:
        alt = ""
    except (OSError, UnicodeDecodeError) as exc:
        return konflikt(f"Übersetzung nicht lesbar ({type(exc).__name__})", "", neu)
    p = e.get("parameter")
    neu_hash = p.get("neu_hash") if isinstance(p, dict) else None
    if (isinstance(neu_hash, str) and neu_hash and ops.pruefsumme(neu) == neu_hash
            and ops.pruefsumme(alt) == neu_hash):
        # Abbruch zwischen Schreiben und Löschen von .neu: die Übersetzung IST schon der Vorschlag
        return UebernahmePlan(n, datei, neu_datei, alt, neu, EintragErgebnis(e, ops.STATUS_ANGEWENDET),
                              bereits=True)
    vorher = e.get("vorher")
    erwartet = vorher.get("hash") if isinstance(vorher, dict) else None
    if not isinstance(erwartet, str) or not erwartet:
        return konflikt("vorher fehlt", alt, neu)
    if not isinstance(neu_hash, str) or not neu_hash:
        return konflikt("parameter.neu_hash fehlt", alt, neu)
    if erwartet != ops.pruefsumme(alt):
        return konflikt("Die Übersetzung hat sich seit dem Vergleich geändert (vorher stimmt nicht mehr)", alt, neu)
    if neu_hash != ops.pruefsumme(neu):
        return konflikt("Der Vorschlag wurde seit dem Vergleich ersetzt (neu_hash stimmt nicht mehr)", alt, neu)
    if not neu.strip():
        return konflikt("Der Vorschlag ist leer", alt, neu)
    return UebernahmePlan(n, datei, neu_datei, alt, neu, EintragErgebnis(e, ops.STATUS_ANGEWENDET))


def _plane_buch(root: Path, buch: str) -> BuchPlan:
    plan = BuchPlan(buch=buch)
    roh = protokoll.lade_eingang(root, buch)
    stand = protokoll.lade_stand(root, buch)
    # Einträge kommen von Geräten: ohne Objekt/Text-id werden sie gemeldet, nie verarbeitet.
    for e in roh:
        if not isinstance(e, dict) or not isinstance(e.get("id"), str) or not e["id"]:
            plan.konflikte.append(EintragErgebnis(e if isinstance(e, dict) else {"art": "?"},
                                                  ops.STATUS_KONFLIKT, "Eintrag ohne id"))
    gueltig = [e for e in roh if isinstance(e, dict) and isinstance(e.get("id"), str) and e["id"]]
    for e in gueltig:
        if e.get("art") == "ruecknahme":
            plan.ruecknahmen.append(_pruefe_ruecknahme(e, stand))
    eintraege = ops.ohne_zurueckgenommene(gueltig)

    offen: list[dict] = []
    uebernahmen: list[dict] = []
    for e in eintraege:
        ist_uebernahme = e.get("art") == ART_UEBERNEHMEN
        if e.get("ebene") != EBENE_CHUNK and not ist_uebernahme:
            plan.uebersprungen.append((e, f"übersprungen (Ebene {e.get('ebene')})"))
            continue
        s = stand.get(e["id"])
        status = s.get("status") if isinstance(s, dict) else "gesendet"
        if status in OFFENE_STAENDE:
            (uebernahmen if ist_uebernahme else offen).append(e)
    if not offen and not uebernahmen:
        return plan

    # Ziel je Eintrag prüfen (Lektor-Schlüssel, Sprache); ein Lauf bearbeitet je Buch einen Lektor-Ordner.
    ziele: dict[str, tuple[str, str | None]] = {}
    brauchbar: list[dict] = []
    for e in offen + uebernahmen:
        z = e.get("ziel") if isinstance(e.get("ziel"), dict) else {}
        try:
            ziele[e["id"]] = (lektor_schluessel(buch, z), chunk_sprache(z))
        except ValueError as exc:
            plan.konflikte.append(EintragErgebnis(e, ops.STATUS_KONFLIKT, str(exc)))
        else:
            brauchbar.append(e)
    offen = [e for e in offen if e in brauchbar]
    uebernahmen = [e for e in uebernahmen if e in brauchbar]
    if not offen and not uebernahmen:
        return plan
    erster = ziele[(offen + uebernahmen)[0]["id"]][0]
    plan.lektor_key = erster
    for e in list(offen + uebernahmen):
        if ziele[e["id"]][0] != erster:
            plan.konflikte.append(EintragErgebnis(
                e, ops.STATUS_KONFLIKT, f"uneinheitliches Ziel: Lektor-Ordner {ziele[e['id']][0]!r}, "
                                        f"in diesem Lauf wird {erster!r} bearbeitet"))
            offen = [x for x in offen if x is not e]
            uebernahmen = [x for x in uebernahmen if x is not e]
    lektor = lektor_ordner(root, buch, {"lektor": erster})
    plan.lektor = lektor
    if not lektor.is_dir():
        plan.konflikte += [EintragErgebnis(e, ops.STATUS_KONFLIKT, "Lektor-Ordner fehlt") for e in offen + uebernahmen]
        return plan
    try:
        red_lektor = lade_lektor_redaktion(lektor)
    except ValueError as exc:
        plan.konflikte += [EintragErgebnis(e, ops.STATUS_KONFLIKT, str(exc)) for e in offen + uebernahmen]
        return plan

    # Schon in redaktion.json vermerkt = bereits geschrieben, nur der Stand fehlt (Abbruch dazwischen):
    # nur noch als angewendet nachtragen, nie erneut planen (sonst doppelt angewendet oder Scheinkonflikt).
    vermerkt = {x.get("id") for x in red_lektor["eintraege"] if isinstance(x, dict)}
    for e in [x for x in offen + uebernahmen if x["id"] in vermerkt]:
        n = _chunk_nummer(e)
        n = n if n is not None else 0
        plan.chunks.append(ChunkPlan(n, chunk_datei(root, buch, n, e.get("ziel")), "", "",
                                     [EintragErgebnis(e, ops.STATUS_ANGEWENDET)], ziele[e["id"]][1] or ""))
    offen = [e for e in offen if e["id"] not in vermerkt]
    uebernahmen = [e for e in uebernahmen if e["id"] not in vermerkt]

    for e in uebernahmen:
        u = _plane_uebernahme(lektor, e)
        if isinstance(u, EintragErgebnis):
            plan.konflikte.append(u)
        else:
            plan.uebernahmen.append(u)

    je_chunk: dict[int, list[dict]] = {}
    for e in offen:
        n = _chunk_nummer(e)
        if n is None:
            plan.konflikte.append(EintragErgebnis(e, ops.STATUS_KONFLIKT, "Chunk-Nummer fehlt im Eintrag"))
        else:
            je_chunk.setdefault(n, []).append(e)

    for n in sorted(je_chunk):
        sprachen = [ziele[e["id"]][1] for e in je_chunk[n]]
        sprache = sprachen[0]
        for e, s_e in zip(list(je_chunk[n]), sprachen):
            if s_e != sprache:
                plan.konflikte.append(EintragErgebnis(
                    e, ops.STATUS_KONFLIKT, f"uneinheitliches Ziel: Chunk {n:03d} mit Sprache {s_e!r} statt {sprache!r}"))
                je_chunk[n].remove(e)
        zeig = {"lektor": erster, **({"sprache": sprache} if sprache else {})}
        datei = chunk_datei(root, buch, n, zeig)
        try:
            alt = _lies_text(datei)
        except (OSError, UnicodeDecodeError) as exc:
            grund = "Chunk-Datei fehlt" if isinstance(exc, FileNotFoundError) else f"Chunk-Datei nicht lesbar ({type(exc).__name__})"
            plan.chunks.append(ChunkPlan(n, datei, "", "", [
                EintragErgebnis(e, ops.STATUS_KONFLIKT, grund) for e in je_chunk[n]], datei.parent.name))
            continue
        neu, ergebnisse = ops.spiele_ab(alt, je_chunk[n])
        plan.chunks.append(ChunkPlan(n, datei, alt, neu, [
            EintragErgebnis(e, r.status, r.grund) for e, r in zip(je_chunk[n], ergebnisse)], datei.parent.name))
    return plan


def plane(root: Path, buch: str | None = None, eingang_datei: Path | None = None) -> list[BuchPlan]:
    """Reine Planung (liest nur). Einzige Ausnahme: `eingang_datei` wird zuvor im Eingang abgelegt.
    Wirft ValueError bei ungültiger `eingang_datei`."""
    root = Path(root)
    if eingang_datei is not None:
        geraet, buch, eintraege = lade_eingangsdatei(eingang_datei)
        protokoll.schreibe_eingang(root, geraet, buch, eintraege)
    buecher = [buch] if buch is not None else protokoll.liste_buecher(root)
    plaene: list[BuchPlan] = []
    for b in buecher:
        try:
            p = _plane_buch(root, b)
        except ValueError:
            plaene.append(BuchPlan(buch=b, hinweis="ungültiger Ordnername, übersprungen"))
            continue
        if p.chunks or p.uebernahmen or p.konflikte or p.uebersprungen or p.ruecknahmen:
            plaene.append(p)
    return plaene


# --------------------------------------------------------------------------- Ausführung

def _setze_stand_sicher(root: Path, buch: str, eintrag: dict, status: str, grund: str) -> None:
    eid = eintrag.get("id")
    if isinstance(eid, str) and eid:
        protokoll.setze_stand(root, buch, eid, status, grund)


def _fuehre_chunk_aus(root: Path, plan: BuchPlan, cp: ChunkPlan, zaehler: dict,
                      warnungen: list[str]) -> None:
    """Reihenfolge (Absicht: nach einem Abbruch bleibt nie eine Änderung ohne Spur):
    1. Drift-Prüfung; 2. redaktion.json lesen und `hash_original` festhalten (VOR der Änderung;
    ein Hash ohne Änderung ist harmlos); 3. Backup; 4. Chunk atomar schreiben (ab hier ist der
    Chunk geändert); 5. Spiegel in en-chunks; 6. Einträge in redaktion.json; 7. Stand.
    Scheitert ein Schritt bis 3 oder 4, ist nichts geändert und der Stand bleibt `gesendet`
    (Wiederholung möglich). Scheitern 5 oder 6 danach, wird weitergemacht (Stand) und gewarnt."""
    buch, lektor = plan.buch, plan.lektor
    angewendet = [r for r in cp.ergebnisse if r.status == ops.STATUS_ANGEWENDET]
    geschrieben = False

    if cp.geaendert:
        try:
            aktuell = _lies_text(cp.datei)
        except (OSError, UnicodeDecodeError):
            aktuell = None
        if aktuell != cp.alt:
            for r in angewendet:
                r.status, r.grund = ops.STATUS_KONFLIKT, "Chunk hat sich seit der Planung geändert"
            angewendet = []
        else:
            pfad = lektor / "redaktion.json"
            try:
                red = lade_lektor_redaktion(lektor)
                vorhanden = red["chunks"].get(str(cp.chunk))
                hash_alt = vorhanden.get("hash_original") if isinstance(vorhanden, dict) else None
                red["chunks"][str(cp.chunk)] = {
                    "hash_original": hash_alt or ops.pruefsumme(cp.alt), "zuletzt": _jetzt()}
                protokoll.speichere_redaktion(pfad, red)
                backup_before_write(lektor, cp.datei)
                _schreibe_text(cp.datei, cp.neu)
                geschrieben = True
            except Exception as exc:  # noqa: BLE001 - ein Chunk darf die anderen nicht abbrechen
                warnungen.append(f"WARNUNG: Chunk {cp.chunk:03d} von {buch} nicht geschrieben, "
                                 f"nichts geändert: {type(exc).__name__}: {exc}")
                for r in angewendet:
                    r.status, r.grund = ops.STATUS_KONFLIKT, f"nicht geschrieben ({type(exc).__name__})"
                return

    if geschrieben:
        if cp.sprache == "en":
            spiegel = en_chunks_datei(root, buch, cp.chunk, {"lektor": plan.lektor_key})
            try:
                if spiegel.is_file():
                    backup_before_write(lektor, spiegel)
                    _schreibe_text(spiegel, cp.neu)
            except Exception as exc:  # noqa: BLE001
                warnungen.append(f"WARNUNG: Chunk {cp.chunk:03d} von {buch} ist geändert, aber die Kopie "
                                 f"in en-chunks konnte nicht geschrieben werden: {type(exc).__name__}: {exc}")
        try:
            red = lade_lektor_redaktion(lektor)
            ids = {x.get("id") for x in red["eintraege"] if isinstance(x, dict)}
            for r in angewendet:
                if r.eintrag["id"] not in ids:
                    red["eintraege"].append({**r.eintrag, "status": ops.STATUS_ANGEWENDET})
            protokoll.speichere_redaktion(lektor / "redaktion.json", red)
        except Exception as exc:  # noqa: BLE001
            warnungen.append(f"WARNUNG: Chunk {cp.chunk:03d} von {buch} ist geändert, aber die Einträge "
                             f"konnten nicht in redaktion.json vermerkt werden: {type(exc).__name__}: {exc}")

    for r in cp.ergebnisse:
        try:
            if r.status == ops.STATUS_ANGEWENDET:
                _setze_stand_sicher(root, buch, r.eintrag, "angewendet", "")
                zaehler["angewendet"] += 1
            elif r.status == ops.STATUS_KONFLIKT:
                _setze_stand_sicher(root, buch, r.eintrag, "konflikt", r.grund)
                zaehler["konflikte"] += 1
        except Exception as exc:  # noqa: BLE001
            warnungen.append(f"WARNUNG: Stand für Eintrag {r.eintrag.get('id')} nicht gesetzt: "
                             f"{type(exc).__name__}: {exc}")


def _fuehre_uebernahme_aus(root: Path, plan: BuchPlan, u: UebernahmePlan, zaehler: dict,
                           warnungen: list[str]) -> None:
    """Reihenfolge: 1. Drift-Prüfung (de-Chunk und Vorschlag unverändert seit der Planung);
    2. Backup der bisherigen Übersetzung; 3. de-Chunk atomar ersetzen (ab hier ist er geändert);
    4. `.neu` löschen; 5. Eintrag in redaktion.json; 6. Stand. Scheitert 2 oder 3, ist nichts
    geändert und der Stand bleibt `gesendet` (Wiederholung möglich)."""
    buch, lektor, r = plan.buch, plan.lektor, u.ergebnis
    if r.status == ops.STATUS_ANGEWENDET and u.bereits:
        try:
            unveraendert = _lies_text(u.datei) == u.alt and (
                not u.neu_datei.exists() or _lies_text(u.neu_datei) == u.alt)
        except (OSError, UnicodeDecodeError):
            unveraendert = False
        if not unveraendert:
            r.status, r.grund = ops.STATUS_KONFLIKT, "Übersetzung hat sich seit der Planung geändert"
        else:
            if u.neu_datei.exists():          # kein zweites Backup, nur den übrigen Vorschlag entfernen
                try:
                    u.neu_datei.unlink()
                except OSError as exc:
                    warnungen.append(f"WARNUNG: Chunk {u.chunk:03d} von {buch}: Übersetzung ist übernommen, aber "
                                     f"{u.neu_datei.name} konnte nicht gelöscht werden: {type(exc).__name__}: {exc}")
            try:
                red = lade_lektor_redaktion(lektor)
                if r.eintrag["id"] not in {x.get("id") for x in red["eintraege"] if isinstance(x, dict)}:
                    red["eintraege"].append({**r.eintrag, "status": ops.STATUS_ANGEWENDET})
                    protokoll.speichere_redaktion(lektor / "redaktion.json", red)
            except Exception as exc:  # noqa: BLE001
                warnungen.append(f"WARNUNG: Chunk {u.chunk:03d} von {buch}: Eintrag nicht in redaktion.json vermerkt: "
                                 f"{type(exc).__name__}: {exc}")
    elif r.status == ops.STATUS_ANGEWENDET:
        try:
            alt_jetzt = _lies_text(u.datei) if u.datei.exists() else ""
            neu_jetzt = _lies_text(u.neu_datei)
        except (OSError, UnicodeDecodeError):
            alt_jetzt = neu_jetzt = None
        if alt_jetzt != u.alt or neu_jetzt != u.neu:
            r.status, r.grund = ops.STATUS_KONFLIKT, "Übersetzung oder Vorschlag hat sich seit der Planung geändert"
        else:
            try:
                u.datei.parent.mkdir(parents=True, exist_ok=True)
                backup_before_write(lektor, u.datei)
                _schreibe_text(u.datei, u.neu)
            except Exception as exc:  # noqa: BLE001 - nichts geändert, Stand bleibt gesendet
                warnungen.append(f"WARNUNG: Übersetzung Chunk {u.chunk:03d} von {buch} nicht geschrieben, "
                                 f"nichts geändert: {type(exc).__name__}: {exc}")
                r.status, r.grund = ops.STATUS_KONFLIKT, f"nicht geschrieben ({type(exc).__name__})"
                return
            try:
                u.neu_datei.unlink()
            except OSError as exc:
                warnungen.append(f"WARNUNG: Chunk {u.chunk:03d} von {buch}: Übersetzung ist übernommen, aber "
                                 f"{u.neu_datei.name} konnte nicht gelöscht werden: {type(exc).__name__}: {exc}")
            try:
                red = lade_lektor_redaktion(lektor)
                if r.eintrag["id"] not in {x.get("id") for x in red["eintraege"] if isinstance(x, dict)}:
                    red["eintraege"].append({**r.eintrag, "status": ops.STATUS_ANGEWENDET})
                protokoll.speichere_redaktion(lektor / "redaktion.json", red)
            except Exception as exc:  # noqa: BLE001
                warnungen.append(f"WARNUNG: Chunk {u.chunk:03d} von {buch}: Übersetzung ist übernommen, aber der "
                                 f"Eintrag konnte nicht in redaktion.json vermerkt werden: {type(exc).__name__}: {exc}")
    try:
        if r.status == ops.STATUS_ANGEWENDET:
            _setze_stand_sicher(root, buch, r.eintrag, "angewendet", "")
            zaehler["angewendet"] += 1
        else:
            _setze_stand_sicher(root, buch, r.eintrag, "konflikt", r.grund)
            zaehler["konflikte"] += 1
    except Exception as exc:  # noqa: BLE001
        warnungen.append(f"WARNUNG: Stand für Eintrag {r.eintrag.get('id')} nicht gesetzt: "
                         f"{type(exc).__name__}: {exc}")


def fuehre_aus(root: Path, plaene: list[BuchPlan]) -> dict:
    """Schreibt die geplanten Änderungen (Backup zuerst). Konflikte bekommen Stand `konflikt`.
    Rückgabe: {"angewendet", "konflikte", "warnungen": [Text]}; die Konflikte schließen
    solche ein, die erst beim Ausführen entstehen (Chunk inzwischen geändert)."""
    root = Path(root)
    zaehler: dict = {"angewendet": 0, "konflikte": 0}
    warnungen: list[str] = []
    for plan in plaene:
        if plan.hinweis:
            continue
        for r in plan.konflikte:
            try:
                _setze_stand_sicher(root, plan.buch, r.eintrag, "konflikt", r.grund)
            except Exception as exc:  # noqa: BLE001
                warnungen.append(f"WARNUNG: Stand nicht gesetzt: {type(exc).__name__}: {exc}")
            zaehler["konflikte"] += 1
        for r in plan.ruecknahmen:
            try:
                _setze_stand_sicher(root, plan.buch, r.eintrag, r.status, r.grund)
            except Exception as exc:  # noqa: BLE001
                warnungen.append(f"WARNUNG: Stand nicht gesetzt: {type(exc).__name__}: {exc}")
        for cp in plan.chunks:
            _fuehre_chunk_aus(root, plan, cp, zaehler, warnungen)
        for u in plan.uebernahmen:
            _fuehre_uebernahme_aus(root, plan, u, zaehler, warnungen)
    zaehler["warnungen"] = warnungen
    return zaehler


# --------------------------------------------------------------------------- Ausgabe / CLI

def _kurz(eintrag: dict) -> str:
    if eintrag.get("art") == ART_UEBERNEHMEN:
        n = _chunk_nummer(eintrag)
        return "Übersetzung übernehmen" + (f" (Chunk {n:03d})" if n is not None else "")
    ziel = eintrag.get("ziel")
    anfang = ziel.get("anfang") if isinstance(ziel, dict) else None
    anfang = anfang if isinstance(anfang, str) else "?"
    return f"{eintrag.get('art', '?')} »{anfang[:30]}{'…' if len(anfang) > 30 else ''}«"


def _bericht(plaene: list[BuchPlan], ausfuehren: bool) -> list[str]:
    zeilen: list[str] = []
    verb = "angewendet" if ausfuehren else "würde angewendet"
    n_ok = n_konf = n_uebersp = n_unmoeglich = n_buecher_ungueltig = 0
    for p in plaene:
        zeilen.append(f"Buch: {p.buch}")
        if p.hinweis:
            zeilen.append(f"  {p.hinweis}")
            n_buecher_ungueltig += 1
            continue
        for c in p.chunks:
            for r in c.ergebnisse:
                if r.status == ops.STATUS_ANGEWENDET:
                    n_ok += 1
                    zeilen.append(f"  Chunk {c.chunk:03d}: {_kurz(r.eintrag)} – {verb}")
                elif r.status == ops.STATUS_KONFLIKT:
                    n_konf += 1
                    zeilen.append(f"  Chunk {c.chunk:03d}: {_kurz(r.eintrag)} – Konflikt: {r.grund}")
                else:
                    n_uebersp += 1
                    zeilen.append(f"  Chunk {c.chunk:03d}: {_kurz(r.eintrag)} – übersprungen ({r.grund})")
        for u in p.uebernahmen:
            r = u.ergebnis
            if r.status == ops.STATUS_ANGEWENDET:
                n_ok += 1
                zeilen.append(f"  Chunk {u.chunk:03d}: {_kurz(r.eintrag)} – {verb}")
            else:
                n_konf += 1
                zeilen.append(f"  Chunk {u.chunk:03d}: {_kurz(r.eintrag)} – Konflikt: {r.grund}")
        for r in p.konflikte:
            n_konf += 1
            zeilen.append(f"  {_kurz(r.eintrag)} – Konflikt: {r.grund}")
        for e, grund in p.uebersprungen:
            n_uebersp += 1
            zeilen.append(f"  {_kurz(e)} – {grund}")
        for r in p.ruecknahmen:
            if r.status == ops.STATUS_KONFLIKT:
                n_unmoeglich += 1
            else:
                n_uebersp += 1
            zeilen.append(f"  {_kurz(r.eintrag)} – {r.grund}")
    teile = [f"{n_ok} {'angewendet' if ausfuehren else 'anzuwenden'}", f"{n_konf} Konflikte",
             f"{n_uebersp} übersprungen"]
    if n_unmoeglich:
        teile.append(f"{n_unmoeglich} Rücknahmen nicht möglich")
    if n_buecher_ungueltig:
        teile.append(f"{n_buecher_ungueltig} Ordner mit ungültigem Namen")
    zeilen.append("Zusammenfassung: " + ", ".join(teile) + ("" if ausfuehren else " (Dry-Run, nichts geschrieben)"))
    return zeilen


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Redaktionsänderungen (Ebene Original-Chunk) am PC einarbeiten.",
        epilog="Exit-Codes: 0 in Ordnung (auch bei Rücknahmen \"nicht möglich\"), 1 ungültige Eingabe, "
               "2 Konflikt, 3 nur Warnungen.")
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent,
                    help="Bibliothekswurzel (Standard: Elternordner von tools)")
    ap.add_argument("--buch", help='nur dieses Buch ("Autor/Titel")')
    ap.add_argument("--eingang", type=Path, help="Sicherungsdatei der App einlesen und im Eingang ablegen")
    ap.add_argument("--ausfuehren", action="store_true", help="wirklich schreiben (Standard: Dry-Run)")
    args = ap.parse_args(argv)

    try:
        plaene = plane(args.root, buch=args.buch, eingang_datei=args.eingang)
    except ValueError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    if args.buch is not None and args.eingang is None:
        try:
            protokoll.eingang_ordner(args.root, args.buch)
        except ValueError:
            print("Fehler: ungültiger Buchschlüssel", file=sys.stderr)
            return 1

    warnungen: list[str] = []
    if args.ausfuehren:
        warnungen = fuehre_aus(args.root, plaene)["warnungen"]
    # nach dem Ausführen neu zählen: der Plan enthält dann auch Konflikte, die erst dabei entstanden
    konflikte = sum(p.anzahl_konflikte for p in plaene)
    for zeile in _bericht(plaene, args.ausfuehren):
        print(zeile)
    for w in warnungen:
        print(w)
    if konflikte:
        return 2
    return 3 if warnungen else 0


if __name__ == "__main__":
    for strom in (sys.stdout, sys.stderr):
        try:
            strom.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
