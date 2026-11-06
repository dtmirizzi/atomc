/** WP-3.5: recording schema validation, redaction and deterministic replay. */
import { describe, expect, it } from "vitest";
import type { ModelRequest } from "../../src/types.js";
import {
  canonicalJson,
  createReplayProvider,
  isJsonPatchOp,
  loadRecordingsFromDir,
  parseRecording,
  RECORDING_SCHEMA_VERSION,
  RecordingValidationError,
  redactRecording,
  serializeRecording,
  validateRecording,
} from "./recordings.js";
import { assertDefined, loadFixture, SESSIONS_DIR } from "./support.js";

function request(turn: number): ModelRequest {
  return {
    session: {
      id: "run:ee-agent",
      runId: "run",
      agentId: "ee-agent",
      holder: "agent:ee-agent#1",
      model: { provider: "fake", model: "recorded-1" },
      startedAt: "2026-11-04T23:00:00Z",
    },
    failure: {
      id: "gate:erc.no_unconnected",
      status: "FAIL",
      severity: "blocking",
      owner_agent: "ee-agent",
      ir_rev: 10,
      summary: "x",
      refs: [],
    },
    scopeReads: [],
    transcript: [],
    tools: [],
    turn,
    remainingCostMinor: 100,
  };
}

describe("recording fixtures", () => {
  it("loads and validates every committed fixture", () => {
    const recordings = loadRecordingsFromDir(SESSIONS_DIR);
    expect(recordings.map((entry) => entry.session.id).sort()).toEqual([
      "ee-erc-pass",
      "ee-gate-retry-pass",
      "fw-tool-verify",
      "mech-conflict-retry",
      "ops-budget-escalate",
    ]);
    for (const { session } of recordings) {
      expect(session.schema_version).toBe(RECORDING_SCHEMA_VERSION);
      expect(session.turns.length).toBeGreaterThan(0);
      expect(session.turns.map((turn) => turn.turn)).toEqual(
        session.turns.map((_turn, index) => index),
      );
    }
  });

  it("rejects recordings with a stale or missing schema version", () => {
    const session = loadFixture("ee-erc-pass");
    expect(validateRecording({ ...session, schema_version: 0 }).ok).toBe(false);
    const { schema_version: _drop, ...withoutVersion } = session;
    expect(validateRecording(withoutVersion).ok).toBe(false);
  });

  it("rejects patch and tool decisions that omit their payload", () => {
    const session = loadFixture("ee-erc-pass");
    const patchless = structuredClone(session);
    assertDefined(patchless.turns[0]).decision = { kind: "patch" };
    expect(validateRecording(patchless).ok).toBe(false);

    const toolless = structuredClone(session);
    assertDefined(toolless.turns[0]).decision = { kind: "tool" };
    expect(validateRecording(toolless).ok).toBe(false);
  });

  it("rejects unknown agents and malformed patch ops", () => {
    const session = loadFixture("ee-erc-pass");
    expect(validateRecording({ ...session, agent: "qa-agent" }).ok).toBe(false);

    const badOp = structuredClone(session);
    assertDefined(badOp.turns[0]).decision = {
      kind: "patch",
      proposal: { path: "/electrical", baseRev: 10, ops: [{ op: "explode", path: "/x" } as never] },
    };
    expect(validateRecording(badOp).ok).toBe(false);
  });

  it("throws a typed error with the fixture id", () => {
    const session = loadFixture("ee-erc-pass");
    expect(() => parseRecording({ ...session, id: "Not Kebab" })).toThrow(RecordingValidationError);
  });
});

describe("JSON Patch op guard", () => {
  it("accepts valid ops and rejects malformed ones", () => {
    expect(isJsonPatchOp({ op: "add", path: "/a", value: 1 })).toBe(true);
    expect(isJsonPatchOp({ op: "remove", path: "/a" })).toBe(true);
    expect(isJsonPatchOp({ op: "move", from: "/a", path: "/b" })).toBe(true);
    expect(isJsonPatchOp({ op: "add", path: "/a" })).toBe(false);
    expect(isJsonPatchOp({ op: "remove" })).toBe(false);
    expect(isJsonPatchOp({ op: "move", path: "/b" })).toBe(false);
    expect(isJsonPatchOp("nope")).toBe(false);
  });
});

describe("redaction and canonical serialization", () => {
  it("scrubs sensitive keys and bearer tokens defensively", () => {
    const redacted = redactRecording({
      api_key: "sk-live-abcdef1234567890",
      note: "use Bearer abc.def.ghi to call the daemon",
      nested: { authorization: "Bearer zzz" },
    }) as Record<string, unknown>;
    expect(redacted.api_key).toBe("[REDACTED]");
    expect(redacted.nested).toEqual({ authorization: "[REDACTED]" });
    expect(String(redacted.note)).not.toContain("abc.def.ghi");
    expect(String(redacted.note)).toContain("[REDACTED]");
  });

  it("serializes deterministically with sorted keys and a trailing newline", () => {
    const session = loadFixture("ee-erc-pass");
    const serialized = serializeRecording(session);
    expect(serialized.endsWith("\n")).toBe(true);
    expect(serialized).toBe(canonicalJson(JSON.parse(serialized)));
    expect(serialized.indexOf('"agent"')).toBeLessThan(serialized.indexOf('"description"'));
    expect(JSON.parse(serialized)).toEqual(session);
  });
});

describe("ReplayProvider", () => {
  it("replays every recorded decision in order and reports progress", async () => {
    const session = loadFixture("ee-erc-pass");
    const provider = createReplayProvider(session);
    expect(provider.remaining).toBe(2);

    const first = await provider.nextTurn(request(0));
    expect(first).toEqual(assertDefined(session.turns[0]).decision);
    expect(provider.consumed).toBe(1);
    expect(provider.remaining).toBe(1);

    const second = await provider.nextTurn(request(1));
    expect(second).toEqual(assertDefined(session.turns[1]).decision);
    expect(provider.consumed).toBe(2);
    expect(provider.remaining).toBe(0);
  });

  it("deep-clones decisions so callers cannot mutate the fixture", async () => {
    const session = loadFixture("ee-erc-pass");
    const provider = createReplayProvider(session);
    const first = (await provider.nextTurn(request(0))) as { kind: string };
    first.kind = "give_up";
    const second = await provider.nextTurn(request(1));
    expect(second.kind).toBe("verify");
    expect(session.turns[0]?.decision.kind).toBe("patch");
  });

  it("fails loudly on a turn mismatch", async () => {
    const provider = createReplayProvider(loadFixture("ee-erc-pass"));
    await expect(provider.nextTurn(request(5))).rejects.toThrow(/turn mismatch/);
  });

  it("gives up deterministically once the recording is exhausted", async () => {
    const provider = createReplayProvider(loadFixture("ee-erc-pass"));
    await provider.nextTurn(request(0));
    await provider.nextTurn(request(1));
    const exhausted = await provider.nextTurn(request(2));
    expect(exhausted).toEqual({ kind: "give_up", reason: "recording exhausted" });
  });

  it("tolerates turn mismatches when explicitly configured", async () => {
    const provider = createReplayProvider(loadFixture("ee-erc-pass"), {
      tolerateTurnMismatch: true,
    });
    const decision = await provider.nextTurn(request(7));
    expect(decision.kind).toBe("patch");
  });
});
