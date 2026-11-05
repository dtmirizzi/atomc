/**
 * `runAgent` — the transactional loop from `agent-protocol.md`.
 *
 * The harness reads scoped IR, acquires per-node locks, asks an injected
 * {@link ModelProvider} for patch/tool decisions, applies only transactions at
 * the current `_meta.rev`, runs a targeted DAG + owned gates, and treats the
 * gate results as the sole source of truth for convergence. Agents never
 * self-report success. Locks are released on every exit path.
 */
import { ConflictError, type GateResult } from "@atomc/daemon-client";
import { z } from "zod";
import { SwarmStateMachine } from "./state-machine.js";
import { TranscriptWriter } from "./transcript.js";
import type {
  AgentBudget,
  AgentDefinition,
  AgentRunResult,
  AgentSession,
  AgentState,
  AgentToolCall,
  GateFailure,
  HarnessDaemon,
  ModelDecision,
  ModelProvider,
  RunOutcome,
  SwarmEvent,
  ToolDescriptor,
  TurnUsage,
} from "./types.js";

/** Options for {@link runAgent}. */
export interface RunAgentOptions {
  definition: AgentDefinition;
  failure: GateFailure;
  daemon: HarnessDaemon;
  provider: ModelProvider;
  /** Transcript writer; a default one under `projectRoot` is created when omitted. */
  transcript?: TranscriptWriter;
  /** Project root for the default transcript writer. */
  projectRoot?: string;
  /** Cancellation signal; checked between turns and daemon calls. */
  signal?: AbortSignal;
  /** Clock override for deterministic tests. */
  now?: () => Date;
  /** Run id (transcript directory); defaults to a timestamp. */
  runId?: string;
  /** Session sequence used in the lock holder id. */
  sessionSeq?: number;
  /** Lock TTL in seconds. */
  lockTtlS?: number;
  /** In-run gate retries before yielding a `RETRY` outcome. */
  maxVerifyRetries?: number;
  /** Bounded re-read/replan attempts after optimistic revision conflicts. */
  maxConflictRetries?: number;
  /** Event sink for CLI/Studio streaming. */
  onEvent?: (event: SwarmEvent) => void;
}

const DEFAULT_BUDGET: AgentBudget = { maxTurns: 8, maxCostMinor: 500 };

