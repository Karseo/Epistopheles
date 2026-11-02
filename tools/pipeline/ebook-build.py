"""
ebook-build.py  —  Schritt 3 der eBook-Toolchain: Gesamttext zusammenfuehren

Fuegt die korrekturgelesenen Chunks eines Lektor-Ordners je Sprache zu EINEM
vollstaendigen Markdown-Dokument zusammen — das ist das eigentliche Ziel der
Kette (Weiterverarbeitung mit KI). Die Bibliothek ist zweisprachig (de + en);
standardmaessig werden beide Fassungen gebaut.
Ein EPUB wird nur auf Wunsch zusaetzlich erzeugt (--epub).

Eingabe : <BASE>\\Lektor\\<Autor>\\<Titel>\\de\\chunk_*.md
          <BASE>\\Lektor\\<Autor>\\<Titel>\\en\\chunk_*.md   (+ meta.json)
Ausgabe : <BASE>\\Outbox\\<Autor> - <Titel>_de.md
          <BASE>\\Outbox\\<Autor> - <Titel>_en.md
          dieselben als .epub nur mit --epub

Buecher im alten flachen Schema (chunk_*.md direkt im Buchordner) werden
weiterhin gelesen und als deutsche Fassung behandelt.

Das Markdown traegt YAML-Frontmatter mit den Metadaten und bleibt
standardmaessig ROH: die Formatierung der Quelle (Anker, Div-Marker,
Attribut-Suffixe) bleibt erhalten, weil sie bei der Analyse der Textstruktur
hilft. --clean entfernt sie, wenn ein glatter Lesetext gebraucht wird.

Abhaengigkeiten:
  - Pandoc im PATH — nur fuer --epub  (https://pandoc.org/)

Verwendung:
  python ebook-build.py "Barclay-Fake News"                 # Suche unter Lektor\\
  python ebook-build.py "C:\\...\\Lektor\\Scott Horton\\Provoked"
  python ebook-build.py "Provoked" --sprache de             # nur deutsche Fassung
  python ebook-build.py "Provoked" --epub                   # zusaetzlich EPUB
  python ebook-build.py "Provoked" --clean                  # glatter Lesetext
  python ebook-build.py "Provoked" --check                  # nur pruefen
  python ebook-build.py "Provoked" --force                  # trotz Luecken bauen
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ── Konfiguration ──────────────────────────────────────────────────────────────

PANDOC = "pandoc"
BASE   = Path(os.environ.get("EBOOK_BASE", Path(__file__).resolve().parents[2] / "rohdaten"))
LEKTOR = BASE / "Lektor"
OUTBOX = BASE / "Outbox"

COVER_NAMES = ("cover", "titelbild", "front")
IMG_EXTS    = (".jpg", ".jpeg", ".png", ".gif", ".webp")

# Heuristik "noch nicht uebersetzt": haeufige englische Funktionswoerter
EN_MARKERS = re.compile(
    r'\b(the|and|of|that|with|which|would|there|their|about|between)\b', re.I
)
DE_MARKERS = re.compile(
    r'\b(der|die|das|und|nicht|eine|einen|wurde|werden|sich|auch|wie)\b', re.I
)


# ── Buchordner finden ──────────────────────────────────────────────────────────

def hat_chunks(d: Path) -> bool:
    """Buchordner: Chunks in de\\ bzw. en\\ oder — altes Schema — flach."""
    return (any(d.glob("chunk_*.md"))
            or any((d / lang).glob("chunk_*.md") for lang in ("de", "en")
                   if (d / lang).is_dir()))


def resolve_book_dir(raw: str) -> Path:
    """Akzeptiert vollen Pfad, '<Autor>\\<Titel>' oder nur den Titel."""
    p = Path(raw)
    if p.is_dir():
        return p.resolve()
    cand = LEKTOR / raw
    if cand.is_dir():
        return cand.resolve()
    if LEKTOR.is_dir():
        # Namensvergleich statt glob — Ordnernamen koennen eckige Klammern
        # enthalten, die glob sonst als Zeichenklasse auswertet.
        name = Path(raw).name
        hits = [d for d in LEKTOR.rglob("*")
                if d.is_dir() and d.name == name and hat_chunks(d)]
        if len(hits) == 1:
            return hits[0].resolve()
        if len(hits) > 1:
            raise SystemExit(
                "[FEHLER] Mehrdeutig — bitte vollen Pfad angeben:\n  "
                + "\n  ".join(str(h) for h in hits)
            )
    raise SystemExit(f"[FEHLER] Buchordner nicht gefunden: {raw}\n"
                     f"         Gesucht unter: {LEKTOR}")


def load_meta(book_dir: Path) -> dict:
    """meta.json aus Schritt 1; Fallback auf Ordnernamen."""
    f = book_dir / "meta.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding='utf-8'))
        except Exception as e:
            print(f"[WARNUNG] meta.json unlesbar ({e}) — nutze Ordnernamen.")
    parent = book_dir.parent.name
    return {
        "titel": book_dir.name,
        "autor": parent if book_dir.parent != LEKTOR else "Unbekannt",
        "jahr": "", "titel_voll": book_dir.name, "chunks": 0,
    }


# ── Vollstaendigkeitspruefung ──────────────────────────────────────────────────

def chunk_dir(book_dir: Path, lang: str) -> Path:
    """
    Sprachordner, mit Rueckfall auf das alte flache Schema (chunk_*.md direkt
    im Buchordner) — dort galt implizit Deutsch.
    """
    d = book_dir / lang
    if d.is_dir() and any(d.glob("chunk_*.md")):
        return d
    if lang == "de" and any(book_dir.glob("chunk_*.md")):
        return book_dir
    return d


def check_chunks(book_dir: Path, meta: dict, lang: str) -> tuple[list[Path], list[str]]:
    """
    Liefert (sortierte Chunkliste, Problemliste).
    Prueft: Luecken in der Nummerierung, leere Dateien, unuebersetzt gebliebene.
    """
    src_dir = chunk_dir(book_dir, lang)
    files = sorted(src_dir.glob("chunk_*.md"))
    problems: list[str] = []
    if not files:
        raise SystemExit(f"[FEHLER] Keine chunk_*.md in {src_dir}")

    # erwartete Gesamtzahl: meta.json, sonst .progress.json
    total = int(meta.get("chunks") or 0)
    prog  = book_dir / ".progress.json"
    if not total and prog.exists():
        try:
            total = int(json.loads(prog.read_text(encoding='utf-8')).get("total", 0))
        except Exception:
            total = 0

    nums = set()
    for f in files:
        m = re.search(r'chunk_(\d+)\.md$', f.name)
        if m:
            nums.add(int(m.group(1)))

    if total:
        missing = sorted(set(range(total)) - nums)
        if missing:
            preview = ", ".join(str(n) for n in missing[:15])
            more    = f" … (+{len(missing)-15})" if len(missing) > 15 else ""
            problems.append(f"{len(missing)} fehlende Chunks: {preview}{more}")

    for f in files:
        text = f.read_text(encoding='utf-8', errors='replace').strip()
        if not text:
            problems.append(f"{f.name}: leer")
            continue
        if len(text) < 20:
            problems.append(f"{f.name}: verdaechtig kurz ({len(text)} Zeichen)")
            continue
        # Sprachprobe — nur sinnvoll, wenn eine Zielsprache erwartet wird
        en, de = len(EN_MARKERS.findall(text)), len(DE_MARKERS.findall(text))
        if lang == "de" and en > 5 and en > de * 3:
            problems.append(f"{f.name}: wirkt nicht deutsch (en={en}, de={de})")
        elif lang == "en" and de > 5 and de > en * 3:
            problems.append(f"{f.name}: wirkt nicht englisch (de={de}, en={en})")

    return files, problems


# ── Bereinigung (optional, --clean) ────────────────────────────────────────────

def normalize_footnotes(text: str) -> str:
    """
    Wandelt InDesign-/Pandoc-Fussnotenreferenzen in Pandoc-Fussnotensyntax um.

    Aus
        [[[1](#01_-_Introduction.xhtml_footnote-011){._idFootnoteLink
        ._idGenColorInherit}]{#01_-_Introduction.xhtml_footnote-011-backlink}]
        {.CharOverride-1}
    wird
        [^01-011]

    Die Kapitelnummer aus der Ziel-ID kommt mit in den Bezeichner: die
    Fussnotenzaehlung beginnt je Kapitel neu, im zusammengefuehrten Gesamttext
    waeren blosse Nummern mehrdeutig.
    """
    def bezeichner(ziel: str) -> str:
        m_kap = re.match(r'(\d+)', ziel)
        m_fn  = re.search(r'footnote-(\d+)', ziel)
        nr = m_fn.group(1) if m_fn else "0"
        return f"{m_kap.group(1)}-{nr}" if m_kap else nr

    # Der Linktext ist meist die Fussnotennummer, kann aber eigene Auszeichnung
    # tragen — entscheidend ist allein, dass das Ziel ein footnote-Anker ist.
    TEXT = r'\[[^\]]{0,40}?\]'

    # Vollstaendige Form: aeussere Klammer + Backlink-Span + Attribut-Suffix
    text = re.sub(
        r'\[?\[' + TEXT + r'\(#([^)]*?footnote-\d+)\)\{[^}]*\}\]\{#[^}]*\}\]?'
        r'(?:\s*\{[^}]*\})?',
        lambda m: f"[^{bezeichner(m.group(1))}]", text)

    # Reduzierte Form ohne Backlink-Span
    text = re.sub(
        TEXT + r'\(#([^)]*?footnote-\d+)\)(?:\{[^}]*\})?',
        lambda m: f"[^{bezeichner(m.group(1))}]", text)

    return text


def clean_markdown(text: str) -> str:
    """
    Entfernt Konvertierungsreste aus dem Pandoc-Durchlauf von Schritt 1.
    Gleiche Logik wie Abschnitt 8/9 in build-vault.ps1 — hier fuer den EPUB-Pfad.
    """
    # Fussnotenreferenzen zuerst — sonst zerlegen die Regeln unten die Struktur
    text = normalize_footnotes(text)
    # [Text](#anker){.calibre}  ->  Text
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)\{\.calibre\}', r'\1', text)
    # Fussnoten-Reste  [][[12]](#..)  ->  [^12]
    text = re.sub(r'\[\]\\?\[\\?\[(\d+)\]\\?\]\\?\]\(#[^)]*\)', r'[^\1]', text)
    text = re.sub(r'\[\]\[\[(\d+)\]\]\(#[^)]*\)', r'[^\1]', text)
    # leere Anker-Zeilen und Pandoc-Div-Marker
    text = re.sub(r'(?m)^\s*\[\]\s*$', '', text)
    text = re.sub(r'\[\]\{#[^}]*\}', '', text)          # auch inline
    text = re.sub(r'(?m)^:::+.*$', '', text)
    # Pandoc-Attribute an Ueberschriften:  ## Titel {.unnumbered}  ->  ## Titel
    text = re.sub(r'(?m)^(#{1,6}\s+.*?)\s*\{[^}]*\}\s*$', r'\1', text)
    # verbliebene Attribut-Suffixe an Bildern/Spans
    text = re.sub(r'(?<=\))\{[^}]*\}', '', text)
    # rohe SVG-Cover-Bloecke aus EPUB-Titelseiten
    text = re.sub(r'<svg\b.*?</svg>', '', text, flags=re.S | re.I)
    text = re.sub(r'`<image\b[^`]*`\{=html\}', '', text)
    # mehr als zwei Leerzeilen zusammenfassen
    text = re.sub(r'\n{3,}', '\n\n', text)
    # vor jeder Ueberschrift eine Leerzeile sicherstellen (CommonMark-sauber)
    text = re.sub(r'(?<=\S)\n(#{1,6}\s)', r'\n\n\1', text)
    return text.strip()


def rewrite_image_paths(text: str, media_dir: Path) -> str:
    """
    Bildverweise auf media/ umbiegen, Verweise auf fehlende Dateien entfernen —
    sonst bricht Pandoc beim EPUB-Bau ab.
    """
    def repl(m):
        alt, src = m.group(1), m.group(2)
        name = Path(src.split(")")[0].strip()).name
        if media_dir.is_dir() and (media_dir / name).exists():
            return f"![{alt}](media/{name})"
        return ""
    return re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', repl, text)


def find_cover(media_dir: Path) -> Path | None:
    if not media_dir.is_dir():
        return None
    imgs = [p for p in media_dir.iterdir() if p.suffix.lower() in IMG_EXTS]
    for p in imgs:
        if any(n in p.stem.lower() for n in COVER_NAMES):
            return p
    return max(imgs, key=lambda p: p.stat().st_size) if imgs else None


# ── Markdown bauen (Hauptergebnis) ─────────────────────────────────────────────

def yaml_escape(v: str) -> str:
    return str(v).replace('"', '\\"')


def write_markdown(text: str, out_path: Path, meta: dict, stats: dict) -> None:
    """
    Schreibt den Gesamttext mit YAML-Frontmatter.
    UTF-8 ohne BOM, LF-Zeilenenden — bequem fuer nachgelagerte KI-Pipelines.
    """
    fm = [
        "---",
        f'titel: "{yaml_escape(meta.get("titel_voll") or meta.get("titel", ""))}"',
        f'autor: "{yaml_escape(meta.get("autor_voll") or meta.get("autor", ""))}"',
    ]
    if meta.get("jahr"):
        fm.append(f'jahr: "{yaml_escape(meta["jahr"])}"')
    lang = stats.get("sprache", "de")
    fm += [
        f'sprache: "{lang}"',
        f'quellsprache: "{yaml_escape(meta.get("quellsprache", ""))}"',
        f'uebersetzt: {"false" if meta.get("quellsprache") == lang else "true"}',
        f'uebersetzt_mit: "{yaml_escape(meta.get("modell", ""))}"',
        f'quelldatei: "{yaml_escape(Path(meta.get("quelldatei", "")).name)}"',
        f'chunks: {stats["chunks"]}',
        f'zeichen: {stats["zeichen"]}',
        f'woerter: {stats["woerter"]}',
        f'roh: {"true" if stats.get("roh", True) else "false"}',
        f'erstellt: "{time.strftime("%Y-%m-%d %H:%M:%S")}"',
        "---",
        "",
        "",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(fm))
        f.write(text)
        f.write("\n")


# ── EPUB bauen (optional) ──────────────────────────────────────────────────────

def pandoc_major() -> int:
    """Pandoc-Hauptversion; bei Fehlschlag konservativ 2."""
    try:
        out = subprocess.run([PANDOC, "--version"], capture_output=True,
                             text=True, encoding='utf-8', errors='replace').stdout
        m = re.search(r'pandoc\s+(\d+)\.', out)
        return int(m.group(1)) if m else 2
    except Exception:
        return 2


def build_epub(markdown_text: str, out_path: Path, meta: dict,
               book_dir: Path, cover: Path | None, lang: str = "de") -> None:
    title  = meta.get("titel_voll") or meta.get("titel", "Unbenannt")
    author = meta.get("autor_voll") or meta.get("autor", "Unbekannt")
    year   = meta.get("jahr", "")

    fm = ["---", f'title: "{title}"', f'author: "{author}"', f"lang: {lang}"]
    if year:
        fm.append(f'date: "{year}"')
    fm += ["---", "", ""]

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False,
                                     encoding='utf-8', errors='replace') as f:
        f.write("\n".join(fm))
        f.write(markdown_text)
        tmp_md = Path(f.name)

    # --split-level ab Pandoc 3.x; --epub-chapter-level ist der alte Name
    split_opt = "--split-level=2" if pandoc_major() >= 3 else "--epub-chapter-level=2"
    cmd = [PANDOC, str(tmp_md), "-o", str(out_path),
           split_opt, "--toc", "--toc-depth=2",
           "--resource-path", str(book_dir)]
    if cover:
        cmd += ["--epub-cover-image", str(cover)]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding='utf-8', errors='replace',
                           stdin=subprocess.DEVNULL, timeout=1800)
        if r.returncode != 0:
            raise SystemExit(f"[FEHLER] Pandoc: {r.stderr[:600]}")
        if r.stderr.strip():
            print(f"  [Pandoc-Hinweise] {r.stderr.strip()[:300]}")
    finally:
        tmp_md.unlink(missing_ok=True)


# ── Hauptprogramm ──────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Schritt 3: korrigierte Lektor-Chunks zu einem Markdown-Gesamttext "
                    "zusammenfuehren (optional zusaetzlich EPUB)"
    )
    ap.add_argument("buch",       help="Buchordner (Pfad, '<Autor>\\<Titel>' oder Titel)")
    ap.add_argument("--sprache",  default="beide", choices=["de", "en", "beide"],
                                  help="welche Fassung bauen (Standard: beide)")
    ap.add_argument("--output",   help="Ziel-Markdown (nur bei --sprache de|en; "
                                       "Standard: Outbox\\<Autor> - <Titel>_<lang>.md)")
    ap.add_argument("--epub",     action="store_true",
                                  help="zusaetzlich ein EPUB bauen (Kosmetik, braucht Pandoc)")
    ap.add_argument("--clean",    action="store_true",
                                  help="Konvertierungsreste entfernen (Calibre-Anker, SVG, "
                                       "Div-Marker, Attribut-Suffixe). Standard ist roh — "
                                       "die Quellformatierung hilft bei der Strukturanalyse.")
    ap.add_argument("--footnotes", action="store_true",
                                  help="Fussnotenreferenzen in Pandoc-Syntax [^kap-nr] "
                                       "umwandeln (in --clean bereits enthalten)")
    ap.add_argument("--check",    action="store_true", help="Nur pruefen, nichts schreiben")
    ap.add_argument("--force",    action="store_true", help="Trotz Problemen bauen")
    ap.add_argument("--no-cover", action="store_true", help="Kein Cover ins EPUB einbetten")
    args = ap.parse_args()

    book_dir = resolve_book_dir(args.buch)
    meta     = load_meta(book_dir)
    autor    = meta.get("autor", "Unbekannt")
    titel    = meta.get("titel", book_dir.name)

    langs = ["de", "en"] if args.sprache == "beide" else [args.sprache]
    if args.output and len(langs) > 1:
        raise SystemExit("[FEHLER] --output nur zusammen mit --sprache de oder en.")

    print("=" * 62)
    print("eBook-Build (Schritt 3)")
    print(f"Lektor:   {book_dir}")
    print(f"Autor:    {autor}  |  Titel: {titel}")
    print(f"Sprachen: {', '.join(langs)}")
    if meta.get("status") and meta["status"] != "fertig":
        print(f"[HINWEIS] meta.json meldet Status '{meta['status']}'")
    print("=" * 62)

    media_dir = book_dir / "media"
    gebaut: list[Path] = []

    for lang in langs:
        src_dir = chunk_dir(book_dir, lang)
        if not any(src_dir.glob("chunk_*.md")):
            print(f"\n[{lang}] keine Chunks in {src_dir} — uebersprungen.")
            continue

        md_path = Path(args.output) if args.output else \
                  OUTBOX / f"{autor} - {titel}_{lang}.md"

        print(f"\n--- {lang} ---")
        print(f"Quelle:   {src_dir}")
        files, problems = check_chunks(book_dir, meta, lang)
        print(f"Chunks:   {len(files)}")

        if problems:
            print(f"[PRUEFUNG] {len(problems)} Problem(e):")
            for p in problems[:25]:
                print(f"  - {p}")
            if len(problems) > 25:
                print(f"  … (+{len(problems)-25} weitere)")
            if not (args.force or args.check):
                print(f"[ABBRUCH {lang}] Erst korrigieren, oder mit --force bauen.")
                continue
        else:
            print("[PRUEFUNG] ok — keine Luecken, keine leeren Chunks.")

        if args.check:
            continue

        # ── Chunks zusammenfuegen ────────────────────────────────────────────
        parts = []
        for f in files:
            t = f.read_text(encoding='utf-8', errors='replace')
            if args.footnotes and not args.clean:
                t = normalize_footnotes(t)
            if args.clean:
                t = clean_markdown(t)
            t = rewrite_image_paths(t, media_dir)
            if t.strip():
                parts.append(t.strip())
        full = "\n\n".join(parts)

        # Fussnotendefinitionen anhaengen, falls extrahiert (extract-footnotes.py).
        # Ohne sie sind die [^..]-Referenzen leere Marken.
        fn_datei = src_dir / "footnotes.md"
        if (args.footnotes or args.clean) and fn_datei.exists():
            defs = fn_datei.read_text(encoding='utf-8', errors='replace').strip()
            benutzt = set(re.findall(r'\[\^([\w-]+)\]', full))
            behalten = [d for d in defs.split("\n\n")
                        if (m := re.match(r'\[\^([\w-]+)\]:', d.strip()))
                        and m.group(1) in benutzt]
            if behalten:
                full += "\n\n" + "\n\n".join(behalten) + "\n"
                print(f"Fussnoten: {len(behalten)} Definitionen angehaengt")

        stats = {
            "chunks":  len(files),
            "zeichen": len(full),
            "woerter": len(full.split()),
            "roh":     not args.clean,
            "sprache": lang,
        }
        print(f"Text:     {stats['zeichen']:,} Zeichen, {stats['woerter']:,} Woerter"
              + ("  (bereinigt)" if args.clean else "  (roh)")
              + f", grob ~{stats['zeichen'] // 4:,} Tokens")

        write_markdown(full, md_path, meta, stats)
        print(f"[FERTIG]  {md_path}  ({md_path.stat().st_size / 1_048_576:.1f} MB)")
        gebaut.append(md_path)

        if args.epub:
            # Das eBook gehoert zu den Chunks seiner Sprache, nicht in die Outbox
            epub_dir  = book_dir / lang
            epub_dir.mkdir(parents=True, exist_ok=True)
            epub_path = epub_dir / f"{autor} - {titel}_{lang}.epub"
            cover = None if args.no_cover else find_cover(media_dir)
            if cover:
                print(f"Cover:    {cover.name}")
            build_epub(full, epub_path, meta, book_dir, cover, lang)
            print(f"[FERTIG]  {epub_path}  ({epub_path.stat().st_size / 1_048_576:.1f} MB)")
            gebaut.append(epub_path)

    if gebaut and not args.check:
        print(f"\n         Obsidian-Vault optional: build-vault.ps1 "
              f'-SourceDir "{chunk_dir(book_dir, "de")}" -Buch "{titel}" -Autor "{autor}"')


if __name__ == "__main__":
    main()
