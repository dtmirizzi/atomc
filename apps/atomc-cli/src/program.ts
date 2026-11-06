/** Commander 15 command tree for the `atomc` CLI. */
import { Command, CommanderError, Option } from "commander";
import { buildCommand } from "./commands/build.js";
import { type CapabilitySpec, capabilityCommand } from "./commands/capability.js";
import { convergeCommand } from "./commands/converge.js";
import { daemonStart, daemonStatus, daemonStop } from "./commands/daemon.js";
import { doctorCommand } from "./commands/doctor.js";
import { initCommand } from "./commands/init.js";
import { pluginList, pluginNew } from "./commands/plugin.js";
import type { CliDeps } from "./deps.js";
import { CliError, CliExit } from "./errors.js";

const CAPABILITIES: Record<string, CapabilitySpec> = {
  sim: {
    command: "sim",
    plugin: "renode",
    summary: "generate a Renode platform/script and run hardware-in-the-loop-style scenarios",
    hint: "track Renode simulation in plugin-renode (Phase 4)",
  },
  jig: {
    command: "jig",
    plugin: "cad-jig",
    summary: "generate the pogo-pin test jig, switch plate and case from the IR",
    hint: "track CAD generation in plugin-cad-jig (Phase 4)",
  },
  quote: {
    command: "quote",
    plugin: "sourcing",
    summary: "refresh BOM offers and fabrication quotes against a budget",
    hint: "track sourcing in plugin-sourcing (Phase 5)",
  },
  orders: {
    command: "orders",
    plugin: "orders",
    summary: "place and track part/PCB/PCBA orders",
    hint: "track order placement in plugin-orders (Phase 5)",
  },
};

/** Wrap a command function so a nonzero code becomes a silent process exit. */
function action<A extends unknown[]>(
  fn: (...args: A) => Promise<number>,
): (...args: A) => Promise<void> {
  return async (...args: A) => {
    const code = await fn(...args);
    if (code !== 0) throw new CliExit(code);
  };
}

/** Build the full `atomc` command tree against injected dependencies. */
export function buildProgram(deps: CliDeps): Command {
  const program = new Command();
  program
    .name("atomc")
    .description("compile declarative hardware descriptions into verified physical systems")
    .version(deps.cliVersion)
    .configureOutput({
      writeOut: (text) => deps.io.out(text),
      writeErr: (text) => deps.io.err(text),
    });

  program
    .command("init")
    .description("scaffold a new atomc project from an example template")
    .argument("<dir>", "target directory")
    .option("--force", "overwrite a non-empty target directory")
    .option("--name <name>", "project name (defaults to the directory name)")
    .option("--template <name>", "example template under examples/", "atomc-pad")
    .option("--json", "emit machine-readable JSON")
    .action(
      action(
        (
          dir: string,
          options: { force?: boolean; name?: string; template?: string; json?: boolean },
        ) => initCommand(deps, dir, options),
      ),
    );

  program
    .command("build")
    .description("run the daemon DAG and summarize nodes and gates")
    .argument("[target]", "optional DAG node id to build")
    .option("--project <dir>", "project root", ".")
    .option("--force", "force a full rebuild")
    .option("--timeout <ms>", "DAG run timeout in milliseconds")
    .option("--json", "emit machine-readable JSON")
    .action(
      action(
        (
          target: string | undefined,
          options: { json?: boolean; project?: string; force?: boolean; timeout?: string },
        ) => buildCommand(deps, target, options),
      ),
    );

  const converge = program
    .command("converge")
    .description("run bounded specialist sessions until blocking gates pass")
    .option("--project <dir>", "project root", ".")
    .option("--max-rounds <n>", "maximum swarm rounds", "3")
    .option("--max-cost <usd>", "maximum aggregate model spend in dollars", "2.00")
    .option("--json", "emit one machine-readable result");
  converge.action(
    action((options: { project?: string; maxRounds?: string; maxCost?: string; json?: boolean }) =>
      convergeCommand(deps, options),
    ),
  );

  for (const spec of Object.values(CAPABILITIES)) {
    program
      .command(spec.command)
      .description(spec.summary)
      .argument("[target]", "optional target")
      .option("--project <dir>", "project root", ".")
      .option("--json", "emit machine-readable JSON")
      .action(
        action((_target: string | undefined, options: { json?: boolean; project?: string }) =>
          capabilityCommand(deps, spec, options),
        ),
      );
  }

  program
    .command("doctor")
    .description("check the CLI, daemon and local toolchains")
    .option("--json", "emit machine-readable JSON")
    .action(action((options: { json?: boolean }) => doctorCommand(deps, options)));

  const daemon = program.command("daemon").description("manage the atomcd daemon");
  daemon
    .command("start")
    .description("start (or attach to) the daemon")
    .option("--project <dir>", "project root", ".")
    .option("--json", "emit machine-readable JSON")
    .action(action((options: { json?: boolean; project?: string }) => daemonStart(deps, options)));
  daemon
    .command("status")
    .description("report whether the daemon is running")
    .option("--json", "emit machine-readable JSON")
    .action(action((options: { json?: boolean; project?: string }) => daemonStatus(deps, options)));
  daemon
    .command("stop")
    .description("stop a running daemon")
    .option("--json", "emit machine-readable JSON")
    .action(action((options: { json?: boolean; project?: string }) => daemonStop(deps, options)));

  const plugin = program.command("plugin").description("inspect and scaffold plugins");
  plugin
    .command("list")
    .description("list plugins loaded by the daemon")
    .option("--project <dir>", "project root", ".")
    .option("--json", "emit machine-readable JSON")
    .action(action((options: { json?: boolean; project?: string }) => pluginList(deps, options)));
  plugin
    .command("new")
    .description("scaffold a new plugin package")
    .argument("<name>", "plugin name (kebab-case)")
    .addOption(
      new Option("--runtime <runtime>", "plugin runtime")
        .choices(["ts", "python", "both"])
        .default("ts"),
    )
    .option("--dir <dir>", "output directory (defaults to ./<name>)")
    .option("--force", "overwrite existing files")
    .option("--json", "emit machine-readable JSON")
    .action(
      action(
        (
          name: string,
          options: {
            runtime?: "ts" | "python" | "both";
            dir?: string;
            force?: boolean;
            json?: boolean;
          },
        ) => pluginNew(deps, name, options),
      ),
    );

  return program;
}

/** Parse `argv` and return the intended process exit code (never throws). */
export async function runCli(
  deps: CliDeps,
  argv: readonly string[] = process.argv.slice(2),
): Promise<number> {
  const program = buildProgram(deps);
  program.exitOverride();
  try {
    await program.parseAsync([...argv], { from: "user" });
    return 0;
  } catch (error) {
    if (error instanceof CliExit) return error.exitCode;
    if (error instanceof CliError) {
      deps.io.err(`error: ${error.message}\n`);
      return error.exitCode;
    }
    if (error instanceof CommanderError) {
      return typeof error.exitCode === "number" ? error.exitCode : 1;
    }
    deps.io.err(`error: ${error instanceof Error ? error.message : String(error)}\n`);
    return 1;
  }
}
