"""Make the test helper module importable regardless of the invoking pytest root.

CI runs a single repository-wide ``pytest`` with ``--import-mode=importlib``; that does not put
this directory on ``sys.path``, so the helpers in ``_helpers.py`` are exposed here explicitly.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
