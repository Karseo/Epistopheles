cd "D:\Workspace\!Episto\tools"
python -m episto_tui


# !Episto — Epistemisch souveräne Bibliothek

Eine ausrollbare „digitale Bibliothek von Alexandria". EPISTO speichert Standardwerke der Philosophie, Soziologie, Ökonomie etc. als **formatierter Volltext + destillierte Metadaten** und macht sie auch auf anderen Computern einem lokalen oder Cloud-LLM zugänglich — nicht als Orakel, sondern als **quellenfundierter Index**, der den Nutzer auf Wunsch bis zum Originaltext zurückführt.

## Kernidee

- **Volltext** (Markdown) bleibt die Quelle der Wahrheit und Referenz zum Nach-/Weiterlesen.
- **Metadaten** (Thesen, Gegenpositionen, Kernbegriffe, Definitionen, Belege) werden kapitelweise per lokalem LLM destilliert.
- **Gliederung + Stränge** machen Thesen/Anti-Thesen über das Werk hinweg navigierbar.
- **Vektoren** (Qdrant) liefern schnellen semantischen Zugriff; jede Trefferstelle referenziert zurück auf das Kapitel → Grounding statt Halluzination.

Die Logik ist die Umkehrung kognitiver Atrophie:

```
Masse:      KI → Antwort → Ende des Denkens
EPISTO:     KI → Hinweis → Originaltext → Beginn des Denkens
```


## Vektorisierung

```
.\ingest.ps1              # inkrementell (hängt an)
.\ingest.ps1 -Buch "D:\...\reader\<Autor>\<Buch>"  # nur ein Buch anhängen
.\ingest.ps1 -Reset       # Collection neu aufbauen
.\ingest.ps1 -Limit 5     # nur die ersten 5 Kapitel (Test)
```

- Embed-Modell: `mxbai-embed-large` (1024 Dims, 512 Token Kontext).
- Chunking: absatzweise, ~250 Wörter je Chunk (respektiert Absatzgrenzen).
- Qdrant: `http://127.0.0.1:6333`, Collection `episto`, Cosine.
- Payload je Punkt: `buch`, `autor`, `datei`, `kapitel_nr`, `abschnitt` (Gliederungspfad),
  `chunk_idx`, `text`.

## Portabilität

