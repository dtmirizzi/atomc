import { describe, expect, it } from "vitest";
import {
  DECISION_INSTRUCTIONS,
  decodeToolName,
  encodeToolName,
  extractJsonObject,
  type PiAiAssistantMessage,
  type PiAiContext,
  PiAiProvider,
  toModelDecision,
  toPiAiContext,
  toPiAiTool,
  toTurnUsage,
} from "../src/index.js";
import type { ModelRequest, ToolDescriptor } from "../src/types.js";

function request(overrides: Partial<ModelRequest> = {}): ModelRequest {
  return {
    session: {
      id: "run:ee-agent",
      runId: "run",
      agentId: "ee-agent",
      holder: "agent:ee-agent#1",
      model: { provider: "openrouter", model: "deepseek/deepseek-v4-flash" },
      startedAt: "2026-11-04T00:00:00Z",
    },
    failure: {
      id: "gate:erc.no_unconnected",
      status: "FAIL",
      severity: "blocking",
      owner_agent: "ee-agent",
      ir_rev: 7,
      summary: "2 unconnected pins",
      refs: ["comp:U1", "net:3V3"],
    },
    scopeReads: [{ path: "/electrical", rev: 7, value: { components: [] } }],
    transcript: [],
    tools: [
      {
        plugin: "atopile",
        name: "compile",
        description: "compile the design",
        input_schema: { type: "object", properties: {} },
        mutates: true,
      },
    ],
    turn: 0,
    remainingCostMinor: 100,
    ...overrides,
  };
}

const tool: ToolDescriptor = {
  plugin: "cad-jig",
  name: "render",
  description: "render the board",
  input_schema: { type: "object" },
  mutates: false,
};

describe("tool name encoding", () => {
  it("round-trips plugin and tool", () => {
    expect(encodeToolName("atopile", "compile")).toBe("atopile__compile");
    expect(decodeToolName("atopile__compile")).toEqual({ plugin: "atopile", tool: "compile" });
  });

  it("rejects malformed names", () => {
    expect(decodeToolName("compile")).toBeUndefined();
    expect(decodeToolName("__x")).toBeUndefined();
    expect(decodeToolName("x__")).toBeUndefined();
  });
});

describe("toPiAiTool", () => {
  it("maps the descriptor to the pi-ai shape", () => {
    expect(toPiAiTool(tool)).toEqual({
      name: "cad-jig__render",
      description: "render the board",
      parameters: { type: "object" },
    });
  });
});

describe("toPiAiContext", () => {
  it("includes the agent prompt, decision protocol and failure summary", () => {
    const context = toPiAiContext(request(), { systemPrompt: "You are ee-agent." });
    expect(context.systemPrompt).toContain("You are ee-agent.");
    expect(context.systemPrompt).toContain(DECISION_INSTRUCTIONS);
    const first = context.messages[0];
    expect(first?.role).toBe("user");
    const text = Array.isArray(first?.content) ? first.content[0] : undefined;
    expect(text).toMatchObject({ type: "text" });
    if (text?.type === "text") {
      expect(text.text).toContain("gate:erc.no_unconnected");
      expect(text.text).toContain("/electrical (rev 7)");
    }
  });

  it("inlines attachments as image parts", () => {
    const context = toPiAiContext(
      request({
        attachments: [{ kind: "image", mimeType: "image/png", data: "AAAA", name: "page" }],
      }),
      { systemPrompt: "s" },
    );
    const content = context.messages[0]?.content;
    expect(Array.isArray(content)).toBe(true);
    if (Array.isArray(content)) {
      expect(content[1]).toEqual({ type: "image", data: "AAAA", mimeType: "image/png" });
    }
  });

  it("omits the tools array when no tools are advertised", () => {
    const context = toPiAiContext(request({ tools: [] }), { systemPrompt: "s" });
    expect(context.tools).toBeUndefined();
  });
});

describe("toTurnUsage", () => {
  it("maps tokens and converts USD to integer minor units", () => {
    expect(toTurnUsage({ input: 10.9, output: 5, cost: { total: 0.0123 } })).toEqual({
      inputTokens: 10,
      outputTokens: 5,
      costMinor: 1,
    });
  });

  it("guards missing and non-finite values", () => {
    expect(toTurnUsage(undefined)).toEqual({});
    expect(toTurnUsage({ input: Number.NaN, cost: { total: Number.POSITIVE_INFINITY } })).toEqual(
      {},
    );
    expect(toTurnUsage({ input: -3 })).toEqual({ inputTokens: 0 });
  });
});

describe("extractJsonObject", () => {
  it("extracts the first JSON object from surrounding prose", () => {
    expect(extractJsonObject('here: {"kind":"verify"} thanks')).toEqual({ kind: "verify" });
  });

  it("throws when there is no object", () => {
    expect(() => extractJsonObject("no json here")).toThrow(/did not contain/);
  });

  it("throws on invalid JSON", () => {
    expect(() => extractJsonObject("{not json}")).toThrow(/not valid JSON/);
  });
});

