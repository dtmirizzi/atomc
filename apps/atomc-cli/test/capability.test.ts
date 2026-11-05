import { describe, expect, it } from "vitest";
import { runCli } from "../src/program.js";
import { FakeDaemon, makeDeps, pluginStatus } from "./helpers/fakes.js";

describe("atomc planned capabilities", () => {
  for (const command of ["sim", "jig", "quote", "orders", "converge"]) {
    it(`${command} never fakes PASS and exits 3`, async () => {
      const daemon = new FakeDaemon({ plugins: [] });
      const { deps, captured } = makeDeps({ daemon });
      const code = await runCli(deps, [command, "--json"]);
      expect(code).toBe(3);
      const payload = JSON.parse(captured.out.join(""));
      expect(payload.status).not.toBe("PASS");
      expect(["unavailable", "not_implemented"]).toContain(payload.status);
    });
  }

  it("reports a missing plugin as unavailable", async () => {
    const daemon = new FakeDaemon({ plugins: [pluginStatus("sourcing", false, "boom")] });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["quote", "--json"]);
    expect(code).toBe(3);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.status).toBe("unavailable");
    expect(payload.plugin).toBe("sourcing");
  });

  it("reports an installed plugin as not implemented rather than passing", async () => {
    const daemon = new FakeDaemon({ plugins: [pluginStatus("renode", true)] });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["sim", "--json"]);
    expect(code).toBe(3);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.status).toBe("not_implemented");
    expect(payload.hint).toContain("Phase 4");
  });

  it("prints a human-readable unavailable message", async () => {
    const daemon = new FakeDaemon({ plugins: [] });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["jig"]);
    expect(code).toBe(3);
    expect(captured.err.join("")).toContain("unavailable");
  });
});
