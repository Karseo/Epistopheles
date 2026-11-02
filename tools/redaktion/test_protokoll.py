"""Tests fuer Protokolldateien und sichere Buchpfade (Task 3)."""
from __future__ import annotations

import os

import pytest

from redaktion.protokoll import (
    buch_schluessel, eingang_ordner, lade_eingang, lade_redaktion, lade_stand,
    liste_buecher, schreibe_eingang, setze_stand, speichere_redaktion,
)

BUCH = "Autor, Eins/Titel"
ERLAUBT = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")


def eintrag(i: str, erstellt: str = "2026-11-02T10:00:00Z", **kw) -> dict:
    d = {"id": i, "buch": BUCH, "ebene": "geraet", "ziel": {}, "art": "ersetzen",
         "parameter": {}, "vorher": {}, "nachher": {}, "hinweis": "",
         "erstellt": erstellt, "geraet": "tab", "status": "offen"}
    d.update(kw)
    return d


def test_buch_schluessel():
    assert buch_schluessel("A", "B") == "A/B"


def test_schreibe_eingang_ist_idempotent(tmp_path):
    es = [eintrag("a"), eintrag("b")]
    assert schreibe_eingang(tmp_path, "tab", BUCH, es) == ["a", "b"]
    assert schreibe_eingang(tmp_path, "tab", BUCH, es) == []
    assert len(list(eingang_ordner(tmp_path, BUCH).iterdir())) == 1
    assert [e["id"] for e in lade_eingang(tmp_path, BUCH)] == ["a", "b"]


def test_idempotent_auch_ueber_geraete_und_innerhalb_einer_liste(tmp_path):
    assert schreibe_eingang(tmp_path, "g1", BUCH, [eintrag("a"), eintrag("a")]) == ["a"]
    assert schreibe_eingang(tmp_path, "g2", BUCH, [eintrag("a"), eintrag("c")]) == ["c"]
    assert sorted(e["id"] for e in lade_eingang(tmp_path, BUCH)) == ["a", "c"]


def test_zwei_schreibvorgaenge_gleiche_sekunde_ueberschreiben_nicht(tmp_path):
    schreibe_eingang(tmp_path, "tab", BUCH, [eintrag("a")])
    schreibe_eingang(tmp_path, "tab", BUCH, [eintrag("b")])
    assert len(list(eingang_ordner(tmp_path, BUCH).glob("*.json"))) == 2
    assert len(lade_eingang(tmp_path, BUCH)) == 2


def test_ungueltige_eintraege_werden_uebersprungen(tmp_path):
    es = ["kein dict", {"ohne": "id"}, {"id": 5}, eintrag("ok")]
    assert schreibe_eingang(tmp_path, "tab", BUCH, es) == ["ok"]


def test_nichts_neues_schreibt_keine_datei(tmp_path):
    assert schreibe_eingang(tmp_path, "tab", BUCH, []) == []
    assert not list(tmp_path.rglob("*.json"))


def test_buch_im_argument_gewinnt(tmp_path):
    schreibe_eingang(tmp_path, "tab", BUCH, [eintrag("a", buch="Anderer/Titel")])
    assert lade_eingang(tmp_path, BUCH)[0]["buch"] == BUCH


def test_lade_eingang_sortiert_nach_erstellt(tmp_path):
    schreibe_eingang(tmp_path, "g1", BUCH, [eintrag("z", "2026-11-02T12:00:00Z")])
    schreibe_eingang(tmp_path, "g2", BUCH, [eintrag("y", "2026-11-02T09:00:00Z"),
                                           eintrag("x", "2026-11-02T10:00:00Z")])
    assert [e["id"] for e in lade_eingang(tmp_path, BUCH)] == ["y", "x", "z"]


def test_lade_eingang_ueberspringt_kaputte_dateien(tmp_path):
    schreibe_eingang(tmp_path, "tab", BUCH, [eintrag("a")])
    ordner = eingang_ordner(tmp_path, BUCH)
    (ordner / "kaputt.json").write_text("{nicht json", encoding="utf-8")
    (ordner / "liste.json").write_text('"nur ein String"', encoding="utf-8")
    (ordner / "bytes.json").write_bytes(b"\xff\xfe\x00")
    assert [e["id"] for e in lade_eingang(tmp_path, BUCH)] == ["a"]


