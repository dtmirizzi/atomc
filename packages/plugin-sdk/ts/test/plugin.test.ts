import { describe, expect, it } from "vitest";
import { PluginManifestError } from "../src/manifest.js";
import {
  defineAtomcPlugin,
  type GateHandler,
  type GateResult,
  PluginRegistrationError,
  type PluginSetupContext,
} from "../src/plugin.js";

function baseManifest(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    manifest_version: "0.1.0",
    name: "demo",
    version: "0.1.0",
    description: "demo plugin",
    atomc: "*",
    runtime: { ts: "./dist/index.js" },
    watches: [{ id: "demo:watch", ir: ["/electrical"] }],
    produces: ["/sourcing"],
    gates: [
      {
        id: "gate:demo.ok",
        severity: "blocking",
        owner_agent: "ee-agent",
        after: ["demo:watch"],
        handler: "check_ok",
      },
    ],
    tools: [
      {
        name: "do_thing",
        description: "does a thing",
        input_schema: { type: "object" },
        agents: ["ee-agent"],
        mutates: false,
        handler: "do_thing",
      },
    ],
    cli: [{ command: "demo-run", description: "run demo", handler: "demo_run" }],
    ui: [],
    ...overrides,
  };
}

function gateResult(id: string): GateResult {
  return {
    id,
    status: "PASS",
    severity: "blocking",
    plugin: "plugin:demo@0.1.0",
    owner_agent: "ee-agent",
    evaluated_at: "2026-11-04T00:00:00Z",
    ir_rev: 1,
    duration_ms: 1,
    summary: "ok",
    evidence: [],
    suggestions: [],
    refs: [],
  };
}

const fullSetup = (ctx: PluginSetupContext): void => {
  ctx.registerGate("check_ok", (_context, gateId) => gateResult(gateId));
  ctx.registerTool("do_thing", () => ({ ok: true }));
  ctx.registerCli("demo_run", () => ({ ran: true }));
};

describe("defineAtomcPlugin", () => {
  it("returns handlers keyed by gate id, tool name and command", async () => {
    const plugin = await defineAtomcPlugin({ manifest: baseManifest(), setup: fullSetup });
    expect(plugin.manifest.name).toBe("demo");
    expect([...plugin.gates.keys()]).toEqual(["gate:demo.ok"]);
    expect([...plugin.tools.keys()]).toEqual(["do_thing"]);
    expect([...plugin.cli.keys()]).toEqual(["demo-run"]);
  });

  it("freezes the descriptor and its manifest", async () => {
    const plugin = await defineAtomcPlugin({ manifest: baseManifest(), setup: fullSetup });
    expect(Object.isFrozen(plugin)).toBe(true);
    expect(Object.isFrozen(plugin.manifest)).toBe(true);
    expect(Object.isFrozen(plugin.manifest.gates)).toBe(true);
    expect((plugin.gates as { set?: unknown }).set).toBeUndefined();
  });

  it("exposes read-only map semantics", async () => {
    const plugin = await defineAtomcPlugin({ manifest: baseManifest(), setup: fullSetup });
    const gates = plugin.gates;
    expect(gates.size).toBe(1);
    expect(gates.has("gate:demo.ok")).toBe(true);
    expect(gates.has("nope")).toBe(false);
    expect(gates.get("nope")).toBeUndefined();
    expect([...gates.entries()]).toHaveLength(1);
    expect([...gates.keys()]).toEqual(["gate:demo.ok"]);
    expect([...gates.values()]).toHaveLength(1);
    const seen: string[] = [];
    gates.forEach((_value, key) => void seen.push(key));
    expect(seen).toEqual(["gate:demo.ok"]);
    expect([...gates]).toHaveLength(1);
  });

  it("supports async setup", async () => {
    const plugin = await defineAtomcPlugin({
      manifest: baseManifest(),
      setup: async (ctx) => {
        await Promise.resolve();
        fullSetup(ctx);
      },
    });
    expect(plugin.tools.size).toBe(1);
  });

  it("maps one shared handler to multiple gates", async () => {
    const manifest = baseManifest({
      gates: [
        {
          id: "gate:demo.a",
          severity: "blocking",
          owner_agent: null,
          after: ["demo:watch"],
          handler: "shared",
        },
        {
          id: "gate:demo.b",
          severity: "advisory",
          owner_agent: null,
          after: ["demo:watch"],
          handler: "shared",
        },
      ],
      tools: [],
      cli: [],
    });
    const calls: string[] = [];
    const handler: GateHandler = (_ctx, gateId) => {
      calls.push(gateId);
      return gateResult(gateId);
    };
    const plugin = await defineAtomcPlugin({
      manifest,
      setup: (ctx) => ctx.registerGate("shared", handler),
    });
    expect([...plugin.gates.keys()]).toEqual(["gate:demo.a", "gate:demo.b"]);
    await plugin.gates.get("gate:demo.b")?.({} as never, "gate:demo.b");
    expect(calls).toEqual(["gate:demo.b"]);
  });

  it("rejects undeclared handlers", async () => {
    await expect(
      defineAtomcPlugin({
        manifest: baseManifest(),
        setup: (ctx) => ctx.registerGate("nope", () => gateResult("x")),
      }),
    ).rejects.toMatchObject({ code: "undeclared_handler" });
  });

  it("rejects duplicate handler registration", async () => {
    await expect(
      defineAtomcPlugin({
        manifest: baseManifest(),
        setup: (ctx) => {
          ctx.registerGate("check_ok", (_c, id) => gateResult(id));
          ctx.registerGate("check_ok", (_c, id) => gateResult(id));
        },
      }),
    ).rejects.toBeInstanceOf(PluginRegistrationError);
  });

  it("rejects missing declared handlers", async () => {
    await expect(
      defineAtomcPlugin({
        manifest: baseManifest(),
        setup: (ctx) => ctx.registerGate("check_ok", (_c, id) => gateResult(id)),
      }),
    ).rejects.toMatchObject({ code: "missing_handler" });
  });

  it("validates the manifest before running setup", async () => {
    let setupRan = false;
    await expect(
      defineAtomcPlugin({
        manifest: baseManifest({ version: "nope" }),
        setup: () => {
          setupRan = true;
        },
      }),
    ).rejects.toBeInstanceOf(PluginManifestError);
    expect(setupRan).toBe(false);
  });

  it("keeps host services unavailable during setup", async () => {
    const plugin = await defineAtomcPlugin({
      manifest: baseManifest(),
      setup: (ctx) => {
        expect(() => {
          void ctx.ir.get("/electrical");
        }).toThrow(/unavailable during setup/);
        expect(() => {
          void ctx.cache.get("k");
        }).toThrow(/unavailable during setup/);
        // logger is a safe no-op during setup
        ctx.logger.info("hello");
        fullSetup(ctx);
      },
    });
    expect(plugin).toBeDefined();
  });
});
