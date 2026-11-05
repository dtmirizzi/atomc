/**
 * `ModelProvider` adapter for `@mariozechner/pi-ai` v0.73.x.
 *
 * This is a real adapter: it imports the frozen pi-ai API (`completeSimple`,
 * `getModel`, `Type`, `Context`, `AssistantMessage`) and exposes a safe factory
 * seam so credentials, transport and environment never appear in an
 * `AgentDefinition` or a browser URL.
 *
 * Integration:
 * ```ts
 * import { completeSimple, getModel } from "@mariozechner/pi-ai";
 * import { createPiAiProvider } from "@atomc/swarm-harness";
 *
 * const base = getModel("openrouter", "deepseek/deepseek-v4-flash");
 * const model = { ...base, id: "deepseek/deepseek-v4.1-flash" };
 * const provider = createPiAiProvider(
 *   { systemPrompt, model, apiKeyEnv: "OPENROUTER_API_KEY", reasoning: "medium" },
 *   { env: process.env, complete: completeSimple },
 * );
 * ```
 *
 * Tests inject a mock `complete` and never touch the network.
 */
import type { JsonPatchOp } from "@atomc/core-ir";
import {
  type Api,
  type AssistantMessage,
  type Context,
  completeSimple,
  type Message,
  type Model,
  type SimpleStreamOptions,
  type Tool,
  Type,
  type Usage,
} from "@mariozechner/pi-ai";
import type {
  ModelAttachment,
  ModelDecision,
  ModelProvider,
  ModelRequest,
  ToolDescriptor,
  TurnUsage,
} from "../types.js";

/** The injected completion function, structurally `pi-ai`'s `completeSimple`. */
export type PiAiComplete = (
  model: Model<Api>,
  context: Context,
  options?: SimpleStreamOptions,
) => Promise<AssistantMessage>;

/** Construction options for {@link PiAiProvider}. */
export interface PiAiProviderOptions {
  /** Provider id surfaced on `ModelProvider.id` (default `"pi-ai"`). */
  id?: string;
  /** The owning agent's system prompt. */
  systemPrompt: string;
  /** Resolved pi-ai model object (from `getModel(...)` or a plain `Model`). */
  model: Model<Api>;
  /** Completion transport; defaults to pi-ai's `completeSimple`. */
  complete?: PiAiComplete;
  /** Absolute API key. Prefer {@link PiAiProviderConfig.apiKeyEnv} for env-sourced keys. */
  apiKey?: string;
  temperature?: number;
  maxTokens?: number;
  reasoning?: SimpleStreamOptions["reasoning"];
  sessionId?: string;
  /** Default cancellation signal; a per-request `signal` takes precedence. */
  signal?: AbortSignal;
}

/** Declarative, secret-free provider configuration for the factory seam. */
export interface PiAiProviderConfig {
  id?: string;
  systemPrompt: string;
  model: Model<Api>;
  /** Name of an environment variable holding the key (never the key itself). */
  apiKeyEnv?: string;
  temperature?: number;
  maxTokens?: number;
  reasoning?: SimpleStreamOptions["reasoning"];
  sessionId?: string;
  signal?: AbortSignal;
}

/** Injected dependencies for {@link createPiAiProvider}. */
export interface PiAiProviderDeps {
  /** Environment map; defaults to `process.env` when available. */
  env?: Record<string, string | undefined>;
  /** Transport override (tests inject a mock; defaults to `completeSimple`). */
  complete?: PiAiComplete;
}

/**
 * Instructions appended to the agent system prompt describing the JSON decision
 * protocol used when the model does not call a tool directly.
 */
export const DECISION_INSTRUCTIONS = `
Decision protocol:
- If you need to run a tool, emit a tool call. Never describe a tool call in prose.
- To change the IR, finish your turn with a single JSON object and no markdown
  fences:
  {"kind":"patch","proposal":{"path":"/electrical","baseRev":12,"ops":[{"op":"replace","path":"/components/0/mpn","value":"..."}],"rationale":"..."}}
- To ask the harness to run the owned gates, finish with: {"kind":"verify"}
- If you cannot make progress, finish with: {"kind":"give_up","reason":"..."}
Never claim the gates pass yourself; only {"kind":"verify"} can end a run.
`.trim();

