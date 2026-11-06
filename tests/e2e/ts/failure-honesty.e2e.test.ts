/**
 * Failure-honesty spec for the vertical slice (WP-4.5).
 *
 * A gate that only ever `PASS`es would be worthless. This spec mutates the seeded
 * `atomc-pad` IR over **real RPC** and asserts that `erc.no_unconnected` reacts to the new
 * state with a `FAIL` whose evidence names the mutation — proving the result is evaluated
 * on live daemon IR rather than a cached or fabricated outcome.
 *
 * The committed fixture already contains single-pin MCU nets, so the test:
 * 1. runs the gate on the untouched fixture and records those nets;
 * 2. transacts a brand-new single-pin net (`net:ORPHAN` on `comp:J9`) through the daemon;
 * 3. reruns the gate and asserts the mutation appears in the evidence, alongside the
 *    baseline nets, with `pins: 1`.
 */
import type { DaemonClient, GateResult } from "@atomc/daemon-client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DaemonHarness } from "./harness.js";

const GATE_ID = "gate:erc.no_unconnected";

const ORPHAN_NET = { id: "net:ORPHAN", name: "ORPHAN" };
const ORPHAN_COMPONENT = {
  id: "comp:J9",
  designator: "J9",
  dnp: false,
  attributes: {},
  package: "SMD",
  pins: [{ number: "1", net_ref: "net:ORPHAN" }],
};

function unconnectedEvidence(result: GateResult): { net: string; pins: number }[] {
  const evidence = result.evidence.find((item) => item.kind === "json" && item.data !== undefined);
  const data = evidence?.data as { unconnected?: { net: string; pins: number }[] } | undefined;
  return data?.unconnected ?? [];
}

describe("gate failure honesty over the real daemon", () => {
  let harness: DaemonHarness;
  let client: DaemonClient;

  beforeEach(async () => {
    harness = await DaemonHarness.start();
    client = await harness.connect();
  }, 300_000);

  afterEach(async () => {
    await harness.stop();
    await harness.assertProcessDead();
  });

  it("fails on a freshly mutated single-pin net and names it in the evidence", async () => {
    const baseline = await client.runGates([GATE_ID]);
    const baselineResult = baseline[0];
    expect(baselineResult?.status).toBe("FAIL");
    expect(unconnectedEvidence(baselineResult as GateResult)).not.toContainEqual({
      net: "net:ORPHAN",
      pins: 1,
    });

    const electrical = await client.getIR("/electrical");
    const tx = await client.transact({
      path: "/electrical",
      base_rev: electrical.rev,
      ops: [
        { op: "add", path: "/nets/-", value: ORPHAN_NET },
        { op: "add", path: "/components/-", value: ORPHAN_COMPONENT },
      ],
      holder: "test:wp-4.5",
    });
    expect(tx.changed_paths.some((path) => path.startsWith("/electrical"))).toBe(true);

    const mutated = await client.runGates([GATE_ID]);
    const mutatedResult = mutated[0];
    expect(mutatedResult?.status).toBe("FAIL");
    expect(mutatedResult?.summary).toMatch(/fewer than 2 connected pins/);
    expect(unconnectedEvidence(mutatedResult as GateResult)).toContainEqual({
      net: "net:ORPHAN",
      pins: 1,
    });

    // The mutation is visible on subsequent reads too: the daemon persisted it.
    const reread = await client.getIR("/electrical");
    const nets = (reread.value as { nets: { id: string }[] }).nets;
    expect(nets.some((net) => net.id === "net:ORPHAN")).toBe(true);
    expect(reread.rev).toBeGreaterThan(electrical.rev);
  });

  it("flips to PASS when the dangling nets are genuinely connected over RPC", async () => {
    const danglingNets = unconnectedEvidence(
      (await client.runGates([GATE_ID]))[0] as GateResult,
    ).map((entry) => entry.net);
    expect(danglingNets.length).toBeGreaterThan(0);

    // Add a debug header that gives each dangling net a second pin. This is a real
    // board fixture edit, performed through the daemon's optimistic-concurrency RPC.
    const electrical = await client.getIR("/electrical");
    await client.transact({
      path: "/electrical",
      base_rev: electrical.rev,
      ops: [
        {
          op: "add",
          path: "/components/-",
          value: {
            id: "comp:J8",
            designator: "J8",
            dnp: false,
            attributes: {},
            mpn: "Debug_Header_1x06",
            package: "PinHeader_1x06",
            pins: danglingNets.map((net, index) => ({
              number: String(index + 1),
              net_ref: net,
            })),
          },
        },
      ],
      holder: "test:wp-4.5",
    });

    const result = (await client.runGates([GATE_ID]))[0];
    expect(result?.status).toBe("PASS");
    expect(unconnectedEvidence(result as GateResult)).toEqual([]);
    expect(result?.evidence.length).toBeGreaterThan(0);
  });
});
