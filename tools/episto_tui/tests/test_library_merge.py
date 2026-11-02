import json
from episto_tui import library
from episto_tui.models import Kommentar, Highlight


def _schreibe(pfad, daten):
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")


def _kommentar(text, erstellt="2026-10-01 10:00", absatz_index=0, id=""):
    return Kommentar(datei="0001_erstes-kapitel.md", absatz_index=absatz_index,
                     absatz_anfang="Erster Absatz", text=text, erstellt=erstellt, id=id)


def test_add_kommentar_vergibt_kennung_und_findet_ihn_wieder(temp_buch):
    k = _kommentar("Alt")
    library.add_kommentar(temp_buch, k)
    assert k.id  # am Objekt gesetzt
    assert library.read_kommentare(temp_buch, k.datei)[0].id == k.id

    library.update_kommentar(temp_buch, k, "Neu")
    assert library.read_kommentare(temp_buch, k.datei)[0].text == "Neu"
    library.remove_kommentar(temp_buch, k)
    assert library.read_kommentare(temp_buch, k.datei) == []


def test_zwei_gleiche_kommentare_sind_ueber_kennung_unterscheidbar(temp_buch):
    a, b = _kommentar("Gleich"), _kommentar("Gleich")
    library.add_kommentar(temp_buch, a)
    library.add_kommentar(temp_buch, b)
    library.remove_kommentar(temp_buch, b)
    rest = library.read_kommentare(temp_buch, a.datei)
    assert [k.id for k in rest] == [a.id]


def test_altbestand_ohne_kennung_bleibt_aenderbar(temp_buch):
    notizen = temp_buch.pfad / "notizen"
    alt = _kommentar("Altbestand")
    _schreibe(notizen / "kommentare.json", {"werk": "x", "kommentare": [alt.to_dict()]})
    assert "id" not in alt.to_dict()
    library.update_kommentar(temp_buch, alt, "Geaendert")
    assert library.read_kommentare(temp_buch, alt.datei)[0].text == "Geaendert"


def test_merge_ohne_konfliktkopien_tut_nichts(temp_buch):
    assert library.merge_konflikte(temp_buch) == 0


def test_merge_kommentare_vereinigt_und_raeumt_kopie_weg(temp_buch):
    notizen = temp_buch.pfad / "notizen"
    pc = _kommentar("Vom PC", erstellt="2026-10-01 10:00", id="aaa")
    handy = _kommentar("Vom Handy", erstellt="2026-10-01 09:00", id="bbb")
    _schreibe(notizen / "kommentare.json", {"werk": "x", "kommentare": [pc.to_dict()]})
    _schreibe(notizen / "kommentare.sync-conflict-20261001-120000-ABCDEFG.json",
              {"werk": "x", "kommentare": [handy.to_dict()]})

    assert library.merge_konflikte(temp_buch) == 1

    texte = [k.text for k in library.read_kommentare(temp_buch, pc.datei)]
    assert texte == ["Vom Handy", "Vom PC"]  # nach Erstellzeit
    assert not list(notizen.glob("*.sync-conflict-*"))
    assert list((notizen / "_backup").glob("kommentare.sync-conflict-*.json"))
    # zweiter Lauf: nichts mehr zu tun, nichts doppelt
    assert library.merge_konflikte(temp_buch) == 0
    assert len(library.read_kommentare(temp_buch, pc.datei)) == 2


def test_merge_kommentare_dupliziert_nicht(temp_buch):
    notizen = temp_buch.pfad / "notizen"
    k = _kommentar("Beidseitig", id="aaa")
    ohne_id = _kommentar("Altbestand")
    _schreibe(notizen / "kommentare.json",
              {"kommentare": [k.to_dict(), ohne_id.to_dict()]})
    _schreibe(notizen / "kommentare.sync-conflict-20261001-120000-ABCDEFG.json",
              {"kommentare": [k.to_dict(), ohne_id.to_dict()]})
    library.merge_konflikte(temp_buch)
    assert len(library.read_kommentare(temp_buch, k.datei)) == 2


def test_merge_highlights_hauptdatei_gewinnt_bei_gleichem_absatz(temp_buch):
    notizen = temp_buch.pfad / "notizen"
    datei = "0001_erstes-kapitel.md"
    _schreibe(notizen / "highlights.json", {"highlights": [
        Highlight(datei, 0, "Erster", "gelb").to_dict()]})
    _schreibe(notizen / "highlights.sync-conflict-20261001-120000-ABCDEFG.json", {"highlights": [
        Highlight(datei, 0, "Erster", "blau").to_dict(),
        Highlight(datei, 2, "Dritter", "rosa").to_dict()]})
    library.merge_konflikte(temp_buch)
    farben = {h.absatz_index: h.farbe for h in library.read_highlights(temp_buch, datei)}
    assert farben == {0: "gelb", 2: "rosa"}


def test_merge_tags_ergaenzt_nur_fehlende_kapitel(temp_buch):
    notizen = temp_buch.pfad / "notizen"
    haupt = json.loads((notizen / "tags.json").read_text(encoding="utf-8"))
    fremd = json.loads(json.dumps(haupt))
    fremd["kapitel"][0]["zusammenfassung"] = "Fassung des anderen Geraets"
    fremd["kapitel"].append({"datei": "0002_zweites-kapitel.md", "kapitel_nr": 2,
                             "titel": "Zweites Kapitel", "woerter": 5})
    _schreibe(notizen / "tags.sync-conflict-20261001-120000-ABCDEFG.json", fremd)
    library.merge_konflikte(temp_buch)
    assert library.read_tags(temp_buch, "0001_erstes-kapitel.md").zusammenfassung == "Kurze Zusammenfassung."
    assert library.read_tags(temp_buch, "0002_zweites-kapitel.md") is not None
    assert json.loads((notizen / "tags.json").read_text(encoding="utf-8"))["eintraege"] == 2


def test_merge_laesst_unlesbare_kopie_liegen(temp_buch):
    notizen = temp_buch.pfad / "notizen"
    kaputt = notizen / "kommentare.sync-conflict-20261001-120000-ABCDEFG.json"
    kaputt.write_text("{kein json", encoding="utf-8")
    assert library.merge_konflikte(temp_buch) == 0
    assert kaputt.exists()


def test_merge_ohne_hauptdatei_uebernimmt_die_kopie(temp_buch):
    notizen = temp_buch.pfad / "notizen"
    k = _kommentar("Nur in der Kopie", id="ccc")
    _schreibe(notizen / "kommentare.sync-conflict-20261001-120000-ABCDEFG.json",
              {"werk": "x", "kommentare": [k.to_dict()]})
    assert library.merge_konflikte(temp_buch) == 1
    assert library.read_kommentare(temp_buch, k.datei)[0].text == "Nur in der Kopie"


def test_merge_alle_konflikte_ueber_die_ganze_bibliothek(temp_buch):
    root = temp_buch.pfad.parents[2]
    notizen = temp_buch.pfad / "notizen"
    _schreibe(notizen / "kommentare.sync-conflict-20261001-120000-ABCDEFG.json",
              {"kommentare": [_kommentar("X", id="ddd").to_dict()]})
    assert library.merge_alle_konflikte(root) == 1
