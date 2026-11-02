#!/usr/bin/env python3
"""OCR-Scan -> EPISTO-Brücke (wiederverwendbarer OCR-Baustein).

Übernimmt einen OCR-gescannten Buchtext, der als eine Textdatei je Seite
(NNNNNNNN.txt, UTF-8) vorliegt, und überführt ihn in das Episto-Schema:

  1. Seiten zusammenführen und vorverarbeiten:
     - Seitenzahlen (arabisch + römisch) und Kolumnentitel (laufende Titel)
       entfernen
     - Fußnoten (Zeilen "^N)" bzw. "^N)" mit Hochzahl ¹²³) vom Fließtext trennen
     - harte Zeilenumbrüche (kurze Zeile = Absatzende) zu Absätzen zusammenziehen
     - Silbentrennung über den Zeilenumbruch auflösen ("be- saßen" -> "besaßen")
  2. Kapitelgrenzen aus einer Kapitelliste (start/end = Seitendatei-Indizes)
  3. OCR-Fehler per LLM (aya-expanse:32b) korrigieren — optional, --skip-ocr
     deaktiviert das. Der Prompt bewahrt bewusst den altertümlichen Stil.
  4. Episto-Struktur schreiben: quelle/NNNN_slug.md + kapitel.json + meta.json

Die Fußnoten werden je Kapitel als Endnoten angehängt (Abschnitt "## Anmerkungen").

Was dieses Skript NICHT tut (nächste Schritte, wie bei lektor-zu-episto.py):
  - notizen/tags.json kapitelweise erzeugen        -> tools\\taggen.ps1
  - notizen/strang_taxonomie.json kuratieren       -> manuell
  - notizen/straenge/ aggregieren                  -> tools\\straenge.ps1
  - Qdrant-Ingest                                  -> ingest.ps1

Aufruf:
  python tools/ocr-zu-episto.py \
      --seiten "d:\\Workspace\\Buch\\Seiten" \
      --autor "Michels, Robert" \
      --titel "Zur Soziologie des Parteiwesens" \
      --kapitel "kapitel.json" \
      --episto "D:\\Workspace\\!Episto\\reader"

Kapitelliste (--kapitel, JSON): Liste von {start, end, titel, teil}. start/end
sind die Seitendatei-Indizes (Datei 00000001.txt = 1). "teil" ist optional und
steuert die Gruppierung in der Gliederung (z.B. "Teil I · A"). Seiten außerhalb
der Kapitelliste (Titelseiten, Inhaltsverzeichnis) werden automatisch verworfen.

Weitere Optionen: --limit N (nur die ersten N Kapitel), --skip-ocr,
--model <name>, --wrap-breite N (Zeilenlängen-Schwelle, Standard 50).
"""
import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.request
from collections import Counter

OLLAMA = "http://127.0.0.1:11434/api/generate"
DEFAULT_MODEL = "aya-expanse:32b"

SYSTEM_PROMPT = (
    "Du bist ein Korrektor für OCR-gescannten deutschen Text (ein Buch von 1911). "
    "Korrigiere ausschließlich OFFENSICHTLICHE OCR-Fehler: falsch erkannte Zeichen "
    "(z.B. '1' statt 'l', 'rn' statt 'm', griechische Buchstaben statt Ziffern), "
    "verlorene Satzzeichen, fehlerhafte Silbentrennung und fälschlich getrennte/verbundene Wörter. "
    "BEWAHRE den originalen, teils altertümlichen Sprachstil UNVERÄNDERT — modernisiere oder "
    "formuliere NICHT um, ersetze keine Wörter durch Synonyme. Wenn du unsicher bist, ob etwas "
    "ein OCR-Fehler ist, lasse es unverändert. Behalte die Absätze bei. "
    "Gib NUR den korrigierten Text zurück — ohne Kommentar, ohne Markdown."
)


# ── Seiten lesen & vorverarbeiten ─────────────────────────────────────────────

def lese_seiten(verzeichnis):
    """Liest alle NNNNNNNN.txt-Seitendateien in numerischer Reihenfolge."""
    alle = glob.glob(os.path.join(verzeichnis, "*.txt"))
    dateien = sorted([f for f in alle if re.fullmatch(r".*\d{8}\.txt", f)],
                     key=lambda f: int(re.search(r"(\d+)", f).group(1)))
    seiten = []
    for f in dateien:
        idx = int(re.search(r"(\d+)", f).group(1))
        seiten.append((idx, open(f, encoding="utf-8").read().splitlines()))
    return seiten


