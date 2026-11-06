import type { GateResult } from "@atomc/daemon-client";
import { describe, expect, it } from "vitest";
import { coerceQuote } from "../src/commands/quote.js";
import { runCli } from "../src/program.js";
import { FakeDaemon, makeDeps, pluginStatus } from "./helpers/fakes.js";

const FAB_QUOTE = {
  id: "quote:jlcpcb_abc123",
  fab: "jlcpcb",
  total_minor: 12345,
  currency: "USD",
  lead_time_days: 7,
  fetched_at: "2026-11-05T12:00:00Z",
  breakdown: { pcb: 10000, shipping: 2000, assembly: 345 },
  url: "https://example.invalid/quote/abc123",
};

function gate(overrides: Partial<GateResult> = {}): GateResult {
  return {
    id: "gate:fab.quote_under_budget",
    status: "PASS",
    severity: "blocking",
    plugin: "sourcing",
    owner_agent: "ops-agent",
    evaluated_at: "2026-11-05T12:00:00Z",
    ir_rev: 1,
    duration_ms: 1,
    summary: "cheapest fab quote within budget",
    evidence: [],
    suggestions: [],
    refs: [FAB_QUOTE.id],
    ...overrides,
  };
}

function quoteDaemon(options: {
  quotes?: unknown[];
  irQuotes?: unknown[];
  toolResult?: unknown;
  gateRuns?: GateResult[];
}): FakeDaemon {
  return new FakeDaemon({
    plugins: [pluginStatus("sourcing", true)],
    ir: { fabrication: { quotes: options.irQuotes ?? options.quotes ?? [] } },
    toolResults: {
      "sourcing.quote_pcb": options.toolResult ?? {
        result: {
          status: "UPDATED",
          summary: "fetched 1 fab quote(s)",
          quotes: options.quotes ?? [FAB_QUOTE],
        },
      },
    },
    gateRuns: options.gateRuns ?? [gate()],
  });
}

