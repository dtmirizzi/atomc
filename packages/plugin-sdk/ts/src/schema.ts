/**
 * Deterministic JSON Schema generation for the manifest contract.
 *
 * The JSON Schema is the cross-language data contract: the Python SDK validates the
 * same artifact instead of maintaining an independent shape. Cross-field invariants
 * that JSON Schema cannot express (array-item uniqueness, `after` reference integrity)
 * are enforced by the SDK validators in each language.
 */
import { z } from "zod";
import { AtomcPluginManifestSchema, MANIFEST_VERSION } from "./manifest.js";

/** Stable `$id` for the committed manifest schema artifact. */
export const MANIFEST_SCHEMA_ID = "https://atomc.dev/schemas/atomc-plugin.schema.json";

const SCHEMA_DESCRIPTION =
  `atomc-plugin.json manifest contract v${MANIFEST_VERSION}. Generated from ` +
  "@atomc/plugin-sdk's zod schema; do not edit by hand.";

/**
 * Generate the manifest JSON Schema as a pretty-printed string.
 *
 * Uses `io: "input"` so fields carrying contract defaults (`files`, `debounce_ms`)
 * remain optional in the schema, matching the raw JSON that plugins author.
 */
export function generateManifestJsonSchema(): string {
  const generated = z.toJSONSchema(AtomcPluginManifestSchema, {
    target: "draft-2020-12",
    io: "input",
    unrepresentable: "any",
  }) as Record<string, unknown>;

  const rest = { ...generated };
  delete rest.$schema;
  delete rest.$id;

  const document = {
    $schema: "https://json-schema.org/draft/2020-12/schema",
    $id: MANIFEST_SCHEMA_ID,
    title: "atomc-plugin.json",
    description: SCHEMA_DESCRIPTION,
    "x-manifest-version": MANIFEST_VERSION,
    ...rest,
  };

  return `${JSON.stringify(document, null, 2)}\n`;
}
