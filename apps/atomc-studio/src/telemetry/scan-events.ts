/**
 * Pure event model and layout math for the matrix-scan timing diagram.
 *
 * The daemon RPC does not expose matrix-scan telemetry yet. These types describe the
 * WaveDrom-style signals Studio wants to show, so a future `telemetry.subscribe` RPC
 * method can feed the same model without touching the view. Demo fixtures are shaped to
 * match the keyboard matrix block of the example IR (`examples/atomc-pad/system_ir.json`
 * and `examples/atomc-keeb/system_ir.json`), including row/column pin names and the
 * `diode_direction` value.
 */

export type ScanEventKind = "row-strobe" | "col-strobe" | "key-down" | "key-up";

export interface ScanEvent {
  id: string;
  kind: ScanEventKind;
  /** Start of the event window, in microseconds from the start of the capture. */
  atUs: number;
  /** Length of the event window, in microseconds. Always >= 1. */
  durationUs: number;
  label: string;
  row?: number;
  col?: number;
}

/** The subset of the IR `keyboard.matrix` node the diagram needs. */
export interface MatrixSpec {
  rows: number;
  cols: number;
  rowPins: string[];
  colPins: string[];
  diodeDirection: string;
}

export interface ScanTimelineModel {
  spec: MatrixSpec;
  durationUs: number;
  events: ScanEvent[];
}

/** Matches `examples/atomc-pad/system_ir.json` (`keyboard.matrix`). */
export const ATOMC_PAD_MATRIX: MatrixSpec = {
  rows: 3,
  cols: 3,
  rowPins: ["B12", "B13", "B14"],
  colPins: ["A0", "A1", "A2"],
  diodeDirection: "COL2ROW",
};

/** Matches `examples/atomc-keeb/system_ir.json` (`keyboard.matrix`). */
export const ATOMC_KEEB_MATRIX: MatrixSpec = {
  rows: 4,
  cols: 12,
  rowPins: ["B12", "B13", "B14", "B15"],
  colPins: ["A0", "A1", "A2", "A3", "A5", "A6", "A7", "B0", "B1", "B10", "C14", "C15"],
  diodeDirection: "COL2ROW",
};

export interface DemoScanOptions {
  /** How long each row is selected, in microseconds. */
  rowStrobeUs?: number;
  /** Idle time between row selections, in microseconds. */
  settleUs?: number;
  /** Number of full matrix-scan cycles to render. */
  cycles?: number;
  /** How long a pressed key stays down after first being detected, in microseconds. */
  holdUs?: number;
  /** Keys held during the capture; defaults to the first key of the first two rows. */
  pressedKeys?: Array<{ row: number; col: number }>;
}

function defaultPressedKeys(spec: MatrixSpec): Array<{ row: number; col: number }> {
  const candidates = [
    { row: 0, col: 0 },
    { row: 1, col: 0 },
  ];
  return candidates.filter((key) => key.row < spec.rows && key.col < spec.cols);
}

/**
 * Deterministic demo capture: each cycle selects every row in turn, samples every column
 * while the row is active, and records key-down/up windows for the pressed keys. No
 * wall-clock time is read, so repeated calls produce byte-identical output.
 */
export function createDemoScanModel(
  spec: MatrixSpec = ATOMC_KEEB_MATRIX,
  options: DemoScanOptions = {},
): ScanTimelineModel {
  const rowStrobeUs = options.rowStrobeUs ?? 200;
  const settleUs = options.settleUs ?? 50;
  const cycles = options.cycles ?? 1;
  const holdUs = options.holdUs ?? 700;
  const stepUs = rowStrobeUs + settleUs;
  const cycleUs = stepUs * spec.rows;
  const durationUs = cycleUs * cycles;
  const events: ScanEvent[] = [];

  for (let cycle = 0; cycle < cycles; cycle += 1) {
    for (let row = 0; row < spec.rows; row += 1) {
      const rowStartUs = cycle * cycleUs + row * stepUs;
      events.push({
        id: `row-strobe-${cycle}-${row}`,
        kind: "row-strobe",
        atUs: rowStartUs,
        durationUs: rowStrobeUs,
        row,
        label: `Row ${row} selected`,
      });
      const sampleOffset = Math.max(1, Math.round(rowStrobeUs / 4));
      const sampleUs = Math.max(1, Math.round(rowStrobeUs / 2));
      for (let col = 0; col < spec.cols; col += 1) {
        events.push({
          id: `col-sample-${cycle}-${row}-${col}`,
          kind: "col-strobe",
          atUs: rowStartUs + sampleOffset,
          durationUs: sampleUs,
          row,
          col,
          label: `Col ${col} sampled`,
        });
      }
    }
  }

  const pressedKeys = options.pressedKeys ?? defaultPressedKeys(spec);
  for (const key of pressedKeys) {
    if (key.row < 0 || key.row >= spec.rows || key.col < 0 || key.col >= spec.cols) continue;
    const downAtUs = key.row * stepUs;
    const releaseUs = Math.min(downAtUs + holdUs, durationUs);
    events.push({
      id: `key-down-${key.row}-${key.col}`,
      kind: "key-down",
      atUs: downAtUs,
      durationUs: Math.max(1, releaseUs - downAtUs),
      row: key.row,
      col: key.col,
      label: `Key R${key.row}C${key.col} down`,
    });
    events.push({
      id: `key-up-${key.row}-${key.col}`,
      kind: "key-up",
      atUs: releaseUs,
      durationUs: Math.max(1, Math.round(stepUs / 4)),
      row: key.row,
      col: key.col,
      label: `Key R${key.row}C${key.col} up`,
    });
  }

  return { spec, durationUs, events };
}

