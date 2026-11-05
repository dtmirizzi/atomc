/**
 * `@atomc/daemon-client` — typed JSON-RPC/WebSocket client for the atomc daemon.
 *
 * Implements the frozen RPC contract (`docs/architecture/contracts/rpc.md`):
 * request/response correlation, event subscriptions, typed server errors, and
 * `toRelativePatch` to reconcile the absolute pointers emitted by
 * `@atomc/core-ir`'s `patch(base)` builder with the daemon's relative-ops contract.
 */
export {
  DaemonClient,
  type DaemonClientOptions,
  DEFAULT_RPC_URL,
  DEFAULT_TIMEOUT_MS,
  type EventListener,
  type Subscription,
} from "./client.js";
export {
  ConflictError,
  ConnectionClosedError,
  ConnectionError,
  DaemonClientError,
  DagRunError,
  LockedError,
  MalformedResponseError,
  mapRpcError,
  PluginError,
  RefIntegrityError,
  RpcError,
  type RpcErrorData,
  TimeoutError,
  ValidationError,
} from "./errors.js";
export { PatchPathError, toRelativePatch } from "./patch.js";
export type * from "./types.js";
