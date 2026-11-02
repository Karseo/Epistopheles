#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lektor-zu-episto.py — Ueberfuehrt ein per eBooks-Toolchain (Lektor-Schema)
uebersetztes und strukturiertes Buch in das Episto-Schema (reader/<Autor>/<Titel>/).

Teil der Zusammenfuehrung von eBooks (Werkstatt) und !Episto (Bibliothek),
siehe dok/KONZEPT_ZUSAMMENFUEHRUNG.md. Dies ist die bislang fehlende Bruecke
zwischen beiden Schemata: eBooks liefert feste 8000-Zeichen-Chunks je Sprache,
Episto braucht ein File je echtem Kapitel (quelle/NNNN_slug.md) plus eine
hierarchische Gliederung.

Voraussetzung im Lektor-Buchordner (<Lektor>/<Autor>/<Titel>/):
  - <arbeit>/chunk_NNN.md  (Standard: de/), aus ebook-translate.py
  - <referenz>/chunk_NNN.md (Standard: en/), Originalsprache als Rueckfallebene
  - kapitel.json mit befuellter "segmente"-Liste (bevorzugt) oder "kapitel"-
    Liste (Fallback, keine Vorspann-Positionen), aus detect-chapters.py bzw.
    suggest-structure.py

Das Skript ist rein mechanisch (kein LLM-Aufruf, keine Netzwerkabhaengigkeit).
Es:
  1. schneidet den durchgehenden Arbeitssprachen-Text an den erkannten
     Kapitelgrenzen in Einzeldateien quelle/NNNN_slug.md (Episto-Konvention)
  2. bereinigt dabei bekannte Pandoc-/InDesign-Konvertierungsreste
     (Logik uebernommen aus ebook-build.py: normalize_footnotes/clean_markdown)
  3. schreibt quelle/_kapitel_index.json + kapitel.json (gliederung/zuordnung)
     im Episto-Format (flache Gliederung; Vorspann/Anhang werden erkannt)
  4. kopiert die Referenzsprache unveraendert nach <referenz>/ im Zielordner
  5. uebertraegt meta.json (+ episto-Block) und schreibt .progress.json
  6. sichert vorhandene chunk-basierte Vorarbeit (Tags/Straenge aus
     suggest-tags.py/collect-tags.py) nach notizen/_chunkweise-vorarbeit/ —
     als Rohstoff fuer die spaetere Taxonomie-Kuration, wird NICHT geloescht
     und NICHT automatisch weiterverarbeitet.

Was dieses Skript NICHT tut (naechste Schritte, brauchen Ollama/PowerShell
auf dem Windows-Rechner):
  - notizen/tags.json kapitelweise erzeugen        -> tools\\taggen.ps1
  - notizen/strang_taxonomie.json kuratieren       -> manuell/LLM-gestuetzt
  - notizen/straenge/ aggregieren                  -> tools\\straenge.ps1
  - Qdrant-Ingest                                  -> ingest.ps1

Aufruf:
  python lektor-zu-episto.py --buch "Parvini, Neema/The Populist Delusion"
  python lektor-zu-episto.py --buch "..." --dry-run
  python lektor-zu-episto.py --buch "..." --lektor "D:\\...\\!Episto\\rohdaten\\Lektor" --episto "D:\\...\\!Episto\\reader"
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from redaktion import schutz  # noqa: E402

DEFAULT_LEKTOR = r"D:\Workspace\!Episto\rohdaten\Lektor"
DEFAULT_EPISTO = r"D:\Workspace\!Episto\reader"

