"""``python -m atomcd`` entry point (delegates to the Typer CLI)."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":  # pragma: no cover
    main()
