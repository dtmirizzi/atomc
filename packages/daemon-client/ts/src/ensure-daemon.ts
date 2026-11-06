/**
 * `ensureDaemon` — discover or bootstrap the `atomcd` daemon.
 *
 * Reads `~/.atomc/daemon.json` (mode 0600, written by the daemon), validates the
 * pid and `GET /health`, reuses a live daemon, and otherwise spawns
 * `uv run [--project <repo>] atomcd serve --project <projectRoot>` detached with
 * logs under `~/.atomc/daemon.log`. Every process/filesystem/clock dependency is
 * injectable for tests.
 *
 * See `docs/architecture/contracts/rpc.md` §Transport and lifecycle.
 */

import { spawn } from "node:child_process";
import { closeSync, openSync } from "node:fs";
import { mkdir, readFile, realpath, rm } from "node:fs/promises";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { DaemonClient, type DaemonClientOptions } from "./client.js";
import { DaemonStartError } from "./errors.js";
import type { DaemonInfo, HealthResult } from "./types.js";

/** Minimal handle returned by a spawn implementation. */
export interface SpawnedDaemon {
  pid?: number | undefined;
  unref?: (() => void) | undefined;
  kill?: ((signal?: NodeJS.Signals | number) => boolean) | undefined;
  /** Set asynchronously if the process could not be started. */
  error?: Error | undefined;
}

/** Options passed to a spawn implementation. */
export interface SpawnDaemonOptions {
  cwd: string;
  env: NodeJS.ProcessEnv;
  logPath: string;
}

/** Spawn implementation signature (defaults to `node:child_process.spawn`). */
export type SpawnDaemon = (
  command: string,
  args: string[],
  options: SpawnDaemonOptions,
) => SpawnedDaemon;

/** Injectable dependencies for {@link ensureDaemon}. */
export interface EnsureDaemonDeps {
  readFile?: (path: string) => Promise<string>;
  removeFile?: (path: string) => Promise<void>;
  mkdirp?: (path: string) => Promise<void>;
  spawnDaemon?: SpawnDaemon;
  isProcessAlive?: (pid: number) => boolean;
  healthCheck?: (info: DaemonInfo) => Promise<boolean>;
  connect?: (options: DaemonClientOptions) => Promise<DaemonClient>;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
  homeDir?: () => string;
  /** Resolves symlinks so project roots compare by real location; defaults to fs.realpath. */
  realpath?: (path: string) => Promise<string>;
}

/** Options for {@link ensureDaemon}. */
export interface EnsureDaemonOptions {
  /** Directory holding `daemon.json`/`daemon.log`; defaults to `~/.atomc`. */
  atomcHome?: string;
  /** `uv` executable; defaults to `"uv"`. */
  uvCommand?: string;
  /** Daemon console script; defaults to `"atomcd"`. */
  daemonCommand?: string;
  /** Repo to pass to `uv run --project` (env `ATOMC_REPO` fallback). */
  uvProject?: string;
  /** Overall bootstrap timeout; defaults to 30 000 ms. */
  timeoutMs?: number;
  /** Initial backoff delay; defaults to 50 ms. */
  initialDelayMs?: number;
  /** Maximum backoff delay; defaults to 1 000 ms. */
  maxDelayMs?: number;
  /** Backoff multiplier; defaults to 1.6. */
  backoffFactor?: number;
  /** Extra environment for the spawned daemon. */
  env?: NodeJS.ProcessEnv;
  /** Optional non-secret log sink (never receives the bearer token). */
  log?: (message: string) => void;
  /** Dependency overrides (tests). */
  deps?: EnsureDaemonDeps;
}

/** Result of {@link ensureDaemon}. */
export interface EnsureDaemonResult {
  info: DaemonInfo;
  /** True if this call spawned a new daemon. */
  started: boolean;
  /** Connected client for the discovered daemon. */
  client: DaemonClient;
}

