import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { redactEntry, redactText, redactValue, TranscriptWriter } from "../src/transcript.js";

describe("transcript redaction", () => {
  it("redacts sensitive keys and token-shaped strings", () => {
    const redacted = redactEntry({
      token: "super-secret",
      nested: { authorization: "Bearer abc.def.ghi", note: "ok" },
      message: "call with Bearer abcdefghijklmnop",
    }) as Record<string, unknown>;

    expect(redacted.token).toBe("[REDACTED]");
    expect((redacted.nested as Record<string, unknown>).authorization).toBe("[REDACTED]");
    expect(String(redacted.message)).not.toContain("abcdefghijklmnop");

    expect(redactText("x sk-abcdefgh12345 y")).toBe("x [REDACTED] y");
    expect(redactValue(["api_key", "visible"], [], new WeakSet())).toEqual(["api_key", "visible"]);
  });

  it("handles circular references without throwing", () => {
    const value: Record<string, unknown> = { name: "a" };
    value.self = value;
    const redacted = redactValue(value, [], new WeakSet()) as Record<string, unknown>;
    expect(redacted.self).toBe("[Circular]");
  });
});

describe("TranscriptWriter", () => {
  it("writes redacted JSONL under .atomc/sessions/<run>/<agent>.jsonl", async () => {
    const root = await mkdtemp(join(tmpdir(), "swarm-tx-"));
    const writer = new TranscriptWriter({ projectRoot: root, runId: "r1", agentId: "ee-agent" });
    await writer.append({ kind: "meta", token: "abc", note: "hello" });

    expect(writer.path).toBe(join(root, ".atomc", "sessions", "r1", "ee-agent.jsonl"));
    const contents = await readFile(writer.path, "utf8");
    expect(contents).toContain("[REDACTED]");
    expect(contents).not.toContain("abc");
    expect(contents.trim().split("\n")).toHaveLength(1);
  });

  it("rotates when the file exceeds maxBytes", async () => {
    const root = await mkdtemp(join(tmpdir(), "swarm-tx-rot-"));
    const writer = new TranscriptWriter({
      projectRoot: root,
      runId: "r2",
      agentId: "fw-agent",
      maxBytes: 10,
    });
    await writer.append({ a: "0123456789" });
    await writer.append({ b: "abcdefghij" });

    const current = await readFile(writer.path, "utf8");
    const rotated = await readFile(`${writer.path}.1`, "utf8");
    expect(current).toContain('"b"');
    expect(rotated).toContain('"a"');
  });
});
