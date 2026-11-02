import json
import pytest
from textual.widgets import OptionList, Input, TabbedContent
from episto_tui import library, notizen
from episto_tui.app import EpistoApp
from episto_tui.models import Buch, Kapitel, Kommentar, Highlight
from episto_tui.widgets.notizen_screen import NotizenScreen
from episto_tui.widgets.querbezuege_pane import QuerbezuegePane
from episto_tui.widgets.reader_pane import ReaderPane
from episto_tui.widgets.straenge_pane import StraengePane
from episto_tui.widgets.tree_sidebar import LibraryTree

K1 = Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md")
K2 = Kapitel(2, "Zweites Kapitel", "0002_zweites-kapitel.md")


def _neues_buch(tmp_path, autor, titel, kapitel=("Einziges Kapitel",)):
    pfad = tmp_path / "reader" / autor / titel
    (pfad / "quelle").mkdir(parents=True)
    for i, name in enumerate(kapitel, start=1):
        (pfad / "quelle" / f"{i:04d}_k{i}.md").write_text(f"Text von {name}.", encoding="utf-8")
    return Buch(autor=autor, titel=titel, pfad=pfad)


# --- library ----------------------------------------------------------------

def test_kapitel_nachbar(temp_buch):
    assert library.kapitel_nachbar(temp_buch, K1, +1).datei == K2.datei
    assert library.kapitel_nachbar(temp_buch, K2, -1).datei == K1.datei
    assert library.kapitel_nachbar(temp_buch, K1, -1) is None
    assert library.kapitel_nachbar(temp_buch, K2, +1) is None
    assert library.kapitel_nachbar(temp_buch, Kapitel(9, "x", "gibt-es-nicht.md"), +1) is None


def test_root_von(tmp_path, temp_buch):
    assert library.root_von(temp_buch) == tmp_path


def test_finde_buch_fuer_ziel(tmp_path):
    a = _neues_buch(tmp_path, "Schumpeter, Joseph A", "Capitalism, Socialism and Democracy")
    best = _neues_buch(tmp_path, "Best, Heinrich", "Democratic Elitism")
    piano = _neues_buch(tmp_path, "Piano, Natasha", "Democratic Elitism")
    buecher = [a, best, piano]
    assert library.finde_buch_fuer_ziel(buecher, "schumpeter_capitalism-socialism-and-democracy") == a
    assert library.finde_buch_fuer_ziel(buecher, "piano_democratic-elitism") == piano
    assert library.finde_buch_fuer_ziel(buecher, "best_democratic-elitism") == best
    assert library.finde_buch_fuer_ziel(buecher, "mosca_elementi-di-scienza-politica") is None
    assert library.finde_buch_fuer_ziel(buecher, "ohne-unterstrich") is None


def test_finde_buch_fuer_ziel_mit_umlauten(tmp_path):
    b = _neues_buch(tmp_path, "Han, Byung-Chul", "Psychopolitik – Neoliberalismus und die neuen Machttechniken")
    assert library.finde_buch_fuer_ziel(
        [b], "han_psychopolitik-neoliberalismus-und-die-neuen-machttechniken") == b
    assert library._slug("Größe über Ärger") == "groesse-ueber-aerger"


def test_straenge_uebersicht_nennt_andere_kapitel(temp_buch):
    (temp_buch.pfad / "notizen" / "straenge" / "test-strang.md").write_text(
        "---\nstrang: Test-Strang\n---\n\n"
        "### Kapitel 1 · Erstes Kapitel\n- a\n\n### Kapitel 2 · Zweites Kapitel\n- b\n",
        encoding="utf-8")
    uebersicht = library.read_straenge_uebersicht(temp_buch, 1)
    assert uebersicht == [{"strang": "Test-Strang", "andere": [(2, "Zweites Kapitel")]}]
    # Nur ein Kapitel -> nichts Weiteres zum Springen
    assert library.read_straenge_uebersicht(temp_buch, 2)[0]["andere"] == [(1, "Erstes Kapitel")]


