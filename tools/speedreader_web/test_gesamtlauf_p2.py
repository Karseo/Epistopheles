"""Gesamtlauf P2 (Task 14), Ende zu Ende auf einer Testwurzel, ohne Eingriff in echte Daten:

  lektor-zu-episto (Urtext) -> Export -> App: Ursache suchen, Absatz bearbeiten, Absatz trennen, markieren
  -> Empfaenger (Eingang) -> redaktion_anwenden (Dry-Run, --ausfuehren, Backup, redaktion.json)
  -> neuer Export (`enthalten`) -> App zeigt den Text ohne doppeltes Anwenden
  -> lektor-zu-episto ohne --ueberschreiben bricht ab, mit --ueberschreiben: Backup + Nachspiel = derselbe Text
  -> Basis geaendert: Konflikt einzeln mit Grund im Bericht.
Ohne Playwright/Chromium uebersprungen."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
TOOLS = HIER.parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(TOOLS))

sync_api = pytest.importorskip("playwright.sync_api")

from test_werkzeugleiste import browser, knopf, waehle  # noqa: E402,F401
from test_neu_uebersetzen import Apic, neue_seite  # noqa: E402
from test_volltext import bearbeite, speichern, tippe, zu_text, text_im_feld  # noqa: E402

import export_korrektur  # noqa: E402
import redaktion_anwenden as ra  # noqa: E402
from episto_tui.korrektur import absatz_spannen  # noqa: E402
from redaktion import ops, protokoll, schutz  # noqa: E402
from redaktion.testwurzel import AUTOR, TITEL, baue_testwurzel  # noqa: E402

_SPEC = importlib.util.spec_from_file_location("lektor_zu_episto", TOOLS / "lektor-zu-episto.py")
lze = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(lze)

BUCH = f"{AUTOR}/{TITEL}"


def lauf_lze(root: Path, **kw):
    lze.verarbeite(BUCH, root / "rohdaten" / "Lektor", root / "reader", "de", "en", False, **kw)


def exportiere(root: Path):
    export_korrektur.exportiere(root, root / "reader" / "export-epistopheles" / "korrektur", root / "rohdaten" / "Lektor", ebooks=False)


def absaetze(text: str) -> list[str]:
    return [text[a:b] for a, b in absatz_spannen(text)]


def test_gesamtlauf_p2(browser, tmp_path, capsys):
    root = baue_testwurzel(tmp_path / "wurzel")
    buch = root / "reader" / AUTOR / TITEL
    lauf_lze(root, ueberschreiben=True)                              # Urtext aus den de-Chunks, wie die Pipeline ihn erzeugt
    exportiere(root)
    index = json.loads((buch / "quelle" / "_kapitel_index.json").read_text(encoding="utf-8"))
    datei = index[0]["datei"]
    pfad = buch / "quelle" / datei
    urtext = pfad.read_bytes().decode("utf-8")
    teile = absaetze(urtext)
    assert teile[2].startswith("Ein zweiter Absatz")

    # --- Gerät: Ursache suchen, bearbeiten, trennen, markieren ------------------------------------------------------
    apic = Apic(root)
    try:
        ctx, pg = neue_seite(browser, apic.url)
        zu_text(pg)
        tippe(pg, "Der Repräsentant ist")
        pg.locator("#absatz-ursache").click()                       # Ursache: Chunk 0 der Übersetzung
        pg.wait_for_function("modus === 'uebersetzung' && gezeigteSig !== null")
        assert pg.evaluate("uebersetzungsIndex(pos.chunk)") == 0
        assert pg.evaluate("eintraege.length") == 0
        pg.locator("#modus-text").click()
        pg.wait_for_function("modus === 'text' && gezeigteSig !== null")

        bearbeite(pg, "Ein zweiter Absatz", "Ein zweiter Absatz folgt dort.")
        speichern(pg)
        pg.wait_for_function("eintraege.length === 1")
        tippe(pg, " dass die Abgeordneten")                        # Zeiger hinter dem Leerzeichen: Absatz 1 teilen
        pg.locator("#absatz-trennen").click()
        pg.wait_for_function("eintraege.length === 2")
        waehle(pg, "Ein zweiter", "Absatz")
        pg.fill("#werkzeug-notiz", "Gesamtlauf")
        knopf(pg, "markieren").click()
        pg.wait_for_function("eintraege.length === 3")
        pg.wait_for_function("eintraege.every((e) => e.status === 'gesendet')")        # automatisch bei APIC angekommen
        erwartet = pg.evaluate("window.Redaktion.spieleAb(daten.kapitel[0].text, eintraege).text")
        ids = pg.evaluate("eintraege.map((e) => e.id)")
        assert pg.evaluate("eintraege.map((e) => [e.ebene, e.art])") == [["volltext", "ersetzen"], ["volltext", "trennen"], ["volltext", "marke"]]
        assert erwartet != urtext and "folgt dort." in erwartet

        # --- PC: Eingang, Dry-Run, Einarbeiten ---------------------------------------------------------------------------
        eingang = protokoll.lade_eingang(root, BUCH)
        assert [e["id"] for e in eingang] == ids and all(e["ziel"]["datei"] == datei for e in eingang)
        capsys.readouterr()
        assert ra.main(["--root", str(root)]) == 0
        out = capsys.readouterr().out
        assert datei in out and "würde angewendet" in out and "3 anzuwenden" in out
        assert pfad.read_bytes().decode("utf-8") == urtext                           # Dry-Run schreibt nichts
        assert ra.main(["--root", str(root), "--ausfuehren"]) == 0
        capsys.readouterr()
        assert pfad.read_bytes().decode("utf-8") == erwartet                         # Python-Replay == JS-Replay des Geräts
        assert list((buch / "notizen" / "_backup").glob(f"{pfad.stem}.*.md"))[0].read_bytes() == urtext.encode("utf-8")
        red = json.loads((buch / "notizen" / "redaktion.json").read_text(encoding="utf-8"))
        assert [e["id"] for e in red["eintraege"]] == ids
        assert red["dateien"][datei]["hash_original"] == ops.pruefsumme(urtext)
        assert red["dateien"][datei]["hash_aktuell"] == ops.pruefsumme(erwartet)

        # --- neuer Export: `enthalten`; dieselbe Seite lädt neu, nichts wird doppelt angewendet --------------------------
        exportiere(root)
        d = json.loads((root / "reader" / "export-epistopheles" / "korrektur" / "k001.json").read_text(encoding="utf-8"))
        assert d["enthalten"] == ids and d["kapitel"][0]["text"] == erwartet and d["kapitel"][0]["datei"] == datei
        pg.reload()
        pg.wait_for_function("typeof buch !== 'undefined' && buch && eintraegeBuchId === buch.id")
        zu_text(pg)
        assert text_im_feld(pg) == erwartet
        assert pg.evaluate("kapitelCache.get(0).ansicht.konflikte.length") == 0 and pg.evaluate("kapitelCache.get(0).ansicht.luecke.length") == 0
        ctx.close()
        assert not pg.fehler, pg.fehler
    finally:
        apic.stop()

    # --- Neuaufbau durch die Pipeline: Schutz und Wiederholbarkeit -------------------------------------------------------
    with pytest.raises(SystemExit) as exc:
        lauf_lze(root)
    assert "--ueberschreiben" in str(exc.value)
    assert pfad.read_bytes().decode("utf-8") == erwartet
    lauf_lze(root, ueberschreiben=True)
    assert pfad.read_bytes().decode("utf-8") == erwartet                              # Urtext neu erzeugt, Korrekturen wieder eingespielt
    assert not (buch / "notizen" / "redaktion-nachspiel.json").exists()
    assert len(list((buch / "notizen" / "_backup").glob("quelle-*"))) == 1            # Sicherung der Kapitel vor dem Neuaufbau

    # --- Basis hat sich geändert: Konflikt einzeln mit Grund ---------------------------------------------------------------
    chunk = root / "rohdaten" / "Lektor" / AUTOR / TITEL / "de" / "chunk_000.md"
    chunk.write_text(chunk.read_text(encoding="utf-8").replace("Ein zweiter Absatz folgt hier.", "Ein zweiter Absatz folgt anderswo."), encoding="utf-8")
    capsys.readouterr()
    lauf_lze(root, ueberschreiben=True)
    out = capsys.readouterr().out
    assert datei in out and "WARNUNG" in out
    bericht = schutz.lade_nachspiel(buch)
    assert [k["id"] for k in bericht["konflikte"]] == [ids[0]] and bericht["konflikte"][0]["datei"] == datei and bericht["konflikte"][0]["grund"]
    assert bericht["basis_geaendert"] == [datei]
    heute = pfad.read_bytes().decode("utf-8")
    assert "folgt anderswo." in heute and "folgt dort." not in heute                    # der Konflikt-Absatz bleibt, wie die neue Basis ihn liefert
    assert any(p.startswith("und die Abgeordneten") or p.startswith("dass die Abgeordneten") for p in absaetze(heute))   # die Teilung (Trennen) wurde trotzdem wieder eingespielt
    protokoll_eintraege = json.loads((buch / "notizen" / "redaktion.json").read_text(encoding="utf-8"))["eintraege"]
    assert [e["id"] for e in protokoll_eintraege] == ids                              # das Protokoll bleibt vollständig
