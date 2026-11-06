/**
 * WP-3.5 end-to-end replay tests.
 *
 * These drive the real `runAgent` transactional loop (WP-3.2) through the
 * `HarnessDaemon` port with a deterministic fixture daemon and recorded provider
 * decisions. No daemon process, socket, LLM, API key or unmerged WP-3.3/3.4 code
 * is involved.
 */
import { rmSync } from "node:fs";
import { afterAll, describe, expect, it } from "vitest";
import { type RunAgentOptions, runAgent } from "../../src/runner.js";
import type { AgentDefinition, SwarmEvent } from "../../src/types.js";
import { FixtureDaemon } from "./fixture-daemon.js";
import { createReplayProvider, type RecordedSession } from "./recordings.js";
import { buildSessionReport, formatSessionReport } from "./report.js";
import {
  assertDefined,
  definitionFor,
  failGate,
  loadFixture,
  makeTempRoot,
  passGate,
  toolDescriptor,
} from "./support.js";

const roots: string[] = [];
function tempRoot(): string {
  const root = makeTempRoot();
  roots.push(root);
  return root;
}
afterAll(() => {
  for (const root of roots) rmSync(root, { recursive: true, force: true });
});

const fixedNow = (): Date => new Date("2026-11-04T23:00:00.000Z");

async function runReplay(
  session: RecordedSession,
  daemon: FixtureDaemon,
  options: Partial<Omit<RunAgentOptions, "definition">> & {
    definition?: Partial<AgentDefinition>;
  } = {},
): Promise<{
  result: Awaited<ReturnType<typeof runAgent>>;
  events: SwarmEvent[];
  provider: ReturnType<typeof createReplayProvider>;
}> {
  const { definition: definitionOverride, ...rest } = options;
  const events: SwarmEvent[] = [];
  const provider = createReplayProvider(session);
  const result = await runAgent({
    definition: definitionFor(session, definitionOverride),
    failure: session.failure,
    daemon,
    provider,
    projectRoot: tempRoot(),
    runId: `wp35-${session.id}`,
    now: fixedNow,
    onEvent: (event) => events.push(event),
    ...rest,
  });
  return { result, events, provider };
}

