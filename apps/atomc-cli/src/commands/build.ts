/** `atomc build [target]` — run the daemon DAG and summarize nodes + gates. */
import { resolve } from "node:path";
import type { CliDeps, DaemonApi } from "../deps.js";
import { CliError } from "../errors.js";
import { emit } from "../output.js";

export interface BuildOptions {
  json?: boolean;
  project?: string;
  force?: boolean;
  timeout?: string;
}

const DEFAULT_POLL_MS = 250;
const DEFAULT_TIMEOUT_MS = 120_000;

/** Attach a best-effort event subscription, ignoring daemons without support. */
async function subscribe(
  client: DaemonApi,
  deps: CliDeps,
): Promise<{ close(): Promise<void> } | undefined> {
  try {
    const subscription = await client.subscribe(
      ["dag.node.start", "dag.node.end", "gate.result"],
      (event) => {
        if (event.topic === "dag.node.end") {
          const data = event.data as { id?: string; ok?: boolean; error?: string };
          if (data.ok === false)
            deps.io.err(`[dag] ${data.id ?? "?"} failed: ${data.error ?? ""}\n`);
        }
      },
    );
    return { close: () => subscription.unsubscribe().catch(() => undefined) };
  } catch {
    return undefined;
  }
}

/** Run `atomc build`; returns the process exit code. */
export async function buildCommand(
  deps: CliDeps,
  target: string | undefined,
  options: BuildOptions = {},
): Promise<number> {
  const projectRoot = resolve(deps.cwd, options.project ?? ".");
  const handle = await deps.ensureDaemon(projectRoot);
  const client = handle.client;
  const subscription = await subscribe(client, deps);

  const timeoutMs = options.timeout ? Number.parseInt(options.timeout, 10) : DEFAULT_TIMEOUT_MS;
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new CliError(`invalid --timeout value "${options.timeout}"`, 1);
  }

  try {
    const run = await client.runDAG({
      ...(target ? { targets: [target] } : {}),
      ...(options.force ? { force: true } : {}),
    });

    const started = deps.now().getTime();
    let status = await client.dagStatus();
    let sawWork = false;
    while (true) {
      const active = status.nodes.filter((n) => n.state === "queued" || n.state === "running");
      if (active.length > 0) sawWork = true;
      if (
        active.length === 0 &&
        (sawWork || status.nodes.length === 0 || deps.now().getTime() - started >= DEFAULT_POLL_MS)
      ) {
        break;
      }
      if (deps.now().getTime() - started >= timeoutMs) {
        throw new CliError(`DAG run ${run.run_id} timed out after ${timeoutMs} ms`, 1, {
          run_id: run.run_id,
        });
      }
      await deps.sleep(DEFAULT_POLL_MS);
      status = await client.dagStatus();
    }

    const gates = await client.listGates();
    const failedNodes = status.nodes.filter((n) => n.state === "failed");
    const blockingFailures = gates.filter((g) => g.status === "FAIL" && g.severity === "blocking");
    const gateCounts = countByStatus(gates);

    const ok = failedNodes.length === 0 && blockingFailures.length === 0;
    const payload = {
      ok,
      run_id: run.run_id,
      target: target ?? null,
      nodes: status.nodes.map((n) => ({ id: n.id, plugin: n.plugin, state: n.state })),
      gates: { counts: gateCounts, failures: blockingFailures.map((g) => g.id) },
    };
    emit(deps, options.json === true, payload, [
      `run ${run.run_id}: ${status.nodes.length} node(s)` +
        (failedNodes.length ? `, ${failedNodes.length} failed` : ", all settled"),
      `gates: ${gateCounts.PASS} pass, ${gateCounts.FAIL} fail, ${gateCounts.SKIP} skip, ${gateCounts.ERROR} error`,
      ...(status.nodes.length === 0
        ? ["no DAG nodes registered — install a plugin and restart the daemon"]
        : []),
      ...blockingFailures.map((g) => `blocking gate FAIL: ${g.id} — ${g.summary}`),
    ]);
    return ok ? 0 : 1;
  } finally {
    await subscription?.close();
    await client.close().catch(() => undefined);
  }
}

function countByStatus(gates: readonly { status: string }[]): {
  PASS: number;
  FAIL: number;
  SKIP: number;
  ERROR: number;
} {
  const counts = { PASS: 0, FAIL: 0, SKIP: 0, ERROR: 0 } as Record<string, number>;
  for (const gate of gates) counts[gate.status] = (counts[gate.status] ?? 0) + 1;
  return {
    PASS: counts.PASS ?? 0,
    FAIL: counts.FAIL ?? 0,
    SKIP: counts.SKIP ?? 0,
    ERROR: counts.ERROR ?? 0,
  };
}
