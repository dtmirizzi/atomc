/**
 * `atomc quote [--json] [--refresh]` — refresh PCB fabrication quotes through the sourcing
 * plugin and report the `fab.quote_under_budget` gate.
 *
 * No price is invented here. The command invokes the sourcing plugin's `quote_pcb` tool over the
 * daemon's `tools.call` RPC (which writes trustworthy quotes into `/fabrication`), reads them
 * back from the IR, runs the budget gate and prints the result. When the plugin is missing, the
 * tool reports `UNAVAILABLE`/`ERROR`, or the daemon is unreachable, the command exits 3 with a
 * structured `unavailable` payload and never claims a quote.
 */
import { resolve } from "node:path";
import type { GateResult } from "@atomc/daemon-client";
import type { CliDeps, DaemonApi } from "../deps.js";
import { EXIT_UNAVAILABLE } from "../errors.js";
import { emit } from "../output.js";

export interface QuoteOptions {
  json?: boolean;
  project?: string;
  refresh?: boolean;
}

const SOURCING_PLUGIN = "sourcing";
const QUOTE_TOOL = "quote_pcb";
const QUOTE_GATE = "gate:fab.quote_under_budget";

/** A fabrication quote as stored at `/fabrication/quotes`. */
export interface QuoteSummary {
  id: string;
  fab: string;
  total_minor: number;
  currency: string;
  lead_time_days: number;
  breakdown: Record<string, number>;
  url: string | null;
  fetched_at: string | null;
}

/** Shape of the sourcing plugin's `quote_pcb` tool result (subset we rely on). */
interface QuoteToolResult {
  status?: string;
  summary?: string;
  quotes?: unknown;
}

interface ToolsCallEnvelope {
  result?: QuoteToolResult;
}

