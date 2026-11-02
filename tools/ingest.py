#!/usr/bin/env python3
"""Python-Äquivalent von ingest.ps1.

Liest alle Buecher unter !Episto/reader/<Autor>/<Buch>/quelle/*.md,
zerlegt sie absatzweise in Chunks (250 Woerter), vektorisiert sie
via Ollama (mxbai-embed-large, 1024 dims) und schreibt sie in Qdrant.

Aufruf:
  python3 tools/ingest.py                          # alle Buecher (inkrementell)
  python3 tools/ingest.py --reset                  # Collection neu aufbauen
  python3 tools/ingest.py --buch "<Pfad zum Buch>" # nur ein Buch anhngen
  python3 tools/ingest.py --limit 5                # nur 5 Dateien pro Buch
  python3 tools/ingest.py --collection episto
  python tools/ingest.py --root "D:\\Workspace\\!Episto"   # unter Windows (Standard-Root ist der WSL-Pfad)

Chunks, die den Kontext des Embedding-Modells sprengen (mxbai-embed-large: 512
Tokens), werden NICHT mehr still abgeschnitten, sondern geteilt (siehe
embed_passend). Frueher fehlten so im Mittel ~19 % des Chunktexts im Vektor.
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.error

ROOT = "/mnt/d/Workspace/!Episto"
QDRANT = "http://127.0.0.1:6333"
OLLAMA_EMBED = "http://127.0.0.1:11434/api/embed"
EMBED_MODEL = "mxbai-embed-large"
DIM = 1024
WORDS_PER_CHUNK = 250
BATCH_SIZE = 16
VERSUCHE_EMBED = 5
RANGL = "\u203a"  # ›


def post_json(uri, obj, timeout=300, retries=3):
    body = json.dumps(obj).encode("utf-8")
    last_err = None
    for versuch in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                uri,
                data=body,
                method="POST",
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last_err = e
            if versuch < retries:
                warte = 5 * versuch
                print(f"  [RETRY {versuch}/{retries}] {uri} : {e} - warte {warte}s", flush=True)
                time.sleep(warte)
    raise last_err


def put_json(uri, obj, timeout=300, retries=3):
    body = json.dumps(obj).encode("utf-8")
    last_err = None
    for versuch in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                uri,
                data=body,
                method="PUT",
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last_err = e
            if versuch < retries:
                warte = 5 * versuch
                print(f"  [RETRY {versuch}/{retries}] {uri} : {e} - warte {warte}s", flush=True)
                time.sleep(warte)
    raise last_err


def get_json(uri, timeout=30):
    req = urllib.request.Request(uri, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ensure_collection(collection):
    try:
        get_json(f"{QDRANT}/collections/{collection}")
        print(f"Collection '{collection}' vorhanden.")
    except Exception:
        put_json(
            f"{QDRANT}/collections/{collection}",
            {"vectors": {"size": DIM, "distance": "Cosine"}},
            timeout=30,
            retries=2,
        )
        print(f"Collection '{collection}' erstellt (dim={DIM}, cosine).")


def delete_collection(collection):
    try:
        req = urllib.request.Request(f"{QDRANT}/collections/{collection}", method="DELETE")
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except Exception:
        pass


def split_chunks(text):
    paras = [p.strip() for p in re.split(r"\r?\n\r?\n", text)]
    paras = [p for p in paras if p]
    chunks = []
    cur = []
    cur_words = 0
    for p in paras:
        w = len([x for x in p.split() if x])
        if cur_words > 0 and (cur_words + w) > WORDS_PER_CHUNK:
            chunks.append("\n\n".join(cur))
            cur = []
            cur_words = 0
        cur.append(p)
        cur_words += w
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


class ZuLang(Exception):
    """Ollama lehnt eine Eingabe ab, weil sie den Kontext des Modells uebersteigt."""


def embed(texte):
    """Vektoren fuer eine Liste von Texten. truncate=false: Ollama kuerzt sonst
    STILL auf den Kontext des Modells (512 Tokens), der Rest des Chunks fehlte dann
    im Vektor, ohne dass es auffiel. Zu lange Eingaben ergeben ZuLang."""
    body = json.dumps({"model": EMBED_MODEL, "input": texte, "truncate": False}).encode("utf-8")
    last_err = None
    for versuch in range(1, VERSUCHE_EMBED + 1):
        try:
            req = urllib.request.Request(
                OLLAMA_EMBED, data=body, method="POST",
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode("utf-8"))["embeddings"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            if e.code == 400 and "exceeds the context length" in detail:
                raise ZuLang(detail) from None
            last_err = e
        except Exception as e:  # noqa: BLE001  (Netz, Timeout)
            last_err = e
        if versuch < VERSUCHE_EMBED:
            # Unter Dauerlast meldet Ollama vereinzelte Verbindungsfehler zwischen Server und
            # Runner ("connectex ... Socketadresse nur einmal verwendet") faelschlich als
            # HTTP 400. Ein erneuter Versuch klappt sofort; deshalb kurze Wartezeiten.
            warte = 2 * versuch
            print(f"  [RETRY {versuch}/{VERSUCHE_EMBED}] {OLLAMA_EMBED} : {last_err} - warte {warte}s", flush=True)
            time.sleep(warte)
    raise last_err


def halbiere(text):
    """Teilt einen Text nahe der Mitte: bevorzugt am Absatz-, dann am Satz-, dann am
    Wortende; als letzter Ausweg mitten im Text. Gibt zwei nicht leere Teile zurueck
    oder None, wenn der Text nicht weiter teilbar ist."""
    for muster in (r"\n\n+", r"(?<=[.!?\u2026])\s+", r"\s+"):
        stellen = list(re.finditer(muster, text))
        if not stellen:
            continue
        mitte = len(text) / 2
        m = min(stellen, key=lambda s: abs((s.start() + s.end()) / 2 - mitte))
        a, b = text[: m.start()].strip(), text[m.end():].strip()
        if a and b:
            return [a, b]
    if len(text) >= 2:
        return [text[: len(text) // 2], text[len(text) // 2:]]
    return None


def embed_passend(chunks):
    """Embeddet Chunks und gibt (text, vektor)-Paare in Reihenfolge zurueck. Chunks,
    die den Kontext sprengen, werden geteilt, bis sie passen (die Ergebnisliste kann
    also laenger sein als die Eingabe). Es geht kein Text verloren."""
    try:
        return list(zip(chunks, embed(chunks)))
    except ZuLang:
        if len(chunks) > 1:
            mitte = len(chunks) // 2
            return embed_passend(chunks[:mitte]) + embed_passend(chunks[mitte:])
        teile = halbiere(chunks[0])
        if teile is None:
            raise
        return embed_passend(teile)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", default="episto")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--buch", default="")
    ap.add_argument("--root", default="", help="Wurzelordner der Bibliothek (Standard: ROOT, der WSL-Pfad)")
    args = ap.parse_args()

    if args.reset:
        delete_collection(args.collection)
    ensure_collection(args.collection)

    import os

    books = []
    autor_root = os.path.join(args.root or ROOT, "reader")
    for autor in sorted(os.listdir(autor_root)):
        autor_dir = os.path.join(autor_root, autor)
        if not os.path.isdir(autor_dir):
            continue
        for buch in sorted(os.listdir(autor_dir)):
            buch_dir = os.path.join(autor_dir, buch)
            if not os.path.isdir(buch_dir):
                continue
            if args.buch and os.path.normpath(buch_dir) != os.path.normpath(args.buch):
                continue
            quelle_dir = os.path.join(buch_dir, "quelle")
            if not os.path.isdir(quelle_dir):
                continue
            meta = None
            kap = None
            meta_path = os.path.join(buch_dir, "meta.json")
            kap_path = os.path.join(buch_dir, "kapitel.json")
            if os.path.isfile(meta_path):
                with open(meta_path, encoding="utf-8") as fh:
                    meta = json.load(fh)
            if os.path.isfile(kap_path):
                with open(kap_path, encoding="utf-8") as fh:
                    kap = json.load(fh)
            books.append(
                {
                    "Autor": autor,
                    "Buch": buch,
                    "Quelle": quelle_dir,
                    "Meta": meta,
                    "Kapitel": kap,
                }
            )
    print(f"Buecher gefunden: {len(books)}")

    next_id = 0
    if not args.reset:
        try:
            col_info = get_json(f"{QDRANT}/collections/{args.collection}")
            next_id = int(col_info["result"]["points_count"])
            print(f"Inkrementell: Punkt-IDs ab {next_id} fortsetzen (bestehende Punkte bleiben unangetastet).")
        except Exception:
            print("  [WARN] points_count nicht lesbar - starte bei 0 (nur bei leerer Collection sicher).")

    total_chunks = 0
    geteilt = 0  # Chunks, die fuer den Kontext des Embedding-Modells geteilt werden mussten
    for b in books:
        pfad_by_nr = {}
        if b["Kapitel"] and "zuordnung" in b["Kapitel"]:
            for z in b["Kapitel"]["zuordnung"]:
                pfad_by_nr[str(z["nr"])] = (RANGL + " ").join(z.get("pfad", []))
        files = sorted(
            f
            for f in os.listdir(b["Quelle"])
            if f.endswith(".md") and not f.startswith("_") and f != "README.md"
        )
        if args.limit > 0:
            files = files[: args.limit]
        print(f"Buch: {b['Autor']} / {b['Buch']}  ({len(files)} Kapitel)")

        for f in files:
            m = re.match(r"^(\d+)", f)
            nr = int(m.group(1)) if m else 0
            with open(os.path.join(b["Quelle"], f), encoding="utf-8") as fh:
                text = fh.read()
            chunks = split_chunks(text)
            abschnitt = pfad_by_nr.get(str(nr), "")

            idx = 0
            for i in range(0, len(chunks), BATCH_SIZE):
                batch = chunks[i : i + BATCH_SIZE]
                paare = embed_passend(batch)
                geteilt += len(paare) - len(batch)
                points = []
                for c, vektor in paare:
                    points.append(
                        {
                            "id": next_id,
                            "vector": vektor,
                            "payload": {
                                "buch": b["Buch"],
                                "autor": b["Autor"],
                                "datei": f,
                                "kapitel_nr": nr,
                                "abschnitt": abschnitt,
                                "chunk_idx": idx,
                                "text": c,
                            },
                        }
                    )
                    next_id += 1
                    idx += 1
                put_json(f"{QDRANT}/collections/{args.collection}/points?wait=true", {"points": points}, timeout=120)
            total_chunks += idx

    print(f"Fertig. Punkte gesamt: {next_id}  (Chunks: {total_chunks}, davon durch Teilen zusaetzlich: {geteilt})  "
          f"Collection: {args.collection}")


if __name__ == "__main__":
    main()
