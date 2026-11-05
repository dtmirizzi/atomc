import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { isToolPermitted, isWithinScopes, runAgent } from "../src/runner.js";
import type { HarnessDaemon } from "../src/types.js";
import { definition, FakeDaemon, FakeProvider, failure, gate } from "./fakes.js";

async function projectRoot(): Promise<string> {
  return mkdtemp(join(tmpdir(), "swarm-edge-"));
}

describe("scope and tool predicates", () => {
  it("accepts a scope and descendants but rejects sibling prefixes and /meta", () => {
    expect(isWithinScopes("/electrical", ["/electrical"])).toBe(true);
    expect(isWithinScopes("/electrical/components/0", ["/electrical"])).toBe(true);
    expect(isWithinScopes("/electrical2", ["/electrical"])).toBe(false);
    expect(isWithinScopes("/meta", ["/meta", "/electrical"])).toBe(false);
    expect(isWithinScopes("/meta/private", ["/meta"])).toBe(false);
    expect(isWithinScopes("/layout", ["/electrical"])).toBe(false);
    expect(isWithinScopes("/electrical", [])).toBe(false);
  });

  it("supports exact, plugin-wide, and global tool grants", () => {
    const call = { plugin: "sourcing", tool: "solve", args: {} };
    expect(isToolPermitted(["sourcing:solve"], call)).toBe(true);
    expect(isToolPermitted(["sourcing:*"], call)).toBe(true);
    expect(isToolPermitted(["*"], call)).toBe(true);
    expect(isToolPermitted(["sourcing:other"], call)).toBe(false);
    expect(isToolPermitted([], call)).toBe(false);
  });
});

