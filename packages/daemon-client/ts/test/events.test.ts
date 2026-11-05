import { afterEach, describe, expect, it } from "vitest";
import { type AtomcEvent, DaemonClient } from "../src/index.js";
import { MockRpcServer } from "./helpers/mock-server.js";

let server: MockRpcServer | undefined;
let client: DaemonClient | undefined;

afterEach(async () => {
  await client?.close();
  client = undefined;
  await server?.close();
  server = undefined;
});

async function waitFor(predicate: () => boolean, timeoutMs = 1000): Promise<void> {
  const start = Date.now();
  while (!predicate()) {
    if (Date.now() - start > timeoutMs) throw new Error("waitFor timed out");
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

describe("DaemonClient events", () => {
  it("registers a server subscription and routes matching events", async () => {
    server = await MockRpcServer.start({ handler: () => ({ subscription: "sub-1" }) });
    const c = await DaemonClient.connect({ url: server.url });
    client = c;

    const events: AtomcEvent[] = [];
    const subscription = await c.subscribe(["ir.changed"], (event) => events.push(event));
    expect(subscription.id).toBe("sub-1");
    expect(server.requests[0]?.method).toBe("events.subscribe");
    expect(server.requests[0]?.params).toEqual({ topics: ["ir.changed"] });

    server.notify("ir.changed", { rev: 5, changed_paths: ["/electrical"] });
    server.notify("log", { level: "info", msg: "ignored" });
    await waitFor(() => events.length === 1);

    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({
      topic: "ir.changed",
      data: { rev: 5, changed_paths: ["/electrical"] },
    });
  });

  it("supports wildcard subscriptions", async () => {
    server = await MockRpcServer.start({ handler: () => ({ subscription: "sub-all" }) });
    const c = await DaemonClient.connect({ url: server.url });
    client = c;

    const topics: string[] = [];
    await c.subscribe(["*"], (event) => topics.push(event.topic));
    server.notify("gate.result", { id: "gate:x" });
    server.notify("log", { level: "info", msg: "hi" });
    await waitFor(() => topics.length === 2);
    expect(topics).toEqual(["gate.result", "log"]);
  });

  it("keeps serving events when a listener throws", async () => {
    let nextId = 0;
    server = await MockRpcServer.start({
      handler: () => ({ subscription: `sub-2-${++nextId}` }),
    });
    const errors: unknown[] = [];
    const c = await DaemonClient.connect({ url: server.url, onError: (e) => errors.push(e) });
    client = c;

    let good = 0;
    await c.subscribe(["ir.changed"], () => {
      throw new Error("listener boom");
    });
    await c.subscribe(["ir.changed"], () => {
      good += 1;
    });

    server.notify("ir.changed", { rev: 1, changed_paths: [] });
    await waitFor(() => good === 1);
    expect(good).toBe(1);
    expect(errors.length).toBeGreaterThan(0);
  });

  it("unsubscribes and stops delivering events", async () => {
    server = await MockRpcServer.start({ handler: () => ({ subscription: "sub-3" }) });
    const c = await DaemonClient.connect({ url: server.url });
    client = c;

    let count = 0;
    const subscription = await c.subscribe(["ir.changed"], () => {
      count += 1;
    });
    await subscription.unsubscribe();
    expect(server.requests.some((r) => r.method === "events.unsubscribe")).toBe(true);
    expect(server.requests.at(-1)?.params).toEqual({ subscription: "sub-3" });

    server.notify("ir.changed", { rev: 2, changed_paths: [] });
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(count).toBe(0);
  });
});
