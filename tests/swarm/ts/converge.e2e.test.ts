/**
 * Swarm convergence over a real `atomcd` process and real WebSocket RPC (WP-3.10).
 *
 * Unlike the WP-3.5 replay tests, these tests drive the real
 * `DaemonClientAdapter` against a spawned `atomcd serve` process. They prove the
 * transactional boundary end to end: the scripted provider patches IR through
 * real RPC, the daemon evaluates the fake plugin's gate on real state, and
 * `converge()` only reports success when the daemon's fresh gate snapshot says so.
 *
 * Three paths are covered:
 * 1. converge-to-PASS with a real gate result and an advanced IR revision;
 * 2. optimistic-conflict retry (a deliberately stale `base_rev` is rebased);
 * 3. abort-by-signal with lock cleanup (a follow-up `ir.lock` succeeds).
 *
 * Every test starts its own daemon and temp tree; `finally`/`afterEach` teardown
 * asserts the daemon process is dead and removes the tree. No fixed ports (the
 * harness binds an ephemeral loopback port), no network beyond loopback, no
 * vendor keys.
 */
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { DaemonClient } from "@atomc/daemon-client";
import {
  AGENT_DEFINITIONS,
  type AgentDefinition,
  AgentRegistry,
  type ConvergeResult,
  converge,
  DaemonClientAdapter,
  type ModelDecision,
  type ModelProvider,
  type ModelRequest,
} from "@atomc/swarm-harness";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { EMPTY_ELECTRICAL, FIX_NET } from "./fixtures/ir.js";
import { DaemonHarness } from "./harness.js";

/** The fake plugin's gate and the bearer-token-shaped string we expect redacted. */
const GATE_ID = "gate:swarm-e2e.ready";
const SECRET_RATIONALE = "fix the failing gate with Bearer sk-1234567890abcdef";

type Behavior = "happy" | "conflict" | "abort";

/**
 * Deterministic provider that reads the live IR rev out of the request and
 * returns a patch adding the missing net. The `conflict` behavior deliberately
 * answers the first turn with a stale `base_rev` to exercise the optimistic
 * conflict path; the `abort` behavior aborts the injected controller before the
 * gate can run.
 */
class ScriptedProvider implements ModelProvider {
  readonly id = "scripted";
  calls = 0;

  constructor(
    private readonly behavior: Behavior,
    private readonly controller?: AbortController,
  ) {}

  async nextTurn(request: ModelRequest): Promise<ModelDecision> {
    this.calls += 1;

    if (this.behavior === "abort") {
      this.controller?.abort();
      return { kind: "verify" };
    }

    const read = request.scopeReads.find((scope) => scope.path === "/electrical");
    const currentRev = read?.rev ?? 0;
    const nets = (read?.value as { nets?: unknown[] } | undefined)?.nets ?? [];
    const hasNet = Array.isArray(nets) && nets.length > 0;

    // First turn of the conflict case: stale base_rev so the daemon rejects it.
    if (this.behavior === "conflict" && this.calls === 1) {
      return {
        kind: "patch",
        proposal: {
          path: "/electrical",
          baseRev: 0,
          ops: [{ op: "add", path: "/nets/-", value: FIX_NET }],
          rationale: SECRET_RATIONALE,
        },
      };
    }

    if (!hasNet) {
      return {
        kind: "patch",
        proposal: {
          path: "/electrical",
          baseRev: currentRev,
          ops: [{ op: "add", path: "/nets/-", value: FIX_NET }],
          rationale: SECRET_RATIONALE,
        },
      };
    }

    return { kind: "verify" };
  }
}

/** Build a registry whose `ee-agent` owns only the fake swarm gate. */
function swarmRegistry(): AgentRegistry {
  const base = AGENT_DEFINITIONS["ee-agent"];
  const definition: AgentDefinition = {
    ...base,
    lockScopes: ["/electrical"],
    produces: ["/electrical"],
    gates: [GATE_ID],
  };
  return new AgentRegistry([definition]);
}

async function readTranscript(projectRoot: string, result: ConvergeResult): Promise<string> {
  const path = join(projectRoot, ".atomc", "sessions", result.runId, "ee-agent.jsonl");
  return readFile(path, "utf8");
}

