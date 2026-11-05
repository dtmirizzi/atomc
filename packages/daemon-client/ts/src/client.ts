/**
 * `DaemonClient` — typed JSON-RPC 2.0 client for the atomc daemon over WebSocket.
 *
 * Conforms to `docs/architecture/contracts/rpc.md` v0.1.0. Requests are correlated
 * by numeric id and may be in flight concurrently. Server errors are mapped to the
 * typed hierarchy in `./errors.js`.
 */
import WebSocket from "ws";
import {
  ConnectionClosedError,
  ConnectionError,
  MalformedResponseError,
  mapRpcError,
  TimeoutError,
} from "./errors.js";
import type {
  AgentName,
  AtomcEvent,
  DaemonShutdownResult,
  DaemonStatusResult,
  DagRunParams,
  DagRunResult,
  DagStatusResult,
  EventNotificationParams,
  EventsSubscribeResult,
  EventsUnsubscribeResult,
  GateResult,
  IRGetParams,
  IRGetResult,
  IRLockResult,
  IRTransactParams,
  IRTransactResult,
  IRUnlockResult,
  PluginStatus,
  ToolInfo,
  ToolsCallParams,
  ToolsCallResult,
} from "./types.js";

/** Default daemon RPC endpoint (rpc.md §Transport and lifecycle). */
export const DEFAULT_RPC_URL = "ws://127.0.0.1:7437/rpc";

/** Default per-request timeout. */
export const DEFAULT_TIMEOUT_MS = 30_000;

/** Connection options for {@link DaemonClient.connect}. */
export interface DaemonClientOptions {
  /** WebSocket URL; defaults to {@link DEFAULT_RPC_URL}. */
  url?: string;
  /** Bearer token sent in the WebSocket upgrade `Authorization` header. */
  token?: string;
  /** Per-request timeout in milliseconds. */
  timeoutMs?: number;
  /** Called for malformed frames and listener errors; defaults to a no-op. */
  onError?: (error: unknown) => void;
  /** WebSocket implementation override (tests). */
  WebSocketImpl?: typeof WebSocket;
}

/** A live event subscription returned by {@link DaemonClient.subscribe}. */
export interface Subscription {
  /** Server-assigned subscription id. */
  readonly id: string;
  /** Topics this subscription listens to; `"*"` matches every topic. */
  readonly topics: readonly string[];
  /** Notify the server and stop delivering events to the listener. */
  unsubscribe(): Promise<void>;
}

/** Event listener callback. */
export type EventListener = (event: AtomcEvent) => void;

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (reason: unknown) => void;
  timer: ReturnType<typeof setTimeout>;
  method: string;
}

interface SubscriptionEntry {
  topics: readonly string[];
  listener: EventListener;
}

/** Typed client for `ws://…/rpc`. */
export class DaemonClient {
  readonly #url: string;
  readonly #token: string | undefined;
  readonly #timeoutMs: number;
  readonly #onError: (error: unknown) => void;
  readonly #WebSocketImpl: typeof WebSocket;

  #socket: WebSocket | undefined;
  #pending = new Map<number, PendingRequest>();
  #subscriptions = new Map<string, SubscriptionEntry>();
  #nextId = 1;
  #closed = false;

  private constructor(options: DaemonClientOptions) {
    this.#url = options.url ?? DEFAULT_RPC_URL;
    this.#token = options.token;
    this.#timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.#onError = options.onError ?? (() => {});
    this.#WebSocketImpl = options.WebSocketImpl ?? WebSocket;
  }

  /** Connect and resolve once the WebSocket is open. */
  static async connect(options: DaemonClientOptions = {}): Promise<DaemonClient> {
    const client = new DaemonClient(options);
    await client.#open();
    return client;
  }

  /** True once {@link close} has been called or the peer closed the socket. */
  get closed(): boolean {
    return this.#closed || this.#socket === undefined;
  }

  /** The RPC endpoint this client targets. */
  get url(): string {
    return this.#url;
  }

