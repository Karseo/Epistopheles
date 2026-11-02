import json
import pytest
from textual.widgets import Button, TextArea, Static
from episto_tui import korrektur, library
from episto_tui.annotate import split_paragraphs
from episto_tui.app import EpistoApp
from episto_tui.models import Highlight, Kapitel
from episto_tui.widgets.korrektur_screen import KorrekturScreen
from episto_tui.widgets.reader_pane import ReaderPane

K1 = Kapitel(1, "Erstes Kapitel", "0001_erstes-kapitel.md")
KAPUTT = "Zweiter Absatz mit mehr Inhalt zum Testen."


def _grounding(temp_buch, absaetze_je_chunk=4):
    lektor = temp_buch.pfad / "_lektor"
    lektor.mkdir()
    (lektor / "kapitel.json").write_text(json.dumps({"segmente": [
        {"id": "s1", "titel": "E", "chunk": 0, "position": 0, "vorspann": False},
        {"id": "s2", "titel": "K", "chunk": 2, "position": 0, "vorspann": False},
    ]}), encoding="utf-8")
    (temp_buch.pfad / "meta.json").write_text(json.dumps({"lektor_pfad": str(lektor), "chunks": 4}), encoding="utf-8")
    en = temp_buch.pfad / "en"
    en.mkdir()
    for i in range(4):
        (en / f"chunk_{i:03d}.md").write_text(
            "\n\n".join(f"EN-{i}-{j}" for j in range(absaetze_je_chunk)), encoding="utf-8")
    return temp_buch


def _marke(temp_buch, index=1, anfang=KAPUTT, farbe="korrektur"):
    library.write_highlight(temp_buch, Highlight(K1.datei, index, anfang, farbe))


# --- Kern ---------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "A\n\nB\n\nC", "\n\nA eins.\n\n\n  B zwei  \r\n\r\nC drei\n", "nur ein Absatz", "A\n   \nB", "", "\n\n\n",
])
def test_absatz_spannen_zaehlen_wie_split_paragraphs(text):
    assert [text[a:b] for a, b in korrektur.absatz_spannen(text)] == split_paragraphs(text)


def test_ersetze_absatz_exakt_laesst_den_rest_zeichengenau_stehen():
    text = "\n\nA eins.\n\n\n  B zwei  \r\n\r\nC drei"      # ohne EOF-Zeilenumbruch, gemischte Leerzeilen
    assert korrektur.ersetze_absatz_exakt(text, 1, " NEU ") == "\n\nA eins.\n\n\n  NEU  \r\n\r\nC drei"
    assert korrektur.ersetze_absatz_exakt(text, 2, "Z").endswith("\r\n\r\nZ")
    with pytest.raises(ValueError):
        korrektur.ersetze_absatz_exakt(text, 3, "x")


def test_englisches_fenster_proportional_und_begrenzt():
    assert korrektur.englisches_fenster(10, 5, 20) == (8, 15)       # Mitte ~ 11, +-3
    assert korrektur.englisches_fenster(10, 0, 20) == (0, 7)        # am Anfang nicht kleiner
    assert korrektur.englisches_fenster(10, 9, 20) == (13, 20)      # am Ende nicht groesser
    assert korrektur.englisches_fenster(10, 5, 3) == (0, 3)         # kurzes Kapitel: alles
    assert korrektur.englisches_fenster(5, 0, 0) == (0, 0)
    assert korrektur.englisches_fenster(0, 0, 10) == (0, 7)


def test_verschiebe_fenster_behaelt_groesse_und_grenzen():
    assert korrektur.verschiebe_fenster((8, 15), -2, 20) == (6, 13)
    assert korrektur.verschiebe_fenster((0, 7), -5, 20) == (0, 7)
    assert korrektur.verschiebe_fenster((13, 20), +5, 20) == (13, 20)


def test_fenster_text_kuerzt_von_aussen():
    absaetze = ["a" * 100, "b" * 100, "MITTE" + "m" * 95, "c" * 100, "d" * 100]
    kurz = korrektur.fenster_text(absaetze, (0, 5), max_zeichen=320)
    assert "MITTE" in kurz and len(kurz) <= 320
    assert korrektur.fenster_text(absaetze, (0, 5), max_zeichen=10_000).count("\n\n") == 4


