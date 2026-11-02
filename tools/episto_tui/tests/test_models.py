from episto_tui.models import Tag, Kommentar


def test_tag_round_trip():
    tag = Tag(
        datei="0001_vorwort.md", kapitel_nr=1, titel="Vorwort", woerter=100,
        these=["These 1"], gegen=[], kern=["kern1", "kern2"], def_=[],
        beleg=["Beleg 1"], zusammenfassung="Kurz.",
    )
    wiederhergestellt = Tag.from_dict(tag.to_dict())
    assert wiederhergestellt == tag


def test_tag_from_dict_mit_fehlenden_feldern():
    tag = Tag.from_dict({"datei": "x.md"})
    assert tag.these == []
    assert tag.zusammenfassung == ""


def test_kommentar_round_trip():
    kommentar = Kommentar(
        datei="0001_vorwort.md", absatz_index=2, absatz_anfang="Der erste Satz",
        text="Nachfragen bei Popper", erstellt="2026-09-27 14:00",
    )
    wiederhergestellt = Kommentar.from_dict(kommentar.to_dict())
    assert wiederhergestellt == kommentar


def test_highlight_round_trip():
    from episto_tui.models import Highlight
    highlight = Highlight(
        datei="0001_vorwort.md", absatz_index=2, absatz_anfang="Der erste Satz",
        farbe="gelb",
    )
    wiederhergestellt = Highlight.from_dict(highlight.to_dict())
    assert wiederhergestellt == highlight


def test_kommentar_kennung_wird_nur_gespeichert_wenn_vorhanden():
    ohne = Kommentar(datei="a.md", absatz_index=0, absatz_anfang="A", text="t", erstellt="e")
    assert "id" not in ohne.to_dict()
    mit = Kommentar(datei="a.md", absatz_index=0, absatz_anfang="A", text="t", erstellt="e", id="abc123")
    assert mit.to_dict()["id"] == "abc123"
    assert Kommentar.from_dict(mit.to_dict()) == mit
    assert Kommentar.from_dict(ohne.to_dict()).id == ""
