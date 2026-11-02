"""
suggest-structure.py  —  Kapitelgrenzen per lokalem LLM erkennen, wo Anker und
                          Ueberschriften-Fallback nichts Brauchbares liefern

ERSTER ANSATZ (verworfen, s. Git-Historie/Chatverlauf): das Modell chunkweise
fragen, ob GENAU HIER eine Gliederungsgrenze beginnt. Live getestet an
"Capitalism, Socialism and Democracy" (175 Chunks, ~85 echte Kapitelmarken
laut Inhaltsverzeichnis): nur 5 gefunden, mit erfundenen Nummern (16, 18 fuer
die ersten beiden Kapitel), riesige unentdeckte Luecken (102 Chunks am Stueck
ohne jede Grenze). Isoliert je Chunk gefragt ist die Trefferquote auf einem
dicht gegliederten Buch mit mehreren Teilen zu niedrig — das Modell uebersieht
die meisten Grenzen, statt bei Unsicherheit lieber zu viele zu melden.

ZWEITER ANSATZ (dieser): nicht raten lassen, WO eine Grenze ist, sondern
das, was jedes Buch bereits selbst verraet, auswerten — das gedruckte
Inhaltsverzeichnis. Das Modell liest nur die ersten Chunks (dort steht das
Inhaltsverzeichnis) und extrahiert daraus die VOLLSTAENDIGE Liste aller
Gliederungspunkte mit Nummer/Titel/Art. Die eigentliche Platzierung im Buch
uebernimmt danach reine Textsuche (kein LLM mehr): jeder Titel wird der
Reihe nach im Rohtext gesucht, beginnend NACH dem Textfenster, das dem
Modell fuers Inhaltsverzeichnis vorlag — alles davor ist per Definition das
gedruckte Inhaltsverzeichnis selbst, kein echter Kapitelanfang. (Ein
selbst-entdeckender erster Suchdurchgang, der das TOC-Ende an der
Cursorposition erraten sollte, erwies sich als bruechig: TOC-Zeilen mit
angehaengtem Untertitel bestehen die Isolations-Praeferenz in
suche_titel() manchmal nicht und die Suche lief dadurch schon im ersten
Durchgang unkontrolliert weit ins Buch hinein — erlebt an "Capitalism,
Socialism and Democracy", wo der Cursor nach dem zweiten Titel bereits bei
Kapitel V stand. Der feste Fensteroffset aus lade_toc_text() ist robuster.)
Titel, die dort nicht wiedergefunden werden (z.B. weil das Buch die
Ueberschrift im Fliesstext nicht wiederholt), bleiben ohne Position — es
wird nichts geraten, nur was die Suche tatsaechlich findet, landet in
kapitel.json. Das macht aus "in jedem einzelnen Chunk pruefen" ein "einmal
lesen, dann exakt wiederfinden" — strukturell zuverlaessiger, weil die
Vollstaendigkeit vom Buch selbst (seinem Inhaltsverzeichnis) kommt statt vom
Modell erfunden werden muss.

Qualitaetsgrenzen, damit ein Buch mit zu wenig Treffern nicht als brauchbare
Struktur durchgeht: --min-recall (Anteil der TOC-Eintraege, die tatsaechlich
wiedergefunden wurden, Standard 0.5) und --max-anteil (Obergrenze wie beim
Ueberschriften-Fallback in detect-chapters.py, gegen ein missratenes/zu
langes Inhaltsverzeichnis).

Ausgabe wie beim Anker-/Ueberschriften-Weg: <Buch>\\kapitel.json, aber mit
"quelle": "llm-toc" — durchlaeuft dieselbe struktur_aus_marken()-Funktion aus
detect-chapters.py und ist fuer build-chapters.py/kapitel_lookup.py nicht zu
unterscheiden.

Zusaetzlich, unabhaengig von der Gliederung: eine Textprobe geht an das
Modell mit der Bitte, die Fussnoten-Konvention des Buchs in eigenen Worten zu
beschreiben (s. diagnose_fussnoten). Rein diagnostisch, in
'hinweise-fussnoten.txt' — keine automatische Aenderung.

Verwendung:
  python suggest-structure.py "Schumpeter, Joseph A\\Capitalism, Socialism and Democracy"
  python suggest-structure.py "<Autor>\\<Titel>" --sprache en
  python suggest-structure.py "<Buch>" --dry-run
  python suggest-structure.py --alle
      # nur Buecher, deren kapitel.json (noch) keine Kapitel enthaelt
  python suggest-structure.py --alle --force
      # auch Buecher mit bereits brauchbarer Struktur neu erkennen lassen
"""

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import requests


