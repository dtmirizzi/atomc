/**
 * JSONL transcript writer with redaction.
 *
 * Sessions live at `<projectRoot>/.atomc/sessions/<run>/<agent>.jsonl`
 * (`docs/architecture/contracts/agent-protocol.md`). Appends are async and
 * best-effort; writes are redacted before they hit disk so bearer tokens and
 * datasheet secrets never enter a transcript by default.
 */
import { appendFile, mkdir, rename, stat } from "node:fs/promises";
import { dirname, join } from "node:path";
import type { TranscriptOptions } from "./types.js";

/** Object keys whose values are always replaced with `[REDACTED]`. */
export const SENSITIVE_KEYS: ReadonlySet<string> = new Set([
  "token",
  "access_token",
  "refresh_token",
  "id_token",
  "secret",
  "client_secret",
  "password",
  "api_key",
  "apikey",
  "authorization",
  "bearer",
  "cookie",
  "set-cookie",
  "private_key",
]);

/** Default string patterns scrubbed from serialized transcripts. */
export const DEFAULT_REDACT_PATTERNS: readonly RegExp[] = [
  /Bearer\s+[A-Za-z0-9._~+/=-]+/gi,
  /\b(?:sk|pk|rk)-[A-Za-z0-9]{8,}\b/g,
  /\bgh[pousr]_[A-Za-z0-9]{20,}\b/g,
];

const REDACTED = "[REDACTED]";

function isSensitiveKey(key: string): boolean {
  return SENSITIVE_KEYS.has(key.toLowerCase());
}

/** Recursively replace sensitive keys and token-shaped strings in a JSON value. */
export function redactValue(
  value: unknown,
  patterns: readonly RegExp[] = [],
  seen = new WeakSet<object>(),
): unknown {
  if (typeof value === "string") return redactText(value, patterns);
  if (value === null || typeof value !== "object") return value;
  if (seen.has(value)) return "[Circular]";
  seen.add(value);
  if (Array.isArray(value)) return value.map((item) => redactValue(item, patterns, seen));
  const output: Record<string, unknown> = {};
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    output[key] = isSensitiveKey(key) ? REDACTED : redactValue(child, patterns, seen);
  }
  return output;
}

/** Scrub token-shaped substrings from a string. */
export function redactText(text: string, patterns: readonly RegExp[] = []): string {
  let output = text;
  for (const pattern of [...DEFAULT_REDACT_PATTERNS, ...patterns]) {
    output = output.replace(pattern, REDACTED);
  }
  return output;
}

/** Produce a redacted, JSON-serializable copy of an arbitrary entry. */
export function redactEntry(entry: unknown, patterns: readonly RegExp[] = []): unknown {
  return redactValue(entry, patterns);
}

/** Append-only JSONL writer for one agent session. */
export class TranscriptWriter {
  readonly #path: string;
  readonly #redact: readonly RegExp[];
  readonly #maxBytes: number;
  #rotation = 0;

  constructor(
    options: TranscriptOptions & {
      runId: string;
      agentId: string;
      maxBytes?: number;
    },
  ) {
    this.#path = join(
      options.projectRoot,
      ".atomc",
      "sessions",
      options.runId,
      `${options.agentId}.jsonl`,
    );
    this.#redact = options.redact ?? [];
    this.#maxBytes = options.maxBytes ?? 8 * 1024 * 1024;
  }

  /** Absolute path of the active transcript file. */
  get path(): string {
    return this.#path;
  }

  /** Serialize and append one entry, rotating the file when it grows past the cap. */
  async append(entry: unknown): Promise<void> {
    const serialized = `${JSON.stringify(redactEntry(entry))}\n`;
    await mkdir(dirname(this.#path), { recursive: true });
    await this.#rotateIfNeeded(serialized.length);
    await appendFile(this.#path, serialized, "utf8");
  }

  async #rotateIfNeeded(incoming: number): Promise<void> {
    try {
      const info = await stat(this.#path);
      if (info.size + incoming <= this.#maxBytes) return;
    } catch {
      return; // File does not exist yet.
    }
    this.#rotation += 1;
    await rename(this.#path, `${this.#path}.${this.#rotation}`);
  }
}
