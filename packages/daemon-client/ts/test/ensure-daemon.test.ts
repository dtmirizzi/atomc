import { afterEach, describe, expect, it, vi } from "vitest";
import type { SpawnDaemonOptions } from "../src/index.js";
import {
  type DaemonClient,
  type DaemonInfo,
  DaemonStartError,
  daemonWebSocketUrl,
  type EnsureDaemonDeps,
  type EnsureDaemonResult,
  ensureDaemon,
} from "../src/index.js";

const BASE: DaemonInfo = {
  pid: 1234,
  host: "127.0.0.1",
  port: 7437,
  token: "super-secret-token",
  project_root: "/proj",
  started_at: "2026-11-04T00:00:00Z",
  version: "0.0.1",
};

const PID_PATH = "/home/test/.atomc/daemon.json";

interface Harness {
  deps: EnsureDaemonDeps;
  files: Map<string, string>;
  spawnCalls: Array<{ command: string; args: string[]; options: SpawnDaemonOptions }>;
  connectCalls: Array<{ url?: string; token?: string }>;
  logs: string[];
  sleeps: number[];
  setAlive(value: boolean): void;
  setHealthy(value: boolean): void;
  setHealthAfter(polls: number): void;
  setWriteOnSpawn(value: boolean): void;
  kill: ReturnType<typeof vi.fn>;
}

function harness(initialRaw?: string): Harness {
  const files = new Map<string, string>();
  if (initialRaw !== undefined) files.set(PID_PATH, initialRaw);
  const spawnCalls: Harness["spawnCalls"] = [];
  const connectCalls: Harness["connectCalls"] = [];
  const logs: string[] = [];
  const sleeps: number[] = [];
  const kill = vi.fn(() => true);
  let alive = true;
  let healthy = true;
  let healthAfter = 0;
  let healthPolls = 0;
  let writeOnSpawn = true;
  let now = 0;
  const fakeClient = { fake: true } as unknown as DaemonClient;

  const deps: EnsureDaemonDeps = {
    readFile: async (path) => {
      const value = files.get(path);
      if (value === undefined) {
        const error = new Error("ENOENT") as NodeJS.ErrnoException;
        error.code = "ENOENT";
        throw error;
      }
      return value;
    },
    removeFile: async (path) => {
      files.delete(path);
    },
    mkdirp: async () => {},
    isProcessAlive: () => alive,
    healthCheck: async () => {
      healthPolls += 1;
      return healthy && healthPolls > healthAfter;
    },
    connect: async (options) => {
      connectCalls.push({
        ...(options.url === undefined ? {} : { url: options.url }),
        ...(options.token === undefined ? {} : { token: options.token }),
      });
      return fakeClient;
    },
    sleep: async (ms) => {
      sleeps.push(ms);
      now += ms;
    },
    now: () => now,
    homeDir: () => "/home/test",
    spawnDaemon: (command, args, options) => {
      spawnCalls.push({ command, args, options });
      alive = true; // the freshly spawned process is alive
      if (writeOnSpawn) files.set(PID_PATH, JSON.stringify({ ...BASE, pid: 9999 }));
      return { pid: 9999, unref: () => {}, kill };
    },
  };

  return {
    deps,
    files,
    spawnCalls,
    connectCalls,
    logs,
    sleeps,
    kill,
    setAlive: (value) => {
      alive = value;
    },
    setHealthy: (value) => {
      healthy = value;
    },
    setHealthAfter: (polls) => {
      healthAfter = polls;
    },
    setWriteOnSpawn: (value) => {
      writeOnSpawn = value;
    },
  };
}

const defaultOptions = (h: Harness) => ({
  deps: h.deps,
  uvProject: "/repo",
  log: (message: string) => h.logs.push(message),
});

afterEach(() => {
  vi.useRealTimers();
});

