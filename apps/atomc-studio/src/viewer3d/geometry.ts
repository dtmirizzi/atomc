/**
 * Pure geometry derivation for the Studio 3D viewer.
 *
 * Every value returned here is traceable to a field in the system IR
 * (`/layout`, `/keyboard`, `/mechanical`). Nothing is invented: when the IR does
 * not carry a board outline the result is an explicit `unavailable` state rather
 * than a placeholder shape.
 *
 * This module deliberately has no `three`/WebGL dependency so it can be unit
 * tested in jsdom and reused by any renderer.
 */

/** 1u in keyboard layout is 19.05 mm (contract: ir-schema.md §1). */
export const KEY_PITCH_MM = 19.05;
/** Fallback switch cutout when `/mechanical/plate` is absent (14 mm MX cutout). */
export const DEFAULT_CUTOUT_MM = 14.0;
/** Fallback PCB thickness in mm. */
export const DEFAULT_THICKNESS_MM = 1.6;

export type Point2 = [number, number];
export type Side = "top" | "bottom";

export interface BoardMesh {
  /** Closed outline polygon in board frame (mm, origin bottom-left). */
  outline: Point2[];
  thicknessMm: number;
}

export interface SwitchMesh {
  id: string;
  row: number;
  col: number;
  /** Cutout centre in board frame (mm). */
  center: Point2;
  cutoutMm: number;
  rotationDeg: number;
}

export interface TestPadMesh {
  id: string;
  netRef: string;
  center: Point2;
  diameterMm: number;
  side: Side;
  kind: string;
  label?: string;
}

export interface GeometryBounds {
  min: Point2;
  max: Point2;
  widthMm: number;
  heightMm: number;
  thicknessMm: number;
}

export interface ViewerGeometryAvailable {
  status: "available";
  /** Where the board outline came from. */
  outlineSource: "layout" | "mechanical";
  board: BoardMesh;
  switches: SwitchMesh[];
  testPads: TestPadMesh[];
  bounds: GeometryBounds;
  /** Honest notes about fields the IR did not provide. */
  notices: string[];
}

export interface ViewerGeometryUnavailable {
  status: "unavailable";
  reason: string;
  notices: string[];
}

export type ViewerGeometry = ViewerGeometryAvailable | ViewerGeometryUnavailable;

type JsonRecord = Record<string, unknown>;

function asRecord(value: unknown): JsonRecord | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as JsonRecord)
    : undefined;
}

function asFiniteNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function asPoint(value: unknown): Point2 | undefined {
  if (!Array.isArray(value) || value.length < 2) return undefined;
  const x = asFiniteNumber(value[0]);
  const y = asFiniteNumber(value[1]);
  if (x === undefined || y === undefined) return undefined;
  return [x, y];
}

function coercePolygon(value: unknown): Point2[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const points: Point2[] = [];
  for (const candidate of value) {
    const point = asPoint(candidate);
    if (!point) return undefined;
    points.push(point);
  }
  return points.length >= 3 ? points : undefined;
}

function rectangleFromBbox(min: Point2, max: Point2): Point2[] {
  return [
    [min[0], min[1]],
    [max[0], min[1]],
    [max[0], max[1]],
    [min[0], max[1]],
  ];
}

function boundsFromPolygon(polygon: Point2[], thicknessMm: number): GeometryBounds {
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const [x, y] of polygon) {
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }
  return {
    min: [minX, minY],
    max: [maxX, maxY],
    widthMm: maxX - minX,
    heightMm: maxY - minY,
    thicknessMm,
  };
}

interface OutlineResult {
  polygon: Point2[];
  thicknessMm: number;
  source: "layout" | "mechanical";
}

function resolveOutline(ir: JsonRecord): OutlineResult | undefined {
  const layout = asRecord(ir.layout);
  const layoutOutline = asRecord(layout?.outline);
  const layoutPolygon = coercePolygon(layoutOutline?.polygon);
  if (layoutPolygon) {
    return {
      polygon: layoutPolygon,
      thicknessMm: asFiniteNumber(layoutOutline?.thickness_mm) ?? DEFAULT_THICKNESS_MM,
      source: "layout",
    };
  }

  const mechanical = asRecord(ir.mechanical);
  const bbox = asRecord(mechanical?.pcb_bbox);
  const min = asPoint(bbox?.min);
  const max = asPoint(bbox?.max);
  if (min && max && max[0] > min[0] && max[1] > min[1]) {
    const bboxMinZ = Array.isArray(bbox?.min) ? asFiniteNumber(bbox.min[2]) : undefined;
    const bboxMaxZ = Array.isArray(bbox?.max) ? asFiniteNumber(bbox.max[2]) : undefined;
    const thickness =
      bboxMinZ !== undefined && bboxMaxZ !== undefined && bboxMaxZ > bboxMinZ
        ? bboxMaxZ - bboxMinZ
        : DEFAULT_THICKNESS_MM;
    return { polygon: rectangleFromBbox(min, max), thicknessMm: thickness, source: "mechanical" };
  }

  return undefined;
}

