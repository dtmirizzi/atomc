/**
 * Generate (or check) the committed manifest JSON Schema.
 *
 * Usage:
 *   pnpm schema:generate     # write packages/plugin-sdk/schema/atomc-plugin.schema.json
 *   pnpm schema:check        # exit 1 if the committed file has drifted
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { generateManifestJsonSchema } from "../src/schema.js";

const here = dirname(fileURLToPath(import.meta.url));
const packageDir = resolve(here, "..");
const outputPath = resolve(packageDir, "../schema/atomc-plugin.schema.json");
const check = process.argv.includes("--check");

const generated = generateManifestJsonSchema();

if (check) {
  if (!existsSync(outputPath)) {
    console.error(`schema:check FAILED — ${outputPath} does not exist. Run: pnpm schema:generate`);
    process.exit(1);
  }
  const committed = readFileSync(outputPath, "utf8");
  if (committed !== generated) {
    console.error(`schema:check FAILED — ${outputPath} is out of date. Run: pnpm schema:generate`);
    process.exit(1);
  }
  console.log(`schema:check OK — ${outputPath}`);
} else {
  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, generated, "utf8");
  console.log(`schema:generate wrote ${outputPath}`);
}