describe("toModelDecision", () => {
  it("maps a tool call", () => {
    const decision = toModelDecision({
      content: [{ type: "toolCall", id: "1", name: "atopile__compile", arguments: { x: 1 } }],
      stopReason: "toolUse",
      usage: { input: 1, output: 2 },
    });
    expect(decision).toEqual({
      kind: "tool",
      tool: { plugin: "atopile", tool: "compile", args: { x: 1 } },
      usage: { inputTokens: 1, outputTokens: 2 },
    });
  });

  it("maps a verify JSON decision", () => {
    expect(
      toModelDecision({
        content: [{ type: "text", text: '{"kind":"verify"}' }],
        stopReason: "stop",
      }),
    ).toEqual({ kind: "verify", usage: {} });
  });

  it("maps a patch decision", () => {
    const decision = toModelDecision({
      content: [
        {
          type: "text",
          text: '{"kind":"patch","proposal":{"path":"/electrical","baseRev":7,"ops":[{"op":"remove","path":"/components/0"}],"rationale":"drop dangling"}}',
        },
      ],
      stopReason: "stop",
    });
    expect(decision.kind).toBe("patch");
    expect(decision.proposal).toMatchObject({ path: "/electrical", baseRev: 7 });
    expect(decision.proposal?.ops).toHaveLength(1);
  });

  it("maps a give_up decision with and without a reason", () => {
    expect(
      toModelDecision({
        content: [{ type: "text", text: '{"kind":"give_up","reason":"stuck"}' }],
        stopReason: "stop",
      }),
    ).toMatchObject({ kind: "give_up", reason: "stuck" });
    expect(
      toModelDecision({
        content: [{ type: "text", text: '{"kind":"give_up"}' }],
        stopReason: "stop",
      }),
    ).toMatchObject({ kind: "give_up" });
  });

  it("throws on error/aborted stops", () => {
    expect(() =>
      toModelDecision({ content: [], stopReason: "error", errorMessage: "boom" }),
    ).toThrow("boom");
    expect(() => toModelDecision({ content: [], stopReason: "aborted" })).toThrow(/aborted/);
  });

  it("throws on malformed names, kinds and proposals", () => {
    expect(() =>
      toModelDecision({
        content: [{ type: "toolCall", id: "1", name: "bad", arguments: {} }],
        stopReason: "toolUse",
      }),
    ).toThrow(/malformed tool name/);
    expect(() =>
      toModelDecision({ content: [{ type: "text", text: '{"kind":"nope"}' }], stopReason: "stop" }),
    ).toThrow(/unknown decision kind/);
    expect(() =>
      toModelDecision({
        content: [{ type: "text", text: '{"kind":"patch"}' }],
        stopReason: "stop",
      }),
    ).toThrow(/requires proposal/);
    expect(() =>
      toModelDecision({
        content: [{ type: "text", text: '{"kind":"tool"}' }],
        stopReason: "stop",
      }),
    ).toThrow(/requires tool/);
    expect(() =>
      toModelDecision({ content: [{ type: "text", text: '{"kind":5}' }], stopReason: "stop" }),
    ).toThrow(/string `kind`/);
  });
});

describe("PiAiProvider", () => {
  it("passes options through and returns a decision", async () => {
    const calls: Array<{ model: unknown; context: PiAiContext; options?: unknown }> = [];
    const message: PiAiAssistantMessage = {
      content: [{ type: "text", text: '{"kind":"verify"}' }],
      stopReason: "stop",
      usage: { input: 3, output: 4, cost: { total: 0.02 } },
    };
    const provider = new PiAiProvider({
      systemPrompt: "You are ee-agent.",
      model: { id: "fake-model" },
      apiKey: "secret",
      temperature: 0.2,
      maxTokens: 512,
      reasoning: "medium",
      sessionId: "sess",
      complete: async (model, context, options) => {
        calls.push({ model, context, options });
        return message;
      },
    });
    expect(provider.id).toBe("pi-ai");
    const decision = await provider.nextTurn(request());
    expect(decision).toEqual({
      kind: "verify",
      usage: { inputTokens: 3, outputTokens: 4, costMinor: 2 },
    });
    expect(calls).toHaveLength(1);
    expect(calls[0]?.options).toMatchObject({
      apiKey: "secret",
      temperature: 0.2,
      maxTokens: 512,
      reasoning: "medium",
      sessionId: "sess",
    });
    expect(calls[0]?.context.tools?.[0]?.name).toBe("atopile__compile");
  });

  it("omits unset options and supports a custom provider id", async () => {
    const seen: Array<unknown> = [];
    const provider = new PiAiProvider({
      id: "openrouter",
      systemPrompt: "s",
      model: {},
      complete: async (_model, _context, options) => {
        seen.push(options);
        return { content: [{ type: "text", text: '{"kind":"give_up"}' }], stopReason: "stop" };
      },
    });
    expect(provider.id).toBe("openrouter");
    await provider.nextTurn(request({ tools: [] }));
    expect(seen[0]).toEqual({});
  });
});
