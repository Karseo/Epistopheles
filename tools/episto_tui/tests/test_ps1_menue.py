"""Statische Pruefung des alten PowerShell-Menues tools\\episto-tui.ps1 (laeuft ohne
PowerShell): Es darf sich nicht auf das aktuelle Verzeichnis verlassen und keine
Vektorisierung ueber die ganze Bibliothek anstossen."""
import re
from pathlib import Path
import pytest

PS1 = Path(__file__).resolve().parents[2] / "episto-tui.ps1"
_AUFRUF = re.compile(r"^\s*&\s+(.*)$")


def aufrufe(text: str) -> list[str]:
    """Alle Zeilen der Form "& <Skript> ..." (Kommentare ausgenommen)."""
    ergebnis = []
    for zeile in text.splitlines():
        if zeile.lstrip().startswith("#"):
            continue
        treffer = _AUFRUF.match(zeile)
        if treffer:
            ergebnis.append(treffer.group(1))
    return ergebnis


def probleme(text: str) -> list[str]:
    gefunden = []
    for a in aufrufe(text):
        if re.match(r"""["']?\.\\""", a):
            gefunden.append(f"relativer Aufruf (haengt vom aktuellen Verzeichnis ab): {a}")
        if "ingest.ps1" in a and "-Buch" not in a and "-Reset" not in a:
            gefunden.append(f"ingest ohne -Buch haengt die ganze Bibliothek erneut an: {a}")
    return gefunden


def test_pruefung_erkennt_die_alten_fehler():
    alt = '''
                & .\\tools\\ingest.ps1
        & .\\tools\\taggen.ps1 -Buch $book.Pfad
    # & .\\tools\\ingest.ps1 steht nur im Kommentar
'''
    assert len(probleme(alt)) == 3          # zwei relative Aufrufe + ingest ohne -Buch
    assert probleme('& (Join-Path $ToolsDir "ingest.ps1") -Buch $buchPfad') == []
    assert probleme('& (Join-Path $ToolsDir "taggen.ps1") -Buch $x') == []


@pytest.mark.skipif(not PS1.exists(), reason="episto-tui.ps1 liegt nicht im Repo")
def test_menue_skript_hat_keine_cwd_abhaengigen_aufrufe_und_kein_globales_ingest():
    text = PS1.read_text(encoding="utf-8-sig")
    assert "$ToolsDir = $PSScriptRoot" in text
    assert probleme(text) == []


@pytest.mark.skipif(not PS1.exists(), reason="episto-tui.ps1 liegt nicht im Repo")
def test_menue_hat_einen_punkt_zum_lesen():
    text = PS1.read_text(encoding="utf-8-sig")
    assert re.search(r'Write-Host "9\. Read', text)                 # Eintrag im Menue
    assert '"9" { Run-Reader }' in text                             # und in der Auswahl
    assert "-m episto_tui" in text and "$ToolsDir" in text         # startet die TUI aus tools\
    assert "(0-9)" in text                                          # Eingabeaufforderung stimmt
