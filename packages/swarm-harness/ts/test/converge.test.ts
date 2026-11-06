/** Convergence scheduler tests: no sockets, API keys or real model calls. */
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  ConflictError,
  type GateResult,
  type JsonPatchOp,
  LockedError,
} from "@atomc/daemon-client";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import {
  type CheckpointContext,
  type CheckpointDecision,
  type ConvergeEvent,
  type ConvergenceRegistry,
  converge,
} from "../src/converge.js";
import type {
  AgentDefinition,
  AgentName,
  HarnessDaemon,
  ModelDecision,
  ModelProvider,
  ModelRequest,
} from "../src/types.js";
import { gate } from "./fakes.js";

interface ScopeState {
  rev: number;
  value: unknown;
}

class MutableDaemon implements HarnessDaemon {
  readonly scopes = new Map<string, ScopeState>();
  readonly locks = new Map<string, string>();
  readonly events: string[] = [];
  gates: GateResult[] = [];
  runGateCalls = 0;
  runDagCalls = 0;
  transactCalls = 0;
  lockConflicts = 0;
  maxLocked = 0;
  /** Make the Nth transact call throw an optimistic ConflictError. */
  conflictAt?: number;

  constructor(initial: Record<string, unknown>) {
    for (const [path, value] of Object.entries(initial)) {
      this.scopes.set(path, { rev: 1, value });
    }
  }

  async getIR(path: string): Promise<{ rev: number; value: unknown }> {
    this.events.push(`getIR:${path}`);
    const scope = this.scopes.get(path);
    if (scope === undefined) throw new Error(`unknown scope ${path}`);
    return { rev: scope.rev, value: scope.value };
  }

  async transact(params: {
    path: string;
    base_rev: number;
    ops: JsonPatchOp[];
    holder?: string;
  }): Promise<{ new_rev: number; changed_paths: string[] }> {
    this.transactCalls += 1;
    if (this.conflictAt === this.transactCalls) {
      throw new ConflictError("stale rev", { current_rev: 99 });
    }
    const scope = this.scopes.get(params.path);
    if (scope === undefined) throw new Error(`unknown scope ${params.path}`);
    if (scope.rev !== params.base_rev) {
      throw new ConflictError("stale rev", { current_rev: scope.rev });
    }
    let value = scope.value;
    for (const op of params.ops) {
      if (op.op !== "replace" || op.path !== "") {
        throw new Error(`unsupported test op ${op.op} at ${op.path}`);
      }
      value = "value" in op ? op.value : undefined;
    }
    const next = { rev: scope.rev + 1, value };
    this.scopes.set(params.path, next);
    return { new_rev: next.rev, changed_paths: [params.path] };
  }

  async lock(node: string, holder: string): Promise<{ expires_at: string }> {
    this.events.push(`lock:${node}`);
    if (this.locks.has(node)) {
      this.lockConflicts += 1;
      throw new LockedError("locked", {
        holder: this.locks.get(node) as string,
        expires_at: "2026-11-05T00:00:00Z",
      });
    }
    this.locks.set(node, holder);
    this.maxLocked = Math.max(this.maxLocked, this.locks.size);
    return { expires_at: "2026-11-05T00:00:00Z" };
  }

  async unlock(node: string, holder: string): Promise<{ released: true }> {
    this.events.push(`unlock:${node}`);
    if (this.locks.get(node) === holder) this.locks.delete(node);
    return { released: true };
  }

  async runDAG(): Promise<{ run_id: string }> {
    this.runDagCalls += 1;
    return { run_id: "fake-dag" };
  }

  async runGates(): Promise<GateResult[]> {
    this.runGateCalls += 1;
    return this.gates.map((result) => ({ ...result }));
  }

  async listTools(): Promise<[]> {
    return [];
  }

  async callTool(): Promise<{ result: unknown }> {
    throw new Error("test daemon does not expose tools");
  }
}

class TestRegistry implements ConvergenceRegistry {
  constructor(
    private readonly definitions: readonly AgentDefinition[],
    private readonly routes: Readonly<Record<string, readonly AgentName[]>> = {},
  ) {}

  get(id: AgentName): AgentDefinition | undefined {
    return this.definitions.find((definition) => definition.id === id);
  }

  agentsForGate(gateId: string): readonly AgentDefinition[] {
    const normalized = gateId.startsWith("gate:") ? gateId.slice("gate:".length) : gateId;
    const names = this.routes[normalized] ?? [];
    return names
      .map((name) => this.get(name))
      .filter((definition): definition is AgentDefinition => definition !== undefined);
  }
}

type Step = (request: ModelRequest) => ModelDecision | Promise<ModelDecision>;

class StepProvider implements ModelProvider {
  readonly id = "step";
  readonly #steps: Step[];

  constructor(steps: readonly Step[]) {
    this.#steps = [...steps];
  }

  async nextTurn(request: ModelRequest): Promise<ModelDecision> {
    const step = this.#steps.shift();
    return step === undefined
      ? { kind: "give_up", reason: "script exhausted" }
      : await step(request);
  }
}

