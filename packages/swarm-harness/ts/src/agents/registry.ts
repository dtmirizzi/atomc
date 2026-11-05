/**
 * Mutable registry of {@link AgentDefinition}s.
 *
 * The four contract agents are seeded by default; a project may override model
 * routing, budgets, tool grants or prompts per agent without forking the
 * package. The registry validates definitions so a typo cannot silently widen an
 * agent's write scope or point it at an unknown lock subtree.
 */
import type { AgentDefinition, AgentName } from "../types.js";
import { AGENT_NAMES } from "../types.js";
import { allAgentDefinitions, routeGateToAgents } from "./definitions.js";

/** Raised when a definition violates the agent protocol contract. */
export class AgentDefinitionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AgentDefinitionError";
  }
}

const AGENT_NAME_SET: ReadonlySet<string> = new Set(AGENT_NAMES);

function assertValid(def: AgentDefinition): void {
  if (!AGENT_NAME_SET.has(def.id)) {
    throw new AgentDefinitionError(
      `unknown agent id "${def.id}" (expected one of ${AGENT_NAMES.join(", ")})`,
    );
  }
  if (def.systemPrompt.trim().length === 0) {
    throw new AgentDefinitionError(`agent "${def.id}" has an empty system prompt`);
  }
  if (def.lockScopes.length === 0) {
    throw new AgentDefinitionError(`agent "${def.id}" declares no lock scopes`);
  }
  for (const scope of [...def.lockScopes, ...(def.produces ?? [])]) {
    if (!scope.startsWith("/")) {
      throw new AgentDefinitionError(`agent "${def.id}" scope "${scope}" is not a JSON pointer`);
    }
    if (scope === "/meta" || scope.startsWith("/meta/")) {
      throw new AgentDefinitionError(`agent "${def.id}" may not touch the /meta node`);
    }
  }
  for (const scope of def.produces ?? []) {
    if (!def.lockScopes.some((lock) => scope === lock || scope.startsWith(`${lock}/`))) {
      throw new AgentDefinitionError(
        `agent "${def.id}" produces scope "${scope}" is outside its lock scopes`,
      );
    }
  }
  if (def.model.provider.trim().length === 0 || def.model.model.trim().length === 0) {
    throw new AgentDefinitionError(`agent "${def.id}" has an incomplete model config`);
  }
}

/** Registry keyed by agent id; seeded with the four contract agents. */
export class AgentRegistry {
  readonly #definitions = new Map<AgentName, AgentDefinition>();

  constructor(definitions: readonly AgentDefinition[] = allAgentDefinitions()) {
    for (const definition of definitions) this.register(definition);
  }

  /** Validate and insert (or replace) a definition. */
  register(definition: AgentDefinition): void {
    assertValid(definition);
    this.#definitions.set(definition.id, definition);
  }

  /** Look up a definition, or `undefined` when not registered. */
  get(id: AgentName): AgentDefinition | undefined {
    return this.#definitions.get(id);
  }

  /** Look up a definition or throw {@link AgentDefinitionError}. */
  require(id: AgentName): AgentDefinition {
    const definition = this.#definitions.get(id);
    if (definition === undefined) {
      throw new AgentDefinitionError(`agent "${id}" is not registered`);
    }
    return definition;
  }

  has(id: AgentName): boolean {
    return this.#definitions.has(id);
  }

  /** Registered definitions in `AGENT_NAMES` order. */
  list(): AgentDefinition[] {
    return AGENT_NAMES.filter((name) => this.#definitions.has(name)).map(
      (name) => this.#definitions.get(name) as AgentDefinition,
    );
  }

  /**
   * Agent definitions responsible for a gate id. Uses each definition's `gates`
   * list plus the shared-ownership overrides from the contract.
   */
  agentsForGate(gateId: string): AgentDefinition[] {
    return routeGateToAgents(gateId)
      .filter((name) => this.#definitions.has(name))
      .map((name) => this.#definitions.get(name) as AgentDefinition);
  }
}

/** A registry seeded with the frozen contract agents. */
export function defaultAgentRegistry(): AgentRegistry {
  return new AgentRegistry();
}
