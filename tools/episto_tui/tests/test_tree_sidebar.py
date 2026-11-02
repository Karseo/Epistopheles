import pytest
from textual.app import App, ComposeResult
from episto_tui.widgets.tree_sidebar import LibraryTree, ChapterSelected


class _BaumTestApp(App):
    def __init__(self, root):
        super().__init__()
        self.root = root
        self.letztes_ereignis: ChapterSelected | None = None

    def compose(self) -> ComposeResult:
        yield LibraryTree(self.root)

    def on_chapter_selected(self, event: ChapterSelected) -> None:
        self.letztes_ereignis = event


@pytest.mark.asyncio
async def test_baum_zeigt_buch_und_kapitel(tmp_path, temp_buch):
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        # ein Buch-Knoten mit zwei Kapitel-Blaettern
        bibliothek_knoten = list(baum.root.children)[0]
        buch_knoten = list(bibliothek_knoten.children)
        assert len(buch_knoten) == 1
        assert "Testbuch" in str(buch_knoten[0].label)
        assert len(buch_knoten[0].children) == 2


@pytest.mark.asyncio
async def test_tippfilterung_grenzt_kapitel_ein(tmp_path, temp_buch):
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        baum.focus()
        await pilot.press("slash", "z", "w", "e", "i")  # "zwei" -> nur "Zweites Kapitel"
        bibliothek_knoten = list(baum.root.children)[0]
        buch_knoten = list(bibliothek_knoten.children)
        assert len(buch_knoten) == 1
        assert len(buch_knoten[0].children) == 1
        assert "Zweites" in str(buch_knoten[0].children[0].label)


@pytest.mark.asyncio
async def test_escape_setzt_filter_zurueck(tmp_path, temp_buch):
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        baum.focus()
        await pilot.press("slash", "z", "w", "e", "i")
        await pilot.press("escape")
        bibliothek_knoten = list(baum.root.children)[0]
        buch_knoten = list(bibliothek_knoten.children)
        assert len(buch_knoten[0].children) == 2


@pytest.mark.asyncio
async def test_auswahl_eines_kapitels_feuert_chapter_selected(tmp_path, temp_buch):
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        bibliothek_knoten = list(baum.root.children)[0]
        buch_knoten = list(bibliothek_knoten.children)[0]
        kapitel_knoten = buch_knoten.children[0]
        baum.select_node(kapitel_knoten)
        await pilot.pause()
        assert app.letztes_ereignis is not None
        assert app.letztes_ereignis.kapitel.datei == "0001_erstes-kapitel.md"


@pytest.mark.asyncio
async def test_baum_zeigt_titel_mit_eckigen_klammern_woertlich(tmp_path, temp_buch):
    """I-3: Kapiteltitel aus _kapitel_index.json wurden als Rich-Markup
    gelesen -- "[b]" verschwand, "[/]" warf MarkupError."""
    import json
    (temp_buch.pfad / "quelle" / "_kapitel_index.json").write_text(
        json.dumps([
            {"nr": 1, "titel": "Kapitel [b]eins[/b] [/]", "datei": "0001_erstes-kapitel.md"},
            {"nr": 2, "titel": "Zweites Kapitel", "datei": "0002_zweites-kapitel.md"},
        ]),
        encoding="utf-8",
    )
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        baum = app.query_one(LibraryTree)
        bibliothek_knoten = list(baum.root.children)[0]
        buch_knoten = list(bibliothek_knoten.children)[0]
        assert buch_knoten.children[0].label.plain == "1. Kapitel [b]eins[/b] [/]"


def _schreibe_tags(buch_pfad, kapitel_eintraege) -> None:
    import json
    notizen = buch_pfad / "notizen"
    notizen.mkdir(parents=True, exist_ok=True)
    (notizen / "tags.json").write_text(
        json.dumps({"kapitel": kapitel_eintraege}, ensure_ascii=False), encoding="utf-8")