UMLAUT_MAP = {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def slugify(text: str, fallback: str) -> str:
    """Wie die vorhandenen Episto-Werke benannt sind (siehe Kant-Ordner):
    kleingeschrieben, Umlaute transliteriert, nicht-alphanumerisch -> '-'."""
    if not text or not text.strip():
        return fallback
    t = text.strip()
    for k, v in UMLAUT_MAP.items():
        t = t.replace(k, v)
    t = t.lower()
    t = re.sub(r"[^a-z0-9]+", "-", t)
    t = t.strip("-")
    return t[:80] if t else fallback


def eindeutig(slug: str, vergeben: set) -> str:
    if slug not in vergeben:
        vergeben.add(slug)
        return slug
    i = 2
    while f"{slug}-{i}" in vergeben:
        i += 1
    vergeben.add(f"{slug}-{i}")
    return f"{slug}-{i}"


# ── Bereinigung — uebernommen aus ebook-build.py (normalize_footnotes/clean_markdown) ──
# Gleiche Regeln, damit Quelltext (Episto) und Gesamttext (Outbox) konsistent bereinigt
# sind. Siehe dort fuer die ausfuehrliche Begruendung der einzelnen Muster.

def normalize_footnotes(text: str) -> str:
    def bezeichner(ziel: str) -> str:
        m_kap = re.match(r'(\d+)', ziel)
        m_fn = re.search(r'footnote-(\d+)', ziel)
        nr = m_fn.group(1) if m_fn else "0"
        return f"{m_kap.group(1)}-{nr}" if m_kap else nr

    TEXT = r'\[[^\]]{0,40}?\]'

    # '#' vor dem Anker ist nicht in jedem EPUB vorhanden (variiert je nach
    # Pandoc-/InDesign-Version des Quell-EPUBs) — daher optional gemacht.
    text = re.sub(
        r'\[?\[' + TEXT + r'\(#?([^)]*?footnote-\d+)\)\{[^}]*\}\]\{#?[^}]*\}\]?'
        r'(?:\s*\{[^}]*\})?',
        lambda m: f"[^{bezeichner(m.group(1))}]", text)

    text = re.sub(
        TEXT + r'\(#?([^)]*?footnote-\d+)\)(?:\{[^}]*\})?',
        lambda m: f"[^{bezeichner(m.group(1))}]", text)


    # Zweite, unabhaengige Fussnoten-Konvention (erlebt bei Kahneman/Schnelles
    # Denken): hochgestellte Referenzen ohne 'footnote-N' im Linkziel, dafuer
    # mit variabler Klammer-/Klassentiefe, das Linkziel zeigt stattdessen auf
    # eine 'index_split_NNN.html_filepos######'-Anker-Position. Kennzeichen:
    # von '^' umschlossen (Hochstellung), Bezeichner ist eine Ziffer oder ein
    # Buchstabe (a, b, c... bei mehreren Fussnoten zur selben Stelle).
    text = re.sub(
        r'\^\[+([0-9a-zA-Z]+)(?:\]\{\.[\w-]+\})*\]\(#[^)]*?filepos\d+\)\]\{\.[\w-]+\}\^',
        lambda m: f"[^{m.group(1)}]", text)
    # Vereinzelt bleibt dabei ein Fragment ohne Bezeichner uebrig (Trennung
    # durch Chunk-/Absatzgrenze im Quell-EPUB) - inhaltsleer, nur entfernen.
    text = re.sub(r'\^\[\]\{\.small\}\^', '', text)

    # Verso-EPUB (z.B. Mouffe "The Return of the Political"): manche Fussnoten
    # haben die Nummer in einem {N}-Span statt direkt: [{8}^](#17_Notes.xhtml_
    # ch07fn8) -> [^8^](#…). Nur die {N}-Variante anfassen, die uebrige Konven-
    # tion [N^](#…) ist in den meisten Kapiteln bereits sauber.
    text = re.sub(r'\[\{(\d+)\}\^\](\(#[^)]*\))', r'[^\1^\2]', text)

    # Princeton-EPUB (Stasavage "Decline and Rise"): Endnoten-Marker — das
    # sichtbare [N]/[1-N] und ^ bleiben erhalten, nur der Anker wird entfernt:
    # {#23_ch11.xhtml_chapter11_62 role="doc-noteref"}.
    text = re.sub(r'\{#[^}]*role="doc-noteref"\}', '', text)

    # Suhrkamp-EPUB (Mouffe "Eine Grüne demokratische Revolution"): Inline-
    # Endnoten-Marker der Form
    #   ^[[[\[N\](nbsp)](#…_fn_FnN)]{#…_fna_FnN .note-anchor}]{.Marker}^
    # → [^N]. Die Nummer steckt im escapeten \[N\], danach ein (nbsp); der
    # Link (#…_fn_FnN) und der Anker (#…_fna_FnN .note-anchor) sind reine
    # Konvertierungs-Hülsen ohne Textwert. Das {.Marker} ist ein Formatierungs-
    # Span der gleichen Herkunft.
    NBSP = " "
    text = re.sub(
        r"\^\[\[\[\\\[(\d+)\\\]" + f"[{NBSP} ]?" + r"\]\(#[^)]*?fn_Fn\d+\)\]\{#[^}]*?fna_Fn\d+\s+\.note-anchor\}\]\{\.Marker\}\^",
        r"[^\1]", text)

    return text


def strip_seitenmarken(text: str) -> str:
    """PDF-Konvertierungs-Artefakt (im Gegensatz zu den EPUB/Pandoc-Resten
    oben): manche Quellen (z.B. Bourdieu/The State Nobility, gescanntes PDF)
    fuegen pro Buchseite eine Marke '## Seite N' ein - manchmal isoliert auf
    eigener Zeile, manchmal ohne Leerzeichen direkt an die folgende
    Ueberschrift geklebt ('## Seite 29TEIL I'). Rein mechanisches
    Seiten-Zaehlwerk der Konvertierung, kein Bestandteil des Buchtexts."""
    text = re.sub(r'#{1,6}\s*Seite\s+\d+\s*', '', text)
    # aya-expanse rendert manche pypdf-Seitenmarker als Fett statt als Ueberschrift:
    # **SEITE 150** statt ## Seite 150 (beobachtet bei Stasavage "States of Credit").
    text = re.sub(r'\*\*\s*SEITE\s+\d+\s*\*\*', '', text)
    return text

def clean_markdown(text: str) -> str:
    text = strip_seitenmarken(text)
    text = normalize_footnotes(text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)\{\.calibre\}', r'\1', text)
    text = re.sub(r'\[\]\\?\[\\?\[(\d+)\]\\?\]\\?\]\(#[^)]*\)', r'[^\1]', text)
    text = re.sub(r'\[\]\[\[(\d+)\]\]\(#[^)]*\)', r'[^\1]', text)
    text = re.sub(r'(?m)^\s*\[\]\s*$', '', text)
    text = re.sub(r'\[\]\{#[^}]*\}', '', text)
    # EPUB-Seitenzahl-Marken [N]{.seite} (Suhrkamp & aehnliche): komplett
    # entfernen, NICHT zu "N" reduzieren — sonst klebt die Seitenzahl mitten
    # im Wort (z.B. "Klassenunterschei[192]dungen" -> "…192dungen"). Das
    # zugehoerige []{#…_page_N} hat die Zeile darueber bereits entfernt.
    text = re.sub(r'\[\d+\]\{\.seite\}', '', text)
    # EPUB-Seitenzahl-Marken mit doc-pagebreak-Anker (Suhrkamp-Neuauflagen,
    # z.B. Mouffe "Eine Grüne demokratische Revolution"): [N]{#…_page_N
    # .pagenum .pagebreak role="doc-pagebreak" title="N"}. Gleicher Effekt wie
    # die .seite-Variante — die _KLASSEN_SPAN-Schleife weiter unten wuerde sie
    # sonst zu "N" reduzieren und die nackte Ziffer klebt dann im Text (z.B.
    # "Mitte-rechts- 10und", "Liquefied 96natural gas") bzw. vor dem Kapitel-
    # Titel ("# 332. Politik…" statt "# 2. Politik…"). Deshalb hier, VOR der
    # Klassen-Span-Schleife, komplett entfernen.
    text = re.sub(r'\[\d+\]\{#[^}]*_page_\d+[^}]*\}', '', text)
    text = re.sub(r'(?m)^:::+.*$', '', text)
    text = re.sub(r'(?m)^(#{1,6}\s+.*?)\s*\{[^}]*\}\s*$', r'\1', text)
    text = re.sub(r'(?<=\))\{[^}]*\}', '', text)
    text = re.sub(r'<svg\b.*?</svg>', '', text, flags=re.S | re.I)
    text = re.sub(r'`<image\b[^`]*`\{=html\}', '', text)
    # Pandoc-Roh-HTML generisch entfernen, z.B. `<wbr>`{=html}`</wbr>`{=html} in
    # URLs der Bibliographie (Stasavage "Decline and Rise") — reine Umbruchmarken.
    text = re.sub(r'`[^`]*`\{=html\}', '', text)
    # Princeton-EPUB (Stasavage): verbliebene inhaltsleere Anker — Bibliographie-
    # Kopf (#…_bib .BMH) und Index-Eintraege (#28_index.xhtml_indN).
    text = re.sub(r'\{#[^}]*\.BMH\}', '', text)
    text = re.sub(r'\{#[^}]*(?:index|register)\.xhtml[^}]*\}', '', text, flags=re.I)
    # Fussnoten-URLs, die Pandoc/InDesign zusaetzlich in geschweifte Klammern
    # setzt: {[http://…](http://…)} -> [http://…](http://…)  (Suhrkamp-EPUBs,
    # z.B. Mouffe "Agonistik": 8 Vorkommen). Nur einzeilige Markdown-Links.
    text = re.sub(r'\{(\[[^\]\n]*\]\([^)\n]*\))\}', r'\1', text)
    # generischer Rest, den ebook-build.py an anderer Stelle (--clean, zusammen mit
    # check-metadata.py) behandelt: [Text]{.irgendeine-Klasse} -> Text
    # Mehrfach verschachtelte Spans (z.B. '[[[Titel]{.bold}]{.italic}]{.calibre1}',
    # haeufig bei Kapitelueberschriften) brauchen mehrere Durchlaeufe: ein
    # einzelner re.sub-Durchgang loest pro Aufruf immer nur die jeweils
    # innerste Ebene auf, die aeusseren Klammern blieben sonst als Rest stehen.
    _KLASSEN_SPAN = re.compile(r'\[([^\[\]]{1,10000}?)\]\{[^}{}]*\}')
    for _ in range(6):
        neu = _KLASSEN_SPAN.sub(r'\1', text)
        if neu == text:
            break
        text = neu
    # Endnoten-Spans, die einen Markdown-Link umschliessen (Campus-EPUB, z.B.
    # Buchter "Wer wird Milliardär"): [[url](url)]{.Hyperlink} plus aeussere
    # {.fn-t ...}-Schale -> [url](url). _KLASSEN_SPAN kann diese nicht
    # entschachteln, weil der Inhalt selbst eckige Klammern traegt.
    _LINK_SPAN = re.compile(r'\[(\[[^\]]*\]\([^)]*\)[^\]]*)\]\{[^}]*\}')
    for _ in range(4):
        neu = _LINK_SPAN.sub(r'\1', text)
        if neu == text:
            break
        text = neu
    # Endnoten mit mehreren Links oder Freitext+Link im Inhalt (gleiche
    # Campus-Quelle): [<inhalt>]{.fn-t...}/{.Hyperlink} -> <inhalt>, wobei
    # <inhalt> beliebig viele [url](url)-Links und Freitext enthalten darf.
    # Zusätzlich escaped eckige Klammern \[…\] erlauben (Suhrkamp-EPUB, z.B.
    # Mouffe "Eine Grüne demokratische Revolution": Jahreszahlen "\[1985\]" im
    # Bibliografie-Text der Endnoten).
    _NOTE_SPAN = re.compile(r'\[((?:[^\[\]]|\\\[|\\\]|\[[^\[\]]*\]\([^)]*\))+?)\]\{\.(?:fn-t|Hyperlink)[^}]*\}')
    for _ in range(4):
        neu = _NOTE_SPAN.sub(r'\1', text)
        if neu == text:
            break
        text = neu
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'(?<=\S)\n(#{1,6}\s)', r'\n\n\1', text)
    # Non-breaking space in Ueberschrift-Zeilen normalisieren (Suhrkamp setzt es
    # zwischen Kapitelnummer und Titel: "# 1.\xa0Eine…" -> "# 1. Eine…"). Nur
    # Ueberschriften — Fliesstext-/Fussnoten-NBSP bleibt wie bei Agonistik
    # unangetastet (dort seit jeher toleriert).
    text = "\n".join(
        line.replace(" ", " ") if re.match(r"^#{1,6}\s", line) else line
        for line in text.split("\n")
    )
    return text.strip()


