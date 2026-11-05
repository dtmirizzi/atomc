import { describe, expect, it } from "vitest";
import {
  APPROVED_TOP_LEVEL_SCOPES,
  AtomcPluginManifestSchema,
  isValidHandlerReference,
  MANIFEST_VERSION,
  PluginManifestError,
  parsePluginManifest,
  validatePluginManifest,
} from "../src/manifest.js";
import { loadFixture, mutableFixture } from "./helpers.js";

const valid = () => mutableFixture("valid", "full.json");

function firstError(input: unknown) {
  const result = validatePluginManifest(input);
  expect(result.success).toBe(false);
  return result.issues;
}

describe("valid fixtures", () => {
  it("parses the contract example with defaults applied", () => {
    const manifest = parsePluginManifest(loadFixture("valid", "full.json"));
    expect(manifest.name).toBe("sourcing");
    expect(manifest.watches[0]?.debounce_ms).toBe(500);
    expect(manifest.watches[0]?.files).toEqual(["**/*.ato"]);
  });

  it("applies files/debounce defaults and accepts empty arrays", () => {
    const manifest = parsePluginManifest(loadFixture("valid", "minimal.json"));
    expect(manifest.watches).toEqual([]);
    expect(manifest.produces).toEqual([]);
  });

  it("exposes the frozen manifest version", () => {
    expect(MANIFEST_VERSION).toBe("0.1.0");
  });
});

describe("structural rules", () => {
  it("rejects unknown top-level keys", () => {
    const issues = firstError(loadFixture("invalid", "unknown-key.json"));
    expect(issues.some((issue) => issue.code === "unrecognized_keys")).toBe(true);
  });

  it("requires at least one runtime", () => {
    const issues = firstError(loadFixture("invalid", "missing-runtime.json"));
    expect(issues.some((issue) => issue.path.startsWith("runtime"))).toBe(true);
  });

  it("rejects a non-kebab-case name", () => {
    const issues = firstError(loadFixture("invalid", "bad-name.json"));
    expect(issues.some((issue) => issue.path === "name")).toBe(true);
  });

  it("rejects the plugin- prefix", () => {
    const issues = firstError({ ...valid(), name: "plugin-sourcing" });
    expect(issues.some((issue) => issue.path === "name")).toBe(true);
  });

  it("rejects a non-SemVer version", () => {
    const issues = firstError({ ...valid(), version: "1.2" });
    expect(issues.some((issue) => issue.path === "version")).toBe(true);
  });

  it("accepts SemVer pre-release and build metadata", () => {
    expect(parsePluginManifest({ ...valid(), version: "1.2.3-rc.1+build.5" }).version).toBe(
      "1.2.3-rc.1+build.5",
    );
  });

  it("rejects an invalid atomc range", () => {
    const issues = firstError({ ...valid(), atomc: "not-a-range" });
    expect(issues.some((issue) => issue.path === "atomc")).toBe(true);
  });

  it("accepts common range forms", () => {
    for (const range of ["*", "^1.2", "~1.2.3", ">=0.0.1 <0.2.0", "1.2.3 - 2.0.0", "^1 || ~2"]) {
      expect(parsePluginManifest({ ...valid(), atomc: range }).atomc).toBe(range);
    }
  });

  it("rejects an unknown manifest_version", () => {
    const issues = firstError({ ...valid(), manifest_version: "9.9.9" });
    expect(issues.some((issue) => issue.path === "manifest_version")).toBe(true);
  });

  it("rejects an out-of-range debounce", () => {
    const bad = valid();
    bad.watches = [{ id: "a:one", ir: ["/electrical"], debounce_ms: 60001 }];
    const issues = firstError(bad);
    expect(issues.some((issue) => issue.path.includes("debounce_ms"))).toBe(true);
  });

  it("rejects a malformed JSON pointer in a watch", () => {
    const bad = valid();
    bad.watches = [{ id: "a:one", ir: ["electrical"] }];
    const issues = firstError(bad);
    expect(issues.some((issue) => issue.path.includes("ir"))).toBe(true);
  });
});

describe("gate rules", () => {
  it("rejects a gate id without the gate: prefix", () => {
    const bad = valid();
    bad.gates = [{ ...(bad.gates as object[])[0], id: "bom.all_in_stock" }];
    const issues = firstError(bad);
    expect(issues.some((issue) => issue.path.includes("id"))).toBe(true);
  });

  it("rejects unknown severities and owners", () => {
    expect(
      firstError({ ...valid(), gates: [{ ...(valid().gates as object[])[0], severity: "loud" }] })
        .length,
    ).toBeGreaterThan(0);
    expect(
      firstError({
        ...valid(),
        gates: [{ ...(valid().gates as object[])[0], owner_agent: "human" }],
      }).length,
    ).toBeGreaterThan(0);
  });

  it("rejects duplicate gate ids", () => {
    const bad = valid();
    const gate = (bad.gates as object[])[0];
    bad.gates = [gate, structuredClone(gate)];
    const issues = firstError(bad);
    expect(issues.some((issue) => issue.code === "duplicate_gate_id")).toBe(true);
  });

  it("rejects after references to undeclared watches", () => {
    const issues = firstError(loadFixture("invalid", "bad-after.json"));
    expect(issues.some((issue) => issue.code === "unknown_watch_reference")).toBe(true);
  });

  it("allows after references to watches from another manifest via context", () => {
    const manifest = valid();
    manifest.gates = [{ ...(manifest.gates as object[])[0], after: ["other:watch"] }];
    const result = validatePluginManifest(manifest, { knownWatchIds: ["other:watch"] });
    expect(result.success).toBe(true);
  });
});