/** Internal control-flow signal that also names the transition to take. */
class RunBail extends Error {
  constructor(
    readonly event: "PLAN_FAILED" | "LOCK_FAILED" | "GIVE_UP" | "ACTION_FAILED" | "ABORT",
    readonly outcome: RunOutcome,
    reason: string,
  ) {
    super(reason);
    this.name = "RunBail";
  }
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** True when `path` is the scope itself or a descendant, and never `/meta`. */
export function isWithinScopes(path: string, scopes: readonly string[]): boolean {
  if (path === "/meta" || path.startsWith("/meta/")) return false;
  return scopes.some((scope) => path === scope || path.startsWith(`${scope}/`));
}

/** Check a `plugin:tool` call against an agent allow-list (`*` and `plugin:*` supported). */
export function isToolPermitted(permitted: readonly string[], call: AgentToolCall): boolean {
  if (permitted.includes("*")) return true;
  return (
    permitted.includes(`${call.plugin}:${call.tool}`) || permitted.includes(`${call.plugin}:*`)
  );
}

function isBlockingFailure(gate: GateResult): boolean {
  return gate.status === "FAIL" && gate.severity === "blocking";
}

function terminalEvent(
  outcome: RunOutcome,
): "RELEASE_PASS" | "RELEASE_RETRY" | "RELEASE_ESCALATE" | "RELEASE_ABORTED" {
  switch (outcome) {
    case "PASS":
      return "RELEASE_PASS";
    case "RETRY":
      return "RELEASE_RETRY";
    case "ABORTED":
      return "RELEASE_ABORTED";
    default:
      return "RELEASE_ESCALATE";
  }
}

/** Run one transactional agent session to a terminal outcome. */
export async function runAgent(options: RunAgentOptions): Promise<AgentRunResult> {
  const { definition, failure, daemon, provider } = options;
  const now = options.now ?? (() => new Date());
  const at = (): string => now().toISOString();
  const emit = (event: SwarmEvent): void => {
    try {
      options.onEvent?.(event);
    } catch {
      // Observability callbacks must not interrupt lock cleanup or the agent transaction.
    }
  };

  const budget: AgentBudget = { ...DEFAULT_BUDGET, ...definition.budget };
  const maxTurns = budget.maxTurns;
  const maxCostMinor = budget.maxCostMinor;
  const maxTokens = budget.maxTokens;
  const maxVerifyRetries = options.maxVerifyRetries ?? 1;
  const maxConflictRetries = options.maxConflictRetries ?? 1;
  const lockTtlS = options.lockTtlS ?? 120;
  const holder = `agent:${definition.id}#${options.sessionSeq ?? 1}`;
  const requestedRunId = options.runId ?? `run-${now().getTime()}`;
  const runId = requestedRunId.replace(/[^A-Za-z0-9._-]/g, "_").slice(0, 128) || "run";
  const session: AgentSession = {
    id: `${runId}:${definition.id}`,
    runId,
    agentId: definition.id,
    holder,
    model: definition.model,
    startedAt: at(),
  };
  const transcript =
    options.transcript ??
    new TranscriptWriter({
      projectRoot: options.projectRoot ?? process.cwd(),
      runId,
      agentId: definition.id,
    });

  const machine = new SwarmStateMachine();
  machine.onTransition((from: AgentState, to: AgentState) => {
    emit({ kind: "state", from, to, at: at() });
  });

  const acquired: string[] = [];
  let scopeReads: Array<{ path: string; rev: number; value: unknown }> = [];
  let turns = 0;
  let costMinor = 0;
  let tokens = 0;
  let verifyRetries = 0;
  let conflictAttempts = 0;
  let outcome: RunOutcome = "ESCALATE";
  let reason: string | undefined;
  let gateResults: GateResult[] = [];
  let currentTools: ToolDescriptor[] = [];

  const readScopes = async (): Promise<void> => {
    const reads: Array<{ path: string; rev: number; value: unknown }> = [];
    for (const scope of definition.lockScopes) {
      const read = await daemon.getIR(scope);
      reads.push({ path: scope, rev: read.rev, value: read.value });
    }
    scopeReads = reads;
  };

  const scopeFor = (path: string): { path: string; rev: number; value: unknown } | undefined =>
    scopeReads.find((read) => path === read.path || path.startsWith(`${read.path}/`));

  const bailIfAborted = (): void => {
    if (options.signal?.aborted) throw new RunBail("ABORT", "ABORTED", "aborted");
  };

  const releaseAll = async (): Promise<void> => {
    for (const node of [...acquired].reverse()) {
      try {
        await daemon.unlock(node, holder);
        emit({ kind: "lock.released", node, holder, at: at() });
      } catch (error) {
        emit({ kind: "error", message: `unlock ${node} failed: ${messageOf(error)}`, at: at() });
      }
    }
    acquired.length = 0;
  };

  const recordUsage = (usage: TurnUsage | undefined): void => {
    const boundedCount = (value: number | undefined): number =>
      value === undefined || !Number.isFinite(value) ? 0 : Math.max(0, Math.floor(value));
    costMinor += boundedCount(usage?.costMinor);
    tokens += boundedCount(usage?.inputTokens) + boundedCount(usage?.outputTokens);
  };

  const acquireLocks = async (): Promise<void> => {
    for (const scope of definition.lockScopes) {
      let attempt = 0;
      for (;;) {
        bailIfAborted();
        attempt += 1;
        try {
          const result = await daemon.lock(scope, holder, lockTtlS, `wake:${failure.id}`);
          acquired.push(scope);
          emit({
            kind: "lock.acquired",
            node: scope,
            holder,
            expires_at: result.expires_at,
            at: at(),
          });
          break;
        } catch (error) {
          emit({ kind: "lock.conflict", node: scope, contact: true, at: at() });
          await readScopes();
          if (attempt > maxConflictRetries) {
            throw new RunBail(
              "LOCK_FAILED",
              "ESCALATE",
              `could not lock ${scope}: ${messageOf(error)}`,
            );
          }
        }
      }
    }
  };

  const runVerification = async (): Promise<void> => {
    bailIfAborted();
    const targets = definition.dagTargets;
    await daemon.runDAG(targets === undefined ? {} : { targets: [...targets] });
    const ids =
      definition.gates === undefined || definition.gates.length === 0
        ? undefined
        : definition.gates;
    gateResults = await daemon.runGates(ids);
    for (const gate of gateResults) {
      emit({ kind: "gate.result", gate, at: at() });
      await transcript.append({ kind: "gate.result", gate, at: at() });
    }
  };

  const handlePatch = async (decision: ModelDecision): Promise<void> => {
    const proposal = decision.proposal;
    if (proposal === undefined) {
      throw new RunBail("ACTION_FAILED", "ESCALATE", "patch decision without a proposal");
    }
    if (!isWithinScopes(proposal.path, definition.lockScopes)) {
      throw new RunBail(
        "ACTION_FAILED",
        "ESCALATE",
        `patch path ${proposal.path} is outside the agent lock scopes`,
      );
    }
    if (definition.produces !== undefined && !isWithinScopes(proposal.path, definition.produces)) {
      throw new RunBail(
        "ACTION_FAILED",
        "ESCALATE",
        `patch path ${proposal.path} is outside the agent produces scopes`,
      );
    }
    const read = scopeFor(proposal.path);
    if (read === undefined) {
      throw new RunBail("ACTION_FAILED", "ESCALATE", `no read for patch path ${proposal.path}`);
    }
    if (proposal.baseRev !== read.rev) {
      conflictAttempts += 1;
      emit({ kind: "patch.conflict", path: proposal.path, attempt: conflictAttempts, at: at() });
      await transcript.append({
        kind: "patch.conflict",
        path: proposal.path,
        expected_rev: proposal.baseRev,
        current_rev: read.rev,
        at: at(),
      });
      await readScopes();
      if (conflictAttempts > maxConflictRetries) {
        throw new RunBail("ACTION_FAILED", "ESCALATE", "optimistic conflict retries exceeded");
      }
      return; // Re-read happened; the model is asked again instead of blind resend.
    }
    try {
      const result = await daemon.transact({
        path: proposal.path,
        base_rev: read.rev,
        ops: proposal.ops,
        holder,
      });
      read.rev = result.new_rev;
      emit({ kind: "patch.applied", path: proposal.path, new_rev: result.new_rev, at: at() });
      await transcript.append({
        kind: "patch.applied",
        path: proposal.path,
        base_rev: result.new_rev - 1,
        new_rev: result.new_rev,
        ops: proposal.ops,
        at: at(),
      });
    } catch (error) {
      if (error instanceof ConflictError) {
        conflictAttempts += 1;
        emit({ kind: "patch.conflict", path: proposal.path, attempt: conflictAttempts, at: at() });
        await readScopes();
        if (conflictAttempts > maxConflictRetries) {
          throw new RunBail("ACTION_FAILED", "ESCALATE", "optimistic conflict retries exceeded");
        }
        return;
      }
      throw new RunBail("ACTION_FAILED", "ESCALATE", `transact failed: ${messageOf(error)}`);
    }
  };

  const handleTool = async (decision: ModelDecision): Promise<void> => {
    const call = decision.tool;
    if (call === undefined) {
      throw new RunBail("ACTION_FAILED", "ESCALATE", "tool decision without a call");
    }
    if (!isToolPermitted(definition.permittedTools, call)) {
      emit({
        kind: "tool.rejected",
        plugin: call.plugin,
        tool: call.tool,
        reason: "not permitted",
        at: at(),
      });
      await transcript.append({
        kind: "tool.rejected",
        plugin: call.plugin,
        tool: call.tool,
        at: at(),
      });
      return;
    }
    const descriptor = currentTools.find(
      (tool) => tool.plugin === call.plugin && tool.name === call.tool,
    );
    if (descriptor === undefined) {
      throw new RunBail(
        "ACTION_FAILED",
        "ESCALATE",
        `tool ${call.plugin}:${call.tool} is not available from the daemon`,
      );
    }
    let schema: z.ZodType;
    try {
      schema = z.fromJSONSchema(descriptor.input_schema as never);
    } catch (error) {
      throw new RunBail(
        "ACTION_FAILED",
        "ESCALATE",
        `tool ${call.plugin}:${call.tool} has an invalid input schema: ${messageOf(error)}`,
      );
    }
    const parsed = schema.safeParse(call.args);
    if (!parsed.success) {
      throw new RunBail(
        "ACTION_FAILED",
        "ESCALATE",
        `tool ${call.plugin}:${call.tool} arguments failed schema validation: ${parsed.error.message}`,
      );
    }
    try {
      const result = await daemon.callTool(call.plugin, call.tool, parsed.data, holder);
      emit({ kind: "tool.called", plugin: call.plugin, tool: call.tool, at: at() });
      await transcript.append({
        kind: "tool",
        plugin: call.plugin,
        tool: call.tool,
        args: call.args,
        result: result.result,
        at: at(),
      });
    } catch (error) {
      await transcript.append({
        kind: "tool.error",
        plugin: call.plugin,
        tool: call.tool,
        error: messageOf(error),
        at: at(),
      });
      throw new RunBail(
        "ACTION_FAILED",
        "ESCALATE",
        `tool ${call.plugin}:${call.tool} failed: ${messageOf(error)}`,
      );
    }
  };

  const actAndVerify = async (): Promise<void> => {
    for (;;) {
      bailIfAborted();
      if (turns >= maxTurns) {
        throw new RunBail("ACTION_FAILED", "ESCALATE", `max turns (${maxTurns}) reached`);
      }
      if (costMinor >= maxCostMinor) {
        throw new RunBail("ACTION_FAILED", "ESCALATE", `cost budget (${maxCostMinor}) reached`);
      }
      if (maxTokens !== undefined && tokens >= maxTokens) {
        throw new RunBail("ACTION_FAILED", "ESCALATE", `token budget (${maxTokens}) reached`);
      }

      currentTools = daemon.listTools ? await daemon.listTools(definition.id) : [];
      const decision = await provider.nextTurn({
        session,
        failure,
        scopeReads: scopeReads.map((read) => ({
          path: read.path,
          rev: read.rev,
          value: read.value,
        })),
        transcript: [],
        tools: currentTools,
        turn: turns,
        remainingCostMinor: Math.max(0, maxCostMinor - costMinor),
      });
      turns += 1;
      recordUsage(decision.usage);
      await transcript.append({ kind: "decision", turn: turns, decision, at: at() });
      if (costMinor >= maxCostMinor) {
        throw new RunBail("ACTION_FAILED", "ESCALATE", `cost budget (${maxCostMinor}) reached`);
      }
      if (maxTokens !== undefined && tokens >= maxTokens) {
        throw new RunBail("ACTION_FAILED", "ESCALATE", `token budget (${maxTokens}) reached`);
      }

      switch (decision.kind) {
        case "verify": {
          machine.send("VERIFY_REQUESTED");
          await runVerification();
          const hasError = gateResults.some((gate) => gate.status === "ERROR");
          const blocking = gateResults.filter(isBlockingFailure);
          if (hasError) {
            throw new RunBail("ACTION_FAILED", "ESCALATE", "a verification gate crashed (ERROR)");
          }
          if (blocking.length === 0) return;
          if (verifyRetries < maxVerifyRetries) {
            verifyRetries += 1;
            await readScopes();
            machine.send("RETRY_TURN");
            continue;
          }
          if (turns < maxTurns && costMinor < maxCostMinor) {
            throw new RunBail("ACTION_FAILED", "RETRY", "blocking gate failures remain");
          }
          throw new RunBail("ACTION_FAILED", "ESCALATE", "blocking gate failures persist");
        }
        case "give_up":
          throw new RunBail("GIVE_UP", "ESCALATE", decision.reason ?? "model gave up");
        case "patch":
          await handlePatch(decision);
          continue;
        case "tool":
          await handleTool(decision);
          continue;
        default:
          throw new RunBail(
            "ACTION_FAILED",
            "ESCALATE",
            `unknown decision kind: ${String(decision.kind)}`,
          );
      }
    }
  };

  machine.send("START");
  try {
    await transcript.append({ kind: "meta", session, failure, budget, at: at() });
    bailIfAborted();
    await readScopes();
    machine.send("PLANNED");
    await acquireLocks();
    machine.send("LOCKED");
    await actAndVerify();
    machine.send("VERIFIED");
    outcome = "PASS";
  } catch (error) {
    if (error instanceof RunBail) {
      machine.trySend(error.event);
      outcome = error.outcome;
      reason = error.message;
    } else if (options.signal?.aborted) {
      machine.trySend("ABORT");
      outcome = "ABORTED";
      reason = "aborted";
    } else {
      emit({ kind: "error", message: messageOf(error), at: at() });
      machine.trySend(machine.state === "PLAN" ? "PLAN_FAILED" : "ACTION_FAILED");
      outcome = "ESCALATE";
      reason = messageOf(error);
    }
  } finally {
    await releaseAll();
    machine.trySend(terminalEvent(outcome));
    await transcript.append({
      kind: "outcome",
      outcome,
      state: machine.state,
      turns,
      cost_minor: costMinor,
      tokens,
      reason,
      at: at(),
    });
  }

  const result: AgentRunResult = {
    outcome,
    session,
    state: machine.state,
    turns,
    costMinor,
    tokens,
    gateResults,
    transcriptPath: transcript.path,
  };
  if (reason !== undefined) result.reason = reason;
  return result;
}
