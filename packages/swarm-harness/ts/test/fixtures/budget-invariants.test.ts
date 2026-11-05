/**
 * WP-3.5: bounded budget/turn invariants for the WP-3.2 `runAgent` loop.
 *
 * A small deterministic PRNG (mulberry32) generates decision scripts and budget
 * caps; the loop must always terminate inside its caps, release every lock, and
 * reproduce exactly on a second run. This is a bounded, seeded property test —
 * no wall-clock or load-sensitive assertions.
 */
import { rmSync } from "node:fs";
import { afterAll, describe, expect, it } from "vitest";
import { runAgent } from "../../src/runner.js";
import type { ModelDecision, RunOutcome } from "../../src/types.js";
import { FixtureDaemon } from "./fixture-daemon.js";
import { createReplayProvider, type RecordedSession } from "./recordings.js";
import { definitionFor, makeTempRoot, passGate, toolDescriptor } from "./support.js";

/** Deterministic 32-bit PRNG; same seed ⇒ same sequence on every platform. */
function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface BudgetCase {
  seed: number;
  maxTurns: number;
  maxCostMinor: number;
  decisions: ModelDecision[];
}

function makeCase(seed: number): BudgetCase {
  const random = mulberry32(seed);
  const maxTurns = Math.floor(random() * 7); // 0..6
  const maxCostMinor = Math.floor(random() * 51); // 0..50
  const turnCount = Math.floor(random() * 7) + 1; // 1..7
  const decisions: ModelDecision[] = [];
  for (let index = 0; index < turnCount; index += 1) {
    const costMinor = Math.floor(random() * 21); // 0..20
    if (index === turnCount - 1) {
      decisions.push({ kind: "verify", usage: { costMinor } });
    } else {
      decisions.push({
        kind: "tool",
        tool: { plugin: "test", tool: "ping", args: {} },
        usage: { costMinor },
      });
    }
  }
  return { seed, maxTurns, maxCostMinor, decisions };
}

const CASES = Array.from({ length: 48 }, (_value, index) => makeCase(index + 1));
const tempRoot = makeTempRoot("atomc-wp35-prop-");
afterAll(() => rmSync(tempRoot, { recursive: true, force: true }));

function sessionFor(testCase: BudgetCase): RecordedSession {
  return {
    schema_version: 1,
    id: `prop-${testCase.seed}`,
    description: "generated budget invariant case",
    agent: "ee-agent",
    model: { provider: "fake", model: "recorded-1" },
    failure: {
      id: "gate:erc.no_unconnected",
      status: "FAIL",
      severity: "blocking",
      owner_agent: "ee-agent",
      ir_rev: 10,
      summary: "generated",
      refs: [],
    },
    turns: testCase.decisions.map((decision, index) => ({ turn: index, decision })),
  };
}

async function runCase(testCase: BudgetCase): Promise<{
  outcome: RunOutcome;
  turns: number;
  costMinor: number;
  consumed: number;
  locksReleased: boolean;
  gateStatuses: string[];
  tokens: number;
}> {
  const session = sessionFor(testCase);
  const daemon = new FixtureDaemon({
    rev: 10,
    gates: [[passGate("gate:erc.no_unconnected")]],
    tools: [toolDescriptor("test", "ping")],
  });
  const provider = createReplayProvider(session);
  const result = await runAgent({
    definition: definitionFor(session, {
      permittedTools: ["test:*"],
      budget: { maxTurns: testCase.maxTurns, maxCostMinor: testCase.maxCostMinor },
    }),
    failure: session.failure,
    daemon,
    provider,
    projectRoot: tempRoot,
    runId: `prop-${testCase.seed}`,
  });
  return {
    outcome: result.outcome,
    turns: result.turns,
    costMinor: result.costMinor,
    consumed: provider.consumed,
    locksReleased: daemon.locksReleased,
    gateStatuses: result.gateResults.map((gate) => gate.status),
    tokens: result.tokens,
  };
}

const OUTCOMES: readonly RunOutcome[] = ["PASS", "RETRY", "ESCALATE", "ABORTED"];

describe("bounded budget invariants", () => {
  it("terminates inside the turn/cost caps and always releases locks", async () => {
    for (const testCase of CASES) {
      const outcome = await runCase(testCase);

      expect(OUTCOMES).toContain(outcome.outcome);
      expect(outcome.turns).toBeLessThanOrEqual(testCase.maxTurns);
      expect(outcome.consumed).toBe(outcome.turns);
      expect(outcome.locksReleased).toBe(true);

      const consumedCost = testCase.decisions
        .slice(0, outcome.turns)
        .reduce((sum, decision) => sum + (decision.usage?.costMinor ?? 0), 0);
      expect(outcome.costMinor).toBe(consumedCost);
      // At most one turn's cost may cross the cap before escalation.
      expect(outcome.costMinor).toBeLessThanOrEqual(testCase.maxCostMinor + 20);

      if (outcome.outcome === "PASS") {
        expect(outcome.turns).toBeGreaterThan(0);
        expect(outcome.gateStatuses.every((status) => status === "PASS")).toBe(true);
      }
      if (outcome.costMinor >= testCase.maxCostMinor && outcome.turns < testCase.maxTurns) {
        expect(outcome.outcome).toBe("ESCALATE");
      }
    }
  });

  it("replays each case deterministically", async () => {
    for (const testCase of CASES.slice(0, 12)) {
      const first = await runCase(testCase);
      const second = await runCase(testCase);
      expect(second).toEqual(first);
    }
  });

  it("never turns negative costs into unbounded spend", async () => {
    const testCase: BudgetCase = {
      seed: 999,
      maxTurns: 8,
      maxCostMinor: 10,
      decisions: [
        {
          kind: "tool",
          tool: { plugin: "test", tool: "ping", args: {} },
          usage: { costMinor: -50 },
        },
        { kind: "verify", usage: { costMinor: -100 } },
      ],
    };
    const outcome = await runCase(testCase);
    expect(outcome.costMinor).toBe(0);
    expect(outcome.tokens).toBe(0);
    expect(outcome.outcome).toBe("PASS");
  });
});
