"""Tests fuer das tokenbewusste Chunking in ingest.py (ohne Ollama)."""
import importlib.util
import io
import json
import urllib.error
from pathlib import Path

import pytest

SKRIPT = Path(__file__).resolve().parent / "ingest.py"
LIMIT_WOERTER = 100  # "Kontext" des Fake-Modells


@pytest.fixture
def ing():
    spec = importlib.util.spec_from_file_location("ingest_mod", SKRIPT)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture
def fake_embed(ing, monkeypatch):
    aufrufe = []

    def embed(texte):
        aufrufe.append(list(texte))
        if any(len(t.split()) > LIMIT_WOERTER for t in texte):
            raise ing.ZuLang("the input length exceeds the context length")
        return [[float(len(t.split()))] for t in texte]
    monkeypatch.setattr(ing, "embed", embed)
    return aufrufe


def _woerter(paare):
    return " ".join(t for t, _ in paare).split()


def test_halbiere_bevorzugt_absatz_dann_satz_dann_wort(ing):
    assert ing.halbiere("eins zwei\n\ndrei vier fuenf sechs") == ["eins zwei", "drei vier fuenf sechs"]
    assert ing.halbiere("Erster Satz hier. Zweiter Satz hier.") == ["Erster Satz hier.", "Zweiter Satz hier."]
    assert ing.halbiere("a b c d") == ["a b", "c d"]
    a, b = ing.halbiere("abcdefgh")           # kein Leerraum: mitten im Text
    assert a + b == "abcdefgh" and a and b
    assert ing.halbiere("x") is None


def test_passende_chunks_werden_nicht_veraendert(ing, fake_embed):
    chunks = ["wort " * 50, "wort " * 80]
    paare = ing.embed_passend(chunks)
    assert [t for t, _ in paare] == chunks
    assert len(fake_embed) == 1                  # ein einziger Aufruf


def test_zu_lange_chunks_werden_geteilt_ohne_textverlust(ing, fake_embed):
    lang = " ".join(f"w{i}" for i in range(450))                 # 450 Woerter > Limit 100
    kurz = "kurz " * 30
    paare = ing.embed_passend([kurz.strip(), lang, kurz.strip()])
    assert all(len(t.split()) <= LIMIT_WOERTER for t, _ in paare)
    assert len(paare) > 3
    assert _woerter(paare) == (kurz.strip() + " " + lang + " " + kurz.strip()).split()  # nichts fehlt, Reihenfolge stimmt


def test_riesenabsatz_ohne_satzzeichen_terminiert(ing, fake_embed):
    riese = " ".join(f"w{i}" for i in range(3004))               # wie der 3004-Woerter-Chunk der Bibliothek
    paare = ing.embed_passend([riese])
    assert all(len(t.split()) <= LIMIT_WOERTER for t, _ in paare)
    assert _woerter(paare) == riese.split()


def test_text_ohne_leerraum_wird_zur_not_mitten_im_text_geteilt(ing, monkeypatch):
    def embed(texte):
        if any(len(t) > 40 for t in texte):
            raise ing.ZuLang("the input length exceeds the context length")
        return [[0.0] for _ in texte]
    monkeypatch.setattr(ing, "embed", embed)
    paare = ing.embed_passend(["x" * 300])
    assert "".join(t for t, _ in paare) == "x" * 300
    assert all(len(t) <= 40 for t, _ in paare)


def test_embed_sendet_truncate_false_und_meldet_zu_lang(ing, monkeypatch):
    gesendet = []

    def urlopen(req, timeout=None):
        gesendet.append(json.loads(req.data.decode("utf-8")))
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(
            b'{"error":"the input length exceeds the context length"}'))
    monkeypatch.setattr(ing.urllib.request, "urlopen", urlopen)
    with pytest.raises(ing.ZuLang):
        ing.embed(["text"])
    assert gesendet == [{"model": "mxbai-embed-large", "input": ["text"], "truncate": False}]  # kein Retry bei 400


def test_embed_wiederholt_bei_serverfehler_nicht_bei_zu_lang(ing, monkeypatch):
    versuche = []
    monkeypatch.setattr(ing.time, "sleep", lambda s: None)

    def urlopen(req, timeout=None):
        versuche.append(1)
        raise urllib.error.HTTPError(req.full_url, 500, "Server Error", {}, io.BytesIO(b"boom"))
    monkeypatch.setattr(ing.urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        ing.embed(["text"])
    assert len(versuche) == ing.VERSUCHE_EMBED


def test_embed_wiederholt_den_ollama_verbindungsfehler_der_als_400_gemeldet_wird(ing, monkeypatch):
    """Beobachtet im Ingest-Lauf: Ollama meldet "connectex ... Socketadresse nur einmal
    verwendet" (Server -> Runner) als HTTP 400. Das ist KEIN "zu lang" und muss
    wiederholt werden, nicht abbrechen."""
    monkeypatch.setattr(ing.time, "sleep", lambda s: None)
    antworten = [
        urllib.error.HTTPError("u", 400, "Bad Request", {}, io.BytesIO(
            b'{"error":"do embedding request: Post \\"http://127.0.0.1:55913/v1/embeddings\\": dial tcp 127.0.0.1:55913: connectex: ..."}')),
        None,
    ]

    class Antwort:
        def read(self):
            return json.dumps({"embeddings": [[1.0]]}).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        a = antworten.pop(0)
        if a is None:
            return Antwort()
        raise a
    monkeypatch.setattr(ing.urllib.request, "urlopen", urlopen)
    assert ing.embed(["text"]) == [[1.0]]
