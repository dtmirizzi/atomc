"""atopile / faebryk availability adapter.

atopile 0.15 is in maintenance mode and does not expose a supported public *build* entrypoint.
This adapter therefore reports version/availability and a cheap ``ping``, and refuses ``build``
with an explicit :class:`KernelUnsupportedOperationError` instead of calling an undocumented
internal function. Phase 4's ``plugin-atopile`` owns compilation and may shell out to the ``ato``
CLI as a subprocess.
"""

from __future__ import annotations

from typing import Any

from atomcd.kernels.base import BaseKernel
from atomcd.kernels.errors import KernelUnsupportedOperationError
from atomcd.kernels.health import ProbeResult
from atomcd.kernels.importer import import_module, module_version, probe_modules

_BUILD_DETAIL = (
    "atopile 0.15 exposes no supported public build API; compile via the 'ato' CLI "
    "subprocess adapter instead of an internal function"
)


class AtopileKernel(BaseKernel):
    """Track atopile/faebryk versions without importing them until started."""

    def __init__(self) -> None:
        super().__init__("atopile", package="atopile")
        self._faebryk_version: str | None = None

    def _probe(self) -> ProbeResult:
        return probe_modules("atopile", distribution="atopile")

    async def _start(self) -> None:
        import_module("atopile")
        self._faebryk_version = module_version("faebryk")

    async def _stop(self) -> None:
        self._faebryk_version = None

    async def _call(self, op: str, **kwargs: Any) -> Any:
        if op == "version":
            return {"atopile": self._version, "faebryk": self._faebryk_version}
        if op == "ping":
            return {"pong": True}
        if op == "build":
            raise KernelUnsupportedOperationError(self.name, op, _BUILD_DETAIL)
        raise KernelUnsupportedOperationError(self.name, op, "supported ops: version, ping")


__all__ = ["AtopileKernel"]
