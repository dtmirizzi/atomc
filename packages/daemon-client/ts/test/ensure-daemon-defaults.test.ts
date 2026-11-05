import { writeFileSync } from "node:fs";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { WebSocketServer } from "ws";
import { DaemonClient, DaemonStartError, ensureDaemon } from "../src/index.js";

let home: string;
let httpServer: Server;
let wss: WebSocketServer;
let port: number;

beforeEach(async () => {
  home = await mkdtemp(join(tmpdir(), "atomc-daemon-client-"));
  httpServer = createServer((request, response) => {
    if (request.url === "/health") {
      response.setHeader("content-type", "application/json");
      response.end(JSON.stringify({ ok: true, version: "0.0.1", ir_rev: 0 }));
      return;
    }
    response.statusCode = 404;
    response.end("not found");
  });
  wss = new WebSocketServer({ server: httpServer });
  await new Promise<void>((resolve) => {
    httpServer.listen(0, "127.0.0.1", () => {
      resolve();
    });
  });
  port = (httpServer.address() as AddressInfo).port;
});

afterEach(async () => {
  wss.close();
  await new Promise<void>((resolve) => {
    httpServer.close(() => {
      resolve();
    });
  });
  await rm(home, { recursive: true, force: true });
});

function info(overrides: Record<string, unknown> = {}): string {
  return JSON.stringify({
    pid: process.pid,
    host: "127.0.0.1",
    port,
    token: "defaults-token",
    project_root: "/proj",
    started_at: new Date().toISOString(),
    version: "0.0.1",
    ...overrides,
  });
}

describe("ensureDaemon default dependencies", () => {
  it("reuses a healthy daemon using the real fs, pid check, health check, and connect", async () => {
    await writeFile(join(home, "daemon.json"), info());
    const result = await ensureDaemon("/proj", { atomcHome: home, timeoutMs: 2000 });
    expect(result.started).toBe(false);
    expect(result.client).toBeInstanceOf(DaemonClient);
    await result.client.close();
  });

  it("deletes a dead-pid file and waits for a spawned daemon with default fs/health/connect", async () => {
    const pidPath = join(home, "daemon.json");
    await writeFile(pidPath, info({ pid: 999_999, token: "old" }));
    const spawnCalls: unknown[] = [];
    const result = await ensureDaemon("/proj", {
      atomcHome: home,
      timeoutMs: 2000,
      initialDelayMs: 10,
      deps: {
        spawnDaemon: (command, args) => {
          spawnCalls.push({ command, args });
          writeFileSync(pidPath, info({ token: "new" }));
          return { pid: process.pid };
        },
      },
    });
    expect(spawnCalls).toHaveLength(1);
    expect(result.started).toBe(true);
    expect(result.info.token).toBe("new");
    await result.client.close();
  });

  it("spawns through the default process layer and times out when no daemon appears", async () => {
    await expect(
      ensureDaemon("/proj", {
        atomcHome: home,
        uvCommand: process.execPath,
        daemonCommand: "definitely-not-a-script",
        timeoutMs: 150,
        initialDelayMs: 20,
        maxDelayMs: 40,
      }),
    ).rejects.toBeInstanceOf(DaemonStartError);
  });
});
