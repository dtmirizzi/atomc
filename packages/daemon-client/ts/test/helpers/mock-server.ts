import { type AddressInfo, WebSocket, WebSocketServer } from "ws";

/** Returned by a handler to suppress the response (for timeout tests). */
export const NO_RESPONSE: unique symbol = Symbol("no-response");

/** A parsed request observed by the mock server. */
export interface MockRequest {
  id: number | string;
  method: string;
  params: unknown;
  raw: Record<string, unknown>;
  socket: WebSocket;
}

/** Wrap an error object so the mock server emits a JSON-RPC error response. */
export class RpcErrorResponse {
  constructor(readonly error: { code: number; message: string; data?: unknown }) {}
}

/** Build a JSON-RPC error response. */
export function rpcError(code: number, message: string, data?: unknown): RpcErrorResponse {
  return new RpcErrorResponse({ code, message, ...(data === undefined ? {} : { data }) });
}

/** Handler invoked for every parsed request. */
export type MockHandler = (
  request: MockRequest,
) => unknown | typeof NO_RESPONSE | Promise<unknown | typeof NO_RESPONSE>;

export interface MockServerOptions {
  handler: MockHandler;
  /** When set, the server rejects connections whose Authorization header differs. */
  requireToken?: string;
}

/** Deterministic JSON-RPC WebSocket server on an ephemeral loopback port. */
export class MockRpcServer {
  readonly url: string;
  readonly requests: MockRequest[] = [];
  readonly #wss: WebSocketServer;
  readonly #sockets = new Set<WebSocket>();
  readonly #handler: MockHandler;
  readonly #requireToken: string | undefined;

  private constructor(options: MockServerOptions, wss: WebSocketServer, port: number) {
    this.#handler = options.handler;
    this.#requireToken = options.requireToken;
    this.#wss = wss;
    this.url = `ws://127.0.0.1:${port}/rpc`;
    wss.on("connection", (socket, request) => {
      if (
        this.#requireToken !== undefined &&
        request.headers.authorization !== `Bearer ${this.#requireToken}`
      ) {
        socket.close(1008, "unauthorized");
        return;
      }
      this.#sockets.add(socket);
      socket.on("close", () => {
        this.#sockets.delete(socket);
      });
      socket.on("message", (data) => {
        void this.#onMessage(socket, data.toString("utf8"));
      });
    });
  }

  static start(options: MockServerOptions): Promise<MockRpcServer> {
    return new Promise((resolve, reject) => {
      const wss = new WebSocketServer({
        host: "127.0.0.1",
        port: 0,
        ...(options.requireToken === undefined
          ? {}
          : {
              verifyClient: (
                info: { req: { headers: Record<string, string | string[] | undefined> } },
                cb: (ok: boolean, code?: number, message?: string) => void,
              ) => {
                if (info.req.headers.authorization === `Bearer ${options.requireToken}`) {
                  cb(true);
                } else {
                  cb(false, 401, "Unauthorized");
                }
              },
            }),
      });
      wss.once("error", reject);
      wss.once("listening", () => {
        const address = wss.address() as AddressInfo;
        resolve(new MockRpcServer(options, wss, address.port));
      });
    });
  }

  async #onMessage(socket: WebSocket, text: string): Promise<void> {
    let raw: Record<string, unknown>;
    try {
      raw = JSON.parse(text) as Record<string, unknown>;
    } catch {
      socket.send("not json");
      return;
    }
    const request: MockRequest = {
      id: raw.id as number | string,
      method: typeof raw.method === "string" ? raw.method : "",
      params: raw.params,
      raw,
      socket,
    };
    this.requests.push(request);
    const outcome = await this.#handler(request);
    if (outcome === NO_RESPONSE || socket.readyState !== WebSocket.OPEN) return;
    if (outcome instanceof RpcErrorResponse) {
      socket.send(JSON.stringify({ jsonrpc: "2.0", id: request.id, error: outcome.error }));
      return;
    }
    socket.send(JSON.stringify({ jsonrpc: "2.0", id: request.id, result: outcome ?? null }));
  }

  /** Send a raw string frame to every connected socket. */
  sendRaw(text: string): void {
    for (const socket of this.#sockets) {
      if (socket.readyState === WebSocket.OPEN) socket.send(text);
    }
  }

  /** Send an `event` notification to every connected socket. */
  notify(topic: string, data: unknown): void {
    this.sendObject({ jsonrpc: "2.0", method: "event", params: { topic, data } });
  }

  /** Send an arbitrary object to every connected socket. */
  sendObject(message: unknown): void {
    const text = JSON.stringify(message);
    for (const socket of this.#sockets) {
      if (socket.readyState === WebSocket.OPEN) socket.send(text);
    }
  }

  /** Abruptly destroy all sockets (simulates a daemon crash). */
  terminateAll(): void {
    for (const socket of this.#sockets) socket.terminate();
  }

  async close(): Promise<void> {
    for (const socket of this.#sockets) socket.terminate();
    this.#sockets.clear();
    await new Promise<void>((resolve) => {
      this.#wss.close(() => {
        resolve();
      });
    });
  }
}