@pytest.mark.asyncio
async def test_baum_zeigt_begriffe_und_definitionen_abschnitt_bibliotheksweit(tmp_path):
    buch_a = tmp_path / "reader" / "Autor A" / "Buch A"
    buch_b = tmp_path / "reader" / "Autor B" / "Buch B"
    (buch_a / "quelle").mkdir(parents=True)
    (buch_b / "quelle").mkdir(parents=True)
    (buch_a / "quelle" / "0001_kap.md").write_text("Text A.", encoding="utf-8")
    (buch_b / "quelle" / "0001_kap.md").write_text("Text B.", encoding="utf-8")
    _schreibe_tags(buch_a, [{
        "datei": "0001_kap.md", "kapitel_nr": 1, "titel": "Kapitel A", "woerter": 1,
        "these": [], "gegen": [], "kern": ["Zebra"], "def": ["Anton ist der erste Begriff."],
        "beleg": [], "zusammenfassung": "",
    }])
    _schreibe_tags(buch_b, [{
        "datei": "0001_kap.md", "kapitel_nr": 1, "titel": "Kapitel B", "woerter": 1,
        "these": [], "gegen": [], "kern": ["apfel"], "def": [],
        "beleg": [], "zusammenfassung": "",
    }])

    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        wurzel_kinder = list(baum.root.children)
        assert len(wurzel_kinder) == 2
        assert "Bibliothek" in str(wurzel_kinder[0].label)
        begriffe_knoten = wurzel_kinder[1]
        assert "Begriffe" in str(begriffe_knoten.label)
        assert begriffe_knoten.is_expanded is False

        # Ohne (ausreichenden) Filter bleibt der Knoten leer -- siehe
        # test_begriffe_abschnitt_bleibt_ohne_filter_leer. "buch" matcht
        # per Buchtitel beide Buecher und damit alle drei Eintraege.
        baum.filter_text = "buch"
        baum.rebuild()
        begriffe_knoten = list(baum.root.children)[1]
        texte = [str(kind.label) for kind in begriffe_knoten.children]
        # Erwartete alphabetische (case-insensitive) Reihenfolge ueber BEIDE
        # Buecher hinweg, ohne Buch-Zwischenknoten. "Zebra" (Grossbuchstabe)
        # und "apfel" (Kleinbuchstabe) sortieren bei case-sensitiver
        # ASCII-Sortierung genau umgekehrt ("Zebra" vor "apfel", weil 'Z' <
        # 'a'); nur eine echte case-insensitive Sortierung liefert die hier
        # erwartete Reihenfolge und deckt damit das ".lower()" im Sortier-
        # schluessel tatsaechlich ab.
        assert texte == ["Anton ist der erste Begriff.", "apfel", "Zebra"]


@pytest.mark.asyncio
async def test_begriffe_abschnitt_bleibt_ohne_filter_leer(tmp_path):
    buch_a = tmp_path / "reader" / "Autor A" / "Buch A"
    (buch_a / "quelle").mkdir(parents=True)
    (buch_a / "quelle" / "0001_kap.md").write_text("Text A.", encoding="utf-8")
    _schreibe_tags(buch_a, [{
        "datei": "0001_kap.md", "kapitel_nr": 1, "titel": "Kapitel A", "woerter": 1,
        "these": [], "gegen": [], "kern": ["einzelbegriff"], "def": [],
        "beleg": [], "zusammenfassung": "",
    }])

    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        begriffe_knoten = list(baum.root.children)[1]
        kinder = list(begriffe_knoten.children)
        assert len(kinder) == 1
        assert kinder[0].data is None
        assert "2 Zeichen" in str(kinder[0].label)

        # Ein Zeichen reicht noch nicht.
        baum.filter_text = "e"
        baum.rebuild()
        begriffe_knoten = list(baum.root.children)[1]
        kinder = list(begriffe_knoten.children)
        assert len(kinder) == 1
        assert kinder[0].data is None

        # Ab zwei Zeichen wird gefiltert befuellt.
        baum.filter_text = "ei"
        baum.rebuild()
        begriffe_knoten = list(baum.root.children)[1]
        texte = [str(kind.label) for kind in begriffe_knoten.children]
        assert texte == ["einzelbegriff"]


