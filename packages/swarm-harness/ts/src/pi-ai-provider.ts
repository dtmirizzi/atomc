/**
 * `ModelProvider` adapter for `@mariozechner/pi-ai`.
 *
 * This module depends on a narrow, structural port rather than importing the
 * pi-ai package. Integrators wire the real functions in one place:
 *
 * ```ts
 * import { completeSimple, getModel } from "@mariozechner/pi-ai";
 * const provider = new PiAiProvider({
 *   systemPrompt: definition.systemPrompt,
 *   model: getModel("openrouter", "deepseek/deepseek-v4-flash"),
 *   complete: completeSimple,
 *   apiKey: process.env.OPENROUTER_API_KEY,
 *   reasoning: "medium",
 * });
 * ```
 *
 * Keeping the dependency at the edge means the harness stays installable without
 * any vendor SDK and deterministic tests inject a fake `complete`. The real
 * function is never called in tests.
 */
import type { JsonPatchOp } from "@atomc/core-ir";
import type {
  ModelAttachment,
  ModelDecision,
  ModelProvider,
  ModelRequest,
  ToolDescriptor,
  TurnUsage,
} from "./types.js";

/** Minimal image content part (pi-ai `ImageContent`). */
export interface PiAiImageContent {
  type: "image";
  data: string;
  mimeType: string;
}

/** Minimal text content part (pi-ai `TextContent`). */
export interface PiAiTextContent {
  type: "text";
  text: string;
}

/** Minimal tool-call content part (pi-ai `ToolCall`). */
export interface PiAiToolCall {
  type: "toolCall";
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

/** Any other content part the provider may return; ignored on decode. */
export interface PiAiUnknownContent {
  type: string;
  [key: string]: unknown;
}

/** Usage subset used for budget accounting (pi-ai `Usage`). */
export interface PiAiUsage {
  input?: number;
  output?: number;
  totalTokens?: number;
  cost?: { total?: number };
}

/** Minimal assistant message (pi-ai `AssistantMessage`). */
export interface PiAiAssistantMessage {
  content: ReadonlyArray<PiAiTextContent | PiAiImageContent | PiAiToolCall | PiAiUnknownContent>;
  stopReason: string;
  errorMessage?: string;
  usage?: PiAiUsage;
}

/** Minimal message shape (pi-ai `Message`). */
export interface PiAiMessage {
  role: "user" | "assistant" | "toolResult";
  content: string | ReadonlyArray<PiAiTextContent | PiAiImageContent>;
  timestamp?: number;
  toolCallId?: string;
  toolName?: string;
  isError?: boolean;
}

/** Minimal tool definition (pi-ai `Tool` with a JSON-Schema shaped parameter). */
export interface PiAiTool {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

/** Minimal completion context (pi-ai `Context`). */
export interface PiAiContext {
  systemPrompt?: string;
  messages: PiAiMessage[];
  tools?: PiAiTool[];
}

/** Completion options passed through to the provider (pi-ai `SimpleStreamOptions`). */
export interface PiAiCompleteOptions {
  apiKey?: string;
  temperature?: number;
  maxTokens?: number;
  signal?: AbortSignal;
  reasoning?: string;
  sessionId?: string;
}

/** The injected completion function, compatible with pi-ai `completeSimple`. */
export type PiAiComplete = (
  model: unknown,
  context: PiAiContext,
  options?: PiAiCompleteOptions,
) => Promise<PiAiAssistantMessage>;

/** Construction options for {@link PiAiProvider}. */
export interface PiAiProviderOptions {
  /** Provider id surfaced on `ModelProvider.id` (default `"pi-ai"`). */
  id?: string;
  /** The owning agent's system prompt. */
  systemPrompt: string;
  /** Resolved pi-ai model object (from `getModel(...)`), passed through verbatim. */
  model: unknown;
  /** pi-ai `completeSimple` (or a compatible function). */
  complete: PiAiComplete;
  apiKey?: string;
  temperature?: number;
  maxTokens?: number;
  /** pi-ai thinking level, e.g. `"medium"`. */
  reasoning?: string;
  /** Optional session id for providers with session-based caching. */
  sessionId?: string;
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

function attachmentPart(attachment: ModelAttachment): PiAiImageContent {
  return { type: "image", data: attachment.data, mimeType: attachment.mimeType };
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

function safeJson(value: unknown): string {
  try {
    const text = JSON.stringify(value);
    return text === undefined ? "null" : text;
  } catch {
    return "[unserializable]";
  }
}

/**
 * Translate a harness {@link ModelRequest} into a pi-ai `Context`.
 *
 * Pure and exported so it can be tested without importing the vendor SDK.
 */
export function toPiAiContext(
  request: ModelRequest,
  options: { systemPrompt: string },
): PiAiContext {
  const content: Array<PiAiTextContent | PiAiImageContent> = [
    { type: "text", text: summarize(request) },
  ];
  for (const attachment of request.attachments ?? []) content.push(attachmentPart(attachment));
  const messages: PiAiMessage[] = [{ role: "user", content }];
  const context: PiAiContext = {
    systemPrompt: `${options.systemPrompt}\n\n${DECISION_INSTRUCTIONS}`,
    messages,
  };
  if (request.tools.length > 0) {
    context.tools = request.tools.map(toPiAiTool);
  }
  return context;
}

/** Map a harness tool descriptor to a pi-ai tool definition. */
export function toPiAiTool(descriptor: ToolDescriptor): PiAiTool {
  return {
    name: encodeToolName(descriptor.plugin, descriptor.name),
    description: descriptor.description,
    parameters: descriptor.input_schema,
  };
}

/** Convert pi-ai usage into integer-USD-minor harness accounting. */
export function toTurnUsage(usage: PiAiUsage | undefined): TurnUsage {
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

/** Extract the first balanced/parsable JSON object from a text blob. */
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
export function toModelDecision(message: PiAiAssistantMessage): ModelDecision {
  if (message.stopReason === "error" || message.stopReason === "aborted") {
    throw new Error(message.errorMessage ?? `model stopped with reason ${message.stopReason}`);
  }
  const usage = toTurnUsage(message.usage);
  const call = message.content.find((part): part is PiAiToolCall => part.type === "toolCall");
  if (call !== undefined) {
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
    .filter((part): part is PiAiTextContent => part.type === "text")
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

  constructor(options: PiAiProviderOptions) {
    this.id = options.id ?? "pi-ai";
    this.#options = options;
  }

  async nextTurn(request: ModelRequest): Promise<ModelDecision> {
    const context = toPiAiContext(request, { systemPrompt: this.#options.systemPrompt });
    const options: PiAiCompleteOptions = {};
    if (this.#options.apiKey !== undefined) options.apiKey = this.#options.apiKey;
    if (this.#options.temperature !== undefined) options.temperature = this.#options.temperature;
    if (this.#options.maxTokens !== undefined) options.maxTokens = this.#options.maxTokens;
    if (this.#options.reasoning !== undefined) options.reasoning = this.#options.reasoning;
    if (this.#options.sessionId !== undefined) options.sessionId = this.#options.sessionId;
    const message = await this.#options.complete(this.#options.model, context, options);
    return toModelDecision(message);
  }
}
