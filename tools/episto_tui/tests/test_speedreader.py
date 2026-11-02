import pytest
from textual.widgets import Static
from episto_tui import library, speedreader as sr
from episto_tui.app import EpistoApp
from episto_tui.models import Kapitel, Tag
from episto_tui.widgets.aktionsleiste import TippKnopf
from episto_tui.widgets.speedreader_screen import SpeedreaderScreen

K1 = Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md")


def _tag(**felder):
    basis = dict(datei=K1.datei, kapitel_nr=1, titel="Erstes Kapitel", woerter=10)
    basis.update(felder)
    return Tag(**basis)


# --- Kern -----------------------------------------------------------------------

def test_woerter_in_festen_abschnitten_und_leere_felder_entfallen():
    tag = _tag(zusammenfassung="Ein kurzer Satz.", these=["Erste These.", "Zweite These"],
               gegen=[], kern=["Habitus"], def_=[], beleg=["Beleg eins"])
    woerter, namen = sr.baue_woerter(tag)
    assert namen == ["Zusammenfassung", "Thesen", "Kernbegriffe", "Belege"]
    marken = [w.text for w in woerter if w.marke]
    assert marken == namen
    assert [w.text for w in woerter if w.abschnitt == 1 and not w.marke] == ["Erste", "These.", "Zweite", "These"]
    # Reihenfolge: Zusammenfassung vor Thesen vor Kernbegriffen vor Belegen
    assert [w.abschnitt for w in woerter] == sorted(w.abschnitt for w in woerter)


def test_listeneintraege_enden_als_eigener_satz_mit_extrapause():
    woerter, _ = sr.baue_woerter(_tag(these=["Alpha beta", "Gamma"]))
    texte = [(w.text, w.satzende, w.faktor >= 2.0) for w in woerter if not w.marke]
    assert texte == [("Alpha", False, False), ("beta", True, True), ("Gamma", True, True)]


def test_fussnotenmarken_fallen_weg_und_leerer_tag_ergibt_nichts():
    woerter, _ = sr.baue_woerter(_tag(these=["Satz [^12] mit Note [^a3]."]))
    assert [w.text for w in woerter if not w.marke] == ["Satz", "mit", "Note."]
    assert all("[^" not in w.text for w in woerter)
    # Satzzeichen direkt hinter einer Fussnotenmarke haengen am vorigen Wort
    woerter, _ = sr.baue_woerter(_tag(these=["Erste Aussage[^3]. Zweite – Aussage[^4] !"]))
    assert [w.text for w in woerter if not w.marke] == ["Erste", "Aussage.", "Zweite–", "Aussage!"]
    assert sr.baue_woerter(_tag()) == ([], [])


@pytest.mark.parametrize("wort,erwartet", [
    ("a", 0), ("zu", 1), ("Macht", 1), ("Habitus", 2), ("Substantiell", 3),
    ("Rechtsschutzversicherung", 4), ("(Substantiell,", 4), ("„Macht“", 2),
])
def test_orp_index(wort, erwartet):
    assert sr.orp_index(wort) == erwartet


@pytest.mark.parametrize("text", ["a", "Macht", "Habitus", "(Substantiell,", "Rechtsschutz"])
def test_erkennungspunkt_steht_immer_in_derselben_spalte(text):
    halb = 12
    zeile = sr.render_wort(sr.Wort(text, 0), halb)
    assert len(zeile.plain) <= 2 * halb + 1
    assert zeile.plain[halb] == text[min(sr.orp_index(text), len(text) - 1)]


@pytest.mark.parametrize("laenge", [24, 30, 36, 37])
def test_lange_woerter_bleiben_ganz_sichtbar(laenge):
    halb = 18
    text = "x" * (laenge - 1) + "y"
    zeile = sr.render_wort(sr.Wort(text, 0), halb).plain
    assert len(zeile) <= 2 * halb + 1
    assert zeile.strip() == text                      # nichts abgeschnitten


