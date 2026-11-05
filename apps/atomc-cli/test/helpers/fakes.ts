/** In-memory fakes for CLI unit tests (no daemon, no network, no real fs). */
import type {
  DaemonInfo,
  DagNodeStatus,
  GateResult,
  PluginStatus,
  Subscription,
} from "@atomc/daemon-client";
import type {
  CliDeps,
  DaemonApi,
  DaemonHandle,
  DaemonProbe,
  FsLike,
  ToolProbe,
} from "../../src/deps.js";

export interface CapturedIo {
  out: string[];
  err: string[];
}

export function makeIo(): {
  io: { out(t: string): void; err(t: string): void };
  captured: CapturedIo;
} {
  const captured: CapturedIo = { out: [], err: [] };
  return {
    captured,
    io: {
      out: (t) => captured.out.push(t),
      err: (t) => captured.err.push(t),
    },
  };
}

interface Entry {
  kind: "file" | "dir";
  data: string;
}

/** Minimal in-memory {@link FsLike}. */
export class FakeFs implements FsLike {
  readonly entries = new Map<string, Entry>();
  readonly copies: Array<[string, string]> = [];

  addFile(path: string, data = ""): void {
    this.entries.set(path, { kind: "file", data });
    let parent = path.slice(0, path.lastIndexOf("/"));
    while (parent !== "" && parent !== "/") {
      if (!this.entries.has(parent)) this.entries.set(parent, { kind: "dir", data: "" });
      parent = parent.slice(0, parent.lastIndexOf("/"));
    }
  }

  addDir(path: string): void {
    this.entries.set(path, { kind: "dir", data: "" });
  }

  async mkdir(path: string, _options: { recursive: true }): Promise<string | undefined> {
    this.entries.set(path, { kind: "dir", data: "" });
    return path;
  }

  async readFile(path: string, _encoding: "utf8"): Promise<string> {
    const entry = this.entries.get(path);
    if (entry?.kind !== "file") throw new Error(`ENOENT: ${path}`);
    return entry.data;
  }

  async writeFile(path: string, data: string): Promise<void> {
    this.addFile(path, data);
  }

  async readdir(
    path: string,
  ): Promise<Array<{ name: string; isDirectory(): boolean; isFile(): boolean }>> {
    const prefix = path.endsWith("/") ? path : `${path}/`;
    const names = new Set<string>();
    for (const key of this.entries.keys()) {
      if (!key.startsWith(prefix)) continue;
      const rest = key.slice(prefix.length);
      if (rest === "" || rest.includes("/")) continue;
      names.add(rest);
    }
    return [...names].map((name) => {
      const entry = this.entries.get(`${prefix}${name}`);
      return {
        name,
        isDirectory: () => entry?.kind === "dir",
        isFile: () => entry?.kind === "file",
      };
    });
  }

  async stat(path: string): Promise<{ isDirectory(): boolean; isFile(): boolean }> {
    const entry = this.entries.get(path);
    if (!entry) throw new Error(`ENOENT: ${path}`);
    return { isDirectory: () => entry.kind === "dir", isFile: () => entry.kind === "file" };
  }

  async copyFile(src: string, dest: string): Promise<void> {
    const entry = this.entries.get(src);
    if (!entry) throw new Error(`ENOENT: ${src}`);
    this.copies.push([src, dest]);
    this.addFile(dest, entry.data);
  }

  async rm(path: string, _options: { recursive: true; force: true }): Promise<void> {
    const prefix = `${path}/`;
    for (const key of [...this.entries.keys()]) {
      if (key === path || key.startsWith(prefix)) this.entries.delete(key);
    }
  }

  async access(path: string): Promise<void> {
    if (!this.entries.has(path)) throw new Error(`ENOENT: ${path}`);
  }
}

export const SAMPLE_INFO: DaemonInfo = {
  pid: 4242,
  host: "127.0.0.1",
  port: 7437,
  token: "secret-token",
  project_root: "/work/proj",
  started_at: "2026-11-04T00:00:00Z",
  version: "0.0.1",
};

export interface FakeDaemonOptions {
  nodes?: DagNodeStatus[];
  gates?: GateResult[];
  plugins?: PluginStatus[];
  started?: boolean;
  onRun?: (params: unknown) => void;
  subscribeThrows?: boolean;
  events?: Array<{ topic: string; data: unknown }>;
}

