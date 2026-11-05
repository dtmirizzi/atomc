"""Pure-Python KiCad ``.kicad_pcb`` parsing adapter (no KiCad GUI dependency)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from atomcd.kernels.base import BaseKernel
from atomcd.kernels.errors import KernelUnsupportedOperationError
from atomcd.kernels.health import ProbeResult
from atomcd.kernels.importer import import_module, probe_modules


class KiutilsKernel(BaseKernel):
    """Parse boards with ``kiutils`` in-process.

    ``kiutils`` is pure Python and safe to run in the daemon process, so unlike OCP it is not
    isolated in a worker.
    """

    def __init__(self) -> None:
        super().__init__("kiutils", package="kiutils")
        self._board_module: Any = None
        self._boards: dict[str, Any] = {}

    def _probe(self) -> ProbeResult:
        return probe_modules("kiutils", distribution="kiutils")

    async def _start(self) -> None:
        self._board_module = import_module("kiutils.board")

    async def _stop(self) -> None:
        self._boards.clear()
        self._board_module = None

    async def _call(self, op: str, **kwargs: Any) -> Any:
        if op == "version":
            return {"kiutils": self._version}
        if op == "load":
            return self._load(str(kwargs["path"]))
        if op == "summary":
            return self._summary(str(kwargs["path"]))
        raise KernelUnsupportedOperationError(
            self.name, op, "supported ops: version, load, summary"
        )

    def _load(self, path: str) -> dict[str, Any]:
        board_path = Path(path)
        if not board_path.is_file():
            raise FileNotFoundError(f"board not found: {board_path}")
        if self._board_module is None:  # pragma: no cover - call() guarantees _start
            raise RuntimeError("kiutils kernel not started")
        board = self._board_module.Board.from_file(str(board_path))
        self._boards[str(board_path.resolve())] = board
        return self._summarize(board, str(board_path))

    def _summary(self, path: str) -> dict[str, Any]:
        key = str(Path(path).resolve())
        board = self._boards.get(key)
        if board is None:
            return self._load(path)
        return self._summarize(board, path)

    @staticmethod
    def _summarize(board: Any, path: str) -> dict[str, Any]:
        footprints = list(getattr(board, "footprints", []) or [])
        return {
            "path": path,
            "footprint_count": len(footprints),
            "footprints": [
                {
                    "reference": str(getattr(fp, "lib_id", "")),
                    "value": str(getattr(fp, "value", "")),
                }
                for fp in footprints
            ],
        }


__all__ = ["KiutilsKernel"]