def test_unmoegliche_woerter_werden_mit_auslassung_gekuerzt():
    halb = 18
    zeile = sr.render_wort(sr.Wort("a" * 60, 0), halb).plain
    assert len(zeile) == 2 * halb + 1 and zeile.endswith("…")


def test_markdown_sternchen_und_randstriche_fallen_weg():
    woerter, _ = sr.baue_woerter(_tag(beleg=["*Storia d'Europa* und Gegner_innen _betont_ 12*"]))
    assert [w.text for w in woerter if not w.marke] == ["Storia", "d'Europa", "und", "Gegner_innen", "betont", "12"]


def test_pausenfaktoren():
    f = sr._faktor
    assert f("Haus") == 1.0
    assert f("Gegenstand") == pytest.approx(1.3)
    assert f("Rechtsschutzversicherung") == pytest.approx(1.6)
    assert f("Ende.") == pytest.approx(2.0)
    assert f("fertig?»") == pytest.approx(2.0)          # schliessende Zeichen zaehlen nicht
    assert f("also,") == pytest.approx(1.5)
    assert sr.dauer(sr.Wort("Haus", 0), 600) == pytest.approx(0.1)
    assert sr.grunddauer(5) == sr.grunddauer(sr.MIN_WPM)  # unter dem Minimum begrenzt


def test_satz_und_abschnittssprunge():
    tag = _tag(zusammenfassung="Eins zwei. Drei vier.", these=["Fuenf sechs"])
    w, _ = sr.baue_woerter(tag)
    texte = [x.text for x in w]
    assert texte == ["Zusammenfassung", "Eins", "zwei.", "Drei", "vier.", "Thesen", "Fuenf", "sechs"]
    assert sr.satzanfang(w, 2) == 1                      # "zwei." gehoert zum Satz ab "Eins"
    assert sr.voriger_satzanfang(w, 2) == 1
    assert sr.voriger_satzanfang(w, 1) == 0              # schon am Satzanfang -> davor (Marke)
    assert sr.voriger_satzanfang(w, 0) == 0
    assert sr.naechster_satzanfang(w, 1) == 3
    assert sr.naechster_satzanfang(w, 7) == 7            # am Ende bleibt es dort
    assert sr.abschnittsanfang(w, 4) == 0
    assert sr.naechster_abschnitt(w, 2) == 5
    assert sr.voriger_abschnitt(w, 6) == 5
    assert sr.voriger_abschnitt(w, 5) == 0
    assert sr.naechster_abschnitt(w, 6) == 7


def test_restdauer_summiert_die_woerter():
    w, _ = sr.baue_woerter(_tag(zusammenfassung="Ein Satz."))
    assert sr.restdauer(w, 0, 600) == pytest.approx(sum(sr.dauer(x, 600) for x in w))
    assert sr.restdauer(w, len(w), 600) == 0
    assert sr.begrenze_tempo(5000) == sr.MAX_WPM and sr.begrenze_tempo(1) == sr.MIN_WPM


# --- Dialog -----------------------------------------------------------------------

def _vollstaendiger_tag(temp_buch):
    library.write_tag(temp_buch, _tag(
        zusammenfassung="Gegenstand und Gang.", these=["Erste These. Zweiter Satz"],
        gegen=["Gegenposition"], kern=["Habitus"], def_=["Habitus: System von Dispositionen"],
        beleg=["Bourdieu 1979"]))


async def _oeffne(app, pilot, temp_buch):
    app._oeffne(temp_buch, K1)
    for _ in range(3):
        await pilot.pause()
    await pilot.press("v")
    await pilot.pause()
    assert isinstance(app.screen, SpeedreaderScreen)
    return app.screen


def _wort(s):
    return s.query_one("#sr-wort", Static).render().plain.splitlines()[1]


def _status(s):
    return str(s.query_one("#sr-status", Static).render())


