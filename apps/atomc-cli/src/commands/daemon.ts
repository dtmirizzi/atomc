/** `atomc daemon {start,status,stop}` — daemon lifecycle via @atomc/daemon-client. */
import { resolve } from "node:path";
import type { CliDeps } from "../deps.js";
import { emit } from "../output.js";

export interface DaemonOptions {
  json?: boolean;
  project?: string;
}

/** `atomc daemon start` — attach to or spawn a daemon for the project. */
export async function daemonStart(deps: CliDeps, options: DaemonOptions = {}): Promise<number> {
  const projectRoot = resolve(deps.cwd, options.project ?? ".");
  const handle = await deps.ensureDaemon(projectRoot);
  const payload = {
    running: true,
    started: handle.started,
    pid: handle.info.pid,
    host: handle.info.host,
    port: handle.info.port,
    version: handle.info.version,
    project_root: handle.info.project_root,
  };
  emit(deps, options.json === true, payload, [
    `${handle.started ? "started" : "attached to"} daemon pid ${handle.info.pid} ` +
      `at ${handle.info.host}:${handle.info.port} (project ${handle.info.project_root})`,
  ]);
  await handle.client.close().catch(() => undefined);
  return 0;
}

/** `atomc daemon status` — report the daemon without spawning one. */
export async function daemonStatus(deps: CliDeps, options: DaemonOptions = {}): Promise<number> {
  const handle = await deps.findDaemon();
  if (handle === undefined) {
    emit(deps, options.json === true, { running: false }, ["daemon: not running"]);
    return 0;
  }
  const status = await handle.client.daemonStatus();
  const payload = {
    running: true,
    pid: status.pid,
    host: status.host,
    port: status.port,
    version: status.version,
    project_root: status.project_root,
    uptime_ms: status.uptime_ms,
  };
  emit(deps, options.json === true, payload, [
    `daemon: running pid ${status.pid} at ${status.host}:${status.port} ` +
      `(v${status.version}, project ${status.project_root}, up ${status.uptime_ms} ms)`,
  ]);
  await handle.client.close().catch(() => undefined);
  return 0;
}

/** `atomc daemon stop` — request shutdown of a running daemon. */
export async function daemonStop(deps: CliDeps, options: DaemonOptions = {}): Promise<number> {
  const handle = await deps.findDaemon();
  if (handle === undefined) {
    emit(deps, options.json === true, { stopped: false, reason: "not running" }, [
      "daemon: not running",
    ]);
    return 0;
  }
  try {
    await handle.client.shutdown();
  } finally {
    await handle.client.close().catch(() => undefined);
  }
  emit(deps, options.json === true, { stopped: true, pid: handle.info.pid }, [
    `daemon: stopped pid ${handle.info.pid}`,
  ]);
  return 0;
}
