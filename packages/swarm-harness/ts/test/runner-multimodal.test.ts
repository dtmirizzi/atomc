import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { runAgent } from "../src/runner.js";
import type { ModelAttachment, ToolDescriptor } from "../src/types.js";
import { definition, FakeDaemon, FakeProvider, failure, gate } from "./fakes.js";

const ATTACHMENT: ModelAttachment = {
  kind: "image",
  mimeType: "image/png",
  data: "AAAA",
  ref: "art:render",
};

const inspectionTool: ToolDescriptor = {
  plugin: "harness",
  name: "inspect_render",
  description: "load a render",
  input_schema: {
    type: "object",
    properties: { path: { type: "string" } },
    required: ["path"],
    additionalProperties: false,
  },
  mutates: false,
};

class AttachmentDaemon extends FakeDaemon {
  override async callTool(plugin: string, tool: string): Promise<{ result: unknown }> {
    this.toolCalls += 1;
    this.events.push(`callTool:${plugin}:${tool}`);
    return { result: ATTACHMENT };
  }
}

async function projectRoot(): Promise<string> {
  return mkdtemp(join(tmpdir(), "swarm-multimodal-"));
}

describe("runAgent — multimodal plumbing", () => {
  it("forwards the AbortSignal and accumulates tool turns plus inspection images", async () => {
    const daemon = new AttachmentDaemon();
    daemon.tools = [inspectionTool];
    daemon.gateResults = [gate()];
    const provider = new FakeProvider([
      {
        kind: "tool",
        tool: { plugin: "harness", tool: "inspect_render", args: { path: "r.png" } },
      },
      { kind: "verify" },
    ]);
    const controller = new AbortController();
    const result = await runAgent({
      definition: definition({
        permittedTools: ["harness:inspect_render"],
        gates: ["erc.no_unconnected"],
      }),
      failure,
      daemon,
      provider,
      signal: controller.signal,
      projectRoot: await projectRoot(),
      runId: "multimodal-run",
    });

    expect(result.outcome).toBe("PASS");
    expect(daemon.toolCalls).toBe(1);
    // First turn has no prior transcript/attachments; second turn carries both.
    expect(provider.requests[0]?.transcript).toHaveLength(0);
    expect(provider.requests[0]?.attachments).toHaveLength(0);
    expect(provider.requests[1]?.transcript).toHaveLength(1);
    expect(provider.requests[1]?.transcript[0]?.call).toEqual({
      plugin: "harness",
      tool: "inspect_render",
      args: { path: "r.png" },
    });
    expect(provider.requests[1]?.attachments).toEqual([ATTACHMENT]);
    expect(provider.requests[1]?.signal).toBe(controller.signal);
  });

  it("records rejected tool calls in the transcript without a daemon call", async () => {
    const daemon = new FakeDaemon();
    daemon.tools = [inspectionTool];
    daemon.gateResults = [gate()];
    const provider = new FakeProvider([
      {
        kind: "tool",
        tool: { plugin: "harness", tool: "inspect_render", args: { path: "r.png" } },
      },
      { kind: "verify" },
    ]);
    await runAgent({
      definition: definition({ permittedTools: [], gates: ["erc.no_unconnected"] }),
      failure,
      daemon,
      provider,
      projectRoot: await projectRoot(),
      runId: "multimodal-rejected",
    });
    expect(provider.requests[1]?.transcript[0]?.error).toContain("not permitted");
    expect(daemon.toolCalls).toBe(0);
  });
});
