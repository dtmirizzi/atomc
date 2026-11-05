/**
 * Deterministic fake plugin used by the RPC contract tests.
 *
 * `DaemonHarness` writes `FAKE_PLUGIN_SOURCE` into each temporary project root and
 * `FAKE_MANIFEST` into `plugins/rpc-fake/atomc-plugin.json`. The daemon discovers it,
 * imports `fake_rpc_plugin:plugin` with the project root on `PYTHONPATH`, and registers:
 *
 * - one watch (`rpc-fake:refresh`, invalidated by `/keyboard`; the mutating tool
 *   writes `/electrical`, so ordinary IR tests never trigger a reactive DAG run),
 * - two gates (`gate:rpc-fake.ok` PASS, `gate:rpc-fake.fail` advisory FAIL),
 * - one read-only tool (`read_status`),
 * - one mutating tool (`add_net`), scoped to its declared `/electrical` `produces`.
 *
 * Everything is deterministic; no hardware kernel, vendor service, LLM or GUI is used.
 */

/** Python module name referenced by the manifest's `runtime.python`. */
export const FAKE_PLUGIN_MODULE = "fake_rpc_plugin";

/** Plugin name (kebab-case, per the frozen manifest contract). */
export const FAKE_PLUGIN_NAME = "rpc-fake";

/** The Python implementation copied into the temp project as `fake_rpc_plugin.py`. */
export const FAKE_PLUGIN_SOURCE = `"""Deterministic fake plugin for atomc RPC contract tests (no hardware)."""

from __future__ import annotations

from typing import Any

PLUGIN_NAME = "rpc-fake"

EMPTY_ELECTRICAL = {
    "_meta": {"rev": 0, "lock": None},
    "source": {"kind": "atopile", "entry": "main.ato:App"},
    "components": [],
    "nets": [],
    "assertions": [],
    "erc": [],
}


class RpcFakePlugin:
    """One watch, two gates, one read tool and one mutating tool."""

    def refresh(self, ctx: Any) -> dict[str, Any]:
        return {"refreshed": True, "plugin": PLUGIN_NAME}

    def check_ok(self, ctx: Any) -> dict[str, Any]:
        return {
            "status": "PASS",
            "summary": "rpc-fake gate passed",
            "evidence": [{"kind": "text", "message": "deterministic PASS"}],
        }

    def check_fail(self, ctx: Any) -> dict[str, Any]:
        return {
            "status": "FAIL",
            "summary": "advisory failure for contract coverage",
            "suggestions": [{"message": "no-op suggestion"}],
        }

    def read_status(self, ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        return {"result": {"ok": True, "plugin": PLUGIN_NAME}}

    async def add_net(self, ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        target = str(args.get("path", "/electrical"))
        if target != "/electrical":
            # Declared produces is /electrical only: this must be rejected by the host.
            await ctx.ir_transact(
                target, 0, [{"op": "add", "path": "", "value": EMPTY_ELECTRICAL}]
            )
            return {"result": {"written": target}}

        try:
            current = await ctx.ir_read("/electrical")
            value = current["value"]
            rev = current["rev"]
        except Exception:
            value = None
            rev = 0
        if value is None:
            await ctx.ir_transact(
                "/electrical", rev, [{"op": "add", "path": "", "value": EMPTY_ELECTRICAL}]
            )
            current = await ctx.ir_read("/electrical")
            value = current["value"]
            rev = current["rev"]

        nets = list(value.get("nets") or [])
        index = len(nets)
        net = {"id": f"net:N{index}", "name": f"N{index}", "class": "signal"}
        result = await ctx.ir_transact(
            "/electrical", rev, [{"op": "add", "path": "/nets/-", "value": net}]
        )
        return {"result": {"net": net["id"], "new_rev": result.new_rev}}


plugin = RpcFakePlugin()
plugin.__atomc_node_handlers__ = {"rpc-fake:refresh": plugin.refresh}
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
  description: "deterministic fake plugin for RPC contract tests",
  atomc: ">=0.0.1 <0.2.0",
  runtime: { python: `${FAKE_PLUGIN_MODULE}:plugin` },
  watches: [{ id: "rpc-fake:refresh", ir: ["/keyboard"], files: [], debounce_ms: 0 }],
  produces: ["/electrical"],
  gates: [
    {
      id: "gate:rpc-fake.ok",
      severity: "blocking",
      owner_agent: "ee-agent",
      after: ["rpc-fake:refresh"],
      handler: "check_ok",
    },
    {
      id: "gate:rpc-fake.fail",
      severity: "advisory",
      owner_agent: "ops-agent",
      after: ["rpc-fake:refresh"],
      handler: "check_fail",
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
    {
      name: "add_net",
      description: "Append a net to /electrical (or attempt an out-of-scope path)",
      input_schema: {
        type: "object",
        properties: { path: { type: "string" } },
        additionalProperties: false,
      },
      agents: ["ops-agent"],
      mutates: true,
      handler: "add_net",
    },
  ],
  cli: [],
  ui: [],
} as const;
