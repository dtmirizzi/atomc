import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

/** Load a JSON fixture from `test/fixtures/<...segments>`. */
export function loadFixture(...segments: string[]): unknown {
  return JSON.parse(readFileSync(resolve(here, "fixtures", ...segments), "utf8"));
}

/** Load a text fixture from `test/fixtures/<...segments>`. */
export function loadFixtureText(...segments: string[]): string {
  return readFileSync(resolve(here, "fixtures", ...segments), "utf8");
}

/** Shallow-clone a fixture object as a mutable record for inline mutation. */
export function mutableFixture(...segments: string[]): Record<string, unknown> {
  return structuredClone(loadFixture(...segments)) as Record<string, unknown>;
}
