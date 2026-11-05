/**
 * Subtree lock contract: `ir.lock` / `ir.unlock`, cross-holder contention (`-32011`),
 * and same-holder mutation while locked.
 */
import { type DaemonClient, LockedError } from "@atomc/daemon-client";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { EMPTY_ELECTRICAL } from "./fixtures/ir.js";
import { DaemonHarness } from "./harness.js";

const HOLDER_ONE = "agent:one#1";
const HOLDER_TWO = "agent:two#1";

describe("ir.lock and ir.unlock", () => {
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

  it("blocks another holder from transacting while locked", async () => {
    const lock = await client.lock("/electrical", HOLDER_ONE, 60, "contract test");
    expect(typeof lock.expires_at).toBe("string");

    const error = await client
      .transact({
        path: "/electrical",
        base_rev: 1,
        holder: HOLDER_TWO,
        ops: [{ op: "add", path: "/nets/-", value: { id: "net:A", name: "A" } }],
      })
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(LockedError);
    if (error instanceof LockedError) {
      expect(error.code).toBe(-32011);
      expect(error.holder).toBe(HOLDER_ONE);
      expect(error.expires_at).toBe(lock.expires_at);
    }
    expect((await client.getIR("/")).rev).toBe(1);
  });

  it("permits the lock holder to transact", async () => {
    const tx = await client.transact({
      path: "/electrical",
      base_rev: 1,
      holder: HOLDER_ONE,
      ops: [{ op: "add", path: "/nets/-", value: { id: "net:B", name: "B" } }],
    });
    expect(tx.new_rev).toBe(2);
    expect((await client.getIR("/electrical")).rev).toBe(2);
  });

  it("refuses unlock by a different holder", async () => {
    const error = await client.unlock("/electrical", HOLDER_TWO).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(LockedError);
  });

  it("releases the lock for the holder and unblocks other writers", async () => {
    const released = await client.unlock("/electrical", HOLDER_ONE);
    expect(released.released).toBe(true);

    const tx = await client.transact({
      path: "/electrical",
      base_rev: 2,
      holder: HOLDER_TWO,
      ops: [{ op: "add", path: "/nets/-", value: { id: "net:C", name: "C" } }],
    });
    expect(tx.new_rev).toBe(3);
  });
});
