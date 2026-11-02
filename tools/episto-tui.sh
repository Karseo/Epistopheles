#!/usr/bin/env sh
# Startet die EPISTO-TUI (Termux, Linux, macOS).
# Ohne EPISTO_ROOT gilt das Elternverzeichnis dieses Skripts, also der
# Wurzelordner der Bibliothek, als Bibliothek. Weitere Argumente (z. B.
# --root PFAD) gehen unveraendert an die TUI; relative Pfade gelten ab dem
# Verzeichnis, aus dem das Skript aufgerufen wird.
hier="$(cd "$(dirname "$0")" && pwd)"
: "${EPISTO_ROOT:=$(dirname "$hier")}"
export EPISTO_ROOT
PYTHONPATH="$hier${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
if python3 -c "" >/dev/null 2>&1; then
    exec python3 -m episto_tui "$@"
fi
exec python -m episto_tui "$@"
