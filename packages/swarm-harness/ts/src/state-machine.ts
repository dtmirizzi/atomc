/**
 * Explicit transactional state machine for a swarm agent run.
 *
 * Contract loop (`docs/architecture/contracts/agent-protocol.md`):
 * `IDLE → PLAN → CLAIM_LOCK → ACT → VERIFY → RELEASE → (PASS/RETRY/ESCALATE)`.
 *
 * `RELEASE` is always entered before a terminal state so lock cleanup runs on
 * every path, including abort and error. The runner performs the actual daemon
 * calls; this module only validates and records transitions.
 */
import type { AgentState } from "./types.js";

/** Events accepted by the reducer. */
export const AGENT_EVENTS = [
  "START",
  "PLANNED",
  "PLAN_FAILED",
  "LOCKED",
  "LOCK_FAILED",
  "TURN",
  "VERIFY_REQUESTED",
  "RETRY_TURN",
  "GIVE_UP",
  "ACTION_FAILED",
  "VERIFIED",
  "RELEASE_PASS",
  "RELEASE_RETRY",
  "RELEASE_ESCALATE",
  "ABORT",
] as const;
export type AgentEvent = (typeof AGENT_EVENTS)[number];

/** Raised when a transition is not part of the frozen loop. */
export class StateTransitionError extends Error {
  readonly from: AgentState;
  readonly event: AgentEvent;

  constructor(from: AgentState, event: AgentEvent) {
    super(`Invalid swarm transition: ${from} --${event}-->`);
    this.name = "StateTransitionError";
    this.from = from;
    this.event = event;
  }
}

/** Transition table for the frozen loop. Terminals have no outgoing edges. */
export const TRANSITIONS: Readonly<Record<AgentState, Partial<Record<AgentEvent, AgentState>>>> = {
  IDLE: { START: "PLAN", ABORT: "ABORTED" },
  PLAN: { PLANNED: "CLAIM_LOCK", PLAN_FAILED: "RELEASE", ABORT: "ABORTED" },
  CLAIM_LOCK: {
    LOCKED: "ACT",
    LOCK_FAILED: "RELEASE",
    ACTION_FAILED: "RELEASE",
    ABORT: "ABORTED",
  },
  ACT: {
    TURN: "ACT",
    VERIFY_REQUESTED: "VERIFY",
    GIVE_UP: "RELEASE",
    ACTION_FAILED: "RELEASE",
    ABORT: "ABORTED",
  },
  VERIFY: {
    VERIFIED: "RELEASE",
    RETRY_TURN: "ACT",
    ACTION_FAILED: "RELEASE",
    ABORT: "ABORTED",
  },
  RELEASE: {
    RELEASE_PASS: "DONE",
    RELEASE_RETRY: "RETRY",
    RELEASE_ESCALATE: "ESCALATE",
  },
  DONE: {},
  RETRY: {},
  ESCALATE: {},
  ABORTED: {},
};

/** Terminal states. */
export const TERMINAL_STATES: ReadonlySet<AgentState> = new Set([
  "DONE",
  "RETRY",
  "ESCALATE",
  "ABORTED",
]);

/** True when no further transitions are possible. */
export function isTerminal(state: AgentState): boolean {
  return TERMINAL_STATES.has(state);
}

/** Pure reducer; throws {@link StateTransitionError} on an invalid edge. */
export function transition(state: AgentState, event: AgentEvent): AgentState {
  const next = TRANSITIONS[state][event];
  if (next === undefined) throw new StateTransitionError(state, event);
  return next;
}

/** State machine that records its own history and emits transition callbacks. */
export class SwarmStateMachine {
  #state: AgentState = "IDLE";
  readonly #history: Array<{ from: AgentState; event: AgentEvent; to: AgentState }> = [];
  readonly #listeners: Array<(from: AgentState, to: AgentState, event: AgentEvent) => void> = [];

  constructor(initial: AgentState = "IDLE") {
    this.#state = initial;
  }

  get state(): AgentState {
    return this.#state;
  }

  get history(): ReadonlyArray<{ from: AgentState; event: AgentEvent; to: AgentState }> {
    return this.#history;
  }

  /** Subscribe to transitions; returns an unsubscribe function. */
  onTransition(
    listener: (from: AgentState, to: AgentState, event: AgentEvent) => void,
  ): () => void {
    this.#listeners.push(listener);
    return () => {
      const index = this.#listeners.indexOf(listener);
      if (index >= 0) this.#listeners.splice(index, 1);
    };
  }

  /** Apply an event or throw {@link StateTransitionError}. */
  send(event: AgentEvent): AgentState {
    const from = this.#state;
    const to = transition(from, event);
    this.#state = to;
    this.#history.push({ from, event, to });
    for (const listener of this.#listeners) listener(from, to, event);
    return to;
  }

  /** Apply an event, ignoring edges that are invalid from the current state. */
  trySend(event: AgentEvent): AgentState {
    try {
      return this.send(event);
    } catch (error) {
      if (error instanceof StateTransitionError) return this.#state;
      throw error;
    }
  }
}