describe("daemonWebSocketUrl", () => {
  it("maps wildcard hosts to loopback", () => {
    expect(daemonWebSocketUrl({ host: "0.0.0.0", port: 1 })).toBe("ws://127.0.0.1:1/rpc");
    expect(daemonWebSocketUrl({ host: "::", port: 2 })).toBe("ws://127.0.0.1:2/rpc");
    expect(daemonWebSocketUrl({ host: "10.0.0.5", port: 3 })).toBe("ws://10.0.0.5:3/rpc");
  });
});

describe("ensureDaemon", () => {
  it("reuses a healthy daemon without spawning", async () => {
    const h = harness(JSON.stringify(BASE));
    const result: EnsureDaemonResult = await ensureDaemon("/proj", defaultOptions(h));

    expect(result.started).toBe(false);
    expect(result.info).toEqual(BASE);
    expect(h.spawnCalls).toHaveLength(0);
    expect(h.connectCalls[0]).toEqual({ url: "ws://127.0.0.1:7437/rpc", token: BASE.token });
  });

  it("deletes a stale dead-pid file and spawns a daemon", async () => {
    const h = harness(JSON.stringify(BASE));
    h.setAlive(false);
    const result = await ensureDaemon("/proj", defaultOptions(h));

    expect(result.started).toBe(true);
    expect(h.spawnCalls).toHaveLength(1);
    expect(h.spawnCalls[0]?.command).toBe("uv");
    expect(h.spawnCalls[0]?.args).toEqual([
      "run",
      "--project",
      "/repo",
      "atomcd",
      "serve",
      "--project",
      "/proj",
    ]);
    expect(h.spawnCalls[0]?.options.cwd).toBe("/proj");
    expect(result.info.pid).toBe(9999);
  });

  it("spawns when the pid file is absent", async () => {
    const h = harness();
    const result = await ensureDaemon("/proj", defaultOptions(h));
    expect(result.started).toBe(true);
    expect(h.spawnCalls).toHaveLength(1);
  });

  it("spawns when the pid file is corrupt or incomplete", async () => {
    const h = harness("{not json");
    const result = await ensureDaemon("/proj", defaultOptions(h));
    expect(result.started).toBe(true);

    const h2 = harness(JSON.stringify({ ...BASE, token: "" }));
    const result2 = await ensureDaemon("/proj", defaultOptions(h2));
    expect(result2.started).toBe(true);
  });

  it("spawns when an existing daemon fails its health check", async () => {
    const h = harness(JSON.stringify(BASE));
    h.setHealthAfter(1); // first (existing) poll fails, then the spawned daemon is healthy
    const result = await ensureDaemon("/proj", defaultOptions(h));
    expect(result.started).toBe(true);
  });

  it("waits with exponential backoff until the daemon is healthy", async () => {
    const h = harness();
    h.setHealthAfter(2);
    const result = await ensureDaemon("/proj", defaultOptions(h));
    expect(result.started).toBe(true);
    expect(h.sleeps.length).toBeGreaterThanOrEqual(2);
    expect(h.sleeps[1]).toBeGreaterThan(h.sleeps[0] ?? 0);
  });

  it("times out and kills the child when the daemon never becomes healthy", async () => {
    const h = harness();
    h.setWriteOnSpawn(false);
    await expect(
      ensureDaemon("/proj", { ...defaultOptions(h), timeoutMs: 100, initialDelayMs: 50 }),
    ).rejects.toBeInstanceOf(DaemonStartError);
    expect(h.kill).toHaveBeenCalledWith("SIGTERM");
  });

  it("rejects an empty project root", async () => {
    const h = harness();
    await expect(ensureDaemon("", defaultOptions(h))).rejects.toBeInstanceOf(DaemonStartError);
  });

  it("never writes the bearer token to the log sink", async () => {
    const h = harness();
    await ensureDaemon("/proj", defaultOptions(h));
    expect(h.logs.join("\n")).not.toContain(BASE.token);
  });

  it("omits --project when no repo is configured", async () => {
    const h = harness();
    const deps = { ...h.deps };
    await ensureDaemon("/proj", { deps, uvProject: "" });
    expect(h.spawnCalls[0]?.args).toEqual(["run", "atomcd", "serve", "--project", "/proj"]);
  });
});