def restartefakte(text: str) -> int:
    """Grobe Kennzahl fuer verbliebene, nicht erkannte Konvertierungsreste —
    zur Selbstpruefung nach der Bereinigung (siehe check-metadata.py)."""
    return len(re.findall(r'\{[^}]*\}|_idFootnote|CharOverride', text))


# ── JSON I/O ─────────────────────────────────────────────────────────────────

def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def save_json(p: Path, data, dry_run: bool):
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if dry_run:
        print(f"  [dry-run] schriebe {p}  ({len(text)} Zeichen)")
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def save_text(p: Path, text: str, dry_run: bool):
    if dry_run:
        print(f"  [dry-run] schriebe {p}  ({len(text)} Zeichen)")
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


# ── Chunks lesen & an Positionen schneiden ──────────────────────────────────

def read_chunks(lang_dir: Path):
    files = sorted(
        p for p in lang_dir.glob("chunk_*.md")
        if re.fullmatch(r"chunk_\d+\.md", p.name)
    )
    return [f.read_text(encoding="utf-8") for f in files], [f.name for f in files]


def slice_text(chunks: list, start: tuple, end: tuple | None) -> str:
    """start/end = (chunk_idx, position). end=None -> bis Textende.
    Chunks wurden von ebook-translate.py an Absatzgrenzen geschnitten, daher
    ist '\\n\\n' die korrekte Klammer beim Wiederzusammenfuegen."""
    c0, p0 = start
    if end is None:
        c1, p1 = len(chunks) - 1, len(chunks[-1]) if chunks else 0
    else:
        c1, p1 = end
    if c0 == c1:
        return chunks[c0][p0:p1]
    parts = [chunks[c0][p0:]]
    parts.extend(chunks[c0 + 1:c1])
    parts.append(chunks[c1][:p1])
    return "\n\n".join(parts)


