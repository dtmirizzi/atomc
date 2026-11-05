/**
 * Manifest + implementation conformance checks, reusable by built-in plugins, third
 * parties, and CI.
 */
import { z } from "zod";
import {
  type AtomcPluginManifest,
  type AtomcTool,
  type ManifestIssue,
  type ManifestValidationContext,
  validatePluginManifest,
} from "./manifest.js";
import type { AtomcPlugin } from "./plugin.js";
import { isValidPointer, parsePointer } from "./pointer.js";

/** A single conformance finding. */
export interface ConformanceIssue {
  readonly path: string;
  readonly message: string;
  readonly code: string;
}

/** Result of a conformance check. */
export interface ConformanceReport {
  readonly ok: boolean;
  readonly issues: readonly ConformanceIssue[];
}

/** Error raised by conformance assertions. */
export class PluginConformanceError extends Error {
  readonly issues: readonly ConformanceIssue[];

  constructor(issues: readonly ConformanceIssue[]) {
    super(
      `Plugin conformance failed (${issues.length} issue${issues.length === 1 ? "" : "s"}): ` +
        issues.map((issue) => `${issue.path}: ${issue.message}`).join("; "),
    );
    this.name = "PluginConformanceError";
    this.issues = issues;
  }
}

function fromManifestIssues(issues: readonly ManifestIssue[]): ConformanceIssue[] {
  return issues.map((issue) => ({ path: issue.path, message: issue.message, code: issue.code }));
}

/** Find a declared tool by name, or `undefined`. */
export function findTool(manifest: AtomcPluginManifest, toolName: string): AtomcTool | undefined {
  return manifest.tools.find((tool) => tool.name === toolName);
}

/**
 * Validate `input` against a tool's declared `input_schema`.
 * The JSON Schema is compiled with zod's `fromJSONSchema`; unsupported or invalid
 * schemas are reported as `invalid_input_schema`.
 */
export function validateToolInput(
  manifest: AtomcPluginManifest,
  toolName: string,
  input: unknown,
): ConformanceReport {
  const tool = findTool(manifest, toolName);
  if (!tool) {
    return {
      ok: false,
      issues: [
        { path: `tools.${toolName}`, message: `unknown tool "${toolName}"`, code: "unknown_tool" },
      ],
    };
  }
  let schema: z.ZodType;
  try {
    schema = z.fromJSONSchema(tool.input_schema as never);
  } catch (error) {
    return {
      ok: false,
      issues: [
        {
          path: `tools.${toolName}.input_schema`,
          message: `invalid JSON Schema: ${error instanceof Error ? error.message : String(error)}`,
          code: "invalid_input_schema",
        },
      ],
    };
  }
  const parsed = schema.safeParse(input);
  if (parsed.success) return { ok: true, issues: [] };
  return {
    ok: false,
    issues: parsed.error.issues.map((issue) => ({
      path: `tools.${toolName}.input_schema.${issue.path.join(".")}`,
      message: issue.message,
      code: "invalid_tool_input",
    })),
  };
}

/** Assert that `agent` is allowed to call `toolName`; throws on failure. */
export function assertAgentAccess(
  manifest: AtomcPluginManifest,
  toolName: string,
  agent: string,
): void {
  const tool = findTool(manifest, toolName);
  if (!tool) {
    throw new PluginConformanceError([
      { path: `tools.${toolName}`, message: `unknown tool "${toolName}"`, code: "unknown_tool" },
    ]);
  }
  if (!tool.agents.includes(agent as never)) {
    throw new PluginConformanceError([
      {
        path: `tools.${toolName}.agents`,
        message: `agent "${agent}" is not permitted to call this tool`,
        code: "agent_not_permitted",
      },
    ]);
  }
}

/**
 * True when every pointer in `pointers` is within an approved `produces` scope,
 * i.e. equal to or a descendant of a declared write scope.
 */
