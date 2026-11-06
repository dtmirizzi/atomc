/**
 * Convergence scheduler for the atomc swarm.
 *
 * `runAgent` (WP-3.2) drives one agent from a gate failure to a terminal
 * outcome. `converge` is the coordinator above it:
 *
 * 1. run the configured gates and treat blocking `FAIL`/`ERROR` as the sole
 *    source of truth (agents never self-report success);
 * 2. route each failure to the owning specialist(s) using the injected
 *    registry port;
 * 3. schedule disjoint lock scopes in parallel and overlapping scopes serially;
 * 4. re-run all gates after each round and stop when convergence criteria are
 *    met, a budget/round cap is hit, or a human checkpoint says so;
 * 5. roll back a failed agent's round-local writes so a conflict or escalation
 *    cannot leave the IR half-edited.
 *
 * The module deliberately knows nothing about WP-3.3's concrete registry or
 * provider implementation: {@link ConvergenceRegistry} is a structural port and
 * {@link ConvergeOptions.providerFor} is the provider seam. The CLI/Studio can
 * wire the real `AgentRegistry` and `PiAiProvider` without this file importing
 * either.
 *
 * See `docs/architecture/swarm.md`, `docs/architecture/contracts/agent-protocol.md`
 * and `docs/architecture/contracts/gate-result.md`.
 */

import type { JsonPatchOp } from "@atomc/core-ir";
import type { GateResult } from "@atomc/daemon-client";
import { runAgent } from "./runner.js";
import type {
  AgentDefinition,
  AgentName,
  AgentRunResult,
  GateFailure,
  HarnessDaemon,
  ModelProvider,
  SwarmEvent,
} from "./types.js";

/** Minimal registry seam; WP-3.3's `AgentRegistry` satisfies it structurally. */
export interface ConvergenceRegistry {
  get(id: AgentName): AgentDefinition | undefined;
  /** Optional multi-owner routing; falls back to `GateResult.owner_agent`. */
  agentsForGate?(gateId: string): readonly AgentDefinition[];
}

/** Build the model provider for one specialist definition. */
export type ProviderFactory = (definition: AgentDefinition) => ModelProvider;

/** Safe host seam for pi-ai construction; raw credentials never enter agent definitions or CLI args. */
export interface ConvergenceModelHost {
  providerFor(definition: AgentDefinition): ModelProvider;
}

/** Why a human checkpoint was requested. */
export type CheckpointReason =
  | "round"
  | "max_rounds"
  | "no_progress"
  | "budget"
  | "error"
  | "unroutable"
  | "unavailable"
  | "aborted";

/** What a checkpoint handler may decide. */
export type CheckpointDecision = "continue" | "accept" | "abort";

/** Context passed to a human-in-the-loop checkpoint. */
export interface CheckpointContext {
  reason: CheckpointReason;
  round: number;
  rounds: number;
  gateResults: readonly GateResult[];
  failures: readonly GateResult[];
  costMinor: number;
  maxCostMinor: number;
  tokens: number;
  maxTokens: number;
  turns: number;
  maxTurns: number;
  runs: readonly AgentRunResult[];
}

/** Rollback policy for failed agent runs. */
export type RollbackPolicy = "escalate" | "conflict" | "none";

/** Terminal status of a convergence run. */
export type ConvergeStatus =
  | "converged"
  | "accepted"
  | "escalated"
  | "budget_exhausted"
  | "aborted";

