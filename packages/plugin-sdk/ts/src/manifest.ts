/**
 * `atomc-plugin.json` manifest schema (contract v0.1.0).
 *
 * This module is the authoritative source for the shared cross-language manifest
 * contract: `scripts/generate-schema.ts` emits `packages/plugin-sdk/schema/atomc-plugin.schema.json`
 * from {@link AtomcPluginManifestSchema}, and the Python SDK consumes that artifact.
 *
 * See `docs/architecture/contracts/plugin-manifest.md` (FROZEN for Phase 2).
 */
import { z } from "zod";
import { isSafeRelativePath } from "./glob.js";
import { isValidPointer, JSON_POINTER_PATTERN, parsePointer } from "./pointer.js";
import { isSemver, isSemverRange, SEMVER_PATTERN, SEMVER_RANGE_PATTERN } from "./semver.js";

/** Manifest contract version implemented by this SDK. */
export const MANIFEST_VERSION = "0.1.0" as const;

/** Specialist agent ids allowed as gate owners / tool callers. */
export const OWNER_AGENTS = ["ee-agent", "fw-agent", "mech-agent", "ops-agent"] as const;
export type OwnerAgent = (typeof OWNER_AGENTS)[number];

/** Gate severities (contract: `blocking|advisory`). */
export const GATE_SEVERITIES = ["blocking", "advisory"] as const;
export type GateSeverity = (typeof GATE_SEVERITIES)[number];

/** Top-level IR nodes a plugin may declare under `produces` (`/meta` is never writable). */
export const APPROVED_TOP_LEVEL_SCOPES = [
  "electrical",
  "layout",
  "keyboard",
  "firmware",
  "simulation",
  "mechanical",
  "sourcing",
  "fabrication",
  "orders",
  "gates",
  "provenance",
  "ext",
] as const;
export type ApprovedTopLevelScope = (typeof APPROVED_TOP_LEVEL_SCOPES)[number];

/**
 * Built-in `atomc` CLI commands from PLAN §3 (WP-3.1). Plugin `cli[].command`
 * values may not shadow these. Override via `ManifestValidationContext.reservedCliCommands`
 * if the built-in surface changes before this constant does.
 */
export const BUILTIN_CLI_COMMANDS = [
  "init",
  "build",
  "sim",
  "jig",
  "quote",
  "orders",
  "converge",
  "doctor",
  "daemon",
  "plugin",
] as const;

const KEBAB_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const DAG_ID_RE = /^[a-z0-9](?:[a-z0-9._:-]*[a-z0-9])?$/i;
const GATE_ID_RE = /^gate:[a-z0-9](?:[a-z0-9._:-]*[a-z0-9])?$/;
const NAME_RE = /^[a-z0-9]+(?:[_-][a-z0-9]+)*$/;
const PYTHON_ENTRY_RE = /^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_$][A-Za-z0-9_$]*$/;
const IDENTIFIER_RE = /^[A-Za-z_$][A-Za-z0-9_$]*$/;
const RELATIVE_PATH_RE = /^\.\/[A-Za-z0-9._/-]+$/;
const HANDLER_RE = new RegExp(
  "^(?:" +
    "[A-Za-z_$][A-Za-z0-9_$]*" +
    "|[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_$][A-Za-z0-9_$]*" +
    "|\\.\\/[A-Za-z0-9._/-]+(?:#[A-Za-z_$][A-Za-z0-9_$]*)?" +
    ")$",
);
const JSON_POINTER_RE = new RegExp(JSON_POINTER_PATTERN);
const SEMVER_RE = new RegExp(SEMVER_PATTERN);
const SEMVER_RANGE_RE = new RegExp(SEMVER_RANGE_PATTERN);
const PRODUCES_RE = new RegExp(
  `^/(?!meta(?:/|$))(?:${APPROVED_TOP_LEVEL_SCOPES.join("|")})(?:/|$)`,
);