def segment_liste(kap: dict) -> list:
    """Bevorzugt 'segmente' (vollstaendig inkl. Vorspann-Positionen, von
    detect-chapters.py erzeugt); Fallback 'kapitel' (aeltere/gecroppte Faelle,
    z.B. wenn die Struktur nur grob per LLM vorlag)."""
    segs = kap.get("segmente") or kap.get("kapitel") or []
    segs = [s for s in segs if s.get("titel")]
    segs = sorted(segs, key=lambda s: (int(s.get("chunk", 0)), int(s.get("position", 0))))
    return segs


# ── Gliederung bauen ─────────────────────────────────────────────────────────

def baue_struktur(segs: list):
    """Liefert (zuordnung, gliederung) im Episto-Format.
    Fuehrende vorspann=True Segmente -> Knoten 'Vorspann'.
    Nachlaufende vorspann=True Segmente (nach dem letzten Sachkapitel) ->
    Knoten 'Anhang'. Dazwischen: flache Kapitelliste (Hierarchie ist damit ein
    erster, automatischer Entwurf — Verfeinerung ist Aufgabe der Tagging-Phase,
    nicht dieses Skripts)."""
    vergeben = set()
    slugs = []
    for s in segs:
        nr = str(s.get("nr") or "")
        fallback = f"kapitel-{len(slugs) + 1}"
        slugs.append(eindeutig(slugify(s.get("titel", ""), fallback), vergeben))

    n = len(segs)
    i_first_real = next((i for i, s in enumerate(segs) if not s.get("vorspann")), 0)
    i_last_real = n - 1 - next(
        (i for i, s in enumerate(reversed(segs)) if not s.get("vorspann")), 0
    )

    zuordnung = []
    for i, s in enumerate(segs):
        zuordnung.append({
            "nr": i + 1,
            "datei": None,  # wird nach dem Schreiben der Dateien ergaenzt
            "abschnitt": slugs[i],
            "pfad": [],  # wird unten befuellt
        })

    gliederung = []
    vorspann_kinder = []
    anhang_kinder = []
    for i, s in enumerate(segs):
        knoten = {"id": slugs[i], "nr": str(s.get("nr") or ""), "titel": s.get("titel", ""), "kinder": []}
        if i < i_first_real:
            vorspann_kinder.append(knoten)
            zuordnung[i]["pfad"] = ["Vorspann", s.get("titel", "")]
        elif i > i_last_real:
            anhang_kinder.append(knoten)
            zuordnung[i]["pfad"] = ["Anhang", s.get("titel", "")]
        else:
            gliederung.append(knoten)
            zuordnung[i]["pfad"] = [s.get("titel", "")]

    if vorspann_kinder:
        gliederung.insert(0, {"id": "vorspann", "nr": "", "titel": "Vorspann", "kinder": vorspann_kinder})
    if anhang_kinder:
        gliederung.append({"id": "anhang", "nr": "", "titel": "Anhang", "kinder": anhang_kinder})

    return zuordnung, gliederung, slugs


