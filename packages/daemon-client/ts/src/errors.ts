/**
 * Error hierarchy for `@atomc/daemon-client`.
 *
 * JSON-RPC error codes are frozen in `docs/architecture/contracts/rpc.md`. Local
 * transport failures (timeouts, closed sockets, malformed frames) are represented
 * by `DaemonClientError` subclasses that never get confused with server errors.
 */

/** Local (non-RPC) failure raised by the client itself. */
export class DaemonClientError extends Error {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message);
    this.name = new.target.name;
    if (options && "cause" in options) {
      (this as { cause?: unknown }).cause = options.cause;
    }
  }
}

/** Underlying socket failed to connect or send. */
export class ConnectionError extends DaemonClientError {}

/** The socket was closed (explicitly or by the peer) while a request was in flight. */
export class ConnectionClosedError extends ConnectionError {}

/** A request exceeded its configured timeout. The server may still have applied a mutation. */
export class TimeoutError extends DaemonClientError {
  readonly method: string;
  readonly timeoutMs: number;

  constructor(method: string, timeoutMs: number) {
    super(`Request "${method}" timed out after ${timeoutMs} ms`);
    this.method = method;
    this.timeoutMs = timeoutMs;
  }
}

/** A frame arrived that was not valid JSON or not a valid JSON-RPC 2.0 envelope. */
export class MalformedResponseError extends DaemonClientError {}

/** JSON-RPC error object returned by the daemon. */
export interface RpcErrorData {
  code: number;
  message: string;
  data?: unknown;
}

/** Base class for every JSON-RPC server error (`{code, message, data}`). */
export class RpcError extends DaemonClientError {
  readonly code: number;
  readonly data: unknown;

  constructor(message: string, code: number, data?: unknown) {
    super(message);
    this.code = code;
    this.data = data;
  }
}

/** `-32010`: optimistic revision conflict. */
export class ConflictError extends RpcError {
  readonly current_rev?: number;
  readonly expected_rev?: number;

  constructor(message: string, data?: unknown) {
    super(message, -32010, data);
    const d = (data ?? {}) as { current_rev?: number; expected_rev?: number };
    if (typeof d.current_rev === "number") this.current_rev = d.current_rev;
    if (typeof d.expected_rev === "number") this.expected_rev = d.expected_rev;
  }
}

/** `-32011`: subtree lock conflict. */
export class LockedError extends RpcError {
  readonly holder?: string;
  readonly expires_at?: string;

  constructor(message: string, data?: unknown) {
    super(message, -32011, data);
    const d = (data ?? {}) as { holder?: string; expires_at?: string };
    if (typeof d.holder === "string") this.holder = d.holder;
    if (typeof d.expires_at === "string") this.expires_at = d.expires_at;
  }
}

/** `-32012`: IR / model validation failure. */
export class ValidationError extends RpcError {
  readonly errors: ReadonlyArray<{ path: string; message: string; type?: string }>;

  constructor(message: string, data?: unknown) {
    super(message, -32012, data);
    const d = (data ?? {}) as { errors?: Array<{ path: string; message: string; type?: string }> };
    this.errors = d.errors ?? [];
  }
}

/** `-32013`: dangling or duplicate IR reference. */
export class RefIntegrityError extends RpcError {
  constructor(message: string, data?: unknown) {
    super(message, -32013, data);
  }
}

/** `-32020`: plugin or tool failure. */
export class PluginError extends RpcError {
  readonly plugin?: string;
  readonly tool?: string;
  readonly retryable: boolean;
  readonly detail?: unknown;

  constructor(message: string, data?: unknown) {
    super(message, -32020, data);
    const d = (data ?? {}) as {
      plugin?: string;
      tool?: string;
      retryable?: boolean;
      detail?: unknown;
    };
    if (typeof d.plugin === "string") this.plugin = d.plugin;
    if (typeof d.tool === "string") this.tool = d.tool;
    this.retryable = d.retryable === true;
    this.detail = d.detail;
  }
}

/** `-32030`: DAG run failure. */
export class DagRunError extends RpcError {
  constructor(message: string, data?: unknown) {
    super(message, -32030, data);
  }
}

/** Errors raised while bootstrapping a daemon process from the client. */
export class DaemonStartError extends DaemonClientError {}

/** Map a JSON-RPC error object to the most specific typed error. */
export function mapRpcError(error: RpcErrorData): RpcError {
  const { code, message, data } = error;
  switch (code) {
    case -32010:
      return new ConflictError(message, data);
    case -32011:
      return new LockedError(message, data);
    case -32012:
      return new ValidationError(message, data);
    case -32013:
      return new RefIntegrityError(message, data);
    case -32020:
      return new PluginError(message, data);
    case -32030:
      return new DagRunError(message, data);
    default:
      return new RpcError(message, code, data);
  }
}