@pytest.mark.asyncio
async def test_ohne_kapitel_kein_dialog(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("v")
        await pilot.pause()
        assert not isinstance(app.screen, SpeedreaderScreen)
        assert any("Kapitel öffnen" in n.message for n in app._notifications)


@pytest.mark.asyncio
async def test_start_pause_und_schrittweises_vorruecken(tmp_path, temp_buch):
    _vollstaendiger_tag(temp_buch)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        s = await _oeffne(app, pilot, temp_buch)
        assert _wort(s).strip() == "ZUSAMMENFASSUNG" and "Pause" in _status(s)
        assert s._woerter and s._i == 0
        await pilot.press("space")
        assert s._laeuft and "läuft" in _status(s)
        s._tick(); s._tick(); s._tick()                    # deterministisch statt Wartezeit
        assert s._i == 3 and _wort(s).strip() == "Gang."
        await pilot.press("space")
        assert not s._laeuft and s._timer is None


@pytest.mark.asyncio
async def test_timer_schaltet_von_selbst_weiter_und_endet(tmp_path, temp_buch):
    library.write_tag(temp_buch, _tag(zusammenfassung="Ein Satz"))
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        s = await _oeffne(app, pilot, temp_buch)
        s._setze_tempo(sr.MAX_WPM)
        await pilot.press("space")
        for _ in range(30):
            await pilot.pause(0.1)
            if not s._laeuft:
                break
        assert not s._laeuft and s._i == len(s._woerter) - 1
        assert "Ende" in _status(s)
        assert s.query_one("#knopf-pause", TippKnopf).label.plain == "Neu"
        await pilot.press("space")                          # nach dem Ende von vorn
        assert s._laeuft and s._i == 0


@pytest.mark.asyncio
async def test_sprung_ans_ende_waehrend_des_laufs_beendet_den_lauf(tmp_path, temp_buch):
    _vollstaendiger_tag(temp_buch)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        s = await _oeffne(app, pilot, temp_buch)
        await pilot.press("space")
        assert s._laeuft
        s.action_abschnitt_vor()                            # bis zum letzten Abschnitt vorspringen
        while s._woerter[s._i].abschnitt < s._woerter[-1].abschnitt:
            s.action_abschnitt_vor()
        s._springe(len(s._woerter) - 1)                     # und ans allerletzte Wort
        assert s._i == len(s._woerter) - 1
        assert not s._laeuft and s._timer is None           # kein "läuft" ohne Timer
        assert "Ende" in _status(s)
        assert s.query_one("#knopf-pause", TippKnopf).label.plain == "Neu"


@pytest.mark.asyncio
async def test_tempo_tasten_begrenzen_und_werden_gemerkt(tmp_path, temp_buch):
    _vollstaendiger_tag(temp_buch)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        s = await _oeffne(app, pilot, temp_buch)
        assert s._wpm == sr.STANDARD_WPM == 400
        await pilot.press("up")                              # grob: +-50
        assert s._wpm == 450
        await pilot.press("plus", "plus", "plus")            # fein: +-5
        assert s._wpm == 465
        await pilot.press("minus")
        assert s._wpm == 460
        await pilot.press("down")
        assert s._wpm == 410
        for _ in range(200):
            await pilot.press("plus")
        assert s._wpm == sr.MAX_WPM
        for _ in range(30):
            await pilot.press("down")
        assert s._wpm == sr.MIN_WPM
        await pilot.press("plus")
        assert library.lade_zustand()["speedreader_wpm"] == sr.MIN_WPM + sr.WPM_FEIN
        await pilot.press("escape")
        await pilot.pause()
        s2 = await _oeffne_erneut(app, pilot)
        assert s2._wpm == sr.MIN_WPM + sr.WPM_FEIN


@pytest.mark.asyncio
async def test_tempo_knoepfe_fein_und_grob(tmp_path, temp_buch):
    _vollstaendiger_tag(temp_buch)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 30)) as pilot:
        s = await _oeffne(app, pilot, temp_buch)
        s.query_one("#knopf-fein-schneller", TippKnopf).press()
        s.query_one("#knopf-fein-schneller", TippKnopf).press()
        s.query_one("#knopf-schneller", TippKnopf).press()
        s.query_one("#knopf-fein-langsamer", TippKnopf).press()
        s.query_one("#knopf-langsamer", TippKnopf).press()
        await pilot.pause()
        assert s._wpm == 400 + 5 + 5 + 50 - 5 - 50
        assert "405 Wörter/min" in _status(s)
        for k in s.query(TippKnopf):
            assert k.region.width > 0 and k.region.right <= 45, f"{k.id}: {k.region}"


