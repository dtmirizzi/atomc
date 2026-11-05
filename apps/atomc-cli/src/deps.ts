/**
 * Injectable dependency surface for the `atomc` CLI.
 *
 * Every command takes a {@link CliDeps} object so unit tests can drive the full
 * command tree with fakes and never spawn a daemon, touch the network, or probe
 * real hardware. The default implementation lives in {@link createDefaultDeps}.
 */
import type {
  DaemonInfo,
  DaemonStatusResult,
  DagRunParams,
  DagRunResult,
  DagStatusResult,
  GateResult,
  HealthResult,
  IRGetResult,
  PluginStatus,
  Subscription,
} from "@atomc/daemon-client";

/** Streaming output channels used by commands (never mixed with JSON payloads). */
export interface CliIO {
  /** Standard output: exactly one JSON object when `--json` is set. */
  out(text: string): void;
  /** Diagnostics, progress and human text. */
  err(text: string): void;
}

/** Minimal fs surface used by `init`/`plugin new`; tests supply an in-memory fake. */
export interface FsLike {
  mkdir(path: string, options: { recursive: true }): Promise<string | undefined>;
  readFile(path: string, encoding: "utf8"): Promise<string>;
  writeFile(path: string, data: string): Promise<void>;
  readdir(
    path: string,
  ): Promise<Array<{ name: string; isDirectory(): boolean; isFile(): boolean }>>;
  stat(path: string): Promise<{ isDirectory(): boolean; isFile(): boolean }>;
  copyFile(src: string, dest: string): Promise<void>;
  rm(path: string, options: { recursive: true; force: true }): Promise<void>;
  access(path: string): Promise<void>;
}

/** The subset of `DaemonClient` the CLI depends on. */
export interface DaemonApi {
  request<T = unknown>(method: string, params?: unknown): Promise<T>;
  getIR(path?: string): Promise<IRGetResult>;
  dagStatus(): Promise<DagStatusResult>;
  runDAG(params?: DagRunParams): Promise<DagRunResult>;
  listGates(ids?: readonly string[]): Promise<GateResult[]>;
  listPlugins(): Promise<PluginStatus[]>;
  daemonStatus(): Promise<DaemonStatusResult>;
  subscribe(
    topics: readonly string[],
    listener: (event: { topic: string; data: unknown }) => void,
  ): Promise<Subscription>;
  shutdown(): Promise<{ shutting_down: true }>;
  close(): Promise<void>;
}

/** A live-or-bootstrapped daemon plus the metadata needed for reporting. */
export interface DaemonHandle {
  info: DaemonInfo;
  started: boolean;
  client: DaemonApi;
}

/** Result of probing one local tool. */
export interface ToolProbe {
  name: string;
  /** Command or module this probe checks. */
  target: string;
  required: boolean;
  status: "PASS" | "WARN" | "FAIL" | "SKIP";
  detail: string;
}

/** Result of probing a possibly-running daemon without spawning one. */
export interface DaemonProbe {
  running: boolean;
  info?: DaemonInfo;
  health?: HealthResult;
  schema?: Record<string, unknown>;
  detail: string;
}

/** Dependency bundle consumed by every command. */
export interface CliDeps {
  io: CliIO;
  cwd: string;
  env: NodeJS.ProcessEnv;
  fs: FsLike;
  now(): Date;
  sleep(ms: number): Promise<void>;
  /** Locate the repository root that contains `examples/` (init template copy). */
  findRepoRoot(): Promise<string>;
  /** Ensure a daemon is running for `projectRoot`, spawning one if needed. */
  ensureDaemon(projectRoot: string): Promise<DaemonHandle>;
  /** Discover an already-running daemon; never spawns. */
  findDaemon(): Promise<DaemonHandle | undefined>;
  /** Probe the running daemon + committed schema without spawning. */
  probeDaemon(): Promise<DaemonProbe>;
  /** Probe local toolchains (uv, ato, qmk, build123d, Renode). */
  probeTools(): Promise<ToolProbe[]>;
  /** CLI version; must match `scripts/release/VERSION`. */
  cliVersion: string;
}