/** Event stream emitted while converging. */
export type ConvergeEvent =
  | {
      kind: "round.start";
      round: number;
      agentIds: AgentName[];
      failureIds: string[];
      at: string;
    }
  | { kind: "round.end"; round: number; gateResults: GateResult[]; costMinor: number; at: string }
  | { kind: "agent.start"; round: number; agentId: AgentName; failureId: string; at: string }
  | { kind: "agent.event"; round: number; agentId: AgentName; event: SwarmEvent; at: string }
  | { kind: "agent.result"; round: number; agentId: AgentName; result: AgentRunResult; at: string }
  | { kind: "agent.error"; round: number; agentId: AgentName; message: string; at: string }
  | { kind: "rollback"; round: number; agentId: AgentName; scopes: string[]; at: string }
  | { kind: "rollback.error"; round: number; agentId: AgentName; message: string; at: string }
  | { kind: "checkpoint"; reason: CheckpointReason; round: number; at: string }
  | { kind: "converged"; at: string }
  | { kind: "escalated"; reason: string; at: string }
  | { kind: "error"; message: string; at: string };

/** Options for {@link converge}. */
export interface ConvergeOptions {
  daemon: HarnessDaemon;
  registry: ConvergenceRegistry;
  providerFor?: ProviderFactory;
  /** Optional explicit host object for embedding applications. */
  modelHost?: ConvergenceModelHost;
  /** Gate ids to run; defaults to all gates the daemon knows about. */
  gateIds?: readonly string[];
  /** Maximum wake/verify rounds before a checkpoint/escalation. Default 3. */
  maxRounds?: number;
  /** Maximum number of extra rounds allowed after explicit human approval. Default 1. */
  maxRoundExtensions?: number;
  /** Retained coordination audit entries (bounded, excludes prompts/tool data). Default 256. */
  maxAuditEntries?: number;
  /** Spend cap in integer USD minor units (cents). Defaults to Number.MAX_SAFE_INTEGER. */
  maxCostMinor?: number;
  /** Aggregate token cap shared across all agents. Defaults to Number.MAX_SAFE_INTEGER. */
  maxTokens?: number;
  /** Aggregate provider-turn cap shared across all agents. Default 32. */
  maxTurns?: number;
  /** Consecutive rounds with an identical failure signature before a checkpoint. Default 2. */
  maxStallRounds?: number;
  /** Project root for `.atomc/sessions/<run>/<agent>.jsonl`. */
  projectRoot?: string;
  /** Shared run id for all agents in this convergence session. */
  runId?: string;
  signal?: AbortSignal;
  now?: () => Date;
  lockTtlS?: number;
  maxVerifyRetries?: number;
  maxConflictRetries?: number;
  /** Rollback failed runs; default `escalate`. */
  rollback?: RollbackPolicy;
  /** Ask a human when blocked or after every round. */
  checkpoint?: (context: CheckpointContext) => CheckpointDecision | Promise<CheckpointDecision>;
  /** Call the checkpoint after each non-converged round. */
  checkpointEveryRound?: boolean;
  /** Event sink for CLI/Studio streaming. */
  onEvent?: (event: ConvergeEvent) => void;
  /** Override the default convergence predicate. */
  isConverged?: (gates: readonly GateResult[]) => boolean;
}

/** Final outcome of a convergence session. */
export interface ConvergeAuditEntry {
  at: string;
  round: number;
  event: "gate_snapshot" | "agent_scheduled" | "agent_completed" | "checkpoint" | "terminal";
  gateIds?: string[];
  agentIds?: AgentName[];
  status?: ConvergeStatus;
  costMinor?: number;
  tokens?: number;
  reason?: string;
}

export interface ConvergeResult {
  status: ConvergeStatus;
  rounds: number;
  costMinor: number;
  tokens: number;
  turns: number;
  gateResults: GateResult[];
  failures: GateResult[];
  runs: AgentRunResult[];
  reasons: string[];
  /** Bounded, low-detail coordination audit; provider prompts/tool payloads are excluded. */
  audit: ConvergeAuditEntry[];
  runId: string;
}

interface ScopeSnapshot {
  path: string;
  rev: number;
  value: unknown;
}

interface WakeGroup {
  definition: AgentDefinition;
  failures: GateResult[];
}

const DEFAULT_MAX_ROUNDS = 3;
const DEFAULT_MAX_AUDIT_ENTRIES = 256;

