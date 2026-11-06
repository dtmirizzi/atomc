import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import * as THREE from "three";
import { afterEach, describe, expect, it, vi } from "vitest";
import { type BoardSnapshot, createDemoSnapshot, type StudioApi } from "../src/model.js";
import { StudioApp } from "../src/studio-app.js";
import {
  BoardViewer,
  GeometrySummary,
  makeOutlineShape,
  toSquareHole,
} from "../src/viewer3d/BoardViewer.js";
import { padFixtureIr } from "../src/viewer3d/fixtures.js";
import { deriveViewerGeometry, geometryCenter, KEY_PITCH_MM } from "../src/viewer3d/geometry.js";
import { Viewer3DView } from "../src/viewer3d/Viewer3DView.js";

// jsdom has no WebGL; the viewer must fall back to its accessible summary.
vi.mock("../src/viewer3d/webgl.js", () => ({ supportsWebGL: () => false }));

afterEach(() => {
  cleanup();
});

function geometryOrThrow(raw: unknown) {
  const geometry = deriveViewerGeometry(raw);
  if (geometry.status !== "available") throw new Error(geometry.reason);
  return geometry;
}

function fixtureApi(snapshot: BoardSnapshot): StudioApi {
  return {
    load: vi.fn(async () => structuredClone(snapshot)),
    runBuild: vi.fn(async () => structuredClone(snapshot)),
  };
}

describe("deriveViewerGeometry", () => {
  it("derives board, switch and test-pad geometry from the pad fixture", () => {
    const geometry = geometryOrThrow(padFixtureIr);
    expect(geometry.outlineSource).toBe("layout");
    expect(geometry.board.outline).toHaveLength(4);
    expect(geometry.board.thicknessMm).toBeCloseTo(1.6);
    expect(geometry.bounds.widthMm).toBeCloseTo(80);
    expect(geometry.bounds.heightMm).toBeCloseTo(80);
    expect(geometry.switches).toHaveLength(9);
    expect(geometry.testPads).toHaveLength(15);
    expect(geometry.notices).toEqual([]);
  });

  it("maps keyboard units to board millimetres on a 19.05 mm pitch", () => {
    const geometry = geometryOrThrow(padFixtureIr);
    const first = geometry.switches.find((sw) => sw.id === "key:K0_0");
    const last = geometry.switches.find((sw) => sw.id === "key:K2_0");
    if (!first || !last) throw new Error("fixture keys are missing");
    const half = KEY_PITCH_MM / 2;
    // Top-left layout origin flips to the board's bottom-left frame.
    expect(first.center[0]).toBeCloseTo(half);
    expect(first.center[1]).toBeCloseTo(80 - half);
    expect(last.center[0]).toBeCloseTo(half);
    expect(last.center[1]).toBeCloseTo(80 - 2 * KEY_PITCH_MM - half);
    expect(first.cutoutMm).toBeCloseTo(14);
    expect(first.rotationDeg).toBe(0);
  });

  it("keeps test-pad coordinates in board frame with side and net refs", () => {
    const geometry = geometryOrThrow(padFixtureIr);
    const vbus = geometry.testPads.find((pad) => pad.id === "pad:TP_VBUS");
    if (!vbus) throw new Error("fixture test pad is missing");
    expect(vbus.center).toEqual([6, 6]);
    expect(vbus.netRef).toBe("net:VBUS");
    expect(vbus.side).toBe("bottom");
    expect(vbus.diameterMm).toBeCloseTo(1);
  });

  it("falls back to the mechanical PCB bbox when no layout outline exists", () => {
    const geometry = geometryOrThrow({
      mechanical: { pcb_bbox: { min: [0, 0, 0], max: [40, 20, 1.6] } },
    });
    expect(geometry.outlineSource).toBe("mechanical");
    expect(geometry.board.outline).toHaveLength(4);
    expect(geometry.bounds.widthMm).toBeCloseTo(40);
    expect(geometry.bounds.heightMm).toBeCloseTo(20);
    expect(geometry.switches).toHaveLength(0);
    expect(geometry.testPads).toHaveLength(0);
    expect(geometry.notices).toContain(
      "No switch placements in /keyboard; rendering the board outline only.",
    );
    expect(geometry.notices).toContain("No test pads in /layout; the test-pad overlay is empty.");
  });

  it("applies default cutout and pitch when /mechanical/plate is absent", () => {
    const geometry = geometryOrThrow({
      layout: {
        outline: {
          polygon: [
            [0, 0],
            [50, 0],
            [50, 50],
            [0, 50],
          ],
        },
      },
      keyboard: {
        keys: [{ id: "key:K0_0", row: 0, col: 0, x_u: 1, y_u: 1, w_u: 1, h_u: 1 }],
      },
    });
    const sw = geometry.switches[0];
    if (!sw) throw new Error("expected a derived switch");
    expect(sw.cutoutMm).toBeCloseTo(14);
    expect(sw.center[0]).toBeCloseTo(KEY_PITCH_MM * 1.5);
  });

  it("reports unavailable states instead of inventing a board", () => {
    expect(deriveViewerGeometry(undefined).status).toBe("unavailable");
    expect(deriveViewerGeometry(null).status).toBe("unavailable");
    expect(deriveViewerGeometry({}).status).toBe("unavailable");
    expect(deriveViewerGeometry({ layout: {} }).status).toBe("unavailable");
    const empty = deriveViewerGeometry({});
    if (empty.status !== "unavailable") throw new Error("expected unavailable");
    expect(empty.reason).toMatch(/no board outline/i);
  });

  it("skips malformed keys and pads rather than rendering bad geometry", () => {
    const geometry = geometryOrThrow({
      layout: {
        outline: {
          polygon: [
            [0, 0],
            [30, 0],
            [30, 30],
            [0, 30],
          ],
        },
        test_pads: [
          { id: "pad:ok", net_ref: "net:X", x: 1, y: 2, kind: "edge" },
          { id: "pad:bad", net_ref: "net:Y", x: "nope", y: 2 },
        ],
      },
      keyboard: {
        keys: [
          { id: "key:ok", row: 0, col: 0, x_u: 0, y_u: 0 },
          { id: "key:bad", row: 1, col: 1 },
        ],
      },
    });
    expect(geometry.switches).toHaveLength(1);
    expect(geometry.testPads).toHaveLength(1);
    expect(geometry.testPads[0]?.side).toBe("top");
    expect(geometry.testPads[0]?.kind).toBe("edge");
  });

  it("computes a bounding-box centre for renderer framing", () => {
    const geometry = geometryOrThrow(padFixtureIr);
    expect(geometryCenter(geometry)).toEqual([40, 40]);
  });
});

