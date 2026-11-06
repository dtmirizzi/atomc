import {
  type Api,
  type AssistantMessage,
  type Context,
  completeSimple,
  type Model,
  type SimpleStreamOptions,
} from "@mariozechner/pi-ai";
import { describe, expect, it } from "vitest";
import {
  createPiAiProvider,
  DECISION_INSTRUCTIONS,
  DEFAULT_PI_AI_COMPLETE,
  decodeToolName,
  encodeToolName,
  extractJsonObject,
  type PiAiComplete,
  PiAiProvider,
  toModelDecision,
  toPiAiContext,
  toTurnUsage,
} from "../../src/index.js";
import type { ModelRequest, ToolDescriptor } from "../../src/types.js";

const model: Model<Api> = {
  id: "deepseek/deepseek-v4.1-flash",
  name: "DeepSeek V4.1 Flash",
  api: "openai-completions",
  provider: "openrouter",
  baseUrl: "https://openrouter.ai/api/v1",
  reasoning: true,
  input: ["text", "image"],
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
  contextWindow: 128_000,
  maxTokens: 8_192,
};

function assistant(
  content: AssistantMessage["content"],
  overrides: Partial<AssistantMessage> = {},
): AssistantMessage {
  return {
    role: "assistant",
    content,
    api: "openai-completions",
    provider: "openrouter",
    model: model.id,
    usage: {
      input: 0,
      output: 0,
      cacheRead: 0,
      cacheWrite: 0,
      totalTokens: 0,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
    },
    stopReason: "stop",
    timestamp: 0,
    ...overrides,
  };
}

