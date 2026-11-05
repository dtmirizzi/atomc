import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { isToolPermitted, isWithinScopes, runAgent } from "../src/runner.js";
import type { HarnessDaemon } from "../src/types.js";
import { FakeDaemon, FakeProvider, gate } from "./fakes.js";
import { definition, failure } from "./runner-pass.test.js";

async function projectRoot(): Promise<string> {
  return mkdtemp(join(tmpdir(), "swarm-edge-"));
}

describe("scope and tool predicates", () => {
  it("accepts a scope, its descendants, and never /meta", () => {
    expect(isWithinScopes("/electrical", ["/electrical"])).toBe(true);
    expect(isWithinScopes("/electrical/components/0", ["/electrical"])).toBe(true);
    expect(isWithinScopes("/meta", ["/meta", "/electrical"])).toBe(false);
    expect(isWithinScopes("/layout", ["/electrical"])).toBe(false);
  });

  it("supports exact, plugin-wide, and global tool grants", () => {
    const call = { plugin: "sourcing", tool: "solve", args: {} };
    expect(isToolPermitted(["sourcing:solve"], call)).toBe(true);
    expect(isToolPermitted(["sourcing:*"], call)).toBe(true);
    expect(isToolPermitted(["*"], call)).toBe(true);
    expect(isToolPermitted(["sourcing:other"], call)).toBe(false);
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
