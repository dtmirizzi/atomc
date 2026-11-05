import { afterEach, describe, expect, it } from "vitest";
import type WebSocket from "ws";
import {
  ConnectionClosedError,
  ConnectionError,
  DaemonClient,
  LockedError,
  MalformedResponseError,
  PluginError,
  RpcError,
  TimeoutError,
  ValidationError,
} from "../src/index.js";
import { MockRpcServer, NO_RESPONSE, rpcError } from "./helpers/mock-server.js";

let server: MockRpcServer | undefined;
let client: DaemonClient | undefined;

afterEach(async () => {
  await client?.close();
  client = undefined;
  await server?.close();
  server = undefined;
});

async function connect(
  options: Parameters<typeof DaemonClient.connect>[0] = {},
): Promise<DaemonClient> {
  client = await DaemonClient.connect(options);
  return client;
}

describe("DaemonClient request/response", () => {
  it("connects, sends a request, and resolves with the result", async () => {
    server = await MockRpcServer.start({ handler: () => ({ rev: 7, value: { ok: true } }) });
    const c = await connect({ url: server.url });
    await expect(c.getIR()).resolves.toEqual({ rev: 7, value: { ok: true } });
    expect(server.requests[0]?.method).toBe("ir.get");
    expect(server.requests[0]?.params).toEqual({ path: "/" });
  });

  it("correlates concurrent in-flight requests even when responses arrive out of order", async () => {
    server = await MockRpcServer.start({
      handler: async (req) => {
        if (req.method === "first") {
          await new Promise((resolve) => setTimeout(resolve, 40));
          return "one";
        }
        return "two";
      },
    });
    const c = await connect({ url: server.url });
    const [a, b] = await Promise.all([c.request<string>("first"), c.request<string>("second")]);
    expect(a).toBe("one");
    expect(b).toBe("two");
  });

  it("maps JSON-RPC error codes to typed error classes", async () => {
    const codes: Record<string, unknown> = {
      conflict: rpcError(-32010, "stale", { current_rev: 9, expected_rev: 8 }),
      locked: rpcError(-32011, "locked", {
        holder: "agent:ee",
        expires_at: "2026-11-04T23:00:00Z",
      }),
      validation: rpcError(-32012, "bad", {
        errors: [{ path: "/x", message: "nope", type: "value" }],
      }),
      plugin: rpcError(-32020, "boom", { plugin: "sourcing", tool: "search", retryable: true }),
      generic: rpcError(-32603, "internal"),
    };
    server = await MockRpcServer.start({
      handler: (req) => codes[req.method] ?? null,
    });
    const c = await connect({ url: server.url });

    const locked = c.request("locked").catch((e: unknown) => e as LockedError);
    await expect(locked).resolves.toBeInstanceOf(LockedError);

    const lockedErr = (await c.request("locked").catch((e: unknown) => e)) as LockedError;
    expect(lockedErr.holder).toBe("agent:ee");
    expect(lockedErr.code).toBe(-32011);

    const validationErr = (await c
      .request("validation")
      .catch((e: unknown) => e)) as ValidationError;
    expect(validationErr).toBeInstanceOf(ValidationError);
    expect(validationErr.errors).toEqual([{ path: "/x", message: "nope", type: "value" }]);

    const pluginErr = (await c.request("plugin").catch((e: unknown) => e)) as PluginError;
    expect(pluginErr).toBeInstanceOf(PluginError);
    expect(pluginErr.plugin).toBe("sourcing");
    expect(pluginErr.retryable).toBe(true);

    const genericErr = (await c.request("generic").catch((e: unknown) => e)) as RpcError;
    expect(genericErr).toBeInstanceOf(RpcError);
    expect(genericErr.code).toBe(-32603);
  });

  it("reports malformed frames and continues serving requests", async () => {
    server = await MockRpcServer.start({ handler: () => "ok" });
    const errors: unknown[] = [];
    const c = await connect({ url: server.url, onError: (e) => errors.push(e) });
    const seen = new Promise<void>((resolve) => {
      const timer = setInterval(() => {
        if (errors.length > 0) {
          clearInterval(timer);
          resolve();
        }
      }, 5);
    });
    server.sendRaw("this is not json");
    await seen;
    expect(errors.length).toBeGreaterThan(0);
    await expect(c.request("ping")).resolves.toBe("ok");
  });

  it("ignores responses with an unknown id", async () => {
    server = await MockRpcServer.start({
      handler: (req) => {
        req.socket.send(JSON.stringify({ jsonrpc: "2.0", id: 99999, result: "intruder" }));
        return "real";
      },
    });
    const c = await connect({ url: server.url });
    await expect(c.request("ping")).resolves.toBe("real");
  });

  it("rejects a request that exceeds its timeout", async () => {
    server = await MockRpcServer.start({ handler: () => NO_RESPONSE });
    const c = await connect({ url: server.url, timeoutMs: 40 });
    await expect(c.request("slow")).rejects.toBeInstanceOf(TimeoutError);
  });

  it("rejects pending requests when the socket is terminated", async () => {
    server = await MockRpcServer.start({ handler: () => NO_RESPONSE });
    const c = await connect({ url: server.url });
    const pending = c.request("stuck");
    server.terminateAll();
    await expect(pending).rejects.toBeInstanceOf(ConnectionClosedError);
    await expect(c.request("after")).rejects.toBeInstanceOf(ConnectionClosedError);
  });

  it("rejects pending requests on explicit close()", async () => {
    server = await MockRpcServer.start({ handler: () => NO_RESPONSE });
    const c = await connect({ url: server.url });
    const pending = c.request("stuck");
    await c.close();
    await expect(pending).rejects.toBeInstanceOf(ConnectionClosedError);
    expect(c.closed).toBe(true);
  });

  it("sends the bearer token in the upgrade request", async () => {
    server = await MockRpcServer.start({ handler: () => "ok", requireToken: "s3cret" });
    const c = await connect({ url: server.url, token: "s3cret" });
    await expect(c.request("ping")).resolves.toBe("ok");
  });

  it("fails to connect when the token is wrong", async () => {
    server = await MockRpcServer.start({ handler: () => "ok", requireToken: "s3cret" });
    await expect(
      DaemonClient.connect({ url: server.url, token: "wrong", timeoutMs: 2000 }),
    ).rejects.toBeInstanceOf(Error);
  });

  it("exposes typed method wrappers that send the documented params", async () => {
    server = await MockRpcServer.start({
      handler: () => {
        const method = server?.requests.at(-1)?.method;
        return method === "gates.list" || method === "gates.run" ? [] : {};
      },
    });
    const c = await connect({ url: server.url });
    await c.getIR("/electrical");
    await c.transact({ path: "/electrical", base_rev: 3, ops: [] });
    await c.lock("/electrical", "agent:ee", 30, "swap");
    await c.unlock("/electrical", "agent:ee");
    await c.dagStatus();
    await c.runDAG({ targets: ["sourcing:bom-refresh"], force: true });
    await c.listGates(["gate:erc.no_unconnected"]);
    await c.runGates();
    await c.listPlugins();
    await c.listTools("ee-agent");
    await c.callTool("sourcing", "search_parts", { q: "x" });
    await c.daemonStatus();
    await c.shutdown();

    const byMethod = new Map(server.requests.map((r) => [r.method, r.params]));
    expect(byMethod.get("ir.get")).toEqual({ path: "/electrical" });
    expect(byMethod.get("ir.transact")).toEqual({ path: "/electrical", base_rev: 3, ops: [] });
    expect(byMethod.get("ir.lock")).toEqual({
      node: "/electrical",
      holder: "agent:ee",
      ttl_s: 30,
      reason: "swap",
    });
    expect(byMethod.get("ir.unlock")).toEqual({ node: "/electrical", holder: "agent:ee" });
    expect(byMethod.get("dag.status")).toEqual({});
    expect(byMethod.get("dag.run")).toEqual({ targets: ["sourcing:bom-refresh"], force: true });
    expect(byMethod.get("gates.list")).toEqual({ ids: ["gate:erc.no_unconnected"] });
    expect(byMethod.get("gates.run")).toEqual({});
    expect(byMethod.get("plugins.list")).toEqual({});
    expect(byMethod.get("tools.list")).toEqual({ agent: "ee-agent" });
    expect(byMethod.get("tools.call")).toEqual({
      plugin: "sourcing",
      tool: "search_parts",
      args: { q: "x" },
    });
    expect(byMethod.get("daemon.status")).toEqual({});
    expect(byMethod.get("daemon.shutdown")).toEqual({});
  });

  it("rejects with ConnectionError when the endpoint is unreachable", async () => {
    await expect(
      DaemonClient.connect({ url: "ws://127.0.0.1:1/rpc", timeoutMs: 2000 }),
    ).rejects.toBeInstanceOf(ConnectionError);
  });

  it("rejects with TimeoutError when the socket never opens", async () => {
    class NeverOpenSocket {
      static readonly OPEN = 1;
      readyState = 0;
      on(): this {
        return this;
      }
      once(): this {
        return this;
      }
      off(): this {
        return this;
      }
      removeAllListeners(): this {
        return this;
      }
      terminate(): void {}
      close(): void {}
      send(): void {}
    }
    await expect(
      DaemonClient.connect({
        url: "ws://127.0.0.1:0/rpc",
        timeoutMs: 30,
        WebSocketImpl: NeverOpenSocket as unknown as typeof WebSocket,
      }),
    ).rejects.toBeInstanceOf(TimeoutError);
  });

  it("handles malformed notifications, envelopes, and responses", async () => {
    server = await MockRpcServer.start({
      handler: (req) => {
        switch (req.method) {
          case "array":
            req.socket.send(JSON.stringify([{ jsonrpc: "2.0", id: req.id, result: 1 }]));
            return "ok";
          case "bad-version":
            req.socket.send(JSON.stringify({ jsonrpc: "1.0", id: req.id, result: 1 }));
            return "ok";
          case "bad-id":
            req.socket.send(JSON.stringify({ jsonrpc: "2.0", id: true, result: 1 }));
            return "ok";
          case "no-topic":
            req.socket.send(JSON.stringify({ jsonrpc: "2.0", method: "event", params: {} }));
            return "ok";
          case "empty":
            req.socket.send(JSON.stringify({ jsonrpc: "2.0", id: req.id }));
            return NO_RESPONSE;
          default:
            return "ok";
        }
      },
    });
    const errors: unknown[] = [];
    const c = await connect({ url: server.url, onError: (e) => errors.push(e) });

    await expect(c.request("array")).resolves.toBe("ok");
    await expect(c.request("bad-version")).resolves.toBe("ok");
    await expect(c.request("bad-id")).resolves.toBe("ok");
    await expect(c.request("no-topic")).resolves.toBe("ok");
    await expect(c.request("empty")).rejects.toBeInstanceOf(MalformedResponseError);

    expect(errors.length).toBeGreaterThanOrEqual(4);
  });

  it("treats an empty topic list as subscribe-to-all", async () => {
    server = await MockRpcServer.start({ handler: () => ({ subscription: "sub-empty" }) });
    const c = await connect({ url: server.url });
    let count = 0;
    await c.subscribe([], () => {
      count += 1;
    });
    server.notify("anything", {});
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(count).toBe(1);
  });
});
