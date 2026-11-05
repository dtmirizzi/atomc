/**
 * Planned-but-unimplemented commands (`sim`, `jig`, `quote`, `orders`, `converge`).
 *
 * These never report PASS. They attach to the daemon, report whether the plugin
 * they need is installed, and return an explicit `unavailable` / `not_implemented`
 * status with an actionable hint. Exit code {@link EXIT_UNAVAILABLE} (3).
 */
import { resolve } from "node:path";
import type { CliDeps } from "../deps.js";
import { EXIT_UNAVAILABLE } from "../errors.js";
import { emit } from "../output.js";

export interface CapabilityOptions {
  json?: boolean;
  project?: string;
}

export interface CapabilitySpec {
  command: string;
  /** Daemon plugin name required for the feature, if any. */
  plugin?: string;
  summary: string;
  hint: string;
}

/** Report a capability as unavailable without ever faking a result. */
export async function capabilityCommand(
  deps: CliDeps,
  spec: CapabilitySpec,
  options: CapabilityOptions = {},
): Promise<number> {
  const projectRoot = resolve(deps.cwd, options.project ?? ".");
  const handle = await deps.ensureDaemon(projectRoot);
  try {
    const plugins = await handle.client.listPlugins();
    const loaded = spec.plugin
      ? plugins.find((p) => p.name === spec.plugin && p.loaded)
      : undefined;
    const pluginMissing = spec.plugin !== undefined && loaded === undefined;
    const status = pluginMissing ? "unavailable" : "not_implemented";
    const reason = pluginMissing
      ? `plugin "${spec.plugin}" is not installed or failed to load`
      : "feature is planned but not implemented in this CLI version";
    const payload = {
      status,
      command: spec.command,
      plugin: spec.plugin ?? null,
      reason,
      hint: pluginMissing
        ? `install the "${spec.plugin}" plugin and restart the daemon`
        : spec.hint,
      summary: spec.summary,
    };
    emit(deps, options.json === true, payload, [
      `atomc ${spec.command}: ${status} — ${reason}`,
      `  ${spec.summary}`,
      `  hint: ${payload.hint}`,
    ]);
    return EXIT_UNAVAILABLE;
  } finally {
    await handle.client.close().catch(() => undefined);
  }
}
