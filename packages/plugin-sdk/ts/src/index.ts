/**
 * `@atomc/plugin-sdk` — TypeScript plugin SDK for atomc.
 *
 * Public surface:
 * - manifest schema + validation ({@link AtomcPluginManifestSchema}, {@link parsePluginManifest})
 * - plugin registration ({@link defineAtomcPlugin}) and host context types
 * - watch / JSON-pointer matching
 * - conformance kit
 *
 * @packageDocumentation
 */

export {
  assertAgentAccess,
  assertConformance,
  type ConformanceIssue,
  type ConformanceReport,
  conformance,
  findTool,
  isWithinProduces,
  PluginConformanceError,
  validateToolInput,
} from "./conformance.js";
export {
  isSafeRelativePath,
  matchesAnyGlob,
  matchesGlob,
  normalizeProjectPath,
} from "./glob.js";
export {
  APPROVED_TOP_LEVEL_SCOPES,
  type ApprovedTopLevelScope,
  type AtomcCli,
  AtomcCliSchema,
  type AtomcGate,
  AtomcGateSchema,
  type AtomcPluginManifest,
  AtomcPluginManifestSchema,
  type AtomcRuntime,
  AtomcRuntimeSchema,
  type AtomcTool,
  AtomcToolSchema,
  type AtomcUi,
  AtomcUiSchema,
  type AtomcWatch,
  AtomcWatchSchema,
  BUILTIN_CLI_COMMANDS,
  GATE_SEVERITIES,
  type GateSeverity,
  MANIFEST_NAME_PATTERN,
  MANIFEST_VERSION,
  type ManifestIssue,
  type ManifestValidationContext,
  type ManifestValidationResult,
  OWNER_AGENTS,
  type OwnerAgent,
  PluginManifestError,
  parsePluginManifest,
  validatePluginManifest,
} from "./manifest.js";
export {
  type AtomcPlugin,
  type AtomcPluginOptions,
  type CliHandler,
  defineAtomcPlugin,
  type GateEvidence,
  type GateHandler,
  type GateResult,
  GateResultSchema,
  type GateSuggestion,
  type IrTransactionOp,
  type IrTransactionResult,
  type PluginArtifacts,
  type PluginCache,
  type PluginContext,
  type PluginEvents,
  type PluginIr,
  type PluginLogger,
  PluginRegistrationError,
  type PluginSetup,
  type PluginSetupContext,
  type ToolHandler,
} from "./plugin.js";

export {
  escapePointerToken,
  isPointerDescendant,
  isValidPointer,
  JsonPointerError,
  joinPointer,
  parsePointer,
  pointerMatchesPattern,
  pointersEqual,
  unescapePointerToken,
} from "./pointer.js";
// Re-exported for scripts/tests that regenerate the committed JSON Schema artifact.
export { generateManifestJsonSchema, MANIFEST_SCHEMA_ID } from "./schema.js";

export { isSemver, isSemverRange } from "./semver.js";
export {
  type ChangeSet,
  normalizeWatchPath,
  watchMatches,
  watchMatchesFiles,
  watchMatchesIr,
} from "./watches.js";