def test_straenge_uebersicht_leer_ohne_andere_kapitel(temp_buch):
    assert library.read_straenge_uebersicht(temp_buch, 1) == []  # Fixture: Strang nur in Kapitel 1


def test_leseposition_rundlauf_und_fehlerfaelle(tmp_path, temp_buch):
    assert library.lade_leseposition(tmp_path) is None
    library.speichere_leseposition(temp_buch, K2, 7)
    buch, kapitel, absatz = library.lade_leseposition(tmp_path)
    assert (buch.titel, kapitel.datei, absatz) == ("Testbuch", K2.datei, 7)
    # Kapitel verschwunden -> keine Position
    library.speichere_leseposition(temp_buch, Kapitel(3, "x", "weg.md"), 0)
    assert library.lade_leseposition(tmp_path) is None
    # kaputte Zustandsdatei -> keine Position, kein Absturz
    library.zustand_pfad().write_text("{kaputt", encoding="utf-8")
    assert library.lade_leseposition(tmp_path) is None


def test_zustand_schreibfehler_wirft_nicht(monkeypatch, tmp_path):
    blockiert = tmp_path / "datei"
    blockiert.write_text("x", encoding="utf-8")
    monkeypatch.setenv("EPISTO_ZUSTAND", str(blockiert / "unterordner" / "z.json"))
    library.speichere_zustand({"a": 1})  # Elternpfad ist eine Datei -> OSError, still


# --- notizen ----------------------------------------------------------------

def _notizen_anlegen(temp_buch):
    library.add_kommentar(temp_buch, Kommentar(
        datei=K1.datei, absatz_index=1, absatz_anfang="Zweiter Absatz mit mehr",
        text="Mit Popper vergleichen", erstellt="2026-10-31 10:00"))
    library.write_highlight(temp_buch, Highlight(
        datei=K2.datei, absatz_index=0, absatz_anfang="Einziger Absatz", farbe="gelb"))


def test_sammle_und_filtere_notizen(tmp_path, temp_buch):
    assert notizen.sammle_notizen(tmp_path) == []
    _notizen_anlegen(temp_buch)
    alle = notizen.sammle_notizen(tmp_path)
    assert [(n.art, n.kapitel.nr) for n in alle] == [("Kommentar", 1), ("Highlight", 2)]
    assert [n.art for n in notizen.filtere(alle, "gelb")] == ["Highlight"]
    assert [n.art for n in notizen.filtere(alle, "KOMMENTAR popper")] == ["Kommentar"]
    assert notizen.filtere(alle, "popper gelb") == []
    assert len(notizen.filtere(alle, "")) == 2
    assert len(notizen.sammle_notizen(tmp_path, nur_buch=temp_buch)) == 2


def test_notiz_zu_geloeschtem_kapitel_wird_uebersprungen(tmp_path, temp_buch):
    library.write_highlight(temp_buch, Highlight(datei="weg.md", absatz_index=0, absatz_anfang="x", farbe="rosa"))
    assert notizen.sammle_notizen(tmp_path) == []


def test_sprungabsatz_folgt_verschobenem_text(tmp_path, temp_buch):
    _notizen_anlegen(temp_buch)
    kommentar = notizen.sammle_notizen(tmp_path)[0]
    assert kommentar.sprungabsatz() == 1
    # Davor wird ein Absatz eingefuegt: der gespeicherte Index 1 passt nicht mehr
    pfad = temp_buch.pfad / "quelle" / K1.datei
    pfad.write_text("Neuer Anfang.\n\n" + pfad.read_text(encoding="utf-8"), encoding="utf-8")
    assert kommentar.sprungabsatz() == 2


# --- App: Kapitel blaettern --------------------------------------------------

async def _oeffne_k1(app, pilot):
    baum = app.query_one(LibraryTree)
    baum.select_node(list(baum.root.children)[0].children[0].children[0])
    for _ in range(3):
        await pilot.pause()


