import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { runAgent } from "../src/runner.js";
import { definition, FakeDaemon, FakeProvider, failure, ThrowingProvider } from "./fakes.js";

async function projectRoot(): Promise<string> {
  return mkdtemp(join(tmpdir(), "swarm-lock-"));
}

describe("runAgent — lock lifecycle", () => {
  it("holds the full declared lock set throughout mutation and verification", async () => {
    const daemon = new FakeDaemon();
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
            ops: [{ op: "add", path: "/components/-", value: { ref: "U2" } }],
          },
        },
        { kind: "verify" },
      ]),
      projectRoot: await projectRoot(),
      runId: "locks-during-work",
    });
    expect(result.outcome).toBe("PASS");
    expect(daemon.maxLocked).toBe(2);
    expect(daemon.locked.size).toBe(0);
    expect(daemon.events.indexOf("runGates:erc.no_unconnected")).toBeLessThan(
      daemon.events.indexOf("unlock:/layout"),
    );
  });

  it("releases locks when the provider throws", async () => {
    const daemon = new FakeDaemon();
    const result = await runAgent({
      definition: definition(),
      failure,
      daemon,
      provider: new ThrowingProvider(),
      projectRoot: await projectRoot(),
      runId: "throw-run",
    });

    expect(result.outcome).toBe("ESCALATE");
    expect(result.reason).toContain("model boom");
    expect(daemon.locked.size).toBe(0);
    expect(daemon.unlockCalls).toBe(2);
  });

  it("continues releasing remaining scopes when an unlock fails", async () => {
    const daemon = new FakeDaemon();
    daemon.unlockFailures.add("/layout");
    const result = await runAgent({
      definition: definition(),
      failure,
      daemon,
      provider: new FakeProvider([{ kind: "verify" }]),
      projectRoot: await projectRoot(),
      runId: "unlock-failure",
    });
    expect(result.outcome).toBe("PASS");
    expect(daemon.unlockCalls).toBe(2);
    expect(daemon.events.slice(-2)).toEqual(["unlock:/layout", "unlock:/electrical"]);
    expect(daemon.locked.has("/electrical")).toBe(false);
    expect(daemon.locked.has("/layout")).toBe(true);
  });

  it("does not acquire locks when aborted before planning", async () => {
    const daemon = new FakeDaemon();
    const controller = new AbortController();
    controller.abort();
    const result = await runAgent({
      definition: definition(),
      failure,
      daemon,
      provider: new FakeProvider([{ kind: "verify" }]),
      projectRoot: await projectRoot(),
      runId: "abort-run",
      signal: controller.signal,
    });

    expect(result.outcome).toBe("ABORTED");
    expect(result.state).toBe("ABORTED");
    expect(result.reason).toContain("aborted");
    expect(daemon.lockCalls).toBe(0);
    expect(daemon.locked.size).toBe(0);
  });

  it("escalates after bounded lock conflicts without leaking locks", async () => {
    const daemon = new FakeDaemon();
    daemon.lockConflicts.add("/layout");
    const events: string[] = [];
    const result = await runAgent({
      definition: definition(),
      failure,
      daemon,
      provider: new FakeProvider([{ kind: "verify" }]),
      projectRoot: await projectRoot(),
      runId: "lock-conflict-run",
      maxConflictRetries: 1,
      onEvent: (event) => events.push(event.kind),
    });

    expect(result.outcome).toBe("ESCALATE");
    expect(result.reason).toContain("/layout");
    expect(daemon.locked.size).toBe(0);
    expect(daemon.unlockCalls).toBe(1); // only /electrical was acquired
    expect(events).toContain("lock.conflict");
  });

  it("re-reads and replans on a stale-rev proposal instead of blindly resending", async () => {
    const daemon = new FakeDaemon();
    const provider = new FakeProvider([
      {
        kind: "patch",
        proposal: {
          path: "/electrical/components/0",
          baseRev: 999,
          ops: [{ op: "replace", path: "/value", value: "10k" }],
        },
      },
      { kind: "verify" },
    ]);
    const result = await runAgent({
      definition: definition(),
      failure,
      daemon,
      provider,
      projectRoot: await projectRoot(),
      runId: "conflict-replan-run",
      maxConflictRetries: 1,
    });

    expect(result.outcome).toBe("PASS");
    expect(daemon.transactCalls).toBe(0); // stale patch was never sent
    expect(provider.requests).toHaveLength(2); // re-read then replan
  });

  it("applies a patch at the current revision and rejects writes outside its scopes", async () => {
    const daemon = new FakeDaemon();
    const applied = await runAgent({
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
      runId: "patch-run",
    });

    expect(applied.outcome).toBe("PASS");
    expect(daemon.transactCalls).toBe(1);
    expect(applied.state).toBe("DONE");

    const forbiddenDaemon = new FakeDaemon();
    const forbidden = await runAgent({
      definition: definition(),
      failure,
      daemon: forbiddenDaemon,
      provider: new FakeProvider([
        { kind: "patch", proposal: { path: "/meta", baseRev: 10, ops: [] } },
      ]),
      projectRoot: await projectRoot(),
      runId: "forbidden-run",
    });

    expect(forbidden.outcome).toBe("ESCALATE");
    expect(forbidden.reason).toContain("outside");
    expect(forbiddenDaemon.transactCalls).toBe(0);
  });
});
