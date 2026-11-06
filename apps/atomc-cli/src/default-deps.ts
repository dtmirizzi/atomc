/** Default (real) implementations of every {@link CliDeps} member. */
import { spawnSync } from "node:child_process";
import { access, copyFile, mkdir, readdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import type { DaemonInfo, HealthResult } from "@atomc/daemon-client";
import {
  DaemonClient,
  daemonWebSocketUrl,
  ensureDaemon as ensureDaemonClient,
} from "@atomc/daemon-client";
import type { CliDeps, DaemonHandle, DaemonProbe, FsLike, ToolProbe } from "./deps.js";

const CLI_VERSION = "0.0.1";

const defaultFs: FsLike = {
  mkdir: (path, options) => mkdir(path, options),
  readFile: (path, encoding) => readFile(path, encoding),
  writeFile: (path, data) => writeFile(path, data),
  readdir: (path) => readdir(path, { withFileTypes: true }),
  stat: (path) => stat(path),
  copyFile: (src, dest) => copyFile(src, dest),
  rm: (path, options) => rm(path, options),
  access: (path) => access(path),
};

function atomcHome(env: NodeJS.ProcessEnv): string {
  return env.ATOMC_HOME && env.ATOMC_HOME !== "" ? env.ATOMC_HOME : join(homedir(), ".atomc");
}

function localHost(host: string): string {
  return host === "0.0.0.0" || host === "::" ? "127.0.0.1" : host;
}

function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}

function parseInfo(value: unknown): DaemonInfo | undefined {
  if (value === null || typeof value !== "object") return undefined;
  const o = value as Record<string, unknown>;
  if (
    typeof o.pid !== "number" ||
    typeof o.host !== "string" ||
    typeof o.port !== "number" ||
    typeof o.token !== "string" ||
    typeof o.project_root !== "string" ||
    typeof o.started_at !== "string" ||
    typeof o.version !== "string"
  ) {
    return undefined;
  }
  return o as unknown as DaemonInfo;
}

async function readInfo(env: NodeJS.ProcessEnv): Promise<DaemonInfo | undefined> {
  try {
    const text = await readFile(join(atomcHome(env), "daemon.json"), "utf8");
    return parseInfo(JSON.parse(text));
  } catch {
    return undefined;
  }
}

async function health(info: DaemonInfo): Promise<HealthResult | undefined> {
  try {
    const response = await fetch(`http://${localHost(info.host)}:${info.port}/health`, {
      signal: AbortSignal.timeout(2000),
    });
    if (!response.ok) return undefined;
    return (await response.json()) as HealthResult;
  } catch {
    return undefined;
  }
}

async function connect(info: DaemonInfo): Promise<DaemonHandle> {
  const client = await DaemonClient.connect({
    url: daemonWebSocketUrl(info),
    token: info.token,
  });
  return {
    info,
    started: false,
    client: client as unknown as DaemonHandle["client"],
  };
}

/** Walk up from the current directory to the repo root (dir with pnpm-workspace.yaml). */
async function findRepoRoot(): Promise<string> {
  let dir = process.cwd();
  for (let i = 0; i < 12; i += 1) {
    try {
      await access(join(dir, "pnpm-workspace.yaml"));
      return dir;
    } catch {
      const parent = dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  }
  return process.cwd();
}

async function probeDaemon(env: NodeJS.ProcessEnv): Promise<DaemonProbe> {
  const info = await readInfo(env);
  if (info === undefined) return { running: false, detail: "no daemon.json (daemon not started)" };
  if (!isAlive(info.pid)) {
    return { running: false, info, detail: `stale daemon.json (pid ${info.pid} not alive)` };
  }
  const h = await health(info);
  if (h === undefined)
    return { running: false, info, detail: `daemon pid ${info.pid} not responding` };
  let schema: Record<string, unknown> | undefined;
  try {
    const response = await fetch(`http://${localHost(info.host)}:${info.port}/schema`, {
      signal: AbortSignal.timeout(2000),
    });
    if (response.ok) schema = (await response.json()) as Record<string, unknown>;
  } catch {
    schema = undefined;
  }
  return { running: true, info, health: h, ...(schema ? { schema } : {}), detail: "running" };
}

function runProbe(
  name: string,
  target: string,
  command: string,
  args: string[],
  required: boolean,
): ToolProbe {
  const result = spawnSync(command, args, { encoding: "utf8", timeout: 10_000 });
  if (result.error) {
    return {
      name,
      target,
      required,
      status: required ? "FAIL" : "WARN",
      detail: `${command} not found (${result.error.message})`,
    };
  }
  if (result.status !== 0) {
    return {
      name,
      target,
      required,
      status: required ? "FAIL" : "WARN",
      detail: `${command} exited ${result.status}`,
    };
  }
  const text = `${result.stdout ?? ""}`.trim().split("\n")[0] ?? "";
  return { name, target, required, status: "PASS", detail: text || `${command} ok` };
}

async function probeTools(): Promise<ToolProbe[]> {
  return [
    runProbe("uv", "uv", "uv", ["--version"], true),
    runProbe("atopile", "ato", "ato", ["--version"], false),
    runProbe("qmk", "qmk", "qmk", ["--version"], false),
    runProbe("renode", "renode", "renode", ["--version"], false),
    runProbe(
      "build123d",
      "python3",
      "python3",
      ["-c", "import build123d; print(build123d.__version__)"],
      false,
    ),
  ];
}

/** Build the production dependency bundle. */
export function createDefaultDeps(overrides: Partial<CliDeps> = {}): CliDeps {
  const env = overrides.env ?? process.env;
  return {
    io: overrides.io ?? {
      out: (text) => process.stdout.write(text),
      err: (text) => process.stderr.write(text),
    },
    cwd: overrides.cwd ?? process.cwd(),
    env,
    fs: overrides.fs ?? defaultFs,
    now: overrides.now ?? (() => new Date()),
    sleep: overrides.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms))),
    findRepoRoot: overrides.findRepoRoot ?? findRepoRoot,
    ensureDaemon:
      overrides.ensureDaemon ??
      (async (projectRoot) => {
        // Resolve the repository that carries the atomcd entry point so scaffolded
        // projects (outside this checkout) can still start the daemon: `uv run
        // atomcd` needs the workspace root, which ATOMC_REPO also provides.
        // ATOMC_HOME keeps daemon state alongside findDaemon's location.
        const uvProject =
          env.ATOMC_REPO && env.ATOMC_REPO !== "" ? env.ATOMC_REPO : await findRepoRoot();
        const result = await ensureDaemonClient(projectRoot, {
          uvProject,
          ...(env.ATOMC_HOME && env.ATOMC_HOME !== "" ? { atomcHome: env.ATOMC_HOME } : {}),
        });
        return {
          info: result.info,
          started: result.started,
          client: result.client as unknown as DaemonHandle["client"],
        };
      }),
    findDaemon:
      overrides.findDaemon ??
      (async () => {
        const info = await readInfo(env);
        if (info === undefined || !isAlive(info.pid)) return undefined;
        if ((await health(info)) === undefined) return undefined;
        return connect(info);
      }),
    probeDaemon: overrides.probeDaemon ?? (() => probeDaemon(env)),
    probeTools: overrides.probeTools ?? probeTools,
    cliVersion: overrides.cliVersion ?? CLI_VERSION,
  };
}

export { CLI_VERSION };
