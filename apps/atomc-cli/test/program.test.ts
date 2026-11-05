import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import { runCli } from "../src/program.js";
import { makeDeps } from "./helpers/fakes.js";

describe("atomc program", () => {
  it("prints help and exits 0", async () => {
    const { deps, captured } = makeDeps();
    const code = await runCli(deps, ["--help"]);
    expect(code).toBe(0);
    expect(captured.out.join("")).toContain("Usage: atomc");
    expect(captured.out.join("")).toContain("doctor");
  });

  it("prints the version", async () => {
    const { deps, captured } = makeDeps();
    const code = await runCli(deps, ["--version"]);
    expect(code).toBe(0);
    expect(captured.out.join("").trim()).toBe("0.0.1");
  });

  it("exits non-zero on an unknown command", async () => {
    const { deps } = makeDeps();
    const code = await runCli(deps, ["frobnicate"]);
    expect(code).toBe(1);
  });

  it("keeps --json stdout to a single JSON document", async () => {
    const { deps, captured } = makeDeps();
    const code = await runCli(deps, ["doctor", "--json"]);
    expect(code).toBe(0);
    expect(captured.out).toHaveLength(1);
    expect(() => JSON.parse(captured.out.join(""))).not.toThrow();
    expect(captured.err).toEqual([]);
  });

  it("stays version-locked to scripts/release/VERSION", async () => {
    const version = (
      await readFile(new URL("../../../scripts/release/VERSION", import.meta.url), "utf8")
    ).trim();
    const { deps } = makeDeps();
    expect(deps.cliVersion).toBe(version);
  });

  it("reports unexpected handler errors and exits 1", async () => {
    const { deps, captured } = makeDeps();
    deps.ensureDaemon = async () => {
      throw new Error("daemon unavailable");
    };
    const code = await runCli(deps, ["build"]);
    expect(code).toBe(1);
    expect(captured.err.join("")).toContain("daemon unavailable");
  });
});
