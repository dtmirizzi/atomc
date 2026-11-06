/**
 * Integration test: convergence over the real WP-3.3 agent registry (WP-3.4 seam).
 *
 * Proves the two branches compose without glue code: `AgentRegistry` satisfies
 * `ConvergenceRegistry` structurally, and the contract agent definitions route
 * real gate ids to the right specialist. The daemon is the WP-3.5
 * `FixtureDaemon` and the provider is scripted — no sockets, keys or models.
 */
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { AgentRegistry } from "../src/agents/index.js";
import { converge } from "../src/converge.js";
import type { ModelDecision, ModelProvider, ModelRequest } from "../src/types.js";
import { FixtureDaemon } from "./fixtures/fixture-daemon.js";
import { failGate, makeTempRoot, passGate } from "./fixtures/support.js";

const GATE_ID = "gate:erc.no_unconnected";

let projectRoot: string;

beforeAll(() => {
  projectRoot = makeTempRoot("atomc-converge-integration-");
});

afterAll(async () => {
  await import("node:fs/promises").then((fs) => fs.rm(projectRoot, { recursive: true }));
});

type Step = (request: ModelRequest) => ModelDecision;

class ScriptedProvider implements ModelProvider {
  readonly id = "scripted";
  readonly #steps: Step[];

  constructor(steps: readonly Step[]) {
    this.#steps = [...steps];
  }

  async nextTurn(request: ModelRequest): Promise<ModelDecision> {
    const step = this.#steps.shift();
    if (step === undefined) {
      return { kind: "give_up", reason: "script exhausted", usage: {} };
    }
    return step(request);
  }
}

describe("converge + AgentRegistry integration", () => {
  it("routes a contract gate to the real ee-agent definition and converges", async () => {
    const registry = new AgentRegistry();
    const daemon = new FixtureDaemon({
      rev: 10,
      gates: [[failGate(GATE_ID)], [passGate(GATE_ID)]],
    });

    const result = await converge({
      daemon,
      registry,
      providerFor: (definition) => {
        expect(definition.id).toBe("ee-agent");
        expect(definition.lockScopes).toContain("/electrical");
        return new ScriptedProvider([
          (request) => ({
            kind: "patch",
            proposal: {
              path: "/electrical",
              baseRev: request.scopeReads.find((read) => read.path === "/electrical")?.rev ?? 10,
              ops: [{ op: "replace", path: "", value: { components: [] } }],
            },
          }),
          () => ({ kind: "verify" }),
        ]);
      },
      projectRoot,
      maxRounds: 2,
    });

    expect(result.status).toBe("converged");
    expect(result.rounds).toBe(1);
    expect(result.runs).toHaveLength(1);
    expect(result.runs[0]?.session.agentId).toBe("ee-agent");
    expect(result.failures).toEqual([]);
    expect(result.gateResults.map((gate) => gate.status)).toEqual(["PASS"]);
    // The transactional loop ran: read, lock, patch, DAG, gates, unlock.
    expect(daemon.transactCalls).toBe(1);
    expect(daemon.lockOrder).toContain("/electrical");
    expect(daemon.events.filter((event) => event.startsWith("runDAG")).length).toBeGreaterThan(0);
  });

  it("escalates unroutable gates instead of waking a specialist", async () => {
    const registry = new AgentRegistry();
    const daemon = new FixtureDaemon({
      gates: [[failGate("gate:no.such_gate", { owner_agent: null })]],
    });

    const result = await converge({
      daemon,
      registry,
      providerFor: () => {
        throw new Error("provider must not be called for an unroutable gate");
      },
      projectRoot,
      maxRounds: 2,
    });

    expect(result.status).toBe("escalated");
    expect(result.runs).toHaveLength(0);
    expect(result.reasons.join("\n")).toContain("no.such_gate");
  });

  it("satisfies the structural ConvergenceRegistry contract via agentsForGate", () => {
    const registry = new AgentRegistry();
    const owners = registry.agentsForGate("bom.cost_under_budget");
    expect(owners.map((definition) => definition.id).sort()).toEqual(["ee-agent", "ops-agent"]);
    expect(registry.get("fw-agent")?.lockScopes).toContain("/firmware");
    expect(registry.get("nope" as never)).toBeUndefined();
  });
});
