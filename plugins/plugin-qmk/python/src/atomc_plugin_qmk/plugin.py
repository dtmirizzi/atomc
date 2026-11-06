"""Entry point for the ``plugin-qmk`` atomc plugin."""

from __future__ import annotations

from typing import Any

from atomc_plugin_sdk import atomc_plugin

from .gates import (
    compile_gate,
    compile_tool,
    generate_tool,
    matrix_pins_gate,
)
from .manifest import MANIFEST


@atomc_plugin(manifest=MANIFEST)
class QmkPlugin:
    """QMK derivation and compile handlers declared by ``atomc-plugin.json``."""

    async def matrix_pins_match_ir(self, ctx: Any) -> dict[str, Any]:
        return await matrix_pins_gate(ctx)

    async def run_qmk_compile(self, ctx: Any) -> dict[str, Any]:
        return await compile_gate(ctx)

    async def qmk_generate_tool(
        self,
        ctx: Any,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await generate_tool(ctx, payload)

    async def qmk_compile_tool(
        self,
        ctx: Any,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await compile_tool(ctx, payload)


plugin = QmkPlugin

__all__ = ["QmkPlugin", "plugin"]