function messageOf(error: unknown): string {
  if (typeof error === "string") return error;
  if (error instanceof Error) return error.message;
  if (error === null) return "null error";
  if (error === undefined) return "undefined error";
  return String(error);
}

/** Sanitize a run id exactly like `runAgent` does for transcript paths. */
function safeRunId(input: string): string {
  const cleaned = input
    .replace(/[^A-Za-z0-9._-]/g, "_")
    .replace(/^[^A-Za-z0-9]+/, "")
    .slice(0, 128);
  if (cleaned.length === 0) return "run";
  return cleaned;
}

/** Normalize a gate id that may carry the `gate:` prefix. */
function normalizeGateId(gateId: string): string {
  if (gateId.startsWith("gate:")) return gateId.slice(5);
  return gateId;
}

/** Blocking failures plus any crashed gate; advisory failures never block. */
function blockingFailures(gates: readonly GateResult[]): GateResult[] {
  return gates.filter(
    (gate) => gate.status === "ERROR" || (gate.severity === "blocking" && gate.status === "FAIL"),
  );
}

/** Default convergence criteria from the contract. */
export function defaultIsConverged(gates: readonly GateResult[]): boolean {
  if (gates.length === 0) return false;
  return !gates.some(
    (gate) => gate.status === "ERROR" || (gate.severity === "blocking" && gate.status === "FAIL"),
  );
}

/** True when two lock scopes are the same pointer or one contains the other. */
export function scopesOverlap(a: readonly string[], b: readonly string[]): boolean {
  if (a.length === 0 || b.length === 0) return false;
  for (const left of a) {
    for (const right of b) {
      if (left === right || left.startsWith(`${right}/`) || right.startsWith(`${left}/`)) {
        return true;
      }
    }
  }
  return false;
}

function toGateFailure(group: WakeGroup): GateFailure {
  const first = group.failures[0];
  if (first === undefined) {
    throw new Error("wake group has no failures");
  }
  return {
    id: first.id,
    status: first.status === "ERROR" ? "ERROR" : "FAIL",
    severity: first.severity,
    owner_agent: first.owner_agent,
    ir_rev: first.ir_rev,
    summary: group.failures.map((gate) => gate.summary).join("; "),
    refs: [...new Set(group.failures.flatMap((gate) => gate.refs))],
  };
}

function definitionForRun(definition: AgentDefinition, failures: GateResult[]): AgentDefinition {
  const existingGates = definition.gates ?? [];
  const failureGates = failures.map((gate) => normalizeGateId(gate.id));
  return { ...definition, gates: [...new Set([...existingGates, ...failureGates])] };
}

function routeFailures(
  failures: readonly GateResult[],
  registry: ConvergenceRegistry,
): { groups: WakeGroup[]; unroutable: GateResult[] } {
  const groups = new Map<AgentName, WakeGroup>();
  const unroutable: GateResult[] = [];

  for (const gate of failures) {
    const routed = registry.agentsForGate ? registry.agentsForGate(gate.id) : [];
    const definitions: AgentDefinition[] = [];
    for (const definition of routed) {
      if (!definitions.some((candidate) => candidate.id === definition.id)) {
        definitions.push(definition);
      }
    }
    if (definitions.length === 0 && gate.owner_agent !== null) {
      const fallback = registry.get(gate.owner_agent);
      if (fallback !== undefined) definitions.push(fallback);
    }
    if (definitions.length === 0) {
      unroutable.push(gate);
      continue;
    }
    for (const definition of definitions) {
      const existing = groups.get(definition.id);
      if (existing === undefined) {
        groups.set(definition.id, { definition, failures: [gate] });
      } else {
        existing.failures.push(gate);
      }
    }
  }

  return { groups: [...groups.values()], unroutable };
}

