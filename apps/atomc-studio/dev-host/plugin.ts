/**
 * Dev-only Studio host bridge.
 *
 * Production hosts (Electron etc.) inject `window.atomcStudioHost` via a context bridge and
 * keep the daemon bearer token out of the browser. This plugin provides the same seam for
 * local development: a Node-side WebSocket proxy that holds the token (read from
 * `~/.atomc/daemon.json`, never sent to the browser) and forwards the browser-safe RPC
 * subset to the daemon.
 *
 * DEV ONLY. The plugin is wired into `vite.config.ts`'s serve path and never ships in
 * production builds; the browser talks to an unauthenticated loopback proxy endpoint.
 */
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import { DaemonClient } from "@atomc/daemon-client";
import type { Plugin, ViteDevServer } from "vite";
import { type WebSocket, WebSocketServer } from "ws";

interface DaemonState {
  pid: number;
  host: string;
  port: number;
  token: string;
}

const PROXY_PATH = "/@dev-host/rpc";
const BRIDGE_PATH = "/@dev-host/bridge.js";

function readDaemonState(home: string): DaemonState | undefined {
  try {
    const parsed = JSON.parse(readFileSync(`${home}/.atomc/daemon.json`, "utf8"));
    if (
      typeof parsed.host === "string" &&
      typeof parsed.port === "number" &&
      typeof parsed.token === "string"
    ) {
      return parsed as DaemonState;
    }
    return undefined;
  } catch {
    return undefined;
  }
}

/** Allowed browser->daemon methods: the read/run surface Studio needs, nothing mutating beyond `dag.run`. */
const METHODS = new Set(["ir.get", "dag.status", "gates.list", "tools.list", "dag.run"]);

/**
 * The browser shim served at {@link BRIDGE_PATH}. Plain JS on purpose: it must load before the
 * app bundle and define `window.atomcStudioHost`.
 */
const BRIDGE_SOURCE = `
// atomc dev host bridge: DEV ONLY. Connects to the local vite-side RPC proxy, which holds
// the real daemon token server-side. Production hosts replace this with a context bridge.
(function () {
  function devRpcClient() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const url = proto + "://" + location.host + "${PROXY_PATH}";
    var socket = null;
    var pending = new Map();
    var nextId = 1;
    var queue = [];

    function connect() {
      return new Promise(function (resolve, reject) {
        try { socket = new WebSocket(url); } catch (err) { reject(err); return; }
        socket.onopen = function () {
          queue.splice(0).forEach(function (frame) { socket.send(frame); });
          resolve();
        };
        socket.onerror = function () { reject(new Error("dev host bridge: proxy unreachable")); };
        socket.onclose = function () {
          pending.forEach(function (entry) { entry.reject(new Error("dev host bridge: connection closed")); });
          pending.clear();
        };
        socket.onmessage = function (event) {
          try {
            var msg = JSON.parse(event.data);
            var entry = pending.get(msg.id);
            if (!entry) return;
            pending.delete(msg.id);
            if (msg.error) entry.reject(new Error(msg.error.message || "rpc error"));
            else entry.resolve(msg.result);
          } catch (err) { /* ignore malformed frame */ }
        };
      });
    }

    function call(method, params) {
      var id = nextId++;
      var frame = JSON.stringify({ jsonrpc: "2.0", id: id, method: method, params: params });
      return new Promise(function (resolve, reject) {
        pending.set(id, { resolve: resolve, reject: reject });
        if (socket && socket.readyState === WebSocket.OPEN) socket.send(frame);
        else queue.push(frame);
      });
    }

    var ready = connect();
    return {
      getIR: function (path) { return ready.then(function () { return call("ir.get", { path: path || "/" }); }); },
      dagStatus: function () { return ready.then(function () { return call("dag.status", {}); }); },
      listGates: function () { return ready.then(function () { return call("gates.list", {}); }); },
      listTools: function (agent) { return ready.then(function () { return call("tools.list", agent ? { agent: agent } : {}); }); },
      runDAG: function (params) { return ready.then(function () { return call("dag.run", params || {}); }); },
    };
  }

  window.atomcStudioHost = {
    connectDaemon: function (options) {
      if (options && typeof options.url === "string") {
        var host = new URL(options.url).hostname;
        if (!["localhost", "127.0.0.1", "[::1]"].includes(host)) {
          return Promise.reject(new Error("dev host bridge: only loopback daemons"));
        }
      }
      return Promise.resolve(devRpcClient());
    },
  };
})();
`;

/**
 * Create the dev host bridge plugin. Enabled in `vite serve` only when
 * `ATOMC_STUDIO_DEV_HOST` is not `"0"`.
 */
