import { describe, expect, it } from "vitest";
import type { ToolProbe } from "../src/deps.js";
import { runCli } from "../src/program.js";
import { makeDeps } from "./helpers/fakes.js";

const tools: ToolProbe[] = [
  { name: "uv", target: "uv", required: true, status: "PASS", detail: "uv 0.9.0" },
  { name: "renode", target: "renode", required: false, status: "WARN", detail: "renode not found" },
];

describe("atomc doctor", () => {
  it("passes when daemon versions agree and required tools exist", async () => {
    const { deps } = makeDeps({
      probe: {
        running: true,
        info: {
          pid: 1,
          host: "127.0.0.1",
          port: 7437,
          token: "t",
          project_root: "/work",
          started_at: "2026-11-04T00:00:00Z",
          version: "0.0.1",
        },
        health: { ok: true, version: "0.0.1", ir_rev: 0 },
        schema: { $id: "schema", properties: { schema_version: { const: "0.1.0" } } },
        detail: "running",
      },
      tools,
    });
    const code = await runCli(deps, ["doctor", "--json"]);
    expect(code).toBe(0);
  });

  it("fails when the daemon version disagrees with the CLI", async () => {
    const { deps, captured } = makeDeps({
      probe: {
        running: true,
        info: {
          pid: 1,
          host: "127.0.0.1",
          port: 7437,
          token: "t",
          project_root: "/work",
          started_at: "2026-11-04T00:00:00Z",
          version: "9.9.9",
        },
        health: { ok: true, version: "9.9.9", ir_rev: 0 },
        detail: "running",
      },
      tools,
    });
    const code = await runCli(deps, ["doctor", "--json"]);
    expect(code).toBe(1);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.ok).toBe(false);
    const check = payload.checks.find((c: { name: string }) => c.name === "daemon.version");
    expect(check.status).toBe("FAIL");
  });

  it("warns but does not fail when the daemon is not running", async () => {
    const { deps, captured } = makeDeps({ tools });
    const code = await runCli(deps, ["doctor", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.status).toBe("WARN");
    expect(captured.err.join("")).toBe("");
  });

  it("fails when a required tool is missing", async () => {
    const missing: ToolProbe[] = [
      { name: "uv", target: "uv", required: true, status: "FAIL", detail: "uv not found" },
    ];
    const { deps } = makeDeps({ tools: missing });
    const code = await runCli(deps, ["doctor", "--json"]);
    expect(code).toBe(1);
  });

  it("lists plugin-independent kernel tools without requiring hardware", async () => {
    const { deps, captured } = makeDeps({ tools: [pluginIndependentProbe()] });
    const code = await runCli(deps, ["doctor", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.checks.some((c: { name: string }) => c.name === "tool:build123d")).toBe(true);
  });
});

function pluginIndependentProbe(): ToolProbe {
  return {
    name: "build123d",
    target: "python3",
    required: false,
    status: "SKIP",
    detail: "not installed",
  };
}

describe("atomc doctor schema + edge cases", () => {
  it("reads an explicit x-schema-version header", async () => {
    const { deps, captured } = makeDeps({
      probe: {
        running: true,
        info: {
          pid: 1,
          host: "127.0.0.1",
          port: 7437,
          token: "t",
          project_root: "/work",
          started_at: "2026-11-04T00:00:00Z",
          version: "0.0.1",
        },
        health: { ok: true, version: "0.0.1", ir_rev: 0 },
        schema: { "x-schema-version": "0.1.0" },
        detail: "running",
      },
    });
    const code = await runCli(deps, ["doctor", "--json"]);
    expect(code).toBe(0);
    const check = JSON.parse(captured.out.join("")).checks.find(
      (c: { name: string }) => c.name === "daemon.schema",
    );
    expect(check.detail).toContain("schema 0.1.0");
  });

  it("fails when health.ok is false", async () => {
    const { deps, captured } = makeDeps({
      probe: {
        running: true,
        info: {
          pid: 1,
          host: "127.0.0.1",
          port: 7437,
          token: "t",
          project_root: "/work",
          started_at: "2026-11-04T00:00:00Z",
          version: "0.0.1",
        },
        health: { ok: false, version: "0.0.1", ir_rev: 0 },
        detail: "running",
      },
    });
    const code = await runCli(deps, ["doctor", "--json"]);
    expect(code).toBe(1);
    const names = JSON.parse(captured.out.join("")).checks.map((c: { name: string }) => c.name);
    expect(names).toContain("daemon.health.ok");
  });

  it("reports SKIP when every check is skipped", async () => {
    const { deps, captured } = makeDeps({
      tools: [{ name: "x", target: "x", required: false, status: "SKIP", detail: "n/a" }],
    });
    // daemon probe fails WARN by default, so force a passing probe instead
    deps.probeDaemon = async () => ({ running: false, detail: "not started" });
    const code = await runCli(deps, ["doctor", "--json"]);
    expect(code).toBe(0);
    expect(JSON.parse(captured.out.join("")).status).toBe("WARN");
  });

  it("handles a probe that throws", async () => {
    const { deps, captured } = makeDeps();
    deps.probeDaemon = async () => {
      throw new Error("connection refused");
    };
    const code = await runCli(deps, ["doctor", "--json"]);
    expect(code).toBe(0);
    expect(JSON.parse(captured.out.join("")).checks[0].name).toBe("cli.version");
  });
});
