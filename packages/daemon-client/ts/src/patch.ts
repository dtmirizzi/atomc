/**
 * Reconcile the absolute pointers emitted by `@atomc/core-ir`'s
 * `patch(base)` builder with the daemon RPC contract, which requires
 * `ir.transact.ops` to be **relative to the supplied `path`**.
 *
 * See `docs/architecture/contracts/ir-schema.md` §2 and
 * `docs/architecture/contracts/rpc.md`. WP-1.3 flagged this mismatch: the TS
 * `patch(base)` helper emits absolute pointers while Python `apply_patch`
 * resolves ops relative to `path`.
 */
import type { JsonPatchOp } from "@atomc/core-ir";

/** Raised when an op targets a top-level node outside the transaction base. */
export class PatchPathError extends Error {
  readonly path: string;
  readonly base: string;

  constructor(path: string, base: string) {
    super(`JSON Patch path "${path}" is outside transaction base "${base}"`);
    this.name = "PatchPathError";
    this.path = path;
    this.base = base;
  }
}

/** Top-level IR nodes (ir-schema.md §3). Used to detect absolute sibling pointers. */
const TOP_LEVEL_NODES = new Set([
  "meta",
  "electrical",
  "layout",
  "keyboard",
  "firmware",
  "simulation",
  "mechanical",
  "sourcing",
  "fabrication",
  "orders",
  "gates",
  "provenance",
  "ext",
]);

/** Normalize a base pointer: `/` and `""` both mean the document root. */
function normalizeBase(base: string): string {
  if (base === "" || base === "/") return "";
  if (!base.startsWith("/")) {
    throw new PatchPathError(base, base);
  }
  // Drop a single trailing slash (`/electrical/` -> `/electrical`).
  return base.endsWith("/") ? base.slice(0, -1) : base;
}

function firstToken(pointer: string): string | undefined {
  if (!pointer.startsWith("/")) return undefined;
  const end = pointer.indexOf("/", 1);
  const token = end === -1 ? pointer.slice(1) : pointer.slice(1, end);
  return token.replace(/~1/g, "/").replace(/~0/g, "~");
}

/**
 * Rewrite one pointer from absolute (or already-relative) to relative-to-base.
 *
 * - `base === ""` (root): pointers are already relative, returned unchanged.
 * - Pointer inside `base`: the base prefix is stripped (boundary-aware).
 * - Pointer whose first token is a top-level IR node but not inside `base`:
 *   treated as an absolute pointer for a sibling subtree and rejected.
 * - Any other pointer is assumed to already be relative and is kept.
 */
function relativize(base: string, pointer: string): string {
  if (pointer === "") return "";
  if (!pointer.startsWith("/")) {
    throw new PatchPathError(pointer, base);
  }
  if (base === "") return pointer;
  if (pointer === base) return "";
  if (pointer.startsWith(`${base}/`)) return pointer.slice(base.length);

  const token = firstToken(pointer);
  if (token !== undefined && TOP_LEVEL_NODES.has(token)) {
    throw new PatchPathError(pointer, base);
  }
  return pointer;
}

/**
 * Convert an op list to be relative to `base` (a JSON Pointer to a top-level node
 * or descendant). Absolute pointers that begin with `base` are stripped; pointers
 * that are already relative pass through; pointers targeting a different
 * top-level node are rejected with `PatchPathError`.
 */
export function toRelativePatch(base: string, ops: readonly JsonPatchOp[]): JsonPatchOp[] {
  const normalized = normalizeBase(base);
  return ops.map((op): JsonPatchOp => {
    const path = relativize(normalized, op.path);
    switch (op.op) {
      case "add":
        return { op: "add", path, value: op.value };
      case "remove":
        return { op: "remove", path };
      case "replace":
        return { op: "replace", path, value: op.value };
      case "test":
        return { op: "test", path, value: op.value };
      case "move":
        return { op: "move", from: relativize(normalized, op.from), path };
      case "copy":
        return { op: "copy", from: relativize(normalized, op.from), path };
      default:
        throw new Error(`Unsupported JSON Patch op: ${(op as { op: string }).op}`);
    }
  });
}
