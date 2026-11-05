import { describe, expect, it } from "vitest";
import { runCli } from "../src/program.js";
import { FakeFs, getFile, makeDeps } from "./helpers/fakes.js";

const MINIMAL_IR = JSON.stringify({
  schema_version: "0.1.0",
  meta: {
    project_id: "proj:atomc-pad",
    name: "atomc-pad",
    created_at: "2026-11-04T00:00:00Z",
    modified_at: "2026-11-04T00:00:00Z",
    atomc_version: "0.1.0",
    rev: 0,
  },
});

const CONFIG = `const config = { project: "atomc-pad" } as const;\nexport default config;\n`;

function seedTemplate(fs: FakeFs): void {
  fs.addFile("/repo/examples/atomc-pad/ato.yaml", "requires:\n");
  fs.addFile("/repo/examples/atomc-pad/system_ir.json", MINIMAL_IR);
  fs.addFile("/repo/examples/atomc-pad/atomc.config.ts", CONFIG);
  fs.addFile("/repo/examples/atomc-pad/README.md", "# atomc-pad\n");
  fs.addFile("/repo/examples/atomc-pad/build/out.o", "binary");
  fs.addFile("/repo/examples/atomc-pad/node_modules/dep/index.js", "x");
  fs.addFile("/repo/examples/atomc-pad/.venv/pyvenv.cfg", "x");
}

describe("atomc init", () => {
  it("copies the template and rewrites project identity", async () => {
    const fs = new FakeFs();
    seedTemplate(fs);
    const { deps, captured } = makeDeps({ fs });
    const code = await runCli(deps, ["init", "my board", "--name", "my-board", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.target).toBe("/work/my board");

    const ir = JSON.parse(getFile(fs, "/work/my board/system_ir.json"));
    expect(ir.meta.project_id).toBe("proj:my-board");
    expect(ir.meta.name).toBe("my-board");

    const config = getFile(fs, "/work/my board/atomc.config.ts");
    expect(config).toContain('project: "my-board"');
  });

  it("skips build/, node_modules/ and .venv/", async () => {
    const fs = new FakeFs();
    seedTemplate(fs);
    const { deps } = makeDeps({ fs });
    await runCli(deps, ["init", "clean"]);
    expect(fs.entries.has("/work/clean/build/out.o")).toBe(false);
    expect(fs.entries.has("/work/clean/node_modules/dep/index.js")).toBe(false);
    expect(fs.entries.has("/work/clean/.venv/pyvenv.cfg")).toBe(false);
    expect(fs.entries.has("/work/clean/ato.yaml")).toBe(true);
  });

  it("refuses to overwrite a non-empty directory without --force", async () => {
    const fs = new FakeFs();
    seedTemplate(fs);
    fs.addFile("/work/existing/keep.txt", "keep");
    const { deps, captured } = makeDeps({ fs });
    const code = await runCli(deps, ["init", "existing"]);
    expect(code).toBe(1);
    expect(captured.err.join("")).toContain("--force");
    expect(fs.entries.get("/work/existing/keep.txt")?.data).toBe("keep");
  });

  it("overwrites with --force", async () => {
    const fs = new FakeFs();
    seedTemplate(fs);
    fs.addFile("/work/existing/keep.txt", "keep");
    const { deps } = makeDeps({ fs });
    const code = await runCli(deps, ["init", "existing", "--force"]);
    expect(code).toBe(0);
    expect(fs.entries.has("/work/existing/keep.txt")).toBe(false);
    expect(fs.entries.has("/work/existing/ato.yaml")).toBe(true);
  });

  it("fails clearly when the template does not exist", async () => {
    const fs = new FakeFs();
    const { deps, captured } = makeDeps({ fs });
    const code = await runCli(deps, ["init", "proj", "--template", "does-not-exist"]);
    expect(code).toBe(1);
    expect(captured.err.join("")).toContain("not found");
  });

  it("succeeds when the template has no atomc.config.ts", async () => {
    const fs = new FakeFs();
    fs.addFile("/repo/examples/atomc-pad/ato.yaml", "x");
    const { deps } = makeDeps({ fs });
    const code = await runCli(deps, ["init", "bare"]);
    expect(code).toBe(0);
    expect(fs.entries.has("/work/bare/ato.yaml")).toBe(true);
  });

  it("requires a target directory", async () => {
    const fs = new FakeFs();
    const { deps } = makeDeps({ fs });
    // Commander rejects a missing argument before our handler runs.
    const code = await runCli(deps, ["init"]);
    expect(code).toBe(1);
  });
});
