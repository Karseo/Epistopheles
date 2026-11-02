"""Tests fuer neu-zusammenfassen.py (ohne LLM: `frage` wird ersetzt)."""
import argparse
import importlib.util
import json
from pathlib import Path

import pytest

SKRIPT = Path(__file__).resolve().parent / "neu-zusammenfassen.py"
SATZ = "Der Abschnitt untersucht Gegenstand und Gang genau."


@pytest.fixture
def nz():
    spec = importlib.util.spec_from_file_location("neu_zusammenfassen", SKRIPT)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _buch(root: Path, autor: str, titel: str, kapitel: int = 2) -> Path:
    pfad = root / "reader" / autor / titel
    (pfad / "quelle").mkdir(parents=True)
    (pfad / "notizen").mkdir()
    eintraege = []
    for n in range(1, kapitel + 1):
        datei = f"{n:04d}_k{n}.md"
        (pfad / "quelle" / datei).write_text(f"Text {n}.", encoding="utf-8")
        eintraege.append({
            "datei": datei, "kapitel_nr": n, "titel": f"Kapitel {n}", "woerter": 2,
            "these": ["Eine These."], "gegen": [], "kern": [], "def": [], "beleg": [],
            "zusammenfassung": f"Alte lange Zusammenfassung {n} mit vielen Worten.",
        })
    (pfad / "notizen" / "tags.json").write_text(json.dumps({
        "werk": titel, "autor": autor, "sprache": "de", "eintraege": kapitel,
        "erstellt": "x", "kapitel": eintraege}, ensure_ascii=False), encoding="utf-8")
    return pfad


def _args(root, **kw):
    basis = dict(root=str(root), plan=False, limit=0, model="m", num_ctx=32768, max_ctx=131072, anwenden=False)
    basis.update(kw)
    return argparse.Namespace(**basis)


def _neu(buch: Path) -> dict:
    return json.loads((buch / "notizen" / "zusammenfassung_neu.json").read_text(encoding="utf-8"))


def _tags(buch: Path) -> dict:
    return json.loads((buch / "notizen" / "tags.json").read_text(encoding="utf-8"))


def _fake(zaehler, vorher=None):
    def frage(modell, num_ctx, system, user):
        zaehler.append(1)
        if vorher:
            vorher(len(zaehler))
        return json.dumps({"zusammenfassung": SATZ})
    return frage


def test_alle_erzeugt_nebendateien_und_laesst_tags_json_unveraendert(nz, tmp_path, monkeypatch):
    b1 = _buch(tmp_path, "A", "Buch1")
    b2 = _buch(tmp_path, "B", "Buch2")
    vorher = (b1 / "notizen" / "tags.json").read_bytes()
    monkeypatch.setattr(nz, "frage", _fake([]))
    nz.alle_erzeugen(_args(tmp_path))
    assert len(_neu(b1)["eintraege"]) == 2 and len(_neu(b2)["eintraege"]) == 2
    assert (b1 / "notizen" / "tags.json").read_bytes() == vorher
    assert not list((b1 / "notizen").glob("*.tmp"))


def test_plan_ruft_das_llm_nicht_auf(nz, tmp_path, monkeypatch, capsys):
    _buch(tmp_path, "A", "Buch1")

    def verboten(*a, **k):
        raise AssertionError("LLM darf im Plan-Modus nicht aufgerufen werden")
    monkeypatch.setattr(nz, "frage", verboten)
    nz.alle_erzeugen(_args(tmp_path, plan=True))
    assert "offene Kapitel: 2" in capsys.readouterr().out