def _lade_detect():
    """detect-chapters.py als Modul laden — struktur_aus_marken() und
    chunk_liste() sollen nur an einer Stelle implementiert sein."""
    pfad = Path(__file__).parent / "detect-chapters.py"
    spec = importlib.util.spec_from_file_location("detect_chapters", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul

_dc = _lade_detect()

BASE   = Path(os.environ.get("EBOOK_BASE", Path(__file__).resolve().parents[2] / "rohdaten"))
LEKTOR = BASE / "Lektor"
OLLAMA = "http://localhost:11434"
MODELL = "qwen3.8:27b"          # Analyse, nicht Uebersetzung — wie suggest-tags.py

# Obergrenze wie beim Ueberschriften-Fallback in detect-chapters.py: hoechstens
# so viele Kapitel wie Chunks mal diesem Faktor — Schutz gegen ein verunglueckt
# ausgelesenes/zu langes Inhaltsverzeichnis.
MAX_ANTEIL = 0.5
# Untergrenze: mindestens so viel Anteil der Inhaltsverzeichnis-Eintraege
# muss im Fliesstext tatsaechlich wiedergefunden werden, sonst ist die
# Struktur zu luekenhaft, um sie kapitel.json anzuvertrauen (s. Docstring:
# der erste Ansatz scheiterte genau daran, ohne dass eine Sperre das
# aufgefangen haette).
MIN_RECALL = 0.5
# Wie viele Zeichen vom Buchanfang dem Modell fuers Inhaltsverzeichnis
# vorgelegt werden — genug fuer ein mehrseitiges TOC, aber innerhalb von
# num_ctx=16384 Tokens (grob 4-5 Zeichen/Token bei deutschem Text).
TOC_MAX_CHARS = 12000
TOC_MAX_CHUNKS = 6

TOC_PROMPT = """Im folgenden Text steht der Anfang eines eBooks, darin das gedruckte Inhaltsverzeichnis (moeglicherweise mit Seitenzahlen, Fuehrungspunkten, mehreren Teilen).

Extrahiere daraus ALLE Eintraege, die eine Gliederungsebene des Buchtexts markieren — echte, gezaehlte Kapitel ebenso wie Titelei/Anhang (Vorwort, Einleitung, Prolog, Teile, Anhang, Register, Bibliographie, Danksagung, Nachwort, Index usw.).

Gib je Eintrag GENAU EINE Zeile aus, in der Reihenfolge des Inhaltsverzeichnisses:

<Nummer oder leer>|<art>|<Titel>

<art> ist genau eines von:
  kapitel   = echtes, gezaehltes Kapitel
  vorspann  = Titelei/Anhang ohne eigene Kapitelzaehlung (s.o.), Teile mit eingeschlossen

WICHTIG — nur die OBERSTE Gliederungsebene: manche Bücher nummerieren
Unterabschnitte innerhalb eines Kapitels erneut mit I., II., III. usw. Nimm
NUR die Ebene, deren Nummerierung fortlaufend über das GANZE Buch ansteigt
(z.B. I, II, III, ... bis XXVIII). Beginnt eine Nummerierung nach einem
hohen Wert wieder bei I. oder 1. neu, ist das eine TIEFERE Ebene innerhalb
des vorherigen Eintrags — die NICHT mit aufnehmen.

Bei "Teil"/"Part"-Eintraegen gib als <Titel> NUR "Teil <Nummer>" (bzw.
"Part <Nummer>") aus, OHNE angehängten Untertitel — der wird oft im
Fliesstext etwas anders formuliert als im Inhaltsverzeichnis und würde die
spätere Suche im Rohtext unnötig erschweren.

<Titel> sonst genau wie im Inhaltsverzeichnis geschrieben, OHNE Seitenzahl
und ohne Fuehrungspunkte, aber sonst wortwoertlich (wird spaeter im
Fliesstext gesucht). Ignoriere reine Layout-Zeilen (z.B. "INHALT" als
Ueberschrift des Verzeichnisses selbst) und Verzeichnisse von
Abbildungen/Tabellen, falls vorhanden — nur Gliederungspunkte des Buchtexts
selbst.

WICHTIG — Nummer NIEMALS auch im Titel wiederholen, auch nicht als
Praefix: die Nummer steht NUR im ersten Feld. Steht im Inhaltsverzeichnis
z.B. "III. Marx der Ökonom", ist die richtige Ausgabe:
  III|kapitel|Marx der Ökonom
NICHT "III|kapitel|III. Marx der Ökonom" und NICHT "III|kapitel|. Marx der
Ökonom" — der Titel beginnt direkt mit dem ersten Buchstaben des eigentlichen
Titelworts, ohne Nummer, ohne Punkt, ohne fuehrendes Leerzeichen.

Ist im Text kein Inhaltsverzeichnis erkennbar, antworte NUR mit:
keine

Keine Erklaerungen, keine weiteren Zeilen, kein Markdown drumherum.

Text:

{text}"""

FUSSNOTEN_PROMPT = """Im folgenden Textauszug eines eBooks (Pandoc-Konvertierung, Markdown): kommen Fussnoten oder Endnoten vor?

Falls ja: beschreibe in 1-3 knappen Saetzen, WIE sie im Rohtext markiert sind — z.B. hochgestellte Zahl mit Link auf eine Fussnote am Kapitelende, Klammerverweis im Fliesstext, Fussnotentext steht direkt im Fliesstext vor der naechsten Ueberschrift, oder der Verweis existiert, aber der Fussnotentext fehlt im Rohtext ganz (muesste aus dem Quell-EPUB nachgezogen werden). Zitiere zur Veranschaulichung eine kurze Beispielstelle wortwoertlich.

Falls keine Fussnoten oder Endnoten vorkommen, antworte NUR mit: keine

Text:

{text}"""

TOC_ZEILE = re.compile(
    r'^\s*([IVXLCDM0-9]*)\s*\|\s*(kapitel|vorspann)\s*\|\s*(.+?)\s*$', re.I)

# Sicherheitsnetz gegen den Prompt-Hinweis "Nummer nur im ersten Feld,
# nicht im Titel wiederholen" — Modelle befolgen so etwas nicht immer
# zuverlaessig (erlebt: "I. Marx der Prophet" statt "I" + "Marx der
# Prophet"; als EIN String durchsucht findet suche_titel() das nirgends,
# weil "KAPITEL I" und "MARX DER PROPHET" im Fliesstext getrennte Zeilen
# sind). Entfernt eine im Titel wiederholte roemische/arabische Nummer.
_FUEHRENDE_NUMMER = re.compile(r'^\(?[IVXLCDM]{1,6}\)?[.:]?\s+|^\(?\d{1,3}\)?[.:]?\s+', re.I)


def saeubere_titel(nr: str, titel: str) -> str:
    bereinigt = titel
    if nr:
        m = re.match(r'^\(?' + re.escape(nr) + r'\)?[.:]?\s+', bereinigt, re.I)
        if m:
            bereinigt = bereinigt[m.end():]
    m2 = _FUEHRENDE_NUMMER.match(bereinigt)
    if m2:
        bereinigt = bereinigt[m2.end():]
    bereinigt = bereinigt.strip()
    return bereinigt or titel


def _ollama_call(prompt: str, modell: str, ollama: str, timeout: int) -> str:
    r = requests.post(f"{ollama}/api/generate", json={
        "model": modell,
        "prompt": prompt,
        "stream": False,
        # num_ctx explizit: sonst schneidet Ollama still ab (s. suggest-tags.py)
        "options": {"temperature": 0.0, "num_ctx": 16384},
    }, timeout=timeout)
    r.raise_for_status()
    antwort = r.json().get("response", "")
    return re.sub(r'<think>.*?</think>', '', antwort, flags=re.S | re.I).strip()


def frage_toc(text: str, modell: str, ollama: str, timeout: int = 300) -> list[dict]:
    """Liefert [{nr, art, titel}, ...] aus dem Inhaltsverzeichnis-Textausschnitt."""
    antwort = _ollama_call(TOC_PROMPT.format(text=text), modell, ollama, timeout)
    if not antwort or antwort.lower().startswith("keine"):
        return []
    eintraege = []
    for zeile in antwort.splitlines():
        m = TOC_ZEILE.match(zeile.strip())
        if not m:
            continue
        nr, art, titel = m.groups()
        nr = nr.strip()
        titel = saeubere_titel(nr, titel.strip())
        if len(titel) < 2:
            continue
        eintraege.append({"nr": nr, "art": art.lower(), "titel": titel})
    return eintraege


# Mehrere Zeilen, die mit einer kleinen Zahl beginnen und danach echten Text
# tragen — das Muster eines gesammelten Fussnoten-/Anmerkungsblocks
# ("1 Fritz Machlup, ...", "2 Joseph A. Schumpeter, ...").
# [ \t]+ statt \s+: \s schliesst Zeilenumbrueche ein, dadurch spannte das
# Muster ueber eine Leerzeile hinweg eine nackte Seitenzahl UND die naechste
# Zeile zu einem einzigen "Treffer" zusammen (z.B. "131\n\nI. Die
# Obsoleszenz ...") — genau das TOC-Muster, das ausgeschlossen werden soll,
# ist so faelschlich selbst durchgerutscht. Mit [ \t]+ bleibt der Treffer
# auf einer Zeile, wie das (?m)^...$ eigentlich vorgibt.
_FUSSNOTEN_DEF_ZEILE = re.compile(r'(?m)^\d{1,3}[ \t]+\S.{20,}$')
# Unterscheidet eine echte Fussnoten-Definition von einem strukturell
# identisch aussehenden Inhaltsverzeichnis-Eintrag ("1. Umverteilung des
# Einkommens durch Besteuerung"): im TOC folgt direkt danach nur eine nackte
# Seitenzahl, bei einer echten Fussnote geht es mit Fliesstext weiter.
_NUR_SEITENZAHL_DANACH = re.compile(r'\A\s*\d{1,4}\s*(?:\n|\Z)')


def echte_fussnotenzeile(text: str, treffer: re.Match) -> bool:
    return not _NUR_SEITENZAHL_DANACH.match(text[treffer.end():treffer.end() + 30])


def finde_fussnoten_probe(d: Path, max_chunks: int = 20) -> str:
    """
    Sucht unter den ersten `max_chunks` Chunks gezielt einen, der wie ein
    gesammelter Fussnoten-/Anmerkungsblock aussieht, statt blind die ersten
    beiden Chunks zu nehmen. Erlebt an "Capitalism, Socialism and
    Democracy": chunk_001/002 zeigen nur die Verweismarker im Fliesstext,
    die zugehoerigen Definitionen folgen erst am Ende des Vorworts unter
    einer eigenen "ANMERKUNGEN"-Ueberschrift (chunk_005) — eine Probe aus
    den ersten beiden Chunks allein fuehrte deshalb zur falschen Diagnose
    "Fussnotentext fehlt im Rohtext ganz", obwohl er da war, nur nicht in
    der Probe. (Die erste Fassung dieser Suche traf dabei prompt das
    Inhaltsverzeichnis selbst — dessen nummerierte Unterpunkte sehen genauso
    aus wie Fussnoten-Definitionen; echte_fussnotenzeile() filtert das raus.)
    Wird kein Block gefunden, faellt die Funktion auf die urspruengliche
    Heuristik zurueck (erste beiden Chunks mit Inhalt).
    """
    dateien = sorted(
        (f for f in d.glob("chunk_*.md") if not f.name.endswith(".tagged.md")),
        key=lambda f: int(re.search(r'chunk_(\d+)', f.name).group(1)))[:max_chunks]
    texte = [f.read_text(encoding='utf-8', errors='replace') for f in dateien]
    for i, t in enumerate(texte):
        treffer = [m for m in _FUSSNOTEN_DEF_ZEILE.finditer(t) if echte_fussnotenzeile(t, m)]
        if len(treffer) >= 3:
            # den vorigen Chunk mit aufnehmen — dort steht meist der
            # Verweis im Fliesstext, der zu diesen Definitionen gehoert
            vorher = texte[i - 1] if i > 0 else ""
            return (vorher + "\n\n" + t)[-6000:]
    return "\n\n".join(texte[1:3])[:6000]


def diagnose_fussnoten(d: Path, modell: str, ollama: str,
                       timeout: int = 180) -> str:
    """
    Eine gezielt gewaehlte Textprobe (s. finde_fussnoten_probe) dem Modell
    zur Fussnoten-Konvention vorlegen. Rein diagnostisch — der Text wird
    nirgends automatisch anhand dieser Antwort veraendert (s. Docstring).
    """
    probe = finde_fussnoten_probe(d)
    if not probe.strip():
        return ""
    try:
        antwort = _ollama_call(FUSSNOTEN_PROMPT.format(text=probe),
                               modell, ollama, timeout)
    except Exception as e:
        return f"[nicht ermittelt: {e}]"
    if not antwort or antwort.lower().startswith("keine"):
        return ""
    return antwort


def lade_toc_text(d: Path, max_chunks: int, max_chars: int) -> str:
    """Text der ersten Chunks bis zur Zeichen-/Chunkgrenze — dort steht
    das gedruckte Inhaltsverzeichnis."""
    dateien = sorted(
        (f for f in d.glob("chunk_*.md") if not f.name.endswith(".tagged.md")),
        key=lambda f: int(re.search(r'chunk_(\d+)', f.name).group(1)))[:max_chunks]
    stuecke, laenge = [], 0
    for f in dateien:
        text = f.read_text(encoding='utf-8', errors='replace')
        if laenge + len(text) > max_chars:
            stuecke.append(text[:max(0, max_chars - laenge)])
            break
        stuecke.append(text)
        laenge += len(text)
    return "".join(stuecke)


def lade_gesamttext(d: Path) -> tuple[str, list[tuple[int, int, int]]]:
    """
    Konkateniert alle Chunks eines Sprachordners in Lesereihenfolge. Liefert
    den Gesamttext plus eine Offset-Tabelle (start, ende, chunknummer) je
    Chunk, um eine Position im Gesamttext auf (chunk, lokale Position)
    zurueckzurechnen.
    """
    dateien = sorted(
        (f for f in d.glob("chunk_*.md") if not f.name.endswith(".tagged.md")),
        key=lambda f: int(re.search(r'chunk_(\d+)', f.name).group(1)))
    teile: list[str] = []
    offsets: list[tuple[int, int, int]] = []
    cursor = 0
    for f in dateien:
        chunk = int(re.search(r'chunk_(\d+)', f.name).group(1))
        text = f.read_text(encoding='utf-8', errors='replace')
        teile.append(text)
        offsets.append((cursor, cursor + len(text), chunk))
        cursor += len(text)
    return "".join(teile), offsets


def abs_zu_chunk(offsets: list[tuple[int, int, int]], pos: int) -> tuple[int, int]:
    for start, ende, chunk in offsets:
        if start <= pos < ende:
            return chunk, pos - start
    if offsets:
        start, ende, chunk = offsets[-1]
        return chunk, max(0, min(pos - start, ende - start))
    return -1, 0


def normalisiere(s: str) -> str:
    return re.sub(r'\s+', ' ', s.strip().lower())


_MARKUP_RAUSCHEN = re.compile(r'\[\]\{[^}]*\}|\{[^}]*\}')


def zeilenisoliert(text: str, start: int, ende: int) -> bool:
    """
    True, wenn der Treffer (fast) allein auf seiner Zeile steht. Manche
    PDF-Konvertate streuen Kolumnentitel (denselben Kapiteltitel, auf jeder
    Seite wiederholt) mitten in einen Satz — erlebt an "Capitalism,
    Socialism and Democracy": '... durch eine wahre oder falsche
    Offenbarung der Logik\\n\\nMarx der Prophet\\n\\n7\\n\\nder sozialen
    Evolution zu ersetzen ...'. Ein solcher Treffer ist keine echte
    Kapitelgrenze, auch wenn der Text exakt passt.

    Pandoc-Anker/Attribut-Markup auf derselben Zeile ('[]{#anker}TEIL I')
    zaehlt dabei nicht mit — sonst faellt eine echte Ueberschrift durch,
    nur weil ein Anker direkt davorklebt (erlebt an genau diesem Buch:
    '[]{#index_split_000.html_filepos56659}TEIL I' wurde als nicht isoliert
    verworfen, obwohl es die echte Kapitelgrenze war).
    """
    zeilenstart = text.rfind('\n', 0, start) + 1
    zeilenende = text.find('\n', ende)
    if zeilenende == -1:
        zeilenende = len(text)
    umgebung = _MARKUP_RAUSCHEN.sub('', text[zeilenstart:zeilenende]).strip()
    treffer = text[start:ende].strip()
    if len(umgebung) > len(treffer) + 6:
        return False
    return not kolumnentitel_mit_seitenzahl(text, ende)


# Seitenzahl direkt hinter dem Treffer — in BEIDEN im Buch vorkommenden
# Schreibweisen: auf derselben Zeile ('... Investitionsmöglichkeiten 113\n')
# oder auf einer eigenen Zeile ('Marx der Prophet\n\n7\n'). \s* schluckt
# in beiden Faellen den Zwischenraum (Leerzeichen bzw. Zeilenumbrueche).
_SEITENZAHL_DANACH = re.compile(r'\A\s*\(?\d{1,4}\)?\s*\n')


def kolumnentitel_mit_seitenzahl(text: str, ende: int) -> bool:
    """
    True, wenn direkt nach dem Treffer nur eine (Seiten-)Zahl folgt, bevor
    der naechste Fliesstext beginnt. Ein Kolumnentitel (auf jeder Seite
    wiederholter Kapiteltitel, den manche PDF-Konvertate als eigene Zeile
    ausgeben) sieht sonst genauso "zeilenisoliert" aus wie eine echte
    Ueberschrift — der Unterschied ist die angehaengte Seitenzahl. Erlebt an
    "Capitalism, Socialism and Democracy": die echte Ueberschrift "KAPITEL X
    / DAS VERSCHWINDEN DER INVESTITIONSMÖGLICHKEITEN" (chunk_048) geht
    direkt in Fliesstext ueber, waehrend ein Kolumnentitel eine Seite
    spaeter ("... Investitionsmöglichkeiten 113", chunk_049 — die Zahl klebt
    dort OHNE Zeilenumbruch direkt an den Titel) zufaellig dieselben
    Suchtreffer-Kriterien erfuellte und faelschlich als Fund durchging.
    """
    return bool(_SEITENZAHL_DANACH.match(text[ende:ende + 20]))


def suche_titel(gesamt_lower: str, titel: str, ab: int) -> int:
    """
    Sucht `titel` (Gross-/Kleinschreibung ignoriert — Verlage setzen
    Kapitelueberschriften im Fliesstext oft in KAPITAELCHEN/CAPS, waehrend
    das Inhaltsverzeichnis normale Schreibung nutzt; Leerraum toleriert) ab
    Position `ab` im bereits kleingeschriebenen Gesamttext. `.lower()`
    aendert bei deutschem/englischem Text die Zeichenlaenge nicht, die
    gefundene Position gilt daher unveraendert im Originaltext.

    Verlangt einen zeilenisolierten Treffer (echte Ueberschrift, s.
    zeilenisoliert) — KEIN Fallback auf den ersten im Fliesstext
    eingebetteten Treffer. Ein solcher Fallback erschien zunaechst wie ein
    vernuenftiger Kompromiss ("ungefaehr richtig statt gar nichts"), erwies
    sich beim Test an "Capitalism, Socialism and Democracy" aber als
    stiller Falschtreffer: das Inhaltsverzeichnis listet Kapitel XV als
    "Vorbereitung", die echte Kapitelueberschrift im Fliesstext lautet aber
    "VORBEREITENDE MASSNAHMEN" — das Wort "Vorbereitung" kommt im Buch also
    nirgends isoliert vor, nur beilaeufig in normalem Fliesstext, und genau
    DAS haette der Fallback als vermeintlichen Fund gemeldet. Lieber korrekt
    als "nicht gefunden" ausgewiesen (--min-recall faengt zu viele Luecken
    ab) als ein falscher, aber selbstbewusst gemeldeter Treffer.
    """
    ziel = normalisiere(titel)
    if len(ziel) < 3:
        return -1
    # \b um JEDES Token, nicht nur um den Gesamttreffer: sonst matcht
    # z.B. "teil i" als Teilstring in "teil ii" (kein Wortende zwischen den
    # beiden i, aber \s+ zwischen den Tokens haette das nicht verhindert) —
    # erlebt an "Teil I", das faelschlich in "TEIL II" gefunden wurde.
    tokens = [r'\b' + re.escape(t) + r'\b' for t in ziel.split()]
    if not tokens:
        return -1
    muster = re.compile(r'\s+'.join(tokens))
    pos, versuche = ab, 0
    while versuche < 200:
        m = muster.search(gesamt_lower, pos)
        if not m:
            break
        if zeilenisoliert(gesamt_lower, m.start(), m.end()):
            return m.start()
        pos = m.end()
        versuche += 1
    return -1


def platziere_toc(eintraege: list[dict], gesamt_lower: str,
                  ab: int) -> tuple[list[dict], list[str]]:
    """
    Sucht jeden TOC-Eintrag sequentiell im Fliesstext, beginnend NACH `ab`
    — dem exakten Ende des Textfensters, das dem Modell fuers
    Inhaltsverzeichnis vorlag (s. lade_toc_text). Alles davor ist per
    Definition das gedruckte Inhaltsverzeichnis selbst oder frueheres
    Titelblatt, kein echter Kapitelanfang; ein zweiter, sich selbst
    entdeckender Suchdurchgang erwies sich als brüchig, weil TOC-Zeilen mit
    angehaengtem Untertitel die Isolations-Praeferenz in suche_titel()
    manchmal nicht erfuellen und die Suche dadurch schon im ersten
    Durchgang unkontrolliert weit ins Buch hineinlief (erlebt an
    "Capitalism, Socialism and Democracy": der Cursor sprang beim ersten
    Titel-Paar bereits bis Kapitel V). Ein fester Fensteroffset ist robuster
    als ihn erraten zu muessen. Nicht wiedergefundene Titel bleiben ohne
    Position — es wird nichts geraten.
    """
    ergebnis, fehlend = [], []
    cursor = ab
    for e in eintraege:
        titel_treffer = e["titel"]
        pos = suche_titel(gesamt_lower, titel_treffer, cursor)
        if pos == -1 and ": " in e["titel"]:
            # Manche Buecher fuehren im gedruckten TOC "Titel: Untertitel",
            # wiederholen im Fliesstext aber nur "Titel" (s. Docstring-
            # Praezedenzfall bei "Teil"-Eintraegen — hier fuer normale
            # Kapitel nachgezogen, weil der TOC_PROMPT den Untertitel bei
            # "kapitel"-Eintraegen bewusst NICHT abschneidet, s. dortiger
            # Kommentar). Nur als Fallback, wenn die volle Zeile nicht
            # isoliert gefunden wird.
            kurz = e["titel"].split(": ", 1)[0].strip()
            if len(kurz) >= 3:
                pos = suche_titel(gesamt_lower, kurz, cursor)
                if pos != -1:
                    titel_treffer = kurz
        if pos == -1:
            fehlend.append(e["titel"])
            continue
        ergebnis.append({**e, "position": pos})
        cursor = pos + len(normalisiere(titel_treffer))
    return ergebnis, fehlend


def braucht_llm(buch: Path) -> bool:
    """True, wenn kapitel.json fehlt oder (noch) keine Kapitel enthaelt."""
    f = buch / "kapitel.json"
    if not f.exists():
        return True
    try:
        s = json.loads(f.read_text(encoding='utf-8'))
    except Exception:
        return True
    return not s.get("kapitel")


def finde_buecher(ziel: str | None) -> list[Path]:
    if ziel:
        p = Path(ziel)
        if not p.is_dir():
            p = LEKTOR / ziel
        if not p.is_dir():
            raise SystemExit(f"[FEHLER] Nicht gefunden: {ziel}")
        return [p.resolve()]
    treffer = []
    for autor in sorted(LEKTOR.iterdir()):
        if not autor.is_dir():
            continue
        for buch in sorted(autor.iterdir()):
            if buch.is_dir() and (buch / "de").is_dir():
                treffer.append(buch)
    return treffer


def verarbeite(buch: Path, sprache: str, modell: str, ollama: str,
               max_anteil: float, min_recall: float,
               toc_chunks: int, toc_max_chars: int, dry_run: bool) -> None:
    d = buch / sprache
    if not d.is_dir() or not any(d.glob("chunk_*.md")):
        print(f"\n{buch.parent.name}\\{buch.name}: kein '{sprache}'-Ordner mit Chunks.")
        return

    print(f"\n{buch.parent.name}\\{buch.name}")

    toc_text = lade_toc_text(d, toc_chunks, toc_max_chars)
    try:
        eintraege = frage_toc(toc_text, modell, ollama)
    except requests.exceptions.Timeout:
        print("  [FEHLER] Timeout beim Auslesen des Inhaltsverzeichnisses.")
        return
    except Exception as e:
        print(f"  [FEHLER] Inhaltsverzeichnis: {e}")
        return

    if not eintraege:
        print("  [verworfen] Kein Inhaltsverzeichnis erkannt "
              f"(erste {toc_chunks} Chunks / {toc_max_chars} Zeichen abgesucht).")
        return

    gesamt, offsets = lade_gesamttext(d)
    gesamt_lower = gesamt.lower()
    platziert, fehlend = platziere_toc(eintraege, gesamt_lower, len(toc_text))

    recall = len(platziert) / len(eintraege)
    print(f"  Inhaltsverzeichnis: {len(eintraege)} Einträge, "
          f"{len(platziert)} im Fließtext wiedergefunden ({recall:.0%})")
    if fehlend:
        bsp = ", ".join(f'"{t[:40]}"' for t in fehlend[:5])
        mehr = " …" if len(fehlend) > 5 else ""
        print(f"    nicht wiedergefunden: {bsp}{mehr}")

    if recall < min_recall:
        print(f"  [verworfen] Trefferquote {recall:.0%} unter der Grenze "
              f"{min_recall:.0%} — zu lückenhaft für kapitel.json.")
        return
    if len(platziert) < 2:
        print("  [verworfen] Zu wenige platzierte Einträge.")
        return

    marken = []
    for e in platziert:
        chunk, lokal = abs_zu_chunk(offsets, e["position"])
        marken.append({"id": "", "nr": e["nr"], "titel": e["titel"],
                       "chunk": chunk, "position": lokal,
                       "vorspann": e["art"] == "vorspann"})
    marken.sort(key=lambda m: (m["chunk"], m["position"]))

    chunks = _dc.chunk_liste(d)
    struktur = _dc.struktur_aus_marken(marken, chunks, quelle="llm-toc")
    n = len(struktur["kapitel"])
    anteil = round(n / len(chunks), 2) if chunks else 0
    if anteil > max_anteil:
        print(f"  [verworfen] {n} „Kapitel“ bei {len(chunks)} Chunks = "
              f"{anteil} je Chunk (Grenze {max_anteil}) — vermutlich Fehlerkennung.")
        return

    print(f"  {n} Kapitel, {len(struktur['vorspann'])} Vorspann-Marken")
    for k in struktur["kapitel"]:
        nr = f"{k['nr']}. " if k["nr"] else ""
        print(f"      {nr}{k['titel'][:46]:48} ab chunk_{k['chunk']:03d}")

    if dry_run:
        print("  (DRY-RUN — nichts geschrieben.)")
        return

    ziel = buch / "kapitel.json"
    ziel.write_text(json.dumps(struktur, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"  -> {ziel}")

    hinweis = diagnose_fussnoten(d, modell, ollama)
    if hinweis:
        hz = buch / "hinweise-fussnoten.txt"
        hz.write_text(
            "Vom lokalen Modell beobachtete Fussnoten-Konvention (Diagnose, "
            "keine automatische Aenderung) — vor extract-footnotes.py/"
            "build-chapters.py pruefen, falls sie von InDesign/calibre "
            f"abweicht:\n\n{hinweis}\n", encoding='utf-8')
        print(f"  -> {hz} (Fussnoten-Hinweis — bitte lesen)")


def main():
    ap = argparse.ArgumentParser(
        description="Kapitelgrenzen ueber das per LLM ausgelesene "
                     "Inhaltsverzeichnis + Textsuche erkennen, wo Anker/"
                     "Ueberschriften-Fallback nichts liefern"
    )
    ap.add_argument("buch", nargs="?", default=None)
    ap.add_argument("--alle", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="mit --alle auch Buecher mit bereits brauchbarer "
                         "Struktur neu erkennen lassen")
    ap.add_argument("--sprache", default="de", choices=["de", "en"])
    ap.add_argument("--model", default=MODELL)
    ap.add_argument("--ollama-url", default=OLLAMA)
    ap.add_argument("--max-anteil", type=float, default=MAX_ANTEIL)
    ap.add_argument("--min-recall", type=float, default=MIN_RECALL,
                    help="Mindestanteil der TOC-Einträge, der im Fließtext "
                         "wiedergefunden werden muss (Standard 0.5)")
    ap.add_argument("--toc-chunks", type=int, default=TOC_MAX_CHUNKS,
                    help="so viele Chunks vom Buchanfang nach dem "
                         "Inhaltsverzeichnis absuchen (Standard 6)")
    ap.add_argument("--toc-max-chars", type=int, default=TOC_MAX_CHARS)
    ap.add_argument("--dry-run", action="store_true", help="nur anzeigen")
    args = ap.parse_args()

    if not args.buch and not args.alle:
        raise SystemExit("[FEHLER] Buch angeben oder --alle verwenden.")

    print("=" * 64)
    print(f"LLM-Kapitelerkennung (Inhaltsverzeichnis){' (DRY-RUN)' if args.dry_run else ''} "
          f"| Modell: {args.model} | Sprache: {args.sprache}")
    print("=" * 64)

    buecher = finde_buecher(None if args.alle else args.buch)
    if args.alle and not args.force:
        buecher = [b for b in buecher if braucht_llm(b)]
        if not buecher:
            print("\nAlle Bücher haben bereits eine brauchbare Struktur "
                  "(--force erzwingt eine erneute LLM-Erkennung).")
            return

    for buch in buecher:
        verarbeite(buch, args.sprache, args.model, args.ollama_url,
                  args.max_anteil, args.min_recall,
                  args.toc_chunks, args.toc_max_chars, args.dry_run)


if __name__ == "__main__":
    main()