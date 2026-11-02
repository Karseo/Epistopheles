from __future__ import annotations
import json
from pathlib import Path

from episto_tui.korrektur import absatz_spannen
from redaktion import ops, schutz


def _eintrag(text: str, index: int, nachher: str, datei: str, **extra) -> dict:
    a, b = absatz_spannen(text)[index]
    ziel = {"absatz_index": index, "anfang": ops.anker_von(text[a:b]), "datei": datei}
    e = ops.neuer_eintrag("A/T", "volltext", ziel, "ersetzen", {"nachher": nachher}, text[a:b])
    e["status"] = "angewendet"
    e.update(extra)
    return e


def _reader(tmp_path: Path, dateien: dict[str, bytes], eintraege) -> Path:
    buch = tmp_path / "A" / "T"
    (buch / "quelle").mkdir(parents=True)
    (buch / "notizen").mkdir()
    for n, inhalt in dateien.items():
        (buch / "quelle" / n).write_bytes(inhalt)
    if isinstance(eintraege, str):
        (buch / "notizen" / "redaktion.json").write_text(eintraege, encoding="utf-8")
    else:
        (buch / "notizen" / "redaktion.json").write_text(
            json.dumps({"eintraege": eintraege}), encoding="utf-8")
    return buch


# --- pruefe_neuuebersetzung -------------------------------------------------

def test_neuuebersetzung_ohne_resume_wird_blockiert_wenn_redaktion_json_existiert(tmp_path):
    (tmp_path / "redaktion.json").write_text("{}", encoding="utf-8")
    msg = schutz.pruefe_neuuebersetzung(tmp_path, resume=False, verwerfen=False)
    assert msg and "--korrekturen-verwerfen" in msg and "--resume" in msg


def test_neuuebersetzung_erlaubt_mit_resume_oder_verwerfen(tmp_path):
    (tmp_path / "redaktion.json").write_text("{}", encoding="utf-8")
    assert schutz.pruefe_neuuebersetzung(tmp_path, resume=True, verwerfen=False) is None
    assert schutz.pruefe_neuuebersetzung(tmp_path, resume=False, verwerfen=True) is None


def test_neuuebersetzung_erlaubt_ohne_redaktion_json(tmp_path):
    assert schutz.pruefe_neuuebersetzung(tmp_path, resume=False, verwerfen=False) is None


# --- pruefe_ueberschreiben --------------------------------------------------

def test_ueberschreiben_blockiert_bei_vorhandenen_md(tmp_path):
    (tmp_path / "0001_x.md").write_text("x", encoding="utf-8")
    msg = schutz.pruefe_ueberschreiben(tmp_path, ueberschreiben=False, dry_run=False)
    assert msg and "--ueberschreiben" in msg
    assert schutz.pruefe_ueberschreiben(tmp_path, True, False) is None
    assert schutz.pruefe_ueberschreiben(tmp_path, False, True) is None


def test_ueberschreiben_none_bei_leerem_oder_fehlendem_ordner(tmp_path):
    assert schutz.pruefe_ueberschreiben(tmp_path / "gibt-es-nicht", False, False) is None
    assert schutz.pruefe_ueberschreiben(tmp_path, False, False) is None
    (tmp_path / "_kapitel_index.json").write_text("[]", encoding="utf-8")
    assert schutz.pruefe_ueberschreiben(tmp_path, False, False) is None


# --- spiele_nach ------------------------------------------------------------

ALT = "Erster Absatz.\r\n\r\nZweiter\tAbsatz alt.\r\n\r\nDritter Absatz."


def test_spiele_nach_wendet_volltext_eintraege_an_und_meldet_unanwendbare(tmp_path):
    ok = _eintrag(ALT, 1, "Zweiter\tAbsatz neu.", "0001_a.md")
    kaputt = _eintrag(ALT, 0, "Neu.", "0002_b.md")          # Datei fehlt
    fremd = _eintrag(ALT, 2, "X.", "0001_a.md", ebene="chunk")  # andere Ebene: ignoriert
    offen = _eintrag(ALT, 2, "X.", "0001_a.md", status="konflikt")  # nicht angewendet: ignoriert
    buch = _reader(tmp_path, {"0001_a.md": ALT.encode("utf-8")}, [ok, kaputt, fremd, offen])
    assert schutz.spiele_nach(buch) == 1
    neu = (buch / "quelle" / "0001_a.md").read_bytes().decode("utf-8")
    assert neu == ALT.replace("Absatz alt.", "Absatz neu.")
    assert not list((buch / "quelle").glob("*.tmp"))


