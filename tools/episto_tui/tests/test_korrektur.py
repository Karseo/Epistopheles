import json
from pathlib import Path
import requests
import episto_tui.korrektur as korrektur
from episto_tui import library
from episto_tui.models import Highlight


def _buch_mit_grounding(temp_buch):
    r"""Legt meta.json + en\chunk_*.md an, damit englischer_kapiteltext greift."""
    # meta.json mit lektor_pfad (zeigt auf einen Lektor-Ordner mit kapitel.json)
    lektor = temp_buch.pfad / "_lektor"
    (lektor).mkdir()
    (lektor / "kapitel.json").write_text(json.dumps({"segmente": [
        {"id": "s1", "titel": "Einleitung", "chunk": 0, "position": 0, "vorspann": False},
        {"id": "s2", "titel": "Kap1", "chunk": 2, "position": 0, "vorspann": False},
    ]}, ensure_ascii=False), encoding="utf-8")
    (temp_buch.pfad / "meta.json").write_text(json.dumps({
        "lektor_pfad": str(lektor), "chunks": 4,
    }), encoding="utf-8")
    en = temp_buch.pfad / "en"
    en.mkdir()
    for i in range(4):
        (en / f"chunk_{i:03d}.md").write_text(f"EN{i}\n\n", encoding="utf-8")
    return temp_buch


def test_ersetze_absatz_ersetzt_nur_den_zielabsatz():
    text = "Absatz eins.\n\nAbsatz zwei.\n\nAbsatz drei."
    neu = korrektur.ersetze_absatz(text, 1, "Korrigiert.")
    assert neu == "Absatz eins.\n\nKorrigiert.\n\nAbsatz drei.\n"


def test_englischer_kapiteltext_liefert_chunks_des_kapitels(temp_buch):
    buch = _buch_mit_grounding(temp_buch)
    # Kapitel 1 (nr=1) = segmente[0] (chunk 0) bis segmente[1] (chunk 2) inklusive
    text = korrektur.englischer_kapiteltext(buch, 1)
    assert "EN0" in text and "EN2" in text and "EN3" not in text


def test_sammle_marken_findet_nur_korrektur(temp_buch):
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=0, absatz_anfang="A", farbe="korrektur"))
    library.write_highlight(temp_buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=1, absatz_anfang="B", farbe="gelb"))
    marken = korrektur.sammle_marken(temp_buch)
    assert [h.farbe for h in marken] == ["korrektur"]


def test_korrigiere_schickt_absatz_und_original_ans_llm(monkeypatch):
    gesendet = {}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"message": {"content": "korrigierter absatz"}}

    def fake_post(url, json, timeout):
        gesendet["url"] = url
        gesendet["body"] = json
        return FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)
    out = korrektur.korrigiere("kaputt [^12]", "The original chapter", model="m", ollama_url="http://x")
    assert out == "korrigierter absatz"
    assert gesendet["body"]["model"] == "m"
    assert "kaputt [^12]" in gesendet["body"]["messages"][1]["content"]
    assert "The original chapter" in gesendet["body"]["messages"][1]["content"]


def _buch_mit_korrektur_marke(temp_buch):
    """Grounding + eine korrektur-Marke auf Absatz 1 von Kapitel 0001."""
    buch = _buch_mit_grounding(temp_buch)
    library.write_highlight(buch, Highlight(
        datei="0001_erstes-kapitel.md", absatz_index=1,
        absatz_anfang="Zweiter Absatz mit mehr Inhalt zum Testen.", farbe="korrektur"))
    return buch


def test_write_back_uebernimmt_korrektur_und_sichert_backup(temp_buch, monkeypatch):
    buch = _buch_mit_korrektur_marke(temp_buch)
    monkeypatch.setattr(korrektur, "korrigiere",
                        lambda absatz, englisch, model="m", ollama_url="u": "KORRIGIERTER ZWEITER ABSATZ.")
    monkeypatch.setattr("builtins.input", lambda prompt="": "j")
    korrektur.main(["-Buch", str(buch.pfad)])
    assert library.read_highlights_nach_farbe(buch, "korrektur") == []
    backups = list((buch.pfad / "notizen" / "_backup").glob("*.md"))
    assert backups
    assert "KORRIGIERTER ZWEITER ABSATZ." in library.read_chapter_text(buch, "0001_erstes-kapitel.md")


def test_write_back_ablehnung_laesst_marke_stehen(temp_buch, monkeypatch):
    buch = _buch_mit_korrektur_marke(temp_buch)
    monkeypatch.setattr(korrektur, "korrigiere",
                        lambda absatz, englisch, model="m", ollama_url="u": "KORRIGIERTER ZWEITER ABSATZ.")
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    korrektur.main(["-Buch", str(buch.pfad)])
    assert len(library.read_highlights_nach_farbe(buch, "korrektur")) == 1
    assert "KORRIGIERTER ZWEITER ABSATZ." not in library.read_chapter_text(buch, "0001_erstes-kapitel.md")
