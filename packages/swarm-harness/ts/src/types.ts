/**
 * Typed protocol for `@atomc/swarm-harness`.
 *
 * Mirrors `docs/architecture/contracts/agent-protocol.md` (v0.1) and
 * `docs/architecture/contracts/gate-result.md`. The harness is deliberately
 * transport-agnostic: it talks to the daemon through the narrow
 * {@link HarnessDaemon} port and to a model through {@link ModelProvider}, so
 * tests never touch the network and real provider wiring lives in an adapter.
 */
import type { JsonPatchOp } from "@atomc/core-ir";
import type { GateResult } from "@atomc/daemon-client";

/** Specialist agent ids from the frozen contract. */
export const AGENT_NAMES = ["ee-agent", "fw-agent", "mech-agent", "ops-agent"] as const;
export type AgentName = (typeof AGENT_NAMES)[number];

/** Terminal outcomes of one `runAgent` invocation. */
export type RunOutcome = "PASS" | "RETRY" | "ESCALATE" | "ABORTED";

/**
 * Model routing config. Mirrors the shape used in `atomc.config.ts`; secrets
 * (API keys, tokens) are never part of an `AgentDefinition` and never logged.
 */
export interface ModelConfig {
  /** Provider id, e.g. `openrouter`, `anthropic`, `fake`. */
  provider: string;
  /** Model id, e.g. `deepseek/deepseek-v4.1-flash`. */
  model: string;
  /** Optional thinking/reasoning budget hint. */
  thinking?: "off" | "low" | "medium" | "high";
  /** Optional sampling temperature. */
  temperature?: number;
  /** Optional max output tokens per turn. */
  maxTokens?: number;
}

/** Budget ceiling for a single agent run. */
export interface AgentBudget {
  /** Maximum model turns before escalation. */
  maxTurns: number;
  /** Maximum spend in integer USD minor units (cents). */
  maxCostMinor: number;
  /** Optional total token ceiling. */
  maxTokens?: number;
}

/** How an agent is allowed to act on IR, from the manifest/registry. */
export interface AgentDefinition {
  /** Stable agent id (`ee-agent`, `fw-agent`, …). */
  id: AgentName;
  /** System prompt used by the model adapter. */
  systemPrompt: string;
  /** Plugin tools the agent may call, as `"plugin:tool"` strings (or `*`). */
  permittedTools: readonly string[];
  /** IR subtree pointers the agent may lock and write (never `/meta`). */
  lockScopes: readonly string[];
  /** Plugin `produces` scopes this agent may write, from the manifest. */
  produces?: readonly string[];
  /** Gate ids this agent is responsible for, without the `gate:` prefix. */
  gates?: readonly string[];
  /** Optional DAG node ids to target before verifying. */
  dagTargets?: readonly string[];
  /** Model routing. */
  model: ModelConfig;
  /** Turn/cost/token ceilings. */
  budget?: Partial<AgentBudget>;
}

/** Metadata persisted alongside a transcript, safe to serialize. */
export interface AgentSession {
  readonly id: string;
  readonly runId: string;
  readonly agentId: AgentName;
  /** Lock holder id, `agent:<name>#<session-seq>`. */
  readonly holder: string;
  readonly model: ModelConfig;
  readonly startedAt: string;
}

/** One gate failure routed to this agent (contract: gate-result.md). */
export interface GateFailure {
  id: string;
  status: "FAIL" | "ERROR";
  severity: "blocking" | "advisory";
  owner_agent: AgentName | null;
  ir_rev: number;
  summary: string;
  refs: string[];
}

/** A pending IR mutation the model wants to apply. */
export interface AgentPatchProposal {
  /** JSON Pointer to the transaction base (must lie within a lock scope). */
  path: string;
  /** Revision the agent read before proposing. */
  baseRev: number;
  /** RFC 6902 ops, relative to `path` (daemon contract). */
  ops: JsonPatchOp[];
  /** Optional human-readable rationale. */
  rationale?: string;
}

/** A plugin tool invocation the model wants to make. */
export interface AgentToolCall {
  plugin: string;
  tool: string;
  args: unknown;
}

/** One tool invocation plus its observed result. */
export interface AgentTurn {
  index: number;
  kind: "tool";
  call: AgentToolCall;
  result?: unknown;
  error?: string;
  at: string;
}

/** What the model wants to do next. */
export interface ModelDecision {
  kind: "patch" | "tool" | "verify" | "give_up";
  proposal?: AgentPatchProposal;
  tool?: AgentToolCall;
  reason?: string;
  usage?: TurnUsage;
}