@pytest.mark.parametrize("original,vorschlag,erwartet", [
    ("Der Satz endet hier [^12]", "Der Satz endet hier ganz sauber [^12]", []),
    ("Der Satz", "", ["leer"]),
    ("Der Satz", "Der Satz", ["unveraendert"]),
    ("a" * 100, "a" * 20, ["halb so lang"]),
    ("a" * 10, "a" * 100, ["2,5-mal"]),
    ("Der Satz bricht ab", "Hier ist der korrigierte Absatz: Der Satz bricht nicht ab", ["Antwort des Modells"]),
    ("Ein Absatz", "Erster.\n\nZweiter Absatz", ["mehrere"]),
    ("Satz [^3] mit Note", "Satz mit Note", ["Fussnotenmarken"]),
    ("Satz mit *4 Note", "Satz mit *5 Note", ["Fussnotenmarken"]),
])
def test_pruefe_vorschlag(original, vorschlag, erwartet):
    warnungen = " | ".join(korrektur.pruefe_vorschlag(original, vorschlag))
    if not erwartet:
        assert warnungen == ""
    for teil in erwartet:
        assert teil in warnungen


def test_sammle_offene_marken_loest_auf_und_markiert_verwaiste(temp_buch):
    _marke(temp_buch, 1, KAPUTT)
    _marke(temp_buch, 2, "Dritter Absatz, der letzte hier.")
    library.write_highlight(temp_buch, Highlight(K1.datei, 0, "Erster Absatz des ersten Kapitels.", "gelb"))
    library.write_highlight(temp_buch, Highlight("0002_zweites-kapitel.md", 5, "Gibt es nicht mehr", "korrektur"))
    marken = korrektur.sammle_offene_marken([temp_buch])
    assert [(m.kapitel.nr, m.absatz_index) for m in marken] == [(1, 1), (1, 2), (2, None)]
    assert marken[0].absatz == KAPUTT and marken[2].absatz == ""


def test_wende_an_ersetzt_nur_diesen_absatz_und_raeumt_auf(temp_buch):
    _marke(temp_buch)
    vorher = library.read_chapter_text(temp_buch, K1.datei)
    marke = korrektur.sammle_offene_marken([temp_buch])[0]
    assert korrektur.wende_an(marke, "Repariert.") == 1
    nachher = library.read_chapter_text(temp_buch, K1.datei)
    assert nachher == vorher.replace(KAPUTT, "Repariert.")
    assert library.read_highlights_nach_farbe(temp_buch, "korrektur") == []
    assert list((temp_buch.pfad / "notizen" / "_backup").glob("0001_erstes-kapitel.*.md"))


def test_wende_an_findet_verschobenen_absatz(temp_buch):
    _marke(temp_buch)
    marke = korrektur.sammle_offene_marken([temp_buch])[0]
    pfad = temp_buch.pfad / "quelle" / K1.datei
    pfad.write_text("Neu davor.\n\n" + pfad.read_text(encoding="utf-8"), encoding="utf-8")   # Index 1 -> 2
    assert korrektur.wende_an(marke, "Repariert.") == 2
    assert "Repariert." in split_paragraphs(pfad.read_text(encoding="utf-8"))


def test_wende_an_bei_verschwundenem_absatz_aendert_nichts(temp_buch):
    _marke(temp_buch)
    marke = korrektur.sammle_offene_marken([temp_buch])[0]
    pfad = temp_buch.pfad / "quelle" / K1.datei
    pfad.write_text("Ganz anderer Text.", encoding="utf-8")
    with pytest.raises(ValueError):
        korrektur.wende_an(marke, "Repariert.")
    assert pfad.read_text(encoding="utf-8") == "Ganz anderer Text."
    assert len(library.read_highlights_nach_farbe(temp_buch, "korrektur")) == 1