interface ResolvedDeps {
  readFile: (path: string) => Promise<string>;
  removeFile: (path: string) => Promise<void>;
  mkdirp: (path: string) => Promise<void>;
  spawnDaemon: SpawnDaemon;
  isProcessAlive: (pid: number) => boolean;
  healthCheck: (info: DaemonInfo) => Promise<boolean>;
  connect: (options: DaemonClientOptions) => Promise<DaemonClient>;
  sleep: (ms: number) => Promise<void>;
  now: () => number;
  homeDir: () => string;
  realpath: (path: string) => Promise<string>;
}

/** WebSocket URL for a daemon, mapping wildcard bind hosts to loopback. */
export function daemonWebSocketUrl(info: Pick<DaemonInfo, "host" | "port">): string {
  const host = info.host === "0.0.0.0" || info.host === "::" ? "127.0.0.1" : info.host;
  return `ws://${host}:${info.port}/rpc`;
}

function defaultSpawnDaemon(
  command: string,
  args: string[],
  options: SpawnDaemonOptions,
): SpawnedDaemon {
  const logFd = openSync(options.logPath, "a");
  try {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env,
      detached: true,
      stdio: ["ignore", logFd, logFd],
    });
    child.unref();
    const handle: SpawnedDaemon = {
      pid: child.pid,
      unref: () => child.unref(),
      kill: (signal) => child.kill(signal),
    };
    child.on("error", (error) => {
      handle.error = error;
    });
    return handle;
  } finally {
    closeSync(logFd);
  }
}

function defaultIsProcessAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    // EPERM means the process exists but belongs to another user.
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}

async function defaultHealthCheck(info: DaemonInfo): Promise<boolean> {
  const host = info.host === "0.0.0.0" || info.host === "::" ? "127.0.0.1" : info.host;
  const url = `http://${host}:${info.port}/health`;
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(2000) });
    if (!response.ok) return false;
    const body = (await response.json()) as HealthResult;
    return body.ok === true;
  } catch {
    return false;
  }
}

function resolveDeps(deps: EnsureDaemonDeps | undefined): ResolvedDeps {
  return {
    readFile: deps?.readFile ?? ((path) => readFile(path, "utf8")),
    removeFile: deps?.removeFile ?? ((path) => rm(path, { force: true })),
    mkdirp:
      deps?.mkdirp ??
      (async (path) => {
        await mkdir(path, { recursive: true });
      }),
    spawnDaemon: deps?.spawnDaemon ?? defaultSpawnDaemon,
    isProcessAlive: deps?.isProcessAlive ?? defaultIsProcessAlive,
    healthCheck: deps?.healthCheck ?? defaultHealthCheck,
    connect: deps?.connect ?? ((options) => DaemonClient.connect(options)),
    sleep: deps?.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms))),
    now: deps?.now ?? (() => Date.now()),
    homeDir: deps?.homeDir ?? homedir,
    realpath: deps?.realpath ?? ((path) => realpath(path)),
  };
}

function parseDaemonInfo(value: unknown): DaemonInfo | undefined {
  if (value === null || typeof value !== "object") return undefined;
  const o = value as Record<string, unknown>;
  if (typeof o.pid !== "number" || !Number.isInteger(o.pid) || o.pid <= 0) return undefined;
  if (typeof o.host !== "string" || o.host === "") return undefined;
  if (typeof o.port !== "number" || !Number.isInteger(o.port) || o.port <= 0 || o.port > 65535) {
    return undefined;
  }
  if (typeof o.token !== "string" || o.token === "") return undefined;
  if (typeof o.project_root !== "string") return undefined;
  if (typeof o.started_at !== "string") return undefined;
  if (typeof o.version !== "string") return undefined;
  return {
    pid: o.pid,
    host: o.host,
    port: o.port,
    token: o.token,
    project_root: o.project_root,
    started_at: o.started_at,
    version: o.version,
  };
}

