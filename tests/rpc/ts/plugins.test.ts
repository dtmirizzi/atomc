/**
 * `plugins.list`, `tools.list` allow-list filtering, read tools, and mutating-tool
 * scope enforcement (`produces`) against the real daemon + fake plugin.
 */
import { type DaemonClient, PluginError } from "@atomc/daemon-client";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { FAKE_PLUGIN_NAME } from "./fixtures/fake-plugin.js";
import { EMPTY_ELECTRICAL } from "./fixtures/ir.js";
import { DaemonHarness } from "./harness.js";

interface GateManifestEntry {
  id: string;
}

describe("plugins.list and tools", () => {
  let harness: DaemonHarness;
  let client: DaemonClient;

  beforeAll(async () => {
    harness = await DaemonHarness.start();
    client = await harness.connect();
    await client.transact({
      path: "/electrical",
      base_rev: 0,
      ops: [{ op: "add", path: "", value: EMPTY_ELECTRICAL }],
    });
  }, 300_000);

  afterAll(async () => {
    await harness.stop();
  });

  it("lists the discovered fake plugin as loaded with its manifest", async () => {
    const plugins = await client.listPlugins();
    const plugin = plugins.find((entry) => entry.name === FAKE_PLUGIN_NAME);
    expect(plugin).toBeDefined();
    expect(plugin?.loaded).toBe(true);
    expect(plugin?.error).toBeUndefined();
    expect(plugin?.watches.map((watch) => watch.id)).toEqual(["rpc-fake:refresh"]);
    expect(plugin?.gates.map((gate: GateManifestEntry) => gate.id).sort()).toEqual([
      "gate:rpc-fake.fail",
      "gate:rpc-fake.ok",
    ]);
  });

  it("lists both tools and filters by agent allow-list", async () => {
    const all = await client.listTools();
    expect(all.map((tool) => tool.name).sort()).toEqual(["add_net", "read_status"]);

    const ee = await client.listTools("ee-agent");
    expect(ee.map((tool) => tool.name)).toEqual(["read_status"]);

    const ops = await client.listTools("ops-agent");
    expect(ops.map((tool) => tool.name).sort()).toEqual(["add_net", "read_status"]);
    expect(ops.find((tool) => tool.name === "add_net")?.mutates).toBe(true);
  });

  it("returns the declared read-tool result", async () => {
    const outcome = await client.callTool(FAKE_PLUGIN_NAME, "read_status", {});
    expect(outcome.result).toEqual({ ok: true, plugin: FAKE_PLUGIN_NAME });
  });

  it("applies a mutating tool write and bumps the revision", async () => {
    const before = await client.getIR("/");
    const first = await client.callTool(FAKE_PLUGIN_NAME, "add_net", {});
    const firstResult = first.result as { net: string; new_rev: number };
    expect(firstResult.net).toBe("net:N0");
    expect(firstResult.new_rev).toBe(before.rev + 1);

    const second = await client.callTool(FAKE_PLUGIN_NAME, "add_net", {});
    const secondResult = second.result as { net: string; new_rev: number };
    expect(secondResult.net).toBe("net:N1");
    expect(secondResult.new_rev).toBe(firstResult.new_rev + 1);
  });

  it("rejects a tool writing outside its declared produces scope", async () => {
    const before = await client.getIR("/");
    const error = await client
      .callTool(FAKE_PLUGIN_NAME, "add_net", { path: "/layout" })
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(PluginError);
    if (error instanceof PluginError) {
      expect(error.code).toBe(-32020);
      expect(String(error.detail)).toContain("may not write");
    }
    const after = await client.getIR("/");
    expect(after.rev).toBe(before.rev);
    expect((after.value as { layout: unknown }).layout).toBeNull();
  });
});
