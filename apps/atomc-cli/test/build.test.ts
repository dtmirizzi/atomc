import type { GateResult } from "@atomc/daemon-client";
import { describe, expect, it } from "vitest";
import { runCli } from "../src/program.js";
import { FakeDaemon, makeDeps } from "./helpers/fakes.js";

function gate(overrides: Partial<GateResult>): GateResult {
  return {
    id: "gate:erc.no_unconnected",
    status: "PASS",
    severity: "blocking",
    plugin: "atopile",
    owner_agent: "ee-agent",
    evaluated_at: "2026-11-04T00:00:00Z",
    ir_rev: 1,
    duration_ms: 1,
    summary: "ok",
    evidence: [],
    suggestions: [],
    refs: [],
    ...overrides,
  };
}

describe("atomc build", () => {
  it("summarizes a clean run", async () => {
    const daemon = new FakeDaemon({
      nodes: [{ id: "atopile:build", plugin: "atopile", state: "ok" }],
      gates: [gate({})],
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["build", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.ok).toBe(true);
    expect(payload.gates.counts.PASS).toBe(1);
    expect(daemon.runParams).toEqual({});
  });

  it("passes targets and force through to dag.run", async () => {
    const daemon = new FakeDaemon({ nodes: [] });
    const { deps } = makeDeps({ daemon });
    await runCli(deps, ["build", "atopile:build", "--force"]);
    expect(daemon.runParams).toEqual({ targets: ["atopile:build"], force: true });
  });

  it("fails on a failed node", async () => {
    const daemon = new FakeDaemon({
      nodes: [{ id: "atopile:build", plugin: "atopile", state: "failed" }],
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["build", "--json"]);
    expect(code).toBe(1);
    expect(JSON.parse(captured.out.join("")).ok).toBe(false);
  });

  it("fails on a blocking gate FAIL", async () => {
    const daemon = new FakeDaemon({
      nodes: [{ id: "atopile:build", plugin: "atopile", state: "ok" }],
      gates: [gate({ id: "gate:erc.no_unconnected", status: "FAIL", summary: "unconnected pin" })],
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["build", "--json"]);
    expect(code).toBe(1);
    expect(JSON.parse(captured.out.join("")).gates.failures).toContain("gate:erc.no_unconnected");
  });

  it("reports an empty DAG without claiming success", async () => {
    const daemon = new FakeDaemon({ nodes: [], gates: [] });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["build", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.nodes).toEqual([]);
  });

  it("rejects an invalid timeout", async () => {
    const daemon = new FakeDaemon({ nodes: [] });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["build", "--timeout", "abc"]);
    expect(code).toBe(1);
    expect(captured.err.join("")).toContain("invalid --timeout");
  });

  it("works when the daemon does not support event subscriptions", async () => {
    const daemon = new FakeDaemon({ nodes: [], subscribeThrows: true });
    const { deps } = makeDeps({ daemon });
    const code = await runCli(deps, ["build", "--json"]);
    expect(code).toBe(0);
  });

  it("surfaces failed node events on stderr", async () => {
    const daemon = new FakeDaemon({
      nodes: [{ id: "atopile:build", plugin: "atopile", state: "ok" }],
      events: [{ topic: "dag.node.end", data: { id: "atopile:build", ok: false, error: "boom" } }],
    });
    const { deps, captured } = makeDeps({ daemon });
    await runCli(deps, ["build"]);
    expect(captured.err.join("")).toContain("atopile:build failed: boom");
  });

  it("times out when nodes never settle", async () => {
    const daemon = new FakeDaemon({
      nodes: [{ id: "atopile:build", plugin: "atopile", state: "running" }],
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["build", "--timeout", "50"]);
    expect(code).toBe(1);
    expect(captured.err.join("")).toContain("timed out");
  });

  it("prints human output without --json", async () => {
    const daemon = new FakeDaemon({ nodes: [{ id: "n", plugin: "p", state: "ok" }] });
    const { deps, captured } = makeDeps({ daemon });
    await runCli(deps, ["build"]);
    expect(captured.err.join("")).toContain("run run-1");
    expect(captured.out).toEqual([]);
  });
});
