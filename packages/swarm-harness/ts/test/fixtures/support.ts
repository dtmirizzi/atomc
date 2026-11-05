/**
 * Shared helpers for the WP-3.5 recording/replay, budget and report tests.
 *
 * These import only the public/stable WP-3.2 surface plus the fixtures in
 * `./sessions`; no WP-3.3/WP-3.4 code is referenced so the suite stays green on
 * the current `main` baseline.
 */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { GateResult } from "@atomc/daemon-client";
import type { AgentDefinition, AgentName, ModelConfig } from "../../src/types.js";
import { loadRecordingFile, type RecordedSession } from "./recordings.js";

export const SESSIONS_DIR = fileURLToPath(new URL("./sessions", import.meta.url));

/** Load one committed recording by base name (without `.json`). */
export function loadFixture(name: string): RecordedSession {
  return loadRecordingFile(join(SESSIONS_DIR, `${name}.json`));
}

/** Narrow an optional value or throw, replacing non-null assertions in tests. */
export function assertDefined<T>(value: T | undefined, message = "expected a defined value"): T {
  if (value === undefined) throw new Error(message);
  return value;
}

/** Build a fresh temp project root for transcript output. */
export function makeTempRoot(prefix = "atomc-wp35-"): string {
  return mkdtempSync(join(tmpdir(), prefix));
}

const AGENT_SCOPES: Record<AgentName, readonly string[]> = {
  "ee-agent": ["/electrical", "/layout", "/keyboard"],
  "fw-agent": ["/firmware", "/simulation"],
  "mech-agent": ["/mechanical"],
  "ops-agent": ["/sourcing", "/fabrication", "/orders"],
};

const AGENT_TOOLS: Record<AgentName, readonly string[]> = {
  "ee-agent": ["atopile:*"],
  "fw-agent": ["qmk:*"],
  "mech-agent": ["cad-jig:*"],
  "ops-agent": ["sourcing:*", "orders:*"],
};

/** Construct an `AgentDefinition` for a recording, with test overrides. */
export function definitionFor(
  session: RecordedSession,
  overrides: Partial<AgentDefinition> = {},
): AgentDefinition {
  const scopes = AGENT_SCOPES[session.agent];
  const model: ModelConfig = { provider: session.model.provider, model: session.model.model };
  if (session.model.thinking !== undefined) model.thinking = session.model.thinking;
  if (session.model.temperature !== undefined) model.temperature = session.model.temperature;
  if (session.model.maxTokens !== undefined) model.maxTokens = session.model.maxTokens;
  return {
    id: session.agent,
    systemPrompt: `recorded ${session.agent}`,
    permittedTools: AGENT_TOOLS[session.agent],
    lockScopes: scopes,
    produces: scopes,
    gates: [session.failure.id.replace(/^gate:/, "")],
    model,
    budget: { maxTurns: 8, maxCostMinor: 1000 },
    ...overrides,
  };
}

/** A blocking PASS gate result. */
export function passGate(id: string, overrides: Partial<GateResult> = {}): GateResult {
  return gate({ id, status: "PASS", ...overrides });
}

/** A blocking FAIL gate result. */
export function failGate(id: string, overrides: Partial<GateResult> = {}): GateResult {
  return gate({ id, status: "FAIL", summary: "still failing", ...overrides });
}

function gate(overrides: Partial<GateResult>): GateResult {
  return {
    id: "gate:erc.no_unconnected",
    status: "PASS",
    severity: "blocking",
    plugin: "plugin:test@0.0.1",
    owner_agent: "ee-agent",
    evaluated_at: "2026-11-04T23:00:00Z",
    ir_rev: 10,
    duration_ms: 1,
    summary: "ok",
    evidence: [],
    suggestions: [],
    refs: [],
    ...overrides,
  };
}

/** A tool descriptor with a permissive-but-real JSON Schema. */
export function toolDescriptor(
  plugin: string,
  name: string,
  overrides: Partial<{
    description: string;
    inputSchema: Record<string, unknown>;
    mutates: boolean;
  }> = {},
): {
  plugin: string;
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  mutates: boolean;
} {
  return {
    plugin,
    name,
    description: overrides.description ?? `${plugin}:${name}`,
    input_schema: overrides.inputSchema ?? {
      type: "object",
      properties: {},
      additionalProperties: true,
    },
    mutates: overrides.mutates ?? true,
  };
}
