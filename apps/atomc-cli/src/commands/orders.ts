/**
 * `atomc orders [--json] [--status <s>]` — print the `/orders` ledger from the daemon.
 * `atomc orders build-cart [--vendor <v>] [--out <dir>]` — ask the orders plugin to render
 * vendor cart files and print the written paths.
 *
 * The ledger command is read-only. `build-cart` is the only mutation and it delegates to the
 * orders plugin's `build_cart` tool: the plugin writes draft `/orders` records and cart files
 * under its own artifact root; this command never contacts a vendor and never places an order.
 */
import { basename, join, resolve } from "node:path";
import type { CliDeps, DaemonApi } from "../deps.js";
import { CliError, EXIT_UNAVAILABLE } from "../errors.js";
import { emit } from "../output.js";

export interface OrdersOptions {
  json?: boolean;
  project?: string;
  status?: string;
}

export interface OrdersBuildCartOptions {
  json?: boolean;
  project?: string;
  vendor?: string;
  out?: string;
}

const ORDERS_PLUGIN = "orders";
const BUILD_CART_TOOL = "build_cart";

/** Frozen order statuses from `packages/core-ir/python/src/atomc_core_ir/orders.py`. */
export const ORDER_STATUSES = [
  "draft",
  "placed",
  "paid",
  "shipped",
  "delivered",
  "cancelled",
] as const;

type OrderStatus = (typeof ORDER_STATUSES)[number];

/** A ledger record as printed by this command. */
export interface LedgerOrder {
  id: string;
  vendor: string;
  kind: string;
  status: string;
  total_minor: number;
  currency: string;
  external_id: string | null;
  tracking: Array<{ carrier: string; number: string; url: string | null }>;
}

interface CartArtifact {
  id?: string | undefined;
  vendor: string;
  kind?: string | undefined;
  format?: string | undefined;
  path: string;
  sha256?: string | undefined;
  bytes?: number | undefined;
  written?: boolean | undefined;
}

interface BuildCartResult {
  status?: string;
  summary?: string;
  artifacts?: unknown;
  orders?: unknown;
  notice?: string | null;
}

interface ToolsCallEnvelope {
  result?: BuildCartResult;
  artifacts?: unknown;
}

function parseStatusFilter(raw: string | undefined): OrderStatus | undefined {
  if (raw === undefined) return undefined;
  if ((ORDER_STATUSES as readonly string[]).includes(raw)) return raw as OrderStatus;
  throw new CliError(
    `invalid --status value "${raw}" (expected one of: ${ORDER_STATUSES.join(", ")})`,
    2,
  );
}

function coerceOrder(raw: unknown): LedgerOrder | undefined {
  if (raw === null || typeof raw !== "object") return undefined;
  const o = raw as Record<string, unknown>;
  if (typeof o.id !== "string") return undefined;
  const tracking: LedgerOrder["tracking"] = [];
  if (Array.isArray(o.tracking)) {
    for (const entry of o.tracking) {
      if (entry !== null && typeof entry === "object") {
        const t = entry as Record<string, unknown>;
        if (typeof t.carrier === "string" && typeof t.number === "string") {
          tracking.push({
            carrier: t.carrier,
            number: t.number,
            url: typeof t.url === "string" ? t.url : null,
          });
        }
      }
    }
  }
  return {
    id: o.id,
    vendor: typeof o.vendor === "string" ? o.vendor : "",
    kind: typeof o.kind === "string" ? o.kind : "parts",
    status: typeof o.status === "string" ? o.status : "draft",
    total_minor: typeof o.total_minor === "number" ? o.total_minor : 0,
    currency: typeof o.currency === "string" ? o.currency : "USD",
    external_id: typeof o.external_id === "string" ? o.external_id : null,
    tracking,
  };
}

function coerceArtifact(raw: unknown): CartArtifact | undefined {
  if (raw === null || typeof raw !== "object") return undefined;
  const o = raw as Record<string, unknown>;
  if (typeof o.path !== "string" || o.path.length === 0) return undefined;
  return {
    id: typeof o.id === "string" ? o.id : undefined,
    vendor: typeof o.vendor === "string" ? o.vendor : "unknown",
    kind: typeof o.kind === "string" ? o.kind : undefined,
    format: typeof o.format === "string" ? o.format : undefined,
    path: o.path,
    sha256: typeof o.sha256 === "string" ? o.sha256 : undefined,
    bytes: typeof o.bytes === "number" ? o.bytes : undefined,
    written: o.written === true,
  };
}

function trackSummary(order: LedgerOrder): string {
  if (order.tracking.length === 0) return "—";
  return order.tracking.map((t) => `${t.carrier}:${t.number}`).join(", ");
}