  #open(): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      const Impl = this.#WebSocketImpl;
      const socket = this.#token
        ? new Impl(this.#url, { headers: { Authorization: `Bearer ${this.#token}` } })
        : new Impl(this.#url);
      this.#socket = socket;

      let timer: ReturnType<typeof setTimeout> | undefined;
      const cleanup = (): void => {
        if (timer !== undefined) clearTimeout(timer);
        socket.off("open", onOpen);
        socket.off("error", onError);
      };
      const onOpen = (): void => {
        cleanup();
        this.#attach(socket);
        resolve();
      };
      const onError = (error: Error): void => {
        cleanup();
        this.#socket = undefined;
        reject(
          new ConnectionError(`Failed to connect to ${this.#url}: ${error.message}`, {
            cause: error,
          }),
        );
      };

      timer = setTimeout(() => {
        cleanup();
        socket.terminate();
        this.#socket = undefined;
        reject(new TimeoutError("connect", this.#timeoutMs));
      }, this.#timeoutMs);

      socket.once("open", onOpen);
      socket.once("error", onError);
    });
  }

  #attach(socket: WebSocket): void {
    socket.on("message", (data) => {
      this.#handleMessage(data);
    });
    socket.on("close", () => {
      this.#handleClose();
    });
    socket.on("error", (error) => {
      this.#onError(error);
    });
  }

  #handleClose(): void {
    const socket = this.#socket;
    if (socket !== undefined) {
      socket.removeAllListeners();
      this.#socket = undefined;
    }
    const error = new ConnectionClosedError("Daemon connection closed");
    for (const pending of this.#pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(error);
    }
    this.#pending.clear();
    this.#subscriptions.clear();
  }

