import { CircleHelp, MonitorPlay, TerminalSquare } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { DataMode } from "../model.js";
import { ConsoleStream } from "./ConsoleStream.js";
import { ConsoleBuffer, type ConsoleLine } from "./console-stream.js";
import { ScanTimeline } from "./ScanTimeline.js";
import { createTelemetrySource, type TelemetryBundle, type TelemetrySource } from "./source.js";

export interface TelemetryViewProps {
  mode: DataMode;
  /** Injectable source for tests or a future daemon telemetry adapter. */
  source?: TelemetrySource;
}

export function TelemetryView({ mode, source }: TelemetryViewProps) {
  const activeSource = useMemo(() => source ?? createTelemetrySource(mode), [source, mode]);
  const [bundle, setBundle] = useState<TelemetryBundle>();
  const [error, setError] = useState(false);
  const [buffer] = useState(() => new ConsoleBuffer());
  const [revision, setRevision] = useState(0);
  const [paused, setPaused] = useState(false);
  const [frozen, setFrozen] = useState<readonly ConsoleLine[]>([]);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  useEffect(() => {
    let active = true;
    buffer.clear();
    setBundle(undefined);
    setError(false);
    setPaused(false);
    setFrozen([]);
    void activeSource
      .load()
      .then((loaded) => {
        if (!active) return;
        buffer.clear();
        buffer.appendAll(loaded.console);
        setBundle(loaded);
        setRevision((value) => value + 1);
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [activeSource, buffer]);

  useEffect(() => {
    return activeSource.subscribe((line) => {
      buffer.append(line);
      if (!pausedRef.current) setRevision((value) => value + 1);
    });
  }, [activeSource, buffer]);

  const lines = useMemo(
    () => (paused ? frozen : buffer.visible()),
    [paused, frozen, buffer, revision],
  );

  const togglePause = () => {
    if (paused) {
      setPaused(false);
      return;
    }
    setFrozen([...buffer.lines]);
    setPaused(true);
  };

  const clearConsole = () => {
    buffer.clear();
    setFrozen([]);
    setRevision((value) => value + 1);
  };

  if (error) {
    return (
      <div className="view-stack">
        <div className="view-intro">
          <div>
            <span className="eyebrow">MATRIX &amp; CONSOLE</span>
            <h2>Telemetry</h2>
          </div>
        </div>
        <div className="info-banner" role="alert">
          <CircleHelp size={16} aria-hidden="true" />
          <span>Could not load telemetry from the active source.</span>
        </div>
      </div>
    );
  }

  if (!bundle) {
    return (
      <div className="view-stack">
        <div className="view-intro">
          <div>
            <span className="eyebrow">MATRIX &amp; CONSOLE</span>
            <h2>Telemetry</h2>
          </div>
        </div>
        <p className="telemetry-loading" role="status">
          Opening telemetry…
        </p>
      </div>
    );
  }

  return (
    <div className="view-stack telemetry-view">
      <div className="view-intro">
        <div>
          <span className="eyebrow">MATRIX &amp; CONSOLE</span>
          <h2>Telemetry</h2>
          <p>
            Matrix-scan timing and firmware console output. Every source is labeled; nothing here is
            presented as live unless it is.
          </p>
        </div>
        <span className={`badge ${bundle.scan ? "badge--neutral" : "badge--warning"}`}>
          <MonitorPlay size={13} aria-hidden="true" />
          {bundle.scan ? "Fixture capture" : "Unavailable"}
        </span>
      </div>

      {bundle.notice.kind === "demo" ? (
        <div className="preview-banner">
          <span className="preview-banner__icon">
            <CircleHelp size={15} aria-hidden="true" />
          </span>
          <div>
            <strong>{bundle.notice.label}</strong>
            <span>{bundle.notice.detail}</span>
          </div>
          <span className="preview-banner__tag">DEMO DATA</span>
        </div>
      ) : (
        <div className="info-banner">
          <CircleHelp size={16} aria-hidden="true" />
          <span>
            <strong>{bundle.notice.label}.</strong> {bundle.notice.detail}
          </span>
        </div>
      )}

      {bundle.scan ? (
        <ScanTimeline model={bundle.scan} />
      ) : (
        <section className="panel telemetry-unavailable" aria-label="Matrix scan telemetry">
          <TerminalSquare size={18} aria-hidden="true" />
          <div>
            <strong>Matrix-scan timing unavailable</strong>
            <p>{bundle.notice.detail}</p>
          </div>
        </section>
      )}

      <ConsoleStream
        lines={lines}
        paused={paused}
        onTogglePause={togglePause}
        onClear={clearConsole}
        droppedCount={buffer.droppedCount}
        emptyMessage={
          bundle.notice.kind === "unavailable"
            ? bundle.notice.detail
            : "No console lines in this fixture capture."
        }
      />
    </div>
  );
}
