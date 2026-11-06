import { describe, expect, it, vi } from "vitest";
import { createConvergenceRuntime } from "../src/commands/converge.js";
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
    const { deps } = makeDeps();
    expect(await runCli(deps, ["converge", "--max-rounds", "0"])).toBe(2);
    expect(await runCli(deps, ["converge", "--max-cost", "1.001"])).toBe(2);
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
});