/**
 * Greedy batch scheduler: put a group in the first batch whose agents do not
 * share a lock scope. Disjoint specialists run in parallel; overlapping ones
 * run in a later batch. Batches themselves are sequential.
 */
function scheduleBatches(groups: readonly WakeGroup[]): WakeGroup[][] {
  const pending = [...groups];
  const batches: WakeGroup[][] = [];
  while (pending.length > 0) {
    const batch: WakeGroup[] = [];
    for (let index = 0; index < pending.length; ) {
      const group = pending[index];
      if (
        group !== undefined &&
        batch.every(
          (scheduled) =>
            !scopesOverlap(group.definition.lockScopes, scheduled.definition.lockScopes),
        )
      ) {
        batch.push(group);
        pending.splice(index, 1);
      } else {
        index += 1;
      }
    }
    batches.push(batch);
  }
  return batches;
}

function sameValue(left: unknown, right: unknown): boolean {
  try {
    const leftJson = JSON.stringify(left);
    const rightJson = JSON.stringify(right);
    if (leftJson === undefined || rightJson === undefined) return false;
    return leftJson === rightJson;
  } catch {
    return false;
  }
}

function shouldRollback(policy: RollbackPolicy, result: AgentRunResult): boolean {
  if (policy === "none") return false;
  if (policy === "escalate") return result.outcome !== "PASS";
  if (result.outcome === "ABORTED") return true;
  return result.outcome === "ESCALATE" && /conflict|lock|abort/i.test(result.reason ?? "");
}

/** Split an integer budget as evenly as possible across a batch. */
export function splitBudget(total: number, count: number): number[] {
  if (!Number.isSafeInteger(count) || count < 0) {
    throw new RangeError("budget recipient count must be a non-negative safe integer");
  }
  if (count === 0) return [];
  if (!Number.isSafeInteger(total) || total < 0) {
    throw new RangeError("aggregate budget must be a non-negative safe integer");
  }
  const base = Math.floor(total / count);
  const remainder = total % count;
  const shares: number[] = [];
  for (let index = 0; index < count; index += 1) {
    const extra = index < remainder;
    shares.push(extra ? base + 1 : base);
  }
  return shares;
}

/** Stable signature of the current blocking failure set, for no-progress detection. */
function failureSignature(gates: readonly GateResult[]): string {
  return blockingFailures(gates)
    .map(
      (gate) => `${gate.id}:${gate.status}:${gate.severity}:${gate.summary}:${gate.refs.join(",")}`,
    )
    .sort()
    .join("|");
}

/**
 * Run the swarm until every blocking gate passes, a budget/round cap is hit, or
 * a human checkpoint stops or accepts the run.
 *
 * Convergence reads actual `GateResult`s only. A run that returns `PASS` from
 * its own gates still has to survive the full gate set re-run at the end of the
 * round.
 */