function pad(text: string, width: number): string {
  return text.length >= width ? text : text + " ".repeat(width - text.length);
}

function emitUnavailable(
  deps: CliDeps,
  json: boolean,
  command: string,
  project: string,
  reason: string,
  hint: string,
): number {
  const payload = {
    status: "unavailable",
    command,
    project,
    plugin: ORDERS_PLUGIN,
    reason,
    hint,
  };
  emit(deps, json, payload, [`atomc ${command}: unavailable — ${reason}`, `  hint: ${hint}`]);
  return EXIT_UNAVAILABLE;
}

async function ensureOrdersDaemon(
  deps: CliDeps,
  json: boolean,
  command: string,
  projectRoot: string,
): Promise<{ client: DaemonApi } | number> {
  let client: DaemonApi;
  try {
    const handle = await deps.ensureDaemon(projectRoot);
    client = handle.client;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return emitUnavailable(
      deps,
      json,
      command,
      projectRoot,
      `daemon unavailable: ${message}`,
      "start the daemon with `atomc daemon start` and retry",
    );
  }
  try {
    const plugins = await client.listPlugins();
    const orders = plugins.find((plugin) => plugin.name === ORDERS_PLUGIN && plugin.loaded);
    if (orders === undefined) {
      await client.close().catch(() => undefined);
      return emitUnavailable(
        deps,
        json,
        command,
        projectRoot,
        `plugin "${ORDERS_PLUGIN}" is not installed or failed to load`,
        `install the "${ORDERS_PLUGIN}" plugin and restart the daemon`,
      );
    }
  } catch (error) {
    await client.close().catch(() => undefined);
    const message = error instanceof Error ? error.message : String(error);
    return emitUnavailable(
      deps,
      json,
      command,
      projectRoot,
      `daemon RPC failed: ${message}`,
      "retry",
    );
  }
  return { client };
}

/** `atomc orders` — print the order ledger (read-only). */
export async function ordersCommand(deps: CliDeps, options: OrdersOptions = {}): Promise<number> {
  const json = options.json === true;
  const filter = parseStatusFilter(options.status);
  const projectRoot = resolve(deps.cwd, options.project ?? ".");
  const ready = await ensureOrdersDaemon(deps, json, "orders", projectRoot);
  if (typeof ready === "number") return ready;
  const { client } = ready;

  try {
    let orders: LedgerOrder[];
    try {
      const document = (await client.getIR("/")).value as
        | { orders?: { orders?: unknown } }
        | undefined;
      const raw = document?.orders?.orders;
      orders = Array.isArray(raw) ? raw.map(coerceOrder).filter((o): o is LedgerOrder => !!o) : [];
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return emitUnavailable(
        deps,
        json,
        "orders",
        projectRoot,
        `daemon RPC failed: ${message}`,
        "retry",
      );
    }

    const filtered = filter === undefined ? orders : orders.filter((o) => o.status === filter);
    const empty = orders.length === 0;
    const payload = {
      status: empty ? "empty" : "ok",
      command: "orders",
      project: projectRoot,
      filter: filter ?? null,
      count: filtered.length,
      total: orders.length,
      orders: filtered.map((order) => ({
        id: order.id,
        vendor: order.vendor,
        kind: order.kind,
        status: order.status,
        total_minor: order.total_minor,
        currency: order.currency,
        external_id: order.external_id,
        tracking: order.tracking,
        tracking_summary: trackSummary(order),
      })),
      reason: empty ? "no orders recorded in /orders for this project" : null,
    };

    const header = `${pad("ID", 24)} ${pad("VENDOR", 10)} ${pad("KIND", 6)} ${pad("STATUS", 10)} ${pad("TOTAL", 14)} TRACKING`;
    const rows = filtered.map(
      (order) =>
        `${pad(order.id, 24)} ${pad(order.vendor, 10)} ${pad(order.kind, 6)} ` +
        `${pad(order.status, 10)} ${pad(`${(order.total_minor / 100).toFixed(2)} ${order.currency}`, 14)} ` +
        `${trackSummary(order)}`,
    );
    const human = [
      empty
        ? "no orders recorded in /orders for this project"
        : `orders: ${filtered.length} of ${orders.length} record(s)` +
          (filter ? ` (status ${filter})` : ""),
      ...(empty ? [] : [header, ...rows]),
    ];
    emit(deps, json, payload, human);
    return empty ? 1 : 0;
  } finally {
    await client.close().catch(() => undefined);
  }
}