describe("tool rules", () => {
  it("rejects duplicate tool names", () => {
    const bad = valid();
    const tool = (bad.tools as object[])[0];
    bad.tools = [tool, structuredClone(tool)];
    const issues = firstError(bad);
    expect(issues.some((issue) => issue.code === "duplicate_tool_name")).toBe(true);
  });

  it("rejects agents outside the specialist set", () => {
    const bad = valid();
    bad.tools = [{ ...(bad.tools as object[])[0], agents: ["pm-agent"] }];
    const issues = firstError(bad);
    expect(issues.some((issue) => issue.path.includes("agents"))).toBe(true);
  });

  it("rejects mutating tools without produces scopes", () => {
    const issues = firstError(loadFixture("invalid", "mutating-tool-no-produces.json"));
    expect(issues.some((issue) => issue.code === "mutating_tool_without_produces")).toBe(true);
  });

  it("accepts a mutating tool when produces is declared", () => {
    const manifest = valid();
    manifest.tools = [{ ...(manifest.tools as object[])[0], mutates: true }];
    expect(parsePluginManifest(manifest).tools[0]?.mutates).toBe(true);
  });
});

describe("produces rules", () => {
  it("rejects writes to /meta", () => {
    const issues = firstError(loadFixture("invalid", "forbidden-meta-scope.json"));
    expect(issues.some((issue) => issue.path === "produces[0]")).toBe(true);
  });

  it("rejects unapproved top-level scopes", () => {
    const issues = firstError({ ...valid(), produces: ["/secrets"] });
    expect(issues.some((issue) => issue.path === "produces[0]")).toBe(true);
  });

  it("accepts every approved top-level scope and descendants", () => {
    for (const scope of APPROVED_TOP_LEVEL_SCOPES) {
      const manifest = { ...valid(), produces: [`/${scope}`, `/${scope}/child`] };
      expect(validatePluginManifest(manifest).success).toBe(true);
    }
  });

  it("rejects duplicate produces scopes", () => {
    const issues = firstError({ ...valid(), produces: ["/sourcing", "/sourcing"] });
    expect(issues.some((issue) => issue.path.includes("produces"))).toBe(true);
  });
});

describe("cli and ui rules", () => {
  it("rejects duplicate CLI commands", () => {
    const bad = valid();
    const entry = (bad.cli as object[])[0];
    bad.cli = [entry, structuredClone(entry)];
    const issues = firstError(bad);
    expect(issues.some((issue) => issue.code === "duplicate_cli_command")).toBe(true);
  });

  it("rejects reserved CLI commands when the host supplies them", () => {
    const result = validatePluginManifest(valid(), { reservedCliCommands: ["quote"] });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.issues.some((issue) => issue.code === "reserved_cli_command")).toBe(true);
    }
  });

  it("rejects duplicate UI panels", () => {
    const bad = valid();
    const panel = (bad.ui as object[])[0];
    bad.ui = [panel, structuredClone(panel)];
    const issues = firstError(bad);
    expect(issues.some((issue) => issue.code === "duplicate_ui_panel")).toBe(true);
  });

  it("rejects UI entries that escape the package root", () => {
    const issues = firstError(loadFixture("invalid", "ui-escape.json"));
    expect(issues.some((issue) => issue.path.includes("entry"))).toBe(true);
  });

  it("rejects UI panels known from another manifest via context", () => {
    const result = validatePluginManifest(valid(), { knownUiPanels: ["bom"] });
    expect(result.success).toBe(false);
  });
});

describe("cross-manifest uniqueness", () => {
  it("rejects watch and gate ids already loaded", () => {
    const watch = validatePluginManifest(valid(), { knownWatchIds: ["sourcing:bom-refresh"] });
    expect(watch.success).toBe(false);
    const gate = validatePluginManifest(valid(), { knownGateIds: ["gate:bom.all_in_stock"] });
    expect(gate.success).toBe(false);
  });
});

describe("handler reference syntax", () => {
  it("accepts bare names, python refs and relative export paths", () => {
    for (const handler of [
      "check_all_in_stock",
      "atomc_plugin_sourcing:check_all_in_stock",
      "./handlers/bom.js",
      "./handlers/bom.js#check",
    ]) {
      expect(isValidHandlerReference(handler)).toBe(true);
    }
  });

  it("rejects absolute paths, escaping paths and empty strings", () => {
    for (const handler of ["", "/abs/handler.js", "./../handler.js", "a b"]) {
      expect(isValidHandlerReference(handler)).toBe(false);
    }
  });

  it("rejects bad handlers at parse time", () => {
    const issues = firstError(loadFixture("invalid", "bad-handler.json"));
    expect(issues.some((issue) => issue.path.includes("handler"))).toBe(true);
  });
});

describe("error surface", () => {
  it("throws PluginManifestError with path-oriented issues", () => {
    expect(() => parsePluginManifest({ ...valid(), version: "nope" })).toThrow(PluginManifestError);
    try {
      parsePluginManifest({ ...valid(), version: "nope" });
    } catch (error) {
      expect(error).toBeInstanceOf(PluginManifestError);
      expect((error as PluginManifestError).issues[0]?.path).toBe("version");
    }
  });

  it("exposes the schema for direct use", () => {
    expect(AtomcPluginManifestSchema.safeParse(valid()).success).toBe(true);
  });
});