describe("runAgent — defensive edges", () => {
  it("escalates on a patch decision without a proposal", async () => {
    const daemon = new FakeDaemon();
    const result = await runAgent({
      definition: definition(),
      failure,
      daemon,
      provider: new FakeProvider([{ kind: "patch" }]),
      projectRoot: await projectRoot(),
      runId: "no-proposal",
    });
    expect(result.outcome).toBe("ESCALATE");
    expect(result.reason).toContain("without a proposal");
  });

  it("escalates on a tool decision without a call", async () => {
    const daemon = new FakeDaemon();
    const result = await runAgent({
      definition: definition(),
      failure,
      daemon,
      provider: new FakeProvider([{ kind: "tool" }]),
      projectRoot: await projectRoot(),
      runId: "no-tool",
    });
    expect(result.outcome).toBe("ESCALATE");
    expect(result.reason).toContain("without a call");
  });

  it("escalates when a permitted tool throws", async () => {
    const daemon = new FakeDaemon();
    daemon.tools = [
      {
        plugin: "sourcing",
        name: "solve",
        description: "solve",
        input_schema: { type: "object" },
        mutates: true,
      },
    ];
    daemon.callTool = async () => {
      throw new Error("tool boom");
    };
    const result = await runAgent({
      definition: definition({ permittedTools: ["sourcing:solve"] }),
      failure,
      daemon,
      provider: new FakeProvider([
        { kind: "tool", tool: { plugin: "sourcing", tool: "solve", args: {} } },
      ]),
      projectRoot: await projectRoot(),
      runId: "tool-boom",
    });
    expect(result.outcome).toBe("ESCALATE");
    expect(result.reason).toContain("tool boom");
  });

  it("recovers from a server-side optimistic conflict", async () => {
    const daemon = new FakeDaemon();
    let conflicts = 0;
    const { ConflictError } = await import("@atomc/daemon-client");
    daemon.transact = async () => {
      conflicts += 1;
      if (conflicts === 1) throw new ConflictError("stale", { current_rev: daemon.rev });
      daemon.rev += 1;
      return { new_rev: daemon.rev, changed_paths: ["/electrical"] };
    };
    const events: string[] = [];
    const result = await runAgent({
      definition: definition(),
      failure,
      daemon,
      provider: new FakeProvider([
        {
          kind: "patch",
          proposal: {
            path: "/electrical",
            baseRev: 10,
            ops: [{ op: "add", path: "/components/-", value: {} }],
          },
        },
        { kind: "verify" },
      ]),
      projectRoot: await projectRoot(),
      runId: "server-conflict",
      maxConflictRetries: 1,
      onEvent: (event) => events.push(event.kind),
    });
    expect(result.outcome).toBe("PASS");
    expect(conflicts).toBe(1);
    expect(events).toContain("patch.conflict");
  });

  it("rejects model-reported cost that exceeds the hard budget before verifying", async () => {
    const daemon = new FakeDaemon();
    const result = await runAgent({
      definition: definition({ budget: { maxTurns: 5, maxCostMinor: 5 } }),
      failure,
      daemon,
      provider: new FakeProvider([{ kind: "verify", usage: { costMinor: 6 } }]),
      projectRoot: await projectRoot(),
      runId: "overspend",
    });
    expect(result.outcome).toBe("ESCALATE");
    expect(result.costMinor).toBe(6);
    expect(result.reason).toContain("cost budget");
    expect(daemon.runDagCalls).toBe(0);
    expect(daemon.locked.size).toBe(0);
  });

  it("does not allow a provider to pass a gate after the cost cap is reached exactly", async () => {
    const daemon = new FakeDaemon();
    const result = await runAgent({
      definition: definition({ budget: { maxTurns: 5, maxCostMinor: 5 } }),
      failure,
      daemon,
      provider: new FakeProvider([{ kind: "verify", usage: { costMinor: 5 } }]),
      projectRoot: await projectRoot(),
      runId: "exact-cost-cap",
    });
    expect(result.outcome).toBe("ESCALATE");
    expect(result.costMinor).toBe(5);
    expect(result.reason).toContain("cost budget");
    expect(daemon.runDagCalls).toBe(0);
  });

  it("does not allow a provider to verify after the token cap is reached exactly", async () => {
    const daemon = new FakeDaemon();
    const result = await runAgent({
      definition: definition({ budget: { maxTurns: 5, maxCostMinor: 100, maxTokens: 5 } }),
      failure,
      daemon,
      provider: new FakeProvider([{ kind: "verify", usage: { inputTokens: 2, outputTokens: 3 } }]),
      projectRoot: await projectRoot(),
      runId: "exact-token-cap",
    });
    expect(result.outcome).toBe("ESCALATE");
    expect(result.tokens).toBe(5);
    expect(result.reason).toContain("token budget");
    expect(daemon.runDagCalls).toBe(0);
  });

  it("does not allow a provider to pass a gate after the cost cap is reached exactly", async () => {
    const daemon = new FakeDaemon();
    const provider = new FakeProvider([
      { kind: "verify", usage: { costMinor: Number.NaN, inputTokens: -40, outputTokens: 3.8 } },
    ]);
    const result = await runAgent({
      definition: definition(),
      failure,
      daemon,
      provider,
      projectRoot: await projectRoot(),
      runId: "invalid-accounting",
    });
    expect(result.outcome).toBe("PASS");
    expect(result.costMinor).toBe(0);
    expect(result.tokens).toBe(3);
  });

  it("escalates before another model call when a retry consumes the remaining token budget", async () => {
    const daemon = new FakeDaemon();
    daemon.gateResults = [gate({ status: "FAIL" })];
    const provider = new FakeProvider([
      { kind: "verify", usage: { outputTokens: 1 } },
      { kind: "verify" },
    ]);
    const result = await runAgent({
      definition: definition({ budget: { maxTurns: 5, maxCostMinor: 100, maxTokens: 1 } }),
      failure,
      daemon,
      provider,
      projectRoot: await projectRoot(),
      runId: "token-at-cap",
      maxVerifyRetries: 1,
    });
    expect(result.outcome).toBe("ESCALATE");
    expect(result.reason).toContain("token budget");
    expect(provider.requests).toHaveLength(1);
    expect(daemon.locked.size).toBe(0);
  });

  it("escalates when the token budget is exhausted", async () => {
    const daemon = new FakeDaemon();
    daemon.gateResults = [gate({ status: "FAIL" })];
    const result = await runAgent({
      definition: definition({ budget: { maxTurns: 5, maxCostMinor: 100, maxTokens: 1 } }),
      failure,
      daemon,
      provider: new FakeProvider([
        { kind: "verify", usage: { outputTokens: 5 } },
        { kind: "verify" },
      ]),
      projectRoot: await projectRoot(),
      runId: "token-budget",
      maxVerifyRetries: 1,
    });
    expect(result.outcome).toBe("ESCALATE");
    expect(result.reason).toContain("token");
  });

  it("rejects a transaction path that is within locks but outside manifest produces", async () => {
    const daemon = new FakeDaemon();
    const result = await runAgent({
      definition: definition({ produces: ["/electrical/components"] }),
      failure,
      daemon,
      provider: new FakeProvider([
        {
          kind: "patch",
          proposal: {
            path: "/electrical",
            baseRev: 10,
            ops: [{ op: "add", path: "/nets/-", value: { name: "GND" } }],
          },
        },
      ]),
      projectRoot: await projectRoot(),
      runId: "produces-scope",
    });
    expect(result.outcome).toBe("ESCALATE");
    expect(result.reason).toContain("produces scopes");
    expect(daemon.transactCalls).toBe(0);
  });

  it("contains thrown event-listener errors so they cannot skip lock cleanup", async () => {
    const daemon = new FakeDaemon();
    const result = await runAgent({
      definition: definition(),
      failure,
      daemon,
      provider: new FakeProvider([{ kind: "verify" }]),
      projectRoot: await projectRoot(),
      runId: "throwing-observer",
      onEvent: () => {
        throw new Error("observer failure");
      },
    });
    expect(result.outcome).toBe("PASS");
    expect(daemon.locked.size).toBe(0);
    expect(daemon.unlockCalls).toBe(2);
  });

  it("permits advisory gate failures and skips while still returning PASS", async () => {
    const daemon = new FakeDaemon();
    daemon.gateResults = [
      gate({ status: "FAIL", severity: "advisory" }),
      gate({ id: "gate:optional", status: "SKIP", severity: "blocking" }),
    ];
    const result = await runAgent({
      definition: definition(),
      failure,
      daemon,
      provider: new FakeProvider([{ kind: "verify" }]),
      projectRoot: await projectRoot(),
      runId: "advisory-and-skip",
    });
    expect(result.outcome).toBe("PASS");
    expect(result.gateResults.map(({ status }) => status)).toEqual(["FAIL", "SKIP"]);
  });

  it("passes only the declared DAG targets and gate ids to the daemon", async () => {
    const daemon = new FakeDaemon();
    const result = await runAgent({
      definition: definition({ dagTargets: ["layout.compile"], gates: ["layout.valid"] }),
      failure,
      daemon,
      provider: new FakeProvider([{ kind: "verify" }]),
      projectRoot: await projectRoot(),
      runId: "targeted-verification",
    });
    expect(result.outcome).toBe("PASS");
    expect(daemon.runDagCalls).toBe(1);
    expect(daemon.runGateCalls).toBe(1);
    expect(daemon.dagTargets).toEqual([["layout.compile"]]);
    expect(daemon.gateIds).toEqual([["layout.valid"]]);
    expect(daemon.events).toContain("runDAG:layout.compile");
    expect(daemon.events).toContain("runGates:layout.valid");
  });

  it("works with a daemon that exposes no tools", async () => {
    const daemon: HarnessDaemon = {
      getIR: async () => ({ rev: 1, value: {} }),
      transact: async () => ({ new_rev: 2, changed_paths: [] }),
      lock: async () => ({ expires_at: "2026-11-05T00:00:00Z" }),
      unlock: async () => ({ released: true }),
      runDAG: async () => ({ run_id: "r" }),
      runGates: async () => [gate()],
      callTool: async () => ({ result: null }),
    };
    const result = await runAgent({
      definition: definition(),
      failure,
      daemon,
      provider: new FakeProvider([{ kind: "verify" }]),
      projectRoot: await projectRoot(),
      runId: "no-tools",
    });
    expect(result.outcome).toBe("PASS");
  });
});