/**
 * Validate a handler reference. Accepted forms (contract §Conventions):
 * - a bare implementation export name: `check_all_in_stock`
 * - a Python `module:attribute` reference: `atomc_plugin_sourcing:check_all_in_stock`
 * - a package-relative export path: `./handlers/bom.js` or `./handlers/bom.js#check`
 */
export function isValidHandlerReference(value: string): boolean {
  if (value.length === 0) return false;
  if (!HANDLER_RE.test(value)) return false;
  if (IDENTIFIER_RE.test(value)) return true;
  if (PYTHON_ENTRY_RE.test(value)) return true;
  const hashIndex = value.indexOf("#");
  const pathPart = hashIndex === -1 ? value : value.slice(0, hashIndex);
  const exportPart = hashIndex === -1 ? undefined : value.slice(hashIndex + 1);
  if (!pathPart.startsWith("./")) return false;
  if (exportPart !== undefined && !IDENTIFIER_RE.test(exportPart)) return false;
  return isSafeRelativePath(pathPart);
}

function topLevelScopeOf(pointer: string): string | undefined {
  return parsePointer(pointer)[0];
}

const nonEmptyString = z.string().min(1);
const irPointerSchema = z
  .string()
  .regex(JSON_POINTER_RE, { error: "must be a valid RFC 6901 JSON Pointer" })
  .refine(isValidPointer, { error: "must be a valid RFC 6901 JSON Pointer" });
const producesPointerSchema = z
  .string()
  .regex(PRODUCES_RE, { error: "must be an approved top-level IR scope (never /meta)" })
  .refine(isValidPointer, { error: "must be a valid RFC 6901 JSON Pointer" });
const handlerSchema = z
  .string()
  .regex(HANDLER_RE, { error: "must be a valid handler reference" })
  .refine(isValidHandlerReference, { error: "must be a valid handler reference" });
const relativePathSchema = z
  .string()
  .regex(RELATIVE_PATH_RE, { error: "must be a package-relative path (./…)" })
  .refine(isSafeRelativePath, { error: "must not escape the package root" });
const jsonSchemaSchema = z.union([z.boolean(), z.record(z.string(), z.unknown())]);

/** `watches[]` — a DAG node invalidated by IR pointer and/or file changes. */
export const AtomcWatchSchema = z.strictObject({
  id: z.string().regex(DAG_ID_RE, { error: "must be a valid DAG node id" }),
  ir: z.array(irPointerSchema),
  files: z.array(z.string()).default([]),
  debounce_ms: z.number().int().min(0).max(60000).default(250),
});
export type AtomcWatch = z.infer<typeof AtomcWatchSchema>;

/** `gates[]` — a verification gate and its implementation handler. */
export const AtomcGateSchema = z.strictObject({
  id: z.string().regex(GATE_ID_RE, { error: 'must start with "gate:"' }),
  severity: z.enum(GATE_SEVERITIES),
  owner_agent: z.enum(OWNER_AGENTS).nullable(),
  after: z.array(z.string().regex(DAG_ID_RE, { error: "must be a valid watch id" })),
  handler: handlerSchema,
});
export type AtomcGate = z.infer<typeof AtomcGateSchema>;

/** `tools[]` — an agent-callable tool and its implementation handler. */
export const AtomcToolSchema = z.strictObject({
  name: z.string().regex(NAME_RE, { error: "must be a valid tool name" }),
  description: nonEmptyString,
  input_schema: jsonSchemaSchema,
  agents: z.array(z.enum(OWNER_AGENTS)),
  mutates: z.boolean(),
  handler: handlerSchema,
});
export type AtomcTool = z.infer<typeof AtomcToolSchema>;

/** `cli[]` — a plugin-provided `atomc` subcommand. */
export const AtomcCliSchema = z.strictObject({
  command: z.string().regex(NAME_RE, { error: "must be a valid CLI command name" }),
  description: nonEmptyString,
  handler: handlerSchema,
});
export type AtomcCli = z.infer<typeof AtomcCliSchema>;

