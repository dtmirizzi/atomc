"""Expose ``_helpers.py`` on ``sys.path`` for importlib-based pytest collection."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
