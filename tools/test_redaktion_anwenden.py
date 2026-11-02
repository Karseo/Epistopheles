from __future__ import annotations

import json
from pathlib import Path

import pytest

import redaktion_anwenden as ra
from redaktion import ops, protokoll

BUCH = "Autor, Vorname/Titel"
ALT = "Erster Absatz mit Fehler hier.\n\nZweiter Absatz bleibt.\n"
NEU = "Erster Absatz ohne Fehler hier."


def eintrag(text_absatz: str = "Erster Absatz mit Fehler hier.", nachher: str = NEU,
            chunk: int = 1, ebene: str = "chunk-orig", index: int = 0) -> dict:
    return ops.neuer_eintrag(
        BUCH, ebene, {"chunk": chunk, "anfang": ops.anker_von(text_absatz), "absatz_index": index},
        "ersetzen", {"nachher": nachher}, text_absatz, geraet="test")


def baue(tmp: Path, text: str = ALT, sprache: str = "en", chunk: int = 1,
         en_chunks: bool = False, eintraege: list[dict] | None = None) -> Path:
    autor, titel = BUCH.split("/")
    lektor = tmp / "rohdaten" / "Lektor" / autor / titel
    ordner = lektor / ("de" if sprache == "de" else "en")
    ordner.mkdir(parents=True)
    (lektor / "meta.json").write_text(json.dumps({"quellsprache": sprache}), encoding="utf-8")
    (ordner / f"chunk_{chunk:03d}.md").write_bytes(text.encode("utf-8"))
    if en_chunks:
        ec = tmp / "rohdaten" / "en-chunks" / autor / titel
        ec.mkdir(parents=True)
        (ec / f"chunk_{chunk:03d}.md").write_bytes(text.encode("utf-8"))
    if eintraege is not None:
        protokoll.schreibe_eingang(tmp, "tablet", BUCH, eintraege)
    return tmp


def lektor(tmp: Path) -> Path:
    autor, titel = BUCH.split("/")
    return tmp / "rohdaten" / "Lektor" / autor / titel


def test_chunk_datei_en_und_de(tmp_path):
    baue(tmp_path)
    assert ra.chunk_datei(tmp_path, BUCH, 7) == lektor(tmp_path) / "en" / "chunk_007.md"
    (lektor(tmp_path) / "meta.json").write_text('{"quellsprache": "de"}', encoding="utf-8")
    assert ra.chunk_datei(tmp_path, BUCH, 7) == lektor(tmp_path) / "de" / "chunk_007.md"


