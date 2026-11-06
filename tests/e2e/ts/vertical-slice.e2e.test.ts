/**
 * End-to-end vertical slice over a real `atomcd` process (WP-4.5).
 *
 * This is the milestone test: a temp project seeded from `examples/atomc-pad/system_ir.json`
 * is served by the **real** daemon, which discovers the four built-in plugins through their
 * `atomc.plugins` entry points, derives the reactive DAG, runs every watch and gate, and
 * reports results over real WebSocket RPC.
 *
 * Honesty rules baked into the assertions:
 * - Every gate outcome is read from a real `gate.result` event emitted by the daemon during
 *   the DAG run — never synthesised here.
 * - `fw.qmk_compile` and `fw.renode_boot` must `SKIP` because the harness runs the daemon
 *   without external toolchains (this holds on a developer machine *and* on clean CI).
 * - `fw.matrix_scan` is declared-not-implemented and must always `SKIP`.
 * - `erc.no_unconnected` genuinely `FAIL`s on the committed pad fixture: six MCU-only nets
 *   (SWDIO/SWCLK/NRST/BOOT0/UART_TX/UART_RX) have a single pin in the hand-authored IR. That
 *   is the fixture's real state, recorded exactly rather than papered over.
 * - Every result carries evidence; no gate may report a bare PASS.
 */
import type { DaemonClient, GateResult } from "@atomc/daemon-client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DaemonHarness, dagNodeIds, EXPECTED_PLUGINS, gatesById, runFullDag } from "./harness.js";

/** DAG nodes derived from the four plugins' manifests (5 watches + 13 gates). */
const WATCH_NODES = [
  "atopile:build",
  "cad:generate",
  "qmk:firmware",
  "qmk:keyboard",
  "renode:generate",
] as const;

const GATE_NODES = [
  "gate:erc.no_unconnected",
  "gate:erc.assertions",
  "gate:layout.testpads.min_count",
  "gate:layout.testpads.nets_covered",
  "gate:fw.renode_boot",
  "gate:fw.matrix_scan",
  "gate:fw.matrix_pins_match_ir",
  "gate:fw.qmk_compile",
  "gate:mech.plate_switch_cutouts_14mm",
  "gate:mech.case_usb_cutout_aligned",
  "gate:mech.pogo_spacing_ge_2p54",
  "gate:mech.jig_no_collision",
  "gate:mech.enclosure_clearance",
] as const;

/**
 * Deterministic expected outcomes for the seeded fixture with no external toolchains.
 * `PASS`/`FAIL` are dictated by the IR; `SKIP` is the honest toolchain-independent result.
 */
const EXPECTED_STATUS: Record<string, GateResult["status"]> = {
  "gate:erc.no_unconnected": "FAIL",
  "gate:erc.assertions": "PASS",
  "gate:layout.testpads.min_count": "PASS",
  "gate:layout.testpads.nets_covered": "PASS",
  "gate:fw.matrix_pins_match_ir": "PASS",
  "gate:fw.qmk_compile": "SKIP",
  "gate:fw.renode_boot": "SKIP",
  "gate:fw.matrix_scan": "SKIP",
  "gate:mech.plate_switch_cutouts_14mm": "PASS",
  "gate:mech.case_usb_cutout_aligned": "PASS",
  "gate:mech.pogo_spacing_ge_2p54": "PASS",
  "gate:mech.jig_no_collision": "PASS",
  "gate:mech.enclosure_clearance": "PASS",
};

/** The six single-pin nets in the committed pad fixture, in IR order. */
const BASELINE_UNCONNECTED = [
  "net:SWDIO",
  "net:SWCLK",
  "net:NRST",
  "net:BOOT0",
  "net:UART_TX",
  "net:UART_RX",
];

/** Nodes no plugin writes during the DAG run; their IR must be byte-identical afterwards. */
const READ_ONLY_NODES = ["/electrical", "/keyboard", "/layout", "/firmware", "/mechanical"];

type NodeSnapshot = { rev: number; value: unknown };

async function snapshotNodes(
  client: DaemonClient,
  paths: readonly string[],
): Promise<Map<string, NodeSnapshot>> {
  const entries = await Promise.all(
    paths.map(async (path) => [path, await client.getIR(path)] as const),
  );
  return new Map(entries);
}