/** `ui[]` — a plugin-provided UI panel entry point. */
export const AtomcUiSchema = z.strictObject({
  panel: z.string().regex(NAME_RE, { error: "must be a valid panel id" }),
  title: nonEmptyString,
  entry: relativePathSchema,
});
export type AtomcUi = z.infer<typeof AtomcUiSchema>;

/** `runtime` — at least one of `python` or `ts` is required. */
export const AtomcRuntimeSchema = z
  .strictObject({
    python: z
      .string()
      .regex(PYTHON_ENTRY_RE, { error: "must be a module:attribute reference" })
      .optional(),
    ts: relativePathSchema.optional(),
  })
  .refine((runtime) => runtime.python !== undefined || runtime.ts !== undefined, {
    error: "at least one of `python` or `ts` is required",
  });
export type AtomcRuntime = z.infer<typeof AtomcRuntimeSchema>;

function addIssue(
  ctx: z.RefinementCtx,
  path: Array<string | number>,
  message: string,
  code: string,
): void {
  ctx.addIssue({ code: "custom", message, path, params: { rule: code } });
}

function findDuplicates(values: readonly string[]): string[] {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const value of values) {
    if (seen.has(value)) duplicates.add(value);
    seen.add(value);
  }
  return [...duplicates];
}

const BaseManifestSchema = z.strictObject({
  manifest_version: z.literal(MANIFEST_VERSION, {
    error: `must be "${MANIFEST_VERSION}"`,
  }),
  name: z
    .string()
    .regex(KEBAB_RE, { error: "must be kebab-case" })
    .refine((name) => !name.startsWith("plugin-"), {
      error: 'must not include the "plugin-" prefix',
    }),
  version: nonEmptyString
    .regex(SEMVER_RE, { error: "must be a valid SemVer version" })
    .refine(isSemver, { error: "must be a valid SemVer version" }),
  description: nonEmptyString,
  atomc: z
    .string()
    .regex(SEMVER_RANGE_RE, { error: "must be a valid SemVer range" })
    .refine(isSemverRange, { error: "must be a valid SemVer range" }),
  runtime: AtomcRuntimeSchema,
  watches: z.array(AtomcWatchSchema),
  produces: z.array(producesPointerSchema),
  gates: z.array(AtomcGateSchema),
  tools: z.array(AtomcToolSchema),
  cli: z.array(AtomcCliSchema),
  ui: z.array(AtomcUiSchema),
});

/**
 * The canonical manifest schema. Structural rules (types, enums, patterns, defaults,
 * `additionalProperties: false`) are represented directly; per-manifest cross-field
 * invariants are enforced with a refinement.
 *
 * Cross-*manifest* references (`after` ids from other plugins, global gate/panel/command
 * uniqueness) are checked by {@link validatePluginManifest} using a validation context.
 */
