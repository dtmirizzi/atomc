import { Canvas, useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import * as THREE from "three";
import {
  geometryCenter,
  type Point2,
  type ViewerGeometry,
  type ViewerGeometryAvailable,
} from "./geometry.js";
import { supportsWebGL } from "./webgl.js";

/** Vertical gap between the PCB and the switch plate, in mm (typical standoff). */
const PLATE_GAP_MM = 4;

export function makeOutlineShape(outline: Point2[]): THREE.Shape {
  const shape = new THREE.Shape();
  outline.forEach(([x, y], index) => {
    if (index === 0) shape.moveTo(x, y);
    else shape.lineTo(x, y);
  });
  shape.closePath();
  return shape;
}

export function toSquareHole(path: THREE.Path, center: Point2, sizeMm: number): void {
  const half = sizeMm / 2;
  const [x, y] = center;
  path.moveTo(x - half, y - half);
  path.lineTo(x + half, y - half);
  path.lineTo(x + half, y + half);
  path.lineTo(x - half, y + half);
  path.closePath();
}

function CameraRig({ distance }: { distance: number }) {
  const camera = useThree((state) => state.camera);
  useEffect(() => {
    camera.up.set(0, 0, 1);
    camera.position.set(distance * 0.55, -distance * 0.75, distance * 0.9);
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
  }, [camera, distance]);
  return null;
}

function BoardScene({ geometry }: { geometry: ViewerGeometryAvailable }) {
  const center = geometryCenter(geometry);
  const plate = useMemo(() => {
    const shape = makeOutlineShape(geometry.board.outline);
    for (const sw of geometry.switches) {
      const hole = new THREE.Path();
      toSquareHole(hole, sw.center, sw.cutoutMm);
      shape.holes.push(hole);
    }
    return shape;
  }, [geometry]);

  const maxDimension = Math.max(geometry.bounds.widthMm, geometry.bounds.heightMm, 20);
  const boardZ = geometry.board.thicknessMm;
  const plateZ = boardZ + PLATE_GAP_MM;

  return (
    <>
      <CameraRig distance={maxDimension} />
      <ambientLight intensity={1.1} />
      <directionalLight position={[maxDimension, -maxDimension, maxDimension]} intensity={1.6} />
      <group position={[-center[0], -center[1], 0]}>
        <mesh>
          <extrudeGeometry
            args={[
              makeOutlineShape(geometry.board.outline),
              { depth: boardZ, bevelEnabled: false },
            ]}
          />
          <meshStandardMaterial color="#17603f" roughness={0.65} metalness={0.1} />
        </mesh>
        <mesh position={[0, 0, plateZ]}>
          <extrudeGeometry args={[plate, { depth: 1.5, bevelEnabled: false }]} />
          <meshStandardMaterial color="#2a2f37" roughness={0.9} metalness={0.05} />
        </mesh>
        {geometry.testPads.map((pad) => (
          <mesh
            key={pad.id}
            position={[pad.center[0], pad.center[1], pad.side === "bottom" ? -0.4 : boardZ + 0.3]}
          >
            <cylinderGeometry args={[pad.diameterMm / 2, pad.diameterMm / 2, 0.6, 16]} />
            <meshStandardMaterial color={pad.side === "bottom" ? "#cfa23a" : "#d35400"} />
          </mesh>
        ))}
      </group>
    </>
  );
}

export interface BoardViewerProps {
  geometry: ViewerGeometry;
}

/**
 * R3F canvas plus an always-present textual summary. The summary is the
 * accessible representation of the geometry, so the canvas is never the only
 * way to read the model.
 */
export function BoardViewer({ geometry }: BoardViewerProps) {
  const webgl = useMemo(() => supportsWebGL(), []);
  if (geometry.status === "unavailable") {
    return (
      <section className="viewer3d" aria-label="3D geometry unavailable">
        <div className="viewer3d__notice">
          <strong>3D geometry unavailable</strong>
          <p>{geometry.reason}</p>
        </div>
      </section>
    );
  }

  const maxDimension = Math.max(geometry.bounds.widthMm, geometry.bounds.heightMm, 20);
  return (
    <section className="viewer3d" aria-label="3D board viewer">
      <div className="viewer3d__stage">
        {webgl ? (
          <Canvas
            role="img"
            aria-label={`Interactive 3D view of ${geometry.switches.length} switch cutouts and ${geometry.testPads.length} test pads`}
            orthographic
            camera={{
              position: [maxDimension * 0.55, -maxDimension * 0.75, maxDimension * 0.9],
              zoom: 3,
              near: -maxDimension * 4,
              far: maxDimension * 8,
              up: [0, 0, 1],
            }}
          >
            <BoardScene geometry={geometry} />
          </Canvas>
        ) : (
          <p className="viewer3d__fallback" role="note">
            Interactive WebGL is not available in this browser. The derived geometry is listed
            below.
          </p>
        )}
      </div>
      <GeometrySummary geometry={geometry} />
    </section>
  );
}

/** Textual, screen-reader accessible description of derived geometry. */
export function GeometrySummary({ geometry }: { geometry: ViewerGeometryAvailable }) {
  return (
    <section className="viewer3d__summary" aria-label="Derived geometry summary">
      <h3>Derived geometry</h3>
      <dl className="viewer3d__facts">
        <div>
          <dt>Board bounds</dt>
          <dd>
            {formatMm(geometry.bounds.widthMm)} × {formatMm(geometry.bounds.heightMm)} ×{" "}
            {formatMm(geometry.board.thicknessMm)} mm
          </dd>
        </div>
        <div>
          <dt>Outline source</dt>
          <dd>/{geometry.outlineSource}</dd>
        </div>
        <div>
          <dt>Switch cutouts</dt>
          <dd>{geometry.switches.length}</dd>
        </div>
        <div>
          <dt>Test pads</dt>
          <dd>{geometry.testPads.length}</dd>
        </div>
      </dl>
      {geometry.notices.length > 0 && (
        <ul className="viewer3d__notices">
          {geometry.notices.map((notice) => (
            <li key={notice}>{notice}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function formatMm(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}