function definition(
  id: AgentName,
  lockScopes: readonly string[],
  gates: readonly string[],
): AgentDefinition {
  return {
    id,
    systemPrompt: `fix ${id}`,
    permittedTools: ["*"],
    lockScopes,
    produces: lockScopes,
    gates,
    model: { provider: "fake", model: "fake-1" },
    budget: { maxTurns: 8, maxCostMinor: 1000, maxTokens: 1_000_000 },
  };
}

function fail(id = "gate:erc.no_unconnected", owner: AgentName | null = "ee-agent"): GateResult {
  return gate({
    id,
    status: "FAIL",
    severity: "blocking",
    owner_agent: owner,
    summary: `fail ${id}`,
  });
}

function pass(id = "gate:erc.no_unconnected", owner: AgentName | null = "ee-agent"): GateResult {
  return gate({ id, status: "PASS", severity: "blocking", owner_agent: owner, summary: "ok" });
}

function verifyPassing(daemon: MutableDaemon, results: GateResult[]): ModelProvider {
  return new StepProvider([
    () => {
      daemon.gates = results;
      return { kind: "verify" };
    },
  ]);
}

let projectRoot: string;

beforeAll(async () => {
  projectRoot = await mkdtemp(join(tmpdir(), "atomc-converge-"));
});

afterAll(async () => {
  await rm(projectRoot, { recursive: true, force: true });
});

