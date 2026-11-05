"""Import safety: ``import atomcd.kernels`` must stay cheap, engine-free and fork-free."""

from __future__ import annotations

import json
import subprocess
import sys

HEAVY_MODULES = ("atopile", "faebryk", "OCP", "build123d", "pyrenode3", "pythonnet", "kiutils")

# Import the public package, every lazy adapter module, and the registry; then assert no heavy
# engine was pulled in and no child process was spawned.
_SCRIPT = f"""
import json
import multiprocessing
import sys
import atomcd
import atomcd.kernels
import atomcd.kernels.builtin
import atomcd.kernels.atopile
import atomcd.kernels.kiutils
import atomcd.kernels.ocp
import atomcd.kernels.ocp_engine
import atomcd.kernels.renode
import atomcd.kernels.testing
heavy = [name for name in {HEAVY_MODULES!r} if name in sys.modules]
children = len(multiprocessing.active_children())
print(json.dumps({{"heavy": heavy, "children": children}}))
"""


def test_importing_kernels_is_engine_free_and_fork_free() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["heavy"] == []
    assert payload["children"] == 0


def test_public_package_exposes_registry_helpers() -> None:
    import atomcd.kernels as kernels

    registry = kernels.create_default_registry()
    assert isinstance(registry, kernels.DefaultKernelRegistry)
    assert "ocp" in registry.names()
