# Design: Navigation im Lesefluss (TUI)

Stand: 2026-10-31. Setzt Punkt 3 der Verbesserungsvorschläge um und baut auf
`2026-10-31-konflikt-merge-und-volltextsuche-design.md` auf.

## Ziel

Beim Lesen soll man sich entlang des Buchs und der Bibliothek bewegen können,
ohne jedes Mal den Baum zu bedienen: weiterblättern, einer Spur (Thema,
Querverweis, eigene Notiz) folgen und nach einer Pause dort weitermachen, wo man
aufgehört hat.

## 1. Kapitel blättern

- `n` = nächstes, `p` = voriges Kapitel desselben Buchs (Footer: „Weiter",
  „Zurück"), auf dem Handy die Knöpfe ◀ und ▶.
- Der aktive Tab bleibt erhalten: wer Tags oder Fazit liest, sieht beim
  Weiterblättern dieselbe Ansicht des nächsten Kapitels.
- Am Buchanfang und -ende erscheint nur ein Hinweis. Im Editiermodus wird nicht
  geblättert (Hinweis: erst speichern oder verwerfen), damit nichts still
  verworfen wird. In Eingabefeldern und im Tippfilter des Baums gehören `n` und
  `p` weiter dem Feld.
- `library.kapitel_nachbar(buch, kapitel, richtung)`.

## 2. Leseposition

- Gespeichert wird die zuletzt gelesene Stelle: Buch, Kapitel und Absatz am
  oberen Rand des Lesebereichs. Beim Start öffnet die TUI sie wieder und
  scrollt hin („Weiter bei: …").
- Ablage: `~/.episto_tui/zustand.json` (Umgebungsvariable `EPISTO_ZUSTAND`
  überschreibt den Pfad). **Bewusst nicht in der Bibliothek**: PC und Handy lesen
  an verschiedenen Stellen, die Datei würde sonst per Syncthing hin- und
  herspringen und Konflikte erzeugen. Schreibfehler werden still ignoriert.
- Gesichert wird beim Kapitelwechsel, beim Beenden (`q`) und alle 15 Sekunden,
  aber nur bei Änderung (Termux wird oft ohne sauberes Beenden geschlossen).
- Der „obere Absatz" wird beim Scrollen entprellt nachgeführt
  (`ReaderPane._lese_absatz`); bei verborgenem Tab scrollt nichts, der Wert bleibt
  gültig. Gescrollt wird nach dem Rendern, und bei noch nicht fertigem Layout (bis
  zu 8 Wiederholungen im 0,1-s-Takt).
- Nur die zuletzt gelesene Stelle wird gemerkt, nicht je Buch.

## 3. Themen: dasselbe Thema in anderen Kapiteln

Im Tab „Themen" steht unter dem Text eine Liste „Dasselbe Thema in anderen
Kapiteln": je Strang, der im aktuellen Kapitel vorkommt, die übrigen Kapitel mit
dem Strang. Enter öffnet das Kapitel im Text-Tab. Die Liste erscheint nur, wenn
es solche Kapitel gibt. (`library.read_straenge_uebersicht`)

## 4. Querverweise öffnen

Das `ziel` eines Querverweises (`schumpeter_capitalism-socialism-and-democracy`
= `<Nachname>_<Titel-Slug>`) wird auf ein Buch der Bibliothek abgebildet:
gleicher Titel-Slug, bei mehreren gleichnamigen Büchern entscheidet der
Nachname. Liegt das Werk in der Bibliothek, erscheint es unter „In der
Bibliothek vorhanden" und Enter öffnet das erste Kapitel. An der echten
Bibliothek sind das 45 von 133 Querverweisen; die übrigen verweisen auf Werke,
die nicht vorhanden sind, und bleiben reiner Text.
(`library.finde_buch_fuer_ziel`)

## 5. Notizenliste

`m` (Handy: Knopf „Notiz") öffnet eine Liste aller eigenen Kommentare und
Highlights der Bibliothek, nach Buch, Kapitel und Absatz sortiert, mit
Kontrollkästchen „Nur in <aktuelles Buch>". Tippen filtert sofort; Art und Farbe
zählen mit (`kommentar`, `highlight`, `gelb`, `rosa`, `blau`, `korrektur`).
Enter springt an die Textstelle. Der Absatz wird über den Absatzanfang neu
bestimmt (`annotate.locate_paragraph`), falls der Text sich verschoben hat.
Höchstens 300 Einträge werden angezeigt. Notizen zu nicht mehr vorhandenen
Kapiteln fehlen in der Liste. (`notizen.py`, `widgets/notizen_screen.py`)

## Gemeinsame Bausteine

- `SpringeZu(buch, kapitel, absatz_index)` (`widgets/sprung.py`) ist die Meldung,
  mit der Ansichten ein Kapitel öffnen lassen. `EpistoApp._oeffne(...)` führt
  den Baum-Cursor mit, lädt alle Tabs und wechselt (außer beim Blättern) in den
  Text-Tab. Suche, Notizen, Themen und Querverweise nutzen dieselbe Funktion.

## Handy-Leiste

Mit ◀ ▶ Suche Notiz wurden es zu viele Knöpfe für eine Zeile bei 45 Spalten. Die
Leiste hat jetzt zwei Zeilen: oben Navigation (Baum, ◀, ▶, Suche, Notiz), unten
Bearbeiten (Edit, Gelb, Rosa, Blau, K, Komm, Lösch). Eine Zeile ohne sichtbaren
Knopf wird ausgeblendet; im Editiermodus bleibt es bei einer Zeile.

## Nicht enthalten

Verlauf („zurück zur vorherigen Stelle" nach einem Sprung), Leseposition je Buch,
Lesezeichen, Springen zwischen Büchern per `n` am Buchende, Querverweise auf
einzelne Kapitel (die Daten nennen nur das Werk).

## Tests

`tests/test_navigation.py`: Kapitelnachbarn, Auflösung der Querverweis-Ziele
(auch bei gleichnamigen Büchern und Umlauten), Strang-Übersicht, Zustandsdatei
(Rundlauf, verschwundenes Kapitel, kaputte Datei, Schreibfehler), Notizen sammeln
und filtern, verschobener Absatz, `n`/`p` (Tab bleibt, Anfang/Ende, Editiermodus,
Tippfilter), Knöpfe, Scroll-Verfolgung, Speichern beim Beenden und
Wiederöffnen beim Start, Sprung aus Themen, Querverweisen und Notizenliste.
Die Zustandsdatei wird in allen Tests auf ein temporäres Verzeichnis umgelenkt
(`conftest.py`).