async def _oeffne_erneut(app, pilot):
    await pilot.press("v")
    await pilot.pause()
    assert isinstance(app.screen, SpeedreaderScreen)
    return app.screen


@pytest.mark.asyncio
async def test_sprungtasten_und_knoepfe(tmp_path, temp_buch):
    _vollstaendiger_tag(temp_buch)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        s = await _oeffne(app, pilot, temp_buch)
        texte = [w.text for w in s._woerter]
        await pilot.press("right")                          # naechster Satz: nach der Marke
        assert texte[s._i] == "Gegenstand"
        s.query_one("#knopf-abschnitt-vor", TippKnopf).press()
        await pilot.pause()
        assert texte[s._i] == "Thesen"
        await pilot.press("right", "right")
        assert texte[s._i] == "Zweiter"
        await pilot.press("left")
        assert texte[s._i] == "Erste"
        s.query_one("#knopf-abschnitt-zurueck", TippKnopf).press()
        await pilot.pause()
        assert texte[s._i] == "Thesen"
        s.query_one("#knopf-satz-vor", TippKnopf).press()
        await pilot.pause()
        assert texte[s._i] == "Erste"


@pytest.mark.asyncio
async def test_kapitel_ohne_ki_felder_zeigt_hinweis_und_bleibt_bedienbar(tmp_path, temp_buch):
    (temp_buch.pfad / "notizen" / "tags.json").unlink()
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        s = await _oeffne(app, pilot, temp_buch)
        assert "keine KI-Felder" in _status(s)
        await pilot.press("space", "right", "left", "up", "down")
        assert not s._laeuft
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, SpeedreaderScreen)


@pytest.mark.asyncio
async def test_escape_stoppt_den_ablauf(tmp_path, temp_buch):
    _vollstaendiger_tag(temp_buch)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 30)) as pilot:
        s = await _oeffne(app, pilot, temp_buch)
        await pilot.press("space")
        assert s._timer is not None
        await pilot.press("escape")
        await pilot.pause()
        assert s._timer is None and not s._laeuft


@pytest.mark.asyncio
async def test_passt_in_die_handybreite(tmp_path, temp_buch):
    library.write_tag(temp_buch, _tag(
        zusammenfassung="Rechtsschutzversicherungsgesellschaftsvertragsbedingungen sind lang."))
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 30)) as pilot:
        s = await _oeffne(app, pilot, temp_buch)
        for _ in range(3):
            s._springe(s._i + 1)
        for k in s.query(TippKnopf):
            assert k.region.width > 0 and k.region.right <= 45, f"{k.id}: {k.region}"
        wort = s.query_one("#sr-wort", Static)
        assert wort.region.right <= 45 and all(len(z) <= 2 * 18 + 1 for z in wort.render().plain.splitlines())


@pytest.mark.asyncio
async def test_knopf_speed_in_der_aktionsleiste_oeffnet_den_dialog(tmp_path, temp_buch):
    _vollstaendiger_tag(temp_buch)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        app._oeffne(temp_buch, K1)
        for _ in range(3):
            await pilot.pause()
        await pilot.click("#knopf-speed")
        await pilot.pause()
        assert isinstance(app.screen, SpeedreaderScreen)
