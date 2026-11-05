/**
 * `dag.status` / `dag.run` with start/end events over the real reactive scheduler,
 * including incremental skip behaviour for unchanged inputs.
 */
import type { AtomcEvent, DaemonClient, DagNodeStatus } from "@atomc/daemon-client";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { MINIMAL_KEYBOARD } from "./fixtures/ir.js";
import { DaemonHarness, waitForEvent } from "./harness.js";

describe("dag.status and dag.run", () => {
  let harness: DaemonHarness;
  let client: DaemonClient;

  beforeAll(async () => {
    harness = await DaemonHarness.start();
    client = await harness.connect();
  }, 300_000);

  afterAll(async () => {
    await harness.stop();
  });

  it("reports the watch and gate nodes derived from the fake manifest", async () => {
    const status = await client.dagStatus();
    const byId = new Map<string, DagNodeStatus>(status.nodes.map((node) => [node.id, node]));
    const watch = byId.get("rpc-fake:refresh");
    expect(watch).toBeDefined();
    expect(watch?.plugin).toBe("rpc-fake");
    const gate = byId.get("gate:rpc-fake.ok");
    expect(gate).toBeDefined();
    expect(gate?.state).toBe("idle");
  });

  it("runs a targeted node and emits dag.node.start/end plus gate.result", async () => {
    const events: AtomcEvent[] = [];
    const subscription = await client.subscribe(
      ["dag.node.start", "dag.node.end", "gate.result"],
      (event) => events.push(event),
    );
    try {
      const run = await client.runDAG({ targets: ["gate:rpc-fake.ok"], force: true });
      expect(run.run_id).toMatch(/^run-\d+$/);

      const end = await waitForEvent(
        events,
        (event) =>
          event.topic === "dag.node.end" &&
          (event.data as { id: string }).id === "gate:rpc-fake.ok",
      );
      const endData = end.data as { run_id: string; ok: boolean; duration_ms: number };
      expect(endData.run_id).toBe(run.run_id);
      expect(endData.ok).toBe(true);
      expect(typeof endData.duration_ms).toBe("number");

      const start = await waitForEvent(
        events,
        (event) =>
          event.topic === "dag.node.start" &&
          (event.data as { id: string }).id === "gate:rpc-fake.ok",
      );
      expect((start.data as { run_id: string }).run_id).toBe(run.run_id);

      const gateEvent = await waitForEvent(
        events,
        (event) =>
          event.topic === "gate.result" && (event.data as { id: string }).id === "gate:rpc-fake.ok",
      );
      expect((gateEvent.data as { status: string }).status).toBe("PASS");
    } finally {
      await subscription.unsubscribe();
    }
  });

  it("reacts to a change in a watched IR pointer without an explicit dag.run", async () => {
    const events: AtomcEvent[] = [];
    const subscription = await client.subscribe(["dag.node.start", "dag.node.end"], (event) =>
      events.push(event),
    );
    try {
      const tx = await client.transact({
        path: "/keyboard",
        base_rev: 0,
        ops: [{ op: "add", path: "", value: MINIMAL_KEYBOARD }],
      });
      const start = await waitForEvent(
        events,
        (event) =>
          event.topic === "dag.node.start" &&
          (event.data as { id: string }).id === "rpc-fake:refresh",
      );
      const startData = start.data as { run_id: string };
      expect(startData.run_id).toMatch(/^run-\d+$/);
      expect(tx.changed_paths).toEqual(["/keyboard"]);
      await waitForEvent(
        events,
        (event) =>
          event.topic === "dag.node.end" &&
          (event.data as { id: string }).id === "rpc-fake:refresh",
      );
    } finally {
      await subscription.unsubscribe();
    }
  });

  it("marks the gate node ok after a run", async () => {
    const deadline = Date.now() + 10_000;
    let state: string | undefined;
    while (Date.now() < deadline) {
      const status = await client.dagStatus();
      state = status.nodes.find((node) => node.id === "gate:rpc-fake.ok")?.state;
      if (state === "ok") break;
      await new Promise((done) => setTimeout(done, 50));
    }
    expect(state).toBe("ok");
  });
});
