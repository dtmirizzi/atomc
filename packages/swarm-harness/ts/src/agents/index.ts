/** Specialist agent definitions, prompts and the registry. */
export {
  AGENT_DEFINITIONS,
  allAgentDefinitions,
  DEFAULT_AGENT_MODEL,
  getAgentDefinition,
  HARNESS_INSPECTION_TOOL_GRANTS,
  MULTI_OWNER_GATES,
  normalizeGateId,
  routeGateToAgents,
} from "./definitions.js";
export {
  EE_AGENT_PROMPT,
  FW_AGENT_PROMPT,
  MECH_AGENT_PROMPT,
  OPS_AGENT_PROMPT,
  SHARED_AGENT_RULES,
} from "./prompts.js";
export { AgentDefinitionError, AgentRegistry, defaultAgentRegistry } from "./registry.js";
