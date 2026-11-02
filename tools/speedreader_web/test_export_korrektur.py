"""Tests fuer export_korrektur.py (Datenquelle der geteilten Korrekturansicht):
Quelldatei und Rohchunks aus dem Lektor-Ordner, bereinigter Text aus der Bibliothek."""
import json
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent))

import export_korrektur  # noqa: E402
from episto_tui import library  # noqa: E402


def _repo_buch(root: Path, autor: str, titel: str, kapitel: dict) -> None:
    quelle = root / "reader" / autor / titel / "quelle"
    quelle.mkdir(parents=True)
    for datei, text in kapitel.items():
        (quelle / datei).write_text(text, encoding="utf-8")


def _lektor_buch(lektor: Path, autor: str, titel: str, *, ebook: tuple[str, str] | None = None,
                 en_chunks=(), de_chunks=(), meta=None, ebook_inhalt: bytes = b"EBOOK") -> None:
    """ebook = (Unterordner, Dateiname), z. B. ("en", "Buch.pdf")."""
    basis = lektor / autor / titel
    (basis / "en").mkdir(parents=True)
    (basis / "de").mkdir()
    for i, t in enumerate(en_chunks):
        (basis / "en" / f"chunk_{i:03d}.md").write_text(t, encoding="utf-8")
    for i, t in enumerate(de_chunks):
        (basis / "de" / f"chunk_{i:03d}.md").write_text(t, encoding="utf-8")
    if ebook:
        (basis / ebook[0] / ebook[1]).write_bytes(ebook_inhalt)
    if meta is not None:
        (basis / "meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_fremdsprachige_quelle_rohchunks_aus_en_und_ebook_wird_mitgeliefert(tmp_path):
    root, lektor, ordner = tmp_path / "bib", tmp_path / "lektor", tmp_path / "aus" / "korrektur"
    _repo_buch(root, "Alonso, S", "Future", {"0001_a.md": "# A\n\nText ä", "0002_b.md": "B"})
    _lektor_buch(lektor, "Alonso, S", "Future", ebook=("en", "Future (ed.).pdf"),
                 en_chunks=["Eins\twort\n", "Zwei"], de_chunks=["Übersetzt 1", "Übersetzt 2"],
                 meta={"quellsprache": "en", "quelldatei": "C:\\Users\\Dude\\Tools\\eBooks\\Lektor\\x\\en\\Future (ed.).pdf"},
                 ebook_inhalt=b"%PDF-1.4 test")

    index = export_korrektur.exportiere(root, ordner, lektor)

    (b,) = index["buecher"]
    assert b["id"] == "k001" and b["quellsprache"] == "en" and b["quelldatei"] == "Future (ed.).pdf"
    assert b["chunkSprache"] == "en" and b["chunks"] == 2 and b["ebook"] == "k001.pdf"
    assert [k["titel"] for k in b["kapitel"]] == ["0001_a", "0002_b"]
    assert (ordner / "k001.pdf").read_bytes() == b"%PDF-1.4 test"
    daten = json.loads((ordner / "k001.json").read_text(encoding="utf-8"))
    assert daten["chunks"] == ["Eins\twort\n", "Zwei"]                      # Rohtext unveraendert, nicht die Uebersetzung
    assert daten["uebersetzung"] == ["Übersetzt 1", "Übersetzt 2"] and b["uebersetzung"] == 2
    assert daten["kapitel"][0] == {"nr": 1, "titel": "0001_a", "datei": "0001_a.md", "text": "# A\n\nText ä"}
    assert daten["erstellt"] == index["erstellt"]
    assert json.loads((ordner / "index.json").read_text(encoding="utf-8")) == index


def test_deutsche_quelle_rohchunks_stehen_in_de_beim_epub(tmp_path):
    root, lektor, ordner = tmp_path / "bib", tmp_path / "lektor", tmp_path / "korrektur"
    _lektor_buch(lektor, "Aigner, F", "Wirklichkeit", ebook=("de", "Aigner.epub"), de_chunks=["Deutsch 1", "Deutsch 2", "Deutsch 3"],
                 meta={"quellsprache": "de", "quelldatei": "/mnt/c/x/de/Aigner.epub"})
    (b,) = export_korrektur.exportiere(root, ordner, lektor)["buecher"]
    assert b["chunkSprache"] == "de" and b["chunks"] == 3 and b["ebook"] == "k001.epub" and b["kapitel"] == []
    assert b["uebersetzung"] == 0 and json.loads((ordner / "k001.json").read_text(encoding="utf-8"))["uebersetzung"] == []   # de\ ist hier die Extraktion
    assert json.loads((ordner / "k001.json").read_text(encoding="utf-8"))["chunks"] == ["Deutsch 1", "Deutsch 2", "Deutsch 3"]


def test_vereinigung_buecher_nur_im_lektor_oder_nur_in_der_bibliothek(tmp_path):
    root, lektor, ordner = tmp_path / "bib", tmp_path / "lektor", tmp_path / "korrektur"
    _repo_buch(root, "B, B", "Nur Repo", {"0001.md": "x"})
    _lektor_buch(lektor, "A, A", "Neu im Lektor", ebook=("en", "n.epub"), en_chunks=["c"])
    index = export_korrektur.exportiere(root, ordner, lektor)
    assert [(b["autor"], b["titel"]) for b in index["buecher"]] == [("A, A", "Neu im Lektor"), ("B, B", "Nur Repo")]
    neu, nur_repo = index["buecher"]
    assert neu["kapitel"] == [] and neu["chunks"] == 1 and neu["ebook"] == "k001.epub"
    assert nur_repo["ebook"] == "" and nur_repo["chunks"] == 0 and len(nur_repo["kapitel"]) == 1
    assert not (ordner / "k002.pdf").exists() and not (ordner / "k002.epub").exists()


def test_kapitelgrenzen_aus_dem_lektor_kapitel_json_werden_sortiert_mitgegeben(tmp_path):
    root, lektor, ordner = tmp_path / "bib", tmp_path / "lektor", tmp_path / "korrektur"
    _lektor_buch(lektor, "A", "B", ebook=("en", "b.pdf"), en_chunks=[f"c{i}" for i in range(6)])
    (lektor / "A" / "B" / "kapitel.json").write_text(json.dumps({"segmente": [
        {"id": "k-2", "nr": "2", "titel": "Zweites", "chunk": 4, "position": 100, "vorspann": False},
        {"id": "vor", "nr": "", "titel": "Vorwort", "chunk": 0, "position": 0, "vorspann": True},
        {"id": "k-1", "nr": "1", "titel": "Erstes", "chunk": 2, "position": 50, "vorspann": False},
    ]}), encoding="utf-8")
    (b,) = export_korrektur.exportiere(root, ordner, lektor)["buecher"]
    assert b["segmente"] == 3
    seg = json.loads((ordner / "k001.json").read_text(encoding="utf-8"))["segmente"]
    assert [(s["titel"], s["chunk"]) for s in seg] == [("Vorwort", 0), ("Erstes", 2), ("Zweites", 4)]   # nach chunk/position sortiert
    assert seg[0] == {"nr": "", "titel": "Vorwort", "chunk": 0, "position": 0, "vorspann": True}        # nur die noetigen Felder


def test_ohne_kapitel_json_oder_mit_kaputtem_keine_kapitelgrenzen(tmp_path):
    root, lektor, ordner = tmp_path / "bib", tmp_path / "lektor", tmp_path / "korrektur"
    _lektor_buch(lektor, "A", "B", en_chunks=["c"])
    _lektor_buch(lektor, "A", "C", en_chunks=["c"])
    (lektor / "A" / "C" / "kapitel.json").write_text("{kaputt", encoding="utf-8")
    index = export_korrektur.exportiere(root, ordner, lektor)
    assert [b["segmente"] for b in index["buecher"]] == [0, 0]


def test_rohchunks_fallen_auf_rohdaten_en_chunks_zurueck_wenn_der_lektor_keine_hat(tmp_path):
    root, ordner = tmp_path / "bib", tmp_path / "korrektur"
    lektor = root / "rohdaten" / "Lektor"
    _repo_buch(root, "Bourdieu, P", "State Nobility", {"0001.md": "x"})
    en = root / "rohdaten" / "en-chunks" / "Bourdieu, P" / "State Nobility"
    en.mkdir(parents=True)
    for i in range(3):
        (en / f"chunk_{i:03d}.md").write_text(f"raw {i}", encoding="utf-8")
    lektor.mkdir(parents=True)                                       # Lektor existiert, kennt das Buch aber nicht
    (b,) = export_korrektur.exportiere(root, ordner, lektor)["buecher"]
    assert b["chunks"] == 3 and b["chunkSprache"] == "en" and b["chunkQuelle"] == "en-chunks"
    assert json.loads((ordner / "k001.json").read_text(encoding="utf-8"))["chunks"] == ["raw 0", "raw 1", "raw 2"]


def test_lektor_chunks_haben_vorrang_vor_en_chunks(tmp_path):
    root, ordner = tmp_path / "bib", tmp_path / "korrektur"
    lektor = root / "rohdaten" / "Lektor"
    _repo_buch(root, "A", "B", {"0001.md": "x"})
    _lektor_buch(lektor, "A", "B", ebook=("en", "b.pdf"), en_chunks=["lektor0"])
    en = root / "rohdaten" / "en-chunks" / "A" / "B"
    en.mkdir(parents=True)
    (en / "chunk_000.md").write_text("en-chunks0", encoding="utf-8")
    (b,) = export_korrektur.exportiere(root, ordner, lektor)["buecher"]
    assert b["chunkQuelle"] == "lektor"
    assert json.loads((ordner / "k001.json").read_text(encoding="utf-8"))["chunks"] == ["lektor0"]


def _repo_meta(root: Path, autor: str, titel: str, meta: dict) -> None:
    (root / "reader" / autor / titel / "meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_zuordnung_ueber_meta_pfad_bei_abweichendem_ordnernamen(tmp_path):
    root, lektor, ordner = tmp_path / "bib", tmp_path / "Lektor", tmp_path / "korrektur"
    _repo_buch(root, "O'Neil, Cathy", "Weapons", {"0001.md": "x"})
    _lektor_buch(lektor, "Cathy O'Neil", "Weapons of Math Destruction", ebook=("en", "w.epub"), en_chunks=["c1", "c2"])
    _repo_meta(root, "O'Neil, Cathy", "Weapons",
               {"quelldatei": f"C:\\Users\\x\\Lektor\\Cathy O'Neil\\Weapons of Math Destruction\\en\\w.epub"})
    index = export_korrektur.exportiere(root, ordner, lektor)
    (b,) = index["buecher"]                                          # kein Duplikat: Repo- und Lektor-Buch sind eins
    assert (b["autor"], b["titel"]) == ("O'Neil, Cathy", "Weapons")
    assert b["chunks"] == 2 and b["ebook"] == "k001.epub" and len(b["kapitel"]) == 1


def test_zuordnung_ueber_eindeutig_aehnlichen_titel(tmp_path):
    root, lektor, ordner = tmp_path / "bib", tmp_path / "Lektor", tmp_path / "korrektur"
    _repo_buch(root, "Piano, N", "Democratic Elitism", {"0001.md": "x"})
    _lektor_buch(lektor, "Piano, N", "Democratic Elitism_ The Founding Myth", ebook=("en", "p.pdf"), en_chunks=["c"])
    _lektor_buch(lektor, "Anders, A", "Ganz Anderes Buch", ebook=("en", "a.pdf"), en_chunks=["c"])
    index = export_korrektur.exportiere(root, ordner, lektor)
    assert [(b["titel"], b["chunks"], len(b["kapitel"])) for b in index["buecher"]] == [
        ("Ganz Anderes Buch", 1, 0), ("Democratic Elitism", 1, 1)]


def test_quelldatei_ausserhalb_des_lektors_wird_aus_meta_pfad_geholt(tmp_path):
    root, lektor, ordner = tmp_path / "bib", tmp_path / "Lektor", tmp_path / "korrektur"
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    (inbox / "Kahneman.epub").write_bytes(b"PK inbox")
    lektor.mkdir()
    _repo_buch(root, "K, D", "Schnelles Denken", {"0001.md": "x"})
    _repo_meta(root, "K, D", "Schnelles Denken", {"quellsprache": "de", "quelldatei": str(inbox / "Kahneman.epub")})
    (b,) = export_korrektur.exportiere(root, ordner, lektor)["buecher"]
    assert b["ebook"] == "k001.epub" and b["chunks"] == 0 and b["quelldatei"] == "Kahneman.epub"
    assert (ordner / "k001.epub").read_bytes() == b"PK inbox"


def test_alter_ablageort_in_meta_wird_unter_dem_ebooks_ordner_neu_aufgesetzt(tmp_path):
    """Seit dem Umzug nach <Bibliothek>\\eBooks nennt die meta.json noch C:\\Users\\Dude\\Tools\\eBooks\\Inbox\\..."""
    root, ebooks, ordner = tmp_path / "bib", tmp_path / "eBooks", tmp_path / "korrektur"
    (ebooks / "Inbox").mkdir(parents=True)
    (ebooks / "Lektor").mkdir()
    (ebooks / "Inbox" / "Kahneman.epub").write_bytes(b"PK neu")
    _repo_buch(root, "K, D", "Schnelles Denken", {"0001.md": "x"})
    _repo_meta(root, "K, D", "Schnelles Denken",
               {"quelldatei": "C:\\Users\\Dude\\Tools\\eBooks\\Inbox\\Kahneman.epub"})
    (b,) = export_korrektur.exportiere(root, ordner, ebooks / "Lektor")["buecher"]
    assert b["ebook"] == "k001.epub" and (ordner / "k001.epub").read_bytes() == b"PK neu"


def test_main_nimmt_standardmaessig_den_lektor_unter_der_bibliothek(tmp_path, monkeypatch):
    root = tmp_path / "bib"
    _repo_buch(root, "A", "B", {"0001.md": "x"})
    _lektor_buch(root / "rohdaten" / "Lektor", "A", "B", ebook=("en", "b.pdf"), en_chunks=["c0", "c1"])
    monkeypatch.delenv("EPISTO_LEKTOR", raising=False)
    out = tmp_path / "korrektur"
    assert export_korrektur.main(["--root", str(root), "--out", str(out), "--ohne-app"]) == 0
    (b,) = json.loads((out / "index.json").read_text(encoding="utf-8"))["buecher"]
    assert b["chunks"] == 2 and b["ebook"] == "k001.pdf"


def test_standardausgabe_ist_das_epistopheles_paket_samt_app_dateien(tmp_path, monkeypatch):
    root = tmp_path / "bib"
    _repo_buch(root, "A", "B", {"0001.md": "x"})
    _lektor_buch(root / "rohdaten" / "Lektor", "A", "B", ebook=("en", "b.pdf"), en_chunks=["c0"])
    monkeypatch.delenv("EPISTO_LEKTOR", raising=False)
    assert export_korrektur.main(["--root", str(root)]) == 0
    paket = root / "reader" / "export-epistopheles"
    assert (paket / "korrektur" / "index.json").is_file() and (paket / "korrektur" / "k001.pdf").is_file()
    for name in ("index.html", "korrektur.html", "speedreader.js", "lesetext.js", "epub.js"):
        assert (paket / name).is_file(), name
    # das Paket liegt im reader-Ordner, ist aber kein Buch
    assert [b.titel for b in library.discover_books(root)] == ["B"]


def test_ohne_app_laesst_die_app_dateien_weg(tmp_path, monkeypatch):
    root = tmp_path / "bib"
    _repo_buch(root, "A", "B", {"0001.md": "x"})
    monkeypatch.delenv("EPISTO_LEKTOR", raising=False)
    assert export_korrektur.main(["--root", str(root), "--ohne-app"]) == 0
    paket = root / "reader" / "export-epistopheles"
    assert (paket / "korrektur" / "index.json").is_file() and not (paket / "index.html").exists()


def test_pfad_aus_meta_wsl_und_windows():
    assert str(export_korrektur.pfad_aus_meta("/mnt/c/Users/Dude/x.epub")).replace("\\", "/") == "C:/Users/Dude/x.epub"
    assert export_korrektur.pfad_aus_meta("C:\\a\\b.pdf").name == "b.pdf"
    assert export_korrektur.pfad_aus_meta("") is None


def test_quelldatei_aus_meta_hat_vorrang_und_ohne_ebooks_wird_nichts_kopiert(tmp_path):
    root, lektor, ordner = tmp_path / "bib", tmp_path / "lektor", tmp_path / "korrektur"
    _lektor_buch(lektor, "A", "B", ebook=("en", "a_erste.pdf"), en_chunks=["c"], meta={"quelldatei": "/x/z_gesucht.epub"})
    (lektor / "A" / "B" / "en" / "z_gesucht.epub").write_bytes(b"PK gesucht")
    (b,) = export_korrektur.exportiere(root, ordner, lektor)["buecher"]
    assert b["quelldatei"] == "z_gesucht.epub" and b["ebook"] == "k001.epub"
    assert (ordner / "k001.epub").read_bytes() == b"PK gesucht"
    (b,) = export_korrektur.exportiere(root, ordner, lektor, ebooks=False)["buecher"]
    assert b["ebook"] == "" and b["quelldatei"] == "z_gesucht.epub"
    assert not list(ordner.glob("k*.epub")) and not list(ordner.glob("k*.pdf"))   # auch Reste sind weg


def test_chunks_in_numerischer_reihenfolge_und_reste_werden_entfernt(tmp_path):
    root, lektor, ordner = tmp_path / "bib", tmp_path / "lektor", tmp_path / "korrektur"
    _lektor_buch(lektor, "A", "B", ebook=("en", "b.pdf"), en_chunks=[f"c{i}" for i in range(12)])
    ordner.mkdir()
    (ordner / "k099.json").write_text("{}", encoding="utf-8")
    (ordner / "k099.pdf").write_bytes(b"alt")
    (ordner / "andere.txt").write_text("bleibt", encoding="utf-8")
    export_korrektur.exportiere(root, ordner, lektor)
    assert not (ordner / "k099.json").exists() and not (ordner / "k099.pdf").exists()
    assert (ordner / "andere.txt").exists()                                  # Fremdes wird nicht angefasst
    assert json.loads((ordner / "k001.json").read_text(encoding="utf-8"))["chunks"] == [f"c{i}" for i in range(12)]


def test_main_ohne_lektor_ordner_exportiert_trotzdem(tmp_path, capsys):
    _repo_buch(tmp_path / "bib", "A", "B", {"0001.md": "x"})
    out = tmp_path / "korrektur"
    assert export_korrektur.main(["--root", str(tmp_path / "bib"), "--lektor", str(tmp_path / "gibt-es-nicht"), "--out", str(out)]) == 0
    assert "Lektor-Ordner nicht gefunden" in capsys.readouterr().out
    assert json.loads((out / "index.json").read_text(encoding="utf-8"))["buecher"][0]["chunks"] == 0


def test_dateiname_von_beiden_schreibweisen():
    assert export_korrektur.dateiname_von("C:\\a\\b\\Buch.pdf") == "Buch.pdf"
    assert export_korrektur.dateiname_von("/mnt/c/x/Buch.epub") == "Buch.epub"
    assert export_korrektur.dateiname_von("") == ""


# --- P2 Task 1: Volltext-Metadaten ------------------------------------------------------------------

def test_kapitel_haben_dateiname(tmp_path):
    root, ordner = tmp_path / "bib", tmp_path / "korrektur"
    _repo_buch(root, "A, B", "T", {"0001_a.md": "x", "0002_b.md": "y"})
    export_korrektur.exportiere(root, ordner, tmp_path / "lektor")
    daten = json.loads((ordner / "k001.json").read_text(encoding="utf-8"))
    assert [k["datei"] for k in daten["kapitel"]] == ["0001_a.md", "0002_b.md"]


def test_kapitel_text_behaelt_windows_zeilenenden(tmp_path):
    root, ordner = tmp_path / "bib", tmp_path / "korrektur"
    _repo_buch(root, "A, B", "T", {})
    roh = "# Titel\r\n\r\nWort\tTab\r\nzweite Zeile\r\n\r\nSchluss"
    (root / "reader" / "A, B" / "T" / "quelle" / "0001_a.md").write_bytes(roh.encode("utf-8"))
    export_korrektur.exportiere(root, ordner, tmp_path / "lektor")
    daten = json.loads((ordner / "k001.json").read_text(encoding="utf-8"))
    assert daten["kapitel"][0]["text"] == roh


def test_index_nennt_reader_und_lektor_schluessel(tmp_path):
    root, lektor, ordner = tmp_path / "bib", tmp_path / "Lektor", tmp_path / "korrektur"
    _repo_buch(root, "O'Neil, Cathy", "Weapons", {"0001.md": "x"})
    _lektor_buch(lektor, "Cathy O'Neil", "Weapons of Math Destruction", ebook=("en", "w.epub"), en_chunks=["c1"])
    _repo_meta(root, "O'Neil, Cathy", "Weapons",
               {"quelldatei": "C:\\Users\\x\\Lektor\\Cathy O'Neil\\Weapons of Math Destruction\\en\\w.epub"})
    (b,) = export_korrektur.exportiere(root, ordner, lektor)["buecher"]
    assert b["reader"] == "O'Neil, Cathy/Weapons"
    assert b["lektor"] == "Cathy O'Neil/Weapons of Math Destruction"


def test_schluessel_leer_wenn_buch_nur_auf_einer_seite_existiert(tmp_path):
    root, lektor, ordner = tmp_path / "bib", tmp_path / "lektor", tmp_path / "korrektur"
    _repo_buch(root, "Nur, Reader", "T", {"0001.md": "x"})
    _lektor_buch(lektor, "Nur Lektor", "T2", en_chunks=["c"])
    buecher = {b["autor"]: b for b in export_korrektur.exportiere(root, ordner, lektor)["buecher"]}
    assert (buecher["Nur, Reader"]["reader"], buecher["Nur, Reader"]["lektor"]) == ("Nur, Reader/T", "")
    assert (buecher["Nur Lektor"]["reader"], buecher["Nur Lektor"]["lektor"]) == ("", "Nur Lektor/T2")


def _redaktion(root: Path, inhalt) -> None:
    pfad = root / "reader" / "A, B" / "T" / "notizen"
    pfad.mkdir(parents=True, exist_ok=True)
    (pfad / "redaktion.json").write_text(inhalt if isinstance(inhalt, str) else json.dumps(inhalt), encoding="utf-8")


def test_enthalten_listet_angewendete_volltext_eintraege(tmp_path):
    root, ordner = tmp_path / "bib", tmp_path / "korrektur"
    _repo_buch(root, "A, B", "T", {"0001.md": "x"})
    _redaktion(root, {"eintraege": [
        {"id": "a1", "ebene": "volltext", "status": "angewendet"},
        {"id": "a2", "ebene": "volltext", "status": "offen"},
        {"id": "a3", "ebene": "chunk-orig", "status": "angewendet"},
        {"id": 7, "ebene": "volltext", "status": "angewendet"},
        "kein objekt",
    ]})
    export_korrektur.exportiere(root, ordner, tmp_path / "lektor")
    assert json.loads((ordner / "k001.json").read_text(encoding="utf-8"))["enthalten"] == ["a1"]


def test_enthalten_ist_leer_ohne_oder_mit_kaputter_datei(tmp_path):
    root, ordner = tmp_path / "bib", tmp_path / "korrektur"
    _repo_buch(root, "A, B", "T", {"0001.md": "x"})
    export_korrektur.exportiere(root, ordner, tmp_path / "lektor")
    assert json.loads((ordner / "k001.json").read_text(encoding="utf-8"))["enthalten"] == []
    for kaputt in ("{nicht json", "[]", '{"eintraege": 5}'):
        _redaktion(root, kaputt)
        export_korrektur.exportiere(root, ordner, tmp_path / "lektor")
        assert json.loads((ordner / "k001.json").read_text(encoding="utf-8"))["enthalten"] == []


def test_enthalten_nimmt_nachspiel_konflikte_aus_und_nennt_sie_mit_grund(tmp_path):
    """Review-Befund 1: Was beim Neuaufbau nicht wieder eingespielt werden konnte, steckt nicht im Text."""
    root, ordner = tmp_path / "bib", tmp_path / "korrektur"
    _repo_buch(root, "A, B", "T", {"0001.md": "x"})
    _redaktion(root, {"eintraege": [{"id": "ok", "ebene": "volltext", "status": "angewendet"},
                                    {"id": "weg", "ebene": "volltext", "status": "angewendet"}]})
    nachspiel = root / "reader" / "A, B" / "T" / "notizen" / "redaktion-nachspiel.json"
    nachspiel.write_text(json.dumps({"konflikte": [{"id": "weg", "datei": "0001.md", "grund": "Absatz nicht gefunden"},
                                                   {"id": None, "datei": None, "grund": "redaktion.json unlesbar"}]}), encoding="utf-8")
    export_korrektur.exportiere(root, ordner, tmp_path / "lektor")
    d = json.loads((ordner / "k001.json").read_text(encoding="utf-8"))
    assert d["enthalten"] == ["ok"] and d["nachspiel"] == {"weg": "Absatz nicht gefunden"}


def test_nachspiel_ist_leer_ohne_oder_mit_kaputtem_bericht(tmp_path):
    root, ordner = tmp_path / "bib", tmp_path / "korrektur"
    _repo_buch(root, "A, B", "T", {"0001.md": "x"})
    export_korrektur.exportiere(root, ordner, tmp_path / "lektor")
    assert json.loads((ordner / "k001.json").read_text(encoding="utf-8"))["nachspiel"] == {}
    n = root / "reader" / "A, B" / "T" / "notizen"
    n.mkdir(parents=True, exist_ok=True)
    for kaputt in ("{kaputt", "[]", '{"konflikte": 5}'):
        (n / "redaktion-nachspiel.json").write_text(kaputt, encoding="utf-8")
        export_korrektur.exportiere(root, ordner, tmp_path / "lektor")
        assert json.loads((ordner / "k001.json").read_text(encoding="utf-8"))["nachspiel"] == {}