def test_kommandozeile_schickt_nur_ein_fenster_und_mit_voll_das_ganze_kapitel(temp_buch, monkeypatch):
    _grounding(temp_buch, absaetze_je_chunk=10)      # Kapitel 1 = Chunks 0..2 = 30 englische Absaetze
    _marke(temp_buch)
    gesehen = []
    monkeypatch.setattr(korrektur, "korrigiere", lambda absatz, englisch, model="m", ollama_url="u":
                        gesehen.append(englisch) or "Repariert.")
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    korrektur.main(["-Buch", str(temp_buch.pfad)])
    korrektur.main(["-Buch", str(temp_buch.pfad), "-Voll"])
    fenster, voll = gesehen
    assert fenster.count("EN-") == 7 and "EN-0-0" not in fenster
    assert voll.count("EN-") == 30


# --- Dialog -----------------------------------------------------------------

async def _oeffne_dialog(app, pilot, temp_buch):
    app._oeffne(temp_buch, K1)
    for _ in range(3):
        await pilot.pause()
    await pilot.press("x")
    for _ in range(2):
        await pilot.pause()
    assert isinstance(app.screen, KorrekturScreen)
    return app.screen


def _text(screen, widget_id):
    return screen.query_one(widget_id, TextArea).text


def _status(screen):
    return str(screen.query_one("#korr-status", Static).render())


@pytest.mark.asyncio
async def test_dialog_zeigt_marke_und_englisches_fenster(tmp_path, temp_buch):
    _grounding(temp_buch)
    _marke(temp_buch)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 40)) as pilot:
        s = await _oeffne_dialog(app, pilot, temp_buch)
        assert "Korrektur 1/1" in str(s.query_one("#korr-kopf", Static).render())
        assert _text(s, "#korr-de") == KAPUTT
        assert _text(s, "#korr-en").count("EN-") == 7
        s.query_one("#knopf-en-runter", Button).press()
        await pilot.pause()
        assert s._fenster == (4, 11)
        s.query_one("#knopf-en-runter10", Button).press()       # am Kapitelende begrenzt
        s.query_one("#knopf-en-hoch10", Button).press()
        await pilot.pause()
        assert s._fenster == (0, 7)


@pytest.mark.asyncio
async def test_vorschlag_kommt_aus_dem_hintergrund_und_wird_geprueft(tmp_path, temp_buch, monkeypatch):
    _grounding(temp_buch)
    _marke(temp_buch)
    gesehen = {}

    def fake(absatz, englisch, model=None, ollama_url=None):
        gesehen.update(absatz=absatz, englisch=englisch)
        return "Hier ist der korrigierte Absatz: Repariert."

    monkeypatch.setattr(korrektur, "korrigiere", fake)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 40)) as pilot:
        s = await _oeffne_dialog(app, pilot, temp_buch)
        s.query_one("#knopf-vorschlag", Button).press()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert _text(s, "#korr-de").startswith("Hier ist der korrigierte")
        assert "Antwort des Modells" in _status(s)
        assert gesehen["absatz"] == KAPUTT and gesehen["englisch"].count("EN-") == 7
        s.query_one("#knopf-original", Button).press()
        await pilot.pause()
        assert _text(s, "#korr-de") == KAPUTT


@pytest.mark.asyncio
async def test_vorschlag_fehler_wird_gemeldet_ohne_absturz(tmp_path, temp_buch, monkeypatch):
    _grounding(temp_buch)
    _marke(temp_buch)

    def kaputt(*args, **kwargs):
        raise ConnectionError("Ollama nicht erreichbar")

    monkeypatch.setattr(korrektur, "korrigiere", kaputt)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 40)) as pilot:
        s = await _oeffne_dialog(app, pilot, temp_buch)
        s.action_vorschlag()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "Kein Vorschlag" in _status(s) and "Ollama" in _status(s)
        assert _text(s, "#korr-de") == KAPUTT


@pytest.mark.asyncio
async def test_uebernehmen_schreibt_absatz_entfernt_marke_und_laedt_kapitel_neu(tmp_path, temp_buch):
    _grounding(temp_buch)
    _marke(temp_buch)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 40)) as pilot:
        s = await _oeffne_dialog(app, pilot, temp_buch)
        s.query_one("#korr-de", TextArea).load_text("Von Hand repariert.")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "Von Hand repariert." in library.read_chapter_text(temp_buch, K1.datei)
        assert library.read_highlights_nach_farbe(temp_buch, "korrektur") == []
        assert "Keine weiteren Marken" in _status(s)
        await pilot.press("escape")
        for _ in range(3):
            await pilot.pause()
        assert not isinstance(app.screen, KorrekturScreen)
        assert app.query_one(ReaderPane).kapitel.datei == K1.datei
        from textual.widgets import Markdown
        assert "Von Hand repariert." in app.query_one(ReaderPane).query_one("#anzeige", Markdown).source