function numberOr(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

/** Coerce one raw IR quote into a {@link QuoteSummary}; returns `undefined` when unusable. */
export function coerceQuote(raw: unknown): QuoteSummary | undefined {
  if (raw === null || typeof raw !== "object") return undefined;
  const o = raw as Record<string, unknown>;
  if (typeof o.id !== "string" || typeof o.fab !== "string") return undefined;
  const breakdown: Record<string, number> = {};
  if (o.breakdown !== null && typeof o.breakdown === "object") {
    for (const [key, value] of Object.entries(o.breakdown as Record<string, unknown>)) {
      if (typeof value === "number" && Number.isFinite(value)) breakdown[key] = value;
    }
  }
  return {
    id: o.id,
    fab: o.fab,
    total_minor: numberOr(o.total_minor, 0),
    currency: typeof o.currency === "string" ? o.currency : "USD",
    lead_time_days: numberOr(o.lead_time_days, 0),
    breakdown,
    url: typeof o.url === "string" ? o.url : null,
    fetched_at: typeof o.fetched_at === "string" ? o.fetched_at : null,
  };
}

function collectQuotes(value: unknown): QuoteSummary[] {
  if (!Array.isArray(value)) return [];
  const quotes: QuoteSummary[] = [];
  for (const entry of value) {
    const quote = coerceQuote(entry);
    if (quote !== undefined) quotes.push(quote);
  }
  return quotes;
}

function money(minor: number, currency: string): string {
  return `${(minor / 100).toFixed(2)} ${currency}`;
}

function breakdownText(breakdown: Record<string, number>): string {
  const parts = Object.entries(breakdown).map(
    ([key, value]) => `${key}=${(value / 100).toFixed(2)}`,
  );
  return parts.length > 0 ? ` (${parts.join(", ")})` : "";
}

function emitUnavailable(
  deps: CliDeps,
  json: boolean,
  project: string,
  reason: string,
  hint: string,
  extra: Record<string, unknown> = {},
): number {
  const payload = {
    status: "unavailable",
    command: "quote",
    project,
    plugin: SOURCING_PLUGIN,
    reason,
    hint,
    quotes: [],
    ...extra,
  };
  emit(deps, json, payload, [`atomc quote: unavailable — ${reason}`, `  hint: ${hint}`]);
  return EXIT_UNAVAILABLE;
}

/** Run `atomc quote`; returns the process exit code. */
export async function quoteCommand(deps: CliDeps, options: QuoteOptions = {}): Promise<number> {
  const projectRoot = resolve(deps.cwd, options.project ?? ".");
  const json = options.json === true;
  let client: DaemonApi;
  try {
    const handle = await deps.ensureDaemon(projectRoot);
    client = handle.client;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return emitUnavailable(
      deps,
      json,
      projectRoot,
      `daemon unavailable: ${message}`,
      "start the daemon with `atomc daemon start` and retry",
    );
  }

  try {
    let plugins: Awaited<ReturnType<DaemonApi["listPlugins"]>>;
    try {
      plugins = await client.listPlugins();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return emitUnavailable(deps, json, projectRoot, `daemon RPC failed: ${message}`, "retry");
    }
    const sourcing = plugins.find((plugin) => plugin.name === SOURCING_PLUGIN && plugin.loaded);
    if (sourcing === undefined) {
      return emitUnavailable(
        deps,
        json,
        projectRoot,
        `plugin "${SOURCING_PLUGIN}" is not installed or failed to load`,
        `install the "${SOURCING_PLUGIN}" plugin and restart the daemon`,
      );
    }

    let tool: ToolsCallEnvelope;
    try {
      tool = await client.request<ToolsCallEnvelope>("tools.call", {
        plugin: SOURCING_PLUGIN,
        tool: QUOTE_TOOL,
        args: { write: true, ...(options.refresh === true ? { force: true } : {}) },
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return emitUnavailable(
        deps,
        json,
        projectRoot,
        `sourcing tool "${QUOTE_TOOL}" failed: ${message}`,
        "check the sourcing plugin configuration (vendor endpoints/credentials)",
      );
    }

    const result = tool?.result ?? {};
    const toolStatus = typeof result.status === "string" ? result.status : "ERROR";
    if (toolStatus === "UNAVAILABLE" || toolStatus === "ERROR") {
      return emitUnavailable(
        deps,
        json,
        projectRoot,
        result.summary ?? `sourcing tool "${QUOTE_TOOL}" reported ${toolStatus}`,
        "verify vendor endpoints/credentials or provide the fabrication spec explicitly",
        { tool_status: toolStatus },
      );
    }

    let quotes: QuoteSummary[] = [];
    try {
      const document = (await client.getIR("/")).value as
        | { fabrication?: { quotes?: unknown } }
        | undefined;
      quotes = collectQuotes(document?.fabrication?.quotes);
    } catch {
      quotes = [];
    }
    if (quotes.length === 0) {
      quotes = collectQuotes(result.quotes);
    }

    let gate: GateResult | undefined;
    try {
      const gates = await client.request<GateResult[]>("gates.run", { ids: [QUOTE_GATE] });
      gate = gates.find((entry) => entry.id === QUOTE_GATE);
    } catch {
      gate = undefined;
    }

    const gateStatus = gate?.status ?? "SKIP";
    const hasData = quotes.length > 0;
    const ok = hasData && gateStatus === "PASS";
    const status = !hasData ? "no_data" : ok ? "ok" : "gate_failed";

    const payload = {
      status,
      command: "quote",
      project: projectRoot,
      plugin: SOURCING_PLUGIN,
      refresh: options.refresh === true,
      tool: { status: toolStatus, summary: result.summary ?? null },
      count: quotes.length,
      quotes: quotes.map((quote) => ({
        id: quote.id,
        fab: quote.fab,
        total_minor: quote.total_minor,
        currency: quote.currency,
        lead_time_days: quote.lead_time_days,
        breakdown: quote.breakdown,
        url: quote.url,
        fetched_at: quote.fetched_at,
      })),
      gate: gate
        ? { id: gate.id, status: gate.status, severity: gate.severity, summary: gate.summary }
        : null,
      reason: hasData ? null : "no fabrication quotes were returned for this project",
    };

    const human = [
      `quote: ${quotes.length} fabrication quote(s) for ${projectRoot}`,
      ...quotes.map(
        (quote) =>
          `  ${quote.fab}  ${quote.id}  ${money(quote.total_minor, quote.currency)}` +
          `  lead ${quote.lead_time_days}d${breakdownText(quote.breakdown)}`,
      ),
      gate
        ? `gate ${gate.id}: ${gate.status} — ${gate.summary}`
        : `gate ${QUOTE_GATE}: not evaluated`,
    ];
    if (quotes.length === 0) {
      human.push(`  no quotes available — run with a configured sourcing plugin and vendor access`);
    }
    emit(deps, json, payload, human);
    return ok ? 0 : 1;
  } finally {
    await client.close().catch(() => undefined);
  }
}
