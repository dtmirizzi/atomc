/**
 * Failure-honesty spec for the vertical slice (WP-4.5).
 *
 * A gate that only ever `PASS`es would be worthless. This spec mutates the seeded
 * `atomc-pad` IR over **real RPC** and asserts that `erc.no_unconnected` reacts to the new
 * state with a `FAIL` whose evidence names the mutation — proving the result is evaluated
 * on live daemon IR rather than a cached or fabricated outcome.
 *
 * The committed fixture's single-pin debug nets terminate on test pads (connected),
 * so the baseline PASSes. The spec then:
 * 1. transacts a brand-new single-pin net with NO test pad (`net:ORPHAN` on `comp:J9`);
 * 2. reruns the gate and asserts a FAIL whose evidence names the mutation;
 * 3. connects the orphan with a second pin and asserts the gate flips back to PASS.
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

function unconnectedEvidence(
  result: GateResult,
): { net: string; pins: number; pin_refs?: string[] }[] {
  const evidence = result.evidence.find((item) => item.kind === "json" && item.data !== undefined);
  const data = evidence?.data as
    | { unconnected?: { net: string; pins: number; pin_refs?: string[] }[] }
    | undefined;
  return data?.unconnected ?? [];
}

/** Match an evidence entry on net and pins, ignoring the pin_refs detail. */
function namesNet(entries: { net: string; pins: number }[], net: string, pins: number): boolean {
  return entries.some((entry) => entry.net === net && entry.pins === pins);
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
    // Debug nets terminate on test pads, so the untouched fixture is connected.
    expect(baselineResult?.status).toBe("PASS");

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
    expect(namesNet(unconnectedEvidence(mutatedResult as GateResult), "net:ORPHAN", 1)).toBe(true);

    // The mutation is visible on subsequent reads too: the daemon persisted it.
    const reread = await client.getIR("/electrical");
    const nets = (reread.value as { nets: { id: string }[] }).nets;
    expect(nets.some((net) => net.id === "net:ORPHAN")).toBe(true);
    expect(reread.rev).toBeGreaterThan(electrical.rev);
  });

  it("flips back to PASS when the orphan net is genuinely connected over RPC", async () => {
    // Start from the connected baseline, then break a debug net by removing its
    // test pad: the net is then genuinely dangling (one pin, no pad).
    const layout = await client.getIR("/layout");
    const pads = (layout.value as { test_pads: { id: string; net_ref: string }[] }).test_pads;
    const swdioPad = pads.find((pad) => pad.net_ref === "net:SWDIO");
    expect(swdioPad).toBeDefined();

    await client.transact({
      path: "/layout",
      base_rev: layout.rev,
      ops: [{ op: "remove", path: `/test_pads/${pads.indexOf(swdioPad!)}` }],
      holder: "test:wp-4.5",
    });
    const broken = (await client.runGates([GATE_ID]))[0];
    expect(broken?.status).toBe("FAIL");
    expect(namesNet(unconnectedEvidence(broken as GateResult), "net:SWDIO", 1)).toBe(true);

    // Give the net a second pin: a debug header connection, through the same
    // optimistic-concurrency RPC. The gate must flip back to PASS.
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
            pins: [{ number: "1", net_ref: "net:SWDIO" }],
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
