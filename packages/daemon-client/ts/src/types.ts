/**
 * Wire types for the `atomcd` JSON-RPC API.
 *
 * Mirrors `docs/architecture/contracts/rpc.md` (v0.1.0), `gate-result.md`, and the
 * structural parts of `plugin-manifest.md` that appear in `plugins.list` /
 * `tools.list` results. Types are intentionally structural so the client does not
 * depend on the plugin SDK package.
 */
import type { JsonPatchOp } from "@atomc/core-ir";

export type { JsonPatchOp };

/** JSON-RPC id: servers echo it exactly; this client only sends numbers. */
export type JsonRpcId = number | string;

/** Outgoing JSON-RPC request envelope. */
export interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: JsonRpcId;
  method: string;
  params: unknown;
}

/** Incoming JSON-RPC success response. */
export interface JsonRpcSuccess {
  jsonrpc: "2.0";
  id: JsonRpcId;
  result: unknown;
}

/** Incoming JSON-RPC error response. */
export interface JsonRpcFailure {
  jsonrpc: "2.0";
  id: JsonRpcId;
  error: { code: number; message: string; data?: unknown };
}

/** Incoming JSON-RPC notification (no id). */
export interface JsonRpcNotification {
  jsonrpc: "2.0";
  method: string;
  params?: unknown;
}

export type JsonRpcMessage = JsonRpcSuccess | JsonRpcFailure | JsonRpcNotification;

// --- IR ---------------------------------------------------------------------

export interface IRGetParams {
  path?: string;
}

export interface IRGetResult {
  rev: number;
  value: unknown;
}

export interface IRTransactParams {
  path: string;
  base_rev: number;
  ops: JsonPatchOp[];
  holder?: string;
}

export interface IRTransactResult {
  new_rev: number;
  changed_paths: string[];
}

export interface IRLockParams {
  node: string;
  holder: string;
  ttl_s: number;
  reason?: string;
}

export interface IRLockResult {
  expires_at: string;
}

export interface IRUnlockParams {
  node: string;
  holder: string;
}

export interface IRUnlockResult {
  released: true;
}

// --- DAG --------------------------------------------------------------------

export type DagNodeState = "idle" | "queued" | "running" | "ok" | "failed" | "stale";

export interface DagNodeStatus {
  id: string;
  plugin: string;
  state: DagNodeState;
  last_run?: string;
}

export interface DagStatusResult {
  nodes: DagNodeStatus[];
}

export interface DagRunParams {
  targets?: string[];
  force?: boolean;
}

export interface DagRunResult {
  run_id: string;
}

// --- Gates ------------------------------------------------------------------

export type GateStatus = "PASS" | "FAIL" | "SKIP" | "ERROR";
export type GateSeverity = "blocking" | "advisory";
export type AgentName = "ee-agent" | "fw-agent" | "mech-agent" | "ops-agent";

export interface GateEvidence {
  kind: "text" | "json" | "artifact" | "image";
  ref?: string;
  data?: unknown;
  message?: string;
}

export interface GateSuggestion {
  message: string;
  patch?: { path: string; ops: JsonPatchOp[] };
}

export interface GateResult {
  id: string;
  status: GateStatus;
  severity: GateSeverity;
  plugin: string;
  owner_agent: AgentName | null;
  evaluated_at: string;
  ir_rev: number;
  duration_ms: number;
  summary: string;
  evidence: GateEvidence[];
  suggestions: GateSuggestion[];
  refs: string[];
}

export interface GatesListParams {
  ids?: string[];
}

export interface GatesRunParams {
  ids?: string[];
}

// --- Plugins / tools --------------------------------------------------------

export interface PluginWatch {
  id: string;
  ir: string[];
  files?: string[];
  debounce_ms?: number;
}

export interface PluginGate {
  id: string;
  severity: GateSeverity;
  owner_agent: AgentName | null;
  after?: string[];
  handler: string;
}

export interface PluginTool {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  agents: AgentName[];
  mutates: boolean;
  handler: string;
}

export interface PluginManifest {
  manifest_version: string;
  name: string;
  version: string;
  description: string;
  atomc: string;
  runtime: { python?: string; ts?: string };
  watches: PluginWatch[];
  produces: string[];
  gates: PluginGate[];
  tools: PluginTool[];
  cli: Array<{ command: string; description: string; handler: string }>;
  ui: Array<{ panel: string; title: string; entry: string }>;
}

export interface PluginStatus extends PluginManifest {
  loaded: boolean;
  error?: string;
}

export interface ToolInfo {
  plugin: string;
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  mutates: boolean;
}

export interface ToolsListParams {
  agent?: AgentName;
}

export interface Artifact {
  id: string;
  kind: string;
  path: string;
  sha256: string;
  bytes: number;
  produced_by?: string;
  produced_at: string;
}

export interface ToolsCallParams {
  plugin: string;
  tool: string;
  args: unknown;
  holder?: string;
}

export interface ToolsCallResult {
  result: unknown;
  artifacts?: Artifact[];
}

// --- Events -----------------------------------------------------------------

export interface EventsSubscribeParams {
  topics: string[];
}

export interface EventsSubscribeResult {
  subscription: string;
}

export interface EventsUnsubscribeParams {
  subscription: string;
}

export interface EventsUnsubscribeResult {
  unsubscribed: true;
}

export type LogLevel = "debug" | "info" | "warning" | "error";

/** Known event payloads; unknown topics fall through to the index signature. */
export type AtomcEvent =
  | { topic: "ir.changed"; data: { rev: number; changed_paths: string[]; holder?: string } }
  | { topic: "gate.result"; data: GateResult }
  | { topic: "dag.node.start"; data: { run_id: string; id: string; plugin: string } }
  | {
      topic: "dag.node.end";
      data: { run_id: string; id: string; ok: boolean; duration_ms: number; error?: string };
    }
  | { topic: "log"; data: { level: LogLevel; msg: string; plugin?: string } }
  | { topic: string; data: unknown };

/** Raw `event` notification params. */
export interface EventNotificationParams {
  topic: string;
  data: unknown;
}

// --- Daemon -----------------------------------------------------------------

export interface DaemonStatusResult {
  pid: number;
  host: string;
  port: number;
  version: string;
  project_root: string;
  uptime_ms: number;
}

export interface DaemonShutdownResult {
  shutting_down: true;
}

/** Shape of `~/.atomc/daemon.json` (mode 0600). */
export interface DaemonInfo {
  pid: number;
  host: string;
  port: number;
  token: string;
  project_root: string;
  started_at: string;
  version: string;
}

/** Result of `GET /health`. */
export interface HealthResult {
  ok: boolean;
  version: string;
  ir_rev: number;
}
