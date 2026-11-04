import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const HERE = dirname(fileURLToPath(import.meta.url));
const PKG = resolve(HERE, "..");
// WP-1.1 owns the canonical schema; it is only present once both work streams land.
const REAL_SCHEMA = resolve(PKG, "../schema/system_ir.schema.json");

describe("generated drift", () => {
  it.skipIf(!existsSync(REAL_SCHEMA))(
    "gen --check reports no drift against the canonical schema",
    () => {
      const tsx = resolve(PKG, "node_modules/.bin/tsx");
      expect(() =>
        execFileSync(tsx, ["scripts/gen.ts", "--check"], {
          cwd: PKG,
          stdio: "pipe",
        }),
      ).not.toThrow();
    },
  );
});
