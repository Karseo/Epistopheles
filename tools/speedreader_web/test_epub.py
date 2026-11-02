"""Tests fuer epub.js, soweit sie ohne DOM laufen (ZIP-Schicht, Pfade, CSS-Bereinigung).
Das EPUB-Rendering selbst braucht DOMParser und wird im Browser geprueft. Ohne Node
werden die Tests uebersprungen."""
import base64
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

HIER = Path(__file__).resolve().parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node nicht installiert")

SKRIPT = r"""
const E = require(process.argv[1]);
const eingabe = JSON.parse(require("fs").readFileSync(0, "utf8"));
(async () => {
  const buf = Buffer.from(eingabe.zip, "base64");
  const ab = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
  const aus = {};
  try {
    const z = E.oeffneZip(ab);
    aus.namen = z.namen();
    aus.eins = await z.text("OEBPS/text.xhtml");
    aus.gespeichert = await z.text("mimetype");
    aus.umlaut = await z.text("OEBPS/Kapitel äöü.xhtml");
    aus.binaer = Array.from(await z.lies("OEBPS/bild.bin"));
    aus.hat = [z.hat("mimetype"), z.hat("gibt-es-nicht")];
    try { await z.lies("gibt-es-nicht"); } catch (e) { aus.fehlt = e.message; }
  } catch (e) { aus.fehler = e.message; }
  aus.pfade = [
    E.pfadAufloesen("OEBPS/text/k1.xhtml", "../bilder/a%20b.png#x"),
    E.pfadAufloesen("OEBPS/k1.xhtml", "k2.xhtml#anker"),
    E.pfadAufloesen("OEBPS/k1.xhtml", "/abs/x.css"),
    E.pfadAufloesen("content.opf", "text/k1.xhtml"),
  ];
  aus.css = E.bereinigeCss("@import url(a.css);@font-face{font-family:X;src:url(f.woff)}p{background:url(bild.png)}i{background:url(data:image/png;base64,AA)}");
  process.stdout.write(JSON.stringify(aus));
})();
"""


def _zip(pfad: Path, mit_muell: bool = False) -> bytes:
    with zipfile.ZipFile(pfad, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("OEBPS/text.xhtml", "<p>Hallo Welt, äöü ß. " + "Wiederholung " * 200 + "</p>", compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/Kapitel äöü.xhtml", "Umlaut im Namen", compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/bild.bin", bytes(range(256)), compress_type=zipfile.ZIP_DEFLATED)
    daten = pfad.read_bytes()
    return daten + b"Muell" if mit_muell else daten


def _node(zipdaten: bytes) -> dict:
    lauf = subprocess.run([NODE, "-e", SKRIPT, str(HIER / "epub.js")],
                          input=json.dumps({"zip": base64.b64encode(zipdaten).decode()}),
                          capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(lauf.stdout)


def test_zip_liest_gespeicherte_und_komprimierte_eintraege(tmp_path):
    aus = _node(_zip(tmp_path / "t.epub"))
    assert aus["namen"] == ["mimetype", "OEBPS/text.xhtml", "OEBPS/Kapitel äöü.xhtml", "OEBPS/bild.bin"]
    assert aus["gespeichert"] == "application/epub+zip"
    assert aus["eins"].startswith("<p>Hallo Welt, äöü ß. Wiederholung") and aus["eins"].endswith("</p>")
    assert aus["umlaut"] == "Umlaut im Namen"
    assert aus["binaer"] == list(range(256))
    assert aus["hat"] == [True, False]
    assert "Nicht im Archiv" in aus["fehlt"]


def test_zip_toleriert_angehaengte_bytes_und_meldet_keine_zip_datei(tmp_path):
    assert _node(_zip(tmp_path / "t.epub", mit_muell=True))["gespeichert"] == "application/epub+zip"
    assert "Keine ZIP" in _node(b"das ist kein zip, nur Text" * 10)["fehler"]


def test_pfade_werden_relativ_zur_datei_aufgeloest(tmp_path):
    pfade = _node(_zip(tmp_path / "t.epub"))["pfade"]
    assert pfade == ["OEBPS/bilder/a b.png", "OEBPS/k2.xhtml", "abs/x.css", "text/k1.xhtml"]


def test_css_bereinigung_entfernt_nicht_ladbares_und_behaelt_data_urls(tmp_path):
    css = _node(_zip(tmp_path / "t.epub"))["css"]
    assert "@import" not in css and "@font-face" not in css and "bild.png" not in css
    assert 'url("")' in css and "data:image/png;base64,AA" in css
