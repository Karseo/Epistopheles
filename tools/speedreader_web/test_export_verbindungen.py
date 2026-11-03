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


# --- Task 4: exportiere und main ---------------------------------------------------------------------------------

import os  # noqa: E402

import pytest  # noqa: E402

from test_qdrant_nachbarn import FakeQdrant, payload  # noqa: E402


def _paket(root: Path, daten: dict) -> Path:
    paket = root / "reader" / "export-epistopheles"
    paket.mkdir(parents=True, exist_ok=True)
    (paket / "daten.json").write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
    return paket


@pytest.fixture()
def welt(tmp_path):
    """Zwei Werke mit je zwei Kapiteln, ein Strang, ein Querverweis; Qdrant-Attrappe mit passenden Punkten."""
    _werk(tmp_path, "A, A", "Alpha", straenge={"macht": ("Macht", [1, 2])},
          querbezuege={"bezuege": [{"ziel": "b_beta", "autor": "B", "titel": "Beta", "relation": "ergaenzt", "notiz": ""}]})
    _werk(tmp_path, "B, B", "Beta")
    daten = _daten(("A, A", "Alpha", [(1, "Eins"), (2, "Zwei")]), ("B, B", "Beta", [(1, "Eins"), (2, "Zwei")]))
    paket = _paket(tmp_path, daten)
    punkte = {1: payload("A, A", "Alpha", 1, 0), 2: payload("A, A", "Alpha", 2, 0), 3: payload("B, B", "Beta", 1, 0, "Beleg über Größe"),
              4: payload("B, B", "Beta", 2, 0)}
    nachbarn = {1: [(3, 0.9), (4, 0.7)], 2: [(4, 0.8)], 3: [(1, 0.9)], 4: [(2, 0.8), (1, 0.7)]}
    fake = FakeQdrant(punkte, nachbarn)
    yield tmp_path, paket, daten, fake
    fake.stop()


def test_vollstaendiger_export_hat_alle_felder_und_gleiches_erstellt_wie_daten_json(welt):
    root, paket, daten, fake = welt
    erg = ev.exportiere(root, qdrant=fake.url, pause=0)
    d = json.loads((paket / "verbindungen.json").read_text(encoding="utf-8"))
    assert d == erg["verbindungen"] and erg["warnungen"] == []
    assert d["version"] == 1 and d["erstellt"] == "2026-11-03 10:00:00"
    assert d["qdrant"] == {"abgefragt": 4, "fehlend": 0, "mindestwert": ev.MINDESTWERT}
    assert [w["id"] for w in d["werke"]] == ["b001", "b002"] and len(d["kapitel"]) == 4
    assert d["themen"] == [{"id": "b001#macht", "werk": "b001", "name": "Macht", "kapitel": [1, 2]}]
    assert [(q["von"], q["nach"]) for q in d["querverweise"]] == [("b001", "b002")]
    paare = {(k["von"], k["nach"]) for k in d["aehnlich"]}
    assert paare == {("b001:1", "b002:1"), ("b001:1", "b002:2"), ("b001:2", "b002:2"), ("b002:1", "b001:1"), ("b002:2", "b001:2"), ("b002:2", "b001:1")}
    assert next(k for k in d["aehnlich"] if (k["von"], k["nach"]) == ("b001:1", "b002:1"))["beleg"] == "Beleg über Größe"
    assert not list(paket.glob("*.tmp")) and not list(paket.glob("verbindungen.json.*"))      # kein Rest der atomaren Schreibung


def test_nur_lesende_aufrufe_an_qdrant(welt):
    root, _, _, fake = welt
    ev.exportiere(root, qdrant=fake.url, pause=0)
    assert fake.anfragen and all(a[0] in ("GET", "POST") and not a[1].endswith(("/delete", "/payload")) for a in fake.anfragen)


def test_ohne_qdrant_bleiben_themen_und_querverweise(welt):
    root, paket, _, _ = welt
    erg = ev.exportiere(root, qdrant=None)
    d = erg["verbindungen"]
    assert d["aehnlich"] == [] and d["qdrant"] is None and len(d["themen"]) == 1 and len(d["querverweise"]) == 1
    assert erg["warnungen"]


def test_qdrant_nicht_erreichbar_gibt_warnung_und_leeren_aehnlichkeitsteil(welt):
    root, paket, _, _ = welt
    erg = ev.exportiere(root, qdrant="http://127.0.0.1:9", pause=0, versuche=1)
    assert erg["verbindungen"]["aehnlich"] == [] and erg["verbindungen"]["qdrant"] is None
    assert any("Qdrant" in w for w in erg["warnungen"])
    assert (paket / "verbindungen.json").is_file()