function request(overrides: Partial<ModelRequest> = {}): ModelRequest {
  return {
    session: {
      id: "run:ee-agent",
      runId: "run",
      agentId: "ee-agent",
      holder: "agent:ee-agent#1",
      model: { provider: "openrouter", model: model.id },
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
    tools: [],
    turn: 0,
    remainingCostMinor: 100,
    ...overrides,
  };
}

const tool: ToolDescriptor = {
  plugin: "cad-jig",
  name: "render",
  description: "render the board",
  input_schema: { type: "object", properties: {} },
  mutates: false,
};

describe("pi-ai compile-level compatibility", () => {
  it("assigns pi-ai's completeSimple to the injected transport seam", () => {
    expect(DEFAULT_PI_AI_COMPLETE).toBe(completeSimple);
    expect(typeof DEFAULT_PI_AI_COMPLETE).toBe("function");
  });
});

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

describe("toPiAiContext", () => {
  it("includes the agent prompt, decision protocol and failure summary", () => {
    const context = toPiAiContext(request(), { systemPrompt: "You are ee-agent.", model });
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

  it("inlines attachments as image parts on the final user message", () => {
    const context = toPiAiContext(
      request({
        attachments: [{ kind: "image", mimeType: "image/png", data: "AAAA", name: "page" }],
      }),
      { systemPrompt: "s", model },
    );
    const last = context.messages.at(-1);
    expect(Array.isArray(last?.content)).toBe(true);
    if (Array.isArray(last?.content)) {
      expect(last.content[1]).toEqual({ type: "image", data: "AAAA", mimeType: "image/png" });
    }
  });

  it("maps tool descriptors with JSON-Schema parameters", () => {
    const context = toPiAiContext(request({ tools: [tool] }), { systemPrompt: "s", model });
    expect(context.tools?.[0]?.name).toBe("cad-jig__render");
    expect(context.tools?.[0]?.parameters).toMatchObject({ type: "object" });
  });

  it("omits the tools array when no tools are advertised", () => {
    const context = toPiAiContext(request({ tools: [] }), { systemPrompt: "s", model });
    expect(context.tools).toBeUndefined();
  });

  it("reconstructs prior tool turns as assistant/toolResult pairs", () => {
    const context = toPiAiContext(
      request({
        transcript: [
          {
            index: 3,
            kind: "tool",
            call: { plugin: "atopile", tool: "compile", args: { force: true } },
            result: { ok: true },
            at: "2026-11-04T00:00:00Z",
          },
          {
            index: 4,
            kind: "tool",
            call: { plugin: "cad-jig", tool: "render", args: {} },
            error: "boom",
            at: "2026-11-04T00:00:01Z",
          },
        ],
      }),
      { systemPrompt: "s", model },
    );
    const [call, result, call2, result2] = context.messages;
    expect(call?.role).toBe("assistant");
    expect(result).toMatchObject({ role: "toolResult", toolCallId: "call-3", isError: false });
    expect(call2?.role).toBe("assistant");
    expect(result2).toMatchObject({ role: "toolResult", toolCallId: "call-4", isError: true });
  });
});

describe("toTurnUsage", () => {
  it("maps tokens and converts USD to integer minor units", () => {
    expect(
      toTurnUsage({
        input: 10.9,
        output: 5,
        cacheRead: 0,
        cacheWrite: 0,
        totalTokens: 15,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0.0123 },
      }),
    ).toEqual({ inputTokens: 10, outputTokens: 5, costMinor: 1 });
  });

  it("guards missing and non-finite values", () => {
    expect(toTurnUsage(undefined)).toEqual({});
    const bad = assistant([], {
      usage: {
        input: Number.NaN,
        output: 0,
        cacheRead: 0,
        cacheWrite: 0,
        totalTokens: 0,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: Number.POSITIVE_INFINITY },
      },
    }).usage;
    expect(toTurnUsage(bad)).toEqual({ outputTokens: 0 });
  });
});

describe("extractJsonObject", () => {
  it("extracts the first JSON object from surrounding prose", () => {
    expect(extractJsonObject('here: {"kind":"verify"} thanks')).toEqual({ kind: "verify" });
  });

  it("throws when there is no object or invalid JSON", () => {
    expect(() => extractJsonObject("no json here")).toThrow(/did not contain/);
    expect(() => extractJsonObject("{not json}")).toThrow(/not valid JSON/);
  });
});

describe("toModelDecision", () => {
  it("maps a tool call", () => {
    const decision = toModelDecision(
      assistant([{ type: "toolCall", id: "1", name: "atopile__compile", arguments: { x: 1 } }], {
        stopReason: "toolUse",
        usage: {
          input: 1,
          output: 2,
          cacheRead: 0,
          cacheWrite: 0,
          totalTokens: 3,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
        },
      }),
    );
    expect(decision).toEqual({
      kind: "tool",
      tool: { plugin: "atopile", tool: "compile", args: { x: 1 } },
      usage: { inputTokens: 1, outputTokens: 2, costMinor: 0 },
    });
  });

  it("maps text decisions", () => {
    expect(toModelDecision(assistant([{ type: "text", text: '{"kind":"verify"}' }]))).toEqual({
      kind: "verify",
      usage: { inputTokens: 0, outputTokens: 0, costMinor: 0 },
    });
    const patch = toModelDecision(
      assistant([
        {
          type: "text",
          text: '{"kind":"patch","proposal":{"path":"/electrical","baseRev":7,"ops":[{"op":"remove","path":"/components/0"}],"rationale":"drop"}}',
        },
      ]),
    );
    expect(patch.kind).toBe("patch");
    expect(patch.proposal?.ops).toHaveLength(1);
    expect(toModelDecision(assistant([{ type: "text", text: '{"kind":"give_up"}' }])).kind).toBe(
      "give_up",
    );
    expect(
      toModelDecision(assistant([{ type: "text", text: '{"kind":"give_up","reason":"stuck"}' }]))
        .reason,
    ).toBe("stuck");
    expect(
      toModelDecision(
        assistant([{ type: "text", text: '{"kind":"tool","tool":{"plugin":"x","tool":"y"}}' }]),
      ).kind,
    ).toBe("tool");
  });

  it("throws on error/aborted stops and malformed output", () => {
    expect(() =>
      toModelDecision(assistant([], { stopReason: "error", errorMessage: "boom" })),
    ).toThrow("boom");
    expect(() => toModelDecision(assistant([], { stopReason: "aborted" }))).toThrow(/aborted/);
    expect(() =>
      toModelDecision(assistant([{ type: "toolCall", id: "1", name: "bad", arguments: {} }])),
    ).toThrow(/malformed tool name/);
    expect(() => toModelDecision(assistant([{ type: "text", text: '{"kind":"nope"}' }]))).toThrow(
      /unknown decision kind/,
    );
    expect(() => toModelDecision(assistant([{ type: "text", text: '{"kind":"patch"}' }]))).toThrow(
      /requires proposal/,
    );
    expect(() => toModelDecision(assistant([{ type: "text", text: '{"kind":"tool"}' }]))).toThrow(
      /requires tool/,
    );
    expect(() => toModelDecision(assistant([{ type: "text", text: '{"kind":5}' }]))).toThrow(
      /string `kind`/,
    );
  });
});

describe("PiAiProvider", () => {
  it("passes options through and returns a decision", async () => {
    const calls: Array<{
      model: unknown;
      context: Context;
      options: SimpleStreamOptions | undefined;
    }> = [];
    const complete: PiAiComplete = async (m, context, options) => {
      calls.push({ model: m, context, options });
      return assistant([{ type: "text", text: '{"kind":"verify"}' }], {
        usage: {
          input: 3,
          output: 4,
          cacheRead: 0,
          cacheWrite: 0,
          totalTokens: 7,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0.02 },
        },
      });
    };
    const provider = new PiAiProvider({
      systemPrompt: "You are ee-agent.",
      model,
      apiKey: "secret",
      temperature: 0.2,
      maxTokens: 512,
      reasoning: "medium",
      sessionId: "sess",
      complete,
    });
    expect(provider.id).toBe("pi-ai");
    expect(provider.hasApiKey).toBe(true);
    expect(provider.hasInjectedTransport).toBe(true);
    const decision = await provider.nextTurn(request());
    expect(decision).toEqual({
      kind: "verify",
      usage: { inputTokens: 3, outputTokens: 4, costMinor: 2 },
    });
    expect(calls[0]?.options).toMatchObject({
      apiKey: "secret",
      temperature: 0.2,
      maxTokens: 512,
      reasoning: "medium",
      sessionId: "sess",
    });
    expect(calls[0]?.context.tools).toBeUndefined();
    expect(calls[0]?.model).toBe(model);
  });

  it("forwards the request AbortSignal, falling back to the provider signal", async () => {
    const seen: Array<AbortSignal | undefined> = [];
    const complete: PiAiComplete = async (_m, _c, options) => {
      seen.push(options?.signal);
      return assistant([{ type: "text", text: '{"kind":"verify"}' }]);
    };
    const providerDefault = new AbortController();
    const provider = new PiAiProvider({
      systemPrompt: "s",
      model,
      signal: providerDefault.signal,
      complete,
    });
    const perRequest = new AbortController();
    await provider.nextTurn(request({ signal: perRequest.signal }));
    await provider.nextTurn(request());
    expect(seen[0]).toBe(perRequest.signal);
    expect(seen[1]).toBe(providerDefault.signal);
  });

  it("redacts the configured key from transport errors", async () => {
    const complete: PiAiComplete = async () => {
      throw new Error("auth failed for sk-live-123: invalid");
    };
    const provider = new PiAiProvider({
      systemPrompt: "s",
      model,
      apiKey: "sk-live-123",
      complete,
    });
    await expect(provider.nextTurn(request())).rejects.toThrow(
      "auth failed for [REDACTED]: invalid",
    );
    try {
      await provider.nextTurn(request());
    } catch (error) {
      expect((error as Error).message).not.toContain("sk-live-123");
    }
  });

  it("uses the default transport when none is injected", () => {
    const provider = new PiAiProvider({ systemPrompt: "s", model });
    expect(provider.hasInjectedTransport).toBe(false);
    expect(provider.hasApiKey).toBe(false);
  });
});

describe("createPiAiProvider factory", () => {
  it("reads the key from the injected environment only", () => {
    const complete: PiAiComplete = async () =>
      assistant([{ type: "text", text: '{"kind":"verify"}' }]);
    const config = {
      systemPrompt: "s",
      model,
      apiKeyEnv: "OPENROUTER_API_KEY",
      reasoning: "medium" as const,
    };
    const provider = createPiAiProvider(config, { env: { OPENROUTER_API_KEY: "k-1" }, complete });
    expect(provider.hasApiKey).toBe(true);
    expect(provider.hasInjectedTransport).toBe(true);
    // The config object is secret-free and safe to serialize.
    expect(JSON.stringify(config)).not.toContain("k-1");
    const noKey = createPiAiProvider(config, { env: {}, complete });
    expect(noKey.hasApiKey).toBe(false);
  });

  it("supports a custom id and omits unset options", () => {
    const provider = createPiAiProvider(
      { id: "openrouter", systemPrompt: "s", model },
      { env: {}, complete: async () => assistant([]) },
    );
    expect(provider.id).toBe("openrouter");
  });
});
