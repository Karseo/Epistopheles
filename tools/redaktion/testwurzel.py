"""Baut eine kleine Test-Bibliothek samt Epistopheles-Paket, fuer Browserpruefungen der App.

    from redaktion.testwurzel import baue_testwurzel
    root = baue_testwurzel(Path(tempfile.mkdtemp()) / "wurzel")
    # python tools/redaktion_server.py --root <root> --port 8791  ->  http://127.0.0.1:8791/korrektur.html

Ein Buch "Test, Autor/Testbuch": ein bereinigtes Kapitel (mit KI-Feldern), drei Rohchunks (en) im
Rohstil (Tabs zwischen Woertern, harter Zeilenumbruch, ein an einer Fussnote gebrochener Satz,
Seitenzahlzeile, Kapitelueberschrift) und drei Uebersetzungen (de). Nur Standardbibliothek."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent
_WEB = _TOOLS / "speedreader_web"
for _p in (str(_TOOLS), str(_WEB)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

AUTOR, TITEL = "Test, Autor", "Testbuch"


def _tabs(satz: str) -> str:
    return "\t".join(satz.split())


ROH = [
    "\n".join([
        "CHAPTER 1",
        "",
        _tabs("The representative is not merely a delegate of the voters, as Pitkin"),
        _tabs("emphasized in her study of the concept and its history; she"),
        _tabs("betonte¹"),
        "12 Vgl. Pitkin (1967), S. 8.",
        _tabs("dass die Abgeordneten ihr Urteil nicht bloss weitergeben."),
        "",
        "— 47 —",
        "",
        _tabs("A second paragraph follows here, with ordinary words and"),
        _tabs("another hard-wrapped line at the end."),
        "",
    ]),
    "\n".join([
        _tabs("Representation requires both distance and responsiveness, so"),
        _tabs("that the people can judge the actions of those who act"),
        _tabs("in their name."),
        "",
        "— 48 —",
        "",
        _tabs("Elections alone do not make a government representative; the"),
        _tabs("claims made on behalf of others must be contested."),
        "",
    ]),
    "\n".join([
        "CHAPTER 2",
        "",
        _tabs("Democracy depends on a continuous exchange between the"),
        _tabs("representatives and those who are represented."),
        "",
        "— 49 —",
        "",
    ]),
]

DEUTSCH = [
    "KAPITEL 1\n\nDer Repräsentant ist nicht bloß ein Delegierter der Wähler, wie Pitkin in ihrer Studie "
    "betonte, dass die Abgeordneten ihr Urteil nicht bloß weitergeben.\n\nEin zweiter Absatz folgt hier.\n",
    "Repräsentation erfordert Distanz und Responsivität, damit das Volk das Handeln derer beurteilen kann, "
    "die in seinem Namen handeln.\n\nWahlen allein machen eine Regierung nicht repräsentativ.\n",
    "KAPITEL 2\n\nDemokratie hängt von einem ständigen Austausch zwischen Repräsentanten und Repräsentierten ab.\n",
]

KAPITEL_TEXT = (
    "# Erstes Kapitel\n\n"
    "Der Repräsentant ist nicht bloß ein Delegierter der Wähler, wie Pitkin in ihrer Studie betonte, "
    "dass die Abgeordneten ihr Urteil nicht bloß weitergeben.\n\n"
    "Ein zweiter Absatz folgt hier, mit gewöhnlichen Wörtern.\n"
)


def _json(pfad: Path, daten) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def baue_testwurzel(pfad: Path) -> Path:
    """Baut die Test-Bibliothek unter `pfad` (Wurzel) samt exportiertem Paket und gibt `pfad` zurueck."""
    import bundle                      # noqa: E402  (liegt in tools/speedreader_web)
    import export_korrektur            # noqa: E402

    root = Path(pfad)
    buch = root / "reader" / AUTOR / TITEL
    quelle = buch / "quelle"
    quelle.mkdir(parents=True, exist_ok=True)
    (quelle / "0001_erstes-kapitel.md").write_text(KAPITEL_TEXT, encoding="utf-8", newline="\n")
    _json(quelle / "_kapitel_index.json", [{"nr": 1, "titel": "Erstes Kapitel", "datei": "0001_erstes-kapitel.md"}])
    _json(buch / "meta.json", {"autor": AUTOR, "titel": TITEL, "quellsprache": "en"})
    _json(buch / "kapitel.json", [{"nr": 1, "titel": "Erstes Kapitel", "datei": "0001_erstes-kapitel.md"}])
    _json(buch / "notizen" / "tags.json", [{
        "datei": "0001_erstes-kapitel.md", "kapitel_nr": 1, "titel": "Erstes Kapitel", "woerter": 40,
        "zusammenfassung": "Das Kapitel unterscheidet Repräsentation von bloßer Delegation.",
        "these": ["Repräsentanten urteilen eigenständig."], "gegen": [], "kern": ["Repräsentation"],
        "def": [], "beleg": [],
    }])

    lektor_buch = root / "rohdaten" / "Lektor" / AUTOR / TITEL
    for i, (roh, de) in enumerate(zip(ROH, DEUTSCH)):
        (lektor_buch / "en").mkdir(parents=True, exist_ok=True)
        (lektor_buch / "de").mkdir(parents=True, exist_ok=True)
        (lektor_buch / "en" / f"chunk_{i:03d}.md").write_text(roh, encoding="utf-8", newline="\n")
        (lektor_buch / "de" / f"chunk_{i:03d}.md").write_text(de, encoding="utf-8", newline="\n")
    _json(lektor_buch / "meta.json", {"quellsprache": "en"})
    _json(lektor_buch / "kapitel.json", {"segmente": [
        {"kapitel": 1, "titel": "Erstes Kapitel", "chunk": 0, "position": 0},
        {"kapitel": 2, "titel": "Zweites Kapitel", "chunk": 2, "position": 0},
    ]})

    paket = root / "reader" / "export-epistopheles"
    export_korrektur.exportiere(root, paket / "korrektur", root / "rohdaten" / "Lektor", ebooks=False)
    bundle.kopiere_app(paket)
    return root


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Aufruf: python -m redaktion.testwurzel <Zielordner>")
    print(baue_testwurzel(Path(sys.argv[1])))
