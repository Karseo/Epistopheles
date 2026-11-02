from __future__ import annotations
from textual.message import Message
from episto_tui.models import Buch, Kapitel


class SpringeZu(Message):
    """Eine Ansicht (Themen, Querverweise, Notizen) will ein Kapitel oeffnen,
    optional an einem bestimmten Absatz. Die App oeffnet es im Text-Tab."""

    def __init__(self, buch: Buch, kapitel: Kapitel, absatz_index: int | None = None) -> None:
        self.buch = buch
        self.kapitel = kapitel
        self.absatz_index = absatz_index
        super().__init__()
