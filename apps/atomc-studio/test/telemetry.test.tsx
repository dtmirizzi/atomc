import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ConsoleStream } from "../src/telemetry/ConsoleStream.js";
import {
  CONSOLE_VIEW_LIMIT,
  ConsoleBuffer,
  type ConsoleLine,
  createDemoConsoleLines,
  formatConsoleTimestamp,
} from "../src/telemetry/console-stream.js";
import { ScanTimeline } from "../src/telemetry/ScanTimeline.js";
import {
  ATOMC_KEEB_MATRIX,
  ATOMC_PAD_MATRIX,
  buildLanes,
  createDemoScanModel,
  eventWindow,
  formatMicros,
  laneForEvent,
  layoutTimeline,
  scaleTime,
} from "../src/telemetry/scan-events.js";
import {
  createDaemonTelemetrySource,
  createDemoTelemetrySource,
  createTelemetrySource,
  DEMO_TELEMETRY_NOTICE,
  type TelemetryBundle,
  type TelemetrySource,
  UNAVAILABLE_TELEMETRY_NOTICE,
} from "../src/telemetry/source.js";
import { TelemetryView } from "../src/telemetry/TelemetryView.js";

afterEach(() => {
  cleanup();
});

const line = (overrides: Partial<ConsoleLine> = {}): ConsoleLine => ({
  id: "console-test",
  at: "2026-11-04T10:41:38.000Z",
  source: "renode",
  level: "info",
  text: "boot",
  ...overrides,
});

function fakeSource(bundle: TelemetryBundle): TelemetrySource & {
  emit: (next: ConsoleLine) => void;
} {
  const listeners = new Set<(next: ConsoleLine) => void>();
  return {
    mode: bundle.notice.kind === "demo" ? "demo" : "daemon",
    load: vi.fn(async () => bundle),
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    emit(next) {
      for (const listener of listeners) listener(next);
    },
  };
}

