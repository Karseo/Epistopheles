"""Warteschlange fuer Auftraege auf APIC (Spec 5.2, Task 12).

Aufträge laufen nur auf ausdrücklichen Wunsch und strikt einzeln nacheinander in einem
Hintergrund-Thread. `starte(job)` fuehrt einen Auftrag aus (im Server: Unterprozess mit
`pipeline/chunk-neu-uebersetzen.py`); wirft es, ist der Zustand `fehler`. Der Zustand
liegt nur im Speicher: nach einem Neustart des Empfaengers ist die Warteschlange leer.
Nur Standardbibliothek.
"""
from __future__ import annotations

import secrets
import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import Callable

from redaktion import protokoll

ART_NEU_UEBERSETZEN = "neu-uebersetzen"
ARTEN = (ART_NEU_UEBERSETZEN,)
WARTET, LAEUFT, FERTIG, FEHLER = "wartet", "laeuft", "fertig", "fehler"
MAX_MERKEN = 200      # so viele beendete Auftraege bleiben abfragbar


class Warteschlange:
    def __init__(self, root: Path, starte: Callable[[dict], None],
                 bereinige: Callable[[str], str] | None = None):
        self.root = Path(root)
        self._starte = starte
        self._bereinige = bereinige or (lambda t: t)      # Server: bereinige_meldung (keine Pfade)
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._reihe: deque[str] = deque()
        self._thread: threading.Thread | None = None

    def reiche_ein(self, art: str, buch: str, chunk: int) -> str:
        """Reiht einen Auftrag ein und gibt seine Id zurueck; wirft ValueError bei ungueltigen
        Angaben. Ein gleicher, noch nicht beendeter Auftrag wird nicht doppelt eingereiht."""
        if art not in ARTEN:
            raise ValueError("Unbekannte Art des Auftrags")
        protokoll.eingang_ordner(self.root, buch)         # ValueError bei unsicherem Namen
        if isinstance(chunk, bool) or not isinstance(chunk, int) or chunk < 0:
            raise ValueError("chunk muss eine Zahl ab 0 sein")
        with self._lock:
            for jid, j in self._jobs.items():
                if (j["zustand"] in (WARTET, LAEUFT) and j["art"] == art
                        and j["buch"] == buch and j["chunk"] == chunk):
                    return jid
            jid = secrets.token_hex(8)
            self._jobs[jid] = {"id": jid, "art": art, "buch": buch, "chunk": chunk,
                               "zustand": WARTET, "meldung": ""}
            self._reihe.append(jid)
            self._vergiss_alte()
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._arbeite, daemon=True)
                self._thread.start()
            return jid

    def status(self, id: str) -> dict:
        """`{"zustand", "meldung"}`; wirft KeyError bei unbekannter Id."""
        with self._lock:
            j = self._jobs[id]
            return {"zustand": j["zustand"], "meldung": j["meldung"]}

    def _vergiss_alte(self) -> None:
        beendet = [i for i, j in self._jobs.items() if j["zustand"] in (FERTIG, FEHLER)]
        for i in beendet[: max(0, len(beendet) - MAX_MERKEN)]:
            del self._jobs[i]

    def _meldung(self, e: BaseException) -> str:
        """Kurze, pfadfreie Meldung. Kein Echo von Kommandozeile oder Ausnahmetext ohne Bereinigung."""
        if isinstance(e, subprocess.TimeoutExpired):
            return "Zeitüberschreitung beim Übersetzen"
        try:
            text = self._bereinige(str(e)).strip()
        except Exception:  # noqa: BLE001 - die Meldung darf den Auftrag nie zusaetzlich zerstoeren
            text = ""
        if isinstance(e, RuntimeError) and text:
            return text                                    # eigene, schon bereinigte Meldung des Starters
        return f"{type(e).__name__}: {text}" if text else type(e).__name__

    def _arbeite(self) -> None:
        while True:
            with self._lock:
                if not self._reihe:
                    self._thread = None       # das nächste reiche_ein startet einen neuen Thread
                    return
                jid = self._reihe.popleft()
                job = dict(self._jobs[jid])
                self._jobs[jid]["zustand"] = LAEUFT
            zustand, meldung = FERTIG, ""
            try:
                self._starte(job)
            except BaseException as e:  # noqa: BLE001 - jeder Fehler wird gemeldet, nie verschluckt
                zustand = FEHLER
                meldung = self._meldung(e)
            with self._lock:
                self._jobs[jid]["zustand"] = zustand
                self._jobs[jid]["meldung"] = meldung
