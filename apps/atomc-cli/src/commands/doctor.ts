/** `atomc doctor` — environment + daemon health checks (never requires hardware). */
import type { CliDeps, ToolProbe } from "../deps.js";
import { emit } from "../output.js";

export interface DoctorCheck {
  name: string;
  status: "PASS" | "WARN" | "SKIP" | "FAIL";
  detail: string;
}

export interface DoctorOptions {
  json?: boolean;
}

function worstStatus(checks: readonly DoctorCheck[]): "PASS" | "WARN" | "SKIP" | "FAIL" {
  if (checks.some((c) => c.status === "FAIL")) return "FAIL";
  if (checks.some((c) => c.status === "WARN")) return "WARN";
  if (checks.every((c) => c.status === "SKIP")) return "SKIP";
  return "PASS";
}

function fromToolProbe(probe: ToolProbe): DoctorCheck {
  return { name: `tool:${probe.name}`, status: probe.status, detail: probe.detail };
}

/** Run all doctor checks; returns the process exit code. */
export async function doctorCommand(deps: CliDeps, options: DoctorOptions = {}): Promise<number> {
  const checks: DoctorCheck[] = [
    { name: "cli.version", status: "PASS", detail: `@atomc/cli ${deps.cliVersion}` },
  ];

  let daemonCheck: DoctorCheck;
  try {
    const probe = await deps.probeDaemon();
    if (probe.running && probe.info) {
      const health = probe.health;
      const schemaVersion = readSchemaVersion(probe.schema);
      checks.push({
        name: "daemon.health",
        status: "PASS",
        detail: `pid ${probe.info.pid} at ${probe.info.host}:${probe.info.port} (v${probe.info.version})`,
      });
      checks.push({
        name: "daemon.schema",
        status: probe.schema ? "PASS" : "WARN",
        detail: schemaVersion ?? "schema returned without an identifiable version",
      });
      daemonCheck = {
        name: "daemon.version",
        status: probe.info.version === deps.cliVersion ? "PASS" : "FAIL",
        detail:
          probe.info.version === deps.cliVersion
            ? "CLI and daemon versions agree"
            : `daemon ${probe.info.version} != CLI ${deps.cliVersion}`,
      };
      checks.push(daemonCheck);
      if (health && health.ok !== true) {
        checks.push({ name: "daemon.health.ok", status: "FAIL", detail: "health.ok is false" });
      }
    } else {
      checks.push({
        name: "daemon.health",
        status: "WARN",
        detail: probe.detail,
      });
    }
  } catch (error) {
    checks.push({
      name: "daemon.health",
      status: "WARN",
      detail: `daemon probe failed: ${errorMessage(error)}`,
    });
  }

  const probes = await deps.probeTools();
  for (const probe of probes) checks.push(fromToolProbe(probe));

  const status = worstStatus(checks);
  const failed = checks.filter((c) => c.status === "FAIL");
  const payload = {
    ok: failed.length === 0,
    status,
    cli_version: deps.cliVersion,
    checks,
  };
  emit(
    deps,
    options.json === true,
    payload,
    checks.map((c) => `[${c.status}] ${c.name}: ${c.detail}`),
  );
  return failed.length === 0 ? 0 : 1;
}

function readSchemaVersion(schema: Record<string, unknown> | undefined): string | undefined {
  if (!schema) return undefined;
  const direct = schema["x-schema-version"];
  if (typeof direct === "string") return `schema ${direct}`;
  const props = schema.properties;
  if (props && typeof props === "object" && "schema_version" in props) {
    const sv = (props as Record<string, unknown>).schema_version;
    if (sv && typeof sv === "object" && "const" in sv) {
      return `schema_version ${String((sv as Record<string, unknown>).const)}`;
    }
  }
  return undefined;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
