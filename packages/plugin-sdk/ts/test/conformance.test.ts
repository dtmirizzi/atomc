import { describe, expect, it } from "vitest";
import {
  assertAgentAccess,
  assertConformance,
  conformance,
  findTool,
  isWithinProduces,
  PluginConformanceError,
  validateToolInput,
} from "../src/conformance.js";
import { type AtomcPluginManifest, parsePluginManifest } from "../src/manifest.js";
import type { AtomcPlugin } from "../src/plugin.js";
import { loadFixture } from "./helpers.js";

function manifest(): AtomcPluginManifest {
  return parsePluginManifest(loadFixture("valid", "full.json"));
}

function fakePlugin(
  parsed: AtomcPluginManifest,
  maps: {
    gates?: ReadonlyMap<string, never>;
    tools?: ReadonlyMap<string, never>;
    cli?: ReadonlyMap<string, never>;
  } = {},
): AtomcPlugin {
  return {
    manifest: parsed,
    gates: maps.gates ?? new Map(),
    tools: maps.tools ?? new Map(),
    cli: maps.cli ?? new Map(),
  };
}

describe("validateToolInput", () => {
  it("accepts valid input", () => {
    expect(validateToolInput(manifest(), "search_parts", { mpn: "STM32F411CEU6" }).ok).toBe(true);
  });

  it("rejects missing/extra fields and wrong types", () => {
    expect(validateToolInput(manifest(), "search_parts", {}).ok).toBe(false);
    expect(validateToolInput(manifest(), "search_parts", { mpn: 5 }).ok).toBe(false);
    expect(validateToolInput(manifest(), "search_parts", { mpn: "x", extra: 1 }).ok).toBe(false);
  });

  it("reports unknown tools", () => {
    const report = validateToolInput(manifest(), "nope", {});
    expect(report.issues[0]?.code).toBe("unknown_tool");
  });

  it("reports invalid declared JSON Schemas", () => {
    const parsed = parsePluginManifest({
      ...(loadFixture("valid", "minimal.json") as Record<string, unknown>),
      tools: [
        {
          name: "broken",
          description: "broken schema",
          input_schema: { type: "nope" },
          agents: [],
          mutates: false,
          handler: "broken",
        },
      ],
    });
    const report = validateToolInput(parsed, "broken", {});
    expect(report.issues[0]?.code).toBe("invalid_input_schema");
  });
});

describe("assertAgentAccess", () => {
  it("allows declared agents and rejects others", () => {
    expect(() => assertAgentAccess(manifest(), "search_parts", "ee-agent")).not.toThrow();
    expect(() => assertAgentAccess(manifest(), "search_parts", "mech-agent")).toThrow(
      PluginConformanceError,
    );
  });

  it("rejects unknown tools", () => {
    expect(() => assertAgentAccess(manifest(), "nope", "ee-agent")).toThrow(PluginConformanceError);
  });
});

describe("isWithinProduces", () => {
  it("matches scopes and descendants", () => {
    const m = manifest();
    expect(isWithinProduces(m, "/sourcing")).toBe(true);
    expect(isWithinProduces(m, "/sourcing/bom/0")).toBe(true);
    expect(isWithinProduces(m, "/fabrication/quotes")).toBe(true);
    expect(isWithinProduces(m, "/electrical/components")).toBe(false);
    expect(isWithinProduces(m, "/sourcingx")).toBe(false);
    expect(isWithinProduces(m, "not-a-pointer")).toBe(false);
  });
});

describe("conformance", () => {
  it("finds every declared tool", () => {
    expect(findTool(manifest(), "search_parts")?.name).toBe("search_parts");
    expect(findTool(manifest(), "nope")).toBeUndefined();
  });

  it("reports missing handlers", () => {
    const parsed = manifest();
    const report = conformance(fakePlugin(parsed));
    expect(report.ok).toBe(false);
    expect(report.issues.some((issue) => issue.code === "missing_handler")).toBe(true);
  });

  it("reports undeclared handlers exposed by the descriptor", () => {
    const parsed = manifest();
    const report = conformance(
      fakePlugin(parsed, { tools: new Map([["ghost", (() => undefined) as never]]) }),
    );
    expect(report.issues.some((issue) => issue.code === "undeclared_handler")).toBe(true);
  });

  it("reports invalid tool input schemas", () => {
    const parsed = parsePluginManifest({
      ...(loadFixture("valid", "minimal.json") as Record<string, unknown>),
      tools: [
        {
          name: "broken",
          description: "broken",
          input_schema: { type: "nope" },
          agents: [],
          mutates: false,
          handler: "broken",
        },
      ],
    });
    const plugin: AtomcPlugin = {
      manifest: parsed,
      gates: new Map(),
      tools: new Map([["broken", (() => undefined) as never]]),
      cli: new Map(),
    };
    const report = conformance(plugin);
    expect(report.issues.some((issue) => issue.code === "invalid_input_schema")).toBe(true);
  });

  it("returns ok for a fully implemented plugin", () => {
    const parsed = manifest();
    const plugin: AtomcPlugin = {
      manifest: parsed,
      gates: new Map([["gate:bom.all_in_stock", (() => ({})) as never]]),
      tools: new Map([["search_parts", (() => ({})) as never]]),
      cli: new Map([["quote", (() => ({})) as never]]),
    };
    const report = conformance(plugin);
    expect(report.issues).toEqual([]);
    expect(report.ok).toBe(true);
    expect(() => assertConformance(plugin)).not.toThrow();
  });

  it("assertConformance throws with structured issues", () => {
    const parsed = manifest();
    try {
      assertConformance(fakePlugin(parsed));
      throw new Error("expected conformance to fail");
    } catch (error) {
      expect(error).toBeInstanceOf(PluginConformanceError);
      expect((error as PluginConformanceError).issues.length).toBeGreaterThan(0);
    }
  });
});