describe("scan-events model", () => {
  it("ships matrix specs that match the example IR", () => {
    expect(ATOMC_PAD_MATRIX).toMatchObject({ rows: 3, cols: 3, diodeDirection: "COL2ROW" });
    expect(ATOMC_KEEB_MATRIX).toMatchObject({ rows: 4, cols: 12, diodeDirection: "COL2ROW" });
    expect(ATOMC_KEEB_MATRIX.rowPins).toHaveLength(4);
    expect(ATOMC_KEEB_MATRIX.colPins).toHaveLength(12);
  });

  it("builds a deterministic demo capture with row, column and key events", () => {
    const first = createDemoScanModel(ATOMC_PAD_MATRIX);
    const second = createDemoScanModel(ATOMC_PAD_MATRIX);
    expect(first).toEqual(second);
    expect(first.durationUs).toBe(750);
    const rowStrobes = first.events.filter((event) => event.kind === "row-strobe");
    const colStrobes = first.events.filter((event) => event.kind === "col-strobe");
    const keyDowns = first.events.filter((event) => event.kind === "key-down");
    expect(rowStrobes).toHaveLength(3);
    expect(colStrobes).toHaveLength(9);
    expect(keyDowns).toHaveLength(2);
    expect(first.events.every((event) => event.durationUs >= 1)).toBe(true);
  });

  it("honours custom capture options and skips out-of-range pressed keys", () => {
    const model = createDemoScanModel(ATOMC_PAD_MATRIX, {
      rowStrobeUs: 100,
      settleUs: 0,
      cycles: 2,
      holdUs: 100,
      pressedKeys: [{ row: 9, col: 9 }],
    });
    expect(model.durationUs).toBe(600);
    expect(model.events.filter((event) => event.kind === "key-down")).toHaveLength(0);
    expect(model.events.filter((event) => event.kind === "row-strobe")).toHaveLength(6);
  });

  it("assigns lanes per row, per column and to a shared key lane", () => {
    const lanes = buildLanes({ ...ATOMC_PAD_MATRIX, rowPins: [], colPins: [] });
    expect(lanes.map((lane) => lane.id)).toEqual([
      "row:0",
      "row:1",
      "row:2",
      "col:0",
      "col:1",
      "col:2",
      "keys",
    ]);
    expect(lanes[0]?.label).toContain("—");
    expect(lanes.at(-1)?.kind).toBe("key");
    expect(
      laneForEvent({ id: "a", kind: "row-strobe", atUs: 0, durationUs: 1, label: "", row: 2 }),
    ).toBe("row:2");
    expect(
      laneForEvent({ id: "b", kind: "col-strobe", atUs: 0, durationUs: 1, label: "", col: 1 }),
    ).toBe("col:1");
    expect(laneForEvent({ id: "c", kind: "key-down", atUs: 0, durationUs: 1, label: "" })).toBe(
      "keys",
    );
  });

  it("clamps event windows and defaults a missing row index", () => {
    expect(eventWindow({ id: "x", kind: "key-up", atUs: -5, durationUs: -2, label: "" })).toEqual({
      startUs: 0,
      endUs: 0,
    });
    expect(eventWindow({ id: "y", kind: "key-up", atUs: 10, durationUs: 5, label: "" })).toEqual({
      startUs: 10,
      endUs: 15,
    });
    expect(laneForEvent({ id: "z", kind: "row-strobe", atUs: 0, durationUs: 1, label: "" })).toBe(
      "row:0",
    );
    expect(laneForEvent({ id: "w", kind: "col-strobe", atUs: 0, durationUs: 1, label: "" })).toBe(
      "col:0",
    );
  });

  it("scales time into a plot and guards degenerate inputs", () => {
    expect(scaleTime(5, 10, 100)).toBe(50);
    expect(scaleTime(-5, 10, 100)).toBe(0);
    expect(scaleTime(50, 10, 100)).toBe(100);
    expect(scaleTime(5, 0, 100)).toBe(0);
    expect(scaleTime(5, 10, 0)).toBe(0);
  });

  it("formats microsecond durations for humans", () => {
    expect(formatMicros(250)).toBe("250µs");
    expect(formatMicros(1000)).toBe("1ms");
    expect(formatMicros(1500)).toBe("1.50ms");
  });

  it("lays out bars, lanes and ticks deterministically", () => {
    const model = createDemoScanModel(ATOMC_PAD_MATRIX);
    const layout = layoutTimeline(model, {
      plotWidth: 300,
      laneHeight: 20,
      labelWidth: 100,
      tickCount: 3,
    });
    expect(layout.width).toBe(400);
    expect(layout.height).toBe(140);
    expect(layout.lanes).toHaveLength(7);
    expect(layout.bars).toHaveLength(model.events.length);
    expect(layout.ticks).toHaveLength(4);
    expect(layout.ticks[0]).toMatchObject({ atUs: 0, x: 100, label: "0µs" });
    expect(layout.ticks.at(-1)?.x).toBe(400);
    const firstRow = layout.bars.find((bar) => bar.event.kind === "row-strobe");
    expect(firstRow?.x).toBe(100);
    expect(firstRow?.width).toBeGreaterThan(0);
  });

  it("skips events that map to an unknown lane", () => {
    const model = {
      spec: { rows: 1, cols: 1, rowPins: ["B12"], colPins: ["A0"], diodeDirection: "COL2ROW" },
      durationUs: 100,
      events: [
        {
          id: "ghost",
          kind: "col-strobe" as const,
          atUs: 0,
          durationUs: 10,
          col: 99,
          label: "ghost",
        },
      ],
    };
    const layout = layoutTimeline(model);
    expect(layout.bars).toHaveLength(0);
  });
});

describe("console-stream model", () => {
  it("caps the buffer and records dropped lines", () => {
    const buffer = new ConsoleBuffer(3);
    buffer.appendAll([line({ id: "1" }), line({ id: "2" }), line({ id: "3" }), line({ id: "4" })]);
    expect(buffer.size).toBe(3);
    expect(buffer.lines.map((entry) => entry.id)).toEqual(["2", "3", "4"]);
    expect(buffer.droppedCount).toBe(1);
    expect(buffer.visible(2).map((entry) => entry.id)).toEqual(["3", "4"]);
    expect(buffer.visible()).toHaveLength(3);
    buffer.clear();
    expect(buffer.size).toBe(0);
    expect(buffer.droppedCount).toBe(0);
  });

  it("rejects an invalid limit and uses the documented view limit by default", () => {
    expect(() => new ConsoleBuffer(0)).toThrow(RangeError);
    expect(() => new ConsoleBuffer(1.5)).toThrow(RangeError);
    const buffer = new ConsoleBuffer(CONSOLE_VIEW_LIMIT + 5);
    for (let index = 0; index < CONSOLE_VIEW_LIMIT + 5; index += 1) {
      buffer.append(line({ id: `line-${index}` }));
    }
    expect(buffer.visible()).toHaveLength(CONSOLE_VIEW_LIMIT);
  });

  it("formats valid timestamps and leaves unparsable input alone", () => {
    expect(formatConsoleTimestamp("2026-11-04T10:41:38.000Z")).toBe("10:41:38.000Z");
    expect(formatConsoleTimestamp("not-a-date")).toBe("not-a-date");
  });

  it("produces a deterministic demo console capture", () => {
    const first = createDemoConsoleLines();
    const second = createDemoConsoleLines();
    expect(first).toEqual(second);
    expect(first.length).toBeGreaterThan(5);
    expect(new Set(first.map((entry) => entry.source))).toEqual(
      new Set(["renode", "qmk", "renode-agent"]),
    );
  });
});