@pytest.mark.asyncio
async def test_klick_auf_begriff_feuert_chapter_selected(tmp_path):
    buch_a = tmp_path / "reader" / "Autor A" / "Buch A"
    (buch_a / "quelle").mkdir(parents=True)
    (buch_a / "quelle" / "0001_kap.md").write_text("Text A.", encoding="utf-8")
    _schreibe_tags(buch_a, [{
        "datei": "0001_kap.md", "kapitel_nr": 1, "titel": "Kapitel A", "woerter": 1,
        "these": [], "gegen": [], "kern": ["einzelbegriff"], "def": [],
        "beleg": [], "zusammenfassung": "",
    }])

    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        baum.filter_text = "einzel"
        baum.rebuild()
        begriffe_knoten = list(baum.root.children)[1]
        begriff_blatt = list(begriffe_knoten.children)[0]
        baum.select_node(begriff_blatt)
        await pilot.pause()
        assert app.letztes_ereignis is not None
        assert app.letztes_ereignis.kapitel.datei == "0001_kap.md"
        assert app.letztes_ereignis.buch.titel == "Buch A"


@pytest.mark.asyncio
async def test_buch_ohne_kern_oder_def_erzeugt_keine_leeren_eintraege(tmp_path, temp_buch):
    # temp_buch (aus conftest) hat kern=["testbegriff"], def=[] fuer Kapitel 1
    # und gar keinen Tag-Eintrag fuer Kapitel 2 - beides darf nicht crashen
    # und darf keine leeren Blätter erzeugen.
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        baum.filter_text = "test"
        baum.rebuild()
        begriffe_knoten = list(baum.root.children)[1]
        texte = [str(kind.label) for kind in begriffe_knoten.children]
        assert texte == ["testbegriff"]


@pytest.mark.asyncio
async def test_aufklapp_zustand_bleibt_bei_tippfilterung_erhalten(tmp_path, temp_buch):
    """Important-Finding aus dem Review: rebuild() (von on_key bei jedem
    Tastendruck der Tippfilterung aufgerufen) legte beide Top-Level-Knoten
    bisher immer mit fest verdrahtetem expand=-Wert neu an, unabhaengig vom
    tatsaechlichen Nutzerzustand -- ein manuell aufgeklappter "Begriffe &
    Definitionen"-Knoten klappte bei jedem Tastendruck wieder zu."""
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        begriffe_knoten = list(baum.root.children)[1]
        assert begriffe_knoten.is_expanded is False
        begriffe_knoten.expand()
        await pilot.pause()
        assert begriffe_knoten.is_expanded is True

        baum.focus()
        await pilot.press("slash", "a")

        begriffe_knoten = list(baum.root.children)[1]
        assert begriffe_knoten.is_expanded is True


@pytest.mark.asyncio
async def test_tippfilterung_filtert_auch_begriffe_abschnitt(tmp_path):
    buch_a = tmp_path / "reader" / "Autor A" / "Buch A"
    (buch_a / "quelle").mkdir(parents=True)
    (buch_a / "quelle" / "0001_kap.md").write_text("Text A.", encoding="utf-8")
    _schreibe_tags(buch_a, [{
        "datei": "0001_kap.md", "kapitel_nr": 1, "titel": "Kapitel A", "woerter": 1,
        "these": [], "gegen": [], "kern": ["passend", "anderswert"], "def": [],
        "beleg": [], "zusammenfassung": "",
    }])

    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        baum.focus()
        await pilot.press("slash", "p", "a", "s", "s")  # "pass" -> nur "passend"
        begriffe_knoten = list(baum.root.children)[1]
        texte = [str(kind.label) for kind in begriffe_knoten.children]
        assert texte == ["passend"]