describe("converge", () => {
  it("normalizes gate ids with and without the gate prefix", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [fail("erc.no_unconnected")];
    const registry = new TestRegistry(
      [definition("ee-agent", ["/electrical"], ["erc.no_unconnected"])],
      { "erc.no_unconnected": ["ee-agent"] },
    );
    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([() => ({ kind: "give_up" })]),
      projectRoot,
      maxRounds: 1,
    });
    expect(result.runs[0]?.session.agentId).toBe("ee-agent");
  });

  it("uses deterministic fallbacks for empty and unsafe run ids", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [pass()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const empty = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([]),
      projectRoot,
      runId: "...",
    });
    const sanitized = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([]),
      projectRoot,
      runId: "../bad id",
    });
    expect(empty.runId).toBe("run");
    expect(sanitized.runId).toBe("bad_id");
  });

  it("does not route an owner absent from the registry", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [fail("gate:unknown-owner", "fw-agent")];
    const registry: ConvergenceRegistry = { get: () => undefined };
    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([]),
      projectRoot,
    });
    expect(result.status).toBe("escalated");
    expect(result.reasons.join(" ")).toContain("unroutable");
  });

  it("runs route failures that have no optional registry router using the owner", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [fail()];
    const registry: ConvergenceRegistry = {
      get: (id) =>
        id === "ee-agent"
          ? definition("ee-agent", ["/electrical"], ["erc.no_unconnected"])
          : undefined,
    };
    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([() => ({ kind: "give_up", reason: "blocked" })]),
      projectRoot,
      maxRounds: 1,
    });
    expect(result.runs[0]?.session.agentId).toBe("ee-agent");

    const noDefinitions: ConvergenceRegistry = { get: () => undefined };
    daemon.gates = [fail("gate:unknown-owner", "fw-agent")];
    const missingOwner = await converge({
      daemon,
      registry: noDefinitions,
      providerFor: () => new StepProvider([]),
      projectRoot,
    });
    expect(missingOwner.status).toBe("escalated");
  });

  it("routes shared failures to multiple owners and groups repeated failures", async () => {
    const daemon = new MutableDaemon({ "/electrical": {}, "/sourcing": {} });
    daemon.gates = [
      fail("gate:bom.cost_under_budget", null),
      fail("gate:bom.cost_under_budget", null),
    ];
    const registry = new TestRegistry(
      [
        definition("ee-agent", ["/electrical"], ["bom.cost_under_budget"]),
        definition("ops-agent", ["/sourcing"], ["bom.cost_under_budget"]),
      ],
      { "bom.cost_under_budget": ["ee-agent", "ops-agent"] },
    );
    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([() => ({ kind: "give_up" })]),
      projectRoot,
      maxRounds: 1,
    });
    expect(result.runs.map((run) => run.session.agentId).sort()).toEqual(["ee-agent", "ops-agent"]);
  });

  it("covers routing fallbacks for null routes, missing owners and multiple owners", async () => {
    const ee = definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]);
    const fw = definition("fw-agent", ["/firmware"], ["fw.qmk_compile"]);
    const registry = new TestRegistry([ee, fw], {
      "gate:erc.no_unconnected": [],
      "gate:fw.qmk_compile": ["fw-agent", "fw-agent"],
    });
    const { defaultIsConverged, scopesOverlap } = await import("../src/converge.js");
    expect(scopesOverlap([], ["/electrical"])).toBe(false);
    expect(scopesOverlap(["/electrical"], [])).toBe(false);
    expect(scopesOverlap(["/board"], ["/board/keys"])).toBe(true);
    expect(scopesOverlap(["/board/keys"], ["/board"])).toBe(true);
    expect(defaultIsConverged([pass()])).toBe(true);
    expect(defaultIsConverged([fail()])).toBe(false);

    const daemon = new MutableDaemon({ "/electrical": {}, "/firmware": {} });
    daemon.gates = [fail("gate:unknown", null)];
    const missing = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([]),
      projectRoot,
    });
    expect(missing.status).toBe("escalated");
    daemon.gates = [fail("gate:unknown", "fw-agent")];
    expect(
      (await converge({ daemon, registry, providerFor: () => new StepProvider([]), projectRoot }))
        .status,
    ).toBe("escalated");

    daemon.gates = [fail("gate:erc.no_unconnected", "ee-agent")];
    const fallback = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([() => ({ kind: "give_up" })]),
      projectRoot,
      maxRounds: 1,
    });
    expect(fallback.runs[0]?.session.agentId).toBe("ee-agent");
  });

  it("returns converged without waking anyone when all blocking gates pass", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: true } });
    daemon.gates = [pass()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const events: ConvergeEvent[] = [];

    const result = await converge({
      daemon,
      registry,
      providerFor: () => {
        throw new Error("provider must not be called");
      },
      projectRoot,
      onEvent: (event) => events.push(event),
    });

    expect(result.status).toBe("converged");
    expect(result.rounds).toBe(0);
    expect(result.runs).toHaveLength(0);
    expect(events.some((event) => event.kind === "converged")).toBe(true);
  });

  it("routes a blocking failure to its owner and converges in one round", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: false } });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const events: ConvergeEvent[] = [];

    const result = await converge({
      daemon,
      registry,
      providerFor: () => verifyPassing(daemon, [pass()]),
      projectRoot,
      now: () => new Date("2026-11-05T00:00:00Z"),
      lockTtlS: 30,
      maxVerifyRetries: 1,
      maxConflictRetries: 1,
      signal: new AbortController().signal,
      onEvent: (event) => events.push(event),
    });

    expect(result.status).toBe("converged");
    expect(result.rounds).toBe(1);
    expect(result.runs).toHaveLength(1);
    expect(result.runs[0]?.session.agentId).toBe("ee-agent");
    expect(events.filter((event) => event.kind === "agent.start")).toHaveLength(1);
    expect(events.filter((event) => event.kind === "agent.result")).toHaveLength(1);
  });

  it("keeps waking the owner across rounds until gates pass", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: false } });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    let wakes = 0;

    const result = await converge({
      daemon,
      registry,
      providerFor: () => {
        wakes += 1;
        const current = wakes;
        return new StepProvider([
          () => {
            if (current >= 2) daemon.gates = [pass()];
            return { kind: "verify" };
          },
        ]);
      },
      projectRoot,
      maxRounds: 3,
    });

    expect(result.status).toBe("converged");
    expect(result.rounds).toBe(2);
    expect(wakes).toBe(2);
  });

  it("ignores advisory failures and does not wake an agent", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: false } });
    daemon.gates = [gate({ status: "FAIL", severity: "advisory", owner_agent: "ee-agent" })];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);

    const result = await converge({
      daemon,
      registry,
      providerFor: () => {
        throw new Error("provider must not be called");
      },
      projectRoot,
    });

    expect(result.status).toBe("converged");
    expect(result.runs).toHaveLength(0);
  });

  it("escalates when a blocking failure has no routable owner", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: false } });
    daemon.gates = [fail("gate:unknown.gate", null)];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const events: ConvergeEvent[] = [];

    const result = await converge({
      daemon,
      registry,
      providerFor: () => {
        throw new Error("provider must not be called");
      },
      projectRoot,
      onEvent: (event) => events.push(event),
    });

    expect(result.status).toBe("escalated");
    expect(result.runs).toHaveLength(0);
    expect(result.reasons.some((reason) => reason.includes("unroutable"))).toBe(true);
    expect(events.some((event) => event.kind === "checkpoint")).toBe(true);
  });

  it("halts at the cost ceiling before provider work and preserves gates", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const checkpointReasons: string[] = [];
    const result = await converge({
      daemon,
      registry,
      providerFor: () => {
        throw new Error("provider must not be invoked at exhausted budget");
      },
      projectRoot,
      maxCostMinor: 0,
      checkpoint: (context) => {
        checkpointReasons.push(context.reason);
        return "abort";
      },
    });
    expect(result.status).toBe("budget_exhausted");
    expect(checkpointReasons).toEqual(["budget"]);
    expect(result.failures).toHaveLength(1);
  });

  it("reports an unexpected checkpoint exception without losing the gate state", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [fail("gate:unknown", null)];
    const registry = new TestRegistry([]);
    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([]),
      projectRoot,
      checkpoint: () => {
        throw new Error("review host failed");
      },
    });
    expect(result.status).toBe("escalated");
    expect(result.failures).toHaveLength(1);
    expect(result.reasons.join(" ")).toContain("checkpoint handler failed");
  });

  it("escalates on a crashed gate without waking a domain agent", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: false } });
    daemon.gates = [gate({ status: "ERROR", severity: "blocking", owner_agent: "ee-agent" })];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);

    const result = await converge({
      daemon,
      registry,
      providerFor: () => {
        throw new Error("provider must not be called");
      },
      projectRoot,
    });

    expect(result.status).toBe("escalated");
    expect(result.runs).toHaveLength(0);
    expect(result.reasons.some((reason) => reason.includes("crashed"))).toBe(true);
  });

  it("stops at the cost cap and reports budget exhaustion", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: false } });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);

    const result = await converge({
      daemon,
      registry,
      providerFor: () =>
        new StepProvider([
          () => ({ kind: "verify", usage: { inputTokens: 10, outputTokens: 10, costMinor: 10 } }),
        ]),
      projectRoot,
      maxCostMinor: 5,
      maxRounds: 2,
    });

    expect(result.status).toBe("budget_exhausted");
    expect(result.costMinor).toBeGreaterThanOrEqual(5);
    expect(result.reasons.some((reason) => reason.includes("cost cap"))).toBe(true);
  });

  it("runs disjoint lock scopes in parallel", async () => {
    const daemon = new MutableDaemon({
      "/electrical": { ok: false },
      "/firmware": { ok: false },
    });
    daemon.gates = [
      fail("gate:erc.no_unconnected", "ee-agent"),
      fail("gate:fw.qmk_compile", "fw-agent"),
    ];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
      definition("fw-agent", ["/firmware"], ["fw.qmk_compile"]),
    ]);
    const concurrency = { active: 0, max: 0 };

    const delayed = (): ModelProvider =>
      new StepProvider([
        async () => {
          concurrency.active += 1;
          concurrency.max = Math.max(concurrency.max, concurrency.active);
          await new Promise((resolve) => setTimeout(resolve, 20));
          concurrency.active -= 1;
          daemon.gates = [
            pass("gate:erc.no_unconnected", "ee-agent"),
            pass("gate:fw.qmk_compile", "fw-agent"),
          ];
          return { kind: "verify" };
        },
      ]);

    const result = await converge({
      daemon,
      registry,
      providerFor: delayed,
      projectRoot,
      maxRounds: 2,
    });

    expect(result.status).toBe("converged");
    expect(result.runs).toHaveLength(2);
    expect(concurrency.max).toBe(2);
    expect(daemon.lockConflicts).toBe(0);
  });

  it("serializes agents whose lock scopes overlap", async () => {
    const daemon = new MutableDaemon({ "/shared": { ok: false } });
    daemon.gates = [
      fail("gate:erc.no_unconnected", "ee-agent"),
      fail("gate:fw.qmk_compile", "fw-agent"),
    ];
    const registry = new TestRegistry([
      definition("ee-agent", ["/shared"], ["erc.no_unconnected"]),
      definition("fw-agent", ["/shared"], ["fw.qmk_compile"]),
    ]);
    const concurrency = { active: 0, max: 0 };

    const delayed = (): ModelProvider =>
      new StepProvider([
        async () => {
          concurrency.active += 1;
          concurrency.max = Math.max(concurrency.max, concurrency.active);
          await new Promise((resolve) => setTimeout(resolve, 20));
          concurrency.active -= 1;
          daemon.gates = [
            pass("gate:erc.no_unconnected", "ee-agent"),
            pass("gate:fw.qmk_compile", "fw-agent"),
          ];
          return { kind: "verify" };
        },
      ]);

    const result = await converge({
      daemon,
      registry,
      providerFor: delayed,
      projectRoot,
      maxRounds: 2,
    });

    expect(result.status).toBe("converged");
    expect(result.runs).toHaveLength(2);
    expect(concurrency.max).toBe(1);
    expect(daemon.lockConflicts).toBe(0);
  });

  it("wakes every multi-owner agent returned by the registry", async () => {
    const daemon = new MutableDaemon({
      "/electrical": { ok: false },
      "/sourcing": { ok: false },
    });
    daemon.gates = [fail("gate:bom.cost_under_budget", null)];
    const registry = new TestRegistry(
      [
        definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
        definition("ops-agent", ["/sourcing"], ["bom.cost_under_budget"]),
      ],
      { "bom.cost_under_budget": ["ee-agent", "ops-agent"] },
    );

    const result = await converge({
      daemon,
      registry,
      providerFor: () => verifyPassing(daemon, [pass("gate:bom.cost_under_budget", null)]),
      projectRoot,
      maxRounds: 2,
    });

    expect(result.status).toBe("converged");
    expect(result.runs.map((run) => run.session.agentId).sort()).toEqual(["ee-agent", "ops-agent"]);
  });

  it("rolls back round-local writes when an agent escalates", async () => {
    const original = { components: ["old"] };
    const daemon = new MutableDaemon({ "/electrical": original });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const events: ConvergeEvent[] = [];

    const result = await converge({
      daemon,
      registry,
      providerFor: () =>
        new StepProvider([
          (request) => {
            const read = request.scopeReads[0];
            if (read === undefined) return { kind: "give_up", reason: "no read" };
            return {
              kind: "patch",
              proposal: {
                path: "/electrical",
                baseRev: read.rev,
                ops: [{ op: "replace", path: "", value: { components: ["new"] } }],
              },
            };
          },
          () => ({ kind: "verify" }),
        ]),
      projectRoot,
      maxRounds: 1,
      onEvent: (event) => events.push(event),
    });

    expect(result.status).toBe("escalated");
    expect(result.runs).toHaveLength(1);
    expect(result.runs[0]?.outcome).toBe("ESCALATE");
    expect(daemon.scopes.get("/electrical")?.value).toEqual(original);
    expect(events.some((event) => event.kind === "rollback")).toBe(true);
  });

  it("does not roll back when the policy is none", async () => {
    const daemon = new MutableDaemon({ "/electrical": { components: ["old"] } });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);

    await converge({
      daemon,
      registry,
      providerFor: () =>
        new StepProvider([
          (request) => {
            const read = request.scopeReads[0];
            if (read === undefined) return { kind: "give_up", reason: "no read" };
            return {
              kind: "patch",
              proposal: {
                path: "/electrical",
                baseRev: read.rev,
                ops: [{ op: "replace", path: "", value: { components: ["new"] } }],
              },
            };
          },
          () => ({ kind: "verify" }),
        ]),
      projectRoot,
      maxRounds: 1,
      rollback: "none",
    });

    expect(daemon.scopes.get("/electrical")?.value).toEqual({ components: ["new"] });
  });

  it("accepts a human checkpoint at max rounds", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: false } });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const checkpoints: CheckpointContext[] = [];

    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([() => ({ kind: "give_up", reason: "cannot fix" })]),
      projectRoot,
      maxRounds: 1,
      checkpoint: (context) => {
        checkpoints.push(context);
        return "accept";
      },
    });

    expect(result.status).toBe("accepted");
    expect(checkpoints[0]?.reason).toBe("max_rounds");
    expect(result.failures).toHaveLength(1);
  });

  it("continues past max rounds when a checkpoint asks for another round", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: false } });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    let wakes = 0;

    const result = await converge({
      daemon,
      registry,
      providerFor: () => {
        wakes += 1;
        const current = wakes;
        return new StepProvider([
          () => {
            if (current >= 2) daemon.gates = [pass()];
            return { kind: "verify" };
          },
        ]);
      },
      projectRoot,
      maxRounds: 1,
      checkpoint: () => "continue",
    });

    expect(result.status).toBe("converged");
    expect(result.rounds).toBe(2);
    expect(wakes).toBe(2);
  });

  it("aborts when a checkpoint rejects the state", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: false } });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);

    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([() => ({ kind: "give_up", reason: "cannot fix" })]),
      projectRoot,
      maxRounds: 1,
      checkpoint: () => "abort",
    });

    expect(result.status).toBe("escalated");
    expect(result.reasons.some((reason) => reason.includes("checkpoint aborted"))).toBe(true);
  });

  it("supports checkpoint-after-every-round", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: false } });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const reasons: string[] = [];

    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([() => ({ kind: "give_up", reason: "cannot fix" })]),
      projectRoot,
      maxRounds: 3,
      checkpointEveryRound: true,
      checkpoint: (context): CheckpointDecision => {
        reasons.push(context.reason);
        return "accept";
      },
    });

    expect(result.status).toBe("accepted");
    expect(reasons).toEqual(["round"]);
  });

  it("treats a continue decision at the budget checkpoint as an abort", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: false } });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);

    const result = await converge({
      daemon,
      registry,
      providerFor: () =>
        new StepProvider([
          () => ({ kind: "verify", usage: { inputTokens: 1, outputTokens: 1, costMinor: 10 } }),
        ]),
      projectRoot,
      maxCostMinor: 5,
      maxRounds: 2,
      checkpoint: () => "continue",
    });

    expect(result.status).toBe("budget_exhausted");
    expect(result.reasons.some((reason) => reason.includes("cannot continue"))).toBe(true);
  });

  it("escalates when the checkpoint handler throws", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: false } });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);

    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([() => ({ kind: "give_up", reason: "cannot fix" })]),
      projectRoot,
      maxRounds: 1,
      checkpoint: () => {
        throw new Error("human unavailable");
      },
    });

    expect(result.status).toBe("escalated");
    expect(result.reasons.some((reason) => reason.includes("checkpoint handler failed"))).toBe(
      true,
    );
  });

  it("stops before running agents when the signal is already aborted", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: false } });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const controller = new AbortController();
    controller.abort();

    const result = await converge({
      daemon,
      registry,
      providerFor: () => {
        throw new Error("provider must not be called");
      },
      projectRoot,
      signal: controller.signal,
    });

    expect(result.status).toBe("aborted");
    expect(result.runs).toHaveLength(0);
  });

  it("records an agent crash and escalates", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: false } });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const events: ConvergeEvent[] = [];
    // Snapshot reads fail, which makes the runGroup throw before runAgent starts.
    const originalGetIR = daemon.getIR.bind(daemon);
    daemon.getIR = async (path: string) => {
      if (path === "/electrical") throw new Error("read boom");
      return originalGetIR(path);
    };

    const result = await converge({
      daemon,
      registry,
      providerFor: () => {
        throw new Error("provider must not be called");
      },
      projectRoot,
      maxRounds: 1,
      onEvent: (event) => events.push(event),
    });

    expect(result.status).toBe("escalated");
    expect(result.reasons.some((reason) => reason.includes("read boom"))).toBe(true);
    expect(events.some((event) => event.kind === "agent.error")).toBe(true);
  });

  it("groups multiple blocking failures owned by the same specialist into one run", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [fail("gate:erc.one"), fail("gate:erc.two")];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.one", "erc.two"]),
    ]);
    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([() => ({ kind: "give_up" })]),
      projectRoot,
      maxRounds: 1,
    });
    expect(result.runs).toHaveLength(1);
    expect(result.runs[0]?.gateResults).toEqual([]);
  });

  it("bounds and sanitizes generated run ids and rejects malformed extension settings", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [pass()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([]),
      projectRoot,
      runId: " ../run with spaces ",
    });
    expect(result.runId).toBe("run_with_spaces_");
    await expect(
      converge({
        daemon,
        registry,
        providerFor: () => new StepProvider([]),
        projectRoot,
        maxRoundExtensions: -1,
      }),
    ).rejects.toThrow(/maxRoundExtensions/);
  });

  it("checkpoints after repeated identical blocking failures and bounds audit history", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: false } });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const reasons: string[] = [];

    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([() => ({ kind: "give_up", reason: "no change" })]),
      projectRoot,
      maxRounds: 5,
      maxStallRounds: 2,
      maxAuditEntries: 4,
      checkpoint: (context) => {
        reasons.push(context.reason);
        return "accept";
      },
    });

    expect(result.status).toBe("accepted");
    expect(result.rounds).toBe(2);
    expect(reasons).toEqual(["no_progress"]);
    expect(result.audit.length).toBeLessThanOrEqual(4);
    expect(result.audit.every((entry) => !("prompt" in entry))).toBe(true);
  });

  it("enforces the aggregate token ceiling and reports actual usage", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: false } });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);

    const result = await converge({
      daemon,
      registry,
      providerFor: () =>
        new StepProvider([
          () => ({
            kind: "give_up",
            reason: "still blocked",
            usage: { inputTokens: 7, outputTokens: 6 },
          }),
        ]),
      projectRoot,
      maxTokens: 10,
      maxRounds: 2,
    });

    expect(result.status).toBe("budget_exhausted");
    expect(result.tokens).toBe(13);
    expect(result.reasons.some((reason) => reason.includes("token cap"))).toBe(true);
  });

  it("enforces an aggregate provider-turn cap across rounds", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);

    const result = await converge({
      daemon,
      registry,
      providerFor: () =>
        new StepProvider([
          () => ({
            kind: "give_up",
            reason: "still blocked",
            usage: { inputTokens: 1, outputTokens: 1 },
          }),
          () => ({
            kind: "give_up",
            reason: "still blocked",
            usage: { inputTokens: 1, outputTokens: 1 },
          }),
        ]),
      projectRoot,
      maxTurns: 1,
      maxRounds: 3,
    });

    expect(result.status).toBe("budget_exhausted");
    expect(result.turns).toBe(1);
    expect(result.reasons.some((reason) => reason.includes("turn cap"))).toBe(true);
  });

  it("escalates when the initial gate snapshot is empty instead of reporting converged", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);

    const result = await converge({
      daemon,
      registry,
      providerFor: () => {
        throw new Error("provider must not be called with no gates");
      },
      projectRoot,
    });

    expect(result.status).toBe("escalated");
    expect(result.turns).toBe(0);
    expect(result.reasons.join("\n")).toContain("no gate results");
  });

  it("serializes transactions for overlapping scopes to avoid lock races", async () => {
    const daemon = new MutableDaemon({ "/board": {} });
    daemon.gates = [
      fail("gate:erc.no_unconnected", "ee-agent"),
      fail("gate:fw.qmk_compile", "fw-agent"),
    ];
    const registry = new TestRegistry([
      definition("ee-agent", ["/board"], ["erc.no_unconnected"]),
      definition("fw-agent", ["/board/nested"], ["fw.qmk_compile"]),
    ]);
    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([() => ({ kind: "give_up", reason: "blocked" })]),
      projectRoot,
      maxRounds: 1,
      rollback: "none",
    });
    expect(result.runs).toHaveLength(2);
    const acquireEvents = daemon.events.filter((event) => event.startsWith("lock:"));
    const releaseEvents = daemon.events.filter((event) => event.startsWith("unlock:"));
    expect(acquireEvents).toHaveLength(1);
    expect(releaseEvents).toHaveLength(1);
    expect(daemon.locks.size).toBe(0);
  });

  it("divides aggregate cost and token budgets across parallel agents", async () => {
    const daemon = new MutableDaemon({ "/electrical": {}, "/firmware": {} });
    daemon.gates = [
      fail("gate:erc.no_unconnected", "ee-agent"),
      fail("gate:fw.qmk_compile", "fw-agent"),
    ];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
      definition("fw-agent", ["/firmware"], ["fw.qmk_compile"]),
    ]);
    const result = await converge({
      daemon,
      registry,
      providerFor: () =>
        new StepProvider([
          (request) => ({
            kind: "give_up",
            reason: "blocked",
            usage: { costMinor: Math.min(4, request.remainingCostMinor), inputTokens: 4 },
          }),
        ]),
      projectRoot,
      maxCostMinor: 7,
      maxTokens: 9,
      maxRounds: 1,
    });

    expect(result.runs).toHaveLength(2);
    expect(result.costMinor).toBeLessThanOrEqual(7);
    expect(result.tokens).toBe(8);
    expect(daemon.locks.size).toBe(0);
  });

  it("waits for all parallel agents to release locks after abort", async () => {
    const daemon = new MutableDaemon({ "/electrical": {}, "/firmware": {} });
    daemon.gates = [
      fail("gate:erc.no_unconnected", "ee-agent"),
      fail("gate:fw.qmk_compile", "fw-agent"),
    ];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
      definition("fw-agent", ["/firmware"], ["fw.qmk_compile"]),
    ]);
    const controller = new AbortController();
    let providerCalls = 0;
    let arrivals = 0;
    let release!: () => void;
    const bothStarted = new Promise<void>((resolve) => {
      release = resolve;
    });

    const result = await converge({
      daemon,
      registry,
      providerFor: () =>
        new StepProvider([
          async () => {
            providerCalls += 1;
            arrivals += 1;
            if (arrivals === 2) release();
            await bothStarted;
            controller.abort();
            return { kind: "give_up", reason: "aborted" };
          },
        ]),
      projectRoot,
      signal: controller.signal,
      maxRounds: 1,
    });

    expect(result.status).toBe("aborted");
    expect(providerCalls).toBe(2);
    expect(daemon.locks.size).toBe(0);
  });

  it("maps every supported error value to a safe string", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    for (const value of [undefined, null, "plain failure", { code: "OFFLINE" }]) {
      const result = await converge({
        daemon,
        registry,
        providerFor: () => ({
          id: "throw",
          nextTurn: async () => {
            throw value;
          },
        }),
        projectRoot,
        maxRounds: 1,
      });
      expect(result.status).toBe("escalated");
      expect(result.reasons.length).toBeGreaterThan(0);
    }
  });

  it("validates all configured bounds", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [pass()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const base = { daemon, registry, providerFor: () => new StepProvider([]), projectRoot };
    await expect(converge({ ...base, maxRounds: 0 })).rejects.toThrow(/maxRounds/);
    await expect(converge({ ...base, maxCostMinor: -1 })).rejects.toThrow(/maxCostMinor/);
    await expect(converge({ ...base, maxTokens: -1 })).rejects.toThrow(/maxTokens/);
    await expect(converge({ ...base, maxStallRounds: 0 })).rejects.toThrow(/maxStallRounds/);
    await expect(converge({ ...base, maxRoundExtensions: -1 })).rejects.toThrow(
      /maxRoundExtensions/,
    );
    await expect(converge({ ...base, maxAuditEntries: 0 })).rejects.toThrow(/maxAuditEntries/);
  });

  it("routes unknown owner to an explicit unowned checkpoint report", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [fail("gate:unknown", null)];
    const registry = new TestRegistry([]);
    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([]),
      projectRoot,
      checkpoint: (context) => {
        expect(context.reason).toBe("unroutable");
        expect(context.failures[0]?.owner_agent).toBeNull();
        return "abort";
      },
    });
    expect(result.status).toBe("escalated");
  });

  it("exercises the accepted branch for every coordinator checkpoint reason", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [gate({ status: "ERROR", severity: "blocking", owner_agent: "ee-agent" })];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const errorAccepted = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([]),
      projectRoot,
      checkpoint: () => "accept",
    });
    expect(errorAccepted.status).toBe("accepted");

    daemon.gates = [fail()];
    const budgetAccepted = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([]),
      projectRoot,
      maxCostMinor: 0,
      checkpoint: () => "accept",
    });
    expect(budgetAccepted.status).toBe("accepted");

    daemon.gates = [fail("gate:unknown", null)];
    const unroutableAccepted = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([]),
      projectRoot,
      checkpoint: () => "accept",
    });
    expect(unroutableAccepted.status).toBe("accepted");
  });

  it("rejects non-integer or negative limits", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const base = { daemon, registry, providerFor: () => new StepProvider([]), projectRoot };
    await expect(converge({ ...base, maxCostMinor: -1 })).rejects.toThrow(/maxCostMinor/);
    await expect(converge({ ...base, maxTokens: 1.5 })).rejects.toThrow(/maxTokens/);
    await expect(converge({ ...base, maxStallRounds: 0 })).rejects.toThrow(/maxStallRounds/);
  });

  it("bounds max-round checkpoint extensions", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    let checkpoints = 0;
    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([() => ({ kind: "give_up", reason: "stuck" })]),
      projectRoot,
      maxRounds: 1,
      maxRoundExtensions: 1,
      checkpoint: () => {
        checkpoints += 1;
        return "continue";
      },
    });
    expect(result.status).toBe("escalated");
    expect(result.rounds).toBe(2);
    expect(checkpoints).toBe(3);
    expect(result.reasons.some((reason) => reason.includes("extensions"))).toBe(true);
  });

  it("rolls back on provider rejection when rollback policy is escalate", async () => {
    const original = { components: ["old"] };
    const daemon = new MutableDaemon({ "/electrical": original });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const result = await converge({
      daemon,
      registry,
      providerFor: () => ({
        id: "reject",
        nextTurn: async () => {
          throw new Error("network down");
        },
      }),
      projectRoot,
      maxRounds: 1,
      rollback: "escalate",
    });
    expect(result.status).toBe("escalated");
    expect(daemon.locks.size).toBe(0);
    expect(daemon.scopes.get("/electrical")?.value).toEqual(original);
  });

  it("returns aborted when cancellation occurs after the initial gate read", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const controller = new AbortController();
    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([]),
      projectRoot,
      signal: controller.signal,
      onEvent: (event) => {
        if (event.kind === "round.start") controller.abort();
      },
    });
    expect(result.status).toBe("aborted");
    expect(daemon.locks.size).toBe(0);
  });

  it("escalates cleanly when the daemon gate read fails", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.runGates = async () => {
      throw new Error("gate transport unavailable");
    };
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([]),
      projectRoot,
    });
    expect(result.status).toBe("escalated");
    expect(result.reasons.join(" ")).toContain("gate transport unavailable");
  });

  it("does not roll back when a transient conflict ends in RETRY", async () => {
    const daemon = new MutableDaemon({ "/electrical": { components: ["old"] } });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const events: ConvergeEvent[] = [];
    daemon.conflictAt = 2;
    const result = await converge({
      daemon,
      registry,
      providerFor: () =>
        new StepProvider([
          (request) => ({
            kind: "patch",
            proposal: {
              path: "/electrical",
              baseRev: request.scopeReads[0]?.rev ?? 1,
              ops: [{ op: "replace", path: "", value: { components: ["new"] } }],
            },
          }),
          () => ({ kind: "verify" }),
        ]),
      projectRoot,
      maxRounds: 1,
      maxVerifyRetries: 0,
      onEvent: (event) => events.push(event),
    });
    expect(result.status).toBe("escalated");
    expect(daemon.scopes.get("/electrical")?.value).toEqual({ components: ["old"] });
    expect(events.some((event) => event.kind === "rollback")).toBe(true);
  });

  it("keeps parallel lock cleanup awaited when one provider fails", async () => {
    const daemon = new MutableDaemon({ "/electrical": {}, "/firmware": {} });
    daemon.gates = [
      fail("gate:erc.no_unconnected", "ee-agent"),
      fail("gate:fw.qmk_compile", "fw-agent"),
    ];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
      definition("fw-agent", ["/firmware"], ["fw.qmk_compile"]),
    ]);
    const result = await converge({
      daemon,
      registry,
      providerFor: (agent) =>
        agent.id === "ee-agent"
          ? {
              id: "broken",
              nextTurn: async () => {
                throw new Error("provider offline");
              },
            }
          : new StepProvider([() => ({ kind: "give_up", reason: "blocked" })]),
      projectRoot,
      maxRounds: 1,
    });
    expect(result.status).toBe("escalated");
    expect(daemon.locks.size).toBe(0);
    expect(daemon.events.filter((event) => event.startsWith("unlock:"))).toHaveLength(2);
  });

  it("retains only the newest entries when the bounded audit rolls over", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([() => ({ kind: "give_up" })]),
      projectRoot,
      maxRounds: 1,
      maxAuditEntries: 2,
    });
    expect(result.audit).toHaveLength(2);
    expect(result.audit.at(-1)?.event).toBe("terminal");
  });

  it("does not swallow observer failures or leak them into the result", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [pass()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const result = await converge({
      daemon,
      registry,
      providerFor: () => new StepProvider([]),
      projectRoot,
      onEvent: () => {
        throw new Error("observer failure");
      },
    });
    expect(result.status).toBe("converged");
    expect(result.reasons).toEqual([]);
  });

  it("rolls back writes after an agent gives up", async () => {
    const original = { components: ["old"] };
    const daemon = new MutableDaemon({ "/electrical": original });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const events: ConvergeEvent[] = [];
    const result = await converge({
      daemon,
      registry,
      providerFor: () =>
        new StepProvider([
          (request) => ({
            kind: "patch",
            proposal: {
              path: "/electrical",
              baseRev: request.scopeReads[0]?.rev ?? 1,
              ops: [{ op: "replace", path: "", value: { components: ["new"] } }],
            },
          }),
          () => ({ kind: "give_up", reason: "cannot resolve" }),
        ]),
      projectRoot,
      maxRounds: 1,
      onEvent: (event) => events.push(event),
    });
    expect(result.status).toBe("escalated");
    expect(daemon.scopes.get("/electrical")?.value).toEqual(original);
    expect(events.some((event) => event.kind === "rollback")).toBe(true);
  });

  it("escalates honestly when a gate snapshot becomes empty mid-run", async () => {
    const daemon = new MutableDaemon({ "/electrical": {} });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);
    const result = await converge({
      daemon,
      registry,
      providerFor: () =>
        new StepProvider([
          () => {
            daemon.gates = [];
            return { kind: "verify" };
          },
        ]),
      projectRoot,
      maxRounds: 1,
    });
    expect(result.status).toBe("escalated");
    expect(result.failures).toEqual([]);
    expect(result.reasons.join("\n")).toContain("no gate results");
  });

  it("exposes a custom convergence predicate", async () => {
    const daemon = new MutableDaemon({ "/electrical": { ok: false } });
    daemon.gates = [fail()];
    const registry = new TestRegistry([
      definition("ee-agent", ["/electrical"], ["erc.no_unconnected"]),
    ]);

    const result = await converge({
      daemon,
      registry,
      providerFor: () => {
        throw new Error("provider must not be called");
      },
      projectRoot,
      isConverged: () => true,
    });

    expect(result.status).toBe("converged");
    expect(result.runs).toHaveLength(0);
  });
});
