/**
 * Real-process harness for the atomc-pad end-to-end vertical slice (WP-4.5).
 *
 * Each instance creates a throwaway project + state directory seeded from the committed
 * `examples/atomc-pad/system_ir.json`, spawns the **actual** `atomcd serve` process with
 * `uv run`, waits for `/health` and `daemon.json`, and exposes the real
 * `@atomc/daemon-client` against `ws://127.0.0.1:<port>/rpc`.
 *
 * The daemon discovers the four built-in plugins (`atopile`, `renode`, `cad-jig`, `qmk`)
 * through the installed `atomc.plugins` entry points — there is deliberately **no** fake
 * plugin and no project-tree manifest in the seed.
 *
 * Determinism: each daemon runs with a sanitized environment so external toolchains
 * (`qmk`, `renode`) are absent regardless of the host. That is what makes the vertical
 * slice reproducible on a developer machine that has them installed *and* on a clean CI
 * runner that does not: `fw.qmk_compile` and `fw.renode_boot` must both report an honest
 * `SKIP` instead of a host-dependent PASS/FAIL. The sanitized environment:
 *
 * - `PATH` points at an empty temp dir (so `shutil.which` finds nothing),
 * - `HOME` points at a temp dir (so the Renode plugin's `~/.local/...` and
 *   `/Applications/...` probes miss),
 * - `QMK_HOME` points at a non-existent path,
 * - `ATOMC_RENODE_BIN` / `PYRENODE_PATH` are unset,
 * - `UV_CACHE_DIR` / `UV_PYTHON_INSTALL_DIR` / `UV_TOOL_DIR` are pinned to the real
 *   locations so `uv run` reuses the already-synced workspace instead of re-downloading.
 *
 * Teardown is `finally`-safe: it asks the daemon to shut down, otherwise terminates, then
 * kills, and always removes the temp tree. Captured stdout/stderr is bounded and included
 * (token-redacted) in failure messages.
 */
