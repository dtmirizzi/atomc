#!/usr/bin/env node
/** `atomc` binary entry point. */
import { createDefaultDeps } from "./default-deps.js";
import { runCli } from "./program.js";

runCli(createDefaultDeps())
  .then((code) => {
    process.exitCode = code;
  })
  .catch((error: unknown) => {
    process.stderr.write(`error: ${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
