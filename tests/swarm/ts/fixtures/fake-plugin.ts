/**
 * Deterministic fake plugin for the swarm real-daemon E2E tests (WP-3.10).
 *
 * Copied from `tests/rpc/ts/fixtures/fake-plugin.ts` (per the brief: copy, do not
 * import across test suites) and adapted to expose one blocking gate whose
 * result depends on the IR state. The scripted provider fixes the gate by
 * patching `/electrical/ready` to `true`.
 *
 * Everything is deterministic; no hardware kernel, vendor service, LLM or GUI is used.
 */

/** Python module name referenced by the manifest's `runtime.python`. */
export const FAKE_PLUGIN_MODULE = "fake_swarm_plugin";

/** Plugin name (kebab-case, per the frozen manifest contract). */
export const FAKE_PLUGIN_NAME = "swarm-fake";

/** The Python implementation copied into the temp project as `fake_swarm_plugin.py`. */
export const FAKE_PLUGIN_SOURCE = `"""Deterministic fake plugin for atomc swarm E2E tests (no hardware)."""

from __future__ import annotations

from typing import Any

PLUGIN_NAME = "swarm-fake"

EMPTY_ELECTRICAL = {
    "_meta": {"rev": 0, "lock": None},
    "source": {"kind": "atopile", "entry": "main.ato:App"},
    "components": [],
    "nets": [],
    "assertions": [],
    "erc": [],
    "ready": False,
}


class SwarmFakePlugin:
    """One watch and one blocking gate whose result follows /electrical/ready."""

    def refresh(self, ctx: Any) -> dict[str, Any]:
        return {"refreshed": True, "plugin": PLUGIN_NAME}

    async def check_ready(self, ctx: Any) -> dict[str, Any]:
        try:
            current = await ctx.ir_read("/electrical")
            value = current["value"]
        except Exception:
            value = None
        nets = value.get("nets", []) if isinstance(value, dict) else []
        if isinstance(nets, list) and len(nets) > 0:
            return {
                "status": "PASS",
                "summary": "electrical has nets",
                "evidence": [{"kind": "text", "message": "nets present"}],
            }
        return {
            "status": "FAIL",
            "summary": "electrical has no nets",
            "suggestions": [{"message": "add a net to /electrical/nets"}],
        }

    async def read_status(self, ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        return {"result": {"ok": True, "plugin": PLUGIN_NAME}}


plugin = SwarmFakePlugin()
plugin.__atomc_node_handlers__ = {"swarm-fake:refresh": plugin.refresh}
`;

const EMPTY_INPUT_SCHEMA = {
  type: "object",
  properties: {},
  additionalProperties: false,
} as const;

/** Frozen-contract-valid `atomc-plugin.json` payload. */
export const FAKE_MANIFEST = {
  manifest_version: "0.1.0",
  name: FAKE_PLUGIN_NAME,
  version: "0.1.0",
  description: "deterministic fake plugin for swarm E2E tests",
  atomc: ">=0.0.1 <0.2.0",
  runtime: { python: `${FAKE_PLUGIN_MODULE}:plugin` },
  watches: [{ id: "swarm-fake:refresh", ir: ["/keyboard"], files: [], debounce_ms: 0 }],
  produces: ["/electrical"],
  gates: [
    {
      id: "gate:swarm-e2e.ready",
      severity: "blocking",
      owner_agent: "ee-agent",
      after: ["swarm-fake:refresh"],
      handler: "check_ready",
    },
  ],
  tools: [
    {
      name: "read_status",
      description: "Return a deterministic plugin status",
      input_schema: EMPTY_INPUT_SCHEMA,
      agents: ["ee-agent", "ops-agent"],
      mutates: false,
      handler: "read_status",
    },
  ],
  cli: [],
  ui: [],
} as const;