import { type ChildProcess, spawn } from "node:child_process";
import { accessSync, constants as fsConstants } from "node:fs";
import { mkdir, mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { delimiter, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  type AtomcEvent,
  DaemonClient,
  type DagNodeStatus,
  type GateResult,
} from "@atomc/daemon-client";
import WebSocket from "ws";

const HERE = dirname(fileURLToPath(import.meta.url));

/** Repository root: this file lives at `tests/e2e/ts/harness.ts`. */
export const REPO_ROOT = resolve(HERE, "../../..");

/** The committed atomc-pad IR fixture the vertical slice is seeded from. */
export const PAD_IR_FIXTURE = resolve(REPO_ROOT, "examples/atomc-pad/system_ir.json");

/** The four built-in plugins the daemon must discover through entry points. */
export const EXPECTED_PLUGINS = ["atopile", "renode", "cad-jig", "qmk"] as const;

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
  /** Per-request client timeout (default 60s; the full DAG run can take a moment). */
  requestTimeoutMs?: number;
  /**
   * Optional transform applied to the seeded IR text before it is written. Used to
   * mutate the fixture deterministically (e.g. the failure-honesty spec) without
   * touching the committed example.
   */
  seedTransform?: (ir: Record<string, unknown>) => Record<string, unknown>;
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

/** Resolve the `uv` executable to an absolute path using the *real* PATH. */
function resolveUv(): string {
  if (process.env.UV !== undefined && process.env.UV.length > 0) return process.env.UV;
  for (const dir of (process.env.PATH ?? "").split(delimiter)) {
    if (dir.length === 0) continue;
    const candidate = join(dir, "uv");
    try {
      accessSync(candidate, fsConstants.X_OK);
      return candidate;
    } catch {
      // keep searching
    }
  }
  return "uv";
}

const UV_BIN = resolveUv();

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
    const rawRoot = await mkdtemp(join(tmpdir(), "atomc-e2e-"));
    const rootDir = await realpath(rawRoot);
    const projectDir = join(rootDir, "project");
    const stateDir = join(rootDir, "state");
    const homeDir = join(rootDir, "home");
    const pathDir = join(rootDir, "empty-path");
    await mkdir(projectDir, { recursive: true });
    await mkdir(stateDir, { recursive: true });
    await mkdir(homeDir, { recursive: true });
    await mkdir(pathDir, { recursive: true });

    const rawSeed = JSON.parse(await readFile(PAD_IR_FIXTURE, "utf8")) as Record<string, unknown>;
    const seed = options.seedTransform ? options.seedTransform(rawSeed) : rawSeed;
    await writeFile(
      join(projectDir, "system_ir.json"),
      `${JSON.stringify(seed, null, 2)}\n`,
      "utf8",
    );

    const port = await freePort();
    const realHome = process.env.HOME ?? tmpdir();
    const env: NodeJS.ProcessEnv = { ...process.env };
    // Deterministic no-toolchain environment (see the module docstring).
    delete env.ATOMCD_TOKEN;
    delete env.ATOMCD_HOST;
    delete env.ATOMCD_PORT;
    delete env.ATOMCD_STATE_DIR;
    delete env.ATOMC_RENODE_BIN;
    delete env.PYRENODE_PATH;
    delete env.PYTHONPATH;
    env.HOME = homeDir;
    env.PATH = pathDir;
    env.QMK_HOME = join(rootDir, "no-qmk-home");
    env.UV_CACHE_DIR = process.env.UV_CACHE_DIR ?? join(realHome, ".cache", "uv");
    env.UV_PYTHON_INSTALL_DIR =
      process.env.UV_PYTHON_INSTALL_DIR ?? join(realHome, ".local", "share", "uv", "python");
    env.UV_TOOL_DIR = process.env.UV_TOOL_DIR ?? join(realHome, ".local", "share", "uv", "tools");
    env.PYTHONUNBUFFERED = "1";

    const proc = spawn(
      UV_BIN,
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
      requestTimeoutMs: options.requestTimeoutMs ?? 60_000,
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

  /** Read the seeded IR document straight from disk (canonical 2-space JSON). */
  async readProjectIR(): Promise<Record<string, unknown>> {
    return JSON.parse(await readFile(join(this.projectDir, "system_ir.json"), "utf8")) as Record<
      string,
      unknown
    >;
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

  /** Assert the daemon process is no longer running. */
  async assertProcessDead(): Promise<void> {
    if (this.#proc.exitCode === null) {
      throw new Error(`daemon process ${this.#proc.pid} is still running`);
    }
  }
}

/** Poll collected events for a predicate; throws with the observed topics on timeout. */
export async function waitForEvent<T extends { topic: string }>(
  events: readonly T[],
  predicate: (event: T) => boolean,
  timeoutMs = 60_000,
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

/** Wait until every expected DAG node has emitted a `dag.node.end` for `runId`. */
export async function waitForDagEnd(
  events: readonly AtomcEvent[],
  expectedNodeIds: readonly string[],
  runId: string,
  timeoutMs = 120_000,
): Promise<Map<string, { ok: boolean; error?: string; duration_ms: number }>> {
  const deadline = Date.now() + timeoutMs;
  const ended = new Map<string, { ok: boolean; error?: string; duration_ms: number }>();
  while (Date.now() < deadline) {
    for (const event of events) {
      if (event.topic !== "dag.node.end") continue;
      const data = event.data as {
        run_id: string;
        id: string;
        ok: boolean;
        error?: string;
        duration_ms: number;
      };
      if (data.run_id === runId) ended.set(data.id, data);
    }
    if (expectedNodeIds.every((id) => ended.has(id))) return ended;
    await sleep(25);
  }
  const missing = expectedNodeIds.filter((id) => !ended.has(id));
  throw new Error(
    `timed out waiting for DAG run ${runId}; missing node.end for: ${missing.join(", ")}`,
  );
}

/** Node ids currently known to the scheduler. */
export function dagNodeIds(status: { nodes: DagNodeStatus[] }): string[] {
  return status.nodes.map((node) => node.id).sort();
}

/** Narrow a collected event list to its gate results. */
export function gateResultsFrom(events: readonly AtomcEvent[]): GateResult[] {
  return events
    .filter(
      (event): event is { topic: "gate.result"; data: GateResult } => event.topic === "gate.result",
    )
    .map((event) => event.data);
}

/** Index gate results by id for assertions. */
export function gatesById(results: readonly GateResult[]): Map<string, GateResult> {
  return new Map(results.map((result) => [result.id, result]));
}

/**
 * Run the whole reactive DAG for the loaded plugins, capturing node and gate events.
 * Subscribes before `dag.run` so no event is missed, waits for every node to finish,
 * then unsubscribes.
 */
export async function runFullDag(
  client: DaemonClient,
): Promise<{ runId: string; events: AtomcEvent[]; gates: GateResult[] }> {
  const status = await client.dagStatus();
  const expected = status.nodes.map((node) => node.id);
  const events: AtomcEvent[] = [];
  const subscription = await client.subscribe(["dag.node.end", "gate.result"], (event) =>
    events.push(event),
  );
  try {
    const run = await client.runDAG({ force: true });
    await waitForDagEnd(events, expected, run.run_id);
    return { runId: run.run_id, events, gates: gateResultsFrom(events) };
  } finally {
    await subscription.unsubscribe().catch(() => undefined);
  }
}

/** Open a raw WebSocket and resolve with the close code (auth policy assertions). */
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
