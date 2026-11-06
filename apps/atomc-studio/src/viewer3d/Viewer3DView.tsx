import { CircleHelp, Cuboid, Layers } from "lucide-react";
import { useMemo } from "react";
import type { BoardSnapshot } from "../model.js";
import { BoardViewer } from "./BoardViewer.js";
import { deriveViewerGeometry } from "./geometry.js";
import "./viewer3d.css";

/**
 * 3D viewer view. Derives all geometry from the snapshot's system IR and labels
 * its source so the canvas can never pass fixture or partial data off as a real
 * build artifact.
 */
export function Viewer3DView({ snapshot }: { snapshot: BoardSnapshot }) {
  const geometry = useMemo(() => deriveViewerGeometry(snapshot.systemJson), [snapshot.systemJson]);
  const isDemo = snapshot.dataMode === "demo";

  const source = isDemo
    ? {
        label: "Simulated geometry",
        detail:
          "Fixture geometry from examples/atomc-pad/system_ir.json. No daemon, CAD export or build artifact was read.",
      }
    : snapshot.systemJson === undefined
      ? {
          label: "Geometry unavailable",
          detail:
            "This daemon snapshot does not include system IR, so no board geometry can be derived.",
        }
      : {
          label: "Daemon IR geometry",
          detail: `Derived from /layout, /keyboard and /mechanical at IR revision ${snapshot.revision}.`,
        };

  const counts =
    geometry.status === "available"
      ? `${geometry.switches.length} switches · ${geometry.testPads.length} test pads`
      : "no geometry";

  return (
    <div className="view-stack">
      <div className="view-intro">
        <div>
          <span className="eyebrow">PHYSICAL MODEL</span>
          <h2>3D viewer</h2>
          <p>Board outline, switch cutouts and test-pad markers derived from the system IR.</p>
        </div>
        <span className="badge badge--neutral">
          <Cuboid size={14} />
          {counts}
        </span>
      </div>
      <div className="info-banner">
        <CircleHelp size={16} />
        <span>
          <strong>{source.label}.</strong> {source.detail}
        </span>
      </div>
      {geometry.status === "available" && (
        <div className="viewer3d__legend">
          <span>
            <Layers size={14} /> PCB outline extrusion plus a plate layer with real cutout holes
          </span>
        </div>
      )}
      <BoardViewer geometry={geometry} />
    </div>
  );
}