describe("telemetry source seam", () => {
  it("returns labeled demo fixtures without touching wall-clock time", async () => {
    const source = createDemoTelemetrySource(ATOMC_PAD_MATRIX);
    expect(source.mode).toBe("demo");
    const bundle = await source.load();
    expect(bundle.notice).toBe(DEMO_TELEMETRY_NOTICE);
    expect(bundle.scan?.spec).toBe(ATOMC_PAD_MATRIX);
    expect(bundle.console.length).toBeGreaterThan(0);
    expect(source.subscribe(() => {})()).toBeUndefined();
  });

  it("reports daemon telemetry as unavailable", async () => {
    const source = createTelemetrySource("daemon");
    expect(source.mode).toBe("daemon");
    const bundle = await source.load();
    expect(bundle.scan).toBeNull();
    expect(bundle.console).toEqual([]);
    expect(bundle.notice).toBe(UNAVAILABLE_TELEMETRY_NOTICE);
    expect(bundle.notice.detail).toMatch(/not exposed by the daemon RPC yet/i);
    expect(createDaemonTelemetrySource().mode).toBe("daemon");
  });
});

describe("ScanTimeline rendering", () => {
  it("exposes the diagram as an image with a text-alternative table", () => {
    const model = createDemoScanModel(ATOMC_PAD_MATRIX);
    render(<ScanTimeline model={model} />);
    const figure = screen.getByRole("img", { name: /matrix scan timing diagram/i });
    expect(figure.tagName.toLowerCase()).toBe("svg");
    const table = screen.getByRole("table", {
      name: /matrix scan event data \(text alternative to the diagram\)/i,
    });
    expect(within(table).getAllByRole("row")).toHaveLength(model.events.length + 1);
    expect(within(table).getAllByRole("columnheader")).toHaveLength(6);
    expect(within(table).getByText("Row 0 selected")).toBeInTheDocument();
    expect(screen.getByText(/Matrix scan · 3×3 · diode direction COL2ROW/)).toBeInTheDocument();
  });
});

describe("ConsoleStream rendering", () => {
  it("renders lines with source badges and a polite live region when unpaused", () => {
    render(
      <ConsoleStream
        lines={[line({ id: "1" }), line({ id: "2", source: "qmk", level: "warn", text: "warn" })]}
        paused={false}
        onTogglePause={() => {}}
        onClear={() => {}}
      />,
    );
    const log = screen.getByRole("log", { name: "Console output" });
    expect(log).toHaveAttribute("aria-live", "polite");
    expect(within(log).getByText("renode")).toBeInTheDocument();
    expect(within(log).getByText("qmk")).toBeInTheDocument();
    expect(within(log).getAllByText("10:41:38.000Z")).toHaveLength(2);
  });

  it("turns announcements off while paused and shows a paused status", () => {
    render(<ConsoleStream lines={[line()]} paused onTogglePause={() => {}} onClear={() => {}} />);
    expect(screen.getByRole("log")).toHaveAttribute("aria-live", "off");
    expect(screen.getByRole("status")).toHaveTextContent(/paused/i);
    expect(screen.getByRole("button", { name: /resume/i })).toHaveAttribute("aria-pressed", "true");
  });

  it("wires pause and clear controls and reports dropped lines", () => {
    const onTogglePause = vi.fn();
    const onClear = vi.fn();
    render(
      <ConsoleStream
        lines={[]}
        paused={false}
        onTogglePause={onTogglePause}
        onClear={onClear}
        droppedCount={1}
      />,
    );
    expect(screen.getByText(/1 earlier line dropped/)).toBeInTheDocument();
    expect(screen.getByText(/No console lines yet/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /pause/i }));
    fireEvent.click(screen.getByRole("button", { name: /clear/i }));
    expect(onTogglePause).toHaveBeenCalledOnce();
    expect(onClear).toHaveBeenCalledOnce();
  });

  it("pluralises dropped lines and accepts a custom empty message", () => {
    render(
      <ConsoleStream
        lines={[]}
        paused={false}
        onTogglePause={() => {}}
        onClear={() => {}}
        droppedCount={4}
        emptyMessage="Unavailable now."
      />,
    );
    expect(screen.getByText(/4 earlier lines dropped/)).toBeInTheDocument();
    expect(screen.getByText("Unavailable now.")).toBeInTheDocument();
  });
});