def test_stopdatei_beendet_nach_dem_laufenden_buch_und_neustart_setzt_fort(nz, tmp_path, monkeypatch):
    b1 = _buch(tmp_path, "A", "Buch1")
    b2 = _buch(tmp_path, "B", "Buch2")
    stop = nz.stopdatei(tmp_path)
    stop.parent.mkdir(parents=True)

    def anfordern(n):
        if n == 1:
            stop.touch()  # mitten in Buch 1 angefordert
    zaehler = []
    monkeypatch.setattr(nz, "frage", _fake(zaehler, anfordern))
    nz.alle_erzeugen(_args(tmp_path))

    assert len(_neu(b1)["eintraege"]) == 2          # Buch 1 wurde noch fertig
    assert not (b2 / "notizen" / "zusammenfassung_neu.json").exists()  # Buch 2 nicht begonnen
    assert not stop.exists()                          # Datei aufgeraeumt
    assert len(zaehler) == 2

    zaehler2 = []
    monkeypatch.setattr(nz, "frage", _fake(zaehler2))
    nz.alle_erzeugen(_args(tmp_path))
    assert len(_neu(b2)["eintraege"]) == 2
    assert len(zaehler2) == 2                         # Buch 1 nicht noch einmal berechnet


def test_alte_stopdatei_blockiert_den_naechsten_lauf_nicht(nz, tmp_path, monkeypatch):
    b1 = _buch(tmp_path, "A", "Buch1")
    b2 = _buch(tmp_path, "B", "Buch2")
    stop = nz.stopdatei(tmp_path)
    stop.parent.mkdir(parents=True)
    stop.touch()
    monkeypatch.setattr(nz, "frage", _fake([]))
    nz.alle_erzeugen(_args(tmp_path))
    assert len(_neu(b1)["eintraege"]) == 2 and len(_neu(b2)["eintraege"]) == 2


def test_strg_c_laesst_den_fortschritt_erhalten(nz, tmp_path, monkeypatch):
    b1 = _buch(tmp_path, "A", "Buch1")
    b2 = _buch(tmp_path, "B", "Buch2")

    def abbrechen(n):
        if n == 2:
            raise KeyboardInterrupt
    monkeypatch.setattr(nz, "frage", _fake([], abbrechen))
    with pytest.raises(SystemExit) as exc:
        nz.alle_erzeugen(_args(tmp_path))
    assert exc.value.code == 130
    assert len(_neu(b1)["eintraege"]) == 1            # erstes Kapitel gesichert, Datei heil
    assert not list((b1 / "notizen").glob("*.tmp"))

    zaehler = []
    monkeypatch.setattr(nz, "frage", _fake(zaehler))
    nz.alle_erzeugen(_args(tmp_path))
    assert len(_neu(b1)["eintraege"]) == 2 and len(_neu(b2)["eintraege"]) == 2
    assert len(zaehler) == 3                          # 1 Rest in Buch 1 + 2 in Buch 2


def test_anwenden_alle_uebernimmt_sichert_und_schuetzt_handarbeit(nz, tmp_path, monkeypatch):
    b1 = _buch(tmp_path, "A", "Buch1")
    b2 = _buch(tmp_path, "B", "Buch2")
    monkeypatch.setattr(nz, "frage", _fake([]))
    nz.alle_erzeugen(_args(tmp_path))

    daten = _tags(b1)
    daten["kapitel"][0]["zusammenfassung"] = "Von Hand geaendert."
    (b1 / "notizen" / "tags.json").write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")

    nz.alle_anwenden(_args(tmp_path, anwenden=True))
    k1 = _tags(b1)["kapitel"]
    assert k1[0]["zusammenfassung"] == "Von Hand geaendert."   # nicht ueberschrieben
    assert k1[1]["zusammenfassung"] == SATZ
    assert all(k["zusammenfassung"] == SATZ for k in _tags(b2)["kapitel"])
    assert len(list((b1 / "notizen" / "_backup").glob("tags.*.json"))) == 1
    # andere Felder unberuehrt
    assert k1[1]["these"] == ["Eine These."]

    # zweiter Lauf aendert nichts und legt kein weiteres Backup an
    nz.alle_anwenden(_args(tmp_path, anwenden=True))
    assert len(list((b2 / "notizen" / "_backup").glob("tags.*.json"))) == 1


def test_stop_modus_legt_die_stopdatei_an(nz, tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["neu-zusammenfassen.py", "--stop", "--root", str(tmp_path)])
    nz.main()
    assert nz.stopdatei(tmp_path).exists()


