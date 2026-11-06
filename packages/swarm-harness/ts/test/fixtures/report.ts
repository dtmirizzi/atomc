/**
 * Safe, deterministic swarm test-report utility (WP-3.5).
 *
 * Summarizes one `runAgent` session — outcome, state path, decisions, tool calls,
 * gate transitions and minor-unit spend — from the {@link SwarmEvent} stream and
 * the returned {@link AgentRunResult}. Deliberately excludes wall-clock
 * timestamps, transcript paths and raw tool arguments so reports can be diffed
 * and attached to CI without leaking secrets or flaking on time.
 */
import { redactText } from "../../src/transcript.js";
import type {
  AgentRunResult,
  AgentState,
  ModelDecision,
  RunOutcome,
  SwarmEvent,
} from "../../src/types.js";

export interface SessionReportInput {
  result: AgentRunResult;
  events: readonly SwarmEvent[];
  /** Decisions the provider returned, in order (optional). */
  decisions?: readonly ModelDecision[];
}

export interface ToolCallSummary {
  plugin: string;
  tool: string;
  rejected: boolean;
}

export interface GateTransition {
  id: string;
  status: string;
  severity: string;
}

export interface SessionReport {
  agentId: string;
  outcome: RunOutcome;
  state: AgentState;
  turns: number;
  costMinor: number;
  tokens: number;
  statePath: string[];
  decisions: string[];
  patchPaths: string[];
  toolCalls: ToolCallSummary[];
  gates: GateTransition[];
  locksAcquired: string[];
  locksReleased: string[];
  conflicts: number;
}

function scrubbed(value: string): string {
  return redactText(value);
}

/** Build a deterministic, secret-free summary of one agent session. */
export function buildSessionReport(input: SessionReportInput): SessionReport {
  const { result, events } = input;
  const statePath: string[] = [];
  const patchPaths: string[] = [];
  const toolCalls: ToolCallSummary[] = [];
  const gates: GateTransition[] = [];
  const locksAcquired: string[] = [];
  const locksReleased: string[] = [];
  let conflicts = 0;

  for (const event of events) {
    switch (event.kind) {
      case "state":
        statePath.push(`${event.from}->${event.to}`);
        break;
      case "lock.acquired":
        locksAcquired.push(scrubbed(event.node));
        break;
      case "lock.released":
        locksReleased.push(scrubbed(event.node));
        break;
      case "lock.conflict":
        conflicts += 1;
        break;
      case "patch.applied":
        patchPaths.push(scrubbed(event.path));
        break;
      case "patch.conflict":
        conflicts += 1;
        break;
      case "tool.called":
        toolCalls.push({
          plugin: scrubbed(event.plugin),
          tool: scrubbed(event.tool),
          rejected: false,
        });
        break;
      case "tool.rejected":
        toolCalls.push({
          plugin: scrubbed(event.plugin),
          tool: scrubbed(event.tool),
          rejected: true,
        });
        break;
      case "gate.result":
        gates.push({
          id: scrubbed(event.gate.id),
          status: event.gate.status,
          severity: event.gate.severity,
        });
        break;
      default:
        break;
    }
  }

  const decisions = (input.decisions ?? []).map((decision) => {
    switch (decision.kind) {
      case "patch":
        return decision.proposal === undefined
          ? "patch"
          : `patch:${scrubbed(decision.proposal.path)}`;
      case "tool":
        return decision.tool === undefined
          ? "tool"
          : `tool:${scrubbed(decision.tool.plugin)}:${scrubbed(decision.tool.tool)}`;
      default:
        return decision.kind;
    }
  });

  return {
    agentId: scrubbed(result.session.agentId),
    outcome: result.outcome,
    state: result.state,
    turns: result.turns,
    costMinor: result.costMinor,
    tokens: result.tokens,
    statePath,
    decisions,
    patchPaths,
    toolCalls,
    gates,
    locksAcquired,
    locksReleased,
    conflicts,
  };
}

/** Render a report as stable key-sorted JSON (trailing newline). */
export function formatSessionReport(report: SessionReport): string {
  return `${JSON.stringify(report, null, 2)}\n`;
}
