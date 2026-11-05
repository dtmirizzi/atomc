import { describe, expect, it } from "vitest";
import { runCli } from "../src/program.js";
import { FakeDaemon, makeDeps, SAMPLE_INFO } from "./helpers/fakes.js";

describe("atomc daemon", () => {
  it("starts and reports the daemon", async () => {
    const daemon = new FakeDaemon({ started: true });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["daemon", "start", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.started).toBe(true);
    expect(payload.pid).toBe(SAMPLE_INFO.pid);
    expect(daemon.closed).toBe(true);
  });

  it("reports not running when no daemon is discoverable", async () => {
    const { deps, captured } = makeDeps({ findDaemonResult: undefined });
    const code = await runCli(deps, ["daemon", "status", "--json"]);
    expect(code).toBe(0);
    expect(JSON.parse(captured.out.join("")).running).toBe(false);
  });

  it("reports live daemon status", async () => {
    const daemon = new FakeDaemon();
    const { deps, captured } = makeDeps({ findDaemonResult: daemon.handle });
    const code = await runCli(deps, ["daemon", "status", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.running).toBe(true);
    expect(payload.uptime_ms).toBe(1000);
  });

  it("stops a running daemon", async () => {
    const daemon = new FakeDaemon();
    const { deps, captured } = makeDeps({ findDaemonResult: daemon.handle });
    const code = await runCli(deps, ["daemon", "stop", "--json"]);
    expect(code).toBe(0);
    expect(daemon.shutdownCalled).toBe(true);
    expect(JSON.parse(captured.out.join("")).stopped).toBe(true);
  });

  it("reports a no-op stop when nothing is running", async () => {
    const { deps, captured } = makeDeps({ findDaemonResult: undefined });
    const code = await runCli(deps, ["daemon", "stop", "--json"]);
    expect(code).toBe(0);
    expect(JSON.parse(captured.out.join("")).stopped).toBe(false);
  });

  it("prints human output for every daemon subcommand", async () => {
    const daemon = new FakeDaemon({ started: true });
    const start = makeDeps({ daemon });
    await runCli(start.deps, ["daemon", "start"]);
    expect(start.captured.err.join("")).toContain("started daemon pid");

    const status = makeDeps({ findDaemonResult: daemon.handle });
    await runCli(status.deps, ["daemon", "status"]);
    expect(status.captured.err.join("")).toContain("daemon: running");

    const stop = makeDeps({ findDaemonResult: daemon.handle });
    await runCli(stop.deps, ["daemon", "stop"]);
    expect(stop.captured.err.join("")).toContain("daemon: stopped");

    const none = makeDeps({ findDaemonResult: undefined });
    await runCli(none.deps, ["daemon", "status"]);
    expect(none.captured.err.join("")).toContain("not running");
  });
});