function unconnectedEvidence(result: GateResult): { net: string; pins: number }[] {
  const evidence = result.evidence.find((item) => item.kind === "json" && item.data !== undefined);
  const data = evidence?.data as { unconnected?: { net: string; pins: number }[] } | undefined;
  return data?.unconnected ?? [];
}

describe("atomc build vertical slice over the real daemon", () => {
  let harness: DaemonHarness;
  let client: DaemonClient;

  beforeEach(async () => {
    harness = await DaemonHarness.start();
    client = await harness.connect();
  }, 300_000);

  afterEach(async () => {
    await harness.stop();
    // Teardown assertion: the real daemon process must not be left running.
    await harness.assertProcessDead();
  });

  it("discovers all four plugins with no load errors", async () => {
    const plugins = await client.listPlugins();
    const byName = new Map(plugins.map((plugin) => [plugin.name, plugin]));
    for (const name of EXPECTED_PLUGINS) {
      const plugin = byName.get(name);
      expect(plugin, `plugin ${name} must be discovered`).toBeDefined();
      expect(plugin?.loaded, `plugin ${name} error: ${plugin?.error ?? "none"}`).toBe(true);
      expect(plugin?.error).toBeUndefined();
    }
  });

  it("derives the expected watch + gate DAG from the four plugin manifests", async () => {
    const status = await client.dagStatus();
    const ids = new Set(dagNodeIds(status));
    for (const id of [...WATCH_NODES, ...GATE_NODES]) {
      expect(ids.has(id), `DAG must contain ${id}`).toBe(true);
    }
    expect(ids.size).toBe(WATCH_NODES.length + GATE_NODES.length);
  });

  it("runs every node and reports the fixture's real gate outcomes over RPC", async () => {
    const { events, gates } = await runFullDag(client);

    // Every node finished successfully (a crashed node aborts the run and surfaces here).
    const ends = events.filter((event) => event.topic === "dag.node.end") as Array<{
      topic: "dag.node.end";
      data: { run_id: string; id: string; ok: boolean; error?: string; duration_ms: number };
    }>;
    expect(ends.length).toBe(WATCH_NODES.length + GATE_NODES.length);
    for (const end of ends) {
      expect(end.data.ok, `node ${end.data.id} failed: ${end.data.error ?? ""}`).toBe(true);
    }

    // Every declared gate produced exactly one result event.
    const byId = gatesById(gates);
    expect([...byId.keys()].sort()).toEqual([...GATE_NODES].sort());

    for (const id of GATE_NODES) {
      const result = byId.get(id);
      expect(result, `missing gate result for ${id}`).toBeDefined();
      if (result === undefined) continue;
      expect(result.status, `${id} status (${result.summary})`).toBe(EXPECTED_STATUS[id]);
      // Every result must explain itself; FAIL/SKIP additionally carry evidence.
      expect(result.summary.length, `${id} needs a summary`).toBeGreaterThan(0);
      if (result.status === "FAIL" || result.status === "SKIP") {
        expect(
          result.evidence.length,
          `${id} ${result.status} must carry evidence`,
        ).toBeGreaterThan(0);
      }
    }
  });

  it("records the erc.no_unconnected FAIL with the fixture's exact single-pin nets", async () => {
    const { gates } = await runFullDag(client);
    const result = gatesById(gates).get("gate:erc.no_unconnected");
    expect(result?.status).toBe("FAIL");
    const unconnected = unconnectedEvidence(result as GateResult);
    expect(unconnected.map((entry) => entry.net)).toEqual(BASELINE_UNCONNECTED);
    expect(unconnected.every((entry) => entry.pins === 1)).toBe(true);
  });

  it("keeps the IR unchanged where no plugin writes, and mutates /simulation where it does", async () => {
    const before = await snapshotNodes(client, READ_ONLY_NODES);
    const simulationBefore = await client.getIR("/simulation");

    await runFullDag(client);

    for (const path of READ_ONLY_NODES) {
      const prior = before.get(path);
      const current = await client.getIR(path);
      expect(current.rev, `${path} rev must not change`).toBe(prior?.rev);
      expect(current.value, `${path} value must not change`).toEqual(prior?.value);
    }

    // The renode watch node has a real handler and records generated script paths.
    const simulationAfter = await client.getIR("/simulation");
    expect(simulationAfter.value).not.toEqual(simulationBefore.value);
    expect(simulationAfter.rev).toBeGreaterThan(simulationBefore.rev);
  });
});
