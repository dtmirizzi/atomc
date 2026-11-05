import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { runAgent } from "../src/runner.js";
import type { ToolDescriptor } from "../src/types.js";
import { FakeDaemon, FakeProvider } from "./fakes.js";
import { definition, failure } from "./runner-pass.test.js";

async function projectRoot(): Promise<string> {
  return mkdtemp(join(tmpdir(), "swarm-tool-"));
}

const descriptor: ToolDescriptor = {
  plugin: "sourcing",
  name: "solve",
  description: "solve the BOM",
  input_schema: { type: "object" },
  mutates: true,
};

describe("runAgent — tool allow-list", () => {
  it("rejects a tool outside the allow-list without calling the daemon", async () => {
    const daemon = new FakeDaemon();
    daemon.tools = [descriptor];
    const events: string[] = [];
    const result = await runAgent({
      definition: definition({ permittedTools: [], budget: { maxTurns: 3, maxCostMinor: 100 } }),
      failure,
      daemon,
      provider: new FakeProvider([
        { kind: "tool", tool: { plugin: "sourcing", tool: "solve", args: {} } },
        { kind: "verify" },
      ]),
      projectRoot: await projectRoot(),
      runId: "reject-tool-run",
      onEvent: (event) => events.push(event.kind),
    });

    expect(result.outcome).toBe("PASS");
    expect(daemon.toolCalls).toBe(0);
    expect(events).toContain("tool.rejected");
  });

  it("invokes a permitted tool with the holder id", async () => {
    const daemon = new FakeDaemon();
    daemon.tools = [descriptor];
    const result = await runAgent({
      definition: definition({ permittedTools: ["sourcing:solve"] }),
      failure,
      daemon,
      provider: new FakeProvider([
        { kind: "tool", tool: { plugin: "sourcing", tool: "solve", args: { qty: 5 } } },
        { kind: "verify" },
      ]),
      projectRoot: await projectRoot(),
      runId: "allow-tool-run",
    });

    expect(result.outcome).toBe("PASS");
    expect(daemon.toolCalls).toBe(1);
    expect(daemon.events).toContain("callTool:sourcing:solve");
  });
});
