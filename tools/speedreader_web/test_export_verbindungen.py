"""Tests fuer export_verbindungen.py (Verbindungsdaten fuer die Ansicht "Verbindungen")."""
import json
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent))

import export_verbindungen as ev  # noqa: E402


def _werk(root: Path, autor: str, titel: str, straenge: dict[str, tuple[str, list[int]]] | None = None, querbezuege=None) -> Path:
    pfad = root / "reader" / autor / titel
    (pfad / "quelle").mkdir(parents=True)
    if straenge:
        (pfad / "notizen" / "straenge").mkdir(parents=True)
        for slug, (name, kapitel) in straenge.items():
            koerper = "".join(f"### Kapitel {nr} · Abschnitt {nr}\n- These\n\n" for nr in kapitel)
            (pfad / "notizen" / "straenge" / f"{slug}.md").write_text(f"---\nstrang: {name}\nslug: {slug}\n---\n\n# Strang\n\n{koerper}", encoding="utf-8")
    if querbezuege is not None:
        (pfad / "querbezuege").mkdir(parents=True)
        (pfad / "querbezuege" / "querbezuege.json").write_text(
            querbezuege if isinstance(querbezuege, str) else json.dumps(querbezuege, ensure_ascii=False), encoding="utf-8")
    return pfad


def _daten(*buecher) -> dict:
    """buecher: (autor, titel, [(nr, titel), ...]) in Reihenfolge; Ids b001, b002 ... wie export_daten."""
    return {"erstellt": "2026-11-03 10:00:00", "buecher": [
        {"id": f"b{i:03d}", "autor": a, "titel": t, "kapitel": [{"nr": nr, "titel": kt, "felder": {}} for nr, kt in kap]}
        for i, (a, t, kap) in enumerate(buecher, start=1)]}


KAP = [(1, "Eins"), (2, "Zwei"), (3, "Drei")]


def test_werke_und_kapitel_stammen_aus_daten_json_mit_stabilen_ids(tmp_path):
    _werk(tmp_path, "Müller, Äh", "Über Größe")
    _werk(tmp_path, "Zed, Z", "Zweites")
    daten = _daten(("Müller, Äh", "Über Größe", KAP), ("Zed, Z", "Zweites", [(7, "Sieben")]))
    basis = ev.baue_basis(tmp_path, daten)
    assert basis["werke"] == [{"id": "b001", "autor": "Müller, Äh", "titel": "Über Größe"}, {"id": "b002", "autor": "Zed, Z", "titel": "Zweites"}]
    assert [k["id"] for k in basis["kapitel"]] == ["b001:1", "b001:2", "b001:3", "b002:7"]
    assert basis["kapitel"][0] == {"id": "b001:1", "werk": "b001", "nr": 1, "titel": "Eins"}


def test_buecher_die_nur_im_dateisystem_oder_nur_in_daten_json_stehen_entfallen(tmp_path):
    _werk(tmp_path, "Nur, Platte", "Ohne Daten")
    _werk(tmp_path, "Beide, B", "Beide")
    basis = ev.baue_basis(tmp_path, _daten(("Beide, B", "Beide", KAP), ("Geist, G", "Nicht auf Platte", KAP)))
    assert [w["id"] for w in basis["werke"]] == ["b001"]
    assert all(k["werk"] == "b001" for k in basis["kapitel"])


def test_themen_filtern_kapitel_ohne_eintrag_in_daten_json_und_kleine_themen(tmp_path):
    _werk(tmp_path, "A, A", "W", straenge={"herrschaft": ("Herrschaft", [1, 3, 9]), "nur-eins": ("Nur eins", [2]),
                                         "ausserhalb": ("Außerhalb", [8, 9])})
    basis = ev.baue_basis(tmp_path, _daten(("A, A", "W", KAP)))
    assert basis["themen"] == [{"id": "b001#herrschaft", "werk": "b001", "name": "Herrschaft", "kapitel": [1, 3]}]


def test_gleicher_strang_slug_in_zwei_werken_ergibt_zwei_themen(tmp_path):
    for t in ("W1", "W2"):
        _werk(tmp_path, "A, A", t, straenge={"markt": ("Markt", [1, 2])})
    basis = ev.baue_basis(tmp_path, _daten(("A, A", "W1", KAP), ("A, A", "W2", KAP)))
    assert [t["id"] for t in basis["themen"]] == ["b001#markt", "b002#markt"]


