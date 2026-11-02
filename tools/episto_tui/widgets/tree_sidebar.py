from __future__ import annotations
from pathlib import Path
from rich.text import Text
from textual.content import Content
from textual.widgets import Tree
from textual.message import Message
from episto_tui import library
from episto_tui.models import Buch, Kapitel

# Nur diese beiden Felder werden bibliotheksweit zusammengefuehrt: these/
# gegen/beleg haben in den Tagging-Daten keine feste Laenge/Zuordnung
# zueinander (siehe dok/2026-09-27-sidebar-buchuebergreifend-design.md).
_BEGRIFF_FELDER = ["kern", "def_"]
_BEGRIFF_ART = {"kern": "Kernbegriff", "def_": "Definition"}

# Unterhalb dieser Filterlaenge bleibt der Begriffe-Knoten leer (nur ein
# Hinweis-Blatt): bei 30+ Buechern waechst die flache, buchuebergreifende
# Liste in die Tausende und macht den Baum ungenutzt unuebersichtlich.
_BEGRIFFE_MIN_FILTER_LAENGE = 2


class ChapterSelected(Message):
    """Kapitel gewaehlt. Kommt die Wahl aus "Begriffe & Definitionen", tragen
    begriff/begriff_art den angeklickten Eintrag, damit die Oberflaeche die
    Herkunft des Textes anzeigen kann."""

    def __init__(self, buch: Buch, kapitel: Kapitel, begriff: str | None = None,
                 begriff_art: str | None = None, absatz_index: int | None = None) -> None:
        self.buch = buch
        self.kapitel = kapitel
        self.begriff = begriff
        self.begriff_art = begriff_art
        # Gesetzt von der Volltextsuche: der Lesebereich scrollt zu diesem Absatz.
        self.absatz_index = absatz_index
        super().__init__()


