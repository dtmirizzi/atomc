/** Output discipline: `--json` emits exactly one JSON object to stdout. */
import type { CliDeps } from "./deps.js";

/** Emit a single JSON document to stdout, or `human` lines to stderr. */
export function emit(
  deps: CliDeps,
  json: boolean,
  payload: Record<string, unknown>,
  human: string[],
): void {
  if (json) {
    deps.io.out(`${JSON.stringify(payload, null, 2)}\n`);
    return;
  }
  for (const line of human) deps.io.err(`${line}\n`);
}
