/* Kern des Schnelllesers fuer Epistopheles (Chromebook). 1:1-Portierung von
 * tools/episto_tui/speedreader.py: macht aus den KI-Feldern eines Kapitels eine
 * Wortfolge mit Abschnittsmarken, Erkennungspunkt und Anzeigedauer je Wort.
 * Aenderungen an Zeiten oder Tokenisierung immer in BEIDEN Dateien machen; der
 * Paritaetstest (test_paritaet.py) vergleicht beide. */
(function (root, fabrik) {
  if (typeof module === "object" && module.exports) module.exports = fabrik();
  else root.Speedreader = fabrik();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const MIN_WPM = 100;
  const MAX_WPM = 900;
  const STANDARD_WPM = 400;
  const WPM_SCHRITT = 50;
  const WPM_FEIN = 5;

  // Reihenfolge und Beschriftung der Abschnitte; Schluessel wie in tags.json
  // (die Daten kommen aus export_daten.py). Leere Felder entfallen.
  const ABSCHNITTE = [
    ["zusammenfassung", "Zusammenfassung"],
    ["these", "Thesen"],
    ["gegen", "Gegenpositionen"],
    ["kern", "Kernbegriffe"],
    ["def", "Definitionen"],
    ["beleg", "Belege"],
  ];

  const FUSSNOTE = /\s*\[\^[^\]]+\]/g;
  const MD = /\*+|^_+|_+$/g;
  const SCHLUSS_ZEICHEN = "\"'»«“”„‘’)]}";
  const SATZENDE = ".!?…";
  const PAUSE_ZEICHEN = ",;:–—";
  const ANFANGS_ZEICHEN = "(['\"„“‘»«";

  const zeichen = (text) => Array.from(text);

  function stripZeichen(text, menge) {
    const z = zeichen(text);
    let a = 0;
    let e = z.length;
    while (a < e && menge.includes(z[a])) a++;
    while (e > a && menge.includes(z[e - 1])) e--;
    return z.slice(a, e).join("");
  }

  function kernDesWortes(text) {
    return stripZeichen(text, SCHLUSS_ZEICHEN + SATZENDE + PAUSE_ZEICHEN + ANFANGS_ZEICHEN);
  }

  function letzteZeichen(text, menge) {
    const z = zeichen(text);
    let e = z.length;
    while (e > 0 && menge.includes(z[e - 1])) e--;
    return e > 0 ? z[e - 1] : "";
  }

  function faktorVon(text) {
    const laenge = zeichen(kernDesWortes(text)).length;
    let faktor = 1.0;
    if (laenge > 12) faktor += 0.6;
    else if (laenge > 8) faktor += 0.3;
    const ende = letzteZeichen(text, SCHLUSS_ZEICHEN);
    if (ende && SATZENDE.includes(ende)) faktor += 1.0;
    else if (ende && PAUSE_ZEICHEN.includes(ende)) faktor += 0.5;
    return faktor;
  }

  const hatBuchstabeOderZiffer = (t) => /[\p{L}\p{N}]/u.test(t);

  function tokens(eintrag) {
    const token = [];
    const roh = eintrag.replace(FUSSNOTE, "").split(/\s+/).filter((t) => t !== "");
    for (let t of roh) {
      t = t.replace(MD, "");
      if (!t) continue;
      if (token.length && !hatBuchstabeOderZiffer(t)) token[token.length - 1] += t;
      else token.push(t);
    }
    return token;
  }

  function feldEintraege(wert) {
    const liste = typeof wert === "string" ? [wert] : Array.isArray(wert) ? wert : [];
    return liste.map((e) => (e === null || e === undefined ? "" : String(e)).trim()).filter((e) => e);
  }

  /** felder: {zusammenfassung, these, gegen, kern, def, beleg} wie im Export. */
  function baueWoerter(felder) {
    const woerter = [];
    const namen = [];
    for (const [feld, name] of ABSCHNITTE) {
      const eintraege = feldEintraege(felder[feld]);
      if (!eintraege.length) continue;
      const abschnitt = namen.length;
      namen.push(name);
      woerter.push({ text: name, abschnitt, marke: true, satzende: true, faktor: 2.0 });
      for (const eintrag of eintraege) {
        const token = tokens(eintrag);
        token.forEach((t, i) => {
          const w = { text: t, abschnitt, marke: false, satzende: false, faktor: faktorVon(t) };
          if (i === token.length - 1) {
            w.satzende = true;
            w.faktor = Math.max(w.faktor, 2.0);
          } else if (SATZENDE.includes(letzteZeichen(t, SCHLUSS_ZEICHEN))) {
            w.satzende = true;
          }
          woerter.push(w);
        });
      }
    }
    return { woerter, namen };
  }

  /** Index des Erkennungspunkts (in Zeichen, nicht UTF-16-Einheiten). */
  function orpIndex(text) {
    const kern = kernDesWortes(text);
    const z = zeichen(text);
    const kz = zeichen(kern);
    let versatz = 0;
    if (kz.length) {
      const pos = text.indexOf(kern);
      versatz = pos < 0 ? 0 : zeichen(text.slice(0, pos)).length;
    }
    const laenge = kz.length;
    let index;
    if (laenge <= 1) index = 0;
    else if (laenge <= 5) index = 1;
    else if (laenge <= 9) index = 2;
    else if (laenge <= 13) index = 3;
    else index = 4;
    return Math.min(versatz + index, Math.max(z.length - 1, 0));
  }

  /** Zerlegt ein Wort in links / Erkennungsbuchstabe / rechts fuer die Anzeige.
   *  Marken werden gross geschrieben, wie in der TUI. */
  function teileWort(wort) {
    const text = wort.marke ? wort.text.toUpperCase() : wort.text;
    const z = zeichen(text);
    const i = Math.min(orpIndex(text), z.length - 1);
    return { links: z.slice(0, i).join(""), mitte: z[i] || "", rechts: z.slice(i + 1).join("") };
  }

  function satzanfang(woerter, i) {
    let j = Math.min(Math.max(i, 0), woerter.length - 1);
    while (j > 0 && !woerter[j - 1].satzende) j--;
    return j;
  }

  function voriger_satzanfang(woerter, i) {
    const start = satzanfang(woerter, i);
    if (start === i && i > 0) return satzanfang(woerter, i - 1);
    return start;
  }

  function naechster_satzanfang(woerter, i) {
    for (let j = i + 1; j < woerter.length; j++) if (woerter[j - 1].satzende) return j;
    return woerter.length - 1;
  }

  function abschnittsanfang(woerter, i) {
    const a = woerter[i].abschnitt;
    while (i > 0 && woerter[i - 1].abschnitt === a) i--;
    return i;
  }

  function voriger_abschnitt(woerter, i) {
    const anfang = abschnittsanfang(woerter, i);
    if (anfang === i && i > 0) return abschnittsanfang(woerter, i - 1);
    return anfang;
  }

  function naechster_abschnitt(woerter, i) {
    const a = woerter[i].abschnitt;
    for (let j = i + 1; j < woerter.length; j++) if (woerter[j].abschnitt !== a) return j;
    return woerter.length - 1;
  }

  const begrenzeTempo = (wpm) => Math.min(Math.max(Math.trunc(Number(wpm)) || STANDARD_WPM, MIN_WPM), MAX_WPM);
  const grunddauer = (wpm) => 60.0 / Math.min(Math.max(wpm, MIN_WPM), MAX_WPM);
  const dauer = (wort, wpm) => grunddauer(wpm) * wort.faktor;

  function restdauer(woerter, i, wpm) {
    let summe = 0;
    for (let j = i; j < woerter.length; j++) summe += dauer(woerter[j], wpm);
    return summe;
  }

  return {
    MIN_WPM, MAX_WPM, STANDARD_WPM, WPM_SCHRITT, WPM_FEIN, ABSCHNITTE,
    kernDesWortes, feldEintraege, baueWoerter, orpIndex, teileWort,
    satzanfang, voriger_satzanfang, naechster_satzanfang,
    abschnittsanfang, voriger_abschnitt, naechster_abschnitt,
    begrenzeTempo, grunddauer, dauer, restdauer,
  };
});
