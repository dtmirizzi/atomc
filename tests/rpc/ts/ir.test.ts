/**
 * `ir.get` / `ir.transact` contract: revisions, subtree reads, conflicts, validation
 * failures and referential-integrity failures against the real daemon.
 */
import {
  ConflictError,
  type DaemonClient,
  RefIntegrityError,
  ValidationError,
} from "@atomc/daemon-client";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { DANGLING_COMPONENT, EMPTY_ELECTRICAL } from "./fixtures/ir.js";
import { DaemonHarness } from "./harness.js";

describe("ir.get and ir.transact", () => {
  let harness: DaemonHarness;
  let client: DaemonClient;

  beforeAll(async () => {
    harness = await DaemonHarness.start();
    client = await harness.connect();
  }, 300_000);

  afterAll(async () => {
    await harness.stop();
  });

  it("reads the root document at rev 0 from the core-ir minimal fixture", async () => {
    const root = await client.getIR("/");
    expect(root.rev).toBe(0);
    const value = root.value as { meta: { project_id: string; name: string } };
    expect(value.meta.project_id).toBe("proj:minimal");
    expect(value.meta.name).toBe("minimal");
  });

  it("creates /electrical and bumps the document and owning-node revisions", async () => {
    const tx = await client.transact({
      path: "/electrical",
      base_rev: 0,
      ops: [{ op: "add", path: "", value: EMPTY_ELECTRICAL }],
    });
    expect(tx.new_rev).toBe(1);
    expect(tx.changed_paths).toEqual(["/electrical"]);

    expect((await client.getIR("/")).rev).toBe(1);
    const electrical = await client.getIR("/electrical");
    expect(electrical.rev).toBe(1);
    const components = await client.getIR("/electrical/components");
    expect(components.rev).toBe(1);
    expect(components.value).toEqual([]);
  });

  it("rejects a stale base revision with ConflictError and leaves data unchanged", async () => {
    const before = await client.getIR("/");
    const error = await client
      .transact({
        path: "/electrical",
        base_rev: 0,
        ops: [{ op: "remove", path: "/source" }],
      })
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ConflictError);
    if (error instanceof ConflictError) {
      expect(error.code).toBe(-32010);
      expect(error.current_rev).toBe(1);
      expect(error.expected_rev).toBe(0);
    }
    expect((await client.getIR("/")).rev).toBe(before.rev);
    expect((await client.getIR("/electrical")).rev).toBe(1);
  });

  it("rejects an invalid patch with ValidationError and leaves data unchanged", async () => {
    const error = await client
      .transact({
        path: "/electrical",
        base_rev: 1,
        ops: [{ op: "replace", path: "/source", value: { kind: "not-a-source" } }],
      })
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ValidationError);
    if (error instanceof ValidationError) {
      expect(error.code).toBe(-32012);
      expect(error.errors.length).toBeGreaterThan(0);
    }
    const electrical = (await client.getIR("/electrical")).value as {
      source: { kind: string };
    };
    expect(electrical.source.kind).toBe("atopile");
    expect((await client.getIR("/")).rev).toBe(1);
  });

  it("rejects a dangling reference with RefIntegrityError and leaves data unchanged", async () => {
    const error = await client
      .transact({
        path: "/electrical",
        base_rev: 1,
        ops: [{ op: "add", path: "/components/-", value: DANGLING_COMPONENT }],
      })
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(RefIntegrityError);
    if (error instanceof RefIntegrityError) {
      expect(error.code).toBe(-32013);
    }
    const electrical = (await client.getIR("/electrical")).value as {
      components: unknown[];
    };
    expect(electrical.components).toEqual([]);
    expect((await client.getIR("/")).rev).toBe(1);
  });

  it("applies a subsequent valid patch relative to the node path", async () => {
    const net = { id: "net:3V3", name: "3V3", class: "power" };
    const tx = await client.transact({
      path: "/electrical",
      base_rev: 1,
      ops: [{ op: "add", path: "/nets/-", value: net }],
    });
    expect(tx.new_rev).toBe(2);
    expect(tx.changed_paths).toEqual(["/electrical/nets/-"]);
    const nets = (await client.getIR("/electrical/nets")).value as Array<{ id: string }>;
    expect(nets.map((entry) => entry.id)).toEqual(["net:3V3"]);
    expect((await client.getIR("/electrical")).rev).toBe(2);
  });
});
