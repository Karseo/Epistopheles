#!/usr/bin/env python3
import os, re, time, json, urllib.request, urllib.parse

BASE = os.environ.get("EBOOK_BASE", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "rohdaten"))
FOLDER = os.path.join(BASE, "Inbox")
DRY_RUN = False
LOG = os.path.join(BASE, "isbn_rename.log")

log_f = open(LOG, "w", encoding="utf-8")

def log(msg=""):
    print(msg, flush=True)
    log_f.write(msg + "\n")
    log_f.flush()

def extract_isbn(filename):
    match = re.match(r'^(\d{9}[\dX]|\d{13})', filename, re.IGNORECASE)
    return match.group(1).upper() if match else None

def sanitize(name):
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:150]

def lookup_openlibrary(isbn):
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'APIC-ISBN-Renamer/1.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        key = f"ISBN:{isbn}"
        if key not in data:
            return None, None
        book = data[key]
        title = book.get('title', '').strip()
        authors = book.get('authors', [])
        author = authors[0].get('name', '').strip() if authors else ''
        return author or None, title or None
    except:
        return None, None

def lookup_google(isbn):
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}&maxResults=1"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'APIC-ISBN-Renamer/1.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        items = data.get('items', [])
        if not items:
            return None, None
        info = items[0].get('volumeInfo', {})
        title = info.get('title', '').strip()
        authors = info.get('authors', [])
        author = authors[0].strip() if authors else ''
        return author or None, title or None
    except:
        return None, None

def lookup(isbn):
    author, title = lookup_openlibrary(isbn)
    if title:
        return author, title, "OpenLib"
    time.sleep(0.3)
    author, title = lookup_google(isbn)
    if title:
        return author, title, "Google"
    return None, None, "NotFound"

def process():
    files = sorted(os.listdir(FOLDER))
    results, skipped, errors = [], [], []

    for fname in files:
        fpath = os.path.join(FOLDER, fname)
        if not os.path.isfile(fpath):
            continue
        stem, ext = os.path.splitext(fname)
        isbn = extract_isbn(stem)
        if not isbn:
            skipped.append(fname)
            continue

        log(f"Lookup: {isbn} | {fname}")
        author, title, source = lookup(isbn)
        time.sleep(0.3)

        if not title:
            errors.append((fname, isbn))
            continue

        new_stem = sanitize(f"{author} - {title}") if author else sanitize(title)
        new_name = new_stem + ext
        new_path = os.path.join(FOLDER, new_name)

        if new_path != fpath and os.path.exists(new_path):
            new_name = new_stem + f"_{isbn}" + ext
            new_path = os.path.join(FOLDER, new_name)

        results.append((fname, new_name, isbn, source))

    log("\n" + "="*70)
    log(f"{'DRY RUN' if DRY_RUN else 'UMBENENNUNG'}")
    log("="*70 + "\n")

    renamed = 0
    for old, new, isbn, source in results:
        if old == new:
            log(f"[GLEICH]     [{source}] {old}")
            continue
        if DRY_RUN:
            log(f"[UMBENENNEN] [{source}] {old}\n             -> {new}\n")
        else:
            try:
                os.rename(os.path.join(FOLDER, old), os.path.join(FOLDER, new))
                log(f"[OK] [{source}] {old}\n  -> {new}\n")
                renamed += 1
            except Exception as e:
                log(f"[FEHLER] {old} -> {e}\n")

    log(f"\nSkipped (kein ISBN): {len(skipped)}")
    for s in skipped:
        log(f"  {s}")
    log(f"\nNicht gefunden ({len(errors)}):")
    for fname, isbn in errors:
        log(f"  {isbn}: {fname}")
    log(f"\nGesamt: {len(results)} verarbeitet, {renamed} umbenannt, {len(skipped)} skip, {len(errors)} Fehler")
    log_f.close()

process()