class LibraryTree(Tree):
    def __init__(self, root: Path) -> None:
        super().__init__("Wurzel")
        # Der echte Tree-Root ist nur ein unsichtbarer Behaelter: "Bibliothek"
        # und "Begriffe & Definitionen" haengen als gleichrangige, sichtbare
        # Kinder darunter, statt dass Buecher direkt am Root haengen.
        self.show_root = False
        self.root_pfad = root
        self.filter_text = ""
        # Tippmodus: nur darin schluckt der Baum druckbare Zeichen (siehe on_key).
        self.filter_aktiv = False

    def on_mount(self) -> None:
        self.rebuild()
        # show_root=False setzt Textuals cursor_line intern auf -1 statt 0
        # (siehe Tree.watch_show_root); ohne diese Zeile braucht man vom
        # Start bis zum ersten Kapitel-Blatt einen "down"-Tastendruck mehr.
        self.cursor_line = 0

    def rebuild(self) -> None:
        # Aufklapp-Zustand der beiden Top-Level-Knoten merken, bevor sie
        # (mitsamt ihren Kindern) verworfen und neu aufgebaut werden -- sonst
        # wirft jeder Tastendruck der Tippfilterung (die rebuild() aufruft)
        # einen manuell aufgeklappten Knoten wieder zu. Beim allerersten
        # Aufruf (self.root.children ist noch leer) gelten die bisherigen
        # Defaults: "Bibliothek" offen, "Begriffe & Definitionen" zu.
        if self.root.children:
            bibliothek_offen = self.root.children[0].is_expanded
            begriffe_offen = self.root.children[1].is_expanded
        else:
            bibliothek_offen = True
            begriffe_offen = False
        self.root.remove_children()
        buecher = library.discover_books(self.root_pfad)
        filter_lower = self.filter_text.lower()
        self._baue_bibliothek_knoten(buecher, filter_lower, bibliothek_offen)
        self._baue_begriffe_knoten(buecher, filter_lower, begriffe_offen)
        self.root.expand()
        self._zeige_filter()

    def zeige_kapitel(self, buch: Buch, kapitel: Kapitel) -> bool:
        """Setzt den Cursor auf das Kapitel unter "Bibliothek" (ohne es neu zu
        laden). Ein aktiver Filter wird geloescht, sonst koennte das Kapitel
        ausgeblendet sein. Gibt False zurueck, wenn es nicht (mehr) existiert."""
        if self.filter_text:
            self.filter_text = ""
            self.rebuild()
        bibliothek = self.root.children[0]
        for buch_knoten in bibliothek.children:
            for blatt in buch_knoten.children:
                if blatt.data is None:
                    continue
                blatt_buch, blatt_kapitel, *_ = blatt.data
                if blatt_buch.pfad == buch.pfad and blatt_kapitel.datei == kapitel.datei:
                    bibliothek.expand()
                    buch_knoten.expand()
                    # Erst nach dem Neuaufbau der Zeilen ist die Zeilennummer
                    # des Blatts gueltig.
                    self.call_after_refresh(self.move_cursor, blatt)
                    return True
        return False

    def _zeige_filter(self) -> None:
        # Die Tippfilterung hat kein eigenes Eingabefeld: ohne Anzeige sieht man
        # nicht, was man getippt hat (besonders beim Begriffe-Knoten, der erst ab
        # _BEGRIFFE_MIN_FILTER_LAENGE Zeichen etwas zeigt). Die Kopfzeile des
        # Baums (border_title) traegt den Filter. Content(...) statt str: der
        # Text ist Nutzereingabe und darf nicht als Markup gelesen werden
        # ("[/]" wuerde sonst die Anzeige zerstoeren).
        if self.filter_aktiv:
            text = f"Filter: {self.filter_text}_  (Enter: übernehmen · Esc: löschen)"
        elif self.filter_text:
            text = f"Filter: {self.filter_text}  (/: ändern · Esc: löschen)"
        else:
            text = "/ drücken zum Filtern"
        self.border_title = Content(text)

    def _baue_bibliothek_knoten(self, buecher: list[Buch], filter_lower: str, expand: bool) -> None:
        bibliothek_knoten = self.root.add(Text("Bibliothek"), expand=expand)
        for buch in buecher:
            kapitel_liste = library.list_chapters(buch)
            passende = [
                k for k in kapitel_liste
                if not filter_lower
                or filter_lower in buch.titel.lower()
                or filter_lower in buch.autor.lower()
                or filter_lower in k.titel.lower()
            ]
            if not passende:
                continue
            # Text(...) statt str: Tree liest str-Labels als Rich-Markup; Titel
            # sind Daten und sollen woertlich erscheinen ("[/]" wuerde crashen).
            # Beim Start (kein Filter) eingeklappt; waehrend der Tippfilterung
            # aufgeklappt, damit passende Kapitel sofort sichtbar sind.
            buch_knoten = bibliothek_knoten.add(Text(f"{buch.autor} — {buch.titel}"), expand=bool(filter_lower))
            for kapitel in passende:
                buch_knoten.add_leaf(Text(f"{kapitel.nr}. {kapitel.titel}"), data=(buch, kapitel))

    def _baue_begriffe_knoten(self, buecher: list[Buch], filter_lower: str, expand: bool) -> None:
        # Flach und bibliotheksweit, bewusst OHNE Buch-Zwischenknoten (siehe
        # Design-Doc): Kernbegriffe und Definitionen werden nicht verknuepft
        # oder zusammengefuehrt, jedes Vorkommen bleibt ein eigenes Blatt.
        begriffe_knoten = self.root.add(Text("Begriffe & Definitionen"), expand=expand)
        if len(filter_lower) < _BEGRIFFE_MIN_FILTER_LAENGE:
            begriffe_knoten.add_leaf(
                Text(f"Mind. {_BEGRIFFE_MIN_FILTER_LAENGE} Zeichen filtern (/ drücken, dann tippen) …")
            )
            return
        eintraege: list[tuple[str, Buch, Kapitel, str]] = []
        for buch in buecher:
            for tag in library.read_all_tags(buch):
                kapitel = Kapitel(tag.kapitel_nr, tag.titel, tag.datei)
                for feld in _BEGRIFF_FELDER:
                    for text in getattr(tag, feld):
                        if (
                            filter_lower in text.lower()
                            or filter_lower in buch.titel.lower()
                            or filter_lower in buch.autor.lower()
                        ):
                            eintraege.append((text, buch, kapitel, _BEGRIFF_ART[feld]))
        eintraege.sort(key=lambda eintrag: eintrag[0].lower())
        for text, buch, kapitel, art in eintraege:
            begriffe_knoten.add_leaf(Text(text), data=(buch, kapitel, text, art))

    def _setze_filter(self, text: str) -> None:
        self.filter_text = text
        self.rebuild()

    def on_key(self, event) -> None:
        """Tippfilterung als eigener Modus. "/" startet ihn; nur darin werden
        druckbare Zeichen geschluckt. Ausserhalb erreichen Ziffern, "q" usw. die
        App-Bindings auch bei fokussiertem Baum. (Vorher schluckte der Baum
        jedes Zeichen, solange er den Fokus hatte: Hotkeys waren blockiert.)

        Im Modus: Zeichen/Backspace bearbeiten den Filter, Enter beendet den
        Modus (der Filter bleibt) und waehlt den Cursor-Knoten, Esc loescht den
        Filter und beendet den Modus. Pfeiltasten wirken normal."""
        if self.filter_aktiv:
            if event.key == "escape":
                self.filter_aktiv = False
                self._setze_filter("")
                event.stop()
            elif event.key == "enter":
                # Nicht stoppen: der Baum waehlt danach den Cursor-Knoten.
                self.filter_aktiv = False
                self._zeige_filter()
            elif event.key == "backspace":
                self._setze_filter(self.filter_text[:-1])
                event.stop()
            elif event.character and len(event.character) == 1 and event.character.isprintable():
                self._setze_filter(self.filter_text + event.character)
                event.stop()
            return
        if event.character == "/":
            self.filter_aktiv = True
            self._zeige_filter()
            event.stop()
        elif event.key == "escape" and self.filter_text:
            self._setze_filter("")
            event.stop()
        elif event.key == "backspace" and self.filter_text:
            self._setze_filter(self.filter_text[:-1])
            event.stop()

    def on_blur(self) -> None:
        # Fokus woanders: der Tippmodus darf nicht "haengen bleiben".
        if self.filter_aktiv:
            self.filter_aktiv = False
            self._zeige_filter()

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        if event.node.data is not None:
            # Bibliothek-Blaetter tragen (buch, kapitel), Begriffe-Blaetter
            # zusaetzlich (text, art).
            buch, kapitel, *begriff = event.node.data
            self.post_message(ChapterSelected(buch, kapitel, *begriff))
