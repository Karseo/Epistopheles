#!/usr/bin/env python3
"""PDF mit Zwei-Spalten-Layout → bereinigter Fließtext (Markdown).

Behebt drei Probleme degradierter PDFify-Konvertierungen gleichzeitig:
  (1) pypdf verliert die Leerzeichen zwischen Wörtern → hier PyMuPDF.
  (2) Der Text liegt in zwei Spalten vor; naive top-to-bottom-Extraktion
      verschränkt sie. Hier werden Zeilen per x-Koordinate getrennt und
      je Seite erst die linke, dann die rechte Spalte gelesen.
  (3) Ligaturen (ﬁ ﬂ …), PDFify-Trial-Wasserzeichen und Störzeichen
      (`|`-Balken, verstreute Satzzeichen) werden bereinigt.

Zusätzlich wird Silbentrennung an Zeilen-/Spalten-/Seitengrenzen
zusammengezogen („de- ren" → „deren"). Ergebnis: Fließtext mit
`## Seite N`-Markern je Seite — kompatibel zur pypdf-Fallback-Ausgabe
von ebook-translate.py, damit die nachgelagerte Kapitel-Zuordnung
(TOC-Seite → `## Seite N`) weiter funktioniert.

Aufruf:
    python pdf-zweispaltig-zu-text.py "<input.pdf>" -o "<output.txt>"
"""

import argparse
import re
import statistics
import sys

import pymupdf  # fitz


LIGATUREN = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "‐": "-",   # hyphen
    "‑": "-",   # non-breaking hyphen
}

# Zeilen, die nach dem Trimmen nur aus diesen Zeichen bestehen → Stör-Müll
STOER_ZEILEN = re.compile(r"^[\|\;\.\,\(\)\{\}\[\]\'\"\\\-\–\—\:\!\*\>\+#\$%&\/\^\~\_\@\=\?]+$")
# Führende Störzeichen am Zeilenanfang (PDFify-Dekorationsbalken)
STOER_ANFANG = re.compile(r"^[\|\;\.\,\'\:\!\)\}\]\>\*#\$%&]+(?=\s*\S)")
# Trailing einzelnes Hochkomma (Layout-Artefakt)
STOER_ENDE = re.compile(r"[\'\`]+$")
# Sehr kurze Störzeilen: Seitenzahlen, Einzelbuchstaben, Zeichen-Müll
# (echte Fließtext-Zeilen sind deutlich länger; Kapitel-Titel ≥ 3 Zeichen)
STOER_KURZ = re.compile(r"^\d{1,3}$|^[^\wäöüÄÖÜß»«]{1,3}$|^[A-Za-z]{1}$|^\d{0,2}[#\$%&{}\|\;\:\!]{1,3}$")


def normiere(text: str) -> str:
    for alt, neu in LIGATUREN.items():
        text = text.replace(alt, neu)
    return text


def linien_extrahieren(page) -> list[tuple[float, float, str]]:
    """(x0, y0, text) je Textzeile."""
    zeilen = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line["spans"]).strip()
            if text:
                zeilen.append((line["bbox"][0], line["bbox"][1], text))
    return zeilen


def globale_spaltengrenze(doc) -> float:
    """Global die x-Grenze zwischen linker und rechter Spalte bestimmen.

    Layout dieser PDFify-Konvertierung (empirisch): linke Spalte (Fließtext
    + eingerückte Zitate) endet bei x≈280, rechte Spalte beginnt bei x≈298;
    dazwischen liegt die Dekorationsspalte aus `|`-Balken/Seitenzahlen. Die
    Grenze liegt also stabil bei ≈287. Die Auto-Erkennung sucht die tiefste
    Dichtelücke in x=240..340 und klemmt das Ergebnis auf [282, 293].
    """
    bins = [0] * 60  # je 10 pt, x in 0..600
    for page in doc:
        for x0, _, _ in linien_extrahieren(page):
            if 0 <= x0 < 600:
                bins[min(59, int(x0 / 10))] += 1
    lo, hi = 24, 34  # Bin 24..34 → x=240..340
    best_bin = 29
    best_count = float("inf")
    for i in range(lo, hi):
        if bins[i] < best_count:
            best_count = bins[i]
            best_bin = i
    schwellen_kandidat = best_bin * 10 + 5
    if 282.0 <= schwellen_kandidat <= 293.0:
        return schwellen_kandidat
    return 287.0


