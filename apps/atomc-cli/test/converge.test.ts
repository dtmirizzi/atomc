import { describe, expect, it, vi } from "vitest";
import { convergeCommand, createConvergenceRuntime } from "../src/commands/converge.js";
import type { ConvergenceRunReport } from "../src/deps.js";
import { runCli } from "../src/program.js";
import { makeDeps } from "./helpers/fakes.js";

function report(status: ConvergenceRunReport["status"] = "converged"): ConvergenceRunReport {
  return {
    status,
    rounds: 2,
    costMinor: 125,
    tokens: 740,
    gateResults: [],
    failures: [],
    reasons: [],
    runs: [],
    runId: "converge-test",
  };
}

describe("atomc converge", () => {
  it("returns unavailable without a configured trusted runtime", async () => {
    const { deps, captured } = makeDeps();
    const code = await runCli(deps, ["converge", "--json"]);
    expect(code).toBe(3);
    expect(JSON.parse(captured.out.join(""))).toMatchObject({
      status: "unavailable",
      command: "converge",
    });
  });

  it("passes project and aggregate limits to the injected runtime", async () => {
    const { deps, captured } = makeDeps({ cwd: "/work" });
    const run = vi.fn(async () => report());
    deps.convergenceRuntime = { run };
    const code = await runCli(deps, [
      "converge",
      "--project",
      "board",
      "--max-rounds",
      "4",
      "--max-cost",
      "3.25",
      "--json",
    ]);
    expect(code).toBe(0);
    expect(run).toHaveBeenCalledWith(
      expect.objectContaining({ projectRoot: "/work/board", maxRounds: 4, maxCostMinor: 325 }),
    );
    const payload = JSON.parse(captured.out.join(""));
    expect(payload).toMatchObject({
      status: "converged",
      ok: true,
      costMinor: 125,
      max_cost_minor: 325,
    });
  });

  it.each(["accepted", "escalated", "budget_exhausted", "aborted"] as const)(
    "uses nonzero exit for incomplete status %s",
    async (status) => {
      const { deps, captured } = makeDeps();
      deps.convergenceRuntime = { run: async () => report(status) };
      expect(await runCli(deps, ["converge", "--json"])).toBe(1);
      expect(JSON.parse(captured.out.join(""))).toMatchObject({ status, ok: false });
    },
  );

  it("validates bounded numeric options", async () => {
    const { deps, captured } = makeDeps();
    expect(await runCli(deps, ["converge", "--max-rounds", "0"])).toBe(2);
    expect(await runCli(deps, ["converge", "--max-rounds", "abc"])).toBe(2);
    expect(await runCli(deps, ["converge", "--max-rounds", "1.5"])).toBe(2);
    expect(await runCli(deps, ["converge", "--max-cost", "1.001"])).toBe(2);
    expect(await runCli(deps, ["converge", "--max-cost", "-1"])).toBe(2);
    expect(await runCli(deps, ["converge", "--max-cost", "abc"])).toBe(2);
    // Unknown options are rejected by commander itself before reaching the command.
    expect(await runCli(deps, ["converge", "--bogus"])).toBe(1);
    expect(captured.err.join(" ")).toContain("unknown");
  });

  it("prints a human summary to stderr", async () => {
    const { deps, captured } = makeDeps();
    deps.convergenceRuntime = { run: async () => report() };
    await runCli(deps, ["converge"]);
    expect(captured.out).toEqual([]);
    expect(captured.err.join(" ")).toContain("converge converged");
  });

  it("createConvergenceRuntime forwards requests verbatim to the host function", async () => {
    const run = vi.fn(async () => report());
    const runtime = createConvergenceRuntime(run);
    const request = {
      projectRoot: "/work/board",
      maxRounds: 2,
      maxCostMinor: 200,
      signal: new AbortController().signal,
    };
    await expect(runtime.run(request)).resolves.toMatchObject({ status: "converged" });
    expect(run).toHaveBeenCalledWith(request);
  });

  it("reports a runtime error and exits nonzero without a fake PASS", async () => {
    const { deps, captured } = makeDeps();
    deps.convergenceRuntime = { run: vi.fn(async () => Promise.reject(new Error("daemon gone"))) };
    const code = await runCli(deps, ["converge", "--json"]);
    expect(code).toBe(1);
    expect(JSON.parse(captured.out.join(""))).toMatchObject({
      status: "error",
      command: "converge",
      reason: "daemon gone",
    });
  });

  it("lists remaining blockers and reasons for an escalated run", async () => {
    const { deps, captured } = makeDeps();
    const failing: ConvergenceRunReport = {
      ...report("escalated"),
      failures: [
        {
          id: "gate:erc.no_unconnected",
          status: "FAIL",
          severity: "blocking",
          plugin: "plugin:test@0.0.1",
          owner_agent: "ee-agent",
          evaluated_at: "2026-11-04T23:00:00Z",
          ir_rev: 10,
          duration_ms: 1,
          summary: "1 unconnected net",
          evidence: [],
          suggestions: [],
          refs: [],
        },
      ],
      reasons: ["blocked without a checkpoint handler: no_progress"],
    };
    deps.convergenceRuntime = { run: async () => failing };
    const code = await runCli(deps, ["converge"]);
    expect(code).toBe(1);
    const text = captured.err.join(" ");
    expect(text).toContain("gate:erc.no_unconnected");
    expect(text).toContain("ee-agent");
    expect(text).toContain("1 unconnected net");
    expect(text).toContain("no_progress");

    // Same escalated report through --json: one machine-readable object.
    const { deps: jsonDeps, captured: jsonCaptured } = makeDeps();
    jsonDeps.convergenceRuntime = { run: async () => failing };
    await runCli(jsonDeps, ["converge", "--json"]);
    const payload = JSON.parse(jsonCaptured.out.join(""));
    expect(payload).toMatchObject({ status: "escalated", ok: false });
    expect(payload.failures).toHaveLength(1);
  });

  it("direct API calls exercise default option fallbacks and unowned gates", async () => {
    const { deps, captured } = makeDeps();
    const unowned: ConvergenceRunReport = {
      ...report("escalated"),
      failures: [
        {
          id: "gate:unknown.ownerless",
          status: "FAIL",
          severity: "blocking",
          plugin: "plugin:test@0.0.1",
          owner_agent: null,
          evaluated_at: "2026-11-04T23:00:00Z",
          ir_rev: 10,
          duration_ms: 1,
          summary: "ownerless failure",
          evidence: [],
          suggestions: [],
          refs: [],
        },
      ],
    };
    deps.convergenceRuntime = { run: async () => unowned };
    // No options: project/rounds/cost all take their code defaults.
    expect(await convergeCommand(deps)).toBe(1);
    const text = captured.err.join(" ");
    expect(text).toContain("unowned");
    expect(text).toContain("ownerless");
  });

  it("stringifies non-Error runtime rejections", async () => {
    const { deps, captured } = makeDeps();
    deps.convergenceRuntime = { run: async () => Promise.reject("plain string failure") };
    const code = await convergeCommand(deps, { json: true });
    expect(code).toBe(1);
    expect(JSON.parse(captured.out.join(""))).toMatchObject({
      status: "error",
      reason: "plain string failure",
    });
  });

  it("aborts the runtime when SIGINT arrives and reports the aborted status", async () => {
    const { deps, captured } = makeDeps();
    const run = vi.fn(
      (request: { signal: AbortSignal }) =>
        new Promise<ConvergenceRunReport>((resolve) => {
          const listener = (): void => {
            // Simulate the runtime honoring the abort signal.
            resolve(report("aborted"));
          };
          request.signal.addEventListener("abort", listener, { once: true });
        }),
    );
    deps.convergenceRuntime = { run };
    const codePromise = runCli(deps, ["converge"]);
    // The command registered its handler on the real process before awaiting.
    for (let attempt = 0; attempt < 50 && run.mock.calls.length === 0; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
    process.emit("SIGINT", process);
    const code = await codePromise;
    expect(code).toBe(1);
    const lines = captured.err.join(" ");
    expect(lines).toContain("converge aborted");
  });
});
