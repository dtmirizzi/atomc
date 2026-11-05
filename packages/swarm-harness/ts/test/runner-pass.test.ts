import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { runAgent } from "../src/runner.js";
import { definition, FakeDaemon, FakeProvider, failure } from "./fakes.js";

async function projectRoot(): Promise<string> {
  return mkdtemp(join(tmpdir(), "swarm-pass-"));
}

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
    expect(daemon.lockOrder).toEqual(["/electrical", "/layout"]);
    expect(daemon.unlockCalls).toBe(2);
    expect(daemon.locked.size).toBe(0);
    expect(daemon.runDagCalls).toBe(1);
    expect(daemon.runGateCalls).toBe(1);
    expect(daemon.dagTargets).toEqual([undefined]);
    expect(daemon.gateIds).toEqual([["erc.no_unconnected"]]);
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