/**
 * One multimodal attachment carried into a model turn.
 *
 * Providers that accept images (pi-ai, Anthropic, OpenRouter multimodal models)
 * inline these as image content parts. Documents are pre-rendered to images by
 * the producing plugin; the harness never sends raw PDFs because provider
 * support is inconsistent.
 */
export interface ModelAttachment {
  /** Only inline images are supported today. */
  kind: "image";
  /** IANA media type, e.g. `image/png`. */
  mimeType: string;
  /** Base64 payload without a `data:` prefix. */
  data: string;
  /** Optional display name (e.g. datasheet page or render id). */
  name?: string;
  /** Optional source artifact ref for provenance (e.g. `art:render-plate`). */
  ref?: string;
}

/** Per-turn model accounting. */
export interface TurnUsage {
  inputTokens?: number;
  outputTokens?: number;
  /** Cost in integer USD minor units (cents). */
  costMinor?: number;
}

/** Context handed to the model adapter for one turn. */
export interface ModelRequest {
  session: AgentSession;
  failure: GateFailure;
  /** IR reads keyed by lock scope pointer. */
  scopeReads: ReadonlyArray<{ path: string; rev: number; value: unknown }>;
  transcript: readonly AgentTurn[];
  tools: readonly ToolDescriptor[];
  /** Optional multimodal attachments (datasheet/render images) for this turn. */
  attachments?: readonly ModelAttachment[];
  turn: number;
  remainingCostMinor: number;
}

/** Tool descriptor surfaced to the model (from `tools.list`). */
export interface ToolDescriptor {
  plugin: string;
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  mutates: boolean;
}

/** Narrow injectable model port. Implementations must not be called in tests. */
export interface ModelProvider {
  readonly id: string;
  nextTurn(request: ModelRequest): Promise<ModelDecision>;
}

/** The daemon operations the harness depends on (a subset of the RPC contract). */
export interface HarnessDaemon {
  getIR(path: string): Promise<{ rev: number; value: unknown }>;
  transact(params: {
    path: string;
    base_rev: number;
    ops: JsonPatchOp[];
    holder?: string;
  }): Promise<{ new_rev: number; changed_paths: string[] }>;
  lock(
    node: string,
    holder: string,
    ttlS: number,
    reason?: string,
  ): Promise<{ expires_at: string }>;
  unlock(node: string, holder: string): Promise<{ released: true }>;
  runDAG(params?: { targets?: string[]; force?: boolean }): Promise<{ run_id: string }>;
  runGates(ids?: readonly string[]): Promise<GateResult[]>;
  listTools?(agent?: AgentName): Promise<ToolDescriptor[]>;
  callTool(
    plugin: string,
    tool: string,
    args: unknown,
    holder?: string,
  ): Promise<{ result: unknown }>;
}

/** Events emitted by the state machine; the CLI can stream these. */
export type SwarmEvent =
  | { kind: "state"; from: AgentState; to: AgentState; at: string }
  | { kind: "lock.acquired"; node: string; holder: string; expires_at: string; at: string }
  | { kind: "lock.released"; node: string; holder: string; at: string }
  | { kind: "lock.conflict"; node: string; contact: boolean; at: string }
  | { kind: "patch.applied"; path: string; new_rev: number; at: string }
  | { kind: "patch.conflict"; path: string; attempt: number; at: string }
  | { kind: "tool.called"; plugin: string; tool: string; at: string }
  | { kind: "tool.rejected"; plugin: string; tool: string; reason: string; at: string }
  | { kind: "gate.result"; gate: GateResult; at: string }
  | { kind: "error"; message: string; at: string };

/** Agent states from the frozen agent-protocol loop plus terminals. */
export const AGENT_STATES = [
  "IDLE",
  "PLAN",
  "CLAIM_LOCK",
  "ACT",
  "VERIFY",
  "RELEASE",
  "DONE",
  "RETRY",
  "ESCALATE",
  "ABORTED",
] as const;
export type AgentState = (typeof AGENT_STATES)[number];

/** Result returned by `runAgent`. */
export interface AgentRunResult {
  outcome: RunOutcome;
  session: AgentSession;
  state: AgentState;
  turns: number;
  costMinor: number;
  tokens: number;
  gateResults: GateResult[];
  transcriptPath?: string;
  reason?: string;
}

/** Constructor options for the transcript writer. */
export interface TranscriptOptions {
  /** Project root; sessions live under `<root>/.atomc/sessions`. */
  projectRoot: string;
  /** Extra redaction patterns (applied to serialized strings). */
  redact?: readonly RegExp[];
}
