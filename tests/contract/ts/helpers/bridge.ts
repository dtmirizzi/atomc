/**
 * Client for the Python JSON-lines bridge (`tests/contract/python/bridge.py`).
 *
 * One `uv run --package atomc-core-ir python bridge.py` process is spawned per
 * `Bridge` instance; callers should create one per test file (`beforeAll`) and
 * close it in `afterAll`. Requests are multiplexed over stdin/stdout by `id`.
 */
import { type ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

/** Repository root (this file lives at `tests/contract/ts/helpers/bridge.ts`). */
export const REPO_ROOT = resolve(HERE, "../../../..");

const BRIDGE_PATH = resolve(REPO_ROOT, "tests/contract/python/bridge.py");

/** Per-request timeout. Generous because the first `uv run` may sync the env. */
const DEFAULT_TIMEOUT_MS = Number(process.env.ATOMC_BRIDGE_TIMEOUT_MS ?? 300_000);

export interface BridgeError {
  type: "conflict" | "locked" | "validation" | "ref_integrity" | "patch" | "error";
  message: string;
}

export interface ValidateResult {
  ir: Record<string, unknown>;
  canonical: string;
}

export interface PatchRequest {
  ir: Record<string, unknown>;
  path: string;
  base_rev: number;
  ops: unknown[];
  holder?: string;
}

export interface PatchResult {
  ir: Record<string, unknown>;
  canonical: string;
  new_rev: number;
  changed_paths: string[];
}

/** Raised when the bridge responds `ok: false`. */
export class BridgeFailure extends Error {
  readonly type: BridgeError["type"];

  constructor(error: BridgeError) {
    super(`bridge ${error.type}: ${error.message}`);
    this.name = "BridgeFailure";
    this.type = error.type;
  }
}

interface Pending {
  resolve: (value: Record<string, unknown>) => void;
  reject: (reason: Error) => void;
  timer: NodeJS.Timeout;
}

export class Bridge {
  readonly #proc: ChildProcessWithoutNullStreams;
  readonly #pending = new Map<number, Pending>();
  readonly #stderrChunks: string[] = [];
  #nextId = 1;
  #closed = false;

  constructor() {
    this.#proc = spawn("uv", ["run", "--package", "atomc-core-ir", "python", BRIDGE_PATH], {
      cwd: REPO_ROOT,
      stdio: ["pipe", "pipe", "pipe"],
    });

    const lines = createInterface({ input: this.#proc.stdout });
    lines.on("line", (line) => this.#onLine(line));
    this.#proc.stderr.on("data", (chunk: Buffer) => this.#stderrChunks.push(chunk.toString()));
    this.#proc.on("error", (err) => this.#failAll(err));
    this.#proc.on("exit", (code) => {
      if (!this.#closed && this.#pending.size > 0) {
        this.#failAll(
          new Error(`bridge exited with code ${code} before responding:\n${this.stderr}`),
        );
      }
    });
  }

  get stderr(): string {
    return this.#stderrChunks.join("");
  }

  #onLine(line: string): void {
    const trimmed = line.trim();
    if (trimmed === "") return;
    let message: Record<string, unknown>;
    try {
      message = JSON.parse(trimmed) as Record<string, unknown>;
    } catch {
      this.#failAll(new Error(`bridge emitted non-JSON stdout line: ${trimmed}`));
      return;
    }
    const id = Number(message.id);
    const pending = this.#pending.get(id);
    if (pending === undefined) return;
    this.#pending.delete(id);
    clearTimeout(pending.timer);
    if (message.ok === true) {
      pending.resolve(message);
    } else {
      const error = (message.error ?? {
        type: "error",
        message: "unknown bridge error",
      }) as BridgeError;
      pending.reject(new BridgeFailure(error));
    }
  }

  #failAll(reason: Error): void {
    for (const [id, pending] of this.#pending) {
      this.#pending.delete(id);
      clearTimeout(pending.timer);
      pending.reject(reason);
    }
  }

  request(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    if (this.#closed) return Promise.reject(new Error("bridge is closed"));
    const id = this.#nextId++;
    return new Promise((resolvePromise, rejectPromise) => {
      const timer = setTimeout(() => {
        this.#pending.delete(id);
        rejectPromise(
          new Error(
            `bridge request ${id} (op=${String(payload.op)}) timed out after ${DEFAULT_TIMEOUT_MS}ms:\n${this.stderr}`,
          ),
        );
      }, DEFAULT_TIMEOUT_MS);
      this.#pending.set(id, { resolve: resolvePromise, reject: rejectPromise, timer });
      this.#proc.stdin.write(`${JSON.stringify({ id, ...payload })}\n`);
    });
  }

  async validate(ir: Record<string, unknown>): Promise<ValidateResult> {
    const res = await this.request({ op: "validate", ir });
    return { ir: res.ir as Record<string, unknown>, canonical: res.canonical as string };
  }

  async patch(req: PatchRequest): Promise<PatchResult> {
    const res = await this.request({ op: "patch", ...req });
    return {
      ir: res.ir as Record<string, unknown>,
      canonical: res.canonical as string,
      new_rev: res.new_rev as number,
      changed_paths: res.changed_paths as string[],
    };
  }

  close(): void {
    this.#closed = true;
    this.#failAll(new Error("bridge closed"));
    this.#proc.kill();
  }
}
