from episto_tui import library
from episto_tui.models import Tag


def test_read_tags_findet_vorhandenes_kapitel(temp_buch):
    tag = library.read_tags(temp_buch, "0001_erstes-kapitel.md")
    assert tag is not None
    assert tag.these == ["Testthese"]
    assert tag.kern == ["testbegriff"]


def test_read_tags_gibt_none_fuer_ungetaggtes_kapitel(temp_buch):
    tag = library.read_tags(temp_buch, "0002_zweites-kapitel.md")
    assert tag is None


def test_read_tags_gibt_none_wenn_datei_fehlt(tmp_path):
    from episto_tui.models import Buch
    buch = Buch(autor="A", titel="B", pfad=tmp_path)
    assert library.read_tags(buch, "irgendwas.md") is None


def test_write_tag_ersetzt_vorhandenes_kapitel(temp_buch):
    neuer_tag = Tag(
        datei="0001_erstes-kapitel.md", kapitel_nr=1, titel="Erstes Kapitel",
        woerter=99, these=["Neue These"], gegen=[], kern=["neu"], def_=[],
        beleg=[], zusammenfassung="Neu.",
    )
    library.write_tag(temp_buch, neuer_tag)

    wieder_gelesen = library.read_tags(temp_buch, "0001_erstes-kapitel.md")
    assert wieder_gelesen.these == ["Neue These"]

    backups = list((temp_buch.pfad / "notizen" / "_backup").glob("tags.*.json"))
    assert len(backups) == 1


def test_write_tag_haengt_neues_kapitel_an(temp_buch):
    neuer_tag = Tag(
        datei="0002_zweites-kapitel.md", kapitel_nr=2, titel="Zweites Kapitel",
        woerter=5, these=["These 2"], gegen=[], kern=[], def_=[], beleg=[],
        zusammenfassung="",
    )
    library.write_tag(temp_buch, neuer_tag)

    assert library.read_tags(temp_buch, "0001_erstes-kapitel.md") is not None
    assert library.read_tags(temp_buch, "0002_zweites-kapitel.md").these == ["These 2"]


# --- I-1: kaputte/unerwartete tags.json darf nie abstuerzen -----------------

def _schreibe_tags_roh(buch, inhalt: str) -> None:
    (buch.pfad / "notizen" / "tags.json").write_text(inhalt, encoding="utf-8")


def test_read_tags_liste_statt_objekt_gibt_none(temp_buch):
    _schreibe_tags_roh(temp_buch, "[]")
    assert library.read_tags(temp_buch, "0001_erstes-kapitel.md") is None


def test_read_tags_zahl_statt_objekt_gibt_none(temp_buch):
    _schreibe_tags_roh(temp_buch, "42")
    assert library.read_tags(temp_buch, "0001_erstes-kapitel.md") is None


def test_read_tags_kapitel_als_dict_statt_liste_gibt_none(temp_buch):
    _schreibe_tags_roh(temp_buch, '{"kapitel": {"datei": "0001_erstes-kapitel.md"}}')
    assert library.read_tags(temp_buch, "0001_erstes-kapitel.md") is None


def test_read_tags_kapitel_als_zahl_gibt_none(temp_buch):
    _schreibe_tags_roh(temp_buch, '{"kapitel": 42}')
    assert library.read_tags(temp_buch, "0001_erstes-kapitel.md") is None


def test_read_tags_ueberspringt_nicht_dict_eintraege(temp_buch):
    _schreibe_tags_roh(
        temp_buch,
        '{"kapitel": [null, 7, "x", {"datei": "0001_erstes-kapitel.md", "these": ["T"]}]}',
    )
    tag = library.read_tags(temp_buch, "0001_erstes-kapitel.md")
    assert tag is not None
    assert tag.these == ["T"]


def test_read_tags_null_in_listenfeld_wird_entfernt(temp_buch):
    _schreibe_tags_roh(
        temp_buch,
        '{"kapitel": [{"datei": "0001_erstes-kapitel.md", "kapitel_nr": 1, '
        '"these": [null, "Echte These", 3], "gegen": [null], "kern": null, '
        '"def": [null], "beleg": "kein-array", "zusammenfassung": null}]}',
    )
    tag = library.read_tags(temp_buch, "0001_erstes-kapitel.md")
    assert tag is not None
    assert tag.these == ["Echte These", "3"]
    assert tag.gegen == []
    assert tag.kern == []
    assert tag.def_ == []
    assert tag.beleg == []
    assert tag.zusammenfassung == ""
    # darf nicht mehr crashen (vorher TypeError in TagsPane):
    assert "\n".join(tag.these) == "Echte These\n3"


