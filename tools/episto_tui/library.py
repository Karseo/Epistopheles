from __future__ import annotations
import json
import os
import re
import dataclasses
import shutil
import sys
import unicodedata
import uuid
from pathlib import Path
from datetime import datetime
from collections.abc import Mapping
from episto_tui.models import Buch, Kapitel, Tag, Kommentar, Highlight
from episto_tui.backup import backup_before_write

DEFAULT_ROOT = Path(r"D:\Workspace\!Episto")

# Aufbau der Bibliothekswurzel:
#   <root>/reader/<Autor>/<Titel>/    fertige Daten fuer den Reader (quelle, notizen, kapitel.json, ...)
#   <root>/rohdaten/                  alles Rohe (Inbox, Lektor, Outbox, en-chunks), nicht synchronisiert
#   <root>/reader/export-epistopheles erzeugte Exporte fuer das Chromebook, kein Buch
READER_ORDNER = "reader"
ROHDATEN_ORDNER = "rohdaten"
EXPORT_ORDNER = "export-epistopheles"


def resolve_root(arg: str | None, env: Mapping[str, str], plattform: str | None = None) -> Path:
    """Wurzelordner der Bibliothek: --root, dann EPISTO_ROOT, sonst der
    Standard der Plattform (Windows: DEFAULT_ROOT, sonst ~/episto, so wie
    Syncthing ihn unter Termux anlegt). Leere Werte zaehlen als nicht gesetzt."""
    if arg:
        return Path(arg).expanduser()
    aus_umgebung = env.get("EPISTO_ROOT")
    if aus_umgebung:
        return Path(aus_umgebung).expanduser()
    if (plattform or sys.platform) == "win32":
        return DEFAULT_ROOT
    return Path.home() / "episto"


def _lade_json_dict(pfad: Path) -> dict | None:
    """Laedt eine JSON-Datei und gibt sie zurueck, wenn sie ein Objekt (dict)
    ist - sonst None (fehlende Datei, kaputtes JSON, oder valides JSON, das
    kein Objekt ist, z.B. eine blosse Liste oder Zahl)."""
    if not pfad.exists():
        return None
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return daten if isinstance(daten, dict) else None


def _dict_eintraege(daten: dict, schluessel: str) -> list[dict]:
    """Gibt daten[schluessel] als Liste zurueck, gefiltert auf dict-Eintraege.
    Ist der Wert gar keine Liste (z.B. ein Objekt oder eine Zahl aus einer
    kaputten Datei), ergibt das eine leere Liste statt eines Absturzes."""
    wert = daten.get(schluessel, [])
    if not isinstance(wert, list):
        return []
    return [eintrag for eintrag in wert if isinstance(eintrag, dict)]


def discover_books(root: Path) -> list[Buch]:
    buecher: list[Buch] = []
    autor_root = root / READER_ORDNER
    if not autor_root.is_dir():
        return buecher
    for autor_dir in sorted(autor_root.iterdir()):
        if not autor_dir.is_dir() or autor_dir.name == EXPORT_ORDNER or autor_dir.name[:1] in "._":
            continue                                   # Export-Ordner und Technisches sind keine Autoren
        for buch_dir in sorted(autor_dir.iterdir()):
            if not buch_dir.is_dir():
                continue
            if (buch_dir / "quelle").is_dir():
                buecher.append(Buch(autor=autor_dir.name, titel=buch_dir.name, pfad=buch_dir))
    return buecher


def list_chapters(buch: Buch) -> list[Kapitel]:
    index_pfad = buch.pfad / "quelle" / "_kapitel_index.json"
    if index_pfad.exists():
        try:
            eintraege = json.loads(index_pfad.read_text(encoding="utf-8"))
            return [Kapitel(nr=e["nr"], titel=e["titel"], datei=e["datei"]) for e in eintraege]
        except (json.JSONDecodeError, KeyError, TypeError, OSError):
            # kaputte Index-Datei -> Fallback auf Glob, nie Absturz. TypeError
            # deckt valides JSON mit falscher Form ab (Objekt statt Liste,
            # Zahlen/Strings statt Eintrags-Objekten).
            pass
    dateien = sorted(
        p for p in (buch.pfad / "quelle").glob("*.md")
        if not p.name.startswith("_") and ".sync-conflict-" not in p.name
    )
    return [Kapitel(nr=i, titel=p.stem, datei=p.name) for i, p in enumerate(dateien, start=1)]


