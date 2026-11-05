import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { runAgent } from "../src/runner.js";
import type { AgentDefinition, GateFailure } from "../src/types.js";
import { FakeDaemon, FakeProvider } from "./fakes.js";

async function projectRoot(): Promise<string> {
  return mkdtemp(join(tmpdir(), "swarm-pass-"));
}

export function definition(overrides: Partial<AgentDefinition> = {}): AgentDefinition {
  return {
    id: "ee-agent",
    systemPrompt: "you fix electrical gates",
    permittedTools: [],
    lockScopes: ["/electrical", "/layout"],
    gates: ["erc.no_unconnected"],
    model: { provider: "fake", model: "fake-1" },
    budget: { maxTurns: 8, maxCostMinor: 100 },
    ...overrides,
  };
}

export const failure: GateFailure = {
  id: "gate:erc.no_unconnected",
  status: "FAIL",
  severity: "blocking",
  owner_agent: "ee-agent",
  ir_rev: 10,
  summary: "2 unconnected pins",
  refs: ["comp:U1"],
};

describe("runAgent — convergence is gate-driven", () => {
  it("returns PASS and releases every lock when gates pass", async () => {
    const daemon = new FakeDaemon();
    const provider = new FakeProvider([{ kind: "verify" }]);
    const events: string[] = [];
    const result = await runAgent({
      definition: definition(),
      failure,
      daemon,
      provider,
      projectRoot: await projectRoot(),
      runId: "pass-run",
      onEvent: (event) => events.push(event.kind),
    });

    expect(result.outcome).toBe("PASS");
    expect(result.state).toBe("DONE");
    expect(result.gateResults).toHaveLength(1);
    expect(daemon.lockCalls).toBe(2);
    expect(daemon.unlockCalls).toBe(2);
    expect(daemon.locked.size).toBe(0);
    expect(daemon.runDagCalls).toBe(1);
    expect(daemon.runGateCalls).toBe(1);
    expect(events).toContain("lock.released");
    expect(events).toContain("gate.result");
  });

  it("does not trust a model that skips verification (give_up escalates)", async () => {
    const daemon = new FakeDaemon();
    const provider = new FakeProvider([{ kind: "give_up", reason: "no idea" }]);
    const result = await runAgent({
      definition: definition(),
      failure,
      daemon,
      provider,
      projectRoot: await projectRoot(),
      runId: "giveup-run",
    });

    expect(result.outcome).toBe("ESCALATE");
    expect(result.state).toBe("ESCALATE");
    expect(daemon.locked.size).toBe(0);
  });
});
