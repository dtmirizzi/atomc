/**
 * Cross-language round-trips for the committed example IRs.
 *
 * Py -> TS: Python emits canonical JSON, TS `parseSystemIR()` accepts it and its
 * normalized shape matches parsing the source fixture directly.
 * TS -> Py: TS validates/serializes the fixture, Python `SystemIR.load()` accepts
 * it, and Python's `dump()` is accepted by TS again.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { parseSystemIR } from "@atomc/core-ir";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { Bridge, REPO_ROOT } from "./helpers/bridge.js";
import { pythonCanonical } from "./helpers/python.js";

const EXAMPLES = [
  "atomc-pad",
  "atomc-keeb",
  "atomc-drivetrain",
  "atomc-cannode",
] as const;

function examplePath(name: string): string {
  return resolve(REPO_ROOT, "examples", name, "system_ir.json");
}

describe("Python <-> TypeScript round-trips", () => {
  const bridge = new Bridge();

  beforeAll(async () => {
    // Warm the bridge so the first real assertion is not the one paying uv sync cost.
    await bridge.validate(JSON.parse(readFileSync(examplePath("atomc-pad"), "utf8")));
  });

  afterAll(() => bridge.close());

  for (const name of EXAMPLES) {
    describe(name, () => {
      it("accepts Python canonical JSON and matches the source shape", async () => {
        const canonical = await pythonCanonical(examplePath(name));
        const fromPython = parseSystemIR(JSON.parse(canonical));
        const fromSource = parseSystemIR(JSON.parse(readFileSync(examplePath(name), "utf8")));
        expect(fromPython).toEqual(fromSource);
        expect(fromPython.schema_version).toBe("0.1.0");
      });

      it("accepts TS-serialized IR in Python and Python dump back in TS", async () => {
        const source = JSON.parse(readFileSync(examplePath(name), "utf8")) as Record<
          string,
          unknown
        >;
        const parsed = parseSystemIR(source);
        const serialized = JSON.parse(JSON.stringify(parsed)) as Record<string, unknown>;

        const validated = await bridge.validate(serialized);
        expect(validated.canonical.endsWith("\n")).toBe(true);
        expect(parseSystemIR(JSON.parse(validated.canonical))).toEqual(parsed);
      });
    });
  }
});