def test_querverweis_auf_werk_in_bibliothek_und_in_daten_json_hat_eine_buch_id(tmp_path):
    _werk(tmp_path, "Schumpeter, Joseph", "Capitalism, Socialism and Democracy")
    _werk(tmp_path, "Quelle, Q", "Quellwerk", querbezuege={"bezuege": [{
        "ziel": "schumpeter_capitalism-socialism-and-democracy", "autor": "Schumpeter", "titel": "Capitalism, Socialism and Democracy",
        "relation": "ergaenzt", "notiz": "Demokratie als Wettbewerb."}]})
    basis = ev.baue_basis(tmp_path, _daten(("Quelle, Q", "Quellwerk", KAP), ("Schumpeter, Joseph", "Capitalism, Socialism and Democracy", KAP)))
    assert basis["querverweise"] == [{"von": "b001", "nach": "b002", "autor": "Schumpeter", "titel": "Capitalism, Socialism and Democracy",
                                      "relation": "ergaenzt", "notiz": "Demokratie als Wettbewerb."}]


def test_querverweis_auf_werk_ausserhalb_der_bibliothek_oder_ohne_eintrag_in_daten_json_hat_nach_null(tmp_path):
    _werk(tmp_path, "Da, D", "Vorhanden aber ohne Daten")
    _werk(tmp_path, "Quelle, Q", "Quellwerk", querbezuege={"bezuege": [
        {"ziel": "weber_wirtschaft-und-gesellschaft", "autor": "Weber", "titel": "Wirtschaft und Gesellschaft", "relation": "bezieht-sich-auf", "notiz": ""},
        {"ziel": "da_vorhanden-aber-ohne-daten", "autor": "Da", "titel": "Vorhanden aber ohne Daten", "relation": "ergaenzt", "notiz": "n"}]})
    basis = ev.baue_basis(tmp_path, _daten(("Quelle, Q", "Quellwerk", KAP)))
    assert [(q["nach"], q["titel"]) for q in basis["querverweise"]] == [(None, "Wirtschaft und Gesellschaft"), (None, "Vorhanden aber ohne Daten")]


def test_kaputte_oder_falsch_aufgebaute_querbezuege_werden_uebersprungen(tmp_path):
    _werk(tmp_path, "K1, K", "Kaputt", querbezuege="{kein json")
    _werk(tmp_path, "K2, K", "Keine Liste", querbezuege={"bezuege": 5})
    _werk(tmp_path, "K3, K", "Gemischt", querbezuege={"bezuege": [
        "text", 7, None, {"ziel": 5, "titel": "Zahl als Ziel"}, {"titel": "Ohne Ziel"}, {"ziel": "x_y", "titel": "Gut", "autor": "X", "relation": "ergaenzt"}]})
    basis = ev.baue_basis(tmp_path, _daten(("K1, K", "Kaputt", KAP), ("K2, K", "Keine Liste", KAP), ("K3, K", "Gemischt", KAP)))
    assert [q["titel"] for q in basis["querverweise"]] == ["Gut"] and basis["querverweise"][0]["von"] == "b003"


def test_querverweis_auf_sich_selbst_und_doppelte_entfallen(tmp_path):
    _werk(tmp_path, "Selbst, S", "Ich", querbezuege={"bezuege": [
        {"ziel": "selbst_ich", "titel": "Ich", "autor": "Selbst", "relation": "ergaenzt"},
        {"ziel": "x_y", "titel": "Y", "autor": "X", "relation": "ergaenzt"},
        {"ziel": "x_y", "titel": "Y", "autor": "X", "relation": "ergaenzt"}]})
    basis = ev.baue_basis(tmp_path, _daten(("Selbst, S", "Ich", KAP)))
    assert [(q["nach"], q["titel"]) for q in basis["querverweise"]] == [(None, "Y")]


def test_umlaute_in_titeln_bleiben_unveraendert_und_die_reihenfolge_ist_stabil(tmp_path):
    _werk(tmp_path, "Ä, Ö", "Ü", straenge={"b": ("Größe", [1, 2]), "a": ("Ärger", [1, 3])})
    daten = _daten(("Ä, Ö", "Ü", [(1, "Über"), (2, "Zwei"), (3, "Drei")]))
    erste = ev.baue_basis(tmp_path, daten)
    assert erste == ev.baue_basis(tmp_path, daten)
    assert [t["name"] for t in erste["themen"]] == ["Ärger", "Größe"]            # Dateireihenfolge a, b
    assert erste["kapitel"][0]["titel"] == "Über"


def test_querbezuege_datei_ohne_utf8_wird_uebersprungen(tmp_path):
    pfad = _werk(tmp_path, "A, A", "W", querbezuege={"bezuege": []})
    (pfad / "querbezuege" / "querbezuege.json").write_bytes(b'{"bezuege": [{"ziel": "x_y", "titel": "\xff\xfe"}]}')
    assert ev.baue_basis(tmp_path, _daten(("A, A", "W", KAP)))["querverweise"] == []
