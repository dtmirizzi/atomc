/**
 * Event subscription contract: `events.subscribe` / `events.unsubscribe` and delivery
 * of `ir.changed` and `gate.result` notifications over the real WebSocket.
 */
import type { AtomcEvent, DaemonClient } from "@atomc/daemon-client";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { EMPTY_ELECTRICAL } from "./fixtures/ir.js";
import { DaemonHarness, waitForEvent } from "./harness.js";

function sleep(ms: number): Promise<void> {
  return new Promise((done) => setTimeout(done, ms));
}

describe("event subscriptions", () => {
  let harness: DaemonHarness;
  let client: DaemonClient;

  beforeAll(async () => {
    harness = await DaemonHarness.start();
    client = await harness.connect();
  }, 300_000);

  afterAll(async () => {
    await harness.stop();
  });

  it("delivers ir.changed with rev and changed_paths", async () => {
    const events: AtomcEvent[] = [];
    const subscription = await client.subscribe(["ir.changed"], (event) => events.push(event));
    try {
      await client.transact({
        path: "/electrical",
        base_rev: 0,
        ops: [{ op: "add", path: "", value: EMPTY_ELECTRICAL }],
      });
      const changed = await waitForEvent(events, (event) => event.topic === "ir.changed");
      const data = changed.data as { rev: number; changed_paths: string[] };
      expect(data.rev).toBe(1);
      expect(data.changed_paths).toEqual(["/electrical"]);
    } finally {
      await subscription.unsubscribe();
    }
  });

  it("delivers gate.result with the frozen GateResult payload", async () => {
    const events: AtomcEvent[] = [];
    const subscription = await client.subscribe(["gate.result"], (event) => events.push(event));
    try {
      await client.runGates(["gate:rpc-fake.ok"]);
      const event = await waitForEvent(
        events,
        (candidate) =>
          candidate.topic === "gate.result" &&
          (candidate.data as { id: string }).id === "gate:rpc-fake.ok",
      );
      const data = event.data as { status: string; plugin: string };
      expect(data.status).toBe("PASS");
      expect(data.plugin).toBe("plugin:rpc-fake@0.1.0");
    } finally {
      await subscription.unsubscribe();
    }
  });

  it("stops delivery after events.unsubscribe", async () => {
    const rev = (await client.getIR("/electrical")).rev;
    const events: AtomcEvent[] = [];
    const subscription = await client.subscribe(["ir.changed"], (event) => events.push(event));
    await subscription.unsubscribe();

    await client.transact({
      path: "/electrical",
      base_rev: rev,
      ops: [{ op: "add", path: "/nets/-", value: { id: "net:Z", name: "Z" } }],
    });
    await sleep(500);
    expect(events).toEqual([]);
  });
});