describe("atomc quote", () => {
  it("prints quotes and a passing gate", async () => {
    const daemon = quoteDaemon({});
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["quote", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.status).toBe("ok");
    expect(payload.count).toBe(1);
    expect(payload.quotes[0].id).toBe(FAB_QUOTE.id);
    expect(payload.quotes[0].breakdown.assembly).toBe(345);
    expect(payload.gate.status).toBe("PASS");
    expect(payload.refresh).toBe(false);
    expect(daemon.toolCalls[0]).toMatchObject({
      plugin: "sourcing",
      tool: "quote_pcb",
      args: { write: true },
    });
  });

  it("passes force on --refresh and exits 1 when the gate fails", async () => {
    const daemon = quoteDaemon({ gateRuns: [gate({ status: "FAIL", summary: "over budget" })] });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["quote", "--refresh", "--json"]);
    expect(code).toBe(1);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.status).toBe("gate_failed");
    expect(payload.refresh).toBe(true);
    expect(payload.gate.status).toBe("FAIL");
    expect(daemon.toolCalls[0]?.args).toEqual({ write: true, force: true });
  });

  it("reports no_data when the tool returns no quotes", async () => {
    const daemon = quoteDaemon({
      quotes: [],
      irQuotes: [],
      toolResult: { result: { status: "UPDATED", summary: "nothing", quotes: [] } },
      gateRuns: [gate({ status: "SKIP", summary: "no quotes fetched yet" })],
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["quote", "--json"]);
    expect(code).toBe(1);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.status).toBe("no_data");
    expect(payload.count).toBe(0);
  });

  it("falls back to the tool result when the IR read has no quotes", async () => {
    const daemon = new FakeDaemon({
      plugins: [pluginStatus("sourcing", true)],
      ir: {},
      toolResults: {
        "sourcing.quote_pcb": {
          result: { status: "OK", summary: "fetched", quotes: [FAB_QUOTE] },
        },
      },
      gateRuns: [gate()],
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["quote", "--json"]);
    expect(code).toBe(0);
    expect(JSON.parse(captured.out.join("")).count).toBe(1);
  });

  it("treats a missing gate result as not green", async () => {
    const daemon = quoteDaemon({ gateRuns: [] });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["quote", "--json"]);
    expect(code).toBe(1);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.gate).toBeNull();
  });

  it("reports unavailable when the sourcing plugin is missing", async () => {
    const daemon = new FakeDaemon({ plugins: [] });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["quote", "--json"]);
    expect(code).toBe(3);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.status).toBe("unavailable");
    expect(payload.plugin).toBe("sourcing");
    expect(daemon.toolCalls).toHaveLength(0);
  });

  it("reports unavailable when the tool returns UNAVAILABLE", async () => {
    const daemon = quoteDaemon({
      toolResult: { result: { status: "UNAVAILABLE", summary: "no vendor credentials" } },
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["quote", "--json"]);
    expect(code).toBe(3);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.status).toBe("unavailable");
    expect(payload.reason).toContain("no vendor credentials");
    expect(payload.tool_status).toBe("UNAVAILABLE");
  });

  it("reports unavailable when the tool returns ERROR", async () => {
    const daemon = quoteDaemon({
      toolResult: { result: { status: "ERROR", summary: "malformed response" } },
    });
    const { deps } = makeDeps({ daemon });
    const code = await runCli(deps, ["quote", "--json"]);
    expect(code).toBe(3);
  });

  it("reports unavailable when the tool invocation throws", async () => {
    const daemon = new FakeDaemon({
      plugins: [pluginStatus("sourcing", true)],
      // no toolResults key => request throws
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["quote", "--json"]);
    expect(code).toBe(3);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.status).toBe("unavailable");
    expect(payload.reason).toContain("failed");
  });

  it("reports unavailable when the daemon cannot be started", async () => {
    const { deps, captured } = makeDeps({ daemon: new FakeDaemon() });
    deps.ensureDaemon = async () => {
      throw new Error("connect ECONNREFUSED");
    };
    const code = await runCli(deps, ["quote", "--json"]);
    expect(code).toBe(3);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.status).toBe("unavailable");
    expect(payload.reason).toContain("daemon unavailable");
  });

  it("prints a human-readable quote summary", async () => {
    const daemon = quoteDaemon({});
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["quote"]);
    expect(code).toBe(0);
    expect(captured.err.join("")).toContain("1 fabrication quote(s)");
    expect(captured.err.join("")).toContain("123.45 USD");
    expect(captured.err.join("")).toContain("gate gate:fab.quote_under_budget: PASS");
    expect(captured.out).toEqual([]);
  });

  it("prints the human no-data hint", async () => {
    const daemon = quoteDaemon({
      quotes: [],
      irQuotes: [],
      toolResult: { result: { status: "UPDATED", summary: "nothing", quotes: [] } },
      gateRuns: [gate({ status: "SKIP" })],
    });
    const { deps, captured } = makeDeps({ daemon });
    await runCli(deps, ["quote"]);
    expect(captured.err.join("")).toContain("no quotes available");
  });

  it("reports unavailable when plugins.list fails", async () => {
    const daemon = new FakeDaemon({ listPluginsThrows: true });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["quote", "--json"]);
    expect(code).toBe(3);
    expect(JSON.parse(captured.out.join("")).reason).toContain("daemon RPC failed");
  });

  it("falls back to the tool quotes when the IR read fails", async () => {
    const daemon = new FakeDaemon({
      plugins: [pluginStatus("sourcing", true)],
      getIRThrows: true,
      toolResults: {
        "sourcing.quote_pcb": { result: { status: "OK", summary: "fetched", quotes: [FAB_QUOTE] } },
      },
      gateRuns: [gate()],
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["quote", "--json"]);
    expect(code).toBe(0);
    expect(JSON.parse(captured.out.join("")).count).toBe(1);
  });

  it("treats a failed gates.run as not green", async () => {
    const failing = new FakeDaemon({
      plugins: [pluginStatus("sourcing", true)],
      ir: { fabrication: { quotes: [FAB_QUOTE] } },
      toolResults: {
        "sourcing.quote_pcb": { result: { status: "OK", summary: "fetched", quotes: [FAB_QUOTE] } },
      },
      gatesRunThrows: true,
    });
    const { deps, captured } = makeDeps({ daemon: failing });
    const code = await runCli(deps, ["quote", "--json"]);
    expect(code).toBe(1);
    expect(JSON.parse(captured.out.join("")).gate).toBeNull();
  });

  it("passes --project through to the daemon", async () => {
    const daemon = quoteDaemon({});
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["quote", "--project", "sub", "--json"]);
    expect(code).toBe(0);
    expect(JSON.parse(captured.out.join("")).project).toBe("/work/sub");
  });

  it("coerces malformed quotes safely", () => {
    expect(coerceQuote(null)).toBeUndefined();
    expect(coerceQuote("nope")).toBeUndefined();
    expect(coerceQuote({ fab: "jlcpcb" })).toBeUndefined();
    expect(coerceQuote({ id: "quote:x", fab: "jlcpcb" })).toEqual({
      id: "quote:x",
      fab: "jlcpcb",
      total_minor: 0,
      currency: "USD",
      lead_time_days: 0,
      breakdown: {},
      url: null,
      fetched_at: null,
    });
    const coerced = coerceQuote({
      id: "quote:y",
      fab: "jlcpcb",
      total_minor: "x",
      currency: 5,
      url: 1,
      fetched_at: false,
      breakdown: { keep: 2, drop: "nope" },
    });
    expect(coerced?.total_minor).toBe(0);
    expect(coerced?.currency).toBe("USD");
    expect(coerced?.url).toBeNull();
    expect(coerced?.fetched_at).toBeNull();
    expect(coerced?.breakdown).toEqual({ keep: 2 });
  });

  it("handles a non-array fabrication node and malformed tool quotes", async () => {
    const daemon = new FakeDaemon({
      plugins: [pluginStatus("sourcing", true)],
      ir: { fabrication: { quotes: "nope" } },
      toolResults: {
        "sourcing.quote_pcb": {
          result: { status: "OK", summary: "fetched", quotes: [{ id: "bad" }, FAB_QUOTE] },
        },
      },
      gateRuns: [gate()],
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["quote", "--json"]);
    expect(code).toBe(0);
    expect(JSON.parse(captured.out.join("")).count).toBe(1);
  });

  it("reports unavailable for a tool result with no status", async () => {
    const daemon = new FakeDaemon({
      plugins: [pluginStatus("sourcing", true)],
      ir: {},
      toolResults: { "sourcing.quote_pcb": { result: { quotes: [] } } },
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["quote", "--json"]);
    expect(code).toBe(3);
    expect(JSON.parse(captured.out.join("")).reason).toContain("reported ERROR");
  });

  it("prints quotes with an empty breakdown and a result without a summary", async () => {
    const bare = { ...FAB_QUOTE, id: "quote:bare", breakdown: {} };
    const daemon = new FakeDaemon({
      plugins: [pluginStatus("sourcing", true)],
      ir: { fabrication: { quotes: [bare] } },
      toolResults: { "sourcing.quote_pcb": { result: { status: "OK", quotes: [bare] } } },
      gateRuns: [gate()],
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["quote", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.gate.status).toBe("PASS");
    expect(payload.tool.summary).toBeNull();
  });
});
