"""
ebook-translate.py  —  Schritt 1 der eBook-Toolchain: Übersetzen ins Deutsche
Übersetzt PDF/EPUB/ODT chunk-weise via aya-expanse:32b (Ollama).

Dieses Skript erzeugt KEIN EPUB. Es liefert Markdown-Chunks zur Korrektur ab:
    <BASE>\\Lektor\\<Autor>\\<Titel>\\de\\chunk_NNN.md
    <BASE>\\Lektor\\<Autor>\\<Titel>\\en\\chunk_NNN.md

Die Bibliothek ist grundsaetzlich ZWEISPRACHIG (de + en):
  - Quelle englisch → en\\ uebernimmt den Quelltext, de\\ wird uebersetzt
  - Quelle deutsch  → de\\ uebernimmt den Quelltext, en\\ wird uebersetzt
  - sonstige Quelle → beide Fassungen werden uebersetzt; das Original bleibt
                      nur als Datei erhalten, nicht als md-Chunks

Den Gesamttext baut anschliessend Schritt 3: ebook-build.py

Ordnerschema:
  Autor/Titel werden aus den Metadaten der Quelldatei gelesen. Sind beide
  eindeutig identifizierbar und zusammen nicht zu lang, wird
  Lektor\\<Autor>\\<Titel>\\ verwendet, sonst Fallback Lektor\\<Dateiname>\\.

Nach vollständiger Übersetzung wird die Quelldatei in den Autor-Ordner
verschoben (Lektor\\<Autor>\\), abschaltbar mit --keep-source.

Resume-Funktion:
  Jeder übersetzte Chunk wird sofort als Datei gespeichert.
  Ein .progress.json trackt den Fortschritt.
  Mit --resume werden bereits übersetzte Chunks übersprungen.

Abhängigkeiten:
  - Pandoc im PATH  (https://pandoc.org/)
  - pip install ebooklib pypdf beautifulsoup4 lxml html2text requests

Verwendung:
  python ebook-translate.py "Barclay-Fake News.epub"      # wird in Inbox\\ gesucht
  python ebook-translate.py "C:\\pfad\\input.pdf" --source-lang en
  python ebook-translate.py "Barclay-Fake News.epub" --resume
  python ebook-translate.py "Barclay-Fake News.epub" --dry-run
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from redaktion import schutz  # noqa: E402

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import requests

# ── Konfiguration ──────────────────────────────────────────────────────────────

OLLAMA_URL    = "http://localhost:11434"
DEFAULT_MODEL = "aya-expanse:32b"
CHUNK_SIZE    = 8000
PANDOC        = "pandoc"

# Arbeitsbasis der Toolchain — alle Schritte spielen sich hierunter ab.
BASE   = Path(os.environ.get("EBOOK_BASE", Path(__file__).resolve().parents[2] / "rohdaten"))
INBOX  = BASE / "Inbox"
LEKTOR = BASE / "Lektor"
OUTBOX = BASE / "Outbox"

# Pfadlängen-Budget (Windows MAX_PATH 260):
#   <LEKTOR>\<Autor>\<Titel>\chunk_NNN.md  bzw.  ...\media\<datei>
MAX_AUTHOR_LEN = 50
MAX_TITLE_LEN  = 80
MAX_COMBINED   = 110   # Autor + Titel zusammen; darüber → Fallback

# Formate, die Pandoc direkt lesen kann (PDF laeuft ueber pypdf-Fallback)
PANDOC_FORMATS  = {".epub", ".odt", ".docx", ".html", ".htm", ".md", ".txt",
                   ".rtf", ".fb2", ".tex", ".org", ".rst"}
# Formate, die erst per Calibre nach EPUB konvertiert werden muessen.
# Pandoc wuerde sie nicht erkennen und dann endlos auf stdin warten.
CONVERT_FORMATS = {".mobi", ".azw", ".azw3", ".azw4", ".lit", ".pdb",
                   ".prc", ".lrf", ".chm", ".djvu", ".cbz", ".cbr"}
CALIBRE_CONVERT = "ebook-convert"

# Metadaten-Werte, die als "nicht identifizierbar" gelten
BAD_META = {
    "", "unknown", "unbekannt", "unknown author", "anonymous", "anonym",
    "n/a", "na", "none", "null", "untitled", "ohne titel", "calibre",
    "microsoft word", "adobe indesign", "author", "titel", "title",
}

LANG_NAMES = {
    "en": "English", "fr": "French", "es": "Spanish", "it": "Italian",
    "pt": "Portuguese", "nl": "Dutch", "pl": "Polish", "ru": "Russian",
    "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "ar": "Arabic",
    "tr": "Turkish", "sv": "Swedish", "da": "Danish", "fi": "Finnish",
    "no": "Norwegian", "cs": "Czech", "hu": "Hungarian", "ro": "Romanian",
    "de": "German",
}

TRANSLATE_PROMPT = (
    "You are a professional {source_lang} ({source_code}) to {target_lang} ({target_code}) translator. "
    "Your goal is to accurately convey the meaning and nuances of the original "
    "{source_lang} text while adhering to {target_lang} grammar, vocabulary, and cultural sensitivities.\n"
    "Produce only the {target_lang} translation, without any additional explanations or commentary. "
    "Please translate the following {source_lang} text into {target_lang}:\n\n\n"
    "{text}"
)

# Die Bibliothek ist grundsaetzlich zweisprachig: Deutsch + Englisch.
# Ist die Quelle weder de noch en, wird zweimal uebersetzt; das Original
# bleibt dann nur als Datei erhalten, nicht als md-Chunks.
LIB_LANGS = ("de", "en")

# ── Hilfsfunktionen: Dateinamen ────────────────────────────────────────────────

def sanitize_filename(name: str, max_len: int = 60) -> str:
    """Bereinigt einen String für den Einsatz als Datei-/Verzeichnisname."""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:max_len].rstrip('. ')


NAME_SUFFIXE = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "phd", "ph.d."}


def normalize_author(raw: str, file_as: str = "") -> str:
    """
    Liefert die Sortierform 'Nachname, Vornamen' — so heissen die Autorordner.

    'Scott Horton'          → 'Horton, Scott'
    'William A. Henry III'  → 'Henry, William A. III'
    'Horton, Scott'         → unveraendert
    'A. Autor; B. Autor'    → nur der erste Autor bestimmt den Ordner

    Das Dublin-Core-Attribut opf:file-as liegt bereits in Sortierform vor und
    wird bevorzugt, wenn es plausibel aussieht.
    """
    def erster(s: str) -> str:
        s = s.strip()
        # 'A.Schumpeter' → 'A. Schumpeter' (fehlendes Leerzeichen nach Initiale)
        s = re.sub(r'\b([A-Z]\.)(?=[A-Z][a-z])', r'\1 ', s)
        for sep in (";", " & ", " and ", " with "):
            if sep in s:
                kopf, rest = s.split(sep, 1)
                # 'Henry, William A; Iii' — der Rest ist nur ein Namenssuffix
                if rest.strip().lower().strip(".,") in NAME_SUFFIXE:
                    s = f"{kopf.strip()} {rest.strip()}"
                else:
                    s = kopf.strip()
                break
        return re.sub(r'\s+', ' ', s).strip()

    # 1. file-as bevorzugen — steht per Spezifikation in Sortierform
    fa = erster(file_as)
    if fa and "," in fa:
        # Namenssuffix ergaenzen, falls es nur im creator-Feld steht
        for t in erster(raw).replace(",", " ").split():
            if t.lower().strip(".,") in NAME_SUFFIXE and t.lower() not in fa.lower():
                fa = f"{fa} {t}"
                break
        return fa

    raw = erster(raw)
    if not raw:
        return ""

    # 2. Enthaelt bereits ein Komma → als Sortierform betrachten
    if "," in raw:
        return raw

    # 3. 'Vornamen Nachname [Suffix]' → 'Nachname, Vornamen [Suffix]'
    teile = raw.split()
    if len(teile) < 2:
        return raw

    suffix = ""
    if teile[-1].lower().strip(".,") in NAME_SUFFIXE:
        suffix = teile.pop()
    if len(teile) < 2:
        return f"{teile[0]} {suffix}".strip()

    nachname = teile[-1]
    vornamen = " ".join(teile[:-1])
    ergebnis = f"{nachname}, {vornamen}"
    return f"{ergebnis} {suffix}".strip() if suffix else ergebnis


def clean_title(raw: str) -> str:
    """Untertitel nach ':' abschneiden, Klammerzusätze am Ende entfernen."""
    raw = re.sub(r'\s+', ' ', raw).strip()
    raw = re.sub(r'\s*\(\d+\)\s*$', '', raw)          # Calibre-ID
    if ":" in raw:
        head = raw.split(":")[0].strip()
        if len(head) >= 3:
            raw = head
    return raw.strip(" -–—_")


def is_identifiable(value: str) -> bool:
    v = (value or "").strip().lower()
    return len(v) >= 2 and v not in BAD_META and not v.isdigit()


def plausibler_autor(kandidat: str, titel: str) -> bool:
    """
    Verwirft Autorangaben, die in Wahrheit Titelwiederholungen sind —
    bei Anna's-Archive-Dateinamen ein haeufiger Katalogisierungsfehler.
    """
    k = kandidat.strip()
    if len(k) < 3 or len(k) > 60:
        return False
    if "[" in k or "]" in k:
        return False
    if len(k.split()) > 6:
        return False
    # starke Wortueberlappung mit dem Titel → vermutlich der Titel selbst
    kw = {w.lower().strip(".,:;") for w in k.split() if len(w) > 3}
    tw = {w.lower().strip(".,:;") for w in titel.split() if len(w) > 3}
    if kw and len(kw & tw) / len(kw) > 0.5:
        return False
    return True


def parse_annas_filename(stem: str) -> dict:
    """
    Metadaten aus dem Dateinamen nach Anna's-Archive-Konvention:

      Titel -- Autor(en) -- Serie/Ausgabe, Ort, Jahr -- Verlag -- isbn13 NNN
      -- md5 -- Anna's Archive

    Felder sind durch ' -- ' getrennt; hinten stehen optional Identifier
    (isbn13 / doi / oclc / duxiu_ssid), ein md5-Hash und die Herkunftsangabe.
    Zeichen, die im Dateinamen unzulaessig sind, wurden durch '_' ersetzt.
    """
    teile = [t.strip() for t in stem.split(" -- ") if t.strip()]
    if len(teile) < 2:
        return {}

    def entschaerfe(s: str) -> str:
        # 'Donald A_ Barclay' → 'Donald A. Barclay'  (Initiale)
        s = re.sub(r'\b([A-Z])_(\s)', r'\1.\2', s)
        # 'Democratic Elitism_ The Founding' → 'Democratic Elitism: The Founding'
        s = re.sub(r'(\w)_(\s)', r'\1:\2', s)
        return re.sub(r'\s+', ' ', s).strip()

    meta = {"author": "", "title": "", "year": "", "file_as": "",
            "publisher": "", "isbn": "", "quelle": "dateiname"}
    meta["title"] = entschaerfe(teile[0])

    # Das Autorfeld ist bei schlecht katalogisierten Titeln oft eine
    # Titelwiederholung. Solche Werte sind schaedlicher als gar kein Autor.
    kandidat = entschaerfe(teile[1])
    if plausibler_autor(kandidat, meta["title"]):
        meta["author"] = kandidat

    rest = teile[2:]
    for feld in rest:
        f = feld.strip()
        low = f.lower()
        if not meta["isbn"]:
            m = re.search(r'isbn13?\s*([0-9Xx\-]{10,17})', f)
            if m:
                meta["isbn"] = m.group(1).replace("-", "")
                continue
        if not meta["year"]:
            m = re.search(r'\b(1[5-9]\d{2}|20\d{2})\b', f)
            if m:
                meta["year"] = m.group(1)
        # Verlag: Feld ohne Identifier, ohne reinen Hash, nicht die Herkunft
        if (not meta["publisher"] and not re.fullmatch(r'[0-9a-f]{32}', low)
                and "anna" not in low
                and not re.match(r'(isbn|doi|oclc|duxiu|md5)', low)
                and not re.fullmatch(r'[\d\s.,-]+', f)):
            kandidat = re.sub(r'\s*;\s*$', '', f)
            if len(kandidat) > 3 and not re.search(r'\b(ed|edition|ausg)\b', low):
                meta["publisher"] = entschaerfe(kandidat)
    return meta


def read_metadata(input_path: Path) -> dict:
    """
    Liest Autor/Titel/Jahr aus den Metadaten der Quelldatei.
    EPUB via ebooklib (Dublin Core), PDF via pypdf. Fehler sind nicht fatal.
    """
    meta = {"author": "", "title": "", "year": "", "file_as": ""}
    suffix = input_path.suffix.lower()
    try:
        if suffix == ".epub":
            from ebooklib import epub
            book = epub.read_epub(str(input_path), options={"ignore_ncx": True})
            def dc(field):
                vals = book.get_metadata("DC", field)
                return vals[0][0].strip() if vals and vals[0] and vals[0][0] else ""
            meta["author"] = dc("creator")
            meta["title"]  = dc("title")
            # opf:file-as steht bereits in Sortierform 'Nachname, Vorname'
            creators = book.get_metadata("DC", "creator")
            if creators and len(creators[0]) > 1 and isinstance(creators[0][1], dict):
                for k, v in creators[0][1].items():
                    if k.endswith("file-as") and v:
                        meta["file_as"] = str(v).strip()
                        break
            date = dc("date")
            m = re.search(r'(1[5-9]\d{2}|20\d{2})', date)
            if m:
                meta["year"] = m.group(1)
        elif suffix == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError:
                from PyPDF2 import PdfReader
            info = PdfReader(str(input_path)).metadata or {}
            meta["author"] = str(info.get("/Author", "") or "").strip()
            meta["title"]  = str(info.get("/Title", "") or "").strip()
    except Exception as e:
        print(f"  [Metadaten nicht lesbar: {e}]")

    # Fallback/Ergaenzung aus dem Dateinamen (Anna's-Archive-Konvention).
    # Betrifft vor allem PDFs, deren Info-Dictionary meist leer ist.
    aus_name = parse_annas_filename(input_path.stem)
    if aus_name:
        ergaenzt = []
        for feld in ("author", "title", "year"):
            if not is_identifiable(meta.get(feld, "")) and aus_name.get(feld):
                meta[feld] = aus_name[feld]
                ergaenzt.append(feld)
        for feld in ("publisher", "isbn"):
            if aus_name.get(feld):
                meta.setdefault(feld, aus_name[feld])
        if ergaenzt:
            print(f"  [Dateiname ergaenzt: {', '.join(ergaenzt)}]")
    return meta


def resolve_book_dir(input_path: Path) -> tuple[Path, str, str, str, dict]:
    """
    Bestimmt Zielordner, Autor, Titel, den Grund der Entscheidung und liefert
    die gelesenen Rohmetadaten mit zurück (für meta.json).

    Lektor\\<Autor>\\<Titel>\\  wenn beide Metadaten eindeutig identifizierbar
    sind und zusammen MAX_COMBINED Zeichen nicht überschreiten,
    sonst Fallback Lektor\\<Dateiname>\\.
    """
    meta   = read_metadata(input_path)
    stem   = sanitize_filename(input_path.stem, MAX_TITLE_LEN)
    author = sanitize_filename(
        normalize_author(meta["author"], meta.get("file_as", "")), MAX_AUTHOR_LEN)
    title  = sanitize_filename(clean_title(meta["title"]),       MAX_TITLE_LEN)

    if not (is_identifiable(author) and is_identifiable(title)):
        return LEKTOR / stem, "Unbekannt", stem, "Metadaten unvollständig", meta
    if len(author) + len(title) > MAX_COMBINED:
        return LEKTOR / stem, author, title, \
               f"Autor+Titel zu lang ({len(author)+len(title)} > {MAX_COMBINED})", meta
    return LEKTOR / author / title, author, title, "Metadaten", meta


def resolve_input(raw: str) -> Path:
    """
    Findet die Eingabedatei: exakter Pfad → Inbox\\ → rekursiv unter Lektor\\
    (damit --resume auch nach dem Verschieben der Quelldatei funktioniert).
    """
    p = Path(raw)
    if p.exists():
        return p.resolve()
    cand = INBOX / raw
    if cand.exists():
        return cand.resolve()
    # Namensvergleich statt glob: Dateinamen enthalten haeufig eckige Klammern,
    # die glob als Zeichenklasse deutet — der Treffer bliebe dann aus.
    name = Path(raw).name
    if LEKTOR.exists():
        for p in LEKTOR.rglob("*"):
            if p.is_file() and p.name == name:
                return p.resolve()
    raise SystemExit(f"[FEHLER] Eingabedatei nicht gefunden: {raw}\n"
                     f"         Gesucht in: {p}, {cand}, {LEKTOR}\\**")


# ── Lektor: Fortschritt & Chunk-Dateien ───────────────────────────────────────

class LektorSession:
    """
    Verwaltet den Korrektur-Ordner eines Buchs — zweisprachig:
      <BASE>/Lektor/<Autor>/<Titel>/
        de/chunk_000.md …  deutsche Fassung
        en/chunk_000.md …  englische Fassung
        .progress.json     Fortschritt je Sprache (Resume)
        meta.json          Metadaten für Schritt 3 (ebook-build.py)
        media/             Bilder aus der Quelldatei
    """

    def __init__(self, book_dir: Path, langs: tuple[str, ...] = LIB_LANGS):
        self.book_dir      = book_dir
        self.langs         = langs
        self.progress_file = self.book_dir / ".progress.json"
        self.meta_file     = self.book_dir / "meta.json"
        self.media_dir     = self.book_dir / "media"
        self.book_dir.mkdir(parents=True, exist_ok=True)
        for lang in langs:
            (self.book_dir / lang).mkdir(exist_ok=True)
        self._progress: dict = self._load_progress()

    def write_meta(self, data: dict):
        """Schnittstelle zu ebook-build.py — ohne diese Datei muss Schritt 2 raten."""
        self.meta_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8'
        )

    # ── Fortschritt ────────────────────────────────────────────────────────────

    def _load_progress(self) -> dict:
        if self.progress_file.exists():
            try:
                p = json.loads(self.progress_file.read_text(encoding='utf-8'))
                # Altformat (flach, nur Deutsch) auf Sprachformat heben
                if "completed" in p and "sprachen" not in p:
                    p = {"total": p.get("total", 0), "source": p.get("source", ""),
                         "sprachen": {"de": {"completed": p.get("completed", [])}}}
                p.setdefault("sprachen", {})
                return p
            except Exception:
                pass
        return {"total": 0, "source": "", "sprachen": {}}

    def _lang_entry(self, lang: str) -> dict:
        return self._progress["sprachen"].setdefault(lang, {"completed": []})

    def _save_progress(self):
        self.progress_file.write_text(
            json.dumps(self._progress, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

    def init(self, total_chunks: int, source: str):
        """Initialisiert den Fortschritts-Tracker (nur wenn nicht bereits vorhanden)."""
        if not self._progress.get("total"):
            self._progress["total"]  = total_chunks
            self._progress["source"] = source
            self._save_progress()

    def is_done(self, index: int, lang: str) -> bool:
        return index in self._lang_entry(lang)["completed"]

    def mark_done(self, index: int, lang: str):
        entry = self._lang_entry(lang)
        if index not in entry["completed"]:
            entry["completed"].append(index)
            self._save_progress()

    def completed_count(self, lang: str) -> int:
        return len(self._lang_entry(lang)["completed"])

    @property
    def total(self) -> int:
        return self._progress.get("total", 0)

    # ── Chunk-Dateien ──────────────────────────────────────────────────────────

    def chunk_path(self, index: int, lang: str) -> Path:
        return self.book_dir / lang / f"chunk_{index:03d}.md"

    def write_chunk(self, index: int, text: str, lang: str):
        p = self.chunk_path(index, lang)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        self.mark_done(index, lang)

    def read_chunk(self, index: int, lang: str) -> str:
        return self.chunk_path(index, lang).read_text(encoding='utf-8')

    def all_chunks_sorted(self, lang: str) -> list[Path]:
        return sorted((self.book_dir / lang).glob("chunk_*.md"))

    def extract_media(self, input_path: Path) -> int:
        """
        Zieht Bilder aus der Quelldatei nach media/.
        Pandoc schreibt Bildverweise in die Chunks, extrahiert die Dateien aber
        nicht — ohne diesen Schritt sind die Verweise im Ziel-EPUB tot.
        """
        if input_path.suffix.lower() != ".epub":
            return 0
        import zipfile
        exts  = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"}
        count = 0
        try:
            with zipfile.ZipFile(input_path) as z:
                for name in z.namelist():
                    if Path(name).suffix.lower() not in exts:
                        continue
                    self.media_dir.mkdir(parents=True, exist_ok=True)
                    target = self.media_dir / Path(name).name
                    if not target.exists():
                        target.write_bytes(z.read(name))
                    count += 1
        except Exception as e:
            print(f"  [Medien-Extraktion fehlgeschlagen: {e}]")
        return count

# ── Text-Extraktion ────────────────────────────────────────────────────────────

def extract_text_pandoc(input_path: Path) -> str:
    # stdin=DEVNULL ist Pflicht: bei unbekanntem Eingabeformat liest Pandoc
    # sonst von stdin und haengt endlos, statt einen Fehler zu melden.
    result = subprocess.run(
        [PANDOC, str(input_path), "-t", "markdown", "--wrap=none"],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        stdin=subprocess.DEVNULL, timeout=900
    )
    if result.returncode != 0:
        raise RuntimeError(f"Pandoc-Fehler: {result.stderr[:300]}")
    return result.stdout


def extract_text_pypdf(input_path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader
    reader = PdfReader(str(input_path))
    pages  = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        pages.append(f"## Seite {i}\n\n{text}")
    return "\n\n".join(pages)


def ensure_readable(input_path: Path) -> tuple[Path, Path | None]:
    """
    Sorgt fuer ein Format, das Pandoc lesen kann.

    MOBI/AZW3/LIT/... werden per Calibre 'ebook-convert' nach EPUB konvertiert.
    Rueckgabe: (zu verarbeitende Datei, Originaldatei falls konvertiert wurde).
    """
    suffix = input_path.suffix.lower()
    if suffix == ".pdf" or suffix in PANDOC_FORMATS:
        return input_path, None

    if suffix not in CONVERT_FORMATS:
        raise SystemExit(
            f"[FEHLER] Format '{suffix}' wird nicht unterstuetzt.\n"
            f"         Direkt lesbar: {', '.join(sorted(PANDOC_FORMATS | {'.pdf'}))}\n"
            f"         Konvertierbar: {', '.join(sorted(CONVERT_FORMATS))}"
        )

    epub_path = input_path.with_suffix(".epub")
    if epub_path.exists():
        print(f"[KONVERT] {suffix} → EPUB bereits vorhanden: {epub_path.name}")
        return epub_path, input_path

    print(f"[KONVERT] {suffix} ist fuer Pandoc unlesbar → konvertiere via Calibre ...")
    try:
        r = subprocess.run(
            [CALIBRE_CONVERT, str(input_path), str(epub_path)],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            stdin=subprocess.DEVNULL, timeout=1800
        )
    except FileNotFoundError:
        raise SystemExit(
            f"[FEHLER] '{CALIBRE_CONVERT}' nicht gefunden — Calibre wird zum Lesen "
            f"von {suffix} benoetigt.\n"
            f"         Entweder Calibre installieren (calibre-ebook.com) oder die "
            f"Datei manuell nach EPUB konvertieren."
        )
    except subprocess.TimeoutExpired:
        raise SystemExit("[FEHLER] Calibre-Konvertierung nach 30 Minuten abgebrochen.")

    if r.returncode != 0 or not epub_path.exists():
        raise SystemExit(f"[FEHLER] Calibre-Konvertierung fehlgeschlagen:\n{r.stderr[-600:]}")

    size_mb = epub_path.stat().st_size / 1_048_576
    print(f"[KONVERT] → {epub_path.name} ({size_mb:.1f} MB)")
    return epub_path, input_path


def extract_text(input_path: Path) -> str:
    suffix = input_path.suffix.lower()
    print(f"[EXTRAKTION] {input_path.name} ({suffix}) → Markdown ...")
    if suffix == ".pdf":
        try:
            text = extract_text_pandoc(input_path)
            if len(text.strip()) < 200:
                raise RuntimeError("Pandoc-Output zu kurz, PDF wahrscheinlich gescannt")
            print(f"  → Pandoc: {len(text):,} Zeichen")
        except Exception as e:
            print(f"  → [pypdf Fallback] ({e})")
            text = extract_text_pypdf(input_path)
            chars = len(text)
            pages = text.count("## Seite")
            print(f"  → [pypdf Fallback] {chars:,} Zeichen aus {pages} Seiten")
    else:
        text = extract_text_pandoc(input_path)
        print(f"  → Pandoc: {len(text):,} Zeichen")
    return text


# ── Chunking ───────────────────────────────────────────────────────────────────

def split_into_chunks(text: str, chunk_size: int) -> list[str]:
    """
    Teilt Text an Absatzgrenzen auf. Kein harter Schnitt mitten in Absätzen.
    Überlange Absätze werden an Satzgrenzen geteilt.
    """
    paragraphs = re.split(r'\n\s*\n', text)
    chunks, current = [], ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(para) > chunk_size:
            # Langen Absatz an Satzgrenzen teilen
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sent in sentences:
                if len(current) + len(sent) + 2 > chunk_size and current:
                    chunks.append(current.strip())
                    current = sent
                else:
                    current = (current + " " + sent).strip() if current else sent
        else:
            if len(current) + len(para) + 2 > chunk_size and current:
                chunks.append(current.strip())
                current = para
            else:
                current = (current + "\n\n" + para).strip() if current else para

    if current.strip():
        chunks.append(current.strip())

    return chunks

# ── Sprach-Detektion ───────────────────────────────────────────────────────────

def detect_language(text: str, ollama_url: str, model: str) -> str:
    sample = text[:500].replace('\n', ' ')
    payload = {
        "model": model,
        "prompt": (
            f"Identify the language of this text. Reply with ONLY the ISO 639-1 "
            f"two-letter code (e.g. 'en', 'fr', 'de'):\n\n{sample}"
        ),
        "stream": False,
        "options": {"temperature": 0.0, "num_ctx": 512},
    }
    resp = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=30)
    resp.raise_for_status()
    code = resp.json().get("response", "").strip().lower()[:2]
    return code if code in LANG_NAMES else "en"


# ── Übersetzung ────────────────────────────────────────────────────────────────

def translate_chunk(text: str, source_code: str, source_lang: str,
                    ollama_url: str, model: str,
                    target_code: str = "de", target_lang: str = "German") -> str:
    prompt  = TRANSLATE_PROMPT.format(
        source_lang=source_lang, source_code=source_code,
        target_lang=target_lang, target_code=target_code, text=text
    )
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_ctx": 16384},
    }
    consecutive_429 = 0
    for attempt in range(3):
        try:
            resp = requests.post(
                f"{ollama_url}/api/generate", json=payload, timeout=300
            )
            if resp.status_code == 429:
                consecutive_429 += 1
                if consecutive_429 >= 3:
                    print("\n[ABORT] 3× Rate-Limit (429). Fortschritt gespeichert.")
                    sys.exit(1)
                wait = 10 * (2 ** attempt)
                print(f" [429 Rate-Limit, warte {wait}s]", end="", flush=True)
                time.sleep(wait)
                continue
            if resp.status_code == 403:
                print("\n[FEHLER 403] Referrer-Block. API-Key prüfen: "
                      "Application restrictions = None setzen.")
                sys.exit(1)
            resp.raise_for_status()
            consecutive_429 = 0
            return resp.json().get("response", "").strip()
        except requests.exceptions.Timeout:
            if attempt < 2:
                print(f" [Timeout, Versuch {attempt+2}/3]", end="", flush=True)
                time.sleep(5)
            else:
                raise
    return ""


# ── Quelldatei archivieren ─────────────────────────────────────────────────────

def move_source(input_path: Path, book_dir: Path, lang: str = "") -> Path | None:
    """
    Legt die Datei zu den Chunks ihrer Sprache: <Buchordner>\\<lang>\\.
    Ohne lang (z.B. Original einer dritten Sprache) in den Buchordner selbst.
    Erst nach vollständiger Übersetzung aufrufen — sonst bricht --resume.
    """
    target_dir = (book_dir / lang) if lang else book_dir
    target     = target_dir / input_path.name
    if input_path.resolve() == target.resolve():
        return target                      # liegt bereits am Ziel
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        if target.exists():
            stem, suf = target.stem, target.suffix
            n = 2
            while (target_dir / f"{stem} ({n}){suf}").exists():
                n += 1
            target = target_dir / f"{stem} ({n}){suf}"
        input_path.replace(target)
        return target
    except Exception as e:
        print(f"[WARNUNG] Quelldatei nicht verschoben: {e}")
        return None

# ── Hauptprogramm ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Schritt 1: eBook übersetzen (PDF/EPUB/ODT → deutsche Chunks im Lektor-Ordner)"
    )
    parser.add_argument("input",          help="Eingabedatei (Pfad oder Dateiname in Inbox\\)")
    parser.add_argument("--lektor",       default=str(LEKTOR),
                                          help="Lektor-Basisverzeichnis (überschreibt ENV EBOOK_BASE)")
    parser.add_argument("--book-dir",     default=None,
                                          help="Buchordner explizit vorgeben — noetig bei "
                                               "kuratierten Ordnernamen, die von den "
                                               "Metadaten abweichen (z.B. beim --resume)")
    parser.add_argument("--keep-source",  action="store_true",
                                          help="Quelldatei nach Abschluss NICHT verschieben")
    parser.add_argument("--model",        default=DEFAULT_MODEL)
    parser.add_argument("--chunk-size",   type=int, default=CHUNK_SIZE)
    parser.add_argument("--delay",        type=float, default=0.0)
    parser.add_argument("--ollama-url",   default=OLLAMA_URL)
    parser.add_argument("--source-lang",  default=None,
                                          help="Quellsprache erzwingen (z.B. 'en')")
    parser.add_argument("--resume",       action="store_true",
                                          help="Abgebrochene Übersetzung fortführen")
    parser.add_argument("--korrekturen-verwerfen", action="store_true",
                                          help="Ohne --resume trotz vorhandener redaktion.json (Korrekturen) alles neu uebersetzen und die Korrekturen verwerfen")
    parser.add_argument("--dry-run",      action="store_true",
                                          help="Nur Extraktion, keine Übersetzung")
    parser.add_argument("--ohne-referenz", action="store_true",
                                          help="Nur die Quellsprache uebernehmen, NICHT in die "
                                               "andere Bibliothekssprache ruebersetzen. Sinnvoll, "
                                               "wenn die Quelle selbst schon eine Uebersetzung ist "
                                               "(z.B. eine deutsche Ausgabe eines englischen "
                                               "Originals) - eine Ruebersetzung zurueck waere dann "
                                               "eine Uebersetzung zweiter Hand. Wirkt nur, wenn die "
                                               "erkannte/erzwungene Quellsprache 'de' oder 'en' ist; "
                                               "bei einer dritten Sprache ohne Wirkung (dann werden "
                                               "wie bisher beide Bibliothekssprachen uebersetzt).")
    args = parser.parse_args()

    input_path = resolve_input(args.input)

    # Format sicherstellen — vor der Metadaten-Ermittlung, damit auch bei
    # MOBI & Co. die Metadaten des konvertierten EPUB gelesen werden.
    input_path, original_source = ensure_readable(input_path)

    # Zielordner aus Metadaten bestimmen (Lektor\<Autor>\<Titel> oder Fallback)
    book_dir, author, title, reason, raw_meta = resolve_book_dir(input_path)
    if args.lektor and Path(args.lektor) != LEKTOR:
        book_dir = Path(args.lektor) / book_dir.relative_to(LEKTOR)

    # Explizit vorgegebener Ordner hat Vorrang — Autor/Titel dann von dort,
    # weil kuratierte Ordnernamen verlaesslicher sind als Dateimetadaten.
    if args.book_dir:
        book_dir = Path(args.book_dir)
        if not book_dir.is_absolute():
            book_dir = LEKTOR / args.book_dir
        book_dir = book_dir.resolve()
        title  = book_dir.name
        author = book_dir.parent.name if book_dir.parent != LEKTOR else author
        reason = "Ordner vorgegeben (--book-dir)"

    print("=" * 62)
    print(f"eBook-Übersetzer (Schritt 1) | Modell: {args.model}")
    print(f"Eingabe:  {input_path}")
    print(f"Lektor:   {book_dir}")
    print(f"Autor:    {author}  |  Titel: {title}   [{reason}]")
    print("=" * 62)

    # Schutz: Neuübersetzung würde Korrekturen (redaktion.json) verwerfen
    fehler = schutz.pruefe_neuuebersetzung(book_dir, args.resume, args.korrekturen_verwerfen)
    if fehler:
        raise SystemExit(fehler)

    # Text extrahieren (Session erst nach dem Dry-Run-Check öffnen —
    # sonst legt ein Dry-Run leere Lektor-Ordner an)
    text   = extract_text(input_path)
    chunks = split_into_chunks(text, args.chunk_size)

    print(f"\nSprache:  ", end="")

    # Sprache ermitteln
    if args.source_lang:
        source_code = args.source_lang.lower()
        source_lang = LANG_NAMES.get(source_code, source_code.upper())
        print(f"{source_lang} (erzwungen)")
    elif args.dry_run:
        source_code, source_lang = "?", "?"
        print("? (dry-run, wird übersprungen)")
    else:
        source_code = detect_language(text, args.ollama_url, args.model)
        source_lang = LANG_NAMES.get(source_code, source_code.upper())
        print(source_lang)

    total = len(chunks)

    # ── Sprachplan: die Bibliothek ist immer de + en ──────────────────────────
    # Die Quellsprache wird uebernommen, wenn sie de oder en ist; sonst wird
    # zweimal uebersetzt und das Original bleibt nur als Datei erhalten.
    plan: list[tuple[str, str]] = []      # (Sprachcode, "uebernehmen"|"uebersetzen")
    for lang in LIB_LANGS:
        plan.append((lang, "uebernehmen" if lang == source_code else "uebersetzen"))

    if args.ohne_referenz and source_code in LIB_LANGS:
        plan = [(lang, mode) for lang, mode in plan if lang == source_code]
        print(f"[HINWEIS] --ohne-referenz: nur '{source_code}' wird angelegt, "
              f"keine Ruebersetzung in die andere Bibliothekssprache.")
    elif args.ohne_referenz:
        print(f"[HINWEIS] --ohne-referenz wirkungslos: Quellsprache '{source_code}' "
              f"ist weder de noch en, beide Bibliothekssprachen werden wie gehabt uebersetzt.")

    if source_code == "?":
        # Dry-Run ohne --source-lang: die Sprache wurde nicht ermittelt, ein
        # Plan waere geraten.
        print("\nBibliothek: de\\ + en\\ — Aufteilung erst nach der "
              "Spracherkennung (--source-lang setzen, um sie hier zu sehen)")
    else:
        plan_txt = ", ".join(
            f"{lang}\\ ({'Quelltext' if mode == 'uebernehmen' else 'Übersetzung'})"
            for lang, mode in plan
        )
        print(f"\nBibliothek: {plan_txt}")
        if source_code not in LIB_LANGS:
            print(f"            Original ({source_lang}) bleibt nur als Datei erhalten, "
                  f"nicht als Chunks.")

    if args.dry_run:
        print(f"\n[DRY-RUN] Extraktion erfolgreich. {len(text):,} Zeichen.")
        print(f"Chunks bei size={args.chunk_size}: {total}")
        preview = chunks[0][:300].replace('\n', '↵ ') if chunks else ""
        print(f"\nVorschau:\n{preview}")
        return

    # Lektor-Session öffnen (legt den Buchordner an)
    session = LektorSession(book_dir)

    # Sichern, welche Quelldatei fuer dieses Buch-Verzeichnis BISHER als
    # Ursprung eingetragen war - session._progress wird beim Konstruieren
    # bereits von der Festplatte geladen, der Wert ist also schon HIER (vor
    # jedem Schreiben) verfuegbar, nicht erst vor session.init(). Wird
    # gebraucht, um zwischen zwei Faellen zu unterscheiden: einem erneuten
    # Lauf DERSELBEN Quelldatei (z.B. --ohne-referenz nachtraeglich ergaenzt)
    # versus einem bewusst zweisprachigen Buch-Verzeichnis, in das zwei
    # VERSCHIEDENE Quelldateien (je eine Sprache) nacheinander eingelesen
    # werden (z.B. deutsches Original per OCR + separat eingelesene
    # fremdsprachige Referenzuebersetzung, siehe Popper/Logik der Forschung).
    # meta.json beschreibt in diesem Fall die HAUPTQUELLE (Titel, Autor,
    # Zeichenzahl etc. des eigentlichen Werks) und darf durch einen Lauf, der
    # nur die Referenzsprache nachliefert, NICHT mit deren eigenen Metadaten
    # ueberschrieben werden (Bug, der genau das tat: meta.json zeigte danach
    # Titel/Autor/Zeichenzahl der englischen Referenzausgabe statt des
    # deutschen Originals).
    alte_quelle = session._progress.get("source", "")
    gleiche_quelle = (not alte_quelle) or (alte_quelle == str(input_path))

    def build_meta(status: str, src: Path) -> dict:
        """meta.json-Inhalt — wird zu Beginn und am Ende geschrieben."""
        return {
            "titel":        title,
            "autor":        author,
            "jahr":         raw_meta.get("year", ""),
            "titel_voll":   raw_meta.get("title", "") or title,
            "autor_voll":   raw_meta.get("author", "") or author,
            "quelldatei":   str(src),
            "original":     str(original_source) if original_source else "",
            "quellsprache": source_code,
            "sprachen":     list(LIB_LANGS),
            "quelle_uebernommen": source_code if source_code in LIB_LANGS else "",
            "modell":       args.model,
            "chunk_size":   args.chunk_size,
            "chunks":       total,
            "ordner_grund": reason,
            "status":       status,
            "zeichen_quelle": len(text),
            "erstellt":     time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def schreibe_meta(status: str, src: Path):
        """Wie build_meta()+write_meta(), aber sicher fuer zweisprachige
        Buch-Verzeichnisse aus zwei unabhaengigen Quelldateien (s.o.)."""
        if gleiche_quelle:
            session.write_meta(build_meta(status, src))
        else:
            print(f"[HINWEIS] meta.json beschreibt bereits eine andere Quelldatei "
                  f"({alte_quelle}) - wird von diesem Lauf (Sprache '{source_code}') "
                  f"nicht ueberschrieben.")

    # meta.json sofort schreiben — nicht erst am Ende. So ist sie auch bei
    # einem Abbruch vorhanden und Schritt 3 muss nie raten.
    schreibe_meta("in_arbeit", input_path)

    # Medien früh sichern (unabhängig vom Abschluss der Übersetzung)
    media_count = session.extract_media(input_path)
    if media_count:
        print(f"[MEDIEN] {media_count} Bilddateien → {session.media_dir}")

    session.init(total, str(input_path))

    # Ohne --resume bei vorhandenen Chunks den Fortschritt zurücksetzen
    if not args.resume:
        vorhanden = {l: session.completed_count(l) for l, _ in plan}
        if any(vorhanden.values()):
            print("[HINWEIS] Bereits vorhanden: "
                  + ", ".join(f"{l}={n}" for l, n in vorhanden.items())
                  + f" von {total}. Starte neu — --resume führt stattdessen fort.")
            session._progress["sprachen"] = {}
            session._save_progress()

    # Automatisches Loeschen ist nur sicher, wenn diese Quelldatei bereits
    # vorher fuer GENAU dieses Buch-Verzeichnis verwendet wurde (oder das
    # Verzeichnis frisch ist) - dann koennen Dateien in der jetzt abgewaehlten
    # Sprache nur Reste eines fruehen/abgebrochenen Versuchs DIESER Quelle
    # sein. Steht dort eine ANDERE Quelldatei, ist das Verzeichnis bewusst
    # zweisprachig aus zwei getrennten Quellen aufgebaut (z.B. deutsches
    # OCR-Original + separat eingelesene fremdsprachige Ausgabe) - dann waeren
    # die Dateien der abgewaehlten Sprache das Ergebnis JENES ANDEREN Laufs,
    # kein Rest, und duerfen nicht angetastet werden.
    # (gleiche_quelle wurde bereits weiter oben, vor dem ersten meta.json-
    # Schreiben, berechnet - siehe dort.)

    if args.ohne_referenz and source_code in LIB_LANGS:
        geplante_sprachen = {l for l, _ in plan}
        for lang in LIB_LANGS:
            if lang in geplante_sprachen:
                continue
            verwaist = session.all_chunks_sorted(lang)
            if not verwaist:
                continue
            if gleiche_quelle:
                for p in verwaist:
                    p.unlink()
                print(f"[AUFRAEUMEN] --ohne-referenz: {len(verwaist)} verwaiste "
                      f"Chunk-Datei(en) aus '{lang}\\' entfernt (Rest eines frueheren "
                      f"Laufs derselben Quelldatei).")
            else:
                print(f"[HINWEIS] '{lang}\\' enthaelt {len(verwaist)} Datei(en) aus einer "
                      f"ANDEREN Quelldatei ({alte_quelle}) - wird NICHT angetastet, da dies "
                      f"nach einem bewusst zweisprachigen Buch-Verzeichnis aussieht.")

    # ── Übersetzungsläufe je Zielsprache ──────────────────────────────────────
    bilanz: dict[str, tuple[int, int]] = {}

    for lang, mode in plan:
        lang_name = LANG_NAMES.get(lang, lang.upper())
        done = skipped = 0

        if mode == "uebernehmen":
            # Quelltext unverändert übernehmen — keine Modellanfrage nötig
            for i, chunk in enumerate(chunks):
                if args.resume and session.is_done(i, lang):
                    skipped += 1
                    continue
                session.write_chunk(i, chunk, lang)
                done += 1
            print(f"\n[{lang}] Quelltext übernommen: {done} Chunks"
                  + (f", {skipped} übersprungen" if skipped else "") + ".")
            bilanz[lang] = (done, skipped)
            continue

        print(f"\n[{lang}] Übersetze {source_lang} → {lang_name} ...")
        for i, chunk in enumerate(chunks):
            if args.resume and session.is_done(i, lang):
                skipped += 1
                continue

            bar_done = int(30 * (i + 1) / total)
            bar_str  = "█" * bar_done + "░" * (30 - bar_done)
            pct      = int(100 * (i + 1) / total)
            print(f"\r[{bar_str}] {pct:3d}% | {lang} | Chunk {i+1:4d}/{total} "
                  f"({'übersprungen: ' + str(skipped) if skipped else ''})",
                  end="", flush=True)

            translated = translate_chunk(
                chunk, source_code, source_lang, args.ollama_url, args.model,
                target_code=lang, target_lang=lang_name
            )
            session.write_chunk(i, translated, lang)
            done += 1

            if args.delay > 0:
                time.sleep(args.delay)

        print(f"\n[{lang}] {done} Chunks übersetzt"
              + (f", {skipped} übersprungen (Resume)" if skipped else "") + ".")
        bilanz[lang] = (done, skipped)

    # ── Quelldatei archivieren (erst jetzt — vorher bräuchte --resume sie) ────
    final_source = input_path
    vollstaendig = all(session.completed_count(l) >= total for l, _ in plan)
    if not args.keep_source and vollstaendig:
        # Die Datei gehoert zu den Chunks ihrer Sprache. Ist die Quellsprache
        # weder de noch en, liegt das Original im Buchordner selbst.
        quell_lang = source_code if source_code in LIB_LANGS else ""
        moved = move_source(input_path, session.book_dir, quell_lang)
        if moved:
            final_source = moved
            print(f"[QUELLE] verschoben → {moved}")
        # bei konvertierten Formaten wandert das Original mit
        if original_source and original_source.exists():
            moved_orig = move_source(original_source, session.book_dir, quell_lang)
            if moved_orig:
                print(f"[QUELLE] Original verschoben → {moved_orig}")

    # ── meta.json aktualisieren (Pfad der Quelle, Status) ────────────────────
    schreibe_meta("fertig" if vollstaendig else "unvollstaendig", final_source)

    print(f"\n[LEKTOR] {session.book_dir}")
    for lang, _ in plan:
        print(f"         {lang}\\  {len(session.all_chunks_sorted(lang))} Chunk-Dateien")
    print(f"         Jetzt korrekturlesen (Schritt 2). Danach Schritt 3:")
    print(f'         python ebook-build.py "{session.book_dir}"')


if __name__ == "__main__":
    main()