def test_lade_eingang_ohne_ordner_ist_leer(tmp_path):
    assert lade_eingang(tmp_path, BUCH) == []


def test_geraetename_wird_bereinigt(tmp_path):
    for name in ["../../evil", "a/b\\c:d", "", "..", "Tab Eins!", "Ünï"]:
        schreibe_eingang(tmp_path, name, BUCH, [eintrag("id-" + name)])
    namen = [p.name for p in eingang_ordner(tmp_path, BUCH).iterdir()]
    assert len(namen) == 6
    for n in namen:
        assert n.endswith(".json")
        assert set(n) <= ERLAUBT
        assert not n.startswith(".")
    basis = tmp_path / "hilfsdaten" / "redaktion" / "eingang"
    alle = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert all(basis in p.parents for p in alle)


def test_unsichere_buchnamen_werden_abgelehnt(tmp_path):
    for schlecht in ["../x/y", "A/../B", "/abs/y", "A", "A/B/C", "A/", "", "/", "//",
                     "./A/B", "A/./B", "A\\B/C", "C:/B", "C:\\x/y", "A/B\x00", "A\x00/B",
                     "A/B:strom", "A/B*", "A/B?", 'A/B"', "A/B<", "A/B>", "A/B|",
                     "A/B.", "A/B ", "A /B.", "CON/B", "A/nul", "A/com1.txt", "A/B\n",
                     "\\\\server\\share/B", "A/..\\B", "A/ B"]:
        with pytest.raises(ValueError):
            eingang_ordner(tmp_path, schlecht)
    p = eingang_ordner(tmp_path, "Bueno de Mesquita, Bruce/The Dictator's Handbook")
    assert p == (tmp_path / "hilfsdaten" / "redaktion" / "eingang"
                 / "Bueno de Mesquita, Bruce" / "The Dictator's Handbook")
    p2 = eingang_ordner(tmp_path, "Müller, Äh/Ü.ber (1)")
    assert p2.name == "Ü.ber (1)" and p2.parent.name == "Müller, Äh"


def test_nichtstring_buch_wird_abgelehnt(tmp_path):
    with pytest.raises(ValueError):
        eingang_ordner(tmp_path, None)  # type: ignore[arg-type]


def test_aufgeloester_pfad_bleibt_im_eingang(tmp_path):
    p = eingang_ordner(tmp_path, BUCH)
    basis = (tmp_path / "hilfsdaten" / "redaktion" / "eingang").resolve()
    assert basis in p.resolve().parents


def test_symlink_ausbruch_wird_abgelehnt(tmp_path):
    basis = tmp_path / "hilfsdaten" / "redaktion" / "eingang"
    basis.mkdir(parents=True)
    aussen = tmp_path / "aussen"
    aussen.mkdir()
    try:
        os.symlink(aussen, basis / "Link", target_is_directory=True)
    except (OSError, NotImplementedError):
        if os.name != "nt":
            pytest.skip("Symlinks nicht verfuegbar")
        import subprocess  # Windows ohne Symlink-Recht: Verzeichnis-Junction
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(basis / "Link"), str(aussen)],
                           capture_output=True)
        if r.returncode != 0:
            pytest.skip("weder Symlink noch Junction verfuegbar")
    with pytest.raises(ValueError):
        eingang_ordner(tmp_path, "Link/Titel")


def test_stand_wird_gespeichert_und_gelesen(tmp_path):
    assert lade_stand(tmp_path, BUCH) == {}
    setze_stand(tmp_path, BUCH, "a", "angewendet")
    setze_stand(tmp_path, BUCH, "b", "konflikt", "Absatz geaendert")
    st = lade_stand(tmp_path, BUCH)
    assert st["a"]["status"] == "angewendet"
    assert st["b"]["status"] == "konflikt" and st["b"]["grund"] == "Absatz geaendert"
    setze_stand(tmp_path, BUCH, "a", "konflikt", "neu")
    assert lade_stand(tmp_path, BUCH)["a"]["status"] == "konflikt"
    assert (eingang_ordner(tmp_path, BUCH) / "_stand.json").is_file()