@pytest.mark.asyncio
async def test_filtertext_steht_in_der_kopfzeile(tmp_path, temp_buch):
    """Die Tippfilterung hat kein Eingabefeld: der getippte Text muss sichtbar
    sein (Kopfzeile des Baums), sonst weiss man nicht, was man getippt hat."""
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        baum.focus()
        assert "zum Filtern" in str(baum.border_title)
        await pilot.press("slash", "z", "w")
        assert "Filter: zw" in str(baum.border_title)
        await pilot.press("backspace")
        assert "Filter: z" in str(baum.border_title)
        assert "Filter: zw" not in str(baum.border_title)
        await pilot.press("escape")
        assert "Filter:" not in str(baum.border_title)


@pytest.mark.asyncio
async def test_filtertext_mit_eckigen_klammern_wird_woertlich_angezeigt(tmp_path, temp_buch):
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        baum.focus()
        await pilot.press("slash", "left_square_bracket", "slash", "right_square_bracket")
        await pilot.pause()
        assert app.is_running
        assert baum.filter_text == "[/]"
        assert "[/]" in str(baum.border_title)


@pytest.mark.asyncio
async def test_begriff_blatt_feuert_chapter_selected_mit_begriff_und_art(tmp_path, temp_buch):
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        baum.focus()
        await pilot.press("slash", "t", "e")  # >= 2 Zeichen: Begriffe-Knoten fuellt sich
        blatt = list(baum.root.children)[1].children[0]
        baum.select_node(blatt)
        await pilot.pause()
        ereignis = app.letztes_ereignis
        assert ereignis is not None
        assert ereignis.begriff == "testbegriff"
        assert ereignis.begriff_art == "Kernbegriff"
        assert ereignis.kapitel.nr == 1


@pytest.mark.asyncio
async def test_kapitel_blatt_hat_keinen_begriff(tmp_path, temp_buch):
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        kapitel_blatt = list(baum.root.children)[0].children[0].children[0]
        baum.select_node(kapitel_blatt)
        await pilot.pause()
        assert app.letztes_ereignis.begriff is None
        assert app.letztes_ereignis.begriff_art is None


@pytest.mark.asyncio
async def test_zeichen_ohne_filtermodus_aendern_den_filter_nicht(tmp_path, temp_buch):
    """Regression: der Baum schluckte jedes druckbare Zeichen, solange er den
    Fokus hatte, und blockierte so Hotkeys wie Ziffern und "q"."""
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        baum.focus()
        await pilot.press("z", "w", "3")
        assert baum.filter_text == ""
        assert baum.filter_aktiv is False
        assert "zum Filtern" in str(baum.border_title)


@pytest.mark.asyncio
async def test_slash_startet_filtermodus_und_enter_beendet_ihn(tmp_path, temp_buch):
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        baum.focus()
        await pilot.press("slash")
        assert baum.filter_aktiv is True
        assert "Enter: übernehmen" in str(baum.border_title)
        await pilot.press("z", "w", "enter")
        await pilot.pause()
        assert baum.filter_aktiv is False
        assert baum.filter_text == "zw"  # Filter bleibt bestehen
        assert "Filter: zw" in str(baum.border_title)
        # danach gehen Zeichen wieder nicht mehr in den Filter
        await pilot.press("x")
        assert baum.filter_text == "zw"


@pytest.mark.asyncio
async def test_escape_im_filtermodus_loescht_filter_und_beendet_modus(tmp_path, temp_buch):
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        baum.focus()
        await pilot.press("slash", "z", "w", "escape")
        assert baum.filter_aktiv is False
        assert baum.filter_text == ""


@pytest.mark.asyncio
async def test_fokusverlust_beendet_den_filtermodus(tmp_path, temp_buch):
    """Der Tippmodus darf nicht haengen bleiben, wenn der Fokus woanders hingeht."""
    app = _BaumTestApp(tmp_path)
    async with app.run_test() as pilot:
        baum = app.query_one(LibraryTree)
        baum.focus()
        await pilot.press("slash", "z")
        assert baum.filter_aktiv is True
        baum.blur()
        await pilot.pause()
        assert baum.filter_aktiv is False
        assert baum.filter_text == "z"
