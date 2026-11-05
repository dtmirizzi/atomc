import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  type BoardSnapshot,
  createDemoApi,
  createDemoSnapshot,
  type StudioApi,
} from "../src/model.js";
import { StudioApp } from "../src/studio-app.js";

afterEach(() => {
  cleanup();
});

function fixtureApi(snapshot = createDemoSnapshot()): StudioApi {
  return {
    load: vi.fn(async () => structuredClone(snapshot)),
    runBuild: vi.fn(async () => structuredClone(snapshot)),
  };
}

async function openStudio(api = fixtureApi(), demo = true) {
  const view = render(<StudioApp api={api} demo={demo} />);
  await screen.findByRole("heading", { name: /good morning, engineer/i });
  return { ...view, api };
}

describe("Atomc Studio workspace", () => {
  it("renders the demo as a clearly marked, accessible offline preview", async () => {
    const { container } = await openStudio();
    expect(screen.getByText("Preview workspace")).toBeInTheDocument();
    expect(screen.getByText(/no build or model run has occurred/i)).toBeInTheDocument();
    expect(screen.getByText("Daemon offline")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run build/i })).toBeDisabled();
    expect(container.querySelector("main")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Project views" })).toBeInTheDocument();
  });

  it("shows project status, counts, gate findings and pipeline progress", async () => {
    await openStudio();
    expect(screen.getAllByText("atomc-keeb").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/1 blocking issue needs attention/i)).toBeInTheDocument();
    expect(screen.getByText("qmk", { exact: true })).toBeInTheDocument();
    expect(
      screen.getAllByText(/Column pin C13 is absent from the IR/).length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("heading", { name: /gate results/i })).toBeInTheDocument();
  });

  it("filters gate results and clears to a helpful empty state", async () => {
    await openStudio();
    const gates = screen.getByRole("table", { name: "Verification gates" });
    fireEvent.click(screen.getAllByRole("tab", { name: /failed/i }).at(0) as HTMLElement);
    expect(within(gates).getByText("Matrix scan pin map")).toBeInTheDocument();
    expect(within(gates).queryByText("Unconnected pins")).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("tab", { name: /skipped/i }).at(0) as HTMLElement);
    expect(within(gates).getByText("Switch plate cutouts")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("tab", { name: /passed/i }).at(0) as HTMLElement);
    expect(within(gates).queryByText("Matrix scan pin map")).not.toBeInTheDocument();
  });

  it("opens accessible gate details and closes them with the close control", async () => {
    await openStudio();
    const failRow = screen
      .getAllByRole("row")
      .find((row) => row.textContent?.includes("Matrix scan pin map"));
    if (!failRow) throw new Error("matrix-scan gate row should be visible");
    fireEvent.click(within(failRow).getByRole("button"));
    const dialog = screen.getByRole("dialog", { name: "Matrix scan pin map" });
    expect(within(dialog).getByText(/Column pin C13/)).toBeInTheDocument();
    expect(within(dialog).getByText("Firmware")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /wake specialist/i })).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("button", { name: /close gate details/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("switches to pipeline, agent and artifact views from the primary navigation", async () => {
    await openStudio();
    fireEvent.click(screen.getAllByRole("button", { name: "Build graph" }).at(0) as HTMLElement);
    expect(screen.getByRole("heading", { name: "Build pipeline" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Agent team" }));
    expect(screen.getByRole("heading", { name: "Specialist agents" })).toBeInTheDocument();
    expect(screen.getByText("Transactional")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Artifacts" }));
    expect(screen.getByRole("heading", { name: "Artifacts" })).toBeInTheDocument();
    expect(screen.getByText(/no files have been generated/i)).toBeInTheDocument();
  });

  it("does not issue a build in preview mode and explains why", async () => {
    const api = fixtureApi();
    await openStudio(api);
    fireEvent.click(screen.getByRole("button", { name: "Daemon connection details" }));
    expect(document.querySelector(".toast")).toHaveTextContent(/preview mode uses fixture data/i);
    expect(screen.getByRole("button", { name: /run build/i })).toBeDisabled();
    expect(api.runBuild).not.toHaveBeenCalled();
  });

  it("sends a build request only when the adapter is explicitly live", async () => {
    const snapshot = createDemoSnapshot();
    snapshot.connection = "connected";
    const api = fixtureApi(snapshot);
    await openStudio(api, false);
    fireEvent.click(screen.getByRole("button", { name: /run build/i }));
    await waitFor(() => expect(api.runBuild).toHaveBeenCalledOnce());
    expect(document.querySelector(".toast")).toHaveTextContent(/build request sent/i);
  });

  it("refreshes the injected snapshot on demand", async () => {
    const api = fixtureApi();
    await openStudio(api);
    fireEvent.click(screen.getByRole("button", { name: /refresh project snapshot/i }));
    await waitFor(() => expect(api.load).toHaveBeenCalledTimes(2));
  });

  it("shows API load failures as a visible, dismissible toast", async () => {
    const api: StudioApi = {
      load: vi.fn().mockRejectedValue(new Error("offline")),
      runBuild: vi.fn(),
    };
    render(<StudioApp api={api} />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/could not load project state/i);
    fireEvent.click(within(alert).getByRole("button", { name: /retry connection/i }));
    await waitFor(() => expect(api.load).toHaveBeenCalledTimes(2));
  });

  it("renders node details and closes them with Escape", async () => {
    await openStudio();
    const pipelineButtons = document.querySelectorAll(".pipeline-node");
    if (!pipelineButtons[2]) throw new Error("QMK compile pipeline node should be visible");
    fireEvent.click(pipelineButtons[2] as HTMLElement);
    expect(screen.getByRole("dialog", { name: /QMK firmware compile/i })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("reports a selected DAG node without a linked gate", async () => {
    await openStudio();
    fireEvent.click(screen.getAllByRole("button", { name: "Build graph" })[0] as HTMLElement);
    const nodeGrid = document.querySelectorAll(".node-detail-card");
    const sourcingCard = Array.from(nodeGrid).find((node) =>
      node.textContent?.includes("sourcing.bom"),
    );
    if (!sourcingCard) throw new Error("sourcing detail card should be visible");
    fireEvent.click(sourcingCard as HTMLElement);
    expect(document.querySelector(".toast")).toHaveTextContent(/sourcing\.bom.*Idle/);
  });

  it("refreshes into a visible load error and can recover when the next snapshot loads", async () => {
    const snapshot = createDemoSnapshot();
    const api: StudioApi = {
      load: vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(snapshot),
      runBuild: vi.fn(),
    };
    render(<StudioApp api={api} demo={false} />);
    const alert = await screen.findByRole("alert");
    fireEvent.click(within(alert).getByRole("button", { name: /retry connection/i }));
    await screen.findByRole("heading", { name: /good morning, engineer/i });
    expect(api.load).toHaveBeenCalledTimes(2);
  });

  it("closes the mobile drawer after a route is chosen", async () => {
    await openStudio();
    fireEvent.click(screen.getByRole("button", { name: "Toggle navigation" }));
    fireEvent.click(screen.getByRole("button", { name: "Artifacts" }));
    expect(document.querySelector(".studio-shell--mobile-open")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Artifacts" })).toBeInTheDocument();
  });

  it("uses cloned demo snapshots and records a local, clearly labeled demo build", async () => {
    const api = createDemoApi(() => new Date("2026-11-04T12:30:00Z"));
    const first = await api.load();
    const firstAgent = first.agents[0];
    if (!firstAgent) throw new Error("demo fixture must contain an electrical agent");
    firstAgent.label = "mutated by consumer";
    const second = await api.load();
    expect(second.agents[0]?.label).toBe("Electrical");
    const built = await api.runBuild();
    expect(built.lastBuild).toBe("just now");
    expect(built.activity[0]?.title).toBe("Build queued");
    expect(built.activity[0]?.time).toBe("4:30:00 AM");
    expect(built.activity[0]?.id).toBe("build-1793795400000");
    expect((await api.load()).activity[0]?.title).toBe("Build queued");
  });

  it("renders an unowned gate under the explicit unknown-owner fallback", async () => {
    const snapshot = createDemoSnapshot();
    const firstGate = snapshot.gates[0];
    if (!firstGate) throw new Error("demo fixture must contain a gate");
    snapshot.gates = [{ ...firstGate, id: "gate:unknown", owner_agent: null }];
    await openStudio(fixtureApi(snapshot));
    fireEvent.click(screen.getAllByRole("button", { name: /gate results/i })[0] as HTMLElement);
    expect(screen.getAllByRole("heading", { name: /gate results/i }).length).toBeGreaterThan(0);
    expect(screen.getByText("?")).toBeInTheDocument();
  });

  it("shows a graceful loading state before project data arrives", () => {
    const snapshot = createDemoSnapshot();
    const pending: StudioApi = {
      load: () => new Promise<BoardSnapshot>(() => {}),
      runBuild: vi.fn(),
    };
    render(<StudioApp api={pending} />);
    expect(screen.getByRole("status")).toHaveTextContent(/opening project workspace/i);
    expect(snapshot.projectName).toBe("atomc-keeb");
  });

  it("supports the mobile navigation drawer and collapsible desktop rail", async () => {
    await openStudio();
    fireEvent.click(screen.getByRole("button", { name: "Toggle navigation" }));
    expect(document.querySelector(".studio-shell--mobile-open")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close navigation" }));
    expect(document.querySelector(".studio-shell--mobile-open")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /collapse sidebar/i }));
    expect(document.querySelector(".studio-shell--collapsed")).toBeInTheDocument();
  });
});