const SECRET_PLACEHOLDER = "[REDACTED]";

function defaultEnv(): Record<string, string | undefined> {
  const proc = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process;
  return proc?.env ?? {};
}

/** Compile-level compatibility check: pi-ai's `completeSimple` fits our seam. */
export const DEFAULT_PI_AI_COMPLETE: PiAiComplete = completeSimple;

/** pnpm/pi-ai tool name encoding: `"<plugin>__<tool>"`. */
export function encodeToolName(plugin: string, tool: string): string {
  return `${plugin}__${tool}`;
}

/** Inverse of {@link encodeToolName}; returns `undefined` for a malformed name. */
export function decodeToolName(name: string): { plugin: string; tool: string } | undefined {
  const separator = name.indexOf("__");
  if (separator <= 0 || separator >= name.length - 2) return undefined;
  return { plugin: name.slice(0, separator), tool: name.slice(separator + 2) };
}

function zeroUsage(): Usage {
  return {
    input: 0,
    output: 0,
    cacheRead: 0,
    cacheWrite: 0,
    totalTokens: 0,
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
  };
}

function safeJson(value: unknown): string {
  try {
    const text = JSON.stringify(value);
    return text === undefined ? "null" : text;
  } catch {
    return "[unserializable]";
  }
}

function summarize(request: ModelRequest): string {
  const lines: string[] = [
    `Gate failure ${request.failure.id} [${request.failure.status}/${request.failure.severity}] ` +
      `at IR rev ${request.failure.ir_rev}`,
    `Summary: ${request.failure.summary}`,
  ];
  if (request.failure.refs.length > 0) lines.push(`Refs: ${request.failure.refs.join(", ")}`);
  lines.push("", "Current IR under your scopes:");
  for (const read of request.scopeReads) {
    lines.push(`- ${read.path} (rev ${read.rev}): ${safeJson(read.value)}`);
  }
  return lines.join("\n");
}

function toPiAiTool(descriptor: ToolDescriptor): Tool {
  return {
    name: encodeToolName(descriptor.plugin, descriptor.name),
    description: descriptor.description,
    parameters: Type.Unsafe(descriptor.input_schema as never),
  };
}

/** Reconstruct prior tool turns as well-formed pi-ai assistant/toolResult pairs. */
function transcriptMessages(request: ModelRequest, model: Model<Api>): Message[] {
  const messages: Message[] = [];
  for (const turn of request.transcript) {
    const callId = `call-${turn.index}`;
    const toolName = encodeToolName(turn.call.plugin, turn.call.tool);
    messages.push({
      role: "assistant",
      api: model.api,
      provider: model.provider,
      model: model.id,
      content: [
        {
          type: "toolCall",
          id: callId,
          name: toolName,
          arguments: (turn.call.args ?? {}) as Record<string, unknown>,
        },
      ],
      usage: zeroUsage(),
      stopReason: "toolUse",
      timestamp: Date.now(),
    });
    messages.push({
      role: "toolResult",
      toolCallId: callId,
      toolName,
      content: [{ type: "text", text: turn.error ?? safeJson(turn.result) }],
      isError: turn.error !== undefined,
      timestamp: Date.now(),
    });
  }
  return messages;
}

/**
 * Translate a harness {@link ModelRequest} into a pi-ai `Context`.
 *
 * Pure (given a clock-free model object) and exported so it can be unit tested
 * against the real pi-ai types without a live call.
 */