@pytest.mark.asyncio
async def test_unveraenderter_oder_leerer_text_wird_nicht_uebernommen(tmp_path, temp_buch):
    _marke(temp_buch)
    vorher = library.read_chapter_text(temp_buch, K1.datei)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 40)) as pilot:
        s = await _oeffne_dialog(app, pilot, temp_buch)
        s.action_uebernehmen()
        assert "unverändert" in _status(s)
        s.query_one("#korr-de", TextArea).load_text("   ")
        s.action_uebernehmen()
        assert "leer" in _status(s)
        assert library.read_chapter_text(temp_buch, K1.datei) == vorher
        assert len(library.read_highlights_nach_farbe(temp_buch, "korrektur")) == 1


@pytest.mark.asyncio
async def test_marke_weg_laesst_den_text_unveraendert(tmp_path, temp_buch):
    _marke(temp_buch)
    vorher = library.read_chapter_text(temp_buch, K1.datei)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 40)) as pilot:
        s = await _oeffne_dialog(app, pilot, temp_buch)
        await pilot.press("ctrl+r")
        await pilot.pause()
        assert library.read_highlights_nach_farbe(temp_buch, "korrektur") == []
        assert library.read_chapter_text(temp_buch, K1.datei) == vorher


@pytest.mark.asyncio
async def test_ohne_englisches_original_bleibt_nur_handarbeit(tmp_path, temp_buch):
    _marke(temp_buch)                       # kein meta.json, kein en-Ordner
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 40)) as pilot:
        s = await _oeffne_dialog(app, pilot, temp_buch)
        assert "Nicht verfügbar" in _text(s, "#korr-en")
        s.action_vorschlag()
        assert "Ohne englisches Original" in _status(s)
        s.query_one("#korr-de", TextArea).load_text("Von Hand.")
        s.action_uebernehmen()
        assert "Von Hand." in library.read_chapter_text(temp_buch, K1.datei)


@pytest.mark.asyncio
async def test_verwaiste_marke_kann_nur_entfernt_werden(tmp_path, temp_buch):
    library.write_highlight(temp_buch, Highlight(K1.datei, 1, "Dieser Absatz existiert nicht", "korrektur"))
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 40)) as pilot:
        s = await _oeffne_dialog(app, pilot, temp_buch)
        assert "nicht mehr auffindbar" in _status(s)
        s.action_uebernehmen()
        assert "nicht mehr auffindbar" in _status(s)
        s.action_marke_weg()
        assert library.read_highlights_nach_farbe(temp_buch, "korrektur") == []


@pytest.mark.asyncio
async def test_dialog_ohne_marken_und_navigation_ueber_mehrere(tmp_path, temp_buch):
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 40)) as pilot:
        s = await _oeffne_dialog(app, pilot, temp_buch)
        assert "Keine offenen" in str(s.query_one("#korr-kopf", Static).render())
        await pilot.press("escape")
        await pilot.pause()
    _marke(temp_buch, 1, KAPUTT)
    _marke(temp_buch, 2, "Dritter Absatz, der letzte hier.")
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 40)) as pilot:
        s = await _oeffne_dialog(app, pilot, temp_buch)
        s.query_one("#knopf-vor", Button).press()
        await pilot.pause()
        assert "2/2" in str(s.query_one("#korr-kopf", Static).render())
        assert _text(s, "#korr-de").startswith("Dritter Absatz")
        s.query_one("#knopf-vor", Button).press()
        await pilot.pause()
        assert "1/2" in str(s.query_one("#korr-kopf", Static).render())