export async function converge(options: ConvergeOptions): Promise<ConvergeResult> {
  const now = options.now ?? (() => new Date());
  const at = (): string => now().toISOString();
  const emit = (event: ConvergeEvent): void => {
    try {
      options.onEvent?.(event);
    } catch {
      // Observability callbacks must never stop convergence or rollback.
    }
  };
  const daemon = options.daemon;
  const registry = options.registry;
  const maxRounds = options.maxRounds ?? DEFAULT_MAX_ROUNDS;
  const maxCostMinor = options.maxCostMinor ?? Number.MAX_SAFE_INTEGER;
  const maxTokens = options.maxTokens ?? Number.MAX_SAFE_INTEGER;
  const maxTurns = options.maxTurns ?? 32;
  const maxStallRounds = options.maxStallRounds ?? 2;
  const maxRoundExtensions = options.maxRoundExtensions ?? 1;
  const maxAuditEntries = options.maxAuditEntries ?? DEFAULT_MAX_AUDIT_ENTRIES;
  if (!Number.isSafeInteger(maxRounds) || maxRounds < 1) {
    throw new RangeError("maxRounds must be a positive safe integer");
  }
  for (const [name, value] of [
    ["maxCostMinor", maxCostMinor],
    ["maxTokens", maxTokens],
    ["maxTurns", maxTurns],
  ] as const) {
    if (!Number.isSafeInteger(value) || value < 0) {
      throw new RangeError(`${name} must be a non-negative safe integer`);
    }
  }
  if (!Number.isSafeInteger(maxStallRounds) || maxStallRounds < 1) {
    throw new RangeError("maxStallRounds must be a positive safe integer");
  }
  if (!Number.isSafeInteger(maxRoundExtensions) || maxRoundExtensions < 0) {
    throw new RangeError("maxRoundExtensions must be a non-negative safe integer");
  }
  if (!Number.isSafeInteger(maxAuditEntries) || maxAuditEntries < 1) {
    throw new RangeError("maxAuditEntries must be a positive safe integer");
  }
  const runId = safeRunId(options.runId ?? `converge-${now().getTime()}`);
  const rollbackPolicy = options.rollback ?? "escalate";
  const converged = options.isConverged ?? defaultIsConverged;

  const runs: AgentRunResult[] = [];
  const reasons: string[] = [];
  let gateResults: GateResult[] = [];
  let rounds = 0;
  let allowedRounds = maxRounds;
  let costMinor = 0;
  let tokens = 0;
  let turns = 0;
  let stallCount = 0;
  let lastSignature = "";
  let checkpointExtensions = 0;
  const audit: ConvergeAuditEntry[] = [];
  const recordAudit = (entry: Omit<ConvergeAuditEntry, "at" | "round">): void => {
    audit.push({ at: at(), round: rounds, ...entry });
    if (audit.length > maxAuditEntries) {
      audit.splice(0, audit.length - maxAuditEntries);
    }
  };

  const buildResult = (status: ConvergeStatus): ConvergeResult => ({
    status,
    rounds,
    costMinor,
    tokens,
    turns,
    gateResults: [...gateResults],
    failures: blockingFailures(gateResults),
    runs: [...runs],
    reasons: [...reasons],
    audit: [...audit],
    runId,
  });

  const checkpoint = async (reason: CheckpointReason): Promise<"continue" | "accept" | "abort"> => {
    emit({ kind: "checkpoint", reason, round: rounds, at: at() });
    recordAudit({ event: "checkpoint", reason });
    const context: CheckpointContext = {
      reason,
      round: rounds,
      rounds: allowedRounds,
      gateResults: [...gateResults],
      failures: blockingFailures(gateResults),
      costMinor,
      maxCostMinor,
      tokens,
      maxTokens,
      turns,
      maxTurns,
      runs: [...runs],
    };
    if (options.checkpoint === undefined) {
      reasons.push(`blocked without a checkpoint handler: ${reason}`);
      return "abort";
    }
    try {
      const decision = await options.checkpoint(context);
      if (
        decision === "continue" &&
        (reason === "budget" ||
          reason === "error" ||
          reason === "unroutable" ||
          reason === "unavailable")
      ) {
        reasons.push(`checkpoint cannot continue after ${reason}`);
        recordAudit({ event: "checkpoint", reason: `denied_continue:${reason}` });
        return "abort";
      }
      if (decision === "accept") {
        reasons.push(`checkpoint accepted remaining failures after ${reason}`);
        recordAudit({ event: "checkpoint", reason: `accept:${reason}` });
        return "accept";
      }
      if (decision === "continue") {
        // A checkpoint may extend the hard cap, but only a bounded number of
        // times. No-progress continuation resets the repeated-failure counter.
        if (reason === "max_rounds") {
          if (checkpointExtensions >= maxRoundExtensions) {
            reasons.push(`max round extensions (${maxRoundExtensions}) exhausted`);
            return "abort";
          }
          checkpointExtensions += 1;
          allowedRounds += 1;
        }
        if (reason === "no_progress") stallCount = 0;
        return "continue";
      }
      reasons.push(`checkpoint aborted after ${reason}`);
      recordAudit({ event: "checkpoint", reason: `abort:${reason}` });
      return "abort";
    } catch (error) {
      reasons.push(`checkpoint handler failed: ${messageOf(error)}`);
      return "abort";
    }
  };

  const abortResult = (reason: CheckpointReason): ConvergeResult => {
    const status: ConvergeStatus = reason === "budget" ? "budget_exhausted" : "escalated";
    recordAudit({ event: "terminal", status, reason });
    emit({ kind: "escalated", reason: reasons.at(-1) ?? reason, at: at() });
    return buildResult(status);
  };

  const snapshotScopes = async (definition: AgentDefinition): Promise<ScopeSnapshot[]> => {
    const snapshots: ScopeSnapshot[] = [];
    for (const path of definition.lockScopes) {
      const read = await daemon.getIR(path);
      snapshots.push({ path, rev: read.rev, value: read.value });
    }
    return snapshots;
  };

  const rollbackScopes = async (
    snapshots: readonly ScopeSnapshot[],
    holder: string,
    agentId: AgentName,
  ): Promise<void> => {
    const restored: string[] = [];
    for (const snapshot of snapshots) {
      let attempt = 0;
      for (;;) {
        try {
          const current = await daemon.getIR(snapshot.path);
          if (current.rev === snapshot.rev || sameValue(current.value, snapshot.value)) {
            break;
          }
          const ops: JsonPatchOp[] = [{ op: "replace", path: "", value: snapshot.value }];
          await daemon.transact({
            path: snapshot.path,
            base_rev: current.rev,
            ops,
            holder,
          });
          restored.push(snapshot.path);
          break;
        } catch (error) {
          attempt += 1;
          if (attempt > 2) {
            emit({
              kind: "rollback.error",
              round: rounds,
              agentId,
              message: messageOf(error),
              at: at(),
            });
            reasons.push(`rollback failed for ${agentId} at ${snapshot.path}: ${messageOf(error)}`);
            break;
          }
        }
      }
    }
    if (restored.length > 0) {
      emit({ kind: "rollback", round: rounds, agentId, scopes: restored, at: at() });
    }
  };

  const runGroup = async (
    group: WakeGroup,
    share: { maxTurns: number; maxCostMinor: number; maxTokens: number },
  ): Promise<AgentRunResult> => {
    const base = definitionForRun(group.definition, group.failures);
    const definition: AgentDefinition = {
      ...base,
      budget: {
        ...base.budget,
        maxTurns: Math.min(base.budget?.maxTurns ?? 8, share.maxTurns),
        maxCostMinor: Math.min(
          base.budget?.maxCostMinor ?? Number.MAX_SAFE_INTEGER,
          share.maxCostMinor,
        ),
        maxTokens: Math.min(base.budget?.maxTokens ?? Number.MAX_SAFE_INTEGER, share.maxTokens),
      },
    };
    const failure = toGateFailure(group);
    const snapshots: ScopeSnapshot[] = [];
    const holder = `agent:${definition.id}#${rounds}`;
    emit({
      kind: "agent.start",
      round: rounds,
      agentId: definition.id,
      failureId: failure.id,
      at: at(),
    });
    try {
      if (rollbackPolicy !== "none") snapshots.push(...(await snapshotScopes(definition)));
      const result = await runAgent({
        definition,
        failure,
        daemon,
        provider:
          options.modelHost?.providerFor(definition) ??
          options.providerFor?.(definition) ??
          (() => {
            throw new Error(`no model provider configured for ${definition.id}`);
          })(),
        runId,
        sessionSeq: rounds,
        ...(options.projectRoot !== undefined && { projectRoot: options.projectRoot }),
        ...(options.signal !== undefined && { signal: options.signal }),
        ...(options.now !== undefined && { now: options.now }),
        ...(options.lockTtlS !== undefined && { lockTtlS: options.lockTtlS }),
        ...(options.maxVerifyRetries !== undefined && {
          maxVerifyRetries: options.maxVerifyRetries,
        }),
        ...(options.maxConflictRetries !== undefined && {
          maxConflictRetries: options.maxConflictRetries,
        }),
        onEvent: (event) =>
          emit({ kind: "agent.event", round: rounds, agentId: definition.id, event, at: at() }),
      });
      if (shouldRollback(rollbackPolicy, result) && snapshots.length > 0) {
        await rollbackScopes(snapshots, holder, definition.id);
      }
      emit({ kind: "agent.result", round: rounds, agentId: definition.id, result, at: at() });
      return result;
    } catch (error) {
      if (rollbackPolicy !== "none" && snapshots.length > 0) {
        await rollbackScopes(snapshots, holder, definition.id);
      }
      reasons.push(`agent ${definition.id} crashed: ${messageOf(error)}`);
      emit({
        kind: "agent.error",
        round: rounds,
        agentId: definition.id,
        message: messageOf(error),
        at: at(),
      });
      throw error;
    }
  };

  try {
    gateResults = await daemon.runGates(options.gateIds);
    recordAudit({ event: "gate_snapshot", gateIds: gateResults.map((gate) => gate.id) });
    if (converged(gateResults)) {
      emit({ kind: "converged", at: at() });
      return buildResult("converged");
    }

    for (;;) {
      if (options.signal?.aborted) {
        reasons.push("aborted by signal");
        emit({ kind: "escalated", reason: "aborted by signal", at: at() });
        return buildResult("aborted");
      }

      const failures = blockingFailures(gateResults);
      if (failures.length === 0 && gateResults.length === 0) {
        reasons.push(
          "daemon returned no gate results; cannot establish convergence (plugins may be missing)",
        );
        const decision = await checkpoint("unavailable");
        if (decision === "accept") return buildResult("accepted");
        return abortResult("unavailable");
      }
      if (failures.length === 0) {
        emit({ kind: "converged", at: at() });
        return buildResult("converged");
      }

      const crashed = failures.find((gate) => gate.status === "ERROR");
      if (crashed !== undefined) {
        reasons.push(`gate ${crashed.id} crashed (ERROR); escalating to the coordinator`);
        const decision = await checkpoint("error");
        if (decision === "accept") return buildResult("accepted");
        if (decision === "continue") continue;
        return abortResult("error");
      }

      if (costMinor >= maxCostMinor) {
        reasons.push(`cost cap reached (${costMinor} >= ${maxCostMinor} minor units)`);
        const decision = await checkpoint("budget");
        if (decision === "accept") return buildResult("accepted");
        if (decision === "continue") continue;
        return abortResult("budget");
      }

      if (tokens >= maxTokens || turns >= maxTurns) {
        reasons.push(
          turns >= maxTurns
            ? `turn cap reached (${turns} >= ${maxTurns})`
            : `token cap reached (${tokens} >= ${maxTokens})`,
        );
        const decision = await checkpoint("budget");
        if (decision === "accept") return buildResult("accepted");
        if (decision === "continue") continue;
        return abortResult("budget");
      }

      const { groups, unroutable } = routeFailures(failures, registry);
      if (unroutable.length > 0) {
        reasons.push(`unroutable blocking gates: ${unroutable.map((gate) => gate.id).join(", ")}`);
        const decision = await checkpoint("unroutable");
        if (decision === "accept") return buildResult("accepted");
        if (decision === "continue") continue;
        return abortResult("unroutable");
      }
      if (rounds >= allowedRounds) {
        const decision = await checkpoint("max_rounds");
        if (decision === "accept") return buildResult("accepted");
        if (decision === "continue") continue;
        return abortResult("max_rounds");
      }

      rounds += 1;
      recordAudit({
        event: "agent_scheduled",
        agentIds: groups.map((group) => group.definition.id),
        gateIds: groups.flatMap((group) => group.failures.map((gate) => gate.id)),
      });
      emit({
        kind: "round.start",
        round: rounds,
        agentIds: groups.map((group) => group.definition.id),
        failureIds: groups.flatMap((group) => group.failures.map((gate) => gate.id)),
        at: at(),
      });

      for (const batch of scheduleBatches(groups)) {
        // Split the remaining aggregate budget across the batch so parallel
        // agents cannot each spend the full shared remainder. Rounding
        // remainders go to the earliest groups.
        const costShares = splitBudget(maxCostMinor - costMinor, batch.length);
        const tokenShares = splitBudget(maxTokens - tokens, batch.length);
        const turnShares = splitBudget(maxTurns - turns, batch.length);
        const settled = await Promise.allSettled(
          batch.map((group, index) =>
            runGroup(group, {
              maxTurns: turnShares[index] ?? 0,
              maxCostMinor: costShares[index] ?? 0,
              maxTokens: tokenShares[index] ?? 0,
            }),
          ),
        );
        for (const [index, outcome] of settled.entries()) {
          if (outcome.status === "fulfilled") {
            runs.push(outcome.value);
            costMinor += Math.max(0, Math.floor(outcome.value.costMinor));
            tokens += Math.max(0, Math.floor(outcome.value.tokens));
            turns += Math.max(0, Math.floor(outcome.value.turns));
            recordAudit({
              event: "agent_completed",
              agentIds: [outcome.value.session.agentId],
              costMinor: outcome.value.costMinor,
              tokens: outcome.value.tokens,
              reason: outcome.value.outcome,
            });
          } else {
            const group = batch[index];
            if (group === undefined) {
              reasons.push(`agent run ${index} failed: ${messageOf(outcome.reason)}`);
              continue;
            }
            reasons.push(`agent ${group.definition.id} failed: ${messageOf(outcome.reason)}`);
          }
        }
        if (options.signal?.aborted) {
          reasons.push("aborted by signal during a round");
          emit({ kind: "escalated", reason: "aborted by signal", at: at() });
          return buildResult("aborted");
        }
      }

      gateResults = await daemon.runGates(options.gateIds);
      recordAudit({ event: "gate_snapshot", gateIds: gateResults.map((gate) => gate.id) });
      emit({
        kind: "round.end",
        round: rounds,
        gateResults: [...gateResults],
        costMinor,
        at: at(),
      });

      if (converged(gateResults)) {
        emit({ kind: "converged", at: at() });
        return buildResult("converged");
      }

      recordAudit({ event: "gate_snapshot", gateIds: gateResults.map((gate) => gate.id) });
      const signature = failureSignature(gateResults);
      if (signature === lastSignature) {
        stallCount += 1;
      } else {
        lastSignature = signature;
        stallCount = 1;
      }
      if (stallCount >= maxStallRounds) {
        reasons.push(`no progress after ${stallCount} rounds with the same blocking failures`);
        const decision = await checkpoint("no_progress");
        if (decision === "accept") return buildResult("accepted");
        if (decision !== "continue") return abortResult("no_progress");
        // "continue" grants one more round without raising the hard cap.
      }

      if (options.checkpointEveryRound && options.checkpoint !== undefined) {
        const decision = await checkpoint("round");
        if (decision === "accept") return buildResult("accepted");
        if (decision !== "continue") return abortResult("round");
        // "continue" falls through to the next round without extending the cap.
      }
    }
  } catch (error) {
    reasons.push(`convergence failed: ${messageOf(error)}`);
    emit({ kind: "error", message: messageOf(error), at: at() });
    if (options.signal?.aborted) return buildResult("aborted");
    emit({ kind: "escalated", reason: messageOf(error), at: at() });
    return buildResult("escalated");
  }
}
