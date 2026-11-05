import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { z } from "zod";
import { validatePluginManifest } from "../src/manifest.js";
import { generateManifestJsonSchema, MANIFEST_SCHEMA_ID } from "../src/schema.js";
import { loadFixture } from "./helpers.js";

const here = dirname(fileURLToPath(import.meta.url));
const SCHEMA_PATH = resolve(here, "../../schema/atomc-plugin.schema.json");

/** Fixtures the structural JSON Schema must also reject. */
const STRUCTURAL_INVALID = [
  "unknown-key.json",
  "missing-runtime.json",
  "forbidden-meta-scope.json",
  "ui-escape.json",
  "bad-name.json",
  "bad-handler.json",
];

/**
 * Cross-field fixtures JSON Schema cannot express (array-item uniqueness and
 * `after` reference integrity). The zod validator must still reject them.
 */
const SEMANTIC_INVALID = [
  "bad-after.json",
  "duplicate-watch-id.json",
  "mutating-tool-no-produces.json",
];

function committedSchemaText(): string {
  return readFileSync(SCHEMA_PATH, "utf8");
}

describe("generated schema artifact", () => {
  it("is byte-identical to a fresh generation", () => {
    expect(committedSchemaText()).toBe(generateManifestJsonSchema());
  });

  it("is deterministic across runs", () => {
    expect(generateManifestJsonSchema()).toBe(generateManifestJsonSchema());
  });

  it("carries the required metadata", () => {
    const doc = JSON.parse(committedSchemaText()) as Record<string, unknown>;
    expect(doc.$id).toBe(MANIFEST_SCHEMA_ID);
    expect(doc.title).toBe("atomc-plugin.json");
    expect(doc["$schema"]).toBe("https://json-schema.org/draft/2020-12/schema");
    expect(doc["x-manifest-version"]).toBe("0.1.0");
    expect((doc.properties as Record<string, { const?: string }>).manifest_version?.const).toBe(
      "0.1.0",
    );
  });

  it("rejects unknown top-level keys and declares defaults", () => {
    const doc = JSON.parse(committedSchemaText()) as {
      additionalProperties: boolean;
      properties: Record<
        string,
        { items?: { properties?: Record<string, { default?: unknown }> } }
      >;
    };
    expect(doc.additionalProperties).toBe(false);
    const watch = doc.properties.watches?.items?.properties;
    expect(watch?.files?.default).toEqual([]);
    expect(watch?.debounce_ms?.default).toBe(250);
  });
});

describe("JSON Schema / zod parity", () => {
  const compiled = z.fromJSONSchema(JSON.parse(committedSchemaText()) as never);

  it("accepts the same valid fixtures", () => {
    for (const fixture of ["full.json", "minimal.json"]) {
      const data = loadFixture("valid", fixture);
      expect(compiled.safeParse(data).success).toBe(true);
      expect(validatePluginManifest(data).success).toBe(true);
    }
  });

  it("rejects the same structurally invalid fixtures", () => {
    for (const fixture of STRUCTURAL_INVALID) {
      const data = loadFixture("invalid", fixture);
      expect(compiled.safeParse(data).success, `schema should reject ${fixture}`).toBe(false);
      expect(validatePluginManifest(data).success, `zod should reject ${fixture}`).toBe(false);
    }
  });

  it("zod enforces cross-field rules that JSON Schema cannot express", () => {
    for (const fixture of SEMANTIC_INVALID) {
      const data = loadFixture("invalid", fixture);
      expect(validatePluginManifest(data).success, `zod should reject ${fixture}`).toBe(false);
    }
  });
});
