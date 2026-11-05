import { describe, expect, it } from "vitest";
import {
  isTerminal,
  StateTransitionError,
  SwarmStateMachine,
  transition,
} from "../src/state-machine.js";

describe("SwarmStateMachine", () => {
  it("routes aborts through RELEASE before entering the ABORTED terminal state", () => {
    for (const state of ["PLAN", "CLAIM_LOCK", "ACT", "VERIFY"] as const) {
      const machine = new SwarmStateMachine(state);
      expect(machine.send("ABORT")).toBe("RELEASE");
      expect(machine.send("RELEASE_ABORTED")).toBe("ABORTED");
      expect(isTerminal(machine.state)).toBe(true);
    }
  });

  it("walks the frozen loop and records history", () => {
    const machine = new SwarmStateMachine();
    machine.send("START");
    machine.send("PLANNED");
    machine.send("LOCKED");
    machine.send("VERIFY_REQUESTED");
    machine.send("VERIFIED");
    machine.send("RELEASE_PASS");

    expect(machine.state).toBe("DONE");
    expect(machine.history.map((entry) => entry.to)).toEqual([
      "PLAN",
      "CLAIM_LOCK",
      "ACT",
      "VERIFY",
      "RELEASE",
      "DONE",
    ]);
  });

  it("routes retries back to ACT and escalation through RELEASE", () => {
    expect(transition("VERIFY", "RETRY_TURN")).toBe("ACT");
    expect(transition("ACT", "ACTION_FAILED")).toBe("RELEASE");
    expect(transition("RELEASE", "RELEASE_ESCALATE")).toBe("ESCALATE");
    expect(isTerminal("ESCALATE")).toBe(true);
    expect(isTerminal("ACT")).toBe(false);
  });

  it("throws on an invalid transition and trySend ignores it", () => {
    expect(() => transition("IDLE", "VERIFIED")).toThrow(StateTransitionError);
    const machine = new SwarmStateMachine("DONE");
    expect(machine.trySend("ACTION_FAILED")).toBe("DONE");
  });

  it("notifies subscribers and can unsubscribe", () => {
    const machine = new SwarmStateMachine();
    const seen: string[] = [];
    const off = machine.onTransition((_from, to) => seen.push(to));
    machine.send("START");
    off();
    machine.send("PLANNED");
    expect(seen).toEqual(["PLAN"]);
  });
});