describe("BoardViewer shape helpers", () => {
  it("reports no WebGL when the real probe runs in jsdom", async () => {
    const actual = await vi.importActual<typeof import("../src/viewer3d/webgl.js")>(
      "../src/viewer3d/webgl.js",
    );
    expect(actual.supportsWebGL()).toBe(false);
  });

  it("builds a closed three shape and square cutout holes", () => {
    const shape = makeOutlineShape([
      [0, 0],
      [10, 0],
      [10, 10],
      [0, 10],
    ]);
    expect(shape.getPoints().length).toBeGreaterThanOrEqual(4);
    const hole = new THREE.Path();
    toSquareHole(hole, [5, 5], 4);
    expect(hole.getPoints().length).toBeGreaterThanOrEqual(4);
  });
});

describe("Viewer3DView", () => {
  it("renders labelled simulated geometry from the demo snapshot", async () => {
    render(<Viewer3DView snapshot={createDemoSnapshot()} />);
    expect(screen.getByRole("heading", { name: "3D viewer" })).toBeInTheDocument();
    expect(screen.getByText("Simulated geometry.")).toBeInTheDocument();
    expect(
      screen.getByText(/no daemon, CAD export or build artifact was read/i),
    ).toBeInTheDocument();
    const summary = screen.getByLabelText("Derived geometry summary");
    expect(within(summary).getByText("9")).toBeInTheDocument();
    expect(within(summary).getByText("15")).toBeInTheDocument();
    expect(within(summary).getByText("80 × 80 × 1.60 mm")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/interactive webgl is not available/i);
    expect(screen.getByText("9 switches · 15 test pads")).toBeInTheDocument();
  });

  it("renders daemon geometry when the snapshot carries system IR", () => {
    const snapshot = createDemoSnapshot();
    snapshot.dataMode = "daemon";
    render(<Viewer3DView snapshot={snapshot} />);
    expect(screen.getByText("Daemon IR geometry.")).toBeInTheDocument();
    expect(screen.getByText(/IR revision 128/)).toBeInTheDocument();
    expect(screen.queryByText("Simulated geometry.")).not.toBeInTheDocument();
  });

  it("shows an honest unavailable notice when daemon IR is missing", () => {
    const snapshot = createDemoSnapshot();
    snapshot.dataMode = "daemon";
    delete snapshot.systemJson;
    render(<Viewer3DView snapshot={snapshot} />);
    expect(screen.getByText("Geometry unavailable.")).toBeInTheDocument();
    expect(screen.getByText(/does not include system IR/i)).toBeInTheDocument();
    expect(screen.getByText("3D geometry unavailable")).toBeInTheDocument();
  });

  it("renders an unavailable state for a snapshot with unusable IR", () => {
    const snapshot = createDemoSnapshot();
    snapshot.systemJson = { layout: {} };
    render(<Viewer3DView snapshot={snapshot} />);
    expect(screen.getByText("3D geometry unavailable")).toBeInTheDocument();
    expect(screen.getByLabelText("3D geometry unavailable")).toBeInTheDocument();
  });

  it("exposes the summary through BoardViewer directly", () => {
    const geometry = geometryOrThrow(padFixtureIr);
    render(<BoardViewer geometry={geometry} />);
    expect(screen.getByLabelText("Derived geometry summary")).toBeInTheDocument();
    render(<GeometrySummary geometry={geometry} />);
    expect(screen.getAllByRole("heading", { name: "Derived geometry" }).length).toBeGreaterThan(0);
  });
});

describe("Studio 3D navigation", () => {
  it("opens the 3D viewer from the primary navigation", async () => {
    render(<StudioApp api={fixtureApi(createDemoSnapshot())} demo={true} />);
    await screen.findByRole("heading", { name: /good morning, engineer/i });
    fireEvent.click(screen.getByRole("button", { name: "3D viewer" }));
    expect(screen.getByRole("heading", { name: "3D viewer" })).toBeInTheDocument();
    expect(screen.getByText("Simulated geometry.")).toBeInTheDocument();
  });
});
