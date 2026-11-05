/**
 * Daemon lifecycle contract: `daemon.status`, `daemon.shutdown`, process exit,
 * pid-file cleanup, and stale pid-file handling on start.
 */
import type { DaemonClient } from "@atomc/daemon-client";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { DaemonHarness } from "./harness.js";

describe("daemon.status and shutdown", () => {
  let harness: DaemonHarness;
  let client: DaemonClient;

  beforeAll(async () => {
    harness = await DaemonHarness.start();
    client = await harness.connect();
  }, 300_000);

  afterAll(async () => {
    await harness.stop();
  });

  it("reports live daemon metadata from daemon.status", async () => {
    const state = await harness.readState();
    expect(state).not.toBeNull();
    const status = await client.daemonStatus();
    expect(status.pid).toBe(state?.pid);
    expect(status.host).toBe("127.0.0.1");
    expect(status.port).toBe(harness.port);
    expect(status.project_root).toBe(state?.project_root);
    expect(status.uptime_ms).toBeGreaterThanOrEqual(0);
  });

  it("shuts down on request, exits the process and removes the pid file", async () => {
    const result = await client.shutdown();
    expect(result.shutting_down).toBe(true);

    const exited = await harness.waitForProcessExit(20_000);
    expect(exited).toBe(true);

    const deadline = Date.now() + 10_000;
    while (Date.now() < deadline && (await harness.pidFileExists())) {
      await new Promise((done) => setTimeout(done, 50));
    }
    expect(await harness.pidFileExists()).toBe(false);
    expect(await harness.readState()).toBeNull();
  });
});

describe("stale pid-file handling", () => {
  let harness: DaemonHarness;

  beforeAll(async () => {
    harness = await DaemonHarness.start({ staleState: true });
  }, 300_000);

  afterAll(async () => {
    await harness.stop();
  });

  it("clears a dead-pid daemon.json and writes the live pid", async () => {
    const state = await harness.readState();
    expect(state).not.toBeNull();
    expect(state?.pid).toBe(harness.pid);
    expect(state?.pid).toBeGreaterThan(0);
    // The stale placeholder had pid 0 and port 1; both must be replaced.
    expect(state?.port).toBe(harness.port);
    expect(state?.version).not.toBe("0.0.0");
  });
});