def read_chapter_text(buch: Buch, dateiname: str) -> str:
    return (buch.pfad / "quelle" / dateiname).read_text(encoding="utf-8")


def write_chapter_text(buch: Buch, dateiname: str, text: str) -> None:
    pfad = buch.pfad / "quelle" / dateiname
    backup_before_write(buch.pfad, pfad)
    pfad.write_text(text, encoding="utf-8", newline="\n")


def _tags_pfad(buch: Buch) -> Path:
    return buch.pfad / "notizen" / "tags.json"


def read_tags(buch: Buch, dateiname: str) -> Tag | None:
    daten = _lade_json_dict(_tags_pfad(buch))
    if daten is None:
        return None
    for eintrag in _dict_eintraege(daten, "kapitel"):
        if eintrag.get("datei") == dateiname:
            return Tag.from_dict(eintrag)
    return None


def write_tag(buch: Buch, tag: Tag) -> None:
    pfad = _tags_pfad(buch)
    # Das Backup MUSS vor allem anderen laufen: Nur weil der bisherige Inhalt
    # hier gesichert ist, ist der Fallback unten (frisches Geruest, falls die
    # vorhandene Datei kein JSON-Objekt ist bzw. "kapitel" keine Liste) sicher
    # -- der Altinhalt bleibt in notizen\_backup erhalten und ist
    # wiederherstellbar, statt still verloren zu gehen.
    backup_before_write(buch.pfad, pfad)
    daten = _lade_json_dict(pfad)
    if daten is None:
        daten = {"werk": buch.titel, "autor": buch.autor, "sprache": "de", "kapitel": []}

    kapitel_liste = daten.get("kapitel", [])
    if not isinstance(kapitel_liste, list):
        kapitel_liste = []  # siehe Backup-Kommentar oben
    ersetzt = False
    for i, eintrag in enumerate(kapitel_liste):
        if isinstance(eintrag, dict) and eintrag.get("datei") == tag.datei:
            kapitel_liste[i] = tag.to_dict()
            ersetzt = True
            break
    if not ersetzt:
        kapitel_liste.append(tag.to_dict())

    daten["kapitel"] = kapitel_liste
    daten["eintraege"] = len(kapitel_liste)
    daten["erstellt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def read_all_tags(buch: Buch) -> list[Tag]:
    daten = _lade_json_dict(_tags_pfad(buch))
    if daten is None:
        return []
    return [Tag.from_dict(e) for e in _dict_eintraege(daten, "kapitel")]


def _parse_kapitel_heading(zeile: str) -> tuple[int, str] | None:
    """Erkennt Zeilen der Form '### Kapitel 3 · Abschnittstitel', wie sie
    tools\\straenge.ps1 erzeugt (Trennzeichen ist ein Mittelpunkt · 0x00B7,
    aber diese Funktion akzeptiert jedes einzelne Trennzeichen)."""
    praefix = "### Kapitel "
    if not zeile.startswith(praefix):
        return None
    rest = zeile[len(praefix):].strip()
    teile = rest.split(None, 1)
    if not teile or not teile[0].isdigit():
        return None
    nr = int(teile[0])
    abschnitt = teile[1].strip() if len(teile) > 1 else ""
    if abschnitt and not abschnitt[0].isalnum():
        abschnitt = abschnitt[1:].strip()
    return nr, abschnitt


def _parse_strang_datei(pfad: Path) -> tuple[str, list[dict]]:
    text = pfad.read_text(encoding="utf-8")
    name = pfad.stem
    if text.startswith("---"):
        ende = text.find("\n---", 3)
        if ende != -1:
            frontmatter = text[3:ende]
            for zeile in frontmatter.splitlines():
                if zeile.startswith("strang:"):
                    name = zeile.split(":", 1)[1].strip()
            text = text[ende + 4:]

    treffer: list[dict] = []
    aktuell: dict | None = None
    for zeile in text.splitlines():
        erkannt = _parse_kapitel_heading(zeile.strip())
        if erkannt is not None:
            if aktuell is not None:
                treffer.append(aktuell)
            nr, abschnitt = erkannt
            aktuell = {"nr": nr, "abschnitt": abschnitt, "inhalt": []}
        elif aktuell is not None:
            aktuell["inhalt"].append(zeile)
    if aktuell is not None:
        treffer.append(aktuell)
    for eintrag in treffer:
        eintrag["inhalt"] = "\n".join(eintrag["inhalt"]).strip()
    return name, treffer


def read_straenge_for_chapter(buch: Buch, kapitel_nr: int) -> list[dict]:
    ordner = buch.pfad / "notizen" / "straenge"
    ergebnisse: list[dict] = []
    if not ordner.is_dir():
        return ergebnisse
    for pfad in sorted(ordner.glob("*.md")):
        if ".sync-conflict-" in pfad.name:
            continue
        name, treffer = _parse_strang_datei(pfad)
        for eintrag in treffer:
            if eintrag["nr"] == kapitel_nr:
                ergebnisse.append({
                    "strang": name,
                    "abschnitt": eintrag["abschnitt"],
                    "inhalt": eintrag["inhalt"],
                })
    return ergebnisse


def read_querbezuege(buch: Buch) -> list[dict]:
    daten = _lade_json_dict(buch.pfad / "querbezuege" / "querbezuege.json")
    if daten is None:
        return []
    return _dict_eintraege(daten, "bezuege")


def _kommentare_pfad(buch: Buch) -> Path:
    return buch.pfad / "notizen" / "kommentare.json"


def read_kommentare(buch: Buch, dateiname: str) -> list[Kommentar]:
    daten = _lade_json_dict(_kommentare_pfad(buch))
    if daten is None:
        return []
    return [
        Kommentar.from_dict(eintrag)
        for eintrag in _dict_eintraege(daten, "kommentare")
        if eintrag.get("datei") == dateiname
    ]


def add_kommentar(buch: Buch, kommentar: Kommentar) -> None:
    pfad = _kommentare_pfad(buch)
    # Backup zuerst: macht den Frisch-Geruest-Fallback bei kaputter Datei sicher.
    backup_before_write(buch.pfad, pfad)
    daten = _lade_json_dict(pfad)
    if daten is None:
        daten = {"werk": buch.titel, "kommentare": []}
    if not isinstance(daten.get("kommentare"), list):
        daten["kommentare"] = []
    if not kommentar.id:
        # Am Objekt setzen, damit spaetere update/remove-Aufrufe mit genau
        # diesem Objekt den gespeicherten Eintrag ueber die Kennung finden.
        kommentar.id = uuid.uuid4().hex[:12]
    daten["kommentare"].append(kommentar.to_dict())
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def _finde_kommentar(eintraege: list, gesucht: Kommentar) -> int | None:
    """Index des gespeicherten Eintrags zu `gesucht`: ueber die Kennung, wenn
    `gesucht` eine hat, sonst (Altbestand ohne Kennung) ueber alle Felder."""
    ohne_id = dataclasses.replace(gesucht, id="")
    for i, eintrag in enumerate(eintraege):
        if not isinstance(eintrag, dict):
            continue
        gespeichert = Kommentar.from_dict(eintrag)
        if gesucht.id and gespeichert.id == gesucht.id:
            return i
        if not gesucht.id and dataclasses.replace(gespeichert, id="") == ohne_id:
            return i
    return None


def update_kommentar(buch: Buch, alt: Kommentar, neuer_text: str) -> None:
    pfad = _kommentare_pfad(buch)
    daten = _lade_json_dict(pfad)
    if daten is None or not isinstance(daten.get("kommentare"), list):
        return
    i = _finde_kommentar(daten["kommentare"], alt)
    if i is None:
        return
    backup_before_write(buch.pfad, pfad)
    daten["kommentare"][i] = dataclasses.replace(alt, text=neuer_text).to_dict()
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def remove_kommentar(buch: Buch, kommentar: Kommentar) -> None:
    pfad = _kommentare_pfad(buch)
    daten = _lade_json_dict(pfad)
    if daten is None or not isinstance(daten.get("kommentare"), list):
        return
    i = _finde_kommentar(daten["kommentare"], kommentar)
    if i is None:
        return
    backup_before_write(buch.pfad, pfad)
    del daten["kommentare"][i]
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def _highlights_pfad(buch: Buch) -> Path:
    return buch.pfad / "notizen" / "highlights.json"


def read_highlights(buch: Buch, dateiname: str) -> list[Highlight]:
    daten = _lade_json_dict(_highlights_pfad(buch))
    if daten is None:
        return []
    return [
        Highlight.from_dict(eintrag)
        for eintrag in _dict_eintraege(daten, "highlights")
        if eintrag.get("datei") == dateiname
    ]


def read_highlights_nach_farbe(buch: Buch, farbe: str) -> list[Highlight]:
    daten = _lade_json_dict(_highlights_pfad(buch))
    if daten is None:
        return []
    return [
        Highlight.from_dict(eintrag)
        for eintrag in _dict_eintraege(daten, "highlights")
        if eintrag.get("farbe") == farbe
    ]


def write_highlight(buch: Buch, highlight: Highlight) -> None:
    pfad = _highlights_pfad(buch)
    # Backup zuerst: macht den Frisch-Geruest-Fallback bei kaputter Datei sicher.
    backup_before_write(buch.pfad, pfad)
    daten = _lade_json_dict(pfad)
    if daten is None:
        daten = {"werk": buch.titel, "highlights": []}
    if not isinstance(daten.get("highlights"), list):
        daten["highlights"] = []
    eintraege = daten["highlights"]
    ersetzt = False
    for i, eintrag in enumerate(eintraege):
        if (
            isinstance(eintrag, dict)
            and eintrag.get("datei") == highlight.datei
            and eintrag.get("absatz_index") == highlight.absatz_index
        ):
            eintraege[i] = highlight.to_dict()
            ersetzt = True
            break
    if not ersetzt:
        eintraege.append(highlight.to_dict())
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def remove_highlight(buch: Buch, dateiname: str, absatz_index: int) -> None:
    pfad = _highlights_pfad(buch)
    daten = _lade_json_dict(pfad)
    if daten is None or not isinstance(daten.get("highlights"), list):
        return
    backup_before_write(buch.pfad, pfad)
    daten["highlights"] = [
        eintrag for eintrag in daten["highlights"]
        if not (
            isinstance(eintrag, dict)
            and eintrag.get("datei") == dateiname
            and eintrag.get("absatz_index") == absatz_index
        )
    ]
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


# --- Zusammenfuehren von Syncthing-Konfliktkopien -------------------------
#
# Aendern PC und Handy zwischen zwei Abgleichen dieselbe Notizdatei, behaelt
# Syncthing eine Fassung unter dem Originalnamen und legt die andere als
# "<name>.sync-conflict-<datum>-<id>.json" daneben. Die TUI las diese Kopien
# nie, die Notizen des anderen Geraets wirkten verloren. merge_konflikte()
# fuehrt sie beim Laden mit der Hauptdatei zusammen (nichts geht verloren, die
# Kopie wandert nach notizen\_backup).
#
# Regeln je Datei (die Hauptdatei ist die von Syncthing als neuer gewertete):
#   kommentare.json  Vereinigung; gleich ist, wer dieselbe Kennung hat (oder,
#                    ohne Kennung, dieselben Felder).
#   highlights.json  Vereinigung ueber (datei, absatz_index); bei zwei Farben
#                    am selben Absatz gewinnt die Hauptdatei.
#   tags.json        Vereinigung ueber `datei`; bei zwei Fassungen desselben
#                    Kapitels gewinnt die Hauptdatei.
# Grenze: Eine Vereinigung kennt keine Loeschungen - ein am einen Geraet
# geloeschter Kommentar kehrt zurueck, wenn ihn die Konfliktkopie noch enthaelt.

def _schreibe_json(pfad: Path, daten: dict) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def _kommentar_inhalt(eintrag: dict) -> tuple:
    k = Kommentar.from_dict(eintrag)
    return (k.datei, k.absatz_index, k.absatz_anfang, k.text, k.erstellt)


def _merge_kommentare(haupt: dict, fremd: dict) -> bool:
    if not isinstance(haupt.get("kommentare"), list):
        haupt["kommentare"] = []
    eigene = [e for e in haupt["kommentare"] if isinstance(e, dict)]
    ids = {str(e["id"]) for e in eigene if e.get("id")}
    inhalte = {_kommentar_inhalt(e) for e in eigene}
    neu = []
    for eintrag in _dict_eintraege(fremd, "kommentare"):
        if eintrag.get("id") and str(eintrag["id"]) in ids:
            continue
        if _kommentar_inhalt(eintrag) in inhalte:
            continue
        neu.append(eintrag)
        if eintrag.get("id"):
            ids.add(str(eintrag["id"]))
        inhalte.add(_kommentar_inhalt(eintrag))
    if not neu:
        return False
    haupt["kommentare"].extend(neu)
    # Stabil nach Erstellzeit, damit die Anzeige-Reihenfolge ("in
    # Erstellungsreihenfolge") nach dem Zusammenfuehren stimmt.
    haupt["kommentare"].sort(key=lambda e: str(e.get("erstellt", "")) if isinstance(e, dict) else "")
    return True


def _merge_highlights(haupt: dict, fremd: dict) -> bool:
    if not isinstance(haupt.get("highlights"), list):
        haupt["highlights"] = []
    belegt = {
        (e.get("datei"), e.get("absatz_index"))
        for e in haupt["highlights"] if isinstance(e, dict)
    }
    neu = [
        e for e in _dict_eintraege(fremd, "highlights")
        if (e.get("datei"), e.get("absatz_index")) not in belegt
    ]
    haupt["highlights"].extend(neu)
    return bool(neu)


def _merge_tags(haupt: dict, fremd: dict) -> bool:
    if not isinstance(haupt.get("kapitel"), list):
        haupt["kapitel"] = []
    belegt = {e.get("datei") for e in haupt["kapitel"] if isinstance(e, dict)}
    neu = [e for e in _dict_eintraege(fremd, "kapitel") if e.get("datei") not in belegt]
    haupt["kapitel"].extend(neu)
    if neu:
        haupt["eintraege"] = len(haupt["kapitel"])
    return bool(neu)


_MERGE_DATEIEN = (
    ("kommentare", _merge_kommentare),
    ("highlights", _merge_highlights),
    ("tags", _merge_tags),
)


def _verschiebe_in_backup(buch: Buch, datei: Path) -> None:
    ziel_ordner = buch.pfad / "notizen" / "_backup"
    ziel_ordner.mkdir(parents=True, exist_ok=True)
    ziel = ziel_ordner / datei.name
    zaehler = 1
    while ziel.exists():
        ziel = ziel_ordner / f"{datei.stem}-{zaehler}{datei.suffix}"
        zaehler += 1
    shutil.move(str(datei), str(ziel))


def merge_konflikte(buch: Buch) -> int:
    """Fuehrt Syncthing-Konfliktkopien von kommentare/highlights/tags.json mit
    der jeweiligen Hauptdatei zusammen und verschiebt die verarbeiteten Kopien
    nach notizen\\_backup. Unlesbare Kopien bleiben unberuehrt liegen. Gibt die
    Zahl der verarbeiteten Konfliktkopien zurueck."""
    notizen = buch.pfad / "notizen"
    if not notizen.is_dir():
        return 0
    verarbeitet = 0
    for stamm, merge in _MERGE_DATEIEN:
        kopien = sorted(notizen.glob(f"{stamm}.sync-conflict-*.json"))
        if not kopien:
            continue
        haupt_pfad = notizen / f"{stamm}.json"
        haupt = _lade_json_dict(haupt_pfad)
        geaendert = False
        lesbar: list[Path] = []
        for kopie in kopien:
            fremd = _lade_json_dict(kopie)
            if fremd is None:
                continue
            lesbar.append(kopie)
            if haupt is None:
                haupt, geaendert = fremd, True
            elif merge(haupt, fremd):
                geaendert = True
        if geaendert and haupt is not None:
            backup_before_write(buch.pfad, haupt_pfad)
            _schreibe_json(haupt_pfad, haupt)
        for kopie in lesbar:
            _verschiebe_in_backup(buch, kopie)
        verarbeitet += len(lesbar)
    return verarbeitet


def merge_alle_konflikte(root: Path) -> int:
    """merge_konflikte() fuer jedes Buch der Bibliothek (Start der TUI)."""
    return sum(merge_konflikte(buch) for buch in discover_books(root))


# --- Navigation ------------------------------------------------------------

def root_von(buch: Buch) -> Path:
    """Bibliothekswurzel zu einem Buch: <root>/reader/<Autor>/<Titel>."""
    return buch.pfad.parents[2]


def rohchunks_en_ordner(buch: Buch) -> Path:
    """Ordner mit den englischen Rohchunks (chunk_NNN.md) eines Buchs: <root>/rohdaten/en-chunks/<Autor>/<Titel>/.
    Sie liegen nicht mehr im Buchordner (der gehoert den fertigen Reader-Daten). Gibt es sie dort nicht,
    aber noch unter <Buch>/en/ (Stand vor dem Umbau), wird dieser Ordner genommen. Existiert keiner, kommt
    der neue Pfad zurueck (Aufrufer behandeln das fehlende Verzeichnis wie bisher)."""
    neu = root_von(buch) / ROHDATEN_ORDNER / "en-chunks" / buch.autor / buch.titel
    alt = buch.pfad / "en"
    if not neu.is_dir() and alt.is_dir():
        return alt
    return neu


def kapitel_nachbar(buch: Buch, kapitel: Kapitel, richtung: int) -> Kapitel | None:
    """Das Kapitel `richtung` Schritte (+1 weiter, -1 zurueck) nach `kapitel`
    in der Lesereihenfolge des Buchs; None am Anfang/Ende (oder wenn `kapitel`
    nicht mehr in der Liste steht)."""
    liste = list_chapters(buch)
    for i, k in enumerate(liste):
        if k.datei == kapitel.datei:
            j = i + richtung
            return liste[j] if 0 <= j < len(liste) else None
    return None


def _slug(text: str) -> str:
    text = text.lower()
    for a, b in (("\u00e4", "ae"), ("\u00f6", "oe"), ("\u00fc", "ue"), ("\u00df", "ss")):
        text = text.replace(a, b)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def finde_buch_fuer_ziel(buecher: list[Buch], ziel: str) -> Buch | None:
    """Loest das `ziel` eines Querverweises ("schumpeter_capitalism-socialism-
    and-democracy" = <Nachname>_<Titel-Slug>) auf ein Buch der Bibliothek auf.
    Gleicher Titel-Slug; bei mehreren Buechern mit demselben Titel entscheidet
    der Nachname. None, wenn das Werk nicht in der Bibliothek liegt (bei rund
    zwei Dritteln der Querverweise der Fall)."""
    if "_" not in ziel:
        return None
    nachname, titel_slug = (t.strip() for t in ziel.split("_", 1))
    treffer = [b for b in buecher if _slug(b.titel) == titel_slug]
    if len(treffer) > 1:
        gleicher_autor = [b for b in treffer if _slug(b.autor.split(",")[0]).startswith(nachname.split("-")[0])]
        treffer = gleicher_autor or treffer
    return treffer[0] if treffer else None


def read_straenge_uebersicht(buch: Buch, kapitel_nr: int) -> list[dict]:
    """Zu jedem Strang, der in Kapitel `kapitel_nr` vorkommt, die ANDEREN
    Kapitel desselben Buchs, in denen er vorkommt:
    [{"strang": name, "andere": [(nr, abschnitt), ...]}, ...]."""
    ordner = buch.pfad / "notizen" / "straenge"
    ergebnis: list[dict] = []
    if not ordner.is_dir():
        return ergebnis
    for pfad in sorted(ordner.glob("*.md")):
        if ".sync-conflict-" in pfad.name:
            continue
        name, treffer = _parse_strang_datei(pfad)
        if not any(t["nr"] == kapitel_nr for t in treffer):
            continue
        andere = sorted({(t["nr"], t["abschnitt"]) for t in treffer if t["nr"] != kapitel_nr})
        if andere:
            ergebnis.append({"strang": name, "andere": andere})
    return ergebnis


def list_straenge(buch: Buch) -> list[dict]:
    """Die Themen (Straenge) eines Werks: [{"name", "slug", "kapitel": [nr, ...]}, ...] in Dateireihenfolge.
    `slug` ist der Dateiname ohne Endung, `kapitel` die Nummern aller Fundstellen (aufsteigend, ohne Doppelte).
    Straenge ohne Fundstelle, Syncthing-Konfliktdateien und nicht lesbare Dateien entfallen; fehlt der Ordner,
    ist die Liste leer. Nur lesend (Grundlage der Verbindungsansicht, Spec 2026-11-03)."""
    ordner = buch.pfad / "notizen" / "straenge"
    ergebnis: list[dict] = []
    if not ordner.is_dir():
        return ergebnis
    for pfad in sorted(ordner.glob("*.md")):
        if ".sync-conflict-" in pfad.name:
            continue
        try:
            name, treffer = _parse_strang_datei(pfad)
        except (OSError, UnicodeDecodeError):
            continue
        nummern = sorted({t["nr"] for t in treffer})
        if nummern:
            ergebnis.append({"name": name, "slug": pfad.stem, "kapitel": nummern})
    return ergebnis


# --- Notizenliste ------------------------------------------------------------

def read_alle_kommentare(buch: Buch) -> list[Kommentar]:
    daten = _lade_json_dict(_kommentare_pfad(buch))
    if daten is None:
        return []
    return [Kommentar.from_dict(e) for e in _dict_eintraege(daten, "kommentare")]


def read_alle_highlights(buch: Buch) -> list[Highlight]:
    daten = _lade_json_dict(_highlights_pfad(buch))
    if daten is None:
        return []
    return [Highlight.from_dict(e) for e in _dict_eintraege(daten, "highlights")]


# --- Zustand dieses Geraets (nicht synchronisiert) ---------------------------
#
# Leseposition ist je Geraet verschieden (PC und Handy lesen an verschiedenen
# Stellen) und gehoert deshalb NICHT in die per Syncthing abgeglichene
# Bibliothek, sondern ins Benutzerverzeichnis.

def zustand_pfad() -> Path:
    aus_umgebung = os.environ.get("EPISTO_ZUSTAND")
    if aus_umgebung:
        return Path(aus_umgebung).expanduser()
    return Path.home() / ".episto_tui" / "zustand.json"


def lade_zustand() -> dict:
    daten = _lade_json_dict(zustand_pfad())
    return daten if daten is not None else {}


def speichere_zustand(zustand: dict) -> None:
    """Best effort: der Zustand ist Komfort, ein Schreibfehler (schreibgeschuetztes
    Home, volle Platte) darf die TUI nie stoeren."""
    try:
        pfad = zustand_pfad()
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(json.dumps(zustand, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    except OSError:
        pass


def buch_schluessel(buch: Buch) -> str:
    return f"{buch.autor}/{buch.titel}"


def speichere_leseposition(buch: Buch, kapitel: Kapitel, absatz_index: int | None) -> None:
    zustand = lade_zustand()
    zustand["zuletzt"] = {
        "buch": buch_schluessel(buch),
        "datei": kapitel.datei,
        "absatz": absatz_index or 0,
    }
    speichere_zustand(zustand)


def lade_leseposition(root: Path) -> tuple[Buch, Kapitel, int] | None:
    """Zuletzt gelesene Stelle, falls Buch und Kapitel noch existieren."""
    zuletzt = lade_zustand().get("zuletzt")
    if not isinstance(zuletzt, dict):
        return None
    for buch in discover_books(root):
        if buch_schluessel(buch) != zuletzt.get("buch"):
            continue
        for kapitel in list_chapters(buch):
            if kapitel.datei == zuletzt.get("datei"):
                absatz = zuletzt.get("absatz")
                return buch, kapitel, absatz if isinstance(absatz, int) and absatz >= 0 else 0
    return None