def test_write_tag_bei_kaputter_datei_sichert_vorher(temp_buch):
    """Existiert tags.json, ist aber kein JSON-Objekt, wird zwar ein frisches
    Geruest geschrieben -- aber erst NACH dem Backup, der Altinhalt ist also
    nie verloren."""
    _schreibe_tags_roh(temp_buch, "[1, 2, 3]")
    library.write_tag(temp_buch, Tag(
        datei="0001_erstes-kapitel.md", kapitel_nr=1, titel="Erstes Kapitel",
        woerter=1, these=["Neu"],
    ))
    backups = list((temp_buch.pfad / "notizen" / "_backup").glob("tags.*.json"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "[1, 2, 3]"
    assert library.read_tags(temp_buch, "0001_erstes-kapitel.md").these == ["Neu"]


def test_write_tag_kapitel_kein_array_crasht_nicht(temp_buch):
    _schreibe_tags_roh(temp_buch, '{"werk": "Testbuch", "kapitel": {"kaputt": true}}')
    library.write_tag(temp_buch, Tag(
        datei="0002_zweites-kapitel.md", kapitel_nr=2, titel="Zweites Kapitel",
        woerter=1, these=["Z"],
    ))
    assert library.read_tags(temp_buch, "0002_zweites-kapitel.md").these == ["Z"]


def test_read_querbezuege_und_kommentare_ueberspringen_nicht_dicts(temp_buch):
    (temp_buch.pfad / "querbezuege" / "querbezuege.json").write_text(
        '{"bezuege": [null, "x", {"autor": "A"}]}', encoding="utf-8")
    assert library.read_querbezuege(temp_buch) == [{"autor": "A"}]
    (temp_buch.pfad / "querbezuege" / "querbezuege.json").write_text(
        '{"bezuege": 5}', encoding="utf-8")
    assert library.read_querbezuege(temp_buch) == []

    (temp_buch.pfad / "notizen" / "kommentare.json").write_text(
        '{"kommentare": [null, 1, {"datei": "0001_erstes-kapitel.md", "text": "ok"}]}',
        encoding="utf-8")
    kommentare = library.read_kommentare(temp_buch, "0001_erstes-kapitel.md")
    assert [k.text for k in kommentare] == ["ok"]
    (temp_buch.pfad / "notizen" / "kommentare.json").write_text("[]", encoding="utf-8")
    assert library.read_kommentare(temp_buch, "0001_erstes-kapitel.md") == []


def test_read_all_tags_liest_alle_kapitel_eines_buchs(tmp_path):
    import json
    from episto_tui.models import Buch
    buch_pfad = tmp_path / "reader" / "A" / "B"
    notizen = buch_pfad / "notizen"
    notizen.mkdir(parents=True)
    (notizen / "tags.json").write_text(json.dumps({
        "kapitel": [
            {
                "datei": "0001_erstes-kapitel.md", "kapitel_nr": 1,
                "titel": "Erstes Kapitel", "woerter": 10,
                "these": [], "gegen": [], "kern": ["begriff-eins"],
                "def": ["Begriff eins ist etwas."], "beleg": [], "zusammenfassung": "",
            },
            {
                "datei": "0002_zweites-kapitel.md", "kapitel_nr": 2,
                "titel": "Zweites Kapitel", "woerter": 8,
                "these": [], "gegen": [], "kern": ["begriff-zwei"],
                "def": [], "beleg": [], "zusammenfassung": "",
            },
        ],
    }, ensure_ascii=False), encoding="utf-8")
    buch = Buch(autor="A", titel="B", pfad=buch_pfad)

    alle_tags = library.read_all_tags(buch)

    assert len(alle_tags) == 2
    assert alle_tags[0].kern == ["begriff-eins"]
    assert alle_tags[0].def_ == ["Begriff eins ist etwas."]
    assert alle_tags[1].kern == ["begriff-zwei"]


def test_read_all_tags_ohne_datei_gibt_leere_liste(tmp_path):
    from episto_tui.models import Buch
    buch = Buch(autor="A", titel="B", pfad=tmp_path)
    assert library.read_all_tags(buch) == []


def test_read_all_tags_bei_kaputtem_json_gibt_leere_liste(tmp_path):
    from episto_tui.models import Buch
    buch_pfad = tmp_path / "reader" / "A" / "B"
    notizen = buch_pfad / "notizen"
    notizen.mkdir(parents=True)
    (notizen / "tags.json").write_text("[]", encoding="utf-8")
    buch = Buch(autor="A", titel="B", pfad=buch_pfad)
    assert library.read_all_tags(buch) == []


def test_read_all_tags_ueberspringt_nicht_dict_eintraege(tmp_path):
    import json
    from episto_tui.models import Buch
    buch_pfad = tmp_path / "reader" / "A" / "B"
    notizen = buch_pfad / "notizen"
    notizen.mkdir(parents=True)
    (notizen / "tags.json").write_text(json.dumps({
        "kapitel": [
            None,
            "kaputter Eintrag",
            {
                "datei": "0001_erstes-kapitel.md", "kapitel_nr": 1,
                "titel": "Erstes Kapitel", "woerter": 10,
                "these": [], "gegen": [], "kern": ["begriff"],
                "def": [], "beleg": [], "zusammenfassung": "",
            },
        ],
    }, ensure_ascii=False), encoding="utf-8")
    buch = Buch(autor="A", titel="B", pfad=buch_pfad)

    alle_tags = library.read_all_tags(buch)

    assert len(alle_tags) == 1
    assert alle_tags[0].kern == ["begriff"]