@pytest.mark.asyncio
async def test_n_und_p_blaettern_und_bleiben_im_tab(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await _oeffne_k1(app, pilot)
        reader = app.query_one(ReaderPane)
        assert reader.kapitel.nr == 1
        await pilot.press("3")           # Tags-Tab
        await pilot.press("n")
        await pilot.pause()
        assert reader.kapitel.nr == 2
        assert app.query_one(TabbedContent).active == "tab-tags"
        await pilot.press("p")
        await pilot.pause()
        assert reader.kapitel.nr == 1


@pytest.mark.asyncio
async def test_blaettern_am_ende_und_anfang_meldet_nur(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await _oeffne_k1(app, pilot)
        await pilot.press("p")
        await pilot.pause()
        assert app.query_one(ReaderPane).kapitel.nr == 1
        assert any("Erstes Kapitel" in n.message for n in app._notifications)
        await pilot.press("n", "n")
        await pilot.pause()
        assert app.query_one(ReaderPane).kapitel.nr == 2
        assert any("Letztes Kapitel" in n.message for n in app._notifications)


@pytest.mark.asyncio
async def test_blaettern_ohne_kapitel_und_im_editiermodus_tut_nichts(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("n")           # noch nichts geoeffnet
        await pilot.pause()
        assert app.query_one(ReaderPane).kapitel is None
        await _oeffne_k1(app, pilot)
        reader = app.query_one(ReaderPane)
        reader.bearbeiten = True
        app.action_naechstes_kapitel()
        await pilot.pause()
        assert reader.kapitel.nr == 1
        assert any("speichern oder verwerfen" in n.message for n in app._notifications)


@pytest.mark.asyncio
async def test_buchstabe_n_im_filtermodus_blaettert_nicht(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await _oeffne_k1(app, pilot)
        app.query_one(LibraryTree).focus()
        await pilot.press("/", "n")
        await pilot.pause()
        assert app.query_one(ReaderPane).kapitel.nr == 1
        assert app.query_one(LibraryTree).filter_text == "n"


@pytest.mark.asyncio
async def test_pfeilknoepfe_der_aktionsleiste_blaettern(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        await pilot.pause()
        await _oeffne_k1(app, pilot)
        await pilot.click("#knopf-weiter")
        await pilot.pause()
        assert app.query_one(ReaderPane).kapitel.nr == 2
        await pilot.click("#knopf-zurueck")
        await pilot.pause()
        assert app.query_one(ReaderPane).kapitel.nr == 1


# --- App: Leseposition -------------------------------------------------------

def _langes_kapitel(temp_buch, n=80):
    absaetze = [f"Absatz Nummer {i} mit etwas Text, damit die Seite waechst." for i in range(n)]
    (temp_buch.pfad / "quelle" / K2.datei).write_text("\n\n".join(absaetze), encoding="utf-8")


@pytest.mark.asyncio
async def test_aktueller_absatz_folgt_dem_scrollen(tmp_path, temp_buch):
    _langes_kapitel(temp_buch)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 20)) as pilot:
        await _oeffne_k1(app, pilot)
        await pilot.press("n")
        for _ in range(3):
            await pilot.pause()
        reader = app.query_one(ReaderPane)
        assert reader.aktueller_absatz() == 0
        reader.query_one("#anzeige-scroll").scroll_to(y=100, animate=False)
        for _ in range(3):
            await pilot.pause(0.2)
        assert reader.aktueller_absatz() > 10


@pytest.mark.asyncio
async def test_position_wird_gespeichert_und_beim_start_wieder_geoeffnet(tmp_path, temp_buch):
    _langes_kapitel(temp_buch)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 20)) as pilot:
        await _oeffne_k1(app, pilot)
        await pilot.press("n")
        for _ in range(3):
            await pilot.pause()
        app.query_one(ReaderPane).query_one("#anzeige-scroll").scroll_to(y=100, animate=False)
        for _ in range(3):
            await pilot.pause(0.2)
        gemerkt = app.query_one(ReaderPane).aktueller_absatz()
        await pilot.press("q")
    zuletzt = library.lade_zustand()["zuletzt"]
    assert zuletzt["datei"] == K2.datei and zuletzt["absatz"] == gemerkt > 10

    neu = EpistoApp(root=tmp_path)
    async with neu.run_test(size=(100, 20)) as pilot:
        for _ in range(4):
            await pilot.pause(0.2)
        reader = neu.query_one(ReaderPane)
        assert reader.kapitel.datei == K2.datei
        assert reader.query_one("#anzeige-scroll").scroll_y > 0
        assert any("Weiter bei" in n.message for n in neu._notifications)


@pytest.mark.asyncio
async def test_start_ohne_gespeicherte_position_oeffnet_nichts(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one(ReaderPane).kapitel is None


# --- App: Sprung aus Themen, Querverweisen und Notizen ------------------------

@pytest.mark.asyncio
async def test_themen_sprungliste_oeffnet_anderes_kapitel(tmp_path, temp_buch):
    (temp_buch.pfad / "notizen" / "straenge" / "test-strang.md").write_text(
        "---\nstrang: Test-Strang\n---\n\n"
        "### Kapitel 1 · Erstes Kapitel\n- a\n\n### Kapitel 2 · Zweites Kapitel\n- b\n",
        encoding="utf-8")
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await _oeffne_k1(app, pilot)
        await pilot.press("4")
        await pilot.pause()
        liste = app.query_one(StraengePane).query_one("#sprung", OptionList)
        assert liste.display and liste.option_count == 1
        liste.focus()
        liste.highlighted = 0
        await pilot.press("enter")
        for _ in range(3):
            await pilot.pause()
        assert app.query_one(ReaderPane).kapitel.nr == 2
        assert app.query_one(TabbedContent).active == "tab-text"


@pytest.mark.asyncio
async def test_themen_ohne_andere_kapitel_zeigen_keine_sprungliste(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await _oeffne_k1(app, pilot)
        await pilot.press("4")
        await pilot.pause()
        assert not app.query_one(StraengePane).query_one("#sprung", OptionList).display


@pytest.mark.asyncio
async def test_querverweis_auf_vorhandenes_werk_oeffnet_es(tmp_path, temp_buch):
    ziel = _neues_buch(tmp_path, "Schumpeter, Joseph A", "Capitalism, Socialism and Democracy")
    (temp_buch.pfad / "querbezuege" / "querbezuege.json").write_text(json.dumps({"bezuege": [
        {"ziel": "schumpeter_capitalism-socialism-and-democracy", "autor": "J. Schumpeter",
         "titel": "CSD", "relation": "ergaenzt", "notiz": "n"},
        {"ziel": "mosca_elementi", "autor": "Mosca", "titel": "Elementi", "relation": "x", "notiz": "n"},
    ]}), encoding="utf-8")
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        app._oeffne(temp_buch, K1)
        for _ in range(3):
            await pilot.pause()
        await pilot.press("5")
        await pilot.pause()
        liste = app.query_one(QuerbezuegePane).query_one("#sprung", OptionList)
        assert liste.option_count == 1       # Mosca liegt nicht in der Bibliothek
        liste.focus()
        liste.highlighted = 0
        await pilot.press("enter")
        for _ in range(3):
            await pilot.pause()
        assert app.query_one(ReaderPane).buch.titel == "Capitalism, Socialism and Democracy"


@pytest.mark.asyncio
async def test_notizenliste_filtert_und_springt_zum_absatz(tmp_path, temp_buch):
    _notizen_anlegen(temp_buch)
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("m")
        await pilot.pause()
        assert isinstance(app.screen, NotizenScreen)
        liste = app.screen.query_one("#notizen-liste", OptionList)
        assert liste.option_count == 2
        app.screen.query_one("#notizen-filter", Input).value = "gelb"
        await pilot.pause()
        assert liste.option_count == 1
        await pilot.press("enter")       # Eingabe -> Fokus in die Liste
        await pilot.press("enter")       # Auswahl
        for _ in range(3):
            await pilot.pause()
        assert not isinstance(app.screen, NotizenScreen)
        assert app.query_one(ReaderPane).kapitel.nr == 2


@pytest.mark.asyncio
async def test_notizenliste_leer_und_esc(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("m")
        await pilot.pause()
        assert "Noch keine" in str(app.screen.query_one("#notizen-status").render())
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, NotizenScreen)
