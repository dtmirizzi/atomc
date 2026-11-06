/**
 * Recorded-session fixtures and a deterministic replay provider (WP-3.5).
 *
 * A recording captures the decisions a {@link ModelProvider} returned for one
 * `runAgent` session so CI can replay the exact same turn sequence without a
 * network, API key, or nondeterministic LLM. The format is versioned and
 * validated before use; a recording never contains secrets and is redacted
 * defensively before it is serialized or logged.
 *
 * Fixtures live in `test/fixtures/sessions/*.json`. See `./README.md` for how to
 * record and update them.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { JsonPatchOp } from "@atomc/core-ir";
import { z } from "zod";
import { redactEntry } from "../../src/transcript.js";
import {
  AGENT_NAMES,
  type GateFailure,
  type ModelConfig,
  type ModelDecision,
  type ModelProvider,
  type ModelRequest,
} from "../../src/types.js";

/** Version of the on-disk recording format. Bump on any breaking change. */
export const RECORDING_SCHEMA_VERSION = 1 as const;

/** Error thrown when a recording fails schema validation. */
export class RecordingValidationError extends Error {
  constructor(
    message: string,
    readonly detail: string,
  ) {
    super(message);
    this.name = "RecordingValidationError";
  }
}

/**
 * Structural guard for RFC 6902 ops. Written by hand so the validated type is
 * exactly {@link JsonPatchOp} (Zod treats `z.unknown()` fields as optional, which
 * would drop the required `value`/`from` members).
 */
export function isJsonPatchOp(value: unknown): value is JsonPatchOp {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  const op = record.op;
  if (typeof op !== "string" || typeof record.path !== "string") return false;
  switch (op) {
    case "add":
    case "replace":
    case "test":
      return "value" in record;
    case "remove":
      return true;
    case "move":
    case "copy":
      return typeof record.from === "string";
    default:
      return false;
  }
}

const JsonPatchOpSchema = z.custom<JsonPatchOp>(isJsonPatchOp, {
  message: "not a valid RFC 6902 JSON Patch op",
});

const ModelConfigSchema = z.object({
  provider: z.string().min(1),
  model: z.string().min(1),
  thinking: z.enum(["off", "low", "medium", "high"]).optional(),
  temperature: z.number().optional(),
  maxTokens: z.number().int().positive().optional(),
});

const TurnUsageSchema = z.object({
  inputTokens: z.number().int().nonnegative().optional(),
  outputTokens: z.number().int().nonnegative().optional(),
  costMinor: z.number().int().nonnegative().optional(),
});

const AgentToolCallSchema = z.object({
  plugin: z.string().min(1),
  tool: z.string().min(1),
  args: z.unknown(),
});

const AgentPatchProposalSchema = z.object({
  path: z.string().min(1),
  baseRev: z.number().int().nonnegative(),
  ops: z.array(JsonPatchOpSchema).min(1),
  rationale: z.string().optional(),
});

/** `ModelDecision` schema with cross-field rules (`patch` ⇒ proposal, `tool` ⇒ call). */
const ModelDecisionSchema = z
  .object({
    kind: z.enum(["patch", "tool", "verify", "give_up"]),
    proposal: AgentPatchProposalSchema.optional(),
    tool: AgentToolCallSchema.optional(),
    reason: z.string().optional(),
    usage: TurnUsageSchema.optional(),
  })
  .superRefine((decision, ctx) => {
    if (decision.kind === "patch" && decision.proposal === undefined) {
      ctx.addIssue({ code: "custom", message: 'kind "patch" requires a proposal' });
    }
    if (decision.kind === "tool" && decision.tool === undefined) {
      ctx.addIssue({ code: "custom", message: 'kind "tool" requires a tool call' });
    }
  });

const GateFailureSchema = z.object({
  id: z.string().min(1),
  status: z.enum(["FAIL", "ERROR"]),
  severity: z.enum(["blocking", "advisory"]),
  owner_agent: z.enum(AGENT_NAMES).nullable(),
  ir_rev: z.number().int().nonnegative(),
  summary: z.string(),
  refs: z.array(z.string()),
});

const RecordedTurnSchema = z.object({
  /** 0-based model turn this decision answers; replayed against `ModelRequest.turn`. */
  turn: z.number().int().nonnegative(),
  decision: ModelDecisionSchema,
  /** Optional context assertions captured at record time. */
  request: z
    .object({
      remainingCostMinor: z.number().int().nonnegative().optional(),
      toolNames: z.array(z.string()).optional(),
    })
    .optional(),
});

const RecordedSessionSchema = z.object({
  schema_version: z.literal(RECORDING_SCHEMA_VERSION),
  id: z.string().regex(/^[a-z0-9][a-z0-9-]{0,63}$/, "id must be a kebab-case slug"),
  description: z.string().min(1),
  agent: z.enum(AGENT_NAMES),
  model: ModelConfigSchema,
  failure: GateFailureSchema,
  turns: z.array(RecordedTurnSchema).min(1),
});

/** A validated, versioned recording of one agent session's model decisions. */
export type RecordedSession = z.infer<typeof RecordedSessionSchema>;