  /** Send a JSON-RPC request. Never retries automatically on the same socket. */
  request<T = unknown>(method: string, params?: unknown): Promise<T> {
    const socket = this.#socket;
    if (this.#closed || socket === undefined || socket.readyState !== this.#WebSocketImpl.OPEN) {
      return Promise.reject(new ConnectionClosedError("Daemon connection is not open"));
    }
    const id = this.#nextId++;
    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.#pending.delete(id);
        reject(new TimeoutError(method, this.#timeoutMs));
      }, this.#timeoutMs);
      timer.unref?.();
      this.#pending.set(id, {
        resolve: resolve as (value: unknown) => void,
        reject,
        timer,
        method,
      });
      try {
        socket.send(JSON.stringify({ jsonrpc: "2.0", id, method, params: params ?? {} }));
      } catch (error) {
        clearTimeout(timer);
        this.#pending.delete(id);
        reject(new ConnectionError(`Failed to send "${method}" request`, { cause: error }));
      }
    });
  }

  #handleMessage(data: WebSocket.RawData): void {
    let parsed: unknown;
    try {
      parsed = JSON.parse(this.#toText(data));
    } catch (error) {
      this.#onError(
        new MalformedResponseError("Received a non-JSON WebSocket frame", { cause: error }),
      );
      return;
    }
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      this.#onError(new MalformedResponseError("Received a malformed JSON-RPC envelope"));
      return;
    }
    const message = parsed as Record<string, unknown>;

    // Notification (event pushes have no id).
    if (typeof message.method === "string" && !("id" in message)) {
      if (message.method === "event") this.#handleEvent(message.params);
      return;
    }

    if (message.jsonrpc !== "2.0" || !("id" in message)) {
      this.#onError(new MalformedResponseError("Received a malformed JSON-RPC response"));
      return;
    }
    const id = message.id;
    if (typeof id !== "number" && typeof id !== "string") {
      this.#onError(new MalformedResponseError("JSON-RPC response id is not a string or number"));
      return;
    }
    const pending = typeof id === "number" ? this.#pending.get(id) : undefined;
    if (pending === undefined) return; // Unknown/duplicate id: ignore.
    this.#pending.delete(id as number);
    clearTimeout(pending.timer);

    if ("error" in message && message.error !== null && typeof message.error === "object") {
      const raw = message.error as { code: number; message: string; data?: unknown };
      pending.reject(mapRpcError(raw));
      return;
    }
    if ("result" in message) {
      pending.resolve(message.result);
      return;
    }
    pending.reject(new MalformedResponseError("JSON-RPC response has neither result nor error"));
  }

  #handleEvent(params: unknown): void {
    const event = params as EventNotificationParams | undefined;
    if (event === undefined || typeof event.topic !== "string") {
      this.#onError(new MalformedResponseError("Received an event notification without a topic"));
      return;
    }
    const payload = { topic: event.topic, data: event.data } as AtomcEvent;
    for (const entry of this.#subscriptions.values()) {
      if (!matchesTopic(entry.topics, event.topic)) continue;
      try {
        entry.listener(payload);
      } catch (error) {
        this.#onError(error);
      }
    }
  }

  #toText(data: WebSocket.RawData): string {
    if (typeof data === "string") return data;
    if (Buffer.isBuffer(data)) return data.toString("utf8");
    if (Array.isArray(data)) return Buffer.concat(data).toString("utf8");
    return Buffer.from(data as ArrayBuffer).toString("utf8");
  }

  /** Subscribe to daemon event topics. Returns a handle with `unsubscribe()`. */
  async subscribe(topics: readonly string[], listener: EventListener): Promise<Subscription> {
    const result = await this.request<EventsSubscribeResult>("events.subscribe", { topics });
    const id = result.subscription;
    this.#subscriptions.set(id, { topics: [...topics], listener });
    const client = this;
    return {
      id,
      topics: [...topics],
      async unsubscribe(): Promise<void> {
        client.#subscriptions.delete(id);
        await client.request<EventsUnsubscribeResult>("events.unsubscribe", {
          subscription: id,
        });
      },
    };
  }

  /** Close the socket and reject all in-flight requests. */
  async close(): Promise<void> {
    if (this.#closed) return;
    this.#closed = true;
    const socket = this.#socket;
    if (socket === undefined) {
      this.#handleClose();
      return;
    }
    const done = new Promise<void>((resolve) => {
      socket.once("close", () => {
        resolve();
      });
    });
    socket.close();
    const fallback = setTimeout(() => {
      socket.terminate();
    }, 1000);
    fallback.unref?.();
    await done;
  }

  // --- Typed method wrappers (rpc.md) ---------------------------------------

  /** `ir.get` — read the whole document or a node. */
  getIR(path = "/"): Promise<IRGetResult> {
    const params: IRGetParams = { path };
    return this.request<IRGetResult>("ir.get", params);
  }

  /** `ir.transact` — apply a relative RFC 6902 patch with optimistic concurrency. */
  transact(params: IRTransactParams): Promise<IRTransactResult> {
    return this.request<IRTransactResult>("ir.transact", params);
  }

  /** `ir.lock` — acquire a subtree lock. */
  lock(node: string, holder: string, ttlS: number, reason?: string): Promise<IRLockResult> {
    const params =
      reason === undefined ? { node, holder, ttl_s: ttlS } : { node, holder, ttl_s: ttlS, reason };
    return this.request<IRLockResult>("ir.lock", params);
  }

  /** `ir.unlock` — release a subtree lock. */
  unlock(node: string, holder: string): Promise<IRUnlockResult> {
    return this.request<IRUnlockResult>("ir.unlock", { node, holder });
  }

  /** `dag.status` — current DAG node states. */
  dagStatus(): Promise<DagStatusResult> {
    return this.request<DagStatusResult>("dag.status", {});
  }

  /** `dag.run` — queue a DAG run; progress arrives as events. */
  runDAG(params: DagRunParams = {}): Promise<DagRunResult> {
    return this.request<DagRunResult>("dag.run", params);
  }

  /** `gates.list` — list known gate results, optionally filtered by id. */
  listGates(ids?: readonly string[]): Promise<GateResult[]> {
    return this.request<GateResult[]>("gates.list", ids === undefined ? {} : { ids });
  }

  /** `gates.run` — evaluate gates, optionally filtered by id. */
  runGates(ids?: readonly string[]): Promise<GateResult[]> {
    return this.request<GateResult[]>("gates.run", ids === undefined ? {} : { ids });
  }

  /** `plugins.list` — loaded plugins plus manifest and load status. */
  listPlugins(): Promise<PluginStatus[]> {
    return this.request<PluginStatus[]>("plugins.list", {});
  }

  /** `tools.list` — available tools, optionally filtered by agent allow-list. */
  listTools(agent?: AgentName): Promise<ToolInfo[]> {
    return this.request<ToolInfo[]>("tools.list", agent === undefined ? {} : { agent });
  }

  /** `tools.call` — invoke a plugin tool. */
  callTool(plugin: string, tool: string, args: unknown, holder?: string): Promise<ToolsCallResult> {
    const params: ToolsCallParams =
      holder === undefined ? { plugin, tool, args } : { plugin, tool, args, holder };
    return this.request<ToolsCallResult>("tools.call", params);
  }

  /** `daemon.status` — live daemon metadata. */
  daemonStatus(): Promise<DaemonStatusResult> {
    return this.request<DaemonStatusResult>("daemon.status", {});
  }

  /** `daemon.shutdown` — ask the daemon to stop; the socket closes after the response. */
  shutdown(): Promise<DaemonShutdownResult> {
    return this.request<DaemonShutdownResult>("daemon.shutdown", {});
  }
}

function matchesTopic(topics: readonly string[], topic: string): boolean {
  if (topics.length === 0) return true;
  return topics.includes("*") || topics.includes(topic);
}