Das Archiv = `!Episto\` (Markdowns + Prompts + Metadaten). **Qdrant-Daten reisen nicht
mit** — sie sind regenerierbar. Auf jedem Zielrechner: `.\ingest.ps1 -Reset` ausführen,
fertig. Damit läuft EPISTO unabhängig vom APIC-Setup auf beliebigen Rechnern.

## Ankerwerk-Referenz

Aufgebaute Werke (Volltext → Tags → Gliederung → Stränge → Vektoren) — **78 Bücher**:

| Autor | Werk | Kapitel | Stränge |
|------|------|--------:|--------:|
| Alonso, Sonia | The Future of Representative Democracy | 12 | 10 |
| Arendt, Hannah | Elemente und Ursprünge totaler Herrschaft | 14 | 11 |
| Bachrach, Peter | The Theory of Democratic Elitism | 8 | 8 |
| Barclay, Donald A | Fake News | 14 | 10 |
| Barlösius, Eva | Pierre Bourdieu | 12 | 9 |
| Beck, Ulrich | Die Metamorphose der Welt | 20 | 7 |
| Beck, Ulrich | Power in the Global Age | 12 | 8 |
| Beck, Ulrich | Risikogesellschaft | 25 | 7 |
| Bernays, Edward | Propaganda | 15 | 6 |
| Best, Heinrich | Democratic Elitism | 13 | 7 |
| Bittner, Wolfgang | Die Eroberung Europas durch die USA | 25 | 7 |
| Bottomore, Tom | Elites and Society | 10 | 5 |
| Bourdieu, Pierre | Die feinen Unterschiede | 42 | 7 |
| Bourdieu, Pierre | The State Nobility | 23 | 11 |
| Bram, Curtis | Elitism versus Populism | 8 | 7 |
| Brüggemann, Michael | Medien im Krieg | 1 | 4 |
| Buchter, Heike | Wer wird Milliardär | 19 | 7 |
| Bueno de Mesquita, Bruce | The Dictator's Handbook | 11 | 6 |
| Callinicos, Alex | Social Theory - A Historical Introduction | 18 | 7 |
| Cooley, Alexander | Dictating the Agenda | 9 | 8 |
| Cooley, Alexander | Exit from Hegemony | 12 | 8 |
| Cooley, Alexander | Great Games, Local Rules | 17 | 9 |
| Cooley, Alexander | Logics of Hierarchy | 9 | 8 |
| Decker, Peter | Demokratie - Die perfekte Form bürgerlicher Herrschaft | 7 | 8 |
| Ditfurth, Jutta | Zeit des Zorns | 15 | 6 |
| Dowding, Keith M and Dumont, Patrick | The Selection of Ministers around the World | 15 | 7 |
| Field, G. Lowell | Elitism (Routledge Revivals) | 7 | 4 |
| Finocchiaro, Maurice A | Beyond Right and Left | 14 | 9 |
| Foucault, Michel | Überwachen und Strafen | 10 | 6 |
| Gehlen, Arnold | Urmensch und Spätkultur | 10 | 6 |
| Gramsci, Antonio | Briefe aus dem Kerker | 47 | 7 |
| Han, Byung-Chul | Psychopolitik | 7 | 8 |
| Harfst, Philipp | Parties, Governments and Elites | 16 | 7 |
| Hartmann, Michael | Die globale Wirtschaftselite | 7 | 6 |
| Hetzel, Andreas | Radikale Demokratie | 11 | 7 |
| Hofbauer, Hannes | Herrschaft der Angst | 18 | 13 |
| Kaesler, Dirk | Klassiker der Soziologie Band 1 | 19 | 7 |
| Kaesler, Dirk | Klassiker der Soziologie Band 2 | 15 | 7 |
| Kahneman, Daniel | Schnelles Denken, langsames Denken | 51 | 11 |
| Karp, Alexander C | The Technological Republic | 23 | 6 |
| Kersey, Timothy | Constrained Elitism and Contemporary Democratic Theory | 6 | 4 |
| Laclau, Ernesto | Hegemonie und radikale Demokratie | 10 | 6 |
| Le Bon, Gustave | Psychologie der Massen | 5 | 7 |
| Lippmann, Walter | Die öffentliche Meinung | 35 | 10 |
| Mattei, Clara E | The Capital Order | 16 | 9 |
| Mausfeld, Rainer | Hegemonie oder Untergang | 9 | 8 |
| Meisel, James H | Der Mythus der herrschenden Klasse | 5 | 8 |
| Michels, Robert | Zur Soziologie des Parteiwesens | 31 | 11 |
| Mills, C. Wright | The Power Elite | 19 | 11 |
| Morris, William | Socialism from the Root Up | 6 | 6 |
| Mouffe, Chantal | Agonistik | 10 | 10 |
| Mouffe, Chantal | The Return of the Political | 12 | 9 |
| Moyser, George | Research Methods for Elite Studies | 15 | 6 |
| Muhsam, Erich | Die Befreiung der Gesellschaft vom Staat | 7 | 7 |
| O'Neil, Cathy | Weapons of Math Destruction | 13 | 6 |
| Parvini, Neema | The Populist Delusion | 15 | 14 |
| Piano, Natasha | Democratic Elitism | 11 | 9 |
| Pilet, Jean-Benoit and Cross, William | The Selection of Political Party Leaders | 22 | 6 |
| Ponsonby, Arthur | Luegen in Kriegszeiten | 31 | 10 |
| Popitz, Heinrich | Phänomene der Macht | 10 | 9 |
| Popper, Karl | Logik der Forschung | 17 | 7 |
| Putnam, Robert D | The Comparative Study of Political Elites | 8 | 6 |
| Roberts, David | Liberal Peacebuilding and Global Governance | 12 | 8 |
| Rothbard, Murray N | Anatomie des Staates | 9 | 6 |
| Sauer, Hanno | Klasse | 11 | 6 |
| Schumpeter, Joseph A | Capitalism, Socialism and Democracy | 30 | 7 |
| Stasavage, David | States of Credit | 9 | 9 |
| Stasavage, David | The Decline and Rise of Democracy | 13 | 10 |
| Tocqueville, Alexis de | Über die Demokratie in Amerika | 44 | 7 |
| Todd, Emmanuel | Der Westen im Niedergang | 19 | 6 |
| Todd, Emmanuel | Traurige Moderne | 23 | 6 |
| Todd, Emmanuel | Weltmacht USA - Ein Nachruf | 12 | 6 |
| Verschiedene Autoren | Die extreme Mitte | 6 | 5 |
| Vianello, Mino | Women and Men in Political and Business Elites | 12 | 6 |
| Vitali, Stefania | The Network of Global Corporate Control | 2 | 0 |
| Wahl, Peter | Die extreme Mitte | 8 | 7 |
| Wissing, Hubert | Intellektuelle Grenzgänge | 14 | 6 |
| Zeuske, Michael | Sklaverei | 13 | 6 |


## Werkzeuge (generisch, `tools\`)

- `taggen.ps1 -Buch <pfad>` — Kapitel-Tagging (Ollama, `qwen3.8:27b`), resume-fähig.
- `straenge.ps1 -Buch <pfad>` — Strang-Aggregation aus `notizen\strang_taxonomie.json` (kern-basiert).
- `lektor-zu-episto.py --buch "<Autor>/<Titel>"` — Brücke `rohdaten\Lektor` → `reader` (`quelle\` + `kapitel.json`; die englischen Referenzchunks landen in `rohdaten\en-chunks`).
- `bereinige-translategemma.py --quelle <pfad> [--reflow] [--ohne-fussnoten]` — bereinigt Fußnoten (`N→*N`), Seitenzahl-Header, `-N-`-Seitenzahlen und Absatz-Reflow.
- `ingest.ps1` — Vektorisierung aller Bücher (scant `reader\**\quelle\*.md`).
- `ingest.ps1 -Buch <pfad>` — nur ein Buch anhängen (inkrementell, ohne -Reset).
- `ingest.ps1 -Reset` — Collection `episto` komplett neu aufbauen (bei neuem Buch, um Duplikate zu vermeiden).
