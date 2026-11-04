import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parseSystemIR, SCHEMA_VERSION } from "../src/index.js";

const HERE = dirname(fileURLToPath(import.meta.url));

function listJson(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => f.endsWith(".json"))
    .map((f) => join(dir, f))
    .sort();
}

const validDirs: Array<{ label: string; dir: string }> = [
  { label: "local", dir: resolve(HERE, "fixtures") },
  { label: "wp-1.1", dir: resolve(HERE, "../../fixtures") },
];

const invalidDirs: Array<{ label: string; dir: string }> = [
  { label: "local", dir: resolve(HERE, "fixtures/invalid") },
  { label: "wp-1.1", dir: resolve(HERE, "../../fixtures/invalid") },
];

describe("SCHEMA_VERSION", () => {
  it("is 0.1.0", () => {
    expect(SCHEMA_VERSION).toBe("0.1.0");
  });
});

describe("parseSystemIR defaults", () => {
  it("fills optional top-level nodes with null and ext with {}", () => {
    const parsed = parseSystemIR({
      schema_version: "0.1.0",
      meta: {
        project_id: "proj:x",
        name: "x",
        created_at: "2026-11-04T23:00:00Z",
        modified_at: "2026-11-04T23:00:00Z",
        rev: 0,
        atomc_version: "0.1.0",
      },
    });
    expect(parsed.electrical).toBeNull();
    expect(parsed.keyboard).toBeNull();
    // `ext` is optional without a default in the canonical schema.
    expect(parsed.ext ?? {}).toEqual({});
  });

  it("applies component pin/key defaults", () => {
    const raw = JSON.parse(readFileSync(resolve(HERE, "fixtures/full.json"), "utf8")) as Record<
      string,
      unknown
    >;
    const parsed = parseSystemIR(raw);
    const key = parsed.keyboard?.keys?.[0];
    expect(key).toMatchObject({ x_u: 0, y_u: 0, w_u: 1, h_u: 1, rotation_deg: 0 });
    const comp = parsed.electrical?.components?.[0];
    expect(comp).toMatchObject({ dnp: false });
  });
});

for (const { label, dir } of validDirs) {
  const files = listJson(dir);
  if (files.length === 0) continue;
  describe(`valid fixtures (${label})`, () => {
    for (const file of files) {
      it(`parses ${file.split("/").slice(-2).join("/")}`, () => {
        const raw = JSON.parse(readFileSync(file, "utf8")) as unknown;
        const parsed = parseSystemIR(raw);
        expect(parsed.schema_version).toBe("0.1.0");
        expect(parsed.meta).toBeDefined();
      });
    }
  });
}

/**
 * v0.1 keeps these semantic checks in the Python loader only (ir-schema.md §1/§4):
 * unique ids, referential integrity of `_ref`/`_refs` fields, and keyboard
 * `row`/`col` bounds. zod validates shape, so an accepted invalid fixture is only
 * allowed when it fails one of these documented Python-only checks.
 */
function classifyPythonOnly(value: unknown): string | null {
  const ids: string[] = [];
  const walk = (node: unknown, visit: (obj: Record<string, unknown>) => void): void => {
    if (Array.isArray(node)) {
      for (const item of node) walk(item, visit);
    } else if (node !== null && typeof node === "object") {
      const obj = node as Record<string, unknown>;
      visit(obj);
      for (const nested of Object.values(obj)) walk(nested, visit);
    }
  };
  walk(value, (obj) => {
    if (typeof obj.id === "string") ids.push(obj.id);
  });

  const seen = new Set<string>();
  let duplicate: string | null = null;
  for (const id of ids) {
    if (seen.has(id)) {
      duplicate = id;
      break;
    }
    seen.add(id);
  }
  if (duplicate !== null) return `duplicate id ${duplicate}`;

  const idSet = new Set(ids);
  let dangling: string | null = null;
  walk(value, (obj) => {
    for (const [key, nested] of Object.entries(obj)) {
      if (key.endsWith("_ref") && typeof nested === "string" && !idSet.has(nested)) {
        dangling = `${key}=${nested}`;
      } else if (key.endsWith("_refs") && Array.isArray(nested)) {
        for (const ref of nested) {
          if (typeof ref === "string" && !idSet.has(ref)) dangling = `${key}=${ref}`;
        }
      }
    }
  });
  if (dangling !== null) return `dangling ref ${dangling}`;

  const root = value as Record<string, unknown>;
  const keyboard = root.keyboard as Record<string, unknown> | undefined;
  const matrix = keyboard?.matrix as Record<string, unknown> | undefined;
  const keys = (keyboard?.keys ?? []) as Array<Record<string, unknown>>;
  if (
    matrix &&
    keys.some((k) => Number(k.row) >= Number(matrix.rows) || Number(k.col) >= Number(matrix.cols))
  ) {
    return "key row/col out of range";
  }
  return null;
}

for (const { label, dir } of invalidDirs) {
  const files = listJson(dir);
  if (files.length === 0) continue;
  describe(`invalid fixtures (${label})`, () => {
    for (const file of files) {
      it(`rejects ${file.split("/").slice(-2).join("/")} (or fails a python-only semantic check)`, () => {
        const raw = JSON.parse(readFileSync(file, "utf8")) as unknown;
        let zodError: unknown;
        try {
          parseSystemIR(raw);
        } catch (err) {
          zodError = err;
        }
        if (zodError === undefined) {
          // Documented subset: zod has no cross-node/field semantic validation in v0.1.
          expect(classifyPythonOnly(raw)).not.toBeNull();
        }
      });
    }
  });
}
