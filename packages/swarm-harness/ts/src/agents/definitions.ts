/**
 * The four specialist {@link AgentDefinition}s registered by the swarm harness.
 *
 * Every value here is derived from a frozen contract:
 * - agent ids, lock scopes and the loop: `docs/architecture/contracts/agent-protocol.md`;
 * - gate ids and their owners: `PLAN.md` §1.2 and `gate-result.md`;
 * - plugin `produces` scopes: `docs/architecture/contracts/plugin-manifest.md`;
 * - model routing default: `PLAN.md` D10/D13.
 *
 * `permittedTools` is a *second* allow-list on top of the daemon's per-agent
 * tool filtering (`tools[].agents` in the plugin manifest). The harness runner
 * rejects any tool call that is not granted here even if the daemon advertises
 * it, so the entries below stay deliberately scoped to each specialist's plugin
 * namespace plus the shared multimodal inspection tools.
 */
import { inspectionToolGrants } from "../multimodal.js";
import type { AgentDefinition, AgentName, ModelConfig } from "../types.js";
import { AGENT_NAMES } from "../types.js";
import {
  EE_AGENT_PROMPT,
  FW_AGENT_PROMPT,
  MECH_AGENT_PROMPT,
  OPS_AGENT_PROMPT,
  SHARED_AGENT_RULES,
} from "./prompts.js";

/** Default routing for every specialist (override per project in `atomc.config.ts`). */
export const DEFAULT_AGENT_MODEL: ModelConfig = {
  provider: "openrouter",
  model: "deepseek/deepseek-v4.1-flash",
  thinking: "medium",
};

/**
 * Shared, read-only inspection tools supplied by the harness (see
 * {@link ./multimodal.ts}). They are granted to every specialist; each call
 * returns an image attachment the model can reason over.
 */
export const HARNESS_INSPECTION_TOOL_GRANTS: readonly string[] = Object.freeze(
  inspectionToolGrants(),
);

function prompt(body: string): string {
  return `${body}\n\n${SHARED_AGENT_RULES}`;
}

/**
 * Frozen specialist definitions. Exported as a `const` record so TypeScript
 * guarantees all four contract agents are present and no others.
 */
export const AGENT_DEFINITIONS: Readonly<Record<AgentName, AgentDefinition>> = {
  "ee-agent": {
    id: "ee-agent",
    systemPrompt: prompt(EE_AGENT_PROMPT),
    permittedTools: ["atopile:*", ...HARNESS_INSPECTION_TOOL_GRANTS],
    lockScopes: ["/electrical", "/layout", "/keyboard"],
    produces: ["/electrical", "/layout", "/keyboard"],
    gates: [
      "erc.no_unconnected",
      "erc.assertions",
      "layout.testpads.min_count",
      "layout.testpads.nets_covered",
      "kb.layout_matches_keymap",
      "kb.diode_per_switch",
      "kb.usb_cc_pulldowns",
    ],
    model: DEFAULT_AGENT_MODEL,
    budget: { maxTurns: 12, maxCostMinor: 250, maxTokens: 200_000 },
  },
  "fw-agent": {
    id: "fw-agent",
    systemPrompt: prompt(FW_AGENT_PROMPT),
    permittedTools: ["qmk:*", "renode:*", ...HARNESS_INSPECTION_TOOL_GRANTS],
    lockScopes: ["/firmware", "/simulation"],
    produces: ["/firmware", "/simulation"],
    gates: ["fw.qmk_compile", "fw.matrix_pins_match_ir", "fw.renode_boot", "fw.matrix_scan"],
    model: DEFAULT_AGENT_MODEL,
    budget: { maxTurns: 12, maxCostMinor: 250, maxTokens: 200_000 },
  },
  "mech-agent": {
    id: "mech-agent",
    systemPrompt: prompt(MECH_AGENT_PROMPT),
    permittedTools: ["cad-jig:*", ...HARNESS_INSPECTION_TOOL_GRANTS],
    lockScopes: ["/mechanical"],
    produces: ["/mechanical"],
    gates: [
      "mech.plate_switch_cutouts_14mm",
      "mech.case_usb_cutout_aligned",
      "mech.pogo_spacing_ge_2p54",
      "mech.jig_no_collision",
      "mech.enclosure_clearance",
    ],
    model: DEFAULT_AGENT_MODEL,
    budget: { maxTurns: 10, maxCostMinor: 200, maxTokens: 160_000 },
  },
  "ops-agent": {
    id: "ops-agent",
    systemPrompt: prompt(OPS_AGENT_PROMPT),
    permittedTools: ["sourcing:*", "orders:*", ...HARNESS_INSPECTION_TOOL_GRANTS],
    lockScopes: ["/sourcing", "/fabrication", "/orders"],
    produces: ["/sourcing", "/fabrication", "/orders"],
    gates: [
      "bom.all_in_stock",
      "bom.cost_under_budget",
      "bom.lead_time_under_days",
      "fab.quote_under_budget",
    ],
    model: DEFAULT_AGENT_MODEL,
    budget: { maxTurns: 10, maxCostMinor: 200, maxTokens: 160_000 },
  },
};

/** Return the definition for a contract agent id. */
export function getAgentDefinition(name: AgentName): AgentDefinition {
  return AGENT_DEFINITIONS[name];
}

/** All four definitions in a stable order (`AGENT_NAMES`). */
export function allAgentDefinitions(): AgentDefinition[] {
  return AGENT_NAMES.map((name) => AGENT_DEFINITIONS[name]);
}

/** Normalize a gate id that may or may not carry the `gate:` prefix. */
export function normalizeGateId(gateId: string): string {
  return gateId.startsWith("gate:") ? gateId.slice("gate:".length) : gateId;
}

/**
 * Gates that wake more than one agent. `bom.cost_under_budget` is shared by the
 * sourcing and electrical owners (`PLAN.md` §1.2). Keys are normalized gate ids.
 */
export const MULTI_OWNER_GATES: Readonly<Record<string, readonly AgentName[]>> = {
  "bom.cost_under_budget": ["ops-agent", "ee-agent"],
};

/**
 * Route a gate id to the agent(s) that own it. Falls back to the `gates` lists
 * declared by the definitions; returns `[]` for an unknown/unowned gate (the
 * coordinator decides what to do, e.g. escalate to a human).
 */
export function routeGateToAgents(gateId: string): AgentName[] {
  const normalized = normalizeGateId(gateId);
  const override = MULTI_OWNER_GATES[normalized];
  if (override !== undefined) return [...override];
  return AGENT_NAMES.filter((name) => AGENT_DEFINITIONS[name].gates?.includes(normalized));
}
