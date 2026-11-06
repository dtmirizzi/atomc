/**
 * Fixture conformance: every valid fixture loads in both languages; every invalid
 * fixture is rejected by Python, and by TS unless it is one of the documented
 * Python-only semantic cases (unique ids, referential integrity, keyboard bounds).
 */
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { parseSystemIR } from "@atomc/core-ir";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { Bridge, BridgeFailure, REPO_ROOT } from "./helpers/bridge.js";

const VALID_DIRS = [
  resolve(REPO_ROOT, "packages/core-ir/fixtures"),
  resolve(REPO_ROOT, "examples/atomc-pad"),
  resolve(REPO_ROOT, "examples/atomc-keeb"),
  resolve(REPO_ROOT, "examples/atomc-drivetrain"),
];

const INVALID_DIR = resolve(REPO_ROOT, "packages/core-ir/fixtures/invalid");

const PYTHON_ONLY = new Set([
  "dangling_ref.json",
  "duplicate_id.json",
  "keyboard_row_out_of_range.json",
]);

function listJson(dir: string): string[] {
  return readdirSync(dir)
    .filter((file) => file.endsWith(".json"))
    .map((file) => resolve(dir, file))
    .sort();
}

function read(path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
}

/**
 * Mirrors the documented v0.1 Python-only semantic checks. Returns a category
 * name for a value that zod accepts but Python rejects, else `null`.
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
  for (const id of ids) {
    if (seen.has(id)) return `duplicate id ${id}`;
    seen.add(id);
  }

  const idSet = new Set(ids);
  let dangling = false;
  walk(value, (obj) => {
    for (const [key, nested] of Object.entries(obj)) {
      if (key.endsWith("_ref") && typeof nested === "string" && !idSet.has(nested)) dangling = true;
      if (key.endsWith("_refs") && Array.isArray(nested)) {
        for (const ref of nested) if (typeof ref === "string" && !idSet.has(ref)) dangling = true;
      }
    }
  });
  if (dangling) return "dangling ref";

  const root = value as Record<string, unknown>;
  const keyboard = root.keyboard as Record<string, unknown> | undefined;
  const matrix = keyboard?.matrix as Record<string, unknown> | undefined;
  const keys = (keyboard?.keys ?? []) as Array<Record<string, unknown>>;
  if (
    matrix &&
    keys.some((k) => Number(k.row) >= Number(matrix.rows) || Number(k.col) >= Number(matrix.cols))
  ) {
    return "keyboard row/col out of range";
  }
  return null;
}

describe("valid fixtures", () => {
  const bridge = new Bridge();
  beforeAll(async () => {
    await bridge.validate(read(listJson(VALID_DIRS[0] as string)[0] as string));
  });
  afterAll(() => bridge.close());

  const files = VALID_DIRS.flatMap((dir) => listJson(dir).map((path) => ({ dir, path })));
  for (const { path } of files) {
    const label = path.slice(REPO_ROOT.length + 1);
    it(`loads ${label} in TS and Python`, async () => {
      const raw = read(path);
      const parsed = parseSystemIR(raw);
      expect(parsed.schema_version).toBe("0.1.0");
      const res = await bridge.validate(raw);
      expect(res.ir).toBeDefined();
    });
  }
});

describe("invalid fixtures", () => {
  const bridge = new Bridge();
  beforeAll(async () => {
    await bridge.validate(read(listJson(VALID_DIRS[0] as string)[0] as string));
  });
  afterAll(() => bridge.close());

  for (const path of listJson(INVALID_DIR)) {
    const file = path.split("/").at(-1) as string;

    it(`rejects ${file} in Python`, async () => {
      let failure: BridgeFailure | undefined;
      try {
        await bridge.validate(read(path));
      } catch (err) {
        failure = err as BridgeFailure;
      }
      expect(failure).toBeInstanceOf(BridgeFailure);
      expect(["ref_integrity", "validation"]).toContain(failure?.type);
    });

    it(`handles ${file} in TS (structural reject or documented Python-only case)`, () => {
      const raw = read(path);
      let tsError: unknown;
      try {
        parseSystemIR(raw);
      } catch (err) {
        tsError = err;
      }
      if (tsError === undefined) {
        const category = classifyPythonOnly(raw);
        expect(category).not.toBeNull();
        expect(PYTHON_ONLY.has(file)).toBe(true);
      } else {
        expect(tsError).toBeInstanceOf(Error);
      }
    });
  }
});