describe("replay end-to-end", () => {
  it("applies a patched fix, verifies through the DAG, and passes", async () => {
    const session = loadFixture("ee-erc-pass");
    const daemon = new FixtureDaemon({
      rev: 10,
      gates: [[passGate("gate:erc.no_unconnected")]],
    });
    const { result, events, provider } = await runReplay(session, daemon);

    expect(result.outcome).toBe("PASS");
    expect(result.state).toBe("DONE");
    expect(provider.consumed).toBe(session.turns.length);
    expect(daemon.transactCalls).toBe(1);
    expect(daemon.dagCalls).toEqual([undefined]);
    expect(daemon.gateCalls).toEqual([["erc.no_unconnected"]]);
    expect(daemon.locksReleased).toBe(true);

    const report = buildSessionReport({ result, events, decisions: provider.decisionsMade });
    expect(report.patchPaths).toEqual(["/electrical"]);
    expect(report.gates).toEqual([
      { id: "gate:erc.no_unconnected", status: "PASS", severity: "blocking" },
    ]);
    expect(report.locksAcquired).toEqual(["/electrical", "/layout", "/keyboard"]);
    expect(report.locksReleased).toEqual(["/keyboard", "/layout", "/electrical"]);
  });

  it("routes an allow-listed tool call through the daemon and then verifies", async () => {
    const session = loadFixture("fw-tool-verify");
    const daemon = new FixtureDaemon({
      rev: 10,
      gates: [[passGate("gate:fw.qmk_compile", { owner_agent: "fw-agent" })]],
      tools: [toolDescriptor("qmk", "compile")],
    });
    const { result, events, provider } = await runReplay(session, daemon);

    expect(result.outcome).toBe("PASS");
    expect(daemon.toolCalls).toHaveLength(1);
    const call = assertDefined(daemon.toolCalls[0]);
    expect(call.plugin).toBe("qmk");
    expect(call.tool).toBe("compile");
    expect(daemon.locksReleased).toBe(true);

    const report = buildSessionReport({ result, events, decisions: provider.decisionsMade });
    expect(report.toolCalls).toEqual([{ plugin: "qmk", tool: "compile", rejected: false }]);
  });

  it("re-reads on an optimistic conflict and passes without a blind resend", async () => {
    const session = loadFixture("mech-conflict-retry");
    const daemon = new FixtureDaemon({
      rev: 11,
      gates: [[passGate("gate:mech.plate_switch_cutouts_14mm", { owner_agent: "mech-agent" })]],
    });
    const { result, events, provider } = await runReplay(session, daemon);

    expect(result.outcome).toBe("PASS");
    expect(daemon.transactCalls).toBe(1);
    expect(provider.consumed).toBe(3);
    expect(daemon.locksReleased).toBe(true);

    const report = buildSessionReport({ result, events, decisions: provider.decisionsMade });
    expect(report.conflicts).toBe(1);
    expect(report.patchPaths).toEqual(["/mechanical"]);
  });

  it("retries once after a blocking gate failure and passes on the next verify", async () => {
    const session = loadFixture("ee-gate-retry-pass");
    const daemon = new FixtureDaemon({
      rev: 10,
      gates: [[failGate("gate:erc.no_unconnected")], [passGate("gate:erc.no_unconnected")]],
    });
    const { result, events } = await runReplay(session, daemon, { maxVerifyRetries: 1 });

    expect(result.outcome).toBe("PASS");
    expect(result.turns).toBe(2);
    const report = buildSessionReport({ result, events });
    expect(report.gates.map((gate) => gate.status)).toEqual(["FAIL", "PASS"]);
    expect(daemon.locksReleased).toBe(true);
  });

  it("escalates and releases locks when the cost budget is crossed", async () => {
    const session = loadFixture("ops-budget-escalate");
    const daemon = new FixtureDaemon({ rev: 10 });
    const { result, events } = await runReplay(session, daemon, {
      definition: { budget: { maxTurns: 8, maxCostMinor: 100 } },
    });

    expect(result.outcome).toBe("ESCALATE");
    expect(result.reason).toMatch(/cost budget/);
    expect(result.costMinor).toBe(500);
    expect(result.turns).toBe(1);
    expect(daemon.locksReleased).toBe(true);
    expect(buildSessionReport({ result, events }).conflicts).toBe(0);
  });

  it("escalates on lock contention and releases whatever it already held", async () => {
    const session = loadFixture("ee-erc-pass");
    const daemon = new FixtureDaemon({ rev: 10, lockConflicts: ["/layout"] });
    const { result, events } = await runReplay(session, daemon);

    expect(result.outcome).toBe("ESCALATE");
    expect(result.reason).toMatch(/could not lock \/layout/);
    expect(daemon.locksReleased).toBe(true);
    expect(buildSessionReport({ result, events }).conflicts).toBeGreaterThan(0);
  });

  it("aborts cleanly before touching the daemon", async () => {
    const session = loadFixture("ee-erc-pass");
    const daemon = new FixtureDaemon({ rev: 10 });
    const controller = new AbortController();
    controller.abort();
    const { result, events } = await runReplay(session, daemon, { signal: controller.signal });

    expect(result.outcome).toBe("ABORTED");
    expect(daemon.transactCalls).toBe(0);
    expect(daemon.locksReleased).toBe(true);
    expect(buildSessionReport({ result, events }).statePath.at(-1)).toBe("RELEASE->ABORTED");
  });

  it("is deterministic: identical inputs produce an identical report", async () => {
    const session = loadFixture("ee-erc-pass");
    const runOnce = async (): Promise<string> => {
      const daemon = new FixtureDaemon({ rev: 10, gates: [[passGate("gate:erc.no_unconnected")]] });
      const { result, events, provider } = await runReplay(session, daemon);
      return formatSessionReport(
        buildSessionReport({ result, events, decisions: provider.decisionsMade }),
      );
    };
    expect(await runOnce()).toBe(await runOnce());
  });
});