@pytest.mark.asyncio
async def test_hinweis_auf_offene_marken_beim_oeffnen_des_kapitels(tmp_path, temp_buch):
    _marke(temp_buch)
    app = EpistoApp(root=tmp_path)
    async with app.run_test() as pilot:
        app._oeffne(temp_buch, K1)
        await pilot.pause()
        assert any("offene Korrektur-Marke" in n.message for n in app._notifications)


# --- Rueckfall ohne Lektor-Ordner ---------------------------------------------------

def _nur_englisch(temp_buch, absaetze_je_chunk=10, chunks=4):
    """Wie die echten Buecher: en/-Chunks vorhanden, aber meta.json zeigt auf
    einen Lektor-Ordner, den es nicht (mehr) gibt."""
    (temp_buch.pfad / "meta.json").write_text(
        json.dumps({"lektor_pfad": str(temp_buch.pfad / "gibt-es-nicht"), "chunks": chunks}), encoding="utf-8")
    en = temp_buch.pfad / "en"
    en.mkdir()
    for i in range(chunks):
        (en / f"chunk_{i:03d}.md").write_text(
            "\n\n".join(f"EN-{i}-{j}" for j in range(absaetze_je_chunk)), encoding="utf-8")


def test_englischer_anker_ohne_lektor_ordner_naehert_ueber_das_ganze_buch(temp_buch):
    _nur_englisch(temp_buch)                       # 40 englische Absaetze
    # Absatz 0 von Kapitel 1 -> ganz vorne im Buch
    vorn = korrektur.englischer_anker(temp_buch, K1.datei, 0)
    assert not vorn.genau and vorn.fenster[0] == 0 and len(vorn.absaetze) == 40
    # das ganze zweite Kapitel (letzter deutscher Absatz) -> hinter der Mitte
    hinten = korrektur.englischer_anker(temp_buch, "0002_zweites-kapitel.md", 0)
    assert hinten.fenster[0] > vorn.fenster[0] and hinten.fenster[1] <= 40
    assert hinten.fenster[1] - hinten.fenster[0] == 9      # FENSTER_BREITE + 1 = 4 -> 2*4+1


def test_englischer_anker_mit_lektor_ordner_ist_genau(temp_buch):
    _grounding(temp_buch)
    anker = korrektur.englischer_anker(temp_buch, K1.datei, 1)
    assert anker.genau and anker.fenster == (3, 10)