def test_dry_run_aendert_nichts_und_nennt_die_aenderungen(tmp_path, capsys):
    baue(tmp_path, eintraege=[eintrag()])
    datei = ra.chunk_datei(tmp_path, BUCH, 1)
    vorher = datei.read_bytes()
    code = ra.main(["--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert datei.read_bytes() == vorher
    assert "ersetzen" in out and "Erster Absatz mit Fehler" in out
    assert not (lektor(tmp_path) / "redaktion.json").exists()
    assert not (lektor(tmp_path) / "notizen").exists()
    assert protokoll.lade_stand(tmp_path, BUCH) == {}


def test_ausfuehren_schreibt_chunk_mit_backup_und_vermerkt_redaktion_json(tmp_path):
    e = eintrag()
    baue(tmp_path, eintraege=[e])
    datei = ra.chunk_datei(tmp_path, BUCH, 1)
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    assert datei.read_text(encoding="utf-8") == NEU + "\n\nZweiter Absatz bleibt.\n"
    backups = list((lektor(tmp_path) / "notizen" / "_backup").glob("chunk_001.*.md"))
    assert len(backups) == 1 and backups[0].read_bytes() == ALT.encode("utf-8")
    red = protokoll.lade_redaktion(lektor(tmp_path) / "redaktion.json")
    assert red["chunks"]["1"]["hash_original"] == ops.pruefsumme(ALT)
    assert red["chunks"]["1"]["zuletzt"]
    assert [x["id"] for x in red["eintraege"]] == [e["id"]]
    assert red["eintraege"][0]["status"] == "angewendet"
    assert protokoll.lade_stand(tmp_path, BUCH)[e["id"]]["status"] == "angewendet"


def test_konflikt_bleibt_liegen_und_setzt_status_konflikt(tmp_path, capsys):
    e = eintrag()
    baue(tmp_path, eintraege=[e])
    datei = ra.chunk_datei(tmp_path, BUCH, 1)
    geaendert = ALT.replace("mit Fehler", "mit anderem Fehler").encode("utf-8")
    datei.write_bytes(geaendert)
    code = ra.main(["--root", str(tmp_path), "--ausfuehren"])
    out = capsys.readouterr().out
    assert code == 2
    assert datei.read_bytes() == geaendert
    assert "Konflikt" in out
    st = protokoll.lade_stand(tmp_path, BUCH)[e["id"]]
    assert st["status"] == "konflikt" and st["grund"]
    assert not (lektor(tmp_path) / "redaktion.json").exists()


def test_konflikt_auch_im_dry_run_exit_2(tmp_path):
    baue(tmp_path, eintraege=[eintrag()])
    ra.chunk_datei(tmp_path, BUCH, 1).write_text("ganz anderer Text\n", encoding="utf-8")
    assert ra.main(["--root", str(tmp_path)]) == 2
    assert protokoll.lade_stand(tmp_path, BUCH) == {}


def test_en_chunks_kopie_wird_mitgezogen(tmp_path):
    baue(tmp_path, en_chunks=True, eintraege=[eintrag()])
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    autor, titel = BUCH.split("/")
    kopie = tmp_path / "rohdaten" / "en-chunks" / autor / titel / "chunk_001.md"
    assert kopie.read_text(encoding="utf-8") == NEU + "\n\nZweiter Absatz bleibt.\n"
    assert len(list((lektor(tmp_path) / "notizen" / "_backup").glob("chunk_001.*.md"))) == 2


def test_deutsche_quelle_schreibt_in_de(tmp_path):
    baue(tmp_path, sprache="de", en_chunks=True, eintraege=[eintrag()])
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    assert (lektor(tmp_path) / "de" / "chunk_001.md").read_text(encoding="utf-8").startswith(NEU)
    autor, titel = BUCH.split("/")
    # bei deutscher Quelle wird en-chunks nicht angefasst
    kopie = tmp_path / "rohdaten" / "en-chunks" / autor / titel / "chunk_001.md"
    assert kopie.read_text(encoding="utf-8") == ALT


def test_eingang_datei_wird_eingelesen_ohne_server(tmp_path):
    baue(tmp_path)
    e = eintrag()
    datei = tmp_path / "aenderungen.json"
    datei.write_text(json.dumps({"geraet": "tablet", "buch": BUCH, "eintraege": [e]}), encoding="utf-8")
    assert ra.main(["--root", str(tmp_path), "--eingang", str(datei), "--ausfuehren"]) == 0
    assert ra.chunk_datei(tmp_path, BUCH, 1).read_text(encoding="utf-8").startswith(NEU)
    assert [x["id"] for x in protokoll.lade_eingang(tmp_path, BUCH)] == [e["id"]]
    # idempotent: zweiter Lauf legt keine zweite Datei an
    assert ra.main(["--root", str(tmp_path), "--eingang", str(datei)]) == 0
    ordner = protokoll.eingang_ordner(tmp_path, BUCH)
    assert len([p for p in ordner.glob("*.json") if p.name != "_stand.json"]) == 1


@pytest.mark.parametrize("inhalt", ["kein json", "[1, 2]", '{"buch": "A/B"}',
                                    '{"geraet": "x", "buch": "../..", "eintraege": []}',
                                    '{"geraet": "x", "buch": "A/B", "eintraege": "nein"}'])
def test_eingang_ungueltige_datei_exit_1(tmp_path, capsys, inhalt):
    baue(tmp_path)
    datei = tmp_path / "x.json"
    datei.write_text(inhalt, encoding="utf-8")
    assert ra.main(["--root", str(tmp_path), "--eingang", str(datei)]) == 1
    assert capsys.readouterr().err
    assert ra.main(["--root", str(tmp_path), "--eingang", str(tmp_path / "fehlt.json")]) == 1


def test_crlf_und_tabs_bleiben_ausserhalb_des_absatzes_byteexakt(tmp_path):
    alt = "Kopf\twort\r\n\r\nZiel Absatz alt\r\nzweite Zeile\r\n\r\nSchluss\tohne Newline"
    absatz = "Ziel Absatz alt\r\nzweite Zeile"
    e = eintrag(absatz, "Ziel Absatz neu", index=1)
    baue(tmp_path, text=alt, eintraege=[e])
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    soll = alt.replace(absatz, "Ziel Absatz neu").encode("utf-8")
    assert ra.chunk_datei(tmp_path, BUCH, 1).read_bytes() == soll


def test_ungueltiger_ordnername_stuerzt_nicht_ab(tmp_path, capsys, monkeypatch):
    e = eintrag()
    baue(tmp_path, eintraege=[e])
    echt = protokoll.liste_buecher
    # Windows lässt manche unzulässigen Ordnernamen gar nicht erst anlegen: Liste simulieren
    monkeypatch.setattr(protokoll, "liste_buecher", lambda root: ["Autor/Titel.", *echt(root)])
    plaene = ra.plane(tmp_path)
    assert any("ungültiger Ordnername" in (p.hinweis or "") for p in plaene)
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    assert "ungültiger Ordnername, übersprungen" in capsys.readouterr().out
    assert ra.chunk_datei(tmp_path, BUCH, 1).read_text(encoding="utf-8").startswith(NEU)


def test_zurueckgenommener_eintrag_wird_nicht_angewendet(tmp_path):
    e = eintrag()
    r = ops.neuer_eintrag(BUCH, "chunk-orig", {"chunk": 1}, "ruecknahme", {"id": e["id"]}, "")
    baue(tmp_path, eintraege=[e, r])
    datei = ra.chunk_datei(tmp_path, BUCH, 1)
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    assert datei.read_bytes() == ALT.encode("utf-8")


def test_ruecknahme_verhindert_anwendung(tmp_path, capsys):
    """Ziel und Rücknahme in beliebiger Reihenfolge und auch aus getrennten Sendungen: nie angewendet."""
    e = eintrag()
    r = ops.neuer_eintrag(BUCH, "chunk-orig", {"chunk": 1}, "ruecknahme", {"id": e["id"]}, "", geraet="test")
    baue(tmp_path)
    protokoll.schreibe_eingang(tmp_path, "tablet", BUCH, [r])            # Rücknahme zuerst, Ziel später
    protokoll.schreibe_eingang(tmp_path, "tablet", BUCH, [e])
    datei = ra.chunk_datei(tmp_path, BUCH, 1)
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    assert datei.read_bytes() == ALT.encode("utf-8")
    assert "Rücknahme von Eintrag" in capsys.readouterr().out
    stand = protokoll.lade_stand(tmp_path, BUCH)
    assert e["id"] not in stand and stand[r["id"]]["status"] == "uebersprungen"
    assert not (lektor(tmp_path) / "notizen" / "_backup").exists()        # nichts geschrieben, kein Backup


def test_ruecknahme_nach_anwendung_ist_konflikt_und_aendert_nichts(tmp_path, capsys):
    e = eintrag()
    baue(tmp_path, eintraege=[e])
    datei = ra.chunk_datei(tmp_path, BUCH, 1)
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    angewendet = datei.read_bytes()
    r = ops.neuer_eintrag(BUCH, "chunk-orig", {"chunk": 1}, "ruecknahme", {"id": e["id"]}, "", geraet="test")
    protokoll.schreibe_eingang(tmp_path, "tablet", BUCH, [r])
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0        # kein Textkonflikt, Exit 0
    assert datei.read_bytes() == angewendet                                # Rücknahme macht nichts rückgängig
    out = capsys.readouterr().out
    assert "schon angewendet" in out
    assert "1 Rücknahmen nicht möglich" in out and "0 übersprungen" in out      # gesondert, nicht als übersprungen gezählt
    stand = protokoll.lade_stand(tmp_path, BUCH)
    assert stand[e["id"]]["status"] == "angewendet"
    assert stand[r["id"]]["status"] == "konflikt" and "nicht möglich" in stand[r["id"]]["grund"]


def test_andere_ebenen_werden_uebersprungen_und_gezaehlt(tmp_path, capsys):
    baue(tmp_path, eintraege=[eintrag(ebene="volltext")])
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    out = capsys.readouterr().out
    assert "übersprungen (Ebene volltext)" in out
    assert ra.chunk_datei(tmp_path, BUCH, 1).read_bytes() == ALT.encode("utf-8")


def test_lektor_ordner_fehlt_ist_konflikt(tmp_path, capsys):
    protokoll.schreibe_eingang(tmp_path, "tablet", BUCH, [eintrag()])
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 2
    assert "Lektor-Ordner fehlt" in capsys.readouterr().out


def test_zweiter_lauf_wendet_nichts_an_und_hash_original_bleibt(tmp_path):
    e1 = eintrag()
    baue(tmp_path, eintraege=[e1])
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    datei = ra.chunk_datei(tmp_path, BUCH, 1)
    nach_eins = datei.read_bytes()
    pfad = lektor(tmp_path) / "redaktion.json"
    hash1 = protokoll.lade_redaktion(pfad)["chunks"]["1"]["hash_original"]
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    assert datei.read_bytes() == nach_eins
    # neuer Eintrag spaeter: hash_original bleibt der des Urzustands
    e2 = eintrag("Zweiter Absatz bleibt.", "Zweiter Absatz ist neu.", index=1)
    protokoll.schreibe_eingang(tmp_path, "tablet", BUCH, [e2])
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    red = protokoll.lade_redaktion(pfad)
    assert red["chunks"]["1"]["hash_original"] == hash1 == ops.pruefsumme(ALT)
    assert [x["id"] for x in red["eintraege"]] == [e1["id"], e2["id"]]


def test_buch_filter(tmp_path):
    baue(tmp_path, eintraege=[eintrag()])
    assert ra.plane(tmp_path, buch="Anderer/Titel") == []
    assert len(ra.plane(tmp_path, buch=BUCH)) == 1


# ----------------------------------------------------------------- Fix-Runde 1

def _zwei_chunks(tmp_path):
    e1 = eintrag()
    e2 = eintrag(chunk=2)
    baue(tmp_path, en_chunks=True, eintraege=[e1, e2])
    ordner = lektor(tmp_path) / "en"
    (ordner / "chunk_002.md").write_bytes(ALT.encode("utf-8"))
    autor, titel = BUCH.split("/")
    (tmp_path / "rohdaten" / "en-chunks" / autor / titel / "chunk_002.md").write_bytes(ALT.encode("utf-8"))
    return e1, e2


def test_spiegel_fehler_chunk_bleibt_erfasst_warnung_exit_nonzero(tmp_path, monkeypatch, capsys):
    e1, e2 = _zwei_chunks(tmp_path)
    echt = ra._schreibe_text

    def schreibe(pfad, text):
        if "en-chunks" in pfad.parts and pfad.name == "chunk_001.md":
            raise OSError("gesperrt")
        echt(pfad, text)

    monkeypatch.setattr(ra, "_schreibe_text", schreibe)
    code = ra.main(["--root", str(tmp_path), "--ausfuehren"])
    out = capsys.readouterr().out
    assert code not in (0, 1)
    assert "WARNUNG" in out and "gesperrt" in out
    assert ra.chunk_datei(tmp_path, BUCH, 1).read_text(encoding="utf-8").startswith(NEU)
    assert ra.chunk_datei(tmp_path, BUCH, 2).read_text(encoding="utf-8").startswith(NEU)
    red = protokoll.lade_redaktion(lektor(tmp_path) / "redaktion.json")
    assert red["chunks"]["1"]["hash_original"] == ops.pruefsumme(ALT)
    assert {x["id"] for x in red["eintraege"]} == {e1["id"], e2["id"]}
    stand = protokoll.lade_stand(tmp_path, BUCH)
    assert stand[e1["id"]]["status"] == "angewendet" and stand[e2["id"]]["status"] == "angewendet"


def test_redaktion_json_schreibfehler_vor_chunk_schreiben_laesst_chunk_unberuehrt(tmp_path, monkeypatch, capsys):
    e = eintrag()
    baue(tmp_path, eintraege=[e])
    datei = ra.chunk_datei(tmp_path, BUCH, 1)

    def kaputt(pfad, daten):
        raise OSError("keine Berechtigung")

    monkeypatch.setattr(protokoll, "speichere_redaktion", kaputt)
    code = ra.main(["--root", str(tmp_path), "--ausfuehren"])
    assert code not in (0, 1)
    assert "keine Berechtigung" in capsys.readouterr().out
    assert datei.read_bytes() == ALT.encode("utf-8")
    assert protokoll.lade_stand(tmp_path, BUCH).get(e["id"], {}).get("status") != "angewendet"


def test_drift_zwischen_plan_und_ausfuehren_ist_konflikt_exit_2(tmp_path, monkeypatch):
    e = eintrag()
    baue(tmp_path, eintraege=[e])
    datei = ra.chunk_datei(tmp_path, BUCH, 1)
    plaene = ra.plane(tmp_path)
    anders = ALT.replace("Zweiter", "Dritter").encode("utf-8")
    datei.write_bytes(anders)
    monkeypatch.setattr(ra, "plane", lambda *a, **k: plaene)
    code = ra.main(["--root", str(tmp_path), "--ausfuehren"])
    assert code == 2
    assert datei.read_bytes() == anders
    assert protokoll.lade_stand(tmp_path, BUCH)[e["id"]]["status"] == "konflikt"


@pytest.mark.parametrize("inhalt", ["{kaputt", "[1]", '{"chunks": [], "eintraege": []}',
                                    '{"chunks": {}, "eintraege": {}}'])
def test_kaputte_redaktion_json_wird_nicht_ueberschrieben(tmp_path, capsys, inhalt):
    e = eintrag()
    baue(tmp_path, eintraege=[e])
    pfad = lektor(tmp_path) / "redaktion.json"
    pfad.write_text(inhalt, encoding="utf-8")
    datei = ra.chunk_datei(tmp_path, BUCH, 1)
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 2
    assert "redaktion.json unlesbar" in capsys.readouterr().out
    assert datei.read_bytes() == ALT.encode("utf-8")
    assert pfad.read_text(encoding="utf-8") == inhalt


def test_eintrag_ohne_id_oder_kein_dict_stuerzt_nicht_ab(tmp_path, monkeypatch, capsys):
    gut = eintrag()
    baue(tmp_path)
    ohne_id = {k: v for k, v in eintrag().items() if k != "id"}
    monkeypatch.setattr(protokoll, "lade_eingang", lambda root, buch: [ohne_id, "text", gut])
    monkeypatch.setattr(protokoll, "liste_buecher", lambda root: [BUCH])
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 2
    assert "Eintrag ohne id" in capsys.readouterr().out
    assert ra.chunk_datei(tmp_path, BUCH, 1).read_text(encoding="utf-8").startswith(NEU)


# --- Task 13: Übersetzung übernehmen -------------------------------------------------------

DE_ALT = "Alte Übersetzung.\r\n\r\nZweiter Absatz.\n"
DE_NEU = "Neue Übersetzung mit Änderung.\n\nZweiter Absatz.\n"


def uebernahme(alt: str = DE_ALT, neu: str | None = DE_NEU, chunk: int = 1, **ueberschreibe) -> dict:
    parameter = {} if neu is None else {"neu_hash": ops.pruefsumme(neu)}
    e = ops.neuer_eintrag(BUCH, "uebersetzung", {"chunk": chunk}, "uebersetzung-uebernehmen",
                          parameter, alt, "Vergleich geprüft", geraet="test")
    e.update(ueberschreibe)
    return e


def baue_de(tmp: Path, alt: str | None = DE_ALT, neu: str | None = DE_NEU, e: dict | None = None,
            chunk: int = 1) -> Path:
    baue(tmp, eintraege=[e if e is not None else uebernahme(chunk=chunk)], chunk=chunk)
    de = lektor(tmp) / "de"
    de.mkdir(exist_ok=True)
    if alt is not None:
        (de / f"chunk_{chunk:03d}.md").write_bytes(alt.encode("utf-8"))
    if neu is not None:
        (de / f"chunk_{chunk:03d}.md.neu").write_bytes(neu.encode("utf-8"))
    return de


def test_uebernehmen_ersetzt_de_chunk_mit_backup(tmp_path, capsys):
    e = uebernahme()
    de = baue_de(tmp_path, e=e)
    original = ra.chunk_datei(tmp_path, BUCH, 1)
    original_vorher = original.read_bytes()
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    assert (de / "chunk_001.md").read_bytes() == DE_NEU.encode("utf-8")
    assert not (de / "chunk_001.md.neu").exists()                              # .neu danach gelöscht
    backups = list((lektor(tmp_path) / "notizen" / "_backup").glob("chunk_001.*.md"))
    assert len(backups) == 1 and backups[0].read_bytes() == DE_ALT.encode("utf-8")      # Sicherung der alten Übersetzung
    assert original.read_bytes() == original_vorher                                   # Original-Chunk unberührt
    assert protokoll.lade_stand(tmp_path, BUCH)[e["id"]]["status"] == "angewendet"
    red = protokoll.lade_redaktion(lektor(tmp_path) / "redaktion.json")
    assert [x["id"] for x in red["eintraege"]] == [e["id"]]
    assert "Übersetzung übernehmen" in capsys.readouterr().out
    # zweiter Lauf: nichts mehr zu tun
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    assert (de / "chunk_001.md").read_bytes() == DE_NEU.encode("utf-8")


def test_uebernehmen_wiederholung_nach_teilausfall_ist_angewendet_nicht_konflikt(tmp_path, monkeypatch, capsys):
    e = uebernahme()
    de = baue_de(tmp_path, e=e)
    echt = protokoll.setze_stand

    def kaputt(*a, **k):
        raise OSError("Platte voll")
    monkeypatch.setattr(protokoll, "setze_stand", kaputt)
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 3          # geschrieben, Stand fehlt
    assert (de / "chunk_001.md").read_bytes() == DE_NEU.encode("utf-8")
    assert not (de / "chunk_001.md.neu").exists()
    assert e["id"] not in protokoll.lade_stand(tmp_path, BUCH)
    monkeypatch.setattr(protokoll, "setze_stand", echt)
    capsys.readouterr()
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0          # kein Konflikt
    assert protokoll.lade_stand(tmp_path, BUCH)[e["id"]]["status"] == "angewendet"
    assert (de / "chunk_001.md").read_bytes() == DE_NEU.encode("utf-8")
    assert len(list((lektor(tmp_path) / "notizen" / "_backup").glob("chunk_001.*.md"))) == 1    # kein zweites Backup


def _pruefe_grund_pfadfrei(tmp_path, capsys, e):
    out = capsys.readouterr().out
    konflikt_zeile = [z for z in out.splitlines() if "Konflikt:" in z]
    assert konflikt_zeile and all("geheim" not in z and str(tmp_path) not in z for z in konflikt_zeile)
    assert "nicht geschrieben (OSError)" in konflikt_zeile[0]
    assert "geheim" in out                                        # die volle Meldung bleibt im Bericht (Warnung)
    stand = protokoll.lade_stand(tmp_path, BUCH).get(e["id"], {})
    assert "geheim" not in json.dumps(stand) and str(tmp_path) not in json.dumps(stand)    # nichts im API-Stand
    assert stand.get("status") != "konflikt" or stand["grund"] == "nicht geschrieben (OSError)"


def test_stand_grund_enthaelt_keine_pfade_chunk(tmp_path, monkeypatch, capsys):
    e = eintrag()
    baue(tmp_path, eintraege=[e])

    def kaputt(pfad, daten):
        raise OSError(f"kein Zugriff auf {tmp_path}/geheim/privat/x.md")
    monkeypatch.setattr(ra, "_schreibe_text", kaputt)
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 2
    _pruefe_grund_pfadfrei(tmp_path, capsys, e)


def test_stand_grund_enthaelt_keine_pfade_uebernahme(tmp_path, monkeypatch, capsys):
    e = uebernahme()
    baue_de(tmp_path, e=e)

    def kaputt(pfad, daten):
        raise OSError(f"kein Zugriff auf {tmp_path}/geheim/privat/x.md")
    monkeypatch.setattr(ra, "_schreibe_text", kaputt)
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 2
    _pruefe_grund_pfadfrei(tmp_path, capsys, e)


def test_stand_fehlt_nach_schreiben_zweiter_lauf_trägt_nur_nach(tmp_path, monkeypatch):
    e = eintrag()
    baue(tmp_path, eintraege=[e])
    datei = ra.chunk_datei(tmp_path, BUCH, 1)
    echt = protokoll.setze_stand

    def kaputt(*a, **k):
        raise OSError("Platte voll")
    monkeypatch.setattr(protokoll, "setze_stand", kaputt)
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 3
    geschrieben = datei.read_bytes()
    assert geschrieben != ALT.encode("utf-8")
    monkeypatch.setattr(protokoll, "setze_stand", echt)
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0          # kein Scheinkonflikt, nichts doppelt
    assert datei.read_bytes() == geschrieben
    assert protokoll.lade_stand(tmp_path, BUCH)[e["id"]]["status"] == "angewendet"
    assert len(list((lektor(tmp_path) / "notizen" / "_backup").glob("chunk_001.*.md"))) == 1
    red = protokoll.lade_redaktion(lektor(tmp_path) / "redaktion.json")
    assert [x["id"] for x in red["eintraege"]] == [e["id"]]


def test_uebernehmen_neu_noch_da_und_de_gleich_neu_ist_bereits(tmp_path, capsys):
    e = uebernahme()
    de = baue_de(tmp_path, alt=DE_NEU, neu=DE_NEU, e=e)               # Abbruch zwischen Schreiben und unlink
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    assert not (de / "chunk_001.md.neu").exists()
    assert (de / "chunk_001.md").read_bytes() == DE_NEU.encode("utf-8")
    assert not (lektor(tmp_path) / "notizen" / "_backup").exists() or not list(
        (lektor(tmp_path) / "notizen" / "_backup").glob("chunk_001.*.md"))      # kein zweites Backup
    assert protokoll.lade_stand(tmp_path, BUCH)[e["id"]]["status"] == "angewendet"


def test_uebernehmen_neu_anders_als_de_wird_nicht_als_bereits_geloescht(tmp_path):
    e = uebernahme()
    de = baue_de(tmp_path, alt=DE_NEU, neu=DE_NEU + "Neuer Vorschlag.\n", e=e)
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 2
    assert (de / "chunk_001.md.neu").exists()


def test_uebernehmen_ohne_neu_und_fremder_de_text_bleibt_konflikt(tmp_path):
    e = uebernahme()
    baue_de(tmp_path, alt="Etwas ganz anderes.\n", neu=None, e=e)
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 2


def test_uebernehmen_im_dry_run_schreibt_nichts(tmp_path, capsys):
    de = baue_de(tmp_path)
    assert ra.main(["--root", str(tmp_path)]) == 0
    assert (de / "chunk_001.md").read_bytes() == DE_ALT.encode("utf-8")
    assert (de / "chunk_001.md.neu").read_bytes() == DE_NEU.encode("utf-8")
    assert not (lektor(tmp_path) / "notizen").exists()
    assert protokoll.lade_stand(tmp_path, BUCH) == {}
    out = capsys.readouterr().out
    assert "Übersetzung übernehmen" in out and "würde angewendet" in out


def test_uebernehmen_ohne_neu_datei_ist_konflikt(tmp_path, capsys):
    e = uebernahme()
    de = baue_de(tmp_path, neu=None, e=e)
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 2
    assert (de / "chunk_001.md").read_bytes() == DE_ALT.encode("utf-8")
    st = protokoll.lade_stand(tmp_path, BUCH)[e["id"]]
    assert st["status"] == "konflikt" and ".neu" in st["grund"]
    assert not (lektor(tmp_path) / "notizen" / "_backup").exists()


def test_uebernehmen_konflikt_wenn_de_chunk_sich_geaendert_hat(tmp_path):
    de = baue_de(tmp_path, alt="Inzwischen anders bearbeitet.\n")                 # vorher.hash passt nicht mehr
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 2
    assert (de / "chunk_001.md").read_bytes() == b"Inzwischen anders bearbeitet.\n"
    assert (de / "chunk_001.md.neu").is_file()                                      # Vorschlag bleibt liegen


def test_uebernehmen_konflikt_wenn_vorschlag_nach_dem_vergleich_ersetzt_wurde(tmp_path):
    de = baue_de(tmp_path, neu="Ein anderer, später erzeugter Vorschlag.\n")      # neu_hash passt nicht mehr
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 2
    assert (de / "chunk_001.md").read_bytes() == DE_ALT.encode("utf-8")
    assert (de / "chunk_001.md.neu").is_file()


def test_uebernehmen_drift_zwischen_plan_und_ausfuehren_ist_konflikt(tmp_path, monkeypatch):
    de = baue_de(tmp_path)
    plaene = ra.plane(tmp_path)
    (de / "chunk_001.md").write_bytes(b"Zwischendurch geaendert\n")
    ergebnis = ra.fuehre_aus(tmp_path, plaene)
    assert ergebnis["konflikte"] == 1 and ergebnis["angewendet"] == 0
    assert (de / "chunk_001.md").read_bytes() == b"Zwischendurch geaendert\n"
    assert (de / "chunk_001.md.neu").is_file()


def test_uebernehmen_bei_deutscher_quelle_ist_konflikt(tmp_path):
    e = uebernahme()
    baue(tmp_path, sprache="de", eintraege=[e])
    (lektor(tmp_path) / "de" / "chunk_001.md.neu").write_bytes(DE_NEU.encode("utf-8"))
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 2
    assert (lektor(tmp_path) / "de" / "chunk_001.md").read_bytes() == ALT.encode("utf-8")


def test_zurueckgenommene_uebernahme_wird_nicht_angewendet(tmp_path):
    e = uebernahme()
    r = ops.neuer_eintrag(BUCH, "uebersetzung", {"chunk": 1}, "ruecknahme", {"id": e["id"]}, "")
    de = baue_de(tmp_path, e=e)
    protokoll.schreibe_eingang(tmp_path, "tablet", BUCH, [r])
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    assert (de / "chunk_001.md").read_bytes() == DE_ALT.encode("utf-8")
    assert (de / "chunk_001.md.neu").is_file()


@pytest.mark.parametrize("ziel", [{}, {"chunk": -1}, {"chunk": "1"}, {"chunk": True}])
def test_uebernehmen_ohne_gueltige_chunknummer_ist_konflikt(tmp_path, ziel):
    e = uebernahme(ziel=ziel)
    de = baue_de(tmp_path, e=e)
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 2
    assert (de / "chunk_001.md").read_bytes() == DE_ALT.encode("utf-8")


def test_uebernehmen_loest_keine_andere_aenderung_aus_und_laesst_original_chunk_byteidentisch(tmp_path):
    de = baue_de(tmp_path)
    ersetzen = eintrag()
    protokoll.schreibe_eingang(tmp_path, "tablet", BUCH, [ersetzen])
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    assert ra.chunk_datei(tmp_path, BUCH, 1).read_text(encoding="utf-8").startswith(NEU)
    assert (de / "chunk_001.md").read_bytes() == DE_NEU.encode("utf-8")


# ----------------------------------------------------------------- P2 Task 2: Lektor-Schlüssel und Sprache

LEKTOR_ALT = "Cathy O'Neil/Weapons of Math Destruction"       # Lektor-Ordner heißt anders als das Bibliotheksbuch


def _mit_ziel(e: dict, **ziel) -> dict:
    e = dict(e)
    e["ziel"] = {**e["ziel"], **ziel}
    return e


def _baue_abweichend(tmp: Path, sprache_ordner: str = "en", quellsprache: str = "en",
                     eintraege=None, lektor_schluessel: str = LEKTOR_ALT) -> Path:
    autor, titel = lektor_schluessel.split("/")
    lek = tmp / "rohdaten" / "Lektor" / autor / titel
    (lek / sprache_ordner).mkdir(parents=True)
    (lek / "meta.json").write_text(json.dumps({"quellsprache": quellsprache}), encoding="utf-8")
    (lek / sprache_ordner / "chunk_001.md").write_bytes(ALT.encode("utf-8"))
    if eintraege is not None:
        protokoll.schreibe_eingang(tmp, "tablet", BUCH, eintraege)
    return lek


def test_lektor_schluessel_im_ziel_ueberschreibt_den_buchschluessel(tmp_path, capsys):
    lek = _baue_abweichend(tmp_path, eintraege=[_mit_ziel(eintrag(), lektor=LEKTOR_ALT)])
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    assert (lek / "en" / "chunk_001.md").read_text(encoding="utf-8").startswith(NEU)
    assert (lek / "redaktion.json").is_file()
    assert not (tmp_path / "rohdaten" / "Lektor" / "Autor, Vorname").exists()      # nichts am Bibliotheksnamen angelegt


def test_unsicherer_lektor_schluessel_ist_konflikt(tmp_path, capsys):
    for schlecht in ("../x/y", "A/../B", "/abs/y", "A", "A/B/C", 5):
        protokoll_root = tmp_path / str(abs(hash(str(schlecht))))
        baue(protokoll_root, eintraege=[_mit_ziel(eintrag(), lektor=schlecht)])
        assert ra.main(["--root", str(protokoll_root), "--ausfuehren"]) == 2
        assert "Lektor-Schlüssel" in capsys.readouterr().out
        assert ra.chunk_datei(protokoll_root, BUCH, 1).read_text(encoding="utf-8") == ALT       # nichts geschrieben


def test_sprache_en_bei_deutscher_quelle_schreibt_in_en(tmp_path):
    """Popper: Quelle deutsch, Rohchunks englisch."""
    lek = _baue_abweichend(tmp_path, sprache_ordner="en", quellsprache="de",
                           lektor_schluessel=BUCH, eintraege=[_mit_ziel(eintrag(), sprache="en")])
    assert ra.chunk_datei(tmp_path, BUCH, 1, {"sprache": "en"}) == lek / "en" / "chunk_001.md"
    assert ra.chunk_datei(tmp_path, BUCH, 1) == lek / "de" / "chunk_001.md"             # ohne Ziel wie bisher
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    assert (lek / "en" / "chunk_001.md").read_text(encoding="utf-8").startswith(NEU)


@pytest.mark.parametrize("sprache", ["fr", "../en", "", 3, "EN"])
def test_sprache_ausserhalb_der_whitelist_ist_konflikt(tmp_path, capsys, sprache):
    baue(tmp_path, eintraege=[_mit_ziel(eintrag(), sprache=sprache)])
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 2
    assert "Sprache" in capsys.readouterr().out
    assert ra.chunk_datei(tmp_path, BUCH, 1).read_text(encoding="utf-8") == ALT


def test_ohne_lektor_und_sprache_unveraendertes_verhalten(tmp_path):
    baue(tmp_path, eintraege=[eintrag()])
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    assert ra.chunk_datei(tmp_path, BUCH, 1).read_text(encoding="utf-8").startswith(NEU)


def test_uneinheitliches_ziel_im_selben_buch_ist_konflikt(tmp_path, capsys):
    """Ein Lauf bearbeitet je Buch genau einen Lektor-Ordner; abweichende Einträge bleiben liegen."""
    lek = _baue_abweichend(tmp_path)
    e1 = _mit_ziel(eintrag(), lektor=LEKTOR_ALT)
    e2 = _mit_ziel(eintrag("Zweiter Absatz bleibt.", "Zweiter neu.", index=1), lektor="Anderer/Ordner")
    protokoll.schreibe_eingang(tmp_path, "tablet", BUCH, [e1, e2])
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 2
    out = capsys.readouterr().out
    assert "uneinheitliches Ziel" in out
    text = (lek / "en" / "chunk_001.md").read_text(encoding="utf-8")
    assert text.startswith(NEU) and "Zweiter Absatz bleibt." in text


def test_en_chunks_kopie_folgt_dem_lektor_schluessel(tmp_path):
    lek = _baue_abweichend(tmp_path, eintraege=[_mit_ziel(eintrag(), lektor=LEKTOR_ALT)])
    ec = tmp_path / "rohdaten" / "en-chunks" / "Cathy O'Neil" / "Weapons of Math Destruction"
    ec.mkdir(parents=True)
    (ec / "chunk_001.md").write_bytes(ALT.encode("utf-8"))
    assert ra.main(["--root", str(tmp_path), "--ausfuehren"]) == 0
    assert (ec / "chunk_001.md").read_text(encoding="utf-8").startswith(NEU)