/** Result of validating an untrusted recording value. */
export type RecordingValidation =
  | { ok: true; session: RecordedSession }
  | { ok: false; error: string };

/** Validate an untrusted value against the versioned recording schema. */
export function validateRecording(value: unknown): RecordingValidation {
  const parsed = RecordedSessionSchema.safeParse(value);
  if (!parsed.success) return { ok: false, error: parsed.error.message };
  return { ok: true, session: parsed.data };
}

/** Parse an untrusted value or throw {@link RecordingValidationError}. */
export function parseRecording(value: unknown): RecordedSession {
  const result = validateRecording(value);
  if (!result.ok) {
    const id =
      typeof value === "object" && value !== null && "id" in value
        ? String((value as { id: unknown }).id)
        : "<unknown>";
    throw new RecordingValidationError(`invalid swarm recording ${id}`, result.error);
  }
  return result.session;
}

/** Defensive redaction: drop sensitive keys/tokens before persisting or logging. */
export function redactRecording(value: unknown): unknown {
  return redactEntry(value);
}

/** Deterministic JSON (recursively sorted keys, 2-space indent, trailing newline). */
export function canonicalJson(value: unknown): string {
  return `${JSON.stringify(sortKeys(value), null, 2)}\n`;
}

function sortKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value === null || typeof value !== "object") return value;
  const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) =>
    a < b ? -1 : a > b ? 1 : 0,
  );
  const out: Record<string, unknown> = {};
  for (const [key, child] of entries) out[key] = sortKeys(child);
  return out;
}

/** Serialize a recording to canonical, diff-stable JSON. */
export function serializeRecording(session: RecordedSession): string {
  return canonicalJson(session);
}

/** Load and validate one recording file. */
export function loadRecordingFile(path: string): RecordedSession {
  let raw: string;
  try {
    raw = readFileSync(path, "utf8");
  } catch (error) {
    throw new RecordingValidationError(`cannot read recording ${path}`, String(error));
  }
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch (error) {
    throw new RecordingValidationError(`recording ${path} is not valid JSON`, String(error));
  }
  try {
    return parseRecording(value);
  } catch (error) {
    if (error instanceof RecordingValidationError) {
      throw new RecordingValidationError(`${path}: ${error.message}`, error.detail);
    }
    throw error;
  }
}

/** Load every `*.json` recording in a directory, sorted by file name. */
export function loadRecordingsFromDir(
  dir: string,
): Array<{ file: string; session: RecordedSession }> {
  return readdirSync(dir)
    .filter((name) => name.endsWith(".json"))
    .sort()
    .map((name) => ({ file: name, session: loadRecordingFile(join(dir, name)) }));
}

/** Deep-clone a decision so replayed turns never share mutable state with fixtures. */
function cloneDecision(decision: unknown): ModelDecision {
  return JSON.parse(JSON.stringify(decision)) as ModelDecision;
}

export interface ReplayProviderOptions {
  /**
   * When false (default) a request whose `turn` does not match the recording
   * throws. Set true to tolerate extra requests (they replay as `give_up`).
   */
  tolerateTurnMismatch?: boolean;
}

/**
 * Deterministic {@link ModelProvider} that replays a {@link RecordedSession}.
 *
 * Turn `n` of the recording is returned for the `n`-th `nextTurn` call and the
 * request's own `turn` field is asserted against the recording so drift is loud.
 * When the recording is exhausted the provider gives up, matching the fake
 * provider's behaviour and keeping `runAgent` bounded.
 */
export class ReplayProvider implements ModelProvider {
  readonly id = "replay";
  readonly requests: ModelRequest[] = [];
  readonly decisionsMade: ModelDecision[] = [];
  #index = 0;
  readonly #tolerateTurnMismatch: boolean;

  constructor(
    readonly session: RecordedSession,
    options: ReplayProviderOptions = {},
  ) {
    this.#tolerateTurnMismatch = options.tolerateTurnMismatch ?? false;
  }

  /** Number of recorded turns already replayed. */
  get consumed(): number {
    return this.#index;
  }

  /** Number of recorded turns still available. */
  get remaining(): number {
    return Math.max(0, this.session.turns.length - this.#index);
  }

  async nextTurn(request: ModelRequest): Promise<ModelDecision> {
    this.requests.push(request);
    const recorded = this.session.turns[this.#index];
    if (recorded === undefined) {
      const decision: ModelDecision = { kind: "give_up", reason: "recording exhausted" };
      this.decisionsMade.push(decision);
      return decision;
    }
    if (request.turn !== recorded.turn && !this.#tolerateTurnMismatch) {
      throw new Error(
        `replay turn mismatch for ${this.session.id}: request turn ${request.turn}, recorded turn ${recorded.turn}`,
      );
    }
    this.#index += 1;
    const decision = cloneDecision(recorded.decision);
    this.decisionsMade.push(decision);
    return decision;
  }
}

/** Convenience factory for {@link ReplayProvider}. */
export function createReplayProvider(
  session: RecordedSession,
  options: ReplayProviderOptions = {},
): ReplayProvider {
  return new ReplayProvider(session, options);
}

// Keep the type exports close to the schema so consumers can build fixtures in code.
export type { GateFailure, ModelConfig, ModelDecision };
