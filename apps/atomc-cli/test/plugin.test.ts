import { validatePluginManifest } from "@atomc/plugin-sdk";
import { describe, expect, it } from "vitest";
import { runCli } from "../src/program.js";
import { FakeDaemon, FakeFs, getFile, makeDeps, pluginStatus } from "./helpers/fakes.js";

describe("atomc plugin new", () => {
  it("writes a manifest that validates against the frozen contract", async () => {
    const fs = new FakeFs();
    const { deps, captured } = makeDeps({ fs });
    const code = await runCli(deps, ["plugin", "new", "my-plugin", "--json"]);
    expect(code).toBe(0);
    const manifest = JSON.parse(getFile(fs, "/work/my-plugin/atomc-plugin.json"));
    expect(validatePluginManifest(manifest).success).toBe(true);
    expect(fs.entries.has("/work/my-plugin/src/index.ts")).toBe(true);
    expect(fs.entries.has("/work/my-plugin/test/manifest.test.ts")).toBe(true);
    expect(JSON.parse(captured.out.join("")).created).toBe(true);
  });

  it("scaffolds a python runtime", async () => {
    const fs = new FakeFs();
    const { deps } = makeDeps({ fs });
    const code = await runCli(deps, ["plugin", "new", "py-plugin", "--runtime", "python"]);
    expect(code).toBe(0);
    const manifest = JSON.parse(getFile(fs, "/work/py-plugin/atomc-plugin.json"));
    expect(manifest.runtime.python).toBe("atomc_plugin_py_plugin:plugin");
    expect(fs.entries.has("/work/py-plugin/python/src/atomc_plugin_py_plugin/__init__.py")).toBe(
      true,
    );
  });

  it("scaffolds both runtimes", async () => {
    const fs = new FakeFs();
    const { deps } = makeDeps({ fs });
    const code = await runCli(deps, ["plugin", "new", "both-plugin", "--runtime", "both"]);
    expect(code).toBe(0);
    const manifest = JSON.parse(getFile(fs, "/work/both-plugin/atomc-plugin.json"));
    expect(manifest.runtime.ts).toBe("./dist/index.js");
    expect(manifest.runtime.python).toBe("atomc_plugin_both_plugin:plugin");
  });

  it("rejects invalid names", async () => {
    const fs = new FakeFs();
    const { deps, captured } = makeDeps({ fs });
    const code = await runCli(deps, ["plugin", "new", "Bad Name"]);
    expect(code).toBe(1);
    expect(captured.err.join("")).toContain("invalid plugin name");
  });

  it("refuses to overwrite without --force", async () => {
    const fs = new FakeFs();
    fs.addFile("/work/existing/atomc-plugin.json", "{}");
    const { deps } = makeDeps({ fs });
    const code = await runCli(deps, ["plugin", "new", "existing"]);
    expect(code).toBe(1);
  });
});

describe("atomc plugin list", () => {
  it("prints loaded plugins as JSON", async () => {
    const daemon = new FakeDaemon({
      plugins: [pluginStatus("atopile", true), pluginStatus("renode", false, "import error")],
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["plugin", "list", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.count).toBe(2);
    expect(payload.plugins[1].loaded).toBe(false);
  });
});
