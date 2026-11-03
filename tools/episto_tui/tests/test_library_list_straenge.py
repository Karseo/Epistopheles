"""list_straenge: Themen (Straenge) eines Werks mit den Kapitelnummern ihrer Fundstellen (Verbindungsansicht)."""
from pathlib import Path

from episto_tui import library
from episto_tui.models import Buch


def _buch(tmp_path: Path) -> Buch:
    pfad = tmp_path / "reader" / "Autor, A" / "Werk"
    (pfad / "notizen" / "straenge").mkdir(parents=True)
    return Buch(autor="Autor, A", titel="Werk", pfad=pfad)


def _strang(buch: Buch, dateiname: str, name: str | None, kapitel: list[tuple[int, str]]) -> None:
    kopf = f"---\nstrang: {name}\nslug: x\n---\n\n# Strang\n\n" if name else ""
    koerper = "".join(f"### Kapitel {nr} · {abschnitt}\n- These\n\n" for nr, abschnitt in kapitel)
    (buch.pfad / "notizen" / "straenge" / dateiname).write_text(kopf + koerper, encoding="utf-8")


def test_list_straenge_liefert_name_slug_und_kapitelnummern_aufsteigend(tmp_path):
    b = _buch(tmp_path)
    _strang(b, "herrschaft.md", "Herrschaft & Macht", [(9, "Neun"), (3, "Drei"), (5, "Fünf")])
    _strang(b, "markt.md", "Markt", [(2, "Zwei"), (5, "Fünf")])
    assert library.list_straenge(b) == [
        {"name": "Herrschaft & Macht", "slug": "herrschaft", "kapitel": [3, 5, 9]},
        {"name": "Markt", "slug": "markt", "kapitel": [2, 5]},
    ]


def test_list_straenge_ohne_kopf_nimmt_den_dateinamen_als_namen(tmp_path):
    b = _buch(tmp_path)
    _strang(b, "ohne-kopf.md", None, [(1, "Eins")])
    assert library.list_straenge(b) == [{"name": "ohne-kopf", "slug": "ohne-kopf", "kapitel": [1]}]


def test_list_straenge_doppelte_kapitelnummern_zaehlen_einmal(tmp_path):
    b = _buch(tmp_path)
    _strang(b, "a.md", "A", [(4, "x"), (4, "y"), (2, "z")])
    assert library.list_straenge(b)[0]["kapitel"] == [2, 4]


def test_list_straenge_strang_ohne_fundstelle_entfaellt(tmp_path):
    b = _buch(tmp_path)
    _strang(b, "leer.md", "Leer", [])
    _strang(b, "voll.md", "Voll", [(1, "Eins")])
    assert [s["slug"] for s in library.list_straenge(b)] == ["voll"]


def test_list_straenge_ueberspringt_konfliktdateien_und_kaputte_dateien(tmp_path):
    b = _buch(tmp_path)
    _strang(b, "gut.md", "Gut", [(1, "Eins")])
    _strang(b, "gut.sync-conflict-20261102-ABC.md", "Gut", [(7, "Sieben")])
    (b.pfad / "notizen" / "straenge" / "kaputt.md").write_bytes(b"\xff\xfe\x00 kein utf-8 \x80\x81")
    (b.pfad / "notizen" / "straenge" / "_strang_index.json").write_text("{}", encoding="utf-8")
    assert library.list_straenge(b) == [{"name": "Gut", "slug": "gut", "kapitel": [1]}]


def test_list_straenge_fehlender_ordner_ist_leer(tmp_path):
    pfad = tmp_path / "reader" / "A" / "W"
    pfad.mkdir(parents=True)
    assert library.list_straenge(Buch(autor="A", titel="W", pfad=pfad)) == []


def test_list_straenge_aendert_die_bestehenden_funktionen_nicht(temp_buch):
    """Regression: dieselben Daten, die read_straenge_* lesen, bleiben unveraendert."""
    vorher = (library.read_straenge_for_chapter(temp_buch, 1), library.read_straenge_uebersicht(temp_buch, 1))
    assert library.list_straenge(temp_buch)[0]["kapitel"] == [1]
    assert (library.read_straenge_for_chapter(temp_buch, 1), library.read_straenge_uebersicht(temp_buch, 1)) == vorher