def test_atomares_schreiben_laesst_bei_fehler_die_alte_datei_heil(nz, tmp_path, monkeypatch):
    ziel = tmp_path / "x.json"
    nz.schreibe_json(ziel, {"a": 1})

    def kaputt(src, dst):
        raise KeyboardInterrupt
    monkeypatch.setattr(nz.os, "replace", kaputt)
    with pytest.raises(KeyboardInterrupt):
        nz.schreibe_json(ziel, {"a": 2})
    assert json.loads(ziel.read_text(encoding="utf-8")) == {"a": 1}


def test_kontext_waechst_mit_der_kapitellaenge(nz):
    assert nz.kontext_fuer(5000) == 32768
    assert nz.kontext_fuer(13000) == 65536     # 13000 * 2,3 + 3500 > 32768
    assert nz.kontext_fuer(29021) == 98304     # das Arendt-Kapitel aus dem Fehlerfall
    assert nz.kontext_fuer(41515) == 131072    # laengstes Kapitel der Bibliothek
    assert nz.kontext_fuer(80000) is None      # passt nicht mehr
    assert nz.kontext_fuer(41515, max_ctx=65536) is None


def test_gekuerzter_prompt_wird_erkannt(nz):
    system, user = "s" * 1000, "u" * 211000
    erwartet = (len(system) + len(user)) / nz.ZEICHEN_JE_TOKEN  # ~63000 Tokens
    # Fehlerfall von 2026-10-12: Ollama meldete 16386 Tokens fuer einen ~63000-Token-Prompt
    with pytest.raises(RuntimeError, match="gekuerzt"):
        nz.pruefe_nicht_gekuerzt({"prompt_eval_count": 16386}, system, user)
    nz.pruefe_nicht_gekuerzt({"prompt_eval_count": int(erwartet * 0.9)}, system, user)   # ok
    nz.pruefe_nicht_gekuerzt({"prompt_eval_count": 100, "prompt_eval_cached_count": int(erwartet)}, system, user)
    nz.pruefe_nicht_gekuerzt({}, system, user)   # ohne Angabe: nicht pruefbar, kein Fehler


def test_antwort_ohne_json_nennt_den_anfang_der_antwort(nz):
    with pytest.raises(ValueError, match="Sie haben hier einen"):
        nz.parse_antwort("Sie haben hier einen ausgedehnten Abschnitt geteilt ...")
    assert nz.parse_antwort('<think>x</think>```json\n{"zusammenfassung": "Ein  Satz."}\n```') == "Ein Satz."


def _langes_kapitel(buch: Path, woerter: int) -> None:
    (buch / "quelle" / "0001_k1.md").write_text("wort " * woerter, encoding="utf-8")


def test_langes_kapitel_bekommt_groesseren_kontext(nz, tmp_path, monkeypatch):
    b = _buch(tmp_path, "A", "Buch1", kapitel=2)
    _langes_kapitel(b, 20000)                       # 20000 * 2,3 + 3500 = 49500 -> 65536
    kontexte = []

    def frage(modell, num_ctx, system, user):
        kontexte.append(num_ctx)
        return json.dumps({"zusammenfassung": SATZ})
    monkeypatch.setattr(nz, "frage", frage)
    nz.alle_erzeugen(_args(tmp_path))
    assert kontexte == [65536, 32768]               # Kapitel 1 gross, Kapitel 2 normal
    assert len(_neu(b)["eintraege"]) == 2


def test_zu_langes_kapitel_wird_uebersprungen_statt_gekuerzt_verarbeitet(nz, tmp_path, monkeypatch, capsys):
    b = _buch(tmp_path, "A", "Buch1", kapitel=2)
    _langes_kapitel(b, 60000)
    aufrufe = []
    monkeypatch.setattr(nz, "frage", _fake(aufrufe))
    nz.alle_erzeugen(_args(tmp_path, max_ctx=65536))
    assert len(aufrufe) == 1                         # nur Kapitel 2
    assert list(_neu(b)["eintraege"]) == ["0002_k2.md"]
    assert "passen nicht in --max-ctx" in capsys.readouterr().out
