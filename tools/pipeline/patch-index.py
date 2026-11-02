import sys, io

path = sys.argv[1]
text = io.open(path, encoding="utf-8").read()

def replace_once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"[FEHLER] Anker '{label}' {n}x gefunden statt 1x")
    return text.replace(old, new, 1)

# 1) Zeile in der Uebersichtstabelle oben
old1 = '| (vorab) | `detect-chapters.py` | rekonstruiert die Kapitelstruktur → `kapitel.json` |\n'
new1 = old1 + '| (vorab) | `check-metadata.py` | prüft Chunks auf InDesign-/Pandoc-Metadatenreste, schlägt Umgang vor |\n'
text = replace_once(text, old1, new1, "Uebersichtstabelle")

# 2) Reihenfolge-Absatz + Code-Block vor 2a erweitern
old2 = '''```powershell
python ebook-build.py "<Titel>" --check      # Stand prüfen
python fix-chunks.py "<Autor>\\<Titel>"       # Defekte finden
```

### 2a. Tags vorschlagen (`suggest-tags.py`)'''

new2 = '''```powershell
python ebook-build.py "<Titel>" --check      # Stand prüfen
python fix-chunks.py "<Autor>\\<Titel>"       # Defekte finden
python check-metadata.py "<Autor>\\<Titel>"   # Metadatenreste im Rohtext pruefen
```

### Metadaten prüfen (`check-metadata.py`)

```powershell
python check-metadata.py                                    # alle Buecher, de+en
python check-metadata.py "<Autor>\\<Titel>"
python check-metadata.py "<Autor>\\<Titel>" --sprache de
python check-metadata.py "<Autor>\\<Titel>" --beispiele 5
python check-metadata.py "<Autor>\\<Titel>" --normalize-footnotes
```

InDesign-EPUBs hinterlassen in den Chunks Reste, die weder Fehler noch Fließtext
sind — ärgerlich werden sie erst, wenn ausgerechnet der zitierte Beleg mittendrin
steckt. `collect-tags.py` übernimmt den Absatz wörtlich ("der Absatz ist der
Beleg, keine Paraphrase"); eine solche Klammerkette macht daraus kein brauchbares
Zitat mehr. Beispiel aus `Parvini, Neema\\The Populist Delusion\\de\\chunk_003.md`:

```
[[[2](#02_-_The_Rulers_and_the_Ruled.xhtml_footnote-046){._idFootnoteLink
._idGenColorInherit}]{#02_-_The_Rulers_and_the_Ruled.xhtml_footnote-046-backlink}]
{.CharOverride-2}
```

`check-metadata.py` meldet je Buch zwei Kategorien und schlägt dazu den Umgang vor:

| Kategorie | Beispiel | Vorschlag |
|---|---|---|
| `fussnoten` | die Klammerkette oben | kein Fehler — `ebook-build.py` kürzt sie beim Bauen ohnehin zu `[^Kapitel-Nr]` (`--footnotes`/`--clean`). Stört aber jedes Zitat, solange nicht gebaut wurde. Fehlt `<lang>\\footnotes.md` noch, zuerst `extract-footnotes.py` laufen lassen; danach optional mit `--normalize-footnotes` direkt in den Chunks auf die kurze Form kürzen |
| `zeichenformat` | `[offensichtlich]{.CharOverride-1}`, `[Provoked]{.class_sdk}` | verlorene Zeichenauszeichnung der Quelle (meist kursiv, fett, Kapitälchen) oder ein Register-/Verweiselement — keine automatische Korrektur; an den Beispielen reicht meist ein Blick, ob Fließtext oder Apparat betroffen ist |

Reine Anker ohne sichtbaren Text (Kapitelmarken, Seitenzahlen, Calibre- und
Index-Anker) werden bewusst nicht gemeldet — sie sind der Grund, warum die
Chunks laut Konzept roh bleiben, und tauchen in einem zitierten Absatz ohnehin
nicht auf.

### 2a. Tags vorschlagen (`suggest-tags.py`)'''

text = replace_once(text, old2, new2, "Schritt-2-Einleitung")

# 3) Kompletter Ablauf: Schritt einfuegen und nachfolgende Nummern anpassen
old3 = '''# 2) Qualität sichern, bevor getaggt wird
python fix-chunks.py "Horton, Scott\\Provoked"

# 3) Tags vorschlagen (Lauf über Nacht)
python suggest-tags.py "Horton, Scott\\Provoked" --in-place --resume

# 4) Korrekturlesen: Tags bestätigen, ==Hervorhebungen== setzen

# 5) Erschließung einsammeln
python collect-tags.py "Horton, Scott\\Provoked" --zusammenfassung
python collect-marks.py "Horton, Scott\\Provoked" --suggest

# 6) Gesamttexte  →  Outbox\\Horton, Scott - Provoked_{de,en}.md
python ebook-build.py "Provoked"

# 7) optional: Obsidian-Vault (aus der deutschen Fassung)'''

new3 = '''# 2) Qualität sichern, bevor getaggt wird
python fix-chunks.py "Horton, Scott\\Provoked"

# 3) Metadatenreste im Rohtext pruefen
python check-metadata.py "Horton, Scott\\Provoked"

# 4) Tags vorschlagen (Lauf über Nacht)
python suggest-tags.py "Horton, Scott\\Provoked" --in-place --resume

# 5) Korrekturlesen: Tags bestätigen, ==Hervorhebungen== setzen

# 6) Erschließung einsammeln
python collect-tags.py "Horton, Scott\\Provoked" --zusammenfassung
python collect-marks.py "Horton, Scott\\Provoked" --suggest

# 7) Gesamttexte  →  Outbox\\Horton, Scott - Provoked_{de,en}.md
python ebook-build.py "Provoked"

# 8) optional: Obsidian-Vault (aus der deutschen Fassung)'''

text = replace_once(text, old3, new3, "Kompletter-Ablauf")

io.open(path, "w", encoding="utf-8", newline="\n").write(text)
print("OK")