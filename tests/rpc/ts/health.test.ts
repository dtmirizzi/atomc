/**
 * HTTP `/health` and `/schema` contract checks against the real daemon.
 */
import { readFile } from "node:fs/promises";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { CORE_IR_SCHEMA_PATH, DaemonHarness } from "./harness.js";

interface HealthResult {
  ok: boolean;
  version: string;
  ir_rev: number;
}

describe("HTTP health and schema", () => {
  let harness: DaemonHarness;

  beforeAll(async () => {
    harness = await DaemonHarness.start();
  }, 300_000);

  afterAll(async () => {
    await harness.stop();
  });

  it("GET /health reports ok with version and ir_rev", async () => {
    const health = await harness.httpJson<HealthResult>("/health");
    expect(health.ok).toBe(true);
    expect(typeof health.version).toBe("string");
    expect(health.version.length).toBeGreaterThan(0);
    expect(health.ir_rev).toBe(0);
  });

  it("GET /schema matches the committed @atomc/core-ir schema exactly", async () => {
    const served = await harness.httpJson<Record<string, unknown>>("/schema");
    const committed = JSON.parse(await readFile(CORE_IR_SCHEMA_PATH, "utf8")) as Record<
      string,
      unknown
    >;
    expect(served).toEqual(committed);
    expect(served.schema_version).toBeUndefined();
    const properties = served.properties as Record<string, unknown>;
    expect(properties.schema_version).toBeDefined();
  });
});