@pytest.mark.parametrize("alt", [
    "C:\\Users\\Dude\\Tools\\eBooks\\Lektor\\Autor\\Buch",       # Windows, erster Ablageort
    "/mnt/c/Users/Dude/Tools/eBooks/Lektor/Autor/Buch",          # WSL-Schreibweise
    "D:\\Workspace\\!Episto\\eBooks\\Lektor\\Autor\\Buch",       # Zwischenstand vor dem Umbau
])
def test_lektor_pfad_vom_alten_ablageort_wird_unter_rohdaten_neu_aufgesetzt(temp_buch, alt):
    """Seit dem Umbau liegt der Lektor-Ordner in <Bibliothek>\\rohdaten\\Lektor; die meta.json der
    Buecher nennt noch einen alten Pfad. Die exakte Kapitelzuordnung soll trotzdem greifen."""
    _grounding(temp_buch)
    neu = library.root_von(temp_buch) / "rohdaten" / "Lektor" / "Autor" / "Buch"
    neu.mkdir(parents=True)
    (neu / "kapitel.json").write_bytes((temp_buch.pfad / "_lektor" / "kapitel.json").read_bytes())
    (temp_buch.pfad / "_lektor" / "kapitel.json").unlink()          # der in der meta.json genannte Ort taugt nicht
    meta = json.loads((temp_buch.pfad / "meta.json").read_text(encoding="utf-8"))
    meta["lektor_pfad"] = alt
    (temp_buch.pfad / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    anker = korrektur.englischer_anker(temp_buch, K1.datei, 1)
    assert anker.genau and anker.fenster == (3, 10)


def test_lektor_pfad_der_nirgends_existiert_faellt_auf_die_naeherung_zurueck(temp_buch):
    _nur_englisch(temp_buch)
    meta = json.loads((temp_buch.pfad / "meta.json").read_text(encoding="utf-8"))
    meta["lektor_pfad"] = "C:\\Users\\Dude\\Tools\\eBooks\\Lektor\\Gibt\\Es Nicht"
    (temp_buch.pfad / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    assert not korrektur.englischer_anker(temp_buch, K1.datei, 0).genau


def test_rohchunks_liegen_unter_rohdaten_en_chunks_nicht_im_buchordner(temp_buch):
    """Nach dem Umbau: <root>/rohdaten/en-chunks/<Autor>/<Titel>/chunk_NNN.md, der Buchordner hat kein en\\ mehr."""
    ordner = library.root_von(temp_buch) / "rohdaten" / "en-chunks" / temp_buch.autor / temp_buch.titel
    ordner.mkdir(parents=True)
    for i in range(4):
        (ordner / f"chunk_{i:03d}.md").write_text("\n\n".join(f"EN-{i}-{j}" for j in range(10)), encoding="utf-8")
    (temp_buch.pfad / "meta.json").write_text(json.dumps({"lektor_pfad": "gibt-es-nicht", "chunks": 4}), encoding="utf-8")
    assert not (temp_buch.pfad / "en").exists()
    assert library.rohchunks_en_ordner(temp_buch) == ordner
    anker = korrektur.englischer_anker(temp_buch, K1.datei, 0)
    assert not anker.genau and len(anker.absaetze) == 40


def test_rohchunks_vorrang_rohdaten_vor_altbestand_im_buchordner(temp_buch):
    alt = temp_buch.pfad / "en"
    alt.mkdir()
    (alt / "chunk_000.md").write_text("ALT", encoding="utf-8")
    assert library.rohchunks_en_ordner(temp_buch) == alt              # nur Altbestand vorhanden
    neu = library.root_von(temp_buch) / "rohdaten" / "en-chunks" / temp_buch.autor / temp_buch.titel
    neu.mkdir(parents=True)
    (neu / "chunk_000.md").write_text("NEU", encoding="utf-8")
    assert library.rohchunks_en_ordner(temp_buch) == neu              # sobald rohdaten da ist, gilt es


def test_englischer_anker_ohne_irgendein_original_wirft(temp_buch):
    with pytest.raises(OSError):
        korrektur.englischer_anker(temp_buch, K1.datei, 0)


@pytest.mark.asyncio
async def test_dialog_nutzt_die_naeherung_und_sagt_es(tmp_path, temp_buch):
    _nur_englisch(temp_buch)
    _marke(temp_buch)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(100, 40)) as pilot:
        s = await _oeffne_dialog(app, pilot, temp_buch)
        assert "Näherung" in str(s.query_one("#korr-en-titel", Static).render())
        assert _text(s, "#korr-en").count("EN-") == 9
        vorher = s._fenster
        s.query_one("#knopf-en-runter", Button).press()
        await pilot.pause()
        assert s._fenster == (vorher[0] + 1, vorher[1] + 1)
        # Fenster bleibt beim Hin- und Herblaettern erhalten (Zwischenspeicher)
        s._gehe(+1)
        s._gehe(-1)
        assert s._fenster == (vorher[0] + 1, vorher[1] + 1)


def test_kommandozeile_faellt_ohne_lektor_ordner_auf_naeherung_zurueck(temp_buch, monkeypatch, capsys):
    _nur_englisch(temp_buch)
    _marke(temp_buch)
    gesehen = []
    monkeypatch.setattr(korrektur, "korrigiere", lambda absatz, englisch, model="m", ollama_url="u":
                        gesehen.append(englisch) or "Repariert.")
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    korrektur.main(["-Buch", str(temp_buch.pfad)])
    assert gesehen and gesehen[0].count("EN-") == 9
    assert "Naeherung" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_alle_knoepfe_passen_in_die_handybreite(tmp_path, temp_buch):
    _marke(temp_buch)
    app = EpistoApp(root=tmp_path)
    async with app.run_test(size=(45, 40)) as pilot:
        s = await _oeffne_dialog(app, pilot, temp_buch)
        knoepfe = list(s.query(Button))
        assert len(knoepfe) == 11
        for k in knoepfe:
            assert k.region.width > 0 and k.region.right <= 45, f"{k.id} ragt aus dem Bildschirm: {k.region}"