def normalisiere_ziffern(s):
    """OCR-/Unicode-Varianten von Ziffern auf ASCII-Ziffern mappen (Hoch-/Tiefzahl, I->1, O->0, l->1)."""
    hoch, tief = "⁰¹²³⁴⁵⁶⁷⁸⁹", "₀₁₂₃₄₅₆₇₈₉"
    for i, (h, t) in enumerate(zip(hoch, tief)):
        s = s.replace(h, str(i)).replace(t, str(i))
    return s.replace("I", "1").replace("O", "0").replace("l", "1")


def ist_seitenzahl(z):
    s = normalisiere_ziffern(z.strip())
    if re.fullmatch(r"\d{1,4}", s):
        return True
    # römische Seitenzahl (Front Matter: VI, XXIV, XXXV …)
    if re.fullmatch(r"[IVXLCDM]{1,8}", z.strip(), re.I):
        return True
    return False


def ist_fussnoten_start(z):
    return re.match(r"^\d{1,2}\)", normalisiere_ziffern(z.strip())) is not None


def baue_kolumnentitel(seiten, min_wdh=2):
    """Sammelt kurze, wiederholte Zeilen (laufende Kolumnentitel) als Menge."""
    c = Counter()
    for _, zeilen in seiten:
        seen = set()
        for l in zeilen:
            s = " ".join(l.split())
            if (s and 6 <= len(s) < 70 and re.search(r"[A-Za-zÄÖÜäöüß]{2}", s)
                    and not ist_seitenzahl(s) and not ist_fussnoten_start(s)):
                if s not in seen:
                    c[s] += 1
                    seen.add(s)
    return {k for k, v in c.items() if v >= min_wdh}


def verarbeite_seite(n, zeilen, kolumnentitel):
    """Liefert (koerper_zeilen, fussnoten_zeilen) einer Seite.

    Entfernt Seitenzahl + Kolumnentitel aus dem Seitenkopf (in beliebiger
    Reihenfolge — das Layout wechselt zwischen linken/rechten Seiten) und trennt
    den Fließtext von den Fußnoten (ab der ersten "^N)"-Zeile)."""
    i = 0
    while i < len(zeilen) and not zeilen[i].strip():
        i += 1
    for _ in range(4):
        if i < len(zeilen):
            s = zeilen[i].strip()
            if ist_seitenzahl(s) or s in kolumnentitel or (len(s) <= 2 and not s.isalnum()):
                i += 1
                continue
        break
    koerper, fussnoten, in_fn = [], [], False
    for z in zeilen[i:]:
        if ist_fussnoten_start(z.strip()):
            in_fn = True
        (fussnoten if in_fn else koerper).append(z)
    return koerper, fussnoten


def zeilen_zu_absaetzen(zeilen, wrap_breite=50):
    """Harte Zeilenumbrüche zu Absätzen zusammenziehen (kurze Zeile = Absatzende)."""
    absaetze, aktuell = [], []
    for z in zeilen:
        s = z.rstrip()
        if not s.strip():
            if aktuell:
                absaetze.append(" ".join(aktuell)); aktuell = []
            continue
        ende_hyphen = s.strip().endswith("-") and not s.strip().endswith("--")
        if aktuell and (len(s) >= wrap_breite or ende_hyphen):
            aktuell.append(s.strip())
        else:
            if aktuell:
                absaetze.append(" ".join(aktuell)); aktuell = []
            aktuell.append(s.strip())
    if aktuell:
        absaetze.append(" ".join(aktuell))
    return absaetze


def hyphens_aufloesen(text):
    """Silbentrennung über den Zeilenumbruch auflösen: 'be- saßen' -> 'besaßen'."""
    return re.sub(r"(\w)- (\w)", r"\1\2", text)


# ── OCR-Korrektur per LLM ─────────────────────────────────────────────────────

