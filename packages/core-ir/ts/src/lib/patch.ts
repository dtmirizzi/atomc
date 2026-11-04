/** RFC 6902 JSON Patch builder. */

export type JsonPatchOp =
  | { op: "add"; path: string; value: unknown }
  | { op: "remove"; path: string }
  | { op: "replace"; path: string; value: unknown }
  | { op: "move"; from: string; path: string }
  | { op: "copy"; from: string; path: string }
  | { op: "test"; path: string; value: unknown };

/**
 * Resolve a relative JSON Pointer against a base pointer. `path` is treated as an
 * RFC 6901 pointer fragment (any `~`/`/` escaping is the caller's responsibility),
 * so `patch("/sourcing").add("bom/-", line)` yields `/sourcing/bom/-`.
 */
function resolvePath(base: string, path: string): string {
  if (path === "") return base;
  return `${base}${path.startsWith("/") ? path : `/${path}`}`;
}

/**
 * Immutable-ish builder for JSON Patch op lists. Each method appends an op and
 * returns `this` for chaining; `build()` returns a shallow copy.
 *
 * ```ts
 * patch("/sourcing").add("/bom/-", line).replace("/build_qty", 5).build();
 * ```
 */
export class PatchBuilder {
  readonly #base: string;
  readonly #ops: JsonPatchOp[];

  constructor(base = "", ops: JsonPatchOp[] = []) {
    this.#base = base;
    this.#ops = ops;
  }

  add(path: string, value: unknown): this {
    this.#ops.push({ op: "add", path: resolvePath(this.#base, path), value });
    return this;
  }

  remove(path: string): this {
    this.#ops.push({ op: "remove", path: resolvePath(this.#base, path) });
    return this;
  }

  replace(path: string, value: unknown): this {
    this.#ops.push({ op: "replace", path: resolvePath(this.#base, path), value });
    return this;
  }

  move(from: string, path: string): this {
    this.#ops.push({
      op: "move",
      from: resolvePath(this.#base, from),
      path: resolvePath(this.#base, path),
    });
    return this;
  }

  copy(from: string, path: string): this {
    this.#ops.push({
      op: "copy",
      from: resolvePath(this.#base, from),
      path: resolvePath(this.#base, path),
    });
    return this;
  }

  test(path: string, value: unknown): this {
    this.#ops.push({ op: "test", path: resolvePath(this.#base, path), value });
    return this;
  }

  build(): JsonPatchOp[] {
    return this.#ops.map((op) => ({ ...op }));
  }
}

/** Start a patch builder scoped to `path` (a top-level node or descendant pointer). */
export function patch(path = ""): PatchBuilder {
  return new PatchBuilder(path);
}