def seite_zu_zeilen(page, schwelle: float, seite_nr: int) -> list[str]:
    """Zeilen einer Seite in korrekter Lesereihenfolge (li. Spalte, dann re.)."""
    zeilen = linien_extrahieren(page)
    links = [z for z in zeilen if z[0] < schwelle]
    rechts = [z for z in zeilen if z[0] >= schwelle]
    links.sort(key=lambda z: z[1])
    rechts.sort(key=lambda z: z[1])
    return [f"## Seite {seite_nr}"] + [t for _, _, t in links] + [t for _, _, t in rechts]


def bereinige_zeile(text: str) -> str | None:
    # Seiten-Marker unverändert durchreichen (darf nicht als Störzeichen
    # zerlegt werden — das `#` würde sonst gestrippt).
    if text.startswith("## Seite "):
        return text
    t = normiere(text).strip()
    if not t:
        return None
    # reine Störzeilen / Wasserzeichen / Seitenzahlen-Duo
    if STOER_ZEILEN.match(t):
        return None
    if re.match(r"^https?://", t):
        return None
    if re.fullmatch(r"\d+\s*/\s*\d+", t):  # Seitenzahl-Paar „12 / 13"
        return None
    if STOER_KURZ.match(t):
        return None
    t = STOER_ANFANG.sub("", t).strip()
    t = STOER_ENDE.sub("", t).strip()
    # Nach dem Trimmen erneut kurz prüfen (z.B. „| 4" → „4")
    if not t or STOER_KURZ.match(t) or STOER_ZEILEN.match(t):
        return None
    return t


def silbentrennung_aufloesen(zeilen: list[str]) -> list[str]:
    """Zieht Zeilenende-Hyphenierung zusammen („de-" + „ren" → „deren")."""
    out: list[str] = []
    i = 0
    while i < len(zeilen):
        line = zeilen[i]
        nxt = zeilen[i + 1] if i + 1 < len(zeilen) else ""
        if line.endswith("-") and nxt and nxt[0].islower():
            out.append(line[:-1] + nxt)
            i += 2
            continue
        out.append(line)
        i += 1
    return out


def zu_absaetzen(zeilen: list[str]) -> str:
    """Zeilen (mit `## Seite N`-Markern) zu Markdown-Absätzen fügen.

    `## Seite N` bleibt als Überschrift erhalten; alles andere wird zu
    Fließtext-Absätzen. Absatzgrenzen lassen sich ohne y-Information nicht
    zuverlässig bestimmen (Spalten-/Seitengrenzen liegen mitten im Absatz),
    deshalb wird konservativ nur an echten Strukturmarkern umgebrochen.
    """
    absaetze: list[str] = []
    aktuell: list[str] = []
    for line in zeilen:
        if line.startswith("## Seite "):
            if aktuell:
                absaetze.append(" ".join(aktuell))
                aktuell = []
            absaetze.append(line)
        else:
            aktuell.append(line)
    if aktuell:
        absaetze.append(" ".join(aktuell))
    # Doppelte Leerzeilen vermeiden, Absätze durch Leerzeile trennen
    return "\n\n".join(a for a in absaetze if a.strip())


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("input", help="Eingabe-PDF")
    ap.add_argument("-o", "--output", required=True, help="Ausgabe-Textdatei")
    args = ap.parse_args()

    doc = pymupdf.open(args.input)
    n_seiten = doc.page_count
    schwelle = globale_spaltengrenze(doc)

    alle_zeilen: list[str] = []
    for i in range(n_seiten):
        zeilen = seite_zu_zeilen(doc[i], schwelle, i + 1)
        bereinigt = [z for z in (bereinige_zeile(t) for t in zeilen) if z]
        alle_zeilen.extend(bereinigt)
    doc.close()

    alle_zeilen = silbentrennung_aufloesen(alle_zeilen)
    volltext = zu_absaetzen(alle_zeilen)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(volltext)

    print(f"[OK] Schwelle x={schwelle:.0f} | {n_seiten} Seiten → {args.output} "
          f"({len(volltext):,} Zeichen)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
