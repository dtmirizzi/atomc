import type { DaemonClient, GateResult } from "@atomc/daemon-client";
import { describe, expect, it, vi } from "vitest";
import { createDaemonStudioApi } from "../src/daemon-api.js";

function makeGate(overrides: Partial<GateResult> = {}): GateResult {
  return {
    id: "gate:erc.clean",
    status: "PASS",
    severity: "blocking",
    plugin: "atopile",
    owner_agent: "ee-agent",
    evaluated_at: "2026-11-04T00:00:00Z",
    ir_rev: 7,
    duration_ms: 14,
    summary: "ERC passed",
    evidence: [],
    suggestions: [],
    refs: [],
    ...overrides,
  };
}

function fakeClient(overrides: Partial<Record<string, unknown>> = {}): DaemonClient {
  return {
    getIR: vi.fn().mockResolvedValue({ rev: 42, value: { meta: { rev: 42 } } }),
    dagStatus: vi.fn().mockResolvedValue({
      nodes: [
        { id: "a", plugin: "atopile", state: "ok" },
        { id: "b", plugin: "qmk", state: "running" },
        { id: "c", plugin: "cad-jig", state: "failed" },
        { id: "d", plugin: "sourcing", state: "stale" },
        { id: "e", plugin: "future", state: "unknown" },
        { id: "f", plugin: "renode", state: "queued" },
      ],
    }),
    listGates: vi
      .fn()
      .mockResolvedValue([makeGate(), makeGate({ id: "gate:bad", status: "FAIL" })]),
    runDAG: vi.fn().mockResolvedValue({ run_id: "run-42" }),
    ...overrides,
  } as unknown as DaemonClient;
}

describe("createDaemonStudioApi", () => {
  it("loads IR revision, DAG states and actual gate results from the local daemon", async () => {
    const client = fakeClient();
    const factory = vi.fn(async () => client);
    const api = createDaemonStudioApi({
      projectName: "fixture-board",
      projectPath: "/tmp/fixture-board",
      clientFactory: factory,
    });

    const snapshot = await api.load();
    expect(factory).toHaveBeenCalledOnce();
    expect(client.getIR).toHaveBeenCalledWith("/");
    expect(snapshot).toMatchObject({
      projectName: "fixture-board",
      projectPath: "/tmp/fixture-board",
      connection: "connected",
      revision: 42,
      nodes: [
        { id: "a", state: "passed" },
        { id: "b", state: "running" },
        { id: "c", state: "failed" },
        { id: "d", state: "stale" },
        { id: "e", state: "idle" },
        { id: "f", state: "queued" },
      ],
      gates: [
        { id: "gate:erc.clean", status: "PASS" },
        { id: "gate:bad", status: "FAIL" },
      ],
    });
    expect(snapshot.agents).toHaveLength(4);
    expect(snapshot.activity[0]?.detail).toContain("1 passing gates");
  });

  it("reuses one client and returns independent snapshots", async () => {
    const client = fakeClient();
    const factory = vi.fn(async () => client);
    const api = createDaemonStudioApi({
      projectName: "fixture-board",
      projectPath: ".",
      clientFactory: factory,
    });
    const first = await api.load();
    const firstAgent = first.agents[0];
    if (!firstAgent) throw new Error("daemon fixture must provide an agent");
    firstAgent.label = "mutated";
    const second = await api.load();
    expect(factory).toHaveBeenCalledOnce();
    expect(second.agents[0]?.label).toBe("Electrical");
  });

  it("runs a DAG then refreshes live state when Run Build is requested", async () => {
    const client = fakeClient();
    const api = createDaemonStudioApi({
      projectName: "fixture-board",
      projectPath: ".",
      clientFactory: async () => client,
    });
    const snapshot = await api.runBuild();
    expect(client.runDAG).toHaveBeenCalledOnce();
    expect(client.getIR).toHaveBeenCalledOnce();
    expect(snapshot.revision).toBe(42);
    expect(snapshot.connection).toBe("connected");
  });

  it("fails closed when the RPC snapshot cannot be loaded", async () => {
    const api = createDaemonStudioApi({
      projectName: "fixture-board",
      projectPath: ".",
      clientFactory: async () =>
        fakeClient({
          dagStatus: vi.fn().mockRejectedValue(new Error("connection dropped")),
        }),
    });
    await expect(api.load()).rejects.toThrow("connection dropped");
  });

  it("uses a fresh client after a rejected connection attempt", async () => {
    const goodClient = fakeClient();
    const factory = vi
      .fn()
      .mockRejectedValueOnce(new Error("connect failed"))
      .mockResolvedValue(goodClient);
    const api = createDaemonStudioApi({
      projectName: "fixture-board",
      projectPath: ".",
      clientFactory: factory,
    });
    await expect(api.load()).rejects.toThrow("connect failed");
    await expect(api.load()).resolves.toMatchObject({ connection: "connected", revision: 42 });
    expect(factory).toHaveBeenCalledTimes(2);
  });

  it("connects through the configured loopback URL via the trusted host bridge", async () => {
    const factory = vi.fn(async () => fakeClient());
    const api = createDaemonStudioApi({
      projectName: "fixture-board",
      projectPath: ".",
      url: "ws://127.0.0.1:9001/rpc",
      clientFactory: factory,
    });
    await api.load();
    expect(factory).toHaveBeenCalledWith("ws://127.0.0.1:9001/rpc");
  });
});