function deriveSwitches(
  ir: JsonRecord,
  topY: number,
  cutoutMm: number,
  pitchMm: number,
): SwitchMesh[] {
  const keyboard = asRecord(ir.keyboard);
  const keys = keyboard?.keys;
  if (!Array.isArray(keys)) return [];
  const switches: SwitchMesh[] = [];
  for (const candidate of keys) {
    const key = asRecord(candidate);
    if (!key) continue;
    const id = typeof key.id === "string" ? key.id : undefined;
    const row = asFiniteNumber(key.row);
    const col = asFiniteNumber(key.col);
    const xU = asFiniteNumber(key.x_u);
    const yU = asFiniteNumber(key.y_u);
    if (
      id === undefined ||
      row === undefined ||
      col === undefined ||
      xU === undefined ||
      yU === undefined
    ) {
      continue;
    }
    const wU = asFiniteNumber(key.w_u) ?? 1;
    const hU = asFiniteNumber(key.h_u) ?? 1;
    // Keyboard layout origin is top-left; board frame origin is bottom-left
    // (contract: ir-schema.md §1). Flip Y against the board bbox height.
    const centerX = xU * pitchMm + (wU * pitchMm) / 2;
    const centerY = topY - yU * pitchMm - (hU * pitchMm) / 2;
    switches.push({
      id,
      row,
      col,
      center: [centerX, centerY],
      cutoutMm,
      rotationDeg: asFiniteNumber(key.rotation_deg) ?? 0,
    });
  }
  return switches;
}

function deriveTestPads(ir: JsonRecord): TestPadMesh[] {
  const layout = asRecord(ir.layout);
  const pads = layout?.test_pads;
  if (!Array.isArray(pads)) return [];
  const markers: TestPadMesh[] = [];
  for (const candidate of pads) {
    const pad = asRecord(candidate);
    if (!pad) continue;
    const id = typeof pad.id === "string" ? pad.id : undefined;
    const netRef = typeof pad.net_ref === "string" ? pad.net_ref : undefined;
    const x = asFiniteNumber(pad.x);
    const y = asFiniteNumber(pad.y);
    if (id === undefined || netRef === undefined || x === undefined || y === undefined) continue;
    const label = typeof pad.label === "string" ? pad.label : undefined;
    markers.push({
      id,
      netRef,
      center: [x, y],
      diameterMm: asFiniteNumber(pad.diameter_mm) ?? 1.0,
      side: pad.side === "bottom" ? "bottom" : "top",
      kind: typeof pad.kind === "string" ? pad.kind : "pogo",
      ...(label !== undefined ? { label } : {}),
    });
  }
  return markers;
}

/**
 * Turn a system IR document (or any subset of it) into renderer-agnostic meshes.
 *
 * Accepts `unknown` because daemon snapshots cross a JSON boundary; every field
 * is narrowed before use and missing data never produces invented geometry.
 */
export function deriveViewerGeometry(raw: unknown): ViewerGeometry {
  const ir = asRecord(raw);
  if (!ir) {
    return {
      status: "unavailable",
      reason: "No system IR was supplied, so there is no board geometry to render.",
      notices: [],
    };
  }

  const outline = resolveOutline(ir);
  if (!outline) {
    return {
      status: "unavailable",
      reason:
        "No board outline found in /layout/outline or /mechanical/pcb_bbox; refusing to draw a placeholder board.",
      notices: [],
    };
  }

  const mechanical = asRecord(ir.mechanical);
  const plate = asRecord(mechanical?.plate);
  const cutoutMm = asFiniteNumber(plate?.cutout_mm) ?? DEFAULT_CUTOUT_MM;
  const pitchMm = asFiniteNumber(plate?.pitch_mm) ?? KEY_PITCH_MM;

  const bounds = boundsFromPolygon(outline.polygon, outline.thicknessMm);
  const switches = deriveSwitches(ir, bounds.max[1], cutoutMm, pitchMm);
  const testPads = deriveTestPads(ir);

  const notices: string[] = [];
  if (switches.length === 0) {
    notices.push("No switch placements in /keyboard; rendering the board outline only.");
  }
  if (testPads.length === 0) {
    notices.push("No test pads in /layout; the test-pad overlay is empty.");
  }

  return {
    status: "available",
    outlineSource: outline.source,
    board: { outline: outline.polygon, thicknessMm: outline.thicknessMm },
    switches,
    testPads,
    bounds,
    notices,
  };
}

/** Centre of a geometry's bounding box in board frame (mm). */
export function geometryCenter(geometry: ViewerGeometryAvailable): Point2 {
  return [
    (geometry.bounds.min[0] + geometry.bounds.max[0]) / 2,
    (geometry.bounds.min[1] + geometry.bounds.max[1]) / 2,
  ];
}