def test_spiele_nach_konflikt_laesst_datei_unveraendert(tmp_path):
    e = _eintrag(ALT, 1, "Zweiter Absatz neu.", "0001_a.md")
    geaendert = ALT.replace("Zweiter\tAbsatz alt.", "Etwas ganz anderes.")
    buch = _reader(tmp_path, {"0001_a.md": geaendert.encode("utf-8")}, [e])
    assert schutz.spiele_nach(buch) == 1
    assert (buch / "quelle" / "0001_a.md").read_bytes() == geaendert.encode("utf-8")


def test_spiele_nach_zweiter_aufruf_beschaedigt_nichts(tmp_path):
    """Gewaehltes Verhalten: ein bereits eingearbeiteter Eintrag stimmt nicht mehr mit
    seiner vorher-Pruefsumme ueberein und zaehlt als nicht anwendbar; der Text bleibt."""
    e = _eintrag(ALT, 1, "Zweiter Absatz neu.", "0001_a.md")
    buch = _reader(tmp_path, {"0001_a.md": ALT.encode("utf-8")}, [e])
    assert schutz.spiele_nach(buch) == 0
    nach_erstem = (buch / "quelle" / "0001_a.md").read_bytes()
    assert schutz.spiele_nach(buch) == 1
    assert (buch / "quelle" / "0001_a.md").read_bytes() == nach_erstem


def test_spiele_nach_ruecknahme_und_reihenfolge(tmp_path):
    e1 = _eintrag(ALT, 0, "Eins.", "0001_a.md")
    r = ops.neuer_eintrag("A/T", "volltext", {"datei": "0001_a.md"}, "ruecknahme",
                          {"id": e1["id"]}, "")
    r["status"] = "angewendet"
    e2 = _eintrag(ALT, 2, "Drei.", "0001_a.md")
    buch = _reader(tmp_path, {"0001_a.md": ALT.encode("utf-8")}, [e1, r, e2])
    assert schutz.spiele_nach(buch) == 0
    neu = (buch / "quelle" / "0001_a.md").read_bytes().decode("utf-8")
    assert neu.startswith("Erster Absatz.") and neu.endswith("Drei.")


def test_spiele_nach_pfadtrenner_im_dateinamen_zaehlt_als_nicht_angewendet(tmp_path):
    ausserhalb = tmp_path / "A" / "T" / "geheim.md"
    es = [_eintrag(ALT, 1, "Z.", "../geheim.md"), _eintrag(ALT, 1, "Z.", "u/x.md"),
          _eintrag(ALT, 1, "Z.", "..\\x.md"), _eintrag(ALT, 1, "Z.", "")]
    buch = _reader(tmp_path, {"0001_a.md": ALT.encode("utf-8")}, es)
    ausserhalb.write_bytes(ALT.encode("utf-8"))
    assert schutz.spiele_nach(buch) == 4
    assert ausserhalb.read_bytes() == ALT.encode("utf-8")
    assert (buch / "quelle" / "0001_a.md").read_bytes() == ALT.encode("utf-8")


def test_spiele_nach_ohne_redaktion_json_ist_null(tmp_path):
    buch = tmp_path / "A" / "T"
    (buch / "quelle").mkdir(parents=True)
    assert schutz.spiele_nach(buch) == 0


def test_spiele_nach_kaputte_redaktion_json_stuerzt_nicht_ab(tmp_path):
    buch = _reader(tmp_path, {"0001_a.md": b"Text."}, "{kaputt")
    assert schutz.spiele_nach(buch) == 1
    assert (buch / "quelle" / "0001_a.md").read_bytes() == b"Text."


def test_spiele_nach_eintraege_keine_liste_stuerzt_nicht_ab(tmp_path):
    buch = _reader(tmp_path, {}, "")
    (buch / "notizen" / "redaktion.json").write_text('{"eintraege": 5}', encoding="utf-8")
    assert schutz.spiele_nach(buch) == 1