export type LaneKind = "row" | "col" | "key";

export interface TimelineLane {
  id: string;
  label: string;
  kind: LaneKind;
  index: number;
}

/** One lane per row signal, one per column signal, then a shared key-event lane. */
export function buildLanes(spec: MatrixSpec): TimelineLane[] {
  const lanes: TimelineLane[] = [];
  for (let row = 0; row < spec.rows; row += 1) {
    lanes.push({
      id: `row:${row}`,
      label: `Row ${row} · ${spec.rowPins[row] ?? "—"}`,
      kind: "row",
      index: row,
    });
  }
  for (let col = 0; col < spec.cols; col += 1) {
    lanes.push({
      id: `col:${col}`,
      label: `Col ${col} · ${spec.colPins[col] ?? "—"}`,
      kind: "col",
      index: col,
    });
  }
  lanes.push({ id: "keys", label: "Key events", kind: "key", index: 0 });
  return lanes;
}

/** Lanes are addressed by id so a key event can share the "keys" lane. */
export function laneForEvent(event: ScanEvent): string {
  if (event.kind === "row-strobe") return `row:${event.row ?? 0}`;
  if (event.kind === "col-strobe") return `col:${event.col ?? 0}`;
  return "keys";
}

export interface TimeWindow {
  startUs: number;
  endUs: number;
}

/** Clamped window bounds: start never precedes the capture, end never precedes start. */
export function eventWindow(event: ScanEvent): TimeWindow {
  const startUs = Math.max(0, event.atUs);
  const endUs = Math.max(startUs, event.atUs + event.durationUs);
  return { startUs, endUs };
}

/** Linear time -> x mapping into a plot of `width` pixels, clamped to the plot. */
export function scaleTime(atUs: number, durationUs: number, width: number): number {
  if (durationUs <= 0 || width <= 0) return 0;
  return Math.min(width, Math.max(0, (atUs / durationUs) * width));
}

export function formatMicros(us: number): string {
  if (us >= 1000) {
    const ms = us / 1000;
    return `${Number.isInteger(ms) ? ms : ms.toFixed(2)}ms`;
  }
  return `${Math.round(us)}µs`;
}

export interface TimelineLayoutOptions {
  plotWidth?: number;
  laneHeight?: number;
  labelWidth?: number;
  tickCount?: number;
  minBarWidth?: number;
}

export interface TimelineBar {
  event: ScanEvent;
  laneId: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface TimelineTick {
  atUs: number;
  x: number;
  label: string;
}

export interface TimelineLayout {
  width: number;
  height: number;
  laneHeight: number;
  labelWidth: number;
  plotWidth: number;
  lanes: TimelineLane[];
  bars: TimelineBar[];
  ticks: TimelineTick[];
}

/**
 * Turns a scan model into pixel geometry: lane y positions, bar x/width and time ticks.
 * Pure and deterministic; the SVG component only draws the result.
 */
export function layoutTimeline(
  model: ScanTimelineModel,
  options: TimelineLayoutOptions = {},
): TimelineLayout {
  const plotWidth = options.plotWidth ?? 640;
  const laneHeight = options.laneHeight ?? 26;
  const labelWidth = options.labelWidth ?? 132;
  const tickCount = Math.max(1, options.tickCount ?? 4);
  const minBarWidth = options.minBarWidth ?? 1;

  const lanes = buildLanes(model.spec);
  const laneIndex = new Map<string, number>(
    lanes.map((lane, index): [string, number] => [lane.id, index]),
  );

  const bars: TimelineBar[] = [];
  for (const event of model.events) {
    const laneId = laneForEvent(event);
    const index = laneIndex.get(laneId);
    if (index === undefined) continue;
    const { startUs, endUs } = eventWindow(event);
    const startX = scaleTime(startUs, model.durationUs, plotWidth);
    const endX = scaleTime(endUs, model.durationUs, plotWidth);
    const x = labelWidth + startX;
    const width = Math.max(minBarWidth, endX - startX);
    bars.push({
      event,
      laneId,
      x,
      y: index * laneHeight + laneHeight * 0.22,
      width,
      height: laneHeight * 0.56,
    });
  }

  const ticks: TimelineTick[] = [];
  for (let i = 0; i <= tickCount; i += 1) {
    const atUs = (model.durationUs * i) / tickCount;
    ticks.push({
      atUs,
      x: labelWidth + scaleTime(atUs, model.durationUs, plotWidth),
      label: `${Math.round(atUs)}µs`,
    });
  }

  return {
    width: labelWidth + plotWidth,
    height: lanes.length * laneHeight,
    laneHeight,
    labelWidth,
    plotWidth,
    lanes,
    bars,
    ticks,
  };
}
