"""Paritaetstest: redaktion.js (Geraet) muss dieselben Ergebnisse liefern wie redaktion/ops.py (PC).
Laeuft in Node; ohne Node werden die Tests uebersprungen."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from episto_tui.korrektur import absatz_spannen
from redaktion import ops

HIER = Path(__file__).resolve().parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node nicht installiert")
VEKTOREN = json.loads((HIER.parent / "redaktion" / "testvektoren.json").read_text(encoding="utf-8"))

SKRIPT = r"""
const R = require(process.argv[1]);
const a = JSON.parse(require("fs").readFileSync(0, "utf8"));
let aus;
if (a.funktion === "spieleAb") {
  aus = a.faelle.map(f => { const r = R.spieleAb(f.text, f.eintraege);
    return { text: r.text, stati: r.ergebnisse.map(e => e.status), gruende: r.ergebnisse.map(e => e.grund) }; });
} else if (a.funktion === "texte") {
  aus = a.faelle.map(t => ({ pruefsumme: R.pruefsumme(t), anker: R.ankerVon(t), normal: R.normalisiere(t) }));
} else if (a.funktion === "ohne") {
  aus = R.ohneZurueckgenommene(a.eintraege);
} else if (a.funktion === "wendeAn") {
  aus = a.faelle.map(f => { const r = R.wendeAn(f.text, f.eintrag); return { text: r.text, status: r.status }; });
} else if (a.funktion === "finde") {
  aus = a.faelle.map(f => R.finde(f.text, f.ziel));
} else if (a.funktion === "neu") {
  aus = R.neuerEintrag(...a.args);
}
process.stdout.write(JSON.stringify(aus));
"""


def js(funktion: str, **daten):
    lauf = subprocess.run([NODE, "-e", SKRIPT, str(HIER / "redaktion.js")],
                          input=json.dumps({"funktion": funktion, **daten}),
                          capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(lauf.stdout)


FESTE_TEXTE = [
    "",
    "foobar",
    "Größe über Ärger – naïve Café",
    "Zeile eins\r\nZeile zwei\r\n",
    "  Tab\tund Nbsp   und 　 Rest  ",
    "Astral \U0001F600 und \U00010400 am Ende \U0001F600" + "x" * 40,
    "lone\rCR und\x85NEL und\x1cFS und﻿BOM",
    "é zusammengesetzt vs é",
]


def test_pruefsumme_bekannte_werte():
    erg = js("texte", faelle=["", "a", "foobar"])
    assert [e["pruefsumme"] for e in erg] == ["cbf29ce484222325", "af63dc4c8601ec8c", "85944171f73967e8"]


def test_pruefsumme_anker_normalisiere_stimmen_mit_python_ueberein():
    erg = js("texte", faelle=FESTE_TEXTE)
    for t, e in zip(FESTE_TEXTE, erg):
        assert e["pruefsumme"] == ops.pruefsumme(t), repr(t)
        assert e["anker"] == ops.anker_von(t), repr(t)
        assert e["normal"] == ops.normalisiere(t), repr(t)


def test_js_stimmt_mit_python_ueberein():
    erg = js("spieleAb", faelle=[{"text": v["text"], "eintraege": v["eintraege"]} for v in VEKTOREN])
    for v, e in zip(VEKTOREN, erg):
        assert e["text"] == v["erwartet_text"], v["name"]
        assert e["stati"][-1] == v["erwartet_status"], v["name"]
        if "erwartet_stati" in v:
            assert e["stati"] == v["erwartet_stati"], v["name"]


def test_alle_vektoren_status_und_text_je_eintrag_wie_python():
    """Alle Vektoren: Status und Text je Eintrag wie Python (volle Liste, nicht nur der letzte)."""
    erg = js("spieleAb", faelle=[{"text": v["text"], "eintraege": v["eintraege"]} for v in VEKTOREN])
    for v, e in zip(VEKTOREN, erg):
        text, py = ops.spiele_ab(v["text"], v["eintraege"])
        assert e["text"] == text, v["name"]
        assert e["stati"] == [x.status for x in py], v["name"]


def _eintrag(text, index, art, parameter=None, **ziel_extra):
    a, b = absatz_spannen(text)[index]
    ziel = {"absatz_index": index, "anfang": ops.anker_von(text[a:b])}
    ziel.update(ziel_extra)
    return ops.neuer_eintrag("Autor/Titel", "volltext", ziel, art, parameter or {}, text[a:b])


def test_verbinden_trennstrich_unicode_wie_python():
    faelle = []
    for oben, unten in [("Wort-", "teil"), ("Wort-", "Teil"), ("Wort -", "teil"), ("Größe-", "ärger"),
                        ("Größe-", "Ärger"), ("Wort-", "ª"), ("Wort-", "ǅx"), ("Wort-", "\U00010428x"),
                        ("Wort\U00010400-", "teil"), ("Wort1-", "teil"), ("-", "teil"), ("ab ", "  cd")]:
        text = f"Kopf\n\n{oben}\n{unten}\nRest"
        faelle.append({"text": text, "eintrag": _eintrag(text, 1, "verbinden", {}, zeile=0)})
    erg = js("wendeAn", faelle=faelle)
    for f, e in zip(faelle, erg):
        py = ops.wende_an(f["text"], f["eintrag"])
        assert (e["text"], e["status"]) == (py.text, py.status), repr(f["text"])


def test_operationen_mit_tabs_crlf_und_leerraum_wie_python():
    t1 = "Kopf\t eins\r\n\r\nA\tx\r\nB y\r\nC z\r\n\r\nSchluss"
    t2 = " Kopf\n\nL0\n  L1\nL2\nL3\n\n\n\nEnde\n"
    faelle = []
    for t in (t1, t2):
        n = len(absatz_spannen(t))
        for i in range(n):
            for art, par, extra in [("trennen", {}, {"zeile": 1}), ("verbinden", {}, {"zeile": 0}),
                                    ("loeschen", {}, {}), ("loeschen", {}, {"zeile": 0}),
                                    ("loeschen", {}, {"zeile": 0, "zeile_bis": 2}),
                                    ("ersetzen", {"nachher": "Neu  text"}, {}),
                                    ("verschieben", {"nach_anfang": ops.anker_von(t[slice(*absatz_spannen(t)[0])])},
                                     {"zeile": 0})]:
                faelle.append({"text": t, "eintrag": _eintrag(t, i, art, par, **extra)})
    erg = js("wendeAn", faelle=faelle)
    for f, e in zip(faelle, erg):
        py = ops.wende_an(f["text"], f["eintrag"])
        assert (e["text"], e["status"]) == (py.text, py.status), (f["text"], f["eintrag"]["art"], f["eintrag"]["ziel"])


def test_finde_stimmt_mit_python_ueberein():
    text = "Gleich\n\nGleich\n\nAnders\n\nGleich\n\n" + "\U0001F600" * 50
    ziele = [{"anfang": "Gleich", "absatz_index": 1}, {"anfang": "Gleich", "absatz_index": 9},
             {"anfang": "Gleich"}, {"anfang": "Anders", "absatz_index": 0}, {"anfang": "Nix"},
             {"anfang": ops.anker_von("\U0001F600" * 50)}]
    erg = js("finde", faelle=[{"text": text, "ziel": z} for z in ziele])
    assert erg == [ops.finde_absatz(text, z) for z in ziele]


def test_ohne_zurueckgenommene_wie_python():
    def e(i, art, **par):
        return {"id": i, "art": art, "parameter": par, "ziel": {}}
    eintraege = [e("a", "ersetzen", nachher="x"), e("b", "ersetzen", nachher="y"), e("r1", "ruecknahme", id="a"),
                 e("c", "marke"), e("r2", "ruecknahme", id="unbekannt"), {"id": "d", "art": "loeschen"},
                 {"id": "r3", "art": "ruecknahme", "parameter": "kaputt"}]
    erg = js("ohne", eintraege=eintraege)
    assert erg == ops.ohne_zurueckgenommene(eintraege)
    assert [x["id"] for x in erg] == ["b", "c", "d"]


def test_fehlerhafte_eintraege_werfen_nie_und_stimmen_mit_python_ueberein():
    text = "Alpha eins.\n\nBeta zwei.\n\nGamma drei."
    gut = _eintrag(text, 1, "ersetzen", {"nachher": "Beta ZWEI."})

    def mit(**aend):
        e = json.loads(json.dumps(gut))
        e.update(aend)
        return e

    kaputt = [
        None, 42, "text", [], mit(ziel="x"), mit(ziel=None), mit(parameter=[]), mit(parameter=None),
        mit(parameter={"nachher": 5}), mit(parameter={"nachher": ""}), mit(parameter={"nachher": "  \n "}),
        mit(parameter={"nachher": "A\n\nB"}), mit(parameter={"nachher": "A\n \t\nB"}),
        mit(vorher=None), mit(vorher={}), mit(vorher={"hash": ""}), mit(vorher={"hash": 7}),
        mit(art="gibtsnicht"), mit(art=None), mit(ziel={"anfang": 3}), mit(ziel={}),
        mit(art="verbinden", ziel={"anfang": "Beta zwei.", "absatz_index": 1, "zeile": "x"}),
        mit(art="loeschen", ziel={"anfang": "Beta zwei.", "absatz_index": 1, "zeile": 99}),
        mit(art="verschieben", ziel={"anfang": "Beta zwei.", "absatz_index": 1, "zeile": 0}, parameter={}),
        mit(id=5), mit(art="ruecknahme"), mit(art="marke", ziel=None),
    ]
    # jeder kaputte Eintrag einzeln, dann alle hintereinander mit einem guten am Ende
    faelle = [{"text": text, "eintraege": [k]} for k in kaputt] + [{"text": text, "eintraege": kaputt + [gut]}]
    erg = js("spieleAb", faelle=faelle)
    for f, e in zip(faelle, erg):
        text_py, py = ops.spiele_ab(f["text"], f["eintraege"])
        assert e["text"] == text_py, f["eintraege"]
        assert e["stati"] == [x.status for x in py], f["eintraege"]
        assert all(g for s, g in zip(e["stati"], e["gruende"]) if s == "konflikt")
    # spieleAb macht nach Fehlern weiter: ein Eintrag an einem unbeteiligten Absatz greift noch
    fern = _eintrag(text, 2, "ersetzen", {"nachher": "Gamma DREI."})
    nach = js("spieleAb", faelle=[{"text": text, "eintraege": kaputt + [fern]}])[0]
    assert nach["stati"][-1] == "angewendet"
    assert nach["text"] == "Alpha eins.\n\nBeta zwei.\n\nGamma DREI."


def test_neuer_eintrag_form():
    e = js("neu", args=["Autor/Titel", "volltext", {"anfang": "Beta", "absatz_index": 1}, "ersetzen",
                        {"nachher": "Beta!"}, "Beta zwei.", "Hinweis", "geraet-1"])
    assert e["buch"] == "Autor/Titel" and e["ebene"] == "volltext" and e["art"] == "ersetzen"
    assert e["vorher"] == {"hash": ops.pruefsumme("Beta zwei."), "ausschnitt": "Beta zwei."}
    assert e["nachher"] == "Beta!" and e["hinweis"] == "Hinweis" and e["geraet"] == "geraet-1"
    assert e["status"] == "offen" and len(e["id"]) == 12
    assert e["parameter"] == {"nachher": "Beta!"} and e["ziel"]["anfang"] == "Beta"
    assert len(e["erstellt"]) == 24 and e["erstellt"].endswith("Z")      # mit Millisekunden


# ---- Speicher, Senden, Stand, Zaehler (Task 7) ---------------------------------------------------------

SKRIPT_ASYNC = r"""
const R = require(process.argv[1]);
const code = require("fs").readFileSync(0, "utf8");
const kvBau = () => { const m = new Map(); return { m, get: async (k) => m.get(k), set: async (k, v) => { m.set(k, v); } }; };
(async () => {
  const aus = await (new Function("R", "kvBau", "return (async () => {" + code + "})();"))(R, kvBau);
  process.stdout.write(JSON.stringify(aus === undefined ? null : aus));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
"""


def js_async(code: str):
    lauf = subprocess.run([NODE, "-e", SKRIPT_ASYNC, str(HIER / "redaktion.js")], input=code,
                          capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(lauf.stdout)


def test_zaehler_trennt_markierungen_von_aenderungen():
    erg = js_async("""
      const e = (art, status) => ({ id: art + status, art, status });
      return R.zaehler([e("ersetzen", "offen"), e("marke", "offen"), e("marke", "gesendet"),
                        e("verbinden", "gesendet"), e("loeschen", "angewendet"), e("trennen", "offen")]);
    """)
    assert erg == {"aenderungen": 4, "markierungen": 2, "wartend": 3}
    assert js_async("return R.zaehler([]);") == {"aenderungen": 0, "markierungen": 0, "wartend": 0}


def test_zaehler_zaehlt_ruecknahmen_und_zurueckgenommene_nicht_als_aenderung():
    erg = js_async("""
      const e = (id, art, status, par) => ({ id, art, status, parameter: par || {}, ziel: {} });
      // Neu anwenden: alter Konflikt, neuer Eintrag, Ruecknahme des alten
      const neuAnwenden = [e("alt", "ersetzen", "konflikt"), e("neu", "ersetzen", "offen"), e("r", "ruecknahme", "offen", { id: "alt" })];
      // Ruecknahme zu spaet: Ziel ist schon angewendet und bleibt eine Aenderung
      const zuSpaet = [e("a", "ersetzen", "angewendet"), e("r", "ruecknahme", "konflikt", { id: "a" })];
      return { neuAnwenden: R.zaehler(neuAnwenden), zuSpaet: R.zaehler(zuSpaet),
               wirksam: R.wirksame(neuAnwenden).map((x) => x.id) };
    """)
    assert erg["neuAnwenden"] == {"aenderungen": 1, "markierungen": 0, "wartend": 2}
    assert erg["zuSpaet"] == {"aenderungen": 1, "markierungen": 0, "wartend": 0}
    assert erg["wirksam"] == ["neu"]


def test_zuruecknehmen_offener_wird_entfernt_gesendeter_bekommt_ruecknahme():
    erg = js_async("""
      const mk = (id, status, extra) => Object.assign({ id, buch: "A/T", ebene: "chunk-orig", art: "marke", status,
        ziel: { chunk: 2, anfang: "Alpha", absatz_index: 0 }, parameter: {} }, extra || {});
      const liste = [mk("a", "offen"), mk("b", "gesendet"), mk("c", "bestaetigt")];
      const kopie = JSON.stringify(liste);
      const ohneA = R.zuruecknehmen(liste, "a", { geraet: "g" });
      const ohneB = R.zuruecknehmen(liste, "b", { geraet: "g" });
      return { unveraendert: JSON.stringify(liste) === kopie, ohneA, ohneB, unbekannt: R.zuruecknehmen(liste, "x") };
    """)
    assert erg["unveraendert"]
    assert [e["id"] for e in erg["ohneA"]] == ["b", "c"]                     # offen: nie gesendet, keine Spur
    assert [e["id"] for e in erg["ohneB"][:2]] == ["a", "c"] and len(erg["ohneB"]) == 3
    r = erg["ohneB"][2]
    assert r["art"] == "ruecknahme" and r["parameter"] == {"id": "b"} and r["status"] == "offen"
    assert r["buch"] == "A/T" and r["ebene"] == "chunk-orig" and r["ziel"]["chunk"] == 2 and r["geraet"] == "g"
    assert [e["id"] for e in erg["unbekannt"]] == ["a", "b", "c"]


def test_zuruecknehmen_laesst_angewendeten_und_ruecknahmen_stehen():
    erg = js_async("""
      const liste = [{ id: "a", art: "ersetzen", status: "angewendet", ziel: { chunk: 1 }, parameter: {} },
                     { id: "r", art: "ruecknahme", status: "offen", ziel: { chunk: 1 }, parameter: { id: "zzz" } }];
      return { a: R.zuruecknehmen(liste, "a"), r: R.zuruecknehmen(liste, "r"), liste };
    """)
    assert erg["a"] == erg["liste"] and erg["r"] == erg["liste"]


def test_zuruecknehmen_markiert_abhaengige_als_konflikt():
    erg = js_async("""
      const ziel = (anfang, extra) => Object.assign({ chunk: 1, anfang, absatz_index: 0 }, extra || {});
      const e = (id, art, z, par, status) => ({ id, buch: "A/T", ebene: "chunk-orig", art, ziel: z, parameter: par || {}, status: status || "offen" });
      const liste = [
        e("a", "ersetzen", ziel("Alpha alt"), { nachher: "Alpha neu" }),
        e("b", "verbinden", ziel("Alpha neu", { zeile: 0 })),                   // baut auf dem Ergebnis von a auf
        e("c", "loeschen", ziel("Alpha neu", { zeile: 1 })),                    // Folgekette
        e("d", "ersetzen", Object.assign(ziel("Beta"), { absatz_index: 1 }), { nachher: "Beta!" }),   // unbeteiligt
        e("m", "marke", ziel("Alpha neu"), { kategorie: "x" }),                 // Marke: keine Textwirkung
        e("f", "ersetzen", Object.assign(ziel("Alpha neu"), { chunk: 9 }), { nachher: "y" }),         // anderer Chunk
      ];
      return R.zuruecknehmen(liste, "a");
    """)
    stati = {x["id"]: x["status"] for x in erg}
    assert stati == {"b": "konflikt", "c": "konflikt", "d": "offen", "m": "offen", "f": "offen"}
    assert next(x for x in erg if x["id"] == "b")["grund"].endswith("Eintrag a")
    assert [x["id"] for x in erg] == ["b", "c", "d", "m", "f"]            # nichts geloescht


def test_speicher_gibt_nach_speichern_dasselbe_zurueck():
    erg = js_async("""
      const kv = kvBau(), sp = R.speicher(kv);
      const leer = await sp.laden("k001");
      const liste = [{ id: "a", status: "offen" }, { id: "b", status: "gesendet" }];
      await sp.speichern("k001", liste);
      return { leer, zurueck: await sp.laden("k001"), anderes: await sp.laden("k002"), schluessel: [...kv.m.keys()] };
    """)
    assert erg["leer"] == [] and erg["anderes"] == []
    assert erg["zurueck"] == [{"id": "a", "status": "offen"}, {"id": "b", "status": "gesendet"}]
    assert erg["schluessel"] == ["redaktion:k001"]


def test_sende_schickt_header_und_body_und_gibt_angenommen_zurueck():
    erg = js_async("""
      const aufrufe = [];
      const f = async (url, opt) => { aufrufe.push({ url, opt }); return { ok: true, status: 200, json: async () => ({ angenommen: ["a", "b"] }) }; };
      const r = await R.sende([{ id: "a" }, { id: "b" }], { adresse: "http://apic:8080/", token: "T0K", buch: "Autor/Titel", geraet: "epistopheles" }, f);
      return { r, aufrufe };
    """)
    assert erg["r"] == {"angenommen": ["a", "b"]}
    (aufruf,) = erg["aufrufe"]
    assert aufruf["url"] == "http://apic:8080/api/aenderungen"
    assert aufruf["opt"]["method"] == "POST"
    assert aufruf["opt"]["headers"]["X-Redaktion-Token"] == "T0K"
    assert aufruf["opt"]["headers"]["Content-Type"].startswith("application/json")
    assert json.loads(aufruf["opt"]["body"]) == {"geraet": "epistopheles", "buch": "Autor/Titel",
                                                  "eintraege": [{"id": "a"}, {"id": "b"}]}


def test_sende_lehnt_bei_netzfehler_und_fehlerstatus_ab_und_laesst_speicher_unveraendert():
    erg = js_async("""
      const kv = kvBau(), sp = R.speicher(kv);
      await sp.speichern("k001", [{ id: "a", status: "offen" }]);
      const opt = { adresse: "http://apic", token: "t", buch: "A/T", geraet: "g" };
      const netz = await R.sende([{ id: "a" }], opt, async () => { throw new TypeError("Failed to fetch"); }).then(() => "ok", (e) => String(e.message));
      const s401 = await R.sende([{ id: "a" }], opt, async () => ({ ok: false, status: 401, json: async () => ({}) })).then(() => "ok", (e) => String(e.message));
      return { netz, s401, danach: await sp.laden("k001") };
    """)
    assert "Failed to fetch" in erg["netz"] and "401" in erg["s401"]
    assert erg["danach"] == [{"id": "a", "status": "offen"}]


OPT = '{ adresse: "http://apic", token: "t", buch: "A/T", geraet: "g" }'


def test_sende_stapel_markiert_alle_ids_auch_wenn_angenommen_leer_ist():
    erg = js_async("""
      const f = async () => ({ ok: true, status: 200, json: async () => ({ angenommen: [] }) });
      return await R.sendeStapel([{ id: "a" }, { id: "b" }], %s, f);
    """ % OPT)
    assert erg == {"gesendet": ["a", "b"], "fehler": None}


def test_sende_stapel_halbiert_bei_400_und_blockiert_nicht_alles():
    erg = js_async("""
      const aufrufe = [];
      const f = async (url, opt) => {
        const ids = JSON.parse(opt.body).eintraege.map((e) => e.id); aufrufe.push(ids.length);
        if (ids.includes("schlecht")) return { ok: false, status: 400, json: async () => ({}) };
        return { ok: true, status: 200, json: async () => ({ angenommen: ids }) };
      };
      const r = await R.sendeStapel([{ id: "a" }, { id: "schlecht" }, { id: "c" }, { id: "d" }], %s, f);
      return { r, aufrufe };
    """ % OPT)
    assert sorted(erg["r"]["gesendet"]) == ["a", "c", "d"]
    assert erg["r"]["fehler"] == {"art": "server", "code": 400}
    assert erg["aufrufe"][0] == 4 and 1 in erg["aufrufe"]


def test_sende_stapel_fehlerarten_token_netz_server():
    erg = js_async("""
      const st = (code) => async () => ({ ok: false, status: code, json: async () => ({}) });
      const e = [{ id: "a" }, { id: "b" }];
      return {
        t401: await R.sendeStapel(e, %(o)s, st(401)), t403: await R.sendeStapel(e, %(o)s, st(403)),
        s500: await R.sendeStapel(e, %(o)s, st(500)),
        netz: await R.sendeStapel(e, %(o)s, async () => { throw new TypeError("Failed to fetch"); }),
      };
    """ % {"o": OPT})
    assert erg["t401"] == {"gesendet": [], "fehler": {"art": "token", "code": 401}}
    assert erg["t403"]["fehler"] == {"art": "token", "code": 403}
    assert erg["s500"] == {"gesendet": [], "fehler": {"art": "server", "code": 500}}
    assert erg["netz"] == {"gesendet": [], "fehler": {"art": "netz", "code": 0}}


def test_stand_fragt_buch_mit_token_ab_und_liefert_die_stands_tabelle():
    erg = js_async("""
      const aufrufe = [];
      const f = async (url, opt) => { aufrufe.push({ url, opt }); return { ok: true, status: 200, json: async () => ({ stand: { a: { status: "angewendet", grund: "" } } }) }; };
      const r = await R.stand("Autor, X/Über Dinge", { adresse: "http://apic:8080", token: "T" }, f);
      return { r, aufrufe };
    """)
    assert erg["r"] == {"a": {"status": "angewendet", "grund": ""}}
    (aufruf,) = erg["aufrufe"]
    assert aufruf["url"] == "http://apic:8080/api/stand?buch=" + "Autor%2C%20X%2F%C3%9Cber%20Dinge"
    assert aufruf["opt"]["headers"]["X-Redaktion-Token"] == "T"


def test_auftrag_ruft_post_mit_token_und_gibt_id_zurueck():
    erg = js_async("""
      const aufrufe = [];
      const f = async (url, opt) => { aufrufe.push({ url, opt }); return { ok: true, status: 200, json: async () => ({ id: "ab12" }) }; };
      const r = await R.auftrag("Autor, Über/Titel", 3, { adresse: "http://apic:8080/", token: "T0K" }, f);
      return { r, aufrufe };
    """)
    assert erg["r"] == {"id": "ab12"}
    (aufruf,) = erg["aufrufe"]
    assert aufruf["url"] == "http://apic:8080/api/auftraege"
    assert aufruf["opt"]["method"] == "POST"
    assert aufruf["opt"]["headers"]["X-Redaktion-Token"] == "T0K"
    assert aufruf["opt"]["headers"]["Content-Type"].startswith("application/json")
    assert json.loads(aufruf["opt"]["body"]) == {"art": "neu-uebersetzen", "buch": "Autor, Über/Titel", "chunk": 3}


def test_auftrag_lehnt_ungueltigen_chunk_fehler_und_antworten_ohne_id_ab():
    erg = js_async("""
      const o = { adresse: "http://apic", token: "t" };
      const ok = (d) => async () => ({ ok: true, status: 200, json: async () => d });
      const fehler = (p) => p.then(() => "ok", (e) => ({ m: String(e.message), s: e.status }));
      return {
        negativ: await fehler(R.auftrag("A/T", -1, o, ok({ id: "x" }))),
        text: await fehler(R.auftrag("A/T", "1", o, ok({ id: "x" }))),
        ohneId: await fehler(R.auftrag("A/T", 1, o, ok({}))),
        s401: await fehler(R.auftrag("A/T", 1, o, async () => ({ ok: false, status: 401, json: async () => ({}) }))),
        netz: await fehler(R.auftrag("A/T", 1, o, async () => { throw new TypeError("Failed to fetch"); })),
      };
    """)
    assert "chunk" in erg["negativ"]["m"] and "chunk" in erg["text"]["m"]
    assert "Auftrags-Id" in erg["ohneId"]["m"]
    assert erg["s401"]["s"] == 401
    assert "Failed to fetch" in erg["netz"]["m"] and "s" not in erg["netz"]       # kein HTTP-Status: Netzfehler


def test_auftrag_status_fragt_id_mit_token_ab():
    erg = js_async("""
      const aufrufe = [];
      const f = async (url, opt) => { aufrufe.push({ url, opt }); return { ok: true, status: 200, json: async () => ({ zustand: "fehler", meldung: "kaputt" }) }; };
      const r = await R.auftragStatus("ab12", { adresse: "http://apic:8080", token: "T" }, f);
      const schlecht = await R.auftragStatus("x", { adresse: "http://apic", token: "t" },
        async () => ({ ok: true, status: 200, json: async () => ({ zustand: "irgendwas" }) })).then(() => "ok", (e) => String(e.message));
      const s404 = await R.auftragStatus("x", { adresse: "http://apic", token: "t" },
        async () => ({ ok: false, status: 404, json: async () => ({}) })).then(() => "ok", (e) => e.status);
      return { r, aufrufe, schlecht, s404 };
    """)
    assert erg["r"] == {"zustand": "fehler", "meldung": "kaputt"}
    (aufruf,) = erg["aufrufe"]
    assert aufruf["url"] == "http://apic:8080/api/auftraege/ab12"
    assert aufruf["opt"]["method"] == "GET" and aufruf["opt"]["headers"]["X-Redaktion-Token"] == "T"
    assert "Zustand" in erg["schlecht"] and erg["s404"] == 404


def test_vorschlag_gibt_alt_und_neu_zurueck():
    erg = js_async("""
      const aufrufe = [];
      const f = async (url, opt) => { aufrufe.push({ url, opt }); return { ok: true, status: 200, json: async () => ({ alt: "Alt äö", neu: "Neu ß" }) }; };
      const r = await R.vorschlag("Autor, X/Über Dinge", 12, { adresse: "http://apic:8080/", token: "T" }, f);
      const kaputt = await R.vorschlag("A/T", 0, { adresse: "http://apic", token: "t" },
        async () => ({ ok: true, status: 200, json: async () => ({ alt: "nur alt" }) })).then(() => "ok", (e) => String(e.message));
      const s404 = await R.vorschlag("A/T", 0, { adresse: "http://apic", token: "t" },
        async () => ({ ok: false, status: 404, json: async () => ({}) })).then(() => "ok", (e) => e.status);
      return { r, aufrufe, kaputt, s404 };
    """)
    assert erg["r"] == {"alt": "Alt äö", "neu": "Neu ß"}
    (aufruf,) = erg["aufrufe"]
    assert aufruf["url"] == "http://apic:8080/api/vorschlag?buch=Autor%2C%20X%2F%C3%9Cber%20Dinge&chunk=12"
    assert aufruf["opt"]["method"] == "GET" and aufruf["opt"]["headers"]["X-Redaktion-Token"] == "T"
    assert "Vorschlag" in erg["kaputt"] and erg["s404"] == 404


def test_uebernehme_stand_ruecknahme_uebersprungen_ist_erledigt():
    erg = js_async("""
      const liste = [
        { id: "a", art: "ersetzen", status: "gesendet" },
        { id: "r", art: "ruecknahme", status: "gesendet" },
        { id: "m", art: "marke", status: "gesendet" },
        { id: "k", art: "ersetzen", status: "konflikt" },
        { id: "o", art: "ersetzen", status: "offen" },
      ];
      const stand = { a: { status: "bestaetigt" }, r: { status: "uebersprungen", grund: "Ziel nie angewendet" },
                      m: { status: "uebersprungen" }, k: { status: "bestaetigt" }, o: { status: "angewendet" } };
      const neu = R.uebernehmeStand(liste, stand);
      return { neu: neu.map((e) => [e.id, e.status, e.grund || ""]), braucht: R.brauchtStand(liste), danach: R.brauchtStand(neu),
               nurRuecknahme: R.brauchtStand(R.uebernehmeStand([liste[1]], stand)) };
    """)
    assert erg["neu"] == [["a", "bestaetigt", ""], ["r", "uebersprungen", "Ziel nie angewendet"],
                          ["m", "gesendet", ""], ["k", "konflikt", ""], ["o", "offen", ""]]
    assert erg["braucht"] is True
    assert erg["danach"] is True            # a (bestaetigt) und m (gesendet) warten weiter
    assert erg["nurRuecknahme"] is False    # eine uebersprungene Ruecknahme wird nicht mehr abgefragt


def test_auftrag_und_vorschlag_tragen_den_lektor_schluessel_wenn_gesetzt():
    erg = js_async("""
      const aufrufe = [];
      const f = async (url, opt) => { aufrufe.push({ url, body: opt.body }); return { ok: true, status: 200,
        json: async () => ({ id: "ab", alt: "a", neu: "n" }) }; };
      const o = { adresse: "http://apic:8080", token: "T", lektor: "Cathy O'Neil/Weapons of Math Destruction" };
      await R.auftrag("O'Neil, Cathy/Weapons", 3, o, f);
      await R.vorschlag("O'Neil, Cathy/Weapons", 3, o, f);
      await R.auftrag("A/T", 1, { adresse: "http://apic:8080", token: "T" }, f);
      await R.vorschlag("A/T", 1, { adresse: "http://apic:8080", token: "T" }, f);
      return aufrufe;
    """)
    assert json.loads(erg[0]["body"])["lektor"] == "Cathy O'Neil/Weapons of Math Destruction"
    assert "&lektor=Cathy%20O'Neil%2FWeapons%20of%20Math%20Destruction" in erg[1]["url"]
    assert "lektor" not in json.loads(erg[2]["body"])
    assert "lektor" not in erg[3]["url"]


def test_fussnote_kennungen_und_kontext_randfaelle_wie_python():
    text = "Kopf\n\nDer Satz 😀😀 hat eine Note[^1] und mehr."
    faelle = []
    for neu in ["a", "1.2", "x y", "x\ty", "", " ", "a[b", "a]b", "^x", "a^", "Ä", "\U0001F600", "a:b"]:
        faelle.append({"text": text, "eintrag": _eintrag(text, 1, "fussnote",
                       {"aktion": "marker-umbenennen", "alt": "1", "neu": neu, "vorkommen": 0})})
    for nach in ["Satz 😀😀 hat", "😀😀 hat e", "hat eine Note", "hat eine", "ine Note[^1] u"]:
        faelle.append({"text": text, "eintrag": _eintrag(text, 1, "fussnote",
                       {"aktion": "marker-setzen", "id": "k", "nach": nach})})
    erg = js("wendeAn", faelle=faelle)
    for f, e in zip(faelle, erg):
        py = ops.wende_an(f["text"], f["eintrag"])
        assert (e["text"], e["status"]) == (py.text, py.status), f["eintrag"]["parameter"]


def test_trennen_mit_kontext_randfaelle_wie_python():
    faelle = []
    for absatz, nach in [("Vorne 😀😀 hinten   und weiter", "Vorne 😀😀 hinten"),
                         ("Vorne 😀😀 hinten\x1c\x1d und weiter", "Vorne 😀😀 hinten"),
                         ("Satz eins.　　Satz zwei.", "Satz eins."),
                         ("Satz eins.​Satz zwei.", "Satz eins."),         # Nullbreiten-Leerzeichen ist kein Leerraum
                         ("Ä-Satz endet.  \tNächster Satz.", "Ä-Satz endet."),
                         ("Nur ein Satz am Ende. ", "Nur ein Satz am Ende.")]:
        text = f"Kopf\n\n{absatz}\n\nSchluss"
        faelle.append({"text": text, "eintrag": _eintrag(text, 1, "trennen", {"nach": nach})})
    erg = js("wendeAn", faelle=faelle)
    for f, e in zip(faelle, erg):
        py = ops.wende_an(f["text"], f["eintrag"])
        assert (e["text"], e["status"]) == (py.text, py.status), f["eintrag"]["parameter"]


def test_neuer_eintrag_zeit_hat_millisekunden_und_steigt_streng():
    erg = js_async("""
      const z = [];
      for (let i = 0; i < 200; i++) z.push(R.neuerEintrag("A/T", "volltext", { anfang: "x" }, "marke", {}, "x", "", "g").erstellt);
      return z;
    """)
    import re
    assert all(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", z) for z in erg)
    assert erg == sorted(set(erg))
