import { describe, expect, it } from "vitest";
import {
  AGENT_DEFINITIONS,
  AGENT_NAMES,
  AgentDefinitionError,
  AgentRegistry,
  allAgentDefinitions,
  DEFAULT_AGENT_MODEL,
  defaultAgentRegistry,
  getAgentDefinition,
  HARNESS_INSPECTION_TOOL_GRANTS,
  MULTI_OWNER_GATES,
  normalizeGateId,
  routeGateToAgents,
} from "../src/index.js";
import { definition } from "./fakes.js";

describe("agent definitions", () => {
  it("covers exactly the four contract agents", () => {
    expect(Object.keys(AGENT_DEFINITIONS).sort()).toEqual([...AGENT_NAMES].sort());
    expect(allAgentDefinitions().map((d) => d.id)).toEqual([...AGENT_NAMES]);
  });

  it("uses the frozen lock scopes from the agent protocol", () => {
    expect(AGENT_DEFINITIONS["ee-agent"].lockScopes).toEqual([
      "/electrical",
      "/layout",
      "/keyboard",
    ]);
    expect(AGENT_DEFINITIONS["fw-agent"].lockScopes).toEqual(["/firmware", "/simulation"]);
    expect(AGENT_DEFINITIONS["mech-agent"].lockScopes).toEqual(["/mechanical"]);
    expect(AGENT_DEFINITIONS["ops-agent"].lockScopes).toEqual([
      "/sourcing",
      "/fabrication",
      "/orders",
    ]);
  });

  it("keeps produces within lock scopes and never /meta", () => {
    for (const agent of allAgentDefinitions()) {
      expect(agent.produces?.length).toBeGreaterThan(0);
      for (const scope of agent.produces ?? []) {
        expect(
          agent.lockScopes.some((lock) => scope === lock || scope.startsWith(`${lock}/`)),
        ).toBe(true);
        expect(scope.startsWith("/meta")).toBe(false);
      }
    }
  });

  it("grants every agent the shared multimodal inspection tools", () => {
    for (const agent of allAgentDefinitions()) {
      for (const grant of HARNESS_INSPECTION_TOOL_GRANTS) {
        expect(agent.permittedTools).toContain(grant);
      }
    }
  });

  it("assigns the documented gates to their owners", () => {
    expect(AGENT_DEFINITIONS["ee-agent"].gates).toContain("erc.no_unconnected");
    expect(AGENT_DEFINITIONS["fw-agent"].gates).toContain("fw.qmk_compile");
    expect(AGENT_DEFINITIONS["mech-agent"].gates).toContain("mech.jig_no_collision");
    expect(AGENT_DEFINITIONS["ops-agent"].gates).toContain("bom.all_in_stock");
  });

  it("embeds the shared rules and specialist focus in each prompt", () => {
    for (const agent of allAgentDefinitions()) {
      expect(agent.systemPrompt).toContain("You are one specialist inside the atomc swarm harness");
      expect(agent.systemPrompt.length).toBeGreaterThan(300);
    }
    expect(AGENT_DEFINITIONS["ee-agent"].systemPrompt).toContain(
      "electrical engineering specialist",
    );
    expect(AGENT_DEFINITIONS["fw-agent"].systemPrompt).toContain("firmware specialist");
    expect(AGENT_DEFINITIONS["mech-agent"].systemPrompt).toContain("mechanical specialist");
    expect(AGENT_DEFINITIONS["ops-agent"].systemPrompt).toContain("supply-chain");
  });

  it("defaults model routing from PLAN D10/D13", () => {
    expect(DEFAULT_AGENT_MODEL).toEqual({
      provider: "openrouter",
      model: "deepseek/deepseek-v4.1-flash",
      thinking: "medium",
    });
    for (const agent of allAgentDefinitions()) expect(agent.model).toBe(DEFAULT_AGENT_MODEL);
  });

  it("looks up a single definition and all definitions", () => {
    expect(getAgentDefinition("mech-agent").id).toBe("mech-agent");
    expect(allAgentDefinitions()).toHaveLength(4);
  });
});

describe("gate routing", () => {
  it("normalizes an optional gate: prefix", () => {
    expect(normalizeGateId("gate:erc.no_unconnected")).toBe("erc.no_unconnected");
    expect(normalizeGateId("erc.no_unconnected")).toBe("erc.no_unconnected");
  });

  it("routes single-owner gates to their agent", () => {
    expect(routeGateToAgents("gate:fw.qmk_compile")).toEqual(["fw-agent"]);
    expect(routeGateToAgents("mech.plate_switch_cutouts_14mm")).toEqual(["mech-agent"]);
    expect(routeGateToAgents("sourcing.unknown")).toEqual([]);
  });

  it("routes the shared cost gate to both owners", () => {
    expect(routeGateToAgents("gate:bom.cost_under_budget")).toEqual(["ops-agent", "ee-agent"]);
    expect(MULTI_OWNER_GATES["bom.cost_under_budget"]).toEqual(["ops-agent", "ee-agent"]);
  });
});

describe("AgentRegistry", () => {
  it("is seeded with the four contract agents", () => {
    const registry = defaultAgentRegistry();
    expect(registry.list().map((d) => d.id)).toEqual([...AGENT_NAMES]);
    expect(registry.has("ee-agent")).toBe(true);
    expect(registry.has("nope-agent" as never)).toBe(false);
    expect(registry.get("fw-agent")?.id).toBe("fw-agent");
    expect(registry.get("zzz" as never)).toBeUndefined();
  });

  it("requires a registered agent", () => {
    const registry = new AgentRegistry([]);
    expect(() => registry.require("ee-agent")).toThrow(AgentDefinitionError);
    registry.register(definition());
    expect(registry.require("ee-agent").id).toBe("ee-agent");
  });

  it("replaces an existing definition on re-register", () => {
    const registry = defaultAgentRegistry();
    registry.register(definition({ model: { provider: "openrouter", model: "other" } }));
    expect(registry.require("ee-agent").model.model).toBe("other");
    expect(registry.list()).toHaveLength(4);
  });

  it("resolves agents for a gate", () => {
    const registry = defaultAgentRegistry();
    expect(registry.agentsForGate("gate:erc.assertions").map((d) => d.id)).toEqual(["ee-agent"]);
    expect(registry.agentsForGate("gate:bom.cost_under_budget").map((d) => d.id)).toEqual([
      "ops-agent",
      "ee-agent",
    ]);
    expect(registry.agentsForGate("nope")).toEqual([]);
  });

  it("rejects malformed definitions", () => {
    const registry = new AgentRegistry([]);
    expect(() => registry.register(definition({ id: "nope" as never }))).toThrow(
      /unknown agent id/,
    );
    expect(() => registry.register(definition({ systemPrompt: "  " }))).toThrow(/empty system/);
    expect(() => registry.register(definition({ lockScopes: [] }))).toThrow(/no lock scopes/);
    expect(() => registry.register(definition({ lockScopes: ["electrical"] }))).toThrow(
      /not a JSON pointer/,
    );
    expect(() => registry.register(definition({ lockScopes: ["/meta"] }))).toThrow(/may not touch/);
    expect(() =>
      registry.register(definition({ lockScopes: ["/electrical"], produces: ["/firmware"] })),
    ).toThrow(/outside its lock scopes/);
    expect(() => registry.register(definition({ model: { provider: "", model: "x" } }))).toThrow(
      /incomplete model/,
    );
  });
});