def test_ausfall_mitten_im_lauf_wird_gezaehlt_und_gemeldet_nie_still_vollstaendig(welt):
    root, paket, _, fake = welt
    fake.batch_500 = True
    fake.immer_500 = {2, 4}                                     # fuer diese Chunks scheitert jede Abfrage
    erg = ev.exportiere(root, qdrant=fake.url, pause=0, versuche=1)
    d = erg["verbindungen"]
    assert d["qdrant"]["fehlend"] == 2 and d["qdrant"]["abgefragt"] == 4
    assert any("2" in w and "fehl" in w.lower() for w in erg["warnungen"])
    assert {k["von"] for k in d["aehnlich"]} == {"b001:1", "b002:1"}      # nur das Bekannte, aber ausdruecklich als unvollstaendig markiert


def test_fehlende_daten_json_ist_ein_fehler_und_die_alte_datei_bleibt(tmp_path):
    paket = tmp_path / "reader" / "export-epistopheles"
    paket.mkdir(parents=True)
    (paket / "verbindungen.json").write_text('{"alt": true}', encoding="utf-8")
    with pytest.raises(ValueError, match="export_daten.py"):
        ev.exportiere(tmp_path, qdrant=None)
    assert (paket / "verbindungen.json").read_text(encoding="utf-8") == '{"alt": true}'


def test_kaputte_daten_json_ist_ein_fehler(tmp_path):
    paket = tmp_path / "reader" / "export-epistopheles"
    paket.mkdir(parents=True)
    (paket / "daten.json").write_text("{kaputt", encoding="utf-8")
    with pytest.raises(ValueError, match="daten.json"):
        ev.exportiere(tmp_path, qdrant=None)


def test_schreibfehler_laesst_die_alte_datei_und_keinen_rest(welt, monkeypatch):
    root, paket, _, _ = welt
    (paket / "verbindungen.json").write_text('{"alt": true}', encoding="utf-8")

    def kaputt(*a, **k):
        raise OSError("Platte voll")
    monkeypatch.setattr(os, "replace", kaputt)
    with pytest.raises(OSError):
        ev.exportiere(root, qdrant=None)
    assert (paket / "verbindungen.json").read_text(encoding="utf-8") == '{"alt": true}'
    assert not [p for p in paket.iterdir() if p.name not in ("daten.json", "verbindungen.json")]


def test_groesse_fuer_950_kapitel_mit_8_kanten_unter_2_mb(tmp_path):
    """Review Focus 4: kuenstliche Bibliothek in Normalgroesse, Belege mit Umlauten und der vollen Laenge."""
    n_werke, je = 80, 12
    kapitel = [{"id": f"b{w:03d}:{k}", "werk": f"b{w:03d}", "nr": k, "titel": f"Kapitel {k} über Größe"} for w in range(1, n_werke + 1) for k in range(1, je + 1)]
    ids = [k["id"] for k in kapitel]
    beleg = ("Ärger über Größe und Übung " * 7)[:140]
    aehnlich = [{"von": ids[i], "nach": ids[(i * 7 + j * 13 + 5) % len(ids)], "wert": round(0.55 + (i * j % 40) / 100, 3), "beleg": beleg}
                for i in range(len(ids)) for j in range(1, 9)]
    d = {"version": 1, "erstellt": "x", "qdrant": {"abgefragt": 1, "fehlend": 0, "mindestwert": 0.55}, "werke": [], "kapitel": kapitel,
         "themen": [], "aehnlich": aehnlich, "querverweise": []}
    ev._schreibe_json(tmp_path / "v.json", d)
    assert len(kapitel) == 960 and (tmp_path / "v.json").stat().st_size < 2 * 1024 * 1024


def test_main_vollstaendig_exit_0_mit_zusammenfassung(welt, capsys):
    root, paket, _, fake = welt
    assert ev.main(["--root", str(root), "--qdrant", fake.url]) == 0
    out = capsys.readouterr().out
    assert "2 Werke" in out and "4 Kapitel" in out and "Ähnlichkeitskanten" in out and "verbindungen.json" in out


def test_main_ohne_qdrant_ausdruecklich_gewaehlt_ist_exit_0(welt, capsys):
    root, paket, _, _ = welt
    assert ev.main(["--root", str(root), "--ohne-qdrant"]) == 0
    assert json.loads((paket / "verbindungen.json").read_text(encoding="utf-8"))["qdrant"] is None


def test_main_qdrant_nicht_erreichbar_ist_exit_3_und_ausfall_mitten_im_lauf_ebenfalls(welt, capsys):
    root, paket, _, fake = welt
    assert ev.main(["--root", str(root), "--qdrant", "http://127.0.0.1:9", "--versuche", "1", "--pause", "0"]) == 3
    assert "WARNUNG" in capsys.readouterr().out
    fake.batch_500, fake.immer_500 = True, {2}
    assert ev.main(["--root", str(root), "--qdrant", fake.url, "--versuche", "1", "--pause", "0"]) == 3


def test_main_ohne_daten_json_ist_exit_1_mit_hinweis(tmp_path, capsys):
    assert ev.main(["--root", str(tmp_path), "--ohne-qdrant"]) == 1
    assert "export_daten.py" in capsys.readouterr().err
