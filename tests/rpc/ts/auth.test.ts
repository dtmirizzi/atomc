/**
 * WebSocket bearer-auth policy: missing/incorrect tokens close with 1008 and a
 * valid token permits an authenticated request.
 */
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { DaemonHarness, expectPolicyClose } from "./harness.js";

describe("WebSocket bearer authentication", () => {
  let harness: DaemonHarness;

  beforeAll(async () => {
    harness = await DaemonHarness.start();
  }, 300_000);

  afterAll(async () => {
    await harness.stop();
  });

  it("closes an unauthenticated upgrade with policy code 1008", async () => {
    const state = await harness.readState();
    expect(state).not.toBeNull();
    const code = await expectPolicyClose(harness.rpcUrl, undefined);
    expect(code).toBe(1008);
  });

  it("closes a wrong-token upgrade with policy code 1008", async () => {
    const code = await expectPolicyClose(harness.rpcUrl, "not-the-real-token");
    expect(code).toBe(1008);
  });

  it("accepts a valid bearer token and serves requests", async () => {
    const client = await harness.connect();
    try {
      const status = await client.daemonStatus();
      expect(status.port).toBe(harness.port);
    } finally {
      await client.close();
    }
  });
});
