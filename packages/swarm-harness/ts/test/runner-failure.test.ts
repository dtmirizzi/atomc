import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { runAgent } from "../src/runner.js";
import { definition, FakeDaemon, FakeProvider, failure, gate } from "./fakes.js";

async function projectRoot(): Promise<string> {
  return mkdtemp(join(tmpdir(), "swarm-fail-"));
}

describe("runAgent — bounded retries and escalation", () => {
  it("yields RETRY while budget remains, then escalates when turns run out", async () => {
    const retry = new FakeDaemon();
    retry.gateResults = [gate({ status: "FAIL", summary: "still broken" })];
    const retryResult = await runAgent({
      definition: definition({ budget: { maxTurns: 4, maxCostMinor: 100 } }),
      failure,
      daemon: retry,
      provider: new FakeProvider([{ kind: "verify" }, { kind: "verify" }]),
      projectRoot: await projectRoot(),
      runId: "retry-run",
      maxVerifyRetries: 1,
    });

    expect(retryResult.outcome).toBe("RETRY");
    expect(retryResult.state).toBe("RETRY");
    expect(retryResult.turns).toBe(2); // one failed verify + one in-run retry
    expect(retry.unlockCalls).toBe(2);

    const escalate = new FakeDaemon();
    escalate.gateResults = [gate({ status: "FAIL", summary: "still broken" })];
    const escalateResult = await runAgent({
      definition: definition({ budget: { maxTurns: 2, maxCostMinor: 100 } }),
      failure,
      daemon: escalate,
      provider: new FakeProvider([{ kind: "verify" }, { kind: "verify" }]),
      projectRoot: await projectRoot(),
      runId: "escalate-run",
      maxVerifyRetries: 1,
    });

    expect(escalateResult.outcome).toBe("ESCALATE");
    expect(escalateResult.reason).toContain("blocking gate failures persist");
    expect(escalate.unlockCalls).toBe(2);
  });

  it("escalates on a crashed gate (ERROR) without domain retries", async () => {
    const daemon = new FakeDaemon();
    daemon.gateResults = [gate({ status: "ERROR", summary: "gate crashed" })];
    const result = await runAgent({
      definition: definition(),
      failure,
      daemon,
      provider: new FakeProvider([{ kind: "verify" }]),
      projectRoot: await projectRoot(),
      runId: "error-run",
    });

    expect(result.outcome).toBe("ESCALATE");
    expect(result.reason).toContain("ERROR");
    expect(daemon.unlockCalls).toBe(2);
  });

  it("escalates after the cost budget is exhausted", async () => {
    const daemon = new FakeDaemon();
    daemon.gateResults = [gate({ status: "FAIL", summary: "still broken" })];
    const result = await runAgent({
      definition: definition({ budget: { maxTurns: 8, maxCostMinor: 5 } }),
      failure,
      daemon,
      provider: new FakeProvider([
        { kind: "verify", usage: { costMinor: 10 } },
        { kind: "verify" },
      ]),
      projectRoot: await projectRoot(),
      runId: "cost-run",
    });

    expect(result.outcome).toBe("ESCALATE");
    expect(result.reason).toContain("cost");
  });
});