export function isWithinProduces(manifest: AtomcPluginManifest, pointer: string): boolean {
  if (!isValidPointer(pointer)) return false;
  return manifest.produces.some((scope) => {
    if (scope === pointer) return true;
    const scopeTokens = parsePointer(scope);
    const pointerTokens = parsePointer(pointer);
    if (pointerTokens.length < scopeTokens.length) return false;
    return scopeTokens.every((token, index) => token === pointerTokens[index]);
  });
}

/**
 * Check a plugin descriptor + its manifest for conformance.
 *
 * Verifies: manifest validity; every declared handler is implemented; no undeclared
 * handlers are exposed; tool input schemas compile; mutating tools declare write
 * scopes; and all tools are rescoped within `produces`.
 */
export function conformance(
  plugin: AtomcPlugin,
  context: ManifestValidationContext = {},
): ConformanceReport {
  const issues: ConformanceIssue[] = [];
  const manifestResult = validatePluginManifest(plugin.manifest, context);
  if (!manifestResult.success) {
    issues.push(...fromManifestIssues(manifestResult.issues));
    return { ok: false, issues };
  }

  for (const gate of plugin.manifest.gates) {
    if (!plugin.gates.has(gate.id)) {
      issues.push({
        path: `gates.${gate.id}`,
        message: `gate "${gate.id}" has no registered handler`,
        code: "missing_handler",
      });
    }
  }
  for (const tool of plugin.manifest.tools) {
    if (!plugin.tools.has(tool.name)) {
      issues.push({
        path: `tools.${tool.name}`,
        message: `tool "${tool.name}" has no registered handler`,
        code: "missing_handler",
      });
    }
    if (tool.mutates && plugin.manifest.produces.length === 0) {
      issues.push({
        path: `tools.${tool.name}.mutates`,
        message: `mutating tool "${tool.name}" requires at least one produces scope`,
        code: "mutating_tool_without_produces",
      });
    }
    try {
      z.fromJSONSchema(tool.input_schema as never);
    } catch (error) {
      issues.push({
        path: `tools.${tool.name}.input_schema`,
        message: `invalid JSON Schema: ${error instanceof Error ? error.message : String(error)}`,
        code: "invalid_input_schema",
      });
    }
  }
  for (const entry of plugin.manifest.cli) {
    if (!plugin.cli.has(entry.command)) {
      issues.push({
        path: `cli.${entry.command}`,
        message: `CLI command "${entry.command}" has no registered handler`,
        code: "missing_handler",
      });
    }
  }

  // Reject handlers reachable through the descriptor that the manifest never declared.
  const declaredGateIds = new Set(plugin.manifest.gates.map((gate) => gate.id));
  for (const id of plugin.gates.keys()) {
    if (!declaredGateIds.has(id)) {
      issues.push({
        path: `gates.${id}`,
        message: `undeclared gate handler for "${id}"`,
        code: "undeclared_handler",
      });
    }
  }
  const declaredToolNames = new Set(plugin.manifest.tools.map((tool) => tool.name));
  for (const name of plugin.tools.keys()) {
    if (!declaredToolNames.has(name)) {
      issues.push({
        path: `tools.${name}`,
        message: `undeclared tool handler for "${name}"`,
        code: "undeclared_handler",
      });
    }
  }
  const declaredCommands = new Set(plugin.manifest.cli.map((entry) => entry.command));
  for (const command of plugin.cli.keys()) {
    if (!declaredCommands.has(command)) {
      issues.push({
        path: `cli.${command}`,
        message: `undeclared CLI handler for "${command}"`,
        code: "undeclared_handler",
      });
    }
  }

  return { ok: issues.length === 0, issues };
}

/** Assert conformance, throwing {@link PluginConformanceError} on failure. */
export function assertConformance(
  plugin: AtomcPlugin,
  context: ManifestValidationContext = {},
): void {
  const report = conformance(plugin, context);
  if (!report.ok) throw new PluginConformanceError(report.issues);
}
