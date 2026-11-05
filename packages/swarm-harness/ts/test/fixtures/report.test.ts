/** WP-3.5: report utility determinism, redaction and stable output. */
import { describe, expect, it } from "vitest";
import type { AgentRunResult, SwarmEvent } from "../../src/types.js";
import { buildSessionReport, formatSessionReport } from "./report.js";
import { passGate } from "./support.js";

function result(overrides: Partial<AgentRunResult> = {}): AgentRunResult {
  return {
    outcome: "PASS",
    session: {
      id: "run:ee-agent",
      runId: "run",
      agentId: "ee-agent",
      holder: "agent:ee-agent#1",
      model: { provider: "fake", model: "recorded-1" },
      startedAt: "2026-11-04T23:00:00Z",
    },
    state: "DONE",
    turns: 2,
    costMinor: 7,
    tokens: 180,
    gateResults: [passGate("gate:erc.no_unconnected")],
    ...overrides,
  };
}

const events: SwarmEvent[] = [
  { kind: "state", from: "IDLE", to: "PLAN", at: "2026-11-04T23:00:00Z" },
  { kind: "state", from: "PLAN", to: "CLAIM_LOCK", at: "2026-11-04T23:00:00Z" },
  {
    kind: "lock.acquired",
    node: "/electrical",
    holder: "agent:ee-agent#1",
    expires_at: "x",
    at: "t",
  },
  {
    kind: "lock.acquired",
    node: "/layout?Bearer abc.def.ghi",
    holder: "agent:ee-agent#1",
    expires_at: "x",
    at: "t",
  },
  { kind: "patch.applied", path: "/electrical", new_rev: 11, at: "t" },
  { kind: "tool.called", plugin: "qmk", tool: "compile", at: "t" },
  { kind: "tool.rejected", plugin: "sourcing", tool: "solve", reason: "not permitted", at: "t" },
  {
    kind: "gate.result",
    gate: passGate("gate:erc.no_unconnected", { summary: "Bearer leaked.token.value" }),
    at: "t",
  },
  {
    kind: "lock.released",
    node: "/layout?Bearer abc.def.ghi",
    holder: "agent:ee-agent#1",
    at: "t",
  },
  { kind: "lock.released", node: "/electrical", holder: "agent:ee-agent#1", at: "t" },
  { kind: "state", from: "RELEASE", to: "DONE", at: "t" },
];

describe("session report", () => {
  it("summarizes outcome, decisions, tools, gates and spend", () => {
    const report = buildSessionReport({
      result: result(),
      events,
      decisions: [
        { kind: "patch", proposal: { path: "/electrical", baseRev: 10, ops: [] } },
        { kind: "tool", tool: { plugin: "qmk", tool: "compile", args: { token: "secret" } } },
        { kind: "verify" },
      ],
    });

    expect(report.agentId).toBe("ee-agent");
    expect(report.outcome).toBe("PASS");
    expect(report.turns).toBe(2);
    expect(report.costMinor).toBe(7);
    expect(report.decisions).toEqual(["patch:/electrical", "tool:qmk:compile", "verify"]);
    expect(report.toolCalls).toEqual([
      { plugin: "qmk", tool: "compile", rejected: false },
      { plugin: "sourcing", tool: "solve", rejected: true },
    ]);
    expect(report.gates).toEqual([
      { id: "gate:erc.no_unconnected", status: "PASS", severity: "blocking" },
    ]);
    expect(report.statePath).toEqual(["IDLE->PLAN", "PLAN->CLAIM_LOCK", "RELEASE->DONE"]);
  });

  it("redacts token-shaped strings and never emits timestamps or tool args", () => {
    const report = buildSessionReport({ result: result(), events });
    expect(report.locksAcquired[1]).toContain("[REDACTED]");
    expect(report.locksAcquired[1]).not.toContain("abc.def.ghi");
    expect(report.locksReleased[0]).toBe(report.locksAcquired[1]);

    const formatted = formatSessionReport(report);
    expect(formatted).not.toMatch(/\d{4}-\d{2}-\d{2}T/);
    expect(formatted).not.toContain("secret");
    expect(formatted).not.toContain("Bearer");
    expect(formatted).not.toContain("evaluated_at");
    expect(formatted.endsWith("\n")).toBe(true);
  });

  it("is deterministic for identical inputs", () => {
    const a = formatSessionReport(buildSessionReport({ result: result(), events }));
    const b = formatSessionReport(buildSessionReport({ result: result(), events }));
    expect(a).toBe(b);
  });

  it("counts patch and lock conflicts", () => {
    const withConflicts: SwarmEvent[] = [
      ...events,
      { kind: "patch.conflict", path: "/electrical", attempt: 1, at: "t" },
      { kind: "lock.conflict", node: "/layout", contact: true, at: "t" },
    ];
    expect(buildSessionReport({ result: result(), events: withConflicts }).conflicts).toBe(2);
  });

  it("handles an empty event list", () => {
    const report = buildSessionReport({ result: result({ turns: 0, costMinor: 0 }), events: [] });
    expect(report.statePath).toEqual([]);
    expect(report.decisions).toEqual([]);
    expect(report.conflicts).toBe(0);
  });
});
