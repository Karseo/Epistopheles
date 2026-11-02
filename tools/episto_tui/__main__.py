from __future__ import annotations
import argparse
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from episto_tui import library
from episto_tui.app import EpistoApp


def bestimme_root(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> Path:
    parser = argparse.ArgumentParser(
        prog="episto_tui",
        description="EPISTO-Bibliothek in der Konsole lesen und bearbeiten.",
    )
    parser.add_argument(
        "--root", default=None,
        help="Wurzelordner der Bibliothek (sonst EPISTO_ROOT, sonst Standard je Plattform)",
    )
    args = parser.parse_args(argv)
    return library.resolve_root(args.root, os.environ if env is None else env)


def main(argv: Sequence[str] | None = None) -> None:
    EpistoApp(root=bestimme_root(argv)).run()


if __name__ == "__main__":
    main()