# ── Hauptablauf ──────────────────────────────────────────────────────────────

def verarbeite(buch_rel: str, lektor_root: Path, episto_root: Path,
                sprache_arbeit: str, sprache_referenz: str, dry_run: bool,
                ueberschreiben: bool = False):
    quelle_buch = lektor_root / buch_rel
    if not quelle_buch.is_dir():
        raise SystemExit(f"[FEHLER] nicht gefunden: {quelle_buch}")

    kap_path = quelle_buch / "kapitel.json"
    if not kap_path.exists():
        raise SystemExit(
            f"[FEHLER] {kap_path} fehlt — erst detect-chapters.py "
            f"(ggf. suggest-structure.py) laufen lassen."
        )
    kap = load_json(kap_path)
    segs = segment_liste(kap)
    if not segs:
        raise SystemExit("[FEHLER] kapitel.json enthaelt keine benannten Segmente.")

    arbeit_dir = quelle_buch / sprache_arbeit
    referenz_dir = quelle_buch / sprache_referenz
    if not arbeit_dir.is_dir():
        raise SystemExit(f"[FEHLER] Arbeitssprache-Ordner fehlt: {arbeit_dir}")

    chunks, chunk_names = read_chunks(arbeit_dir)
    print(f"Buch: {buch_rel}")
    print(f"  Segmente: {len(segs)}  |  Chunks ({sprache_arbeit}): {len(chunks)}")

    max_chunk = max(int(s.get("chunk", 0)) for s in segs)
    if max_chunk >= len(chunks):
        raise SystemExit(
            f"[FEHLER] kapitel.json verweist auf Chunk {max_chunk}, "
            f"aber nur {len(chunks)} Chunks vorhanden in {arbeit_dir} "
            f"(evtl. falsche --sprache-arbeit, oder Uebersetzung unvollstaendig)."
        )

    zuordnung, gliederung, slugs = baue_struktur(segs)

    # Zielordner
    autor_titel = Path(buch_rel)
    ziel_buch = episto_root / autor_titel
    ziel_quelle = ziel_buch / "quelle"
    fehler = schutz.pruefe_ueberschreiben(ziel_quelle, ueberschreiben, dry_run)
    if fehler:
        raise SystemExit(fehler)
    # Referenzsprache (Rohchunks) gehoert nicht zu den fertigen Reader-Daten: rohdaten/<sprache>-chunks/<Autor>/<Titel>/
    ziel_referenz = episto_root.parent / "rohdaten" / f"{sprache_referenz}-chunks" / autor_titel

    index_eintraege = []
    reste_gesamt = 0
    for i, s in enumerate(segs):
        start = (int(s["chunk"]), int(s["position"]))
        end = None
        if i + 1 < len(segs):
            end = (int(segs[i + 1]["chunk"]), int(segs[i + 1]["position"]))
        roh = slice_text(chunks, start, end)
        text = clean_markdown(roh)
        reste_gesamt += restartefakte(text)

        dateiname = f"{i + 1:04d}_{slugs[i]}.md"
        zuordnung[i]["datei"] = dateiname
        index_eintraege.append({"nr": i + 1, "titel": s.get("titel", ""), "datei": dateiname})

        save_text(ziel_quelle / dateiname, text, dry_run)

    save_json(ziel_quelle / "_kapitel_index.json", index_eintraege, dry_run)

    meta_alt = {}
    meta_path = quelle_buch / "meta.json"
    if meta_path.exists():
        meta_alt = load_json(meta_path)

    kapitel_json_neu = {
        "werk": meta_alt.get("titel", ""),
        "quelle": kap.get("quelle", ""),
        "gliederung": gliederung,
        "zuordnung": zuordnung,
    }
    save_json(ziel_buch / "kapitel.json", kapitel_json_neu, dry_run)

    meta_neu = dict(meta_alt)
    meta_neu.update({
        "quellsprache": meta_alt.get("quellsprache", ""),
        "sprache_arbeit": sprache_arbeit,
        "sprache_referenz": sprache_referenz,
        "quelle_kapitel": len(segs),
        "quelle_status": "uebernommen_aus_lektor",
        "lektor_pfad": str(quelle_buch),
        "episto": meta_alt.get("episto", {"typ": "", "kanon": "", "funktion": "", "anker_tags": []}),
        "migriert": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    save_json(ziel_buch / "meta.json", meta_neu, dry_run)

    progress = {
        "quelle_volltext": {"abgerufen": True, "kapitel": len(segs), "ordner": "quelle"},
        "gliederung": {
            "gemappt": True,
            "abschnitte": len(gliederung),
            "zugeordnete_kapitel": len(segs),
            "datei": "kapitel.json",
            "hinweis": "automatisch aus Lektor-Segmenten erzeugt, Hierarchie ungeprueft",
        },
        "analysen": {
            "tagging": False, "tagging_model": "", "tagging_kapitel": 0,
            "straenge": False, "straenge_anzahl": 0,
            "thesen": False, "querbezuege": False,
        },
        "bereinigung": {
            "methode": "clean_markdown (ebook-build.py)",
            "verbliebene_reste_geschaetzt": reste_gesamt,
        },
    }
    save_json(ziel_buch / ".progress.json", progress, dry_run)

    # Referenzsprache unveraendert uebernehmen
    if referenz_dir.resolve() == ziel_referenz.resolve():
        # Lektor- und Episto-Wurzel fallen zusammen (Buch liegt bereits unter
        # !Episto, z.B. teilmigrierte Altbestaende) - Referenzsprache ist
        # schon am Zielort, ein Copy waere ein Kopieren auf sich selbst
        # (shutil.SameFileError).
        print(f"  Referenzsprache '{sprache_referenz}': bereits am Zielort ({referenz_dir}), kein Kopiervorgang noetig")
    elif referenz_dir.is_dir():
        ref_chunks, ref_names = read_chunks(referenz_dir)
        if not dry_run:
            (ziel_referenz).mkdir(parents=True, exist_ok=True)
            for name in ref_names:
                shutil.copy2(referenz_dir / name, ziel_referenz / name)
        print(f"  Referenzsprache '{sprache_referenz}': {len(ref_names)} Chunks kopiert nach {ziel_referenz}")
    else:
        print(f"  [Hinweis] keine Referenzsprache gefunden unter {referenz_dir}")

    # Vorhandene chunk-basierte Vorarbeit sichern (nicht loeschen, nicht verarbeiten)
    alte_notizen = quelle_buch / "notizen"
    ziel_alt = ziel_buch / "notizen" / "_chunkweise-vorarbeit"
    kopiert = []
    if alte_notizen.is_dir():
        for name in ("tags.json", "tags.md", "stichworte.md", "_Zusammenfassung_Entwurf.md"):
            p = alte_notizen / name
            if p.exists():
                if not dry_run:
                    ziel_alt.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, ziel_alt / name)
                kopiert.append(name)
        straenge_alt = alte_notizen / "straenge"
        if straenge_alt.is_dir():
            if not dry_run:
                shutil.copytree(straenge_alt, ziel_alt / "straenge", dirs_exist_ok=True)
            kopiert.append("straenge/")
    if kopiert:
        print(f"  Chunk-basierte Vorarbeit gesichert (Referenz fuer Taxonomie-Kuration): {', '.join(kopiert)}")

    if not dry_run:
        offen = schutz.spiele_nach(ziel_buch)
        if offen:
            print(f"  [WARNUNG] {offen} Korrektur(en) aus notizen/redaktion.json konnten nicht "
                  f"erneut angewendet werden (Konflikt, Datei fehlt oder Protokoll unlesbar).")

    print(f"\nFertig{' (DRY-RUN, nichts geschrieben)' if dry_run else ''}.")
    print(f"  Kapitel-Dateien : {len(segs)}")
    print(f"  Gliederungs-Knoten (oberste Ebene): {len(gliederung)}")
    print(f"  Geschaetzte verbliebene Konvertierungsreste: {reste_gesamt}  "
          f"(0 = sauber; >0 -> quelle/*.md stichprobenartig pruefen)")
    print(f"  Ziel: {ziel_buch}")
    print(f"\nNaechste Schritte (auf dem Windows-Rechner, brauchen Ollama):")
    print(f'  tools\\taggen.ps1 -Buch "{ziel_buch}"')
    print(f"  # danach: notizen\\strang_taxonomie.json kuratieren")
    print(f'  #          (Rohstoff: notizen\\_chunkweise-vorarbeit\\stichworte.md, falls vorhanden)')
    print(f'  tools\\straenge.ps1 -Buch "{ziel_buch}"')
    print(f"  tools\\ingest.ps1")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--buch", required=True, help='z.B. "Parvini, Neema/The Populist Delusion"')
    ap.add_argument("--lektor", default=DEFAULT_LEKTOR)
    ap.add_argument("--episto", default=DEFAULT_EPISTO)
    ap.add_argument("--sprache-arbeit", default="de")
    ap.add_argument("--sprache-referenz", default="en")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ueberschreiben", action="store_true",
                    help="vorhandene quelle/*.md ueberschreiben (sonst Abbruch); Volltext-Korrekturen "
                         "aus notizen/redaktion.json werden danach erneut eingespielt")
    args = ap.parse_args()

    verarbeite(
        args.buch.replace("\\", "/"),
        Path(args.lektor), Path(args.episto),
        args.sprache_arbeit, args.sprache_referenz,
        args.dry_run, args.ueberschreiben,
    )


if __name__ == "__main__":
    main()