/** Scriptable {@link DaemonApi} fake. */
export class FakeDaemon implements DaemonApi {
  closed = false;
  shutdownCalled = false;
  runParams: unknown;
  subscriptionClosed = false;
  readonly #options: FakeDaemonOptions;

  constructor(options: FakeDaemonOptions = {}) {
    this.#options = options;
  }

  get handle(): DaemonHandle {
    return { info: SAMPLE_INFO, started: this.#options.started ?? false, client: this };
  }

  async request<T>(_method: string, _params?: unknown): Promise<T> {
    return undefined as T;
  }
  async getIR(): Promise<{ rev: number; value: unknown }> {
    return { rev: 0, value: {} };
  }
  async dagStatus(): Promise<{ nodes: DagNodeStatus[] }> {
    return { nodes: this.#options.nodes ?? [] };
  }
  async runDAG(params?: unknown): Promise<{ run_id: string }> {
    this.runParams = params;
    this.#options.onRun?.(params);
    return { run_id: "run-1" };
  }
  async listGates(): Promise<GateResult[]> {
    return this.#options.gates ?? [];
  }
  async listPlugins(): Promise<PluginStatus[]> {
    return this.#options.plugins ?? [];
  }
  async daemonStatus(): Promise<{
    pid: number;
    host: string;
    port: number;
    version: string;
    project_root: string;
    uptime_ms: number;
  }> {
    return {
      pid: SAMPLE_INFO.pid,
      host: SAMPLE_INFO.host,
      port: SAMPLE_INFO.port,
      version: SAMPLE_INFO.version,
      project_root: SAMPLE_INFO.project_root,
      uptime_ms: 1000,
    };
  }
  async subscribe(
    _topics: readonly string[],
    listener: (event: { topic: string; data: unknown }) => void,
  ): Promise<Subscription> {
    if (this.#options.subscribeThrows) throw new Error("subscribe unsupported");
    for (const event of this.#options.events ?? []) listener(event);
    return {
      id: "sub-1",
      topics: [],
      unsubscribe: async () => {
        this.subscriptionClosed = true;
      },
    };
  }
  async shutdown(): Promise<{ shutting_down: true }> {
    this.shutdownCalled = true;
    return { shutting_down: true };
  }
  async close(): Promise<void> {
    this.closed = true;
  }
}

export function getFile(fs: FakeFs, path: string): string {
  const entry = fs.entries.get(path);
  if (!entry) throw new Error(`missing fake file: ${path}`);
  return entry.data;
}

export function pluginStatus(name: string, loaded: boolean, error?: string): PluginStatus {
  return {
    manifest_version: "0.1.0",
    name,
    version: "0.0.1",
    description: `${name} plugin`,
    atomc: ">=0.0.1 <0.2.0",
    runtime: { ts: "./dist/index.js" },
    watches: [],
    produces: [],
    gates: [],
    tools: [],
    cli: [],
    ui: [],
    loaded,
    ...(error ? { error } : {}),
  };
}

export interface MakeDepsOptions {
  daemon?: FakeDaemon;
  daemonHandle?: DaemonHandle;
  findDaemonResult?: DaemonHandle | undefined;
  probe?: DaemonProbe;
  tools?: ToolProbe[];
  fs?: FakeFs;
  cwd?: string;
  now?: Date;
  repoRoot?: string;
  sleep?: (ms: number) => Promise<void>;
}

export function makeDeps(options: MakeDepsOptions = {}) {
  const { io, captured } = makeIo();
  const fs = options.fs ?? new FakeFs();
  const daemon = options.daemon;
  const handle = options.daemonHandle ??
    daemon?.handle ?? { info: SAMPLE_INFO, started: false, client: daemon as DaemonApi };
  const baseTime = (options.now ?? new Date("2026-11-04T00:00:00Z")).getTime();
  let tick = 0;
  const deps: CliDeps = {
    io,
    cwd: options.cwd ?? "/work",
    env: {},
    fs,
    now: () => new Date(baseTime + tick++ * 100),
    sleep: options.sleep ?? (async () => undefined),
    findRepoRoot: async () => options.repoRoot ?? "/repo",
    ensureDaemon: async () => handle,
    findDaemon: async () => options.findDaemonResult,
    probeDaemon: async () =>
      options.probe ?? { running: false, detail: "no daemon.json (daemon not started)" },
    probeTools: async () => options.tools ?? [],
    cliVersion: "0.0.1",
  };
  return { deps, captured, fs, daemon };
}
