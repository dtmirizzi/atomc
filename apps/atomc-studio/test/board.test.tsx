import type { GateResult } from "@atomc/daemon-client";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import {
  countBySeverity,
  countByStatus,
  DEFAULT_GATE_FILTER,
  domainOf,
  elementIdFor,
  filterGates,
  formatDuration,
  formatTimestamp,
  gateTitle,
  groupGates,
  passRate,
} from "../src/board/derive.js";
import { GateBoard } from "../src/board/GateBoard.js";
import { createDemoApi, createDemoSnapshot } from "../src/model.js";
import { StudioApp } from "../src/studio-app.js";

afterEach(() => {
  cleanup();
});

function makeGate(overrides: Partial<GateResult> = {}): GateResult {
  return {
    id: "gate:erc.no_unconnected",
    status: "PASS",
    severity: "blocking",
    plugin: "atopile@0.15.9",
    owner_agent: "ee-agent",
    evaluated_at: "2026-11-04T23:00:00Z",
    ir_rev: 128,
    duration_ms: 340,
    summary: "No unconnected pins",
    evidence: [],
    suggestions: [],
    refs: [],
    ...overrides,
  };
}

describe("board derivation", () => {
  it("maps owners to their domain and treats null as unowned", () => {
    expect(domainOf("ee-agent")).toBe("ee");
    expect(domainOf("fw-agent")).toBe("fw");
    expect(domainOf("mech-agent")).toBe("mech");
    expect(domainOf("ops-agent")).toBe("ops");
    expect(domainOf(null)).toBe("unowned");
  });

  it("groups gates by domain and computes pass rates in a stable order", () => {
    const gates = [
      makeGate({ id: "gate:a", owner_agent: "fw-agent", status: "FAIL" }),
      makeGate({ id: "gate:b", owner_agent: "ee-agent", status: "PASS" }),
      makeGate({ id: "gate:c", owner_agent: null, status: "SKIP", severity: "advisory" }),
      makeGate({ id: "gate:d", owner_agent: "ee-agent", status: "FAIL" }),
    ];
    const groups = groupGates(gates);
    expect(groups.map((group) => group.domain)).toEqual(["ee", "fw", "unowned"]);
    const ee = groups[0];
    if (!ee) throw new Error("ee group expected");
    expect(ee.total).toBe(2);
    expect(ee.passCount).toBe(1);
    expect(ee.passRate).toBe(0.5);
    expect(ee.unowned).toBe(false);
    const unowned = groups[2];
    if (!unowned) throw new Error("unowned group expected");
    expect(unowned.unowned).toBe(true);
    expect(unowned.blockingFailCount).toBe(0);
  });

  it("counts blocking failures separately from advisory ones", () => {
    const groups = groupGates([
      makeGate({ id: "gate:a", status: "FAIL", severity: "blocking" }),
      makeGate({ id: "gate:b", status: "FAIL", severity: "advisory" }),
      makeGate({ id: "gate:c", status: "ERROR", severity: "blocking" }),
    ]);
    expect(groups[0]?.blockingFailCount).toBe(2);
  });

  it("filters by severity and status independently", () => {
    const gates = [
      makeGate({ id: "gate:a", severity: "blocking", status: "FAIL" }),
      makeGate({ id: "gate:b", severity: "advisory", status: "FAIL" }),
      makeGate({ id: "gate:c", severity: "advisory", status: "SKIP" }),
    ];
    expect(filterGates(gates, DEFAULT_GATE_FILTER)).toHaveLength(3);
    expect(filterGates(gates, { severity: "advisory", status: "all" })).toHaveLength(2);
    expect(filterGates(gates, { severity: "all", status: "FAIL" })).toHaveLength(2);
    expect(filterGates(gates, { severity: "advisory", status: "SKIP" })).toHaveLength(1);
    expect(filterGates(gates, { severity: "blocking", status: "SKIP" })).toHaveLength(0);
  });

  it("counts statuses and severities and computes pass rate", () => {
    const gates = [
      makeGate({ id: "gate:a", status: "PASS" }),
      makeGate({ id: "gate:b", status: "FAIL" }),
      makeGate({ id: "gate:c", status: "SKIP" }),
      makeGate({ id: "gate:d", status: "ERROR" }),
    ];
    expect(countByStatus(gates)).toEqual({ PASS: 1, FAIL: 1, SKIP: 1, ERROR: 1 });
    expect(countBySeverity(gates)).toEqual({ all: 4, blocking: 4, advisory: 0 });
    expect(passRate(gates)).toBe(0.25);
    expect(passRate([])).toBe(0);
  });

  it("formats durations, timestamps, titles and element ids", () => {
    expect(formatDuration(340)).toBe("340ms");
    expect(formatDuration(1840)).toBe("1.8s");
    expect(formatTimestamp("2026-11-04T23:00:00.123Z")).toBe("2026-11-04 23:00:00Z");
    expect(formatTimestamp("not-a-date")).toBe("not-a-date");
    expect(gateTitle(makeGate({ id: "gate:erc.no_unconnected" }))).toBe("Unconnected pins");
    expect(gateTitle(makeGate({ id: "gate:custom.check" }))).toBe("custom check");
    expect(elementIdFor("gate:fw.matrix_scan")).toBe("gate-fw-matrix_scan");
  });
});

