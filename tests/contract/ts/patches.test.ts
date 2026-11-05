/**
 * RFC 6902 patch transactions across the language boundary.
 *
 * TS builds the ops with `patch()` from `@atomc/core-ir`; Python applies them via
 * `apply_patch()` using the owning top-level node's `_meta.rev` as `base_rev`.
 * Both examples share `/electrical/assertions`, so the same patches apply to each.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { patch } from "@atomc/core-ir";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { Bridge, BridgeFailure, REPO_ROOT } from "./helpers/bridge.js";

const EXAMPLES = ["atomc-pad", "atomc-keeb"] as const;

interface ElectricalNode {
  _meta: { rev: number; lock?: Record<string, unknown> | null };
  assertions: Array<{ id: string; expr: string; status: string; message?: string }>;
}

function examplePath(name: string): string {
  return resolve(REPO_ROOT, "examples", name, "system_ir.json");
}

function loadExample(name: string): Record<string, unknown> {
  return JSON.parse(readFileSync(examplePath(name), "utf8")) as Record<string, unknown>;
}

function electrical(ir: Record<string, unknown>): ElectricalNode {
  return ir.electrical as ElectricalNode;
}

describe("patch transactions (Python apply_patch)", () => {
  const bridge = new Bridge();
  const originals = new Map<string, Record<string, unknown>>();

  beforeAll(async () => {
    for (const name of EXAMPLES) {
      const ir = loadExample(name);
      expect(Array.isArray(electrical(ir).assertions)).toBe(true);
      expect(electrical(ir).assertions.length).toBeGreaterThan(0);
      originals.set(name, ir);
      await bridge.validate(ir);
    }
  });

  afterAll(() => bridge.close());

  for (const name of EXAMPLES) {
    describe(name, () => {
      it("replace: updates an existing assertion status", async () => {
        const ir = originals.get(name) as Record<string, unknown>;
        const node = electrical(ir);
        const ops = patch().replace("/assertions/0/status", "fail").build();

        const res = await bridge.patch({
          ir,
          path: "/electrical",
          base_rev: node._meta.rev,
          ops,
          holder: "agent:contract",
        });

        const updated = res.ir.electrical as ElectricalNode;
        expect(updated.assertions[0]?.status).toBe("fail");
        expect(res.new_rev).toBe((ir.meta as { rev: number }).rev + 1);
        expect(updated._meta.rev).toBe(res.new_rev);
        expect(res.changed_paths).toEqual(["/electrical/assertions/0/status"]);
      });

      it("add: appends a valid assertion", async () => {
        const ir = originals.get(name) as Record<string, unknown>;
        const node = electrical(ir);
        const before = node.assertions.length;
        const added = { id: "assert:contract_probe", expr: "1 == 1", status: "unknown" };
        const ops = patch().add("/assertions/-", added).build();

        const res = await bridge.patch({
          ir,
          path: "/electrical",
          base_rev: node._meta.rev,
          ops,
          holder: "agent:contract",
        });

        const updated = res.ir.electrical as ElectricalNode;
        expect(updated.assertions).toHaveLength(before + 1);
        expect(updated.assertions.at(-1)).toMatchObject(added);
      });

      it("remove: deletes the first assertion", async () => {
        const ir = originals.get(name) as Record<string, unknown>;
        const node = electrical(ir);
        const before = node.assertions.length;
        const secondId = node.assertions[1]?.id;
        const ops = patch().remove("/assertions/0").build();

        const res = await bridge.patch({
          ir,
          path: "/electrical",
          base_rev: node._meta.rev,
          ops,
          holder: "agent:contract",
        });

        const updated = res.ir.electrical as ElectricalNode;
        expect(updated.assertions).toHaveLength(before - 1);
        expect(updated.assertions[0]?.id).toBe(secondId);
      });

      it("invalid patch rolls back (no revision change, no state leak)", async () => {
        const ir = originals.get(name) as Record<string, unknown>;
        const node = electrical(ir);
        const ops = patch().replace("/assertions/0/status", "bogus").build();

        await expect(
          bridge.patch({
            ir,
            path: "/electrical",
            base_rev: node._meta.rev,
            ops,
            holder: "agent:contract",
          }),
        ).rejects.toMatchObject({ type: "validation" });

        // The pure transaction left the document untouched: a valid patch based on
        // the same rev still succeeds and reports rev + 1.
        const goodOps = patch().replace("/assertions/0/status", "fail").build();
        const res = await bridge.patch({
          ir,
          path: "/electrical",
          base_rev: node._meta.rev,
          ops: goodOps,
          holder: "agent:contract",
        });
        expect(res.new_rev).toBe((ir.meta as { rev: number }).rev + 1);
      });

      it("rejects a stale base_rev with a structured conflict", async () => {
        const ir = originals.get(name) as Record<string, unknown>;
        const node = electrical(ir);
        const ops = patch().replace("/assertions/0/status", "fail").build();

        let failure: BridgeFailure | undefined;
        try {
          await bridge.patch({
            ir,
            path: "/electrical",
            base_rev: Math.max(0, node._meta.rev - 1),
            ops,
            holder: "agent:contract",
          });
        } catch (err) {
          failure = err as BridgeFailure;
        }
        expect(failure).toBeInstanceOf(BridgeFailure);
        expect(failure?.type).toBe("conflict");
        expect(failure?.message).toContain("revision conflict");
      });

      it("rejects a patch while another holder owns an unexpired lock", async () => {
        const ir = loadExample(name);
        const node = electrical(ir);
        node._meta.lock = {
          holder: "agent:other",
          acquired_at: "2026-11-04T00:00:00Z",
          expires_at: "2999-01-01T00:00:00Z",
          reason: "held for contract test",
        };
        const ops = patch().replace("/assertions/0/status", "fail").build();

        let failure: BridgeFailure | undefined;
        try {
          await bridge.patch({
            ir,
            path: "/electrical",
            base_rev: node._meta.rev,
            ops,
            holder: "agent:contract",
          });
        } catch (err) {
          failure = err as BridgeFailure;
        }
        expect(failure).toBeInstanceOf(BridgeFailure);
        expect(failure?.type).toBe("locked");
        expect(failure?.message).toContain("agent:other");
      });
    });
  }
});
