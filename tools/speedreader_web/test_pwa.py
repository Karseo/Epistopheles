"""PWA: Manifest, Icons und Service-Worker-Huelle passen zum Paket."""
import json
import re
from pathlib import Path

import bundle

HIER = Path(__file__).resolve().parent


def test_manifest_verweist_auf_vorhandene_dateien():
    m = json.loads((HIER / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert m["display"] == "standalone" and m["start_url"] == "index.html"
    for ic in m["icons"]:
        assert (HIER / ic["src"]).is_file()
    assert {i["sizes"] for i in m["icons"]} >= {"192x192", "512x512"}


def test_huelle_des_service_workers_liegt_im_paket(tmp_path):
    sw = (HIER / "sw.js").read_text(encoding="utf-8")
    huelle = re.search(r"const HUELLE = \[(.*?)\];", sw, re.S).group(1)
    namen = [n for n in re.findall(r'"([^"]+)"', huelle) if n != "./"]
    kopiert = bundle.kopiere_app(tmp_path / "paket")
    assert set(namen) <= set(kopiert)
    assert {"sw.js", "manifest.webmanifest"} <= set(kopiert)


def test_seiten_binden_manifest_und_service_worker_ein():
    for seite in ("index.html", "korrektur.html"):
        t = (HIER / seite).read_text(encoding="utf-8")
        assert 'rel="manifest"' in t and "serviceWorker" in t


def test_alle_skripte_der_seiten_stehen_in_huelle_und_pages_workflow():
    """Sonst fehlt eine Datei offline (Service Worker) oder auf GitHub Pages."""
    sw = (HIER / "sw.js").read_text(encoding="utf-8")
    huelle = set(re.findall(r'"([^"]+)"', re.search(r"const HUELLE = \[(.*?)\];", sw, re.S).group(1)))
    wf = (HIER.parent.parent / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    for seite in ("index.html", "korrektur.html"):
        for src in re.findall(r'<script src="([^"]+)"', (HIER / seite).read_text(encoding="utf-8")):
            assert src in huelle, (seite, src)
            assert src in wf, (seite, src)
