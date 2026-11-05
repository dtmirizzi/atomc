/**
 * Real-daemon harness for the RPC contract tests.
 *
 * Each instance creates a throwaway project + state directory, writes a canonical
 * minimal `system_ir.json` (from the core-ir fixture) plus the deterministic fake
 * plugin, spawns the **actual** `atomcd serve` process with `uv run`, waits for
 * `/health` and `daemon.json`, and exposes the real `@atomc/daemon-client` against
 * `ws://127.0.0.1:<port>/rpc`.
 *
 * Teardown is `finally`-safe: it asks the daemon to shut down, otherwise terminates,
 * then kills, and always removes the temp tree. Captured stdout/stderr is bounded and
 * included (token-redacted) in failure messages.
 */
import { type ChildProcess, spawn } from "node:child_process";
import { mkdir, mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { delimiter, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { DaemonClient } from "@atomc/daemon-client";
import WebSocket from "ws";
import { FAKE_MANIFEST, FAKE_PLUGIN_SOURCE } from "./fixtures/fake-plugin.js";

const HERE = dirname(fileURLToPath(import.meta.url));

/** Repository root: this file lives at `tests/rpc/ts/harness.ts`. */
export const REPO_ROOT = resolve(HERE, "../../..");

/** Canonical minimal IR document produced by WP-1.1. */
export const CORE_IR_FIXTURE = resolve(REPO_ROOT, "packages/core-ir/fixtures/minimal.json");

/** Committed JSON Schema the `/schema` endpoint must reproduce. */
export const CORE_IR_SCHEMA_PATH = resolve(
  REPO_ROOT,
  "packages/core-ir/schema/system_ir.schema.json",
);

/** Shape of `~/.atomc/daemon.json` (mode 0600). */
export interface DaemonStateFile {
  pid: number;
  host: string;
  port: number;
  token: string;
  project_root: string;
  started_at: string;
  version: string;
}

/** Startup options. */
export interface DaemonHarnessOptions {
  /** How long to wait for `/health` + `daemon.json` (default 180s; first uv sync can be slow). */
  startupTimeoutMs?: number;
  /** Per-request client timeout (default 30s). */
  requestTimeoutMs?: number;
  /** Pre-write a stale `daemon.json` (dead pid 0) before starting. */
  staleState?: boolean;
}

const LOG_LIMIT_BYTES = 64 * 1024;
const STATE_FILENAME = "daemon.json";

function sleep(ms: number): Promise<void> {
  return new Promise((done) => setTimeout(done, ms));
}

async function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<never>((_resolve, reject) => {
        timer = setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms);
      }),
    ]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}

async function freePort(): Promise<number> {
  const net = await import("node:net");
  return new Promise<number>((resolvePort, rejectPort) => {
    const server = net.createServer();
    server.unref();
    server.on("error", rejectPort);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (address !== null && typeof address === "object") {
        const { port } = address;
        server.close(() => resolvePort(port));
      } else {
        server.close();
        rejectPort(new Error("failed to allocate a free port"));
      }
    });
  });
}

/** A running `atomcd` plus its private temp tree. */
export class DaemonHarness {
  readonly rootDir: string;
  readonly projectDir: string;
  readonly stateDir: string;
  readonly port: number;
  readonly httpBase: string;
  readonly rpcUrl: string;

  #daemonPid = 0;
  #token = "";
  #proc: ChildProcess;
  #requestTimeoutMs: number;
  #logs: string[] = [];
  #logBytes = 0;
  #clients: DaemonClient[] = [];
  #stopping = false;

  private constructor(options: {
    rootDir: string;
    projectDir: string;
    stateDir: string;
    port: number;
    proc: ChildProcess;
    requestTimeoutMs: number;
  }) {
    this.rootDir = options.rootDir;
    this.projectDir = options.projectDir;
    this.stateDir = options.stateDir;
    this.port = options.port;
    this.httpBase = `http://127.0.0.1:${options.port}`;
    this.rpcUrl = `ws://127.0.0.1:${options.port}/rpc`;
    this.#proc = options.proc;
    this.#requestTimeoutMs = options.requestTimeoutMs;
  }