def test_stand_datei_zaehlt_nicht_als_eintragsdatei(tmp_path):
    schreibe_eingang(tmp_path, "tab", BUCH, [eintrag("a")])
    setze_stand(tmp_path, BUCH, "a", "angewendet")
    assert [e["id"] for e in lade_eingang(tmp_path, BUCH)] == ["a"]


def test_kaputter_stand_ist_leer(tmp_path):
    ordner = eingang_ordner(tmp_path, BUCH)
    ordner.mkdir(parents=True)
    (ordner / "_stand.json").write_text("{kaputt", encoding="utf-8")
    assert lade_stand(tmp_path, BUCH) == {}
    setze_stand(tmp_path, BUCH, "a", "angewendet")
    assert "a" in lade_stand(tmp_path, BUCH)


def test_fehlende_redaktion_datei_ist_leer(tmp_path):
    assert lade_redaktion(tmp_path / "nix" / "redaktion.json") == {"eintraege": [], "chunks": {}}


def test_redaktion_roundtrip_utf8(tmp_path):
    pfad = tmp_path / "unter" / "redaktion.json"
    daten = {"eintraege": [{"id": "a", "hinweis": "Äpfel"}], "chunks": {"1": {"x": "ü"}}}
    speichere_redaktion(pfad, daten)
    assert "Äpfel" in pfad.read_text(encoding="utf-8")
    assert lade_redaktion(pfad) == daten
    assert not list(pfad.parent.glob("*.tmp"))


def test_kaputte_redaktion_datei_ist_leer(tmp_path):
    pfad = tmp_path / "redaktion.json"
    pfad.write_text("{kaputt", encoding="utf-8")
    assert lade_redaktion(pfad) == {"eintraege": [], "chunks": {}}
    pfad.write_text('{"eintraege": [1]}', encoding="utf-8")
    assert lade_redaktion(pfad) == {"eintraege": [1], "chunks": {}}


def test_liste_buecher(tmp_path):
    assert liste_buecher(tmp_path) == []
    schreibe_eingang(tmp_path, "t", "Zed/Buch", [eintrag("a")])
    schreibe_eingang(tmp_path, "t", "Alf, X/Werk (1)", [eintrag("b")])
    basis = tmp_path / "hilfsdaten" / "redaktion" / "eingang"
    (basis / "streu.json").write_text("{}", encoding="utf-8")
    (basis / "Zed" / "datei.txt").write_text("x", encoding="utf-8")
    (basis / "NurAutor").mkdir()
    (basis / "Tief" / "A" / "B").mkdir(parents=True)
    assert liste_buecher(tmp_path) == ["Alf, X/Werk (1)", "Tief/A", "Zed/Buch"]


def test_pruefe_schluessel_gibt_gueltige_unveraendert_zurueck_und_lehnt_unsichere_ab():
    from redaktion.protokoll import pruefe_schluessel
    for ok in ("Cathy O'Neil/Weapons of Math Destruction", "Müller, Äh/Ü.ber (1)"):
        assert pruefe_schluessel(ok) == ok
    for schlecht in ("../x/y", "A/../B", "/abs/y", "A", "A/B/C", "A/", "A\\B/C", 5, None):
        with pytest.raises(ValueError):
            pruefe_schluessel(schlecht)


def test_lade_eingang_sortiert_gleiche_sekunde_nach_millisekunden(tmp_path):
    """Eintraege derselben Sekunde duerfen nicht umgeordnet werden (Ketten bauen aufeinander auf); Eintraege
    ohne Millisekunden (aeltere Geraete) zaehlen als .000."""
    schreibe_eingang(tmp_path, "g1", BUCH, [eintrag("c", "2026-11-02T10:00:00.250Z"), eintrag("a", "2026-11-02T10:00:00Z")])
    schreibe_eingang(tmp_path, "g2", BUCH, [eintrag("b", "2026-11-02T10:00:00.100Z"), eintrag("d", "2026-11-02T10:00:01Z")])
    assert [e["id"] for e in lade_eingang(tmp_path, BUCH)] == ["a", "b", "c", "d"]
