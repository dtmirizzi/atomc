/**
 * The telemetry API seam. The view talks to a `TelemetrySource` and nothing else, so a
 * future daemon RPC method (`telemetry.subscribe`) only has to implement this interface.
 * Until then the demo source returns clearly labeled fixtures and the daemon source
 * reports the feature as unavailable rather than faking a live stream.
 */

import type { DataMode, TelemetryNotice } from "../model.js";
import { type ConsoleLine, createDemoConsoleLines } from "./console-stream.js";
import {
  ATOMC_KEEB_MATRIX,
  createDemoScanModel,
  type MatrixSpec,
  type ScanTimelineModel,
} from "./scan-events.js";

export interface TelemetryBundle {
  /** Null when the active source cannot provide matrix-scan data. */
  scan: ScanTimelineModel | null;
  console: ConsoleLine[];
  notice: TelemetryNotice;
}

export interface TelemetrySource {
  readonly mode: DataMode;
  load(): Promise<TelemetryBundle>;
  /** Subscribe to new console lines. Returns an unsubscribe function. */
  subscribe(listener: (line: ConsoleLine) => void): () => void;
}

export const DEMO_TELEMETRY_NOTICE: TelemetryNotice = {
  kind: "demo",
  label: "Simulated telemetry",
  detail:
    "Fixture events below are illustrative samples shaped like real matrix scans and console output. No daemon, Renode session or firmware run produced them.",
};

export const UNAVAILABLE_TELEMETRY_NOTICE: TelemetryNotice = {
  kind: "unavailable",
  label: "Telemetry unavailable",
  detail: "Matrix-scan and console telemetry are not exposed by the daemon RPC yet.",
};

export function createDemoTelemetrySource(spec: MatrixSpec = ATOMC_KEEB_MATRIX): TelemetrySource {
  return {
    mode: "demo",
    async load() {
      return {
        scan: createDemoScanModel(spec),
        console: createDemoConsoleLines(),
        notice: DEMO_TELEMETRY_NOTICE,
      };
    },
    subscribe() {
      return () => {};
    },
  };
}

export function createDaemonTelemetrySource(): TelemetrySource {
  return {
    mode: "daemon",
    async load() {
      return {
        scan: null,
        console: [],
        notice: UNAVAILABLE_TELEMETRY_NOTICE,
      };
    },
    subscribe() {
      return () => {};
    },
  };
}

export function createTelemetrySource(
  mode: DataMode,
  spec: MatrixSpec = ATOMC_KEEB_MATRIX,
): TelemetrySource {
  return mode === "demo" ? createDemoTelemetrySource(spec) : createDaemonTelemetrySource();
}
