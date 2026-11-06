/** Run the swarm convergence loop; model/daemon construction is injected by the host. */
import { resolve } from "node:path";
import type { CliDeps, ConvergenceRunReport, ConvergenceRunRequest } from "../deps.js";
import { CliError, EXIT_UNAVAILABLE } from "../errors.js";
import { emit } from "../output.js";

export interface ConvergeCommandOptions {
  project?: string;
  maxRounds?: string;
  maxCost?: string;
  json?: boolean;
}

/** Project/environment-specific trust boundary for model and daemon construction. */
export function createConvergenceRuntime(
  run: (request: ConvergenceRunRequest) => Promise<ConvergenceRunReport>,
): NonNullable<CliDeps["convergenceRuntime"]> {
  return { run };
}

function positiveInteger(option: string, raw: string | undefined, fallback: number): number {
  if (raw === undefined) return fallback;
  const parsed = Number(raw);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    throw new CliError(`invalid ${option} value "${raw}" (expected a positive integer)`, 2);
  }
  return parsed;
}

/** maxCost is entered in dollars and converted to integer USD cents. */
function costMinor(raw: string | undefined): number {
  if (raw === undefined) return 200;
  const dollars = Number(raw);
  if (!Number.isFinite(dollars) || dollars <= 0 || !Number.isSafeInteger(dollars * 100)) {
    throw new CliError(
      `invalid --max-cost value "${raw}" (expected positive dollars with at most two decimals)`,
      2,
    );
  }
  return dollars * 100;
}

/** Exit code: 0 converged, 1 incomplete/escalated, 3 runtime unavailable. */
export async function convergeCommand(
  deps: CliDeps,
  options: ConvergeCommandOptions = {},
): Promise<number> {
  const projectRoot = resolve(deps.cwd, options.project ?? ".");
  const maxRounds = positiveInteger("--max-rounds", options.maxRounds, 3);
  const maxCostMinor = costMinor(options.maxCost);
  const runtime = deps.convergenceRuntime;
  if (runtime === undefined) {
    const payload = {
      status: "unavailable",
      command: "converge",
      project: projectRoot,
      max_rounds: maxRounds,
      max_cost_minor: maxCostMinor,
      reason: "no convergence runtime is configured by this CLI host",
      hint: "configure a trusted convergence runtime or use the harness SDK",
    };
    emit(deps, options.json === true, payload, [
      "atomc converge: unavailable — no convergence runtime is configured by this CLI host",
      `  hint: ${payload.hint}`,
    ]);
    return EXIT_UNAVAILABLE;
  }

  const controller = new AbortController();
  const onSigint = (): void => controller.abort();
  process.once("SIGINT", onSigint);

  try {
    const report = await runtime.run({
      projectRoot,
      maxRounds,
      maxCostMinor,
      signal: controller.signal,
    });
    const payload = {
      ...report,
      ok: report.status === "converged",
      project: projectRoot,
      max_rounds: maxRounds,
      max_cost_minor: maxCostMinor,
    };
    emit(deps, options.json === true, payload, [
      `converge ${report.status} after ${report.rounds} round(s) · $${(report.costMinor / 100).toFixed(2)} spent`,
      `gates: ${report.failures.length} blocking failure(s) remain`,
      ...report.failures.map(
        (gate) => `  ${gate.id} · ${gate.owner_agent ?? "unowned"} · ${gate.summary}`,
      ),
      ...report.reasons.map((reason) => `  ${reason}`),
    ]);
    return report.status === "converged" ? 0 : 1;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const payload = { status: "error", command: "converge", reason: message };
    emit(deps, options.json === true, payload, [`atomc converge: error — ${message}`]);
    return 1;
  } finally {
    process.removeListener("SIGINT", onSigint);
  }
}
