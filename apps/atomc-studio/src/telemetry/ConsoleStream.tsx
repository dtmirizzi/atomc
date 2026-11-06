import { Pause, Play, Trash2 } from "lucide-react";
import {
  CONSOLE_BUFFER_LIMIT,
  type ConsoleLine,
  formatConsoleTimestamp,
} from "./console-stream.js";

const sourceLabels: Record<ConsoleLine["source"], string> = {
  renode: "renode",
  qmk: "qmk",
  "renode-agent": "renode-agent",
};

export interface ConsoleStreamProps {
  lines: readonly ConsoleLine[];
  paused: boolean;
  onTogglePause: () => void;
  onClear: () => void;
  droppedCount?: number;
  emptyMessage?: string;
}

/**
 * Append-only console view. The live region only announces new lines while unpaused; when
 * paused the view keeps the frozen snapshot visible and says so. All controls are native
 * buttons, so they are keyboard operable and announced correctly.
 */
export function ConsoleStream({
  lines,
  paused,
  onTogglePause,
  onClear,
  droppedCount = 0,
  emptyMessage = "No console lines yet.",
}: ConsoleStreamProps) {
  const liveProps = {
    role: "log" as const,
    "aria-label": "Console output",
    "aria-live": paused ? ("off" as const) : ("polite" as const),
    "aria-relevant": "additions" as const,
  };
  return (
    <section className="panel console-stream" aria-labelledby="console-stream-heading">
      <div className="console-stream__header">
        <div>
          <div className="panel__eyebrow">FIRMWARE OUTPUT</div>
          <h3 id="console-stream-heading" className="console-stream__title">
            Console stream
          </h3>
        </div>
        <div className="console-stream__controls">
          <button
            type="button"
            className="button button--quiet console-stream__control"
            onClick={onTogglePause}
            aria-pressed={paused}
          >
            {paused ? (
              <Play size={13} aria-hidden="true" />
            ) : (
              <Pause size={13} aria-hidden="true" />
            )}
            {paused ? "Resume" : "Pause"}
          </button>
          <button
            type="button"
            className="button button--quiet console-stream__control"
            onClick={onClear}
          >
            <Trash2 size={13} aria-hidden="true" />
            Clear
          </button>
        </div>
      </div>

      {droppedCount > 0 && (
        <p className="console-stream__dropped">
          {droppedCount} earlier {droppedCount === 1 ? "line" : "lines"} dropped · buffer capped at{" "}
          {CONSOLE_BUFFER_LIMIT}
        </p>
      )}

      {/* biome-ignore lint/a11y/noNoninteractiveTabindex: console log must stay keyboard-scrollable */}
      <div className="console-stream__log" {...liveProps} tabIndex={0}>
        {lines.length === 0 ? (
          <p className="console-stream__empty">{emptyMessage}</p>
        ) : (
          <ol className="console-stream__list">
            {lines.map((line) => (
              <li key={line.id} className={`console-line console-line--${line.level}`}>
                <time className="console-line__time" dateTime={line.at}>
                  {formatConsoleTimestamp(line.at)}
                </time>
                <span className={`source-badge source-badge--${line.source}`}>
                  {sourceLabels[line.source]}
                </span>
                <span className="console-line__text">{line.text}</span>
              </li>
            ))}
          </ol>
        )}
      </div>

      {paused && (
        <p className="console-stream__paused" role="status">
          Paused · new lines are buffered but not announced.
        </p>
      )}
    </section>
  );
}
