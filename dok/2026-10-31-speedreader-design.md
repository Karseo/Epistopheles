# Design: Speedreader für die KI-Felder eines Kapitels

Stand: 2026-10-31.

## Ziel und Abgrenzung

Ein schneller Durchlauf durch alles, was die KI aus einem Kapitel destilliert hat,
**bevor** man in den Originaltext springt. Das passt zur Leitlogik (Hinweis →
Originaltext → Beginn des Denkens). Bewusst **nicht** für den Originaltext: Bei
schwerer Theorie ist hohes Lesetempo kein Gewinn, und der Originaltext ist die
Stelle, an der das Denken beginnen soll.

## Bedienung

- Aufruf: Taste `v` oder Knopf **Speed** (Handy-Leiste, obere Zeile). Dialog
  `SpeedreaderScreen` für das aktuell geöffnete Kapitel; ohne geöffnetes Kapitel
  erscheint ein Hinweis.
- Der Dialog startet **pausiert** und zeigt das erste Wort. Leertaste oder
  **Start** läuft los, danach Pause/Weiter. Nach dem Ende startet Leertaste von vorn
  (Knopf heißt dann **Neu**).
- Tempo (100 bis 900 Wörter pro Minute, Standard **400**): grob mit ↑ / ↓ oder den
  Knöpfen **+50** / **−50**, fein mit `+` / `−` oder den Knöpfen **+5** / **−5**.
  Das Tempo wird gemerkt (`speedreader_wpm` in `~/.episto_tui/zustand.json`, nur
  auf diesem Gerät); ein schon gemerkter Wert hat Vorrang vor dem Standard.
- Springen: ← / **◀ Satz** zum Anfang des laufenden Satzes (am Satzanfang: des
  vorigen), → / **Satz ▶** zum nächsten Satz, **◀◀** / **▶▶** zum Anfang des
  vorigen/nächsten Abschnitts. Die Wartezeit des neuen Worts beginnt neu.
- Esc / **Schließen** beendet den Dialog und stoppt den Ablauf.
- Die Knöpfe nehmen keinen Fokus, damit Leertaste und Pfeile immer beim Dialog
  ankommen.

## Was gezeigt wird

Alle KI-Felder aus dem Tagging (`tags.json`) des Kapitels, in fester Reihenfolge:
Zusammenfassung, Thesen, Gegenpositionen, Kernbegriffe, Definitionen, Belege.
Leere Felder entfallen. Jeder Abschnitt beginnt mit einem Marken-Wort in
Großbuchstaben (cyan), jeder Listeneintrag zählt als eigener Satz.

Anzeige: eine Zeile, in der der **Erkennungspunkt** (ab Mitte des ersten Drittels
des Worts, Satzzeichen zählen nicht mit; rot) immer in derselben Spalte steht,
darüber und darunter ein Strich als Fixpunkt. Die Zeile ist 37 Zeichen breit und
passt damit in 45 Handy-Spalten. Sehr lange Wörter rutschen nach links, statt
abgeschnitten zu werden (der Erkennungspunkt weicht für dieses eine Wort aus);
erst über 37 Zeichen wird mit „…" gekürzt.

Statuszeile: Abschnitt · Wort i/n · Tempo · geschätzte Restzeit · läuft/Pause/Ende.

## Anzeigedauer

Grunddauer = 60 / Tempo Sekunden, mal Faktor je Wort:

| Merkmal | Zuschlag |
|---|---|
| Wort über 8 Zeichen | +0,3 |
| Wort über 12 Zeichen | +0,6 |
| endet auf `.` `!` `?` `…` | +1,0 |
| endet auf `,` `;` `:` `–` `—` | +0,5 |
| Ende eines Listeneintrags | mindestens 2,0 |
| Abschnittsmarke | 2,0 |

Schließende Anführungszeichen und Klammern zählen beim Satzzeichen nicht mit.
Der Ablauf nutzt einen Timer pro Wort (kein fester Takt), die Dauer ergibt sich
aus dem Faktor.

## Aufbereitung des Texts

- Fußnotenmarken `[^n]` fallen weg; ein Satzzeichen dahinter bleibt am vorigen
  Wort (kein eigenes „."-Wort).
- Markdown-Sternchen (`*Titel*`) und Randstriche (`_betont_`) fallen weg;
  Unterstriche im Wort (`Gegner_innen`) bleiben.

## Datenlage

An der echten Bibliothek (1178 getaggte Kapitel, 2 ohne KI-Felder): Median 434
Wörter je Kapitel, höchstens 832. Bei 300 Wörtern pro Minute dauert ein Kapitel im
Median etwa 1,8 Minuten, das längste 3,4; beim Standardtempo von 400 sind es etwa
1,4 bzw. 2,6 Minuten (die Dauer verhält sich umgekehrt proportional zum Tempo). Ein
Kapitel ohne KI-Felder zeigt einen Hinweis, der Dialog bleibt bedienbar.

## Grenzen

- Kein Springen in den Originaltext aus dem Dialog (Idee: Taste, die das Kapitel
  öffnet und den Dialog schließt).
- Das Tempo ändert sich nicht selbstständig (kein Anlaufen, kein Verlangsamen bei
  schweren Begriffen außer dem Zuschlag für lange Wörter).
- Ob das Standardtempo von 400 Wörtern pro Minute für diese Texte passt, ist nicht
  erprobt; es lässt sich in 5er- und 50er-Schritten ändern.

## Tests

`tests/test_speedreader.py`: Wortfolge und Reihenfolge der Abschnitte, leere Felder,
Satzenden, Fußnoten, Sternchen, Erkennungspunkt (Tabelle) und feste Spalte, lange
und unmögliche Wörter, Pausenfaktoren, Satz- und Abschnittssprünge, Restdauer;
Dialog: Start/Pause/Ende/Neustart, Timer, Tempo mit Grenzen und Merken, Sprünge
über Tasten und Knöpfe, Kapitel ohne KI-Felder, Esc stoppt, Handybreite,
Knopf **Speed**. Die Zeitabläufe sind teils über direkte `_tick()`-Aufrufe
getestet (deterministisch), ein Test wartet den echten Timer ab.
