/**
 * `gates.run` / `gates.list`: deterministic GateResult persistence at
 * `/gates/results/<id-without-prefix>`, filtering, and advisory FAIL isolation.
 */
import type { DaemonClient, GateResult } from "@atomc/daemon-client";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { DaemonHarness } from "./harness.js";

describe("gates.run and gates.list", () => {
  let harness: DaemonHarness;
  let client: DaemonClient;

  beforeAll(async () => {
    harness = await DaemonHarness.start();
    client = await harness.connect();
  }, 300_000);

  afterAll(async () => {
    await harness.stop();
  });

  it("runs the deterministic PASS gate", async () => {
    const results = await client.runGates(["gate:rpc-fake.ok"]);
    expect(results).toHaveLength(1);
    const gate = results[0] as GateResult;
    expect(gate.id).toBe("gate:rpc-fake.ok");
    expect(gate.status).toBe("PASS");
    expect(gate.severity).toBe("blocking");
    expect(gate.owner_agent).toBe("ee-agent");
    expect(gate.plugin).toBe("plugin:rpc-fake@0.1.0");
    expect(typeof gate.evaluated_at).toBe("string");
    expect(gate.evidence[0]?.message).toBe("deterministic PASS");
  });

  it("stores the result in IR and lists it", async () => {
    const gates = await client.getIR("/gates");
    const results = (gates.value as { results: Record<string, GateResult> }).results;
    expect(results["rpc-fake.ok"]?.status).toBe("PASS");

    const listed = await client.listGates(["gate:rpc-fake.ok"]);
    expect(listed.map((gate) => gate.id)).toEqual(["gate:rpc-fake.ok"]);
  });

  it("surfaces an advisory FAIL without crashing the daemon", async () => {
    const results = await client.runGates(["gate:rpc-fake.fail"]);
    const gate = results[0] as GateResult;
    expect(gate.status).toBe("FAIL");
    expect(gate.severity).toBe("advisory");

    // The daemon must still be responsive and the result must be queryable.
    const status = await client.daemonStatus();
    expect(status.pid).toBeGreaterThan(0);
    const listed = await client.listGates();
    expect(listed.map((entry) => entry.id).sort()).toEqual([
      "gate:rpc-fake.fail",
      "gate:rpc-fake.ok",
    ]);
  });

  it("runs all declared gates when no ids are supplied", async () => {
    const results = await client.runGates();
    expect(results.map((gate) => gate.id).sort()).toEqual([
      "gate:rpc-fake.fail",
      "gate:rpc-fake.ok",
    ]);
    expect(results.find((gate) => gate.id === "gate:rpc-fake.ok")?.status).toBe("PASS");
    expect(results.find((gate) => gate.id === "gate:rpc-fake.fail")?.status).toBe("FAIL");
  });
});