export function toPiAiContext(
  request: ModelRequest,
  options: { systemPrompt: string; model: Model<Api> },
): Context {
  const messages: Message[] = transcriptMessages(request, options.model);
  const content: Array<
    { type: "text"; text: string } | { type: "image"; data: string; mimeType: string }
  > = [{ type: "text", text: summarize(request) }];
  for (const attachment of request.attachments ?? []) content.push(attachmentPart(attachment));
  messages.push({ role: "user", content, timestamp: Date.now() });
  const context: Context = {
    systemPrompt: `${options.systemPrompt}\n\n${DECISION_INSTRUCTIONS}`,
    messages,
  };
  if (request.tools.length > 0) {
    context.tools = request.tools.map((descriptor) => toPiAiTool(descriptor));
  }
  return context;
}

function attachmentPart(attachment: ModelAttachment): {
  type: "image";
  data: string;
  mimeType: string;
} {
  return { type: "image", data: attachment.data, mimeType: attachment.mimeType };
}

/** Convert pi-ai usage into integer-USD-minor harness accounting. */
export function toTurnUsage(usage: Usage | undefined): TurnUsage {
  const count = (value: number | undefined): number | undefined =>
    value === undefined || !Number.isFinite(value) ? undefined : Math.max(0, Math.floor(value));
  const minor = usage?.cost?.total;
  const result: TurnUsage = {};
  const input = count(usage?.input);
  const output = count(usage?.output);
  if (input !== undefined) result.inputTokens = input;
  if (output !== undefined) result.outputTokens = output;
  if (minor !== undefined && Number.isFinite(minor)) {
    result.costMinor = Math.max(0, Math.round(minor * 100));
  }
  return result;
}

