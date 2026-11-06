import { useId } from "react";
import {
  formatMicros,
  layoutTimeline,
  type ScanEvent,
  type ScanTimelineModel,
} from "./scan-events.js";

const kindLabels: Record<ScanEvent["kind"], string> = {
  "row-strobe": "Row select",
  "col-strobe": "Column sample",
  "key-down": "Key down",
  "key-up": "Key up",
};

const AXIS_HEIGHT = 24;

export interface ScanTimelineProps {
  model: ScanTimelineModel;
}

/**
 * Hand-rolled, WaveDrom-style SVG timing diagram. The SVG is exposed as a single image
 * with a title/description; the full event list is repeated in a table that serves as the
 * accessible text alternative.
 */
export function ScanTimeline({ model }: ScanTimelineProps) {
  const titleId = useId();
  const descId = useId();
  const layout = layoutTimeline(model);
  const viewBoxHeight = layout.height + AXIS_HEIGHT;

  return (
    <figure className="scan-timeline">
      <svg
        className="scan-timeline__svg"
        viewBox={`0 0 ${layout.width} ${viewBoxHeight}`}
        role="img"
        aria-labelledby={`${titleId} ${descId}`}
        preserveAspectRatio="xMidYMid meet"
      >
        <title id={titleId}>Matrix scan timing diagram</title>
        <desc id={descId}>
          {model.spec.rows} row signals and {model.spec.cols} column signals over{" "}
          {formatMicros(model.durationUs)}, diode direction {model.spec.diodeDirection}. The same
          events are listed in the table titled matrix scan event data.
        </desc>

        {layout.ticks.map((tick) => (
          <g key={tick.x}>
            <line
              className="scan-timeline__grid"
              x1={tick.x}
              x2={tick.x}
              y1={0}
              y2={layout.height}
            />
            <text
              className="scan-timeline__tick"
              x={tick.x}
              y={layout.height + 16}
              textAnchor="middle"
            >
              {tick.label}
            </text>
          </g>
        ))}

        {layout.lanes.map((lane, index) => (
          <g key={lane.id}>
            <line
              className="scan-timeline__lane-rule"
              x1={layout.labelWidth}
              x2={layout.width}
              y1={(index + 1) * layout.laneHeight}
              y2={(index + 1) * layout.laneHeight}
            />
            <text
              className="scan-timeline__lane-label"
              x={layout.labelWidth - 10}
              y={index * layout.laneHeight + layout.laneHeight / 2 + 4}
              textAnchor="end"
            >
              {lane.label}
            </text>
          </g>
        ))}

        {layout.bars.map((bar) => (
          <rect
            key={bar.event.id}
            className={`scan-timeline__bar scan-timeline__bar--${bar.event.kind}`}
            x={bar.x}
            y={bar.y}
            width={bar.width}
            height={bar.height}
            rx={2}
          />
        ))}
      </svg>

      <figcaption className="scan-timeline__caption">
        Matrix scan · {model.spec.rows}×{model.spec.cols} · diode direction{" "}
        {model.spec.diodeDirection} · {formatMicros(model.durationUs)} window
      </figcaption>

      {/* biome-ignore lint/a11y/noNoninteractiveTabindex: scroll region must be keyboard-focusable */}
      <section className="scan-timeline__table-wrap" tabIndex={0} aria-label="Scan events table">
        <table className="scan-timeline__table">
          <caption>Matrix scan event data (text alternative to the diagram)</caption>
          <thead>
            <tr>
              <th scope="col">Start</th>
              <th scope="col">Duration</th>
              <th scope="col">Signal</th>
              <th scope="col">Event</th>
              <th scope="col">Row</th>
              <th scope="col">Col</th>
            </tr>
          </thead>
          <tbody>
            {model.events.map((event) => (
              <tr key={event.id}>
                <td>{Math.round(event.atUs)}µs</td>
                <td>{formatMicros(event.durationUs)}</td>
                <td>{kindLabels[event.kind]}</td>
                <td>{event.label}</td>
                <td>{event.row ?? "—"}</td>
                <td>{event.col ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </figure>
  );
}