/** `atomc orders build-cart` — render per-vendor cart files via the orders plugin. */
export async function ordersBuildCart(
  deps: CliDeps,
  options: OrdersBuildCartOptions = {},
): Promise<number> {
  const json = options.json === true;
  const projectRoot = resolve(deps.cwd, options.project ?? ".");
  const vendorFilter = options.vendor;
  const ready = await ensureOrdersDaemon(deps, json, "orders build-cart", projectRoot);
  if (typeof ready === "number") return ready;
  const { client } = ready;

  try {
    let envelope: ToolsCallEnvelope;
    try {
      envelope = await client.request<ToolsCallEnvelope>("tools.call", {
        plugin: ORDERS_PLUGIN,
        tool: BUILD_CART_TOOL,
        args: {},
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return emitUnavailable(
        deps,
        json,
        "orders build-cart",
        projectRoot,
        `orders tool "${BUILD_CART_TOOL}" failed: ${message}`,
        "check the orders plugin configuration",
      );
    }

    const result = envelope?.result ?? {};
    const toolStatus = typeof result.status === "string" ? result.status : "FAIL";
    if (toolStatus !== "PASS") {
      const reason = result.summary ?? `orders tool "${BUILD_CART_TOOL}" reported ${toolStatus}`;
      const payload = {
        status: "failed",
        command: "orders build-cart",
        project: projectRoot,
        plugin: ORDERS_PLUGIN,
        tool_status: toolStatus,
        reason,
        hint: "ensure /sourcing has one chosen offer per BOM line, then retry build-cart",
      };
      emit(deps, json, payload, [
        `atomc orders build-cart: failed — ${reason}`,
        `  hint: ${payload.hint}`,
      ]);
      return 1;
    }

    const rawArtifacts = Array.isArray(result.artifacts) ? result.artifacts : envelope?.artifacts;
    const allArtifacts = (Array.isArray(rawArtifacts) ? rawArtifacts : [])
      .map(coerceArtifact)
      .filter((a): a is CartArtifact => !!a);
    const artifacts =
      vendorFilter === undefined
        ? allArtifacts
        : allArtifacts.filter((a) => a.vendor.toLowerCase() === vendorFilter.toLowerCase());
    if (allArtifacts.length > 0 && artifacts.length === 0) {
      const payload = {
        status: "failed",
        command: "orders build-cart",
        project: projectRoot,
        plugin: ORDERS_PLUGIN,
        reason: `no cart file was built for vendor "${vendorFilter}"`,
        vendors: [...new Set(allArtifacts.map((a) => a.vendor))].sort(),
      };
      emit(deps, json, payload, [`atomc orders build-cart: failed — ${payload.reason}`]);
      return 1;
    }

    const writtenTo: string[] = [];
    if (options.out !== undefined) {
      const outDir = resolve(deps.cwd, options.out);
      try {
        await deps.fs.mkdir(outDir, { recursive: true });
        for (const artifact of artifacts) {
          const destination = join(outDir, basename(artifact.path));
          await deps.fs.copyFile(artifact.path, destination);
          writtenTo.push(destination);
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        const payload = {
          status: "failed",
          command: "orders build-cart",
          project: projectRoot,
          plugin: ORDERS_PLUGIN,
          reason: `could not copy cart files to ${outDir}: ${message}`,
        };
        emit(deps, json, payload, [`atomc orders build-cart: failed — ${payload.reason}`]);
        return 1;
      }
    }

    const orderIds = Array.isArray(result.orders)
      ? result.orders.filter((value): value is string => typeof value === "string")
      : [];
    const payload = {
      status: "ok",
      command: "orders build-cart",
      project: projectRoot,
      plugin: ORDERS_PLUGIN,
      vendor: vendorFilter ?? null,
      out: options.out !== undefined ? resolve(deps.cwd, options.out) : null,
      count: artifacts.length,
      artifacts: artifacts.map((artifact) => ({
        vendor: artifact.vendor,
        format: artifact.format ?? null,
        path: artifact.path,
        sha256: artifact.sha256 ?? null,
        bytes: artifact.bytes ?? null,
      })),
      written_to: writtenTo,
      orders: orderIds,
      notice: result.notice ?? null,
      summary: result.summary ?? null,
    };
    const human = [
      `built ${artifacts.length} cart(s); ${orderIds.length} draft order(s) recorded`,
      ...artifacts.map(
        (artifact) =>
          `  ${artifact.vendor} ${artifact.format ?? ""} ${artifact.path}` +
          (artifact.sha256 ? `  ${artifact.sha256}` : ""),
      ),
      ...writtenTo.map((path) => `  copied -> ${path}`),
      ...(result.notice ? [`  notice: ${result.notice}`] : []),
    ];
    emit(deps, json, payload, human);
    return 0;
  } finally {
    await client.close().catch(() => undefined);
  }
}