  /** Create the temp tree, spawn the daemon and wait until it is healthy. */
  static async start(options: DaemonHarnessOptions = {}): Promise<DaemonHarness> {
    const rawRoot = await mkdtemp(join(tmpdir(), "atomc-rpc-"));
    const rootDir = await realpath(rawRoot);
    const projectDir = join(rootDir, "project");
    const stateDir = join(rootDir, "state");
    await mkdir(projectDir, { recursive: true });
    await mkdir(stateDir, { recursive: true });

    await writeFile(
      join(projectDir, "system_ir.json"),
      await readFile(CORE_IR_FIXTURE, "utf8"),
      "utf8",
    );
    await writeFile(join(projectDir, "fake_rpc_plugin.py"), FAKE_PLUGIN_SOURCE, "utf8");
    const pluginDir = join(projectDir, "plugins", FAKE_MANIFEST.name);
    await mkdir(pluginDir, { recursive: true });
    await writeFile(
      join(pluginDir, "atomc-plugin.json"),
      `${JSON.stringify(FAKE_MANIFEST, null, 2)}\n`,
      "utf8",
    );

    if (options.staleState) {
      const stale = {
        pid: 0,
        host: "127.0.0.1",
        port: 1,
        token: "stale-token-not-used",
        project_root: projectDir,
        started_at: "2026-01-01T00:00:00Z",
        version: "0.0.0",
      };
      await writeFile(
        join(stateDir, STATE_FILENAME),
        `${JSON.stringify(stale, null, 2)}\n`,
        "utf8",
      );
    }

    const port = await freePort();
    const env: NodeJS.ProcessEnv = { ...process.env };
    delete env.ATOMCD_TOKEN;
    delete env.ATOMCD_HOST;
    delete env.ATOMCD_PORT;
    delete env.ATOMCD_STATE_DIR;
    env.PYTHONPATH = process.env.PYTHONPATH
      ? `${projectDir}${delimiter}${process.env.PYTHONPATH}`
      : projectDir;
    env.PYTHONUNBUFFERED = "1";

    const proc = spawn(
      "uv",
      [
        "run",
        "--project",
        REPO_ROOT,
        "--all-packages",
        "atomcd",
        "serve",
        "--project",
        projectDir,
        "--host",
        "127.0.0.1",
        "--port",
        String(port),
        "--state-dir",
        stateDir,
      ],
      { cwd: REPO_ROOT, env, stdio: ["ignore", "pipe", "pipe"] },
    );

    const harness = new DaemonHarness({
      rootDir,
      projectDir,
      stateDir,
      port,
      proc,
      requestTimeoutMs: options.requestTimeoutMs ?? 30_000,
    });
    proc.stdout?.on("data", (chunk: Buffer) => harness.#appendLog(chunk));
    proc.stderr?.on("data", (chunk: Buffer) => harness.#appendLog(chunk));
    proc.on("error", (error) => harness.#appendLog(Buffer.from(`spawn error: ${error.message}\n`)));
    await harness.#waitForHealthy(options.startupTimeoutMs ?? 180_000);
    return harness;
  }

  #appendLog(chunk: Buffer): void {
    const text = chunk.toString("utf8");
    this.#logs.push(text);
    this.#logBytes += text.length;
    while (this.#logBytes > LOG_LIMIT_BYTES && this.#logs.length > 1) {
      const dropped = this.#logs.shift();
      this.#logBytes -= dropped?.length ?? 0;
    }
  }

  /** The daemon process pid from `daemon.json` (0 until healthy). */
  get pid(): number {
    return this.#daemonPid;
  }

  /** Redact the bearer token from arbitrary text. */
  redact(text: string): string {
    if (this.#token.length === 0) return text;
    return text.split(this.#token).join("<redacted>");
  }

  /** Bounded, token-redacted captured daemon output. */
  logs(): string {
    return this.redact(this.#logs.join(""));
  }

  async #tryReadState(): Promise<DaemonStateFile | null> {
    try {
      const text = await readFile(join(this.stateDir, STATE_FILENAME), "utf8");
      return JSON.parse(text) as DaemonStateFile;
    } catch {
      return null;
    }
  }

  async #waitForHealthy(timeoutMs: number): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (this.#proc.exitCode !== null) {
        throw new Error(`daemon exited early with code ${this.#proc.exitCode}\n${this.logs()}`);
      }
      const state = await this.#tryReadState();
      if (
        state !== null &&
        state.port === this.port &&
        typeof state.pid === "number" &&
        state.pid > 0 &&
        typeof state.token === "string" &&
        state.token.length > 0
      ) {
        this.#token = state.token;
        this.#daemonPid = state.pid;
        try {
          const response = await fetch(`${this.httpBase}/health`, {
            signal: AbortSignal.timeout(2_000),
          });
          if (response.ok) {
            const body = (await response.json()) as { ok?: boolean };
            if (body.ok === true) return;
          }
        } catch {
          // not ready yet
        }
      }
      await sleep(100);
    }
    throw new Error(`daemon did not become healthy within ${timeoutMs}ms\n${this.logs()}`);
  }

  /** Connect the real client (tracks the socket for teardown). */
  async connect(): Promise<DaemonClient> {
    const client = await DaemonClient.connect({
      url: this.rpcUrl,
      token: this.#token,
      timeoutMs: this.#requestTimeoutMs,
    });
    this.#clients.push(client);
    return client;
  }

  /** GET an HTTP endpoint and parse JSON, with a bounded timeout. */
  async httpJson<T>(path: string): Promise<T> {
    const response = await fetch(`${this.httpBase}${path}`, {
      signal: AbortSignal.timeout(5_000),
    });
    if (!response.ok) {
      throw new Error(`GET ${path} returned ${response.status}: ${await response.text()}`);
    }
    return (await response.json()) as T;
  }

  /** Current `daemon.json`, or `null` when absent. */
  async readState(): Promise<DaemonStateFile | null> {
    return this.#tryReadState();
  }

  /** True when `daemon.json` still exists. */
  async pidFileExists(): Promise<boolean> {
    return (await this.#tryReadState()) !== null;
  }

  /** Wait for the child process to exit; resolves `false` on timeout. */
  async waitForProcessExit(timeoutMs = 15_000): Promise<boolean> {
    if (this.#proc.exitCode !== null) return true;
    return new Promise<boolean>((resolveExit) => {
      const timer = setTimeout(() => {
        resolveExit(this.#proc.exitCode !== null);
      }, timeoutMs);
      this.#proc.once("exit", () => {
        clearTimeout(timer);
        resolveExit(true);
      });
    });
  }

  /** Shut down the daemon (best-effort) and remove the temp tree. Never throws. */
  async stop(): Promise<void> {
    if (this.#stopping) return;
    this.#stopping = true;
    for (const client of this.#clients) {
      try {
        if (!client.closed) {
          await withTimeout(client.shutdown(), 3_000, "shutdown").catch(() => undefined);
          await client.close().catch(() => undefined);
        }
      } catch {
        // ignore teardown races
      }
    }
    if (this.#proc.exitCode === null) {
      const exited = await this.waitForProcessExit(8_000);
      if (!exited) {
        this.#proc.kill("SIGTERM");
        const terminated = await this.waitForProcessExit(5_000);
        if (!terminated) this.#proc.kill("SIGKILL");
      }
    }
    await rm(this.rootDir, { recursive: true, force: true }).catch(() => undefined);
  }
}

/**
 * Open a raw WebSocket and resolve with the close code. Used to assert policy
 * rejection (`1008`) for missing/incorrect bearer tokens.
 */
export function expectPolicyClose(
  url: string,
  token: string | undefined,
  timeoutMs = 10_000,
): Promise<number> {
  return new Promise<number>((resolveClose, rejectClose) => {
    const socket =
      token === undefined
        ? new WebSocket(url)
        : new WebSocket(url, { headers: { Authorization: `Bearer ${token}` } });
    const timer = setTimeout(() => {
      socket.terminate();
      rejectClose(new Error(`expected a policy close within ${timeoutMs}ms`));
    }, timeoutMs);
    socket.on("close", (code: number) => {
      clearTimeout(timer);
      resolveClose(code);
    });
    socket.on("error", () => {
      // A reset counts as a non-policy failure; wait for `close` or timeout.
    });
  });
}

/** Poll collected events for a predicate; throws with the observed topics on timeout. */
export async function waitForEvent<T extends { topic: string }>(
  events: readonly T[],
  predicate: (event: T) => boolean,
  timeoutMs = 10_000,
): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const found = events.find(predicate);
    if (found !== undefined) return found;
    await sleep(25);
  }
  const topics = events.map((event) => event.topic).join(", ") || "<none>";
  throw new Error(`timed out after ${timeoutMs}ms waiting for an event; saw: ${topics}`);
}