describe("GateBoard", () => {
  it("groups every gate under its owning domain and flags unowned gates", () => {
    const gates = [
      makeGate({ id: "gate:erc.no_unconnected", owner_agent: "ee-agent", status: "PASS" }),
      makeGate({ id: "gate:fw.qmk_compile", owner_agent: "fw-agent", status: "FAIL" }),
      makeGate({ id: "gate:orphan", owner_agent: null, status: "ERROR", severity: "advisory" }),
    ];
    render(<GateBoard gates={gates} dataMode="daemon" />);
    expect(screen.getByRole("heading", { name: /Electrical/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Firmware/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Unowned/ })).toBeInTheDocument();
    expect(screen.getByText(/coordinator must review/i)).toBeInTheDocument();
    expect(screen.queryByText(/Preview snapshot/)).not.toBeInTheDocument();
  });

  it("renders a pass-rate bar per group and a live count for the filters", () => {
    const gates = [
      makeGate({ id: "gate:a", owner_agent: "ee-agent", status: "PASS" }),
      makeGate({ id: "gate:b", owner_agent: "ee-agent", status: "FAIL" }),
    ];
    render(<GateBoard gates={gates} dataMode="daemon" />);
    const bar = screen.getByRole("progressbar", { name: "Electrical pass rate" });
    expect(bar).toHaveAttribute("aria-valuenow", "50");
    expect(screen.getByRole("status")).toHaveTextContent("Showing 2 of 2 gates across 1 domains.");
  });

  it("filters rows through severity and status chips with announced counts", async () => {
    const user = userEvent.setup();
    const gates = [
      makeGate({ id: "gate:erc", owner_agent: "ee-agent", status: "PASS", severity: "blocking" }),
      makeGate({
        id: "gate:mech.plate_switch_cutouts_14mm",
        owner_agent: "mech-agent",
        status: "SKIP",
        severity: "advisory",
      }),
    ];
    render(<GateBoard gates={gates} dataMode="daemon" />);
    const severity = screen.getByRole("group", { name: "Severity" });
    await user.click(within(severity).getByRole("button", { name: /Advisory/ }));
    expect(screen.queryByText("Unconnected pins")).not.toBeInTheDocument();
    expect(screen.getByText("Switch plate cutouts")).toBeInTheDocument();
    const status = screen.getByRole("group", { name: "Result" });
    await user.click(within(status).getByRole("button", { name: /Error/ }));
    expect(screen.getByRole("status")).toHaveTextContent("Showing 0 of 2 gates");
  });

  it("toggles filters with the keyboard", async () => {
    const user = userEvent.setup();
    render(<GateBoard gates={[makeGate({ status: "FAIL" })]} dataMode="daemon" />);
    const chip = within(screen.getByRole("group", { name: "Result" })).getByRole("button", {
      name: /Failed/,
    });
    chip.focus();
    await user.keyboard("{Enter}");
    expect(chip).toHaveAttribute("aria-pressed", "true");
  });

  it("expands a drill-in row with real GateResult detail fields", async () => {
    const user = userEvent.setup();
    const gates = [
      makeGate({
        id: "gate:fw.matrix_scan",
        owner_agent: "fw-agent",
        status: "FAIL",
        duration_ms: 4210,
        ir_rev: 42,
        evaluated_at: "2026-11-04T23:00:00Z",
        evidence: [{ kind: "artifact", ref: "art:scan" }],
        suggestions: [
          {
            message: "Add C13 to the matrix",
            patch: { path: "/keyboard/matrix/col_pins", ops: [] },
          },
        ],
        refs: ["key:K0_12"],
      }),
    ];
    render(<GateBoard gates={gates} dataMode="daemon" />);
    const toggle = screen.getByRole("button", { name: /Details/ });
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("art:scan")).toBeInTheDocument();
    expect(screen.getByText("Add C13 to the matrix")).toBeInTheDocument();
    expect(screen.getByText("/keyboard/matrix/col_pins · 0 JSON Patch op(s)")).toBeInTheDocument();
    expect(screen.getByText("key:K0_12")).toBeInTheDocument();
    expect(screen.getAllByText("4.2s").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("r42")).toBeInTheDocument();
    expect(screen.getByText("2026-11-04 23:00:00Z")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Hide/ }));
    expect(screen.queryByText("key:K0_12")).not.toBeInTheDocument();
  });

  it("shows an honest empty state when no gates exist and labels demo data", () => {
    const { unmount } = render(<GateBoard gates={[]} dataMode="daemon" />);
    expect(screen.getByText(/No gate results exist for this project revision/)).toBeInTheDocument();
    unmount();
    render(<GateBoard gates={[makeGate()]} dataMode="demo" />);
    expect(screen.getByText(/simulated fixture data/)).toBeInTheDocument();
  });

  it("renders the demo snapshot gate data from the Studio shell", async () => {
    const api = createDemoApi();
    render(<StudioApp api={api} demo />);
    await screen.findByRole("heading", { name: /good morning, engineer/i });
    fireEvent.click(screen.getByRole("button", { name: "Gate board" }));
    expect(screen.getByRole("heading", { name: "Gate board" })).toBeInTheDocument();
    expect(screen.getByText("Matrix scan pin map")).toBeInTheDocument();
    expect(createDemoSnapshot().gates).toHaveLength(6);
    expect(createDemoSnapshot().gates[2]?.evidence.length).toBeGreaterThan(0);
  });
});