def korrigiere(text, model, ollama=OLLAMA, num_ctx=32768):
    prompt = SYSTEM_PROMPT + "\n\nTEXT:\n" + text
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.1, "num_ctx": num_ctx}}).encode("utf-8")
    req = urllib.request.Request(ollama, data=body, headers={"Content-Type": "application/json"})
    for v in range(3):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=600).read()).get("response", "").strip()
        except Exception:
            if v == 2:
                raise
            time.sleep(5 * (v + 1))


def chunk_absaetze(absaetze, max_chars=7000):
    chunks, cur, n = [], [], 0
    for a in absaetze:
        if cur and n + len(a) > max_chars:
            chunks.append("\n\n".join(cur)); cur, n = [], 0
        cur.append(a); n += len(a)
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def slugify(text):
    return re.sub(r"[^a-z0-9äöüß]+", "-", text.lower()).strip("-")


# ── Hauptablauf ───────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(description="OCR-Scan -> EPISTO-Brücke")
    ap.add_argument("--seiten", required=True, help="Verzeichnis mit NNNNNNNN.txt-Seitendateien")
    ap.add_argument("--autor", required=True)
    ap.add_argument("--titel", required=True)
    ap.add_argument("--kapitel", required=True, help="JSON mit [{start,end,titel,teil}, …]")
    ap.add_argument("--episto", default=r"D:\Workspace\!Episto\reader")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--skip-ocr", action="store_true")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--wrap-breite", type=int, default=50)
    ap.add_argument("--titel-voll", default="")
    ap.add_argument("--jahr", default="")
    args = ap.parse_args(argv)

    seiten = lese_seiten(args.seiten)
    kolumnen = baue_kolumnentitel(seiten)
    kapitel = json.load(open(args.kapitel, encoding="utf-8"))
    if args.limit:
        kapitel = kapitel[:args.limit]

    ziel = os.path.join(args.episto, args.autor, args.titel)
    quelle = os.path.join(ziel, "quelle")
    os.makedirs(quelle, exist_ok=True)

    gliederung, zuordnung, index = [], [], []
    for i, k in enumerate(kapitel, 1):
        start, end, titel = k["start"], k["end"], k["titel"]
        teil = k.get("teil", "")
        zeilen, fn = [], []
        for n, z in seiten:
            if start <= n <= end:
                kz, fz = verarbeite_seite(n, z, kolumnen)
                zeilen.extend(kz)
                if fz:
                    fn.append((n, fz))
        absaetze = [hyphens_aufloesen(a) for a in zeilen_zu_absaetzen(zeilen, args.wrap_breite)]
        absaetze = [a for a in absaetze if re.search(r"[A-Za-zÄÖÜäöüß0-9]", a)]
        print(f"[{i}/{len(kapitel)}] {titel} ({len(absaetze)} Abs., {len(fn)} Seiten m. Fußn.)", flush=True)

        text = "\n\n".join(absaetze)
        if not args.skip_ocr:
            text = "\n\n".join(korrigiere(c, args.model) for c in chunk_absaetze(absaetze))
        if fn:
            text += "\n\n## Anmerkungen\n\n"
            for n, f in fn:
                text += "\n".join(x.strip() for x in f) + "\n\n"

        slug = slugify(titel)
        dateiname = f"{i:04d}_{slug}.md"
        with open(os.path.join(quelle, dateiname), "w", encoding="utf-8") as fh:
            fh.write(text)

        gliederung.append({"id": slug, "nr": str(i), "titel": titel, "kinder": []})
        pfad = [teil, titel] if teil else [titel]
        zuordnung.append({"nr": i, "datei": dateiname, "abschnitt": slug, "pfad": pfad})
        index.append({"nr": i, "titel": titel, "datei": dateiname})

    json.dump({"werk": args.titel, "quelle": "ocr", "gliederung": gliederung, "zuordnung": zuordnung},
              open(os.path.join(ziel, "kapitel.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(index, open(os.path.join(quelle, "_kapitel_index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    meta = {"titel": args.titel, "autor": args.autor, "jahr": args.jahr,
            "titel_voll": args.titel_voll or args.titel, "autor_voll": args.autor,
            "quellsprache": "de", "sprachen": ["de"], "quelle_kapitel": len(kapitel),
            "quelle_status": "ocr_bereinigt" if not args.skip_ocr else "ocr_vorverarbeitet"}
    json.dump(meta, open(os.path.join(ziel, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"-> {len(kapitel)} Kapitel nach {ziel}")


if __name__ == "__main__":
    main()