describe("swarm convergence over real daemon + RPC", () => {
  let harness: DaemonHarness;
  let client: DaemonClient;
  let transcriptRoot: string;

  beforeEach(async () => {
    harness = await DaemonHarness.start();
    client = await harness.connect();
    transcriptRoot = await mkdtemp(join(tmpdir(), "atomc-swarm-transcripts-"));
    await client.transact({
      path: "/electrical",
      base_rev: 0,
      ops: [{ op: "add", path: "", value: EMPTY_ELECTRICAL }],
    });
  }, 300_000);

  afterEach(async () => {
    await harness.stop();
    await rm(transcriptRoot, { recursive: true, force: true }).catch(() => undefined);
    // Teardown assertion: the real daemon process must not be left running.
    await harness.assertProcessDead();
  });

  it("converges to PASS with a real daemon gate result and advances the IR", async () => {
    const adapter = new DaemonClientAdapter(client);
    const provider = new ScriptedProvider("happy");

    const result = await converge({
      daemon: adapter,
      registry: swarmRegistry(),
      providerFor: () => provider,
      gateIds: [GATE_ID],
      projectRoot: transcriptRoot,
      rollback: "none",
    });

    expect(result.status).toBe("converged");
    expect(result.gateResults).toHaveLength(1);
    expect(result.gateResults[0]?.id).toBe(GATE_ID);
    expect(result.gateResults[0]?.status).toBe("PASS");
    expect(result.failures).toHaveLength(0);

    // The daemon revision advanced because the provider applied a real patch.
    const electrical = await adapter.getIR("/electrical");
    expect(electrical.rev).toBeGreaterThan(1);
    const nets = (electrical.value as { nets: unknown[] }).nets;
    expect(nets).toHaveLength(1);

    // Locks were released: a follow-up lock attempt succeeds.
    const lock = await adapter.lock("/electrical", "test-holder", 60, "cleanup check");
    expect(typeof lock.expires_at).toBe("string");
    await adapter.unlock("/electrical", "test-holder");

    // The transcript carries no bearer/token material.
    const transcript = await readTranscript(transcriptRoot, result);
    expect(transcript).not.toContain("sk-1234567890abcdef");
    expect(transcript).toContain("[REDACTED]");
    const state = await harness.readState();
    expect(transcript).not.toContain(state?.token ?? "unused-token-should-not-appear");
  }, 300_000);

  it("recovers from an optimistic conflict and still converges", async () => {
    const adapter = new DaemonClientAdapter(client);
    const provider = new ScriptedProvider("conflict");

    const result = await converge({
      daemon: adapter,
      registry: swarmRegistry(),
      providerFor: () => provider,
      gateIds: [GATE_ID],
      projectRoot: transcriptRoot,
      rollback: "none",
    });

    expect(result.status).toBe("converged");
    // One stale attempt, one rebased patch, one verify.
    expect(provider.calls).toBeGreaterThanOrEqual(3);

    const electrical = await adapter.getIR("/electrical");
    expect(electrical.rev).toBeGreaterThan(1);

    const lock = await adapter.lock("/electrical", "test-holder", 60, "cleanup check");
    expect(typeof lock.expires_at).toBe("string");
    await adapter.unlock("/electrical", "test-holder");

    const transcript = await readTranscript(transcriptRoot, result);
    expect(transcript).toContain("patch.conflict");
    expect(transcript).not.toContain("sk-1234567890abcdef");
  }, 300_000);

  it("aborts on signal and releases locks", async () => {
    const adapter = new DaemonClientAdapter(client);
    const controller = new AbortController();
    const provider = new ScriptedProvider("abort", controller);

    const result = await converge({
      daemon: adapter,
      registry: swarmRegistry(),
      providerFor: () => provider,
      gateIds: [GATE_ID],
      projectRoot: transcriptRoot,
      signal: controller.signal,
      rollback: "none",
    });

    expect(result.status).toBe("aborted");
    expect(provider.calls).toBeGreaterThanOrEqual(1);

    // Aborting mid-run must not leak the agent's subtree lock.
    const lock = await adapter.lock("/electrical", "test-holder", 60, "cleanup check");
    expect(typeof lock.expires_at).toBe("string");
    await adapter.unlock("/electrical", "test-holder");
  }, 300_000);
});
