/**
 * Dev host bridge plugin tests (no daemon, no sockets: internals only).
 *
 * The end-to-end path (browser -> vite proxy -> real daemon) is verified by the
 * live-mode smoke: start a daemon for an example project, run
 * `pnpm --filter @atomc/studio dev`, open
 * `/?demo=false&project=<name>&path=<dir>` and confirm real data renders.
 */
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { __internals, devHostBridge } from "../dev-host/plugin.js";

const { readDaemonState, METHODS, PROXY_PATH, BRIDGE_PATH } = __internals;

describe("dev host bridge", () => {
  it("only forwards the read/run surface Studio needs", () => {
    expect([...METHODS].sort()).toEqual([
      "dag.run",
      "dag.status",
      "gates.list",
      "ir.get",
      "tools.list",
    ]);
    // Mutating methods a browser page must never reach:
    for (const forbidden of [
      "ir.transact",
      "ir.lock",
      "ir.unlock",
      "tools.call",
      "daemon.shutdown",
    ]) {
      expect(METHODS.has(forbidden)).toBe(false);
    }
  });

  it("reads daemon state that stays server-side", () => {
    const home = mkdtempSync(join(tmpdir(), "atomc-devhost-"));
    mkdirSync(join(home, ".atomc"), { recursive: true });
    writeFileSync(
      join(home, ".atomc", "daemon.json"),
      JSON.stringify({ pid: 1, host: "127.0.0.1", port: 7437, token: "sekret" }),
    );
    const state = readDaemonState(home);
    expect(state).toMatchObject({ host: "127.0.0.1", port: 7437, token: "sekret" });
  });

  it("returns undefined for a missing or malformed daemon.json", () => {
    const home = mkdtempSync(join(tmpdir(), "atomc-devhost-"));
    expect(readDaemonState(home)).toBeUndefined();
    const state = mkdtempSync(join(tmpdir(), "atomc-devhost-"));
    mkdirSync(join(state, ".atomc"), { recursive: true });
    writeFileSync(join(state, ".atomc", "daemon.json"), "{not json");
    expect(readDaemonState(state)).toBeUndefined();
  });

  it("exposes the plugin only in serve mode with dev-only paths", () => {
    const plugin = devHostBridge();
    expect(plugin.apply).toBe("serve");
    expect(PROXY_PATH.startsWith("/@dev-host/")).toBe(true);
    expect(BRIDGE_PATH.startsWith("/@dev-host/")).toBe(true);
  });
});
