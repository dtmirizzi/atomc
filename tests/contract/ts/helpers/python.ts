/**
 * Emit the canonical form of a `system_ir.json` document straight from Python via
 * `uv run --package atomc-core-ir python -c ...` (the brief's cross-language check),
 * using argv so paths containing spaces are safe.
 */
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { REPO_ROOT } from "./bridge.js";

const execFileAsync = promisify(execFile);

const CANONICAL_CODE =
  "import sys; from atomc_core_ir import SystemIR; sys.stdout.write(SystemIR.load(sys.argv[1]).dump())";

export async function pythonCanonical(absolutePath: string): Promise<string> {
  const { stdout } = await execFileAsync(
    "uv",
    ["run", "--package", "atomc-core-ir", "python", "-c", CANONICAL_CODE, absolutePath],
    { cwd: REPO_ROOT, maxBuffer: 64 * 1024 * 1024 },
  );
  return stdout;
}
