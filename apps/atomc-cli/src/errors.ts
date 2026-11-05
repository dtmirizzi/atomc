/** Structured CLI failure with an explicit process exit code. */
export class CliError extends Error {
  readonly exitCode: number;
  readonly details: Record<string, unknown> | undefined;

  constructor(message: string, exitCode = 1, details?: Record<string, unknown>) {
    super(message);
    this.name = "CliError";
    this.exitCode = exitCode;
    this.details = details;
  }
}

/** Exit code used for capabilities that are planned but not yet implemented. */
export const EXIT_UNAVAILABLE = 3;

/**
 * Signal a nonzero exit code *after* the command has already emitted its output.
 * The top-level handler returns the code without printing an additional error.
 */
export class CliExit extends Error {
  readonly exitCode: number;

  constructor(exitCode: number) {
    super(`command exited with code ${exitCode}`);
    this.name = "CliExit";
    this.exitCode = exitCode;
  }
}
