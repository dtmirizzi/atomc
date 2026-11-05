/** Shared in-memory fakes: no sockets, no API keys, no network. */
import {
  ConflictError,
  type GateResult,
  type JsonPatchOp,
  LockedError,
} from "@atomc/daemon-client";
import type {
  AgentDefinition,
  AgentName,
  GateFailure,
  HarnessDaemon,
  ModelDecision,
  ModelProvider,
  ModelRequest,
  ToolDescriptor,
} from "../src/types.js";

export function gate(overrides: Partial<GateResult> = {}): GateResult {
  return {
    id: "gate:erc.no_unconnected",
    status: "PASS",
    severity: "blocking",
    plugin: "plugin:atopile@0.0.1",
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

export class FakeDaemon implements HarnessDaemon {
  rev = 10;
  readonly locked = new Map<string, string>();
  readonly events: string[] = [];
  readonly dagTargets: Array<string[] | undefined> = [];
  readonly gateIds: Array<readonly string[] | undefined> = [];
  readonly lockOrder: string[] = [];
  /** Scopes that always report a lock conflict. */
  lockConflicts = new Set<string>();
  /** Scopes whose unlock operation fails, for best-effort cleanup tests. */
  unlockFailures = new Set<string>();
  /** When true, `transact` throws an optimistic `ConflictError`. */
  transactConflict = false;
  gateResults: GateResult[] = [gate()];
  tools: ToolDescriptor[] = [];
  lockCalls = 0;
  unlockCalls = 0;
  maxLocked = 0;
  transactCalls = 0;
  toolCalls = 0;
  runDagCalls = 0;
  runGateCalls = 0;

  async getIR(path: string): Promise<{ rev: number; value: unknown }> {
    this.events.push(`getIR:${path}`);
    return { rev: this.rev, value: { path } };
  }

  async transact(params: {
    path: string;
    base_rev: number;
    ops: JsonPatchOp[];
    holder?: string;
  }): Promise<{ new_rev: number; changed_paths: string[] }> {
    this.transactCalls += 1;
    if (this.transactConflict) throw new ConflictError("stale rev", { current_rev: this.rev });
    this.rev += 1;
    return { new_rev: this.rev, changed_paths: [params.path] };
  }

  async lock(node: string, holder: string): Promise<{ expires_at: string }> {
    this.lockCalls += 1;
    this.events.push(`lock:${node}`);
    this.lockOrder.push(node);
    if (this.lockConflicts.has(node)) {
      throw new LockedError("locked", {
        holder: "agent:other#1",
        expires_at: "2026-11-05T00:00:00Z",
      });
    }
    this.locked.set(node, holder);
    this.maxLocked = Math.max(this.maxLocked, this.locked.size);
    return { expires_at: "2026-11-05T00:00:00Z" };
  }

  async unlock(node: string, holder: string): Promise<{ released: true }> {
    this.unlockCalls += 1;
    this.events.push(`unlock:${node}`);
    if (this.unlockFailures.has(node)) throw new Error(`unlock ${node} failed`);
    if (this.locked.get(node) === holder) this.locked.delete(node);
    return { released: true };
  }

  async runDAG(params?: { targets?: string[] }): Promise<{ run_id: string }> {
    this.runDagCalls += 1;
    this.dagTargets.push(params?.targets);
    this.events.push(`runDAG:${params?.targets?.join(",") ?? "*"}`);
    return { run_id: "fake-run" };
  }

  async runGates(ids?: readonly string[]): Promise<GateResult[]> {
    this.runGateCalls += 1;
    this.gateIds.push(ids);
    this.events.push(`runGates:${ids?.join(",") ?? "*"}`);
    return this.gateResults;
  }

  async listTools(agent?: AgentName): Promise<ToolDescriptor[]> {
    this.events.push(`listTools:${agent ?? "*"}`);
    return this.tools;
  }

  async callTool(plugin: string, tool: string, args: unknown): Promise<{ result: unknown }> {
    this.toolCalls += 1;
    this.events.push(`callTool:${plugin}:${tool}`);
    return { result: { args } };
  }
}

export function definition(overrides: Partial<AgentDefinition> = {}): AgentDefinition {
  return {
    id: "ee-agent",
    systemPrompt: "you fix electrical gates",
    permittedTools: [],
    lockScopes: ["/electrical", "/layout"],
    gates: ["erc.no_unconnected"],
    model: { provider: "fake", model: "fake-1" },
    budget: { maxTurns: 8, maxCostMinor: 100 },
    ...overrides,
  };
}

export const failure: GateFailure = {
  id: "gate:erc.no_unconnected",
  status: "FAIL",
  severity: "blocking",
  owner_agent: "ee-agent",
  ir_rev: 10,
  summary: "2 unconnected pins",
  refs: ["comp:U1"],
};

/** Scripted provider: yields the given decisions in order, then `give_up`. */
export class FakeProvider implements ModelProvider {
  readonly id = "fake";
  readonly requests: ModelRequest[] = [];

  constructor(private readonly decisions: ModelDecision[]) {}

  async nextTurn(request: ModelRequest): Promise<ModelDecision> {
    this.requests.push(request);
    const decision = this.decisions.shift();
    return decision ?? { kind: "give_up", reason: "script exhausted" };
  }
}

/** Provider that always throws (exercises error paths). */
export class ThrowingProvider implements ModelProvider {
  readonly id = "throwing";
  async nextTurn(): Promise<ModelDecision> {
    throw new Error("model boom");
  }
}