export const AtomcPluginManifestSchema = BaseManifestSchema.superRefine((manifest, ctx) => {
  const duplicateWatchIds = findDuplicates(manifest.watches.map((watch) => watch.id));
  for (const id of duplicateWatchIds) {
    addIssue(ctx, ["watches"], `duplicate watch id "${id}"`, "duplicate_watch_id");
  }

  const duplicateGateIds = findDuplicates(manifest.gates.map((gate) => gate.id));
  for (const id of duplicateGateIds) {
    addIssue(ctx, ["gates"], `duplicate gate id "${id}"`, "duplicate_gate_id");
  }

  const duplicateToolNames = findDuplicates(manifest.tools.map((tool) => tool.name));
  for (const name of duplicateToolNames) {
    addIssue(ctx, ["tools"], `duplicate tool name "${name}"`, "duplicate_tool_name");
  }

  const duplicateCommands = findDuplicates(manifest.cli.map((entry) => entry.command));
  for (const command of duplicateCommands) {
    addIssue(ctx, ["cli"], `duplicate CLI command "${command}"`, "duplicate_cli_command");
  }

  const duplicatePanels = findDuplicates(manifest.ui.map((entry) => entry.panel));
  for (const panel of duplicatePanels) {
    addIssue(ctx, ["ui"], `duplicate UI panel "${panel}"`, "duplicate_ui_panel");
  }

  const duplicateProduces = findDuplicates(manifest.produces);
  for (const pointer of duplicateProduces) {
    addIssue(
      ctx,
      ["produces"],
      `duplicate produces scope "${pointer}"`,
      "duplicate_produces_scope",
    );
  }

  manifest.produces.forEach((pointer, index) => {
    const scope = topLevelScopeOf(pointer);
    if (scope === undefined) {
      addIssue(
        ctx,
        ["produces", index],
        `"${pointer}" must target a top-level IR node`,
        "invalid_produces_scope",
      );
      return;
    }
    if (scope === "meta") {
      addIssue(ctx, ["produces", index], "writes to /meta are forbidden", "forbidden_meta_scope");
      return;
    }
    if (!APPROVED_TOP_LEVEL_SCOPES.includes(scope as ApprovedTopLevelScope)) {
      addIssue(
        ctx,
        ["produces", index],
        `"${scope}" is not an approved top-level IR node`,
        "unapproved_produces_scope",
      );
    }
  });

  const watchIds = new Set(manifest.watches.map((watch) => watch.id));
  manifest.gates.forEach((gate, gateIndex) => {
    gate.after.forEach((afterId, afterIndex) => {
      if (!watchIds.has(afterId)) {
        addIssue(
          ctx,
          ["gates", gateIndex, "after", afterIndex],
          `"${afterId}" does not reference a watch id declared by this manifest`,
          "unknown_watch_reference",
        );
      }
    });
  });

  manifest.tools.forEach((tool, index) => {
    if (tool.mutates && manifest.produces.length === 0) {
      addIssue(
        ctx,
        ["tools", index, "mutates"],
        `mutating tool "${tool.name}" requires at least one produces scope`,
        "mutating_tool_without_produces",
      );
    }
  });
});

/** Parsed, defaulted manifest as produced by {@link parsePluginManifest}. */
export type AtomcPluginManifest = z.infer<typeof AtomcPluginManifestSchema>;

/** Context for checks that reference *other* loaded manifests. */
export interface ManifestValidationContext {
  /** Watch ids declared by other loaded plugins (for `after` cross-references + global uniqueness). */
  readonly knownWatchIds?: Iterable<string>;
  /** Gate ids declared by other loaded plugins (global uniqueness). */
  readonly knownGateIds?: Iterable<string>;
  /** Additional reserved CLI command names (merged with {@link BUILTIN_CLI_COMMANDS}). */
  readonly reservedCliCommands?: Iterable<string>;
  /** UI panel ids declared by other loaded plugins (global uniqueness). */
  readonly knownUiPanels?: Iterable<string>;
}

/** Path-oriented manifest validation issue. */
export interface ManifestIssue {
  /** Dotted path into the manifest, e.g. `gates[0].after[1]`. */
  readonly path: string;
  readonly message: string;
  readonly code: string;
}

/** Discriminated result returned by {@link validatePluginManifest}. */
export type ManifestValidationResult =
  | { readonly success: true; readonly manifest: AtomcPluginManifest; readonly issues: [] }
  | { readonly success: false; readonly manifest?: undefined; readonly issues: ManifestIssue[] };

/** Error thrown by {@link parsePluginManifest} on validation failure. */
export class PluginManifestError extends Error {
  readonly issues: readonly ManifestIssue[];

  constructor(issues: readonly ManifestIssue[]) {
    super(
      `Invalid atomc plugin manifest (${issues.length} issue${issues.length === 1 ? "" : "s"}): ` +
        issues.map((issue) => `${issue.path}: ${issue.message}`).join("; "),
    );
    this.name = "PluginManifestError";
    this.issues = issues;
  }
}

