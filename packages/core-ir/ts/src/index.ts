/**
 * @atomc/core-ir — TypeScript types, zod schemas, and JSON-Patch helpers for
 * `system_ir.json`. Types and `SystemIRSchema` are generated from the frozen
 * JSON Schema produced by the Python package (`atomc-core-ir`).
 *
 * See `docs/architecture/contracts/ir-schema.md` §6.
 */
import type { ZodType } from "zod";
import type { SystemIR as GeneratedSystemIR } from "./generated/types.js";
import { SystemIRSchema as GeneratedSystemIRSchema } from "./generated/zod.js";

export type { SystemIR } from "./generated/types.js";
export type { JsonPatchOp } from "./lib/patch.js";
export { PatchBuilder, patch } from "./lib/patch.js";
export {
  escapePointerToken,
  getAt,
  joinPointer,
  parsePointer,
  unescapePointerToken,
} from "./lib/pointer.js";

/** Top-level zod validator for a complete `system_ir.json` document. */
export const SystemIRSchema: ZodType<GeneratedSystemIR> = GeneratedSystemIRSchema;

/** IR schema version implemented by this package. */
export const SCHEMA_VERSION = "0.1.0" as const;

/** Validate an unknown value as a `SystemIR`, throwing a `ZodError` on failure. */
export function parseSystemIR(json: unknown): GeneratedSystemIR {
  return SystemIRSchema.parse(json);
}