describe("TelemetryView", () => {
  it("shows the labeled demo capture with timeline and console", async () => {
    render(<TelemetryView mode="demo" />);
    expect(await screen.findByRole("heading", { name: "Telemetry" })).toBeInTheDocument();
    expect(screen.getByText(DEMO_TELEMETRY_NOTICE.label)).toBeInTheDocument();
    expect(screen.getByText("DEMO DATA")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /matrix scan timing diagram/i })).toBeInTheDocument();
    expect(screen.getByRole("log")).toBeInTheDocument();
    expect(screen.getByText("Fixture capture")).toBeInTheDocument();
  });

  it("reports daemon telemetry as unavailable instead of faking a stream", async () => {
    const source = fakeSource({
      scan: null,
      console: [],
      notice: UNAVAILABLE_TELEMETRY_NOTICE,
    });
    render(<TelemetryView mode="daemon" source={source} />);
    const notices = await screen.findAllByText(
      /Matrix-scan and console telemetry are not exposed by the daemon RPC yet/i,
    );
    expect(notices.length).toBeGreaterThanOrEqual(2);
    expect(
      screen.queryByRole("img", { name: /matrix scan timing diagram/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });

  it("freezes new lines while paused and resumes with them buffered", async () => {
    const source = fakeSource({
      scan: createDemoScanModel(ATOMC_PAD_MATRIX),
      console: [line({ id: "seed", text: "seed line" })],
      notice: DEMO_TELEMETRY_NOTICE,
    });
    render(<TelemetryView mode="demo" source={source} />);
    await screen.findByText("seed line");
    act(() => source.emit(line({ id: "live-1", text: "live line one" })));
    expect(screen.getByText("live line one")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /pause/i }));
    act(() => source.emit(line({ id: "live-2", text: "live line two" })));
    expect(screen.queryByText("live line two")).not.toBeInTheDocument();
    expect(screen.getByText(/new lines are buffered but not announced/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /resume/i }));
    expect(screen.getByText("live line two")).toBeInTheDocument();
  });

  it("clears the console and can resubscribe via the seam", async () => {
    const source = fakeSource({
      scan: createDemoScanModel(ATOMC_PAD_MATRIX),
      console: [line({ id: "seed", text: "seed line" })],
      notice: DEMO_TELEMETRY_NOTICE,
    });
    render(<TelemetryView mode="demo" source={source} />);
    await screen.findByText("seed line");
    fireEvent.click(screen.getByRole("button", { name: /clear/i }));
    expect(screen.queryByText("seed line")).not.toBeInTheDocument();
    expect(screen.getByText(/No console lines in this fixture capture/i)).toBeInTheDocument();
    act(() => source.emit(line({ id: "after-clear", text: "after clear" })));
    expect(screen.getByText("after clear")).toBeInTheDocument();
  });

  it("renders a loading status and a recoverable load error", async () => {
    const pending: TelemetrySource = {
      mode: "demo",
      load: () => new Promise<TelemetryBundle>(() => {}),
      subscribe: () => () => {},
    };
    render(<TelemetryView mode="demo" source={pending} />);
    expect(screen.getByRole("status")).toHaveTextContent(/opening telemetry/i);

    cleanup();
    const failing: TelemetrySource = {
      mode: "daemon",
      load: vi.fn().mockRejectedValue(new Error("offline")),
      subscribe: () => () => {},
    };
    render(<TelemetryView mode="daemon" source={failing} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load telemetry/i);
  });

  it("uses the singular demo notice badge for an inconsistent bundle", async () => {
    const source = fakeSource({
      scan: null,
      console: [],
      notice: { kind: "demo", label: "Simulated", detail: "fixture detail" },
    });
    render(<TelemetryView mode="demo" source={source} />);
    await screen.findAllByText("fixture detail");
    expect(screen.getAllByText(/fixture detail/i).length).toBeGreaterThanOrEqual(1);
    expect(
      screen.queryByRole("img", { name: /matrix scan timing diagram/i }),
    ).not.toBeInTheDocument();
  });
});

describe("Studio navigation integration", () => {
  it("exposes telemetry as a nav item reachable from the shell", async () => {
    const { StudioApp } = await import("../src/studio-app.js");
    const { createDemoApi } = await import("../src/model.js");
    render(<StudioApp api={createDemoApi()} demo />);
    const navItem = await screen.findByRole("button", { name: "Telemetry" });
    expect(navItem).toBeInTheDocument();
    fireEvent.click(navItem);
    expect(await screen.findByRole("heading", { name: "Telemetry" })).toBeInTheDocument();
    expect(screen.getByText(DEMO_TELEMETRY_NOTICE.label)).toBeInTheDocument();
  });
});