function formatPath(path: readonly (string | number | symbol)[]): string {
  return path.reduce<string>((acc, segment) => {
    if (typeof segment === "number") return `${acc}[${segment}]`;
    return acc === "" ? String(segment) : `${acc}.${String(segment)}`;
  }, "");
}

/**
 * Validate an unknown value as an {@link AtomcPluginManifest} without throwing.
 *
 * Structural + per-manifest rules run via Zod; the optional `context` enables
 * cross-manifest checks (unique ids, `after` references to other plugins, reserved
 * CLI commands, global panel ids).
 */
export function validatePluginManifest(
  data: unknown,
  context: ManifestValidationContext = {},
): ManifestValidationResult {
  const parsed = AtomcPluginManifestSchema.safeParse(data);
  if (!parsed.success) {
    return {
      success: false,
      issues: parsed.error.issues.map((issue) => ({
        path: formatPath(issue.path),
        message: issue.message,
        code: String(issue.code),
      })),
    };
  }

  const manifest = parsed.data;
  const issues: ManifestIssue[] = [];
  const knownWatchIds = new Set(context.knownWatchIds ?? []);
  const knownGateIds = new Set(context.knownGateIds ?? []);
  const knownPanels = new Set(context.knownUiPanels ?? []);
  // NOTE: the frozen contract says plugin CLI commands may not shadow built-in
  // commands, but its own example declares `command: "quote"` (a built-in). The
  // built-in list is therefore exported as data and enforced only when the host
  // supplies it via `reservedCliCommands`; see WP-2.1 handoff for the ambiguity.
  const reservedCommands = new Set<string>(context.reservedCliCommands ?? []);

  manifest.watches.forEach((watch, index) => {
    if (knownWatchIds.has(watch.id)) {
      issues.push({
        path: `watches[${index}].id`,
        message: `watch id "${watch.id}" is already declared by another loaded manifest`,
        code: "duplicate_watch_id",
      });
    }
  });

  const allWatchIds = new Set([...knownWatchIds, ...manifest.watches.map((watch) => watch.id)]);
  manifest.gates.forEach((gate, gateIndex) => {
    if (knownGateIds.has(gate.id)) {
      issues.push({
        path: `gates[${gateIndex}].id`,
        message: `gate id "${gate.id}" is already declared by another loaded manifest`,
        code: "duplicate_gate_id",
      });
    }
    gate.after.forEach((afterId, afterIndex) => {
      if (!allWatchIds.has(afterId)) {
        issues.push({
          path: `gates[${gateIndex}].after[${afterIndex}]`,
          message: `"${afterId}" does not reference a declared watch id`,
          code: "unknown_watch_reference",
        });
      }
    });
  });

  manifest.cli.forEach((entry, index) => {
    if (reservedCommands.has(entry.command)) {
      issues.push({
        path: `cli[${index}].command`,
        message: `CLI command "${entry.command}" shadows a reserved atomc command`,
        code: "reserved_cli_command",
      });
    }
  });

  manifest.ui.forEach((entry, index) => {
    if (knownPanels.has(entry.panel)) {
      issues.push({
        path: `ui[${index}].panel`,
        message: `UI panel "${entry.panel}" is already declared by another loaded manifest`,
        code: "duplicate_ui_panel",
      });
    }
  });

  if (issues.length > 0) return { success: false, issues };
  return { success: true, manifest, issues: [] };
}

/**
 * Parse and validate a manifest, throwing {@link PluginManifestError} on failure.
 * Defaults declared in the contract (`files`, `debounce_ms`) are applied.
 */
export function parsePluginManifest(
  data: unknown,
  context: ManifestValidationContext = {},
): AtomcPluginManifest {
  const result = validatePluginManifest(data, context);
  if (!result.success) throw new PluginManifestError(result.issues);
  return result.manifest;
}

// Re-exported for consumers that want regex details without importing internals.
export const MANIFEST_NAME_PATTERN = KEBAB_RE;