/** Extract the first parsable JSON object from a text blob. */
export function extractJsonObject(text: string): unknown {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start < 0 || end <= start) {
    throw new Error("model response did not contain a JSON decision object");
  }
  try {
    return JSON.parse(text.slice(start, end + 1));
  } catch (error) {
    throw new Error(`model decision was not valid JSON: ${(error as Error).message}`);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** Convert a pi-ai assistant message into a harness {@link ModelDecision}. */
export function toModelDecision(message: AssistantMessage): ModelDecision {
  if (message.stopReason === "error" || message.stopReason === "aborted") {
    throw new Error(message.errorMessage ?? `model stopped with reason ${message.stopReason}`);
  }
  const usage = toTurnUsage(message.usage);
  const call = message.content.find((part) => part.type === "toolCall");
  if (call !== undefined && call.type === "toolCall") {
    const decoded = decodeToolName(call.name);
    if (decoded === undefined) {
      throw new Error(`model returned a malformed tool name "${call.name}"`);
    }
    return {
      kind: "tool",
      tool: { plugin: decoded.plugin, tool: decoded.tool, args: call.arguments },
      usage,
    };
  }
  const text = message.content
    .filter((part): part is { type: "text"; text: string } => part.type === "text")
    .map((part) => part.text)
    .join("\n");
  const decision = extractJsonObject(text);
  if (!isRecord(decision) || typeof decision.kind !== "string") {
    throw new Error("model decision is missing a string `kind`");
  }
  return toDecisionFromJson(decision, usage);
}

function toDecisionFromJson(record: Record<string, unknown>, usage: TurnUsage): ModelDecision {
  switch (record.kind) {
    case "verify":
      return { kind: "verify", usage };
    case "give_up": {
      const reason = typeof record.reason === "string" ? record.reason : undefined;
      return reason === undefined ? { kind: "give_up", usage } : { kind: "give_up", reason, usage };
    }
    case "patch": {
      const proposal = record.proposal;
      if (
        !isRecord(proposal) ||
        typeof proposal.path !== "string" ||
        typeof proposal.baseRev !== "number" ||
        !Array.isArray(proposal.ops)
      ) {
        throw new Error("`patch` decision requires proposal {path, baseRev, ops}");
      }
      const rationale = typeof proposal.rationale === "string" ? proposal.rationale : undefined;
      return {
        kind: "patch",
        proposal: {
          path: proposal.path,
          baseRev: proposal.baseRev,
          ops: proposal.ops as JsonPatchOp[],
          ...(rationale !== undefined ? { rationale } : {}),
        },
        usage,
      };
    }
    case "tool": {
      const tool = record.tool;
      if (!isRecord(tool) || typeof tool.plugin !== "string" || typeof tool.tool !== "string") {
        throw new Error("`tool` decision requires tool {plugin, tool, args}");
      }
      return {
        kind: "tool",
        tool: { plugin: tool.plugin, tool: tool.tool, args: tool.args },
        usage,
      };
    }
    default:
      throw new Error(`unknown decision kind "${record.kind}"`);
  }
}

/** `ModelProvider` that drives a pi-ai model for one agent. */
export class PiAiProvider implements ModelProvider {
  readonly id: string;
  readonly #options: PiAiProviderOptions;
  readonly #apiKey: string | undefined;
  readonly #complete: PiAiComplete;

  constructor(options: PiAiProviderOptions, apiKey?: string) {
    this.id = options.id ?? "pi-ai";
    this.#options = options;
    this.#apiKey = options.apiKey ?? apiKey;
    this.#complete = options.complete ?? DEFAULT_PI_AI_COMPLETE;
  }

  /** True when an API key is configured; used by `doctor`, never printed. */
  get hasApiKey(): boolean {
    return this.#apiKey !== undefined && this.#apiKey.length > 0;
  }

  /** True when an explicit transport was injected (tests); never exposes it. */
  get hasInjectedTransport(): boolean {
    return this.#options.complete !== undefined;
  }

  async nextTurn(request: ModelRequest): Promise<ModelDecision> {
    const context = toPiAiContext(request, {
      systemPrompt: this.#options.systemPrompt,
      model: this.#options.model,
    });
    const options: SimpleStreamOptions = {};
    if (this.#apiKey !== undefined) options.apiKey = this.#apiKey;
    if (this.#options.temperature !== undefined) options.temperature = this.#options.temperature;
    if (this.#options.maxTokens !== undefined) options.maxTokens = this.#options.maxTokens;
    if (this.#options.reasoning !== undefined) options.reasoning = this.#options.reasoning;
    if (this.#options.sessionId !== undefined) options.sessionId = this.#options.sessionId;
    const signal = request.signal ?? this.#options.signal;
    if (signal !== undefined) options.signal = signal;
    try {
      const message = await this.#complete(this.#options.model, context, options);
      return toModelDecision(message);
    } catch (error) {
      throw new Error(this.#redact(error instanceof Error ? error.message : String(error)));
    }
  }

  /** Remove the configured key (if any) from an error before it reaches logs. */
  #redact(message: string): string {
    if (this.#apiKey === undefined || this.#apiKey.length === 0) return message;
    return message.split(this.#apiKey).join(SECRET_PLACEHOLDER);
  }
}

/**
 * Build a {@link PiAiProvider} from a secret-free config plus injected env and
 * transport. The key is read from `env[config.apiKeyEnv]` and is never stored on
 * the config object or an `AgentDefinition`.
 */
export function createPiAiProvider(
  config: PiAiProviderConfig,
  deps: PiAiProviderDeps = {},
): PiAiProvider {
  const env = deps.env ?? defaultEnv();
  const apiKey = config.apiKeyEnv === undefined ? undefined : env[config.apiKeyEnv];
  const options: PiAiProviderOptions = {
    systemPrompt: config.systemPrompt,
    model: config.model,
  };
  if (config.id !== undefined) options.id = config.id;
  if (config.temperature !== undefined) options.temperature = config.temperature;
  if (config.maxTokens !== undefined) options.maxTokens = config.maxTokens;
  if (config.reasoning !== undefined) options.reasoning = config.reasoning;
  if (config.sessionId !== undefined) options.sessionId = config.sessionId;
  if (config.signal !== undefined) options.signal = config.signal;
  if (deps.complete !== undefined) options.complete = deps.complete;
  return new PiAiProvider(options, apiKey);
}
