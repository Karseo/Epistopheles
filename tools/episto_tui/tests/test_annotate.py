from episto_tui.annotate import (
    split_paragraphs, locate_paragraph, maskiere_markdown, render_mit_kommentaren, Segment,
)
from episto_tui.models import Kommentar


def test_split_paragraphs_trennt_an_leerzeilen():
    text = "Erster Absatz.\n\nZweiter Absatz.\n\n\nDritter Absatz."
    assert split_paragraphs(text) == [
        "Erster Absatz.", "Zweiter Absatz.", "Dritter Absatz.",
    ]


def test_locate_paragraph_per_index_wenn_text_passt():
    absaetze = ["Erster Absatz.", "Zweiter Absatz."]
    treffer = locate_paragraph(absaetze, 1, "Zweiter Absatz")
    assert treffer == 1


def test_locate_paragraph_fallback_bei_verschobenem_index():
    absaetze = ["Neuer Absatz davor.", "Erster Absatz.", "Zweiter Absatz."]
    # absatz_index zeigt noch auf die alte Position (0), aber der Text ist jetzt an Position 1
    treffer = locate_paragraph(absaetze, 0, "Erster Absatz")
    assert treffer == 1


def test_locate_paragraph_gibt_none_bei_verwaistem_kommentar():
    absaetze = ["Ganz anderer Text."]
    treffer = locate_paragraph(absaetze, 5, "Text, der nicht mehr vorkommt")
    assert treffer is None


def _k(index, anfang, text="Notiz", erstellt="2026-09-28 10:00"):
    return Kommentar(
        datei="x.md", absatz_index=index, absatz_anfang=anfang,
        text=text, erstellt=erstellt,
    )


def test_maskiere_markdown_maskiert_sonderzeichen():
    roh = "Vgl. [LdF] und [/] *fett* _kursiv_ `code` # > | \\"
    assert maskiere_markdown(roh) == (
        "Vgl. \\[LdF\\] und \\[/\\] \\*fett\\* \\_kursiv\\_ \\`code\\` \\# \\> \\| \\\\"
    )


def test_render_ohne_kommentare_ist_reine_absatzliste():
    text, segmente = render_mit_kommentaren(["Erster Absatz.", "Zweiter Absatz."], [])
    assert text == "Erster Absatz.\n\nZweiter Absatz."
    assert segmente == [Segment(0, "absatz", 0, None), Segment(2, "absatz", 1, None)]


def test_render_haengt_kommentarblock_direkt_unter_den_richtigen_absatz():
    k = _k(1, "Zweiter Absatz")
    text, segmente = render_mit_kommentaren(["Erster Absatz.", "Zweiter Absatz.", "Dritter."], [k])
    assert text == (
        "Erster Absatz.\n\nZweiter Absatz.\n\n> \U0001f4ac Notiz — 2026-09-28 10:00\n\nDritter."
    )
    assert [(s.startzeile, s.art, s.absatz_index) for s in segmente] == [
        (0, "absatz", 0), (2, "absatz", 1), (4, "kommentar", 1), (6, "absatz", 2),
    ]
    assert segmente[2].kommentar == k


def test_render_mehrere_kommentare_je_eigener_block_in_reihenfolge():
    k1, k2 = _k(0, "Erster", "Eins"), _k(0, "Erster", "Zwei")
    text, segmente = render_mit_kommentaren(["Erster Absatz."], [k1, k2])
    assert text == (
        "Erster Absatz.\n\n> \U0001f4ac Eins — 2026-09-28 10:00"
        "\n\n> \U0001f4ac Zwei — 2026-09-28 10:00"
    )
    assert [s.kommentar for s in segmente] == [None, k1, k2]


def test_render_mehrzeiliger_absatz_verschiebt_folgende_startzeilen():
    _text, segmente = render_mit_kommentaren(["Zeile a\nZeile b", "Zweiter."], [_k(0, "Zeile a")])
    assert [(s.startzeile, s.art) for s in segmente] == [
        (0, "absatz"), (3, "kommentar"), (5, "absatz"),
    ]


def test_render_maskiert_kommentartext():
    text, _ = render_mit_kommentaren(["A."], [_k(0, "A.", "Vgl. [LdF] und [/]")])
    assert "Vgl. \\[LdF\\] und \\[/\\]" in text


def test_render_haelt_kommentarblock_einzeilig():
    text, _ = render_mit_kommentaren(["A."], [_k(0, "A.", "eins\nzwei")])
    assert "> \U0001f4ac eins zwei —" in text


def test_render_verwaiste_kommentare_am_kapitelende_unter_eigener_ueberschrift():
    k = _k(9, "Text, der nicht mehr existiert")
    text, segmente = render_mit_kommentaren(["Einziger Absatz."], [k])
    assert text == (
        "Einziger Absatz.\n\n## Kommentare ohne Absatz\n\n> \U0001f4ac Notiz — 2026-09-28 10:00"
    )
    assert [(s.startzeile, s.art, s.absatz_index) for s in segmente] == [
        (0, "absatz", 0), (2, "kopf", None), (4, "kommentar", None),
    ]
    assert segmente[2].kommentar == k