export function devHostBridge(): Plugin {
  const state = () => readDaemonState(process.env.HOME ?? process.cwd());
  let rpcServer: WebSocketServer | undefined;

  const startProxy = (server: ViteDevServer): void => {
    rpcServer = new WebSocketServer({ noServer: true });
    rpcServer.on("connection", (browser: WebSocket) => {
      let client: DaemonClient | undefined;
      const pending = new Map<
        number,
        { resolve: (v: unknown) => void; reject: (e: Error) => void }
      >();
      const nextId = 1;

      const connectDaemon = async (): Promise<DaemonClient> => {
        if (client !== undefined) return client;
        const info = state();
        if (info === undefined) {
          throw new Error(
            "dev host bridge: no daemon.json under ~/.atomc — start one with 'atomc build --project <dir>'",
          );
        }
        client = await DaemonClient.connect({
          url: `ws://${info.host}:${info.port}/rpc`,
          token: info.token,
        });
        // Forward daemon notifications to the browser as untyped frames.
        return client;
      };

      browser.on("message", (data: unknown) => {
        void (async () => {
          let frame: { id?: number; method?: string; params?: unknown };
          try {
            frame = JSON.parse(String(data));
          } catch {
            browser.send(
              JSON.stringify({ jsonrpc: "2.0", id: null, error: { message: "bad frame" } }),
            );
            return;
          }
          if (frame.id === undefined || typeof frame.method !== "string") return;
          if (!METHODS.has(frame.method)) {
            browser.send(
              JSON.stringify({
                jsonrpc: "2.0",
                id: frame.id,
                error: { message: `method ${frame.method} not allowed by the dev host bridge` },
              }),
            );
            return;
          }
          try {
            const daemon = await connectDaemon();
            const result = await callOnDaemon(daemon, frame.method, frame.params);
            browser.send(JSON.stringify({ jsonrpc: "2.0", id: frame.id, result }));
          } catch (error) {
            browser.send(
              JSON.stringify({
                jsonrpc: "2.0",
                id: frame.id,
                error: { message: error instanceof Error ? error.message : String(error) },
              }),
            );
          }
        })();
      });

      browser.on("close", () => {
        void client?.close();
        pending.clear();
      });
      void pending; // kept for future notification fan-out
    });

    server.httpServer?.on("upgrade", (request, socket, head) => {
      if (request.url?.split("?")[0] === PROXY_PATH) {
        rpcServer?.handleUpgrade(request, socket as never, head, (ws) => {
          rpcServer?.emit("connection", ws, request);
        });
      }
    });
  };

  return {
    name: "atomc-dev-host-bridge",
    apply: "serve",
    configureServer(server) {
      // Serve the browser shim without touching the app bundle.
      server.middlewares.use((req, res, next) => {
        if (req.url?.split("?")[0] === BRIDGE_PATH) {
          res.setHeader("content-type", "application/javascript");
          res.end(BRIDGE_SOURCE);
          return;
        }
        if (req.url?.split("?")[0] === PROXY_PATH && req.method !== "GET") {
          res.statusCode = 426;
          res.end("upgrade required");
          return;
        }
        next();
      });
      startProxy(server);
    },
    transformIndexHtml() {
      return [
        {
          tag: "script",
          attrs: { src: BRIDGE_PATH, "data-atomc-dev-host": "bridge" },
          injectTo: "head-prepend",
        },
      ];
    },
  };
}

/** Typed forwarding for the allowed surface. */
async function callOnDaemon(
  daemon: DaemonClient,
  method: string,
  params: unknown,
): Promise<unknown> {
  const p = (params ?? {}) as Record<string, unknown>;
  switch (method) {
    case "ir.get":
      return daemon.getIR(typeof p.path === "string" ? p.path : "/");
    case "dag.status":
    case "dagStatus":
      return daemon.dagStatus();
    case "gates.list":
      return daemon.listGates(Array.isArray(p.ids) ? (p.ids as string[]) : undefined);
    case "tools.list":
      return daemon.listTools(typeof p.agent === "string" ? (p.agent as never) : undefined);
    case "dag.run":
      return daemon.runDAG({
        ...(Array.isArray(p.targets) ? { targets: p.targets as string[] } : {}),
        ...(typeof p.force === "boolean" ? { force: p.force } : {}),
      });
    default:
      throw new Error(`unreachable method ${method}`);
  }
}

/** Exported for tests: the HTTP server shape used to detect the plugin in isolation. */
export const __internals = { createServer, readDaemonState, METHODS, PROXY_PATH, BRIDGE_PATH };