async function readDaemonInfo(deps: ResolvedDeps, path: string): Promise<DaemonInfo | undefined> {
  let text: string;
  try {
    text = await deps.readFile(path);
  } catch {
    return undefined;
  }
  try {
    return parseDaemonInfo(JSON.parse(text));
  } catch {
    return undefined;
  }
}

async function validateDaemon(deps: ResolvedDeps, info: DaemonInfo): Promise<boolean> {
  return deps.isProcessAlive(info.pid) && (await deps.healthCheck(info));
}

/** Compare two project roots by their real (symlink-resolved) locations. */
async function sameProjectRoot(deps: ResolvedDeps, left: string, right: string): Promise<boolean> {
  const resolveReal = async (path: string): Promise<string> => {
    try {
      return await deps.realpath(path);
    } catch {
      return resolve(path);
    }
  };
  return (await resolveReal(left)) === (await resolveReal(right));
}

/**
 * Return a live daemon for `projectRoot`, spawning one if necessary.
 *
 * Stale pid files (unparseable, dead pid, or failing health) are deleted before
 * spawning. Never automatically retries mutating RPC requests.
 */
export async function ensureDaemon(
  projectRoot: string,
  options: EnsureDaemonOptions = {},
): Promise<EnsureDaemonResult> {
  if (projectRoot === "") {
    throw new DaemonStartError("projectRoot must be a non-empty path");
  }
  const deps = resolveDeps(options.deps);
  const home = options.atomcHome ?? join(deps.homeDir(), ".atomc");
  const pidPath = join(home, "daemon.json");
  const logPath = join(home, "daemon.log");
  const timeoutMs = options.timeoutMs ?? 30_000;

  const existing = await readDaemonInfo(deps, pidPath);
  if (existing !== undefined && (await validateDaemon(deps, existing))) {
    if (!(await sameProjectRoot(deps, existing.project_root, projectRoot))) {
      throw new DaemonStartError(
        `A daemon is already running for project ${existing.project_root}, not ${projectRoot}. ` +
          "Run 'atomc daemon stop' first (or use the same project), then retry.",
      );
    }
    const client = await deps.connect({ url: daemonWebSocketUrl(existing), token: existing.token });
    return { info: existing, started: false, client };
  }
  if (existing !== undefined) {
    await deps.removeFile(pidPath).catch(() => undefined);
  }

  await deps.mkdirp(home);
  const uv = options.uvCommand ?? "uv";
  const daemon = options.daemonCommand ?? "atomcd";
  const uvProject = options.uvProject ?? process.env.ATOMC_REPO;
  const args = ["run"];
  if (uvProject !== undefined && uvProject !== "") {
    args.push("--project", uvProject);
  }
  args.push(daemon, "serve", "--project", projectRoot);

  const env: NodeJS.ProcessEnv = { ...process.env, ...options.env };
  options.log?.(`[atomc] starting daemon: ${uv} ${args.join(" ")}`);
  const child = deps.spawnDaemon(uv, args, { cwd: projectRoot, env, logPath });

  const start = deps.now();
  let delay = options.initialDelayMs ?? 50;
  const maxDelay = options.maxDelayMs ?? 1000;
  const factor = options.backoffFactor ?? 1.6;

  for (;;) {
    if (child.error !== undefined) {
      throw new DaemonStartError(`Failed to start daemon: ${child.error.message}`);
    }
    const info = await readDaemonInfo(deps, pidPath);
    if (info !== undefined && (await validateDaemon(deps, info))) {
      const client = await deps.connect({ url: daemonWebSocketUrl(info), token: info.token });
      return { info, started: true, client };
    }
    if (deps.now() - start >= timeoutMs) {
      child.kill?.("SIGTERM");
      throw new DaemonStartError(
        `Timed out after ${timeoutMs} ms waiting for daemon (logs: ${logPath})`,
      );
    }
    await deps.sleep(delay);
    delay = Math.min(delay * factor, maxDelay);
  }
}
