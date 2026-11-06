import type { GateResult, GateStatus } from "@atomc/daemon-client";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  ShieldCheck,
  X,
} from "lucide-react";
import { Fragment, useId, useMemo, useState } from "react";
import type { DataMode } from "../model.js";
import {
  countBySeverity,
  countByStatus,
  DEFAULT_GATE_FILTER,
  elementIdFor,
  filterGates,
  formatDuration,
  formatTimestamp,
  type GateFilterState,
  type GateGroup,
  gateTitle,
  groupGates,
} from "./derive.js";
import "./board.css";

const SEVERITY_FILTERS: ReadonlyArray<{ id: GateFilterState["severity"]; label: string }> = [
  { id: "all", label: "Any severity" },
  { id: "blocking", label: "Blocking" },
  { id: "advisory", label: "Advisory" },
];

const STATUS_FILTERS: ReadonlyArray<{ id: GateFilterState["status"]; label: string }> = [
  { id: "all", label: "Any result" },
  { id: "PASS", label: "Passed" },
  { id: "FAIL", label: "Failed" },
  { id: "SKIP", label: "Skipped" },
  { id: "ERROR", label: "Error" },
];

const STATUS_LABELS: Record<GateStatus, string> = {
  PASS: "Passed",
  FAIL: "Failed",
  SKIP: "Skipped",
  ERROR: "Error",
};

function StatusPill({ status }: { status: GateStatus }) {
  const Icon =
    status === "PASS"
      ? Check
      : status === "FAIL"
        ? X
        : status === "ERROR"
          ? AlertTriangle
          : ChevronRight;
  return (
    <span className={`status status--${status.toLowerCase()}`}>
      <Icon size={13} strokeWidth={2.4} aria-hidden="true" />
      {STATUS_LABELS[status]}
    </span>
  );
}

function DetailRow({ gate, colSpan }: { gate: GateResult; colSpan: number }) {
  return (
    <tr className="gboard-detail">
      <td colSpan={colSpan}>
        <div className="gboard-detail__grid">
          <div className="gboard-detail__field">
            <span className="gboard-detail__label">Gate id</span>
            <code>{gate.id}</code>
          </div>
          <div className="gboard-detail__field">
            <span className="gboard-detail__label">Plugin</span>
            <code>{gate.plugin}</code>
          </div>
          <div className="gboard-detail__field">
            <span className="gboard-detail__label">IR revision</span>
            <code>r{gate.ir_rev}</code>
          </div>
          <div className="gboard-detail__field">
            <span className="gboard-detail__label">Duration</span>
            <code>{formatDuration(gate.duration_ms)}</code>
          </div>
          <div className="gboard-detail__field">
            <span className="gboard-detail__label">Evaluated</span>
            <code>{formatTimestamp(gate.evaluated_at)}</code>
          </div>
          <div className="gboard-detail__field">
            <span className="gboard-detail__label">Severity</span>
            <span className={`severity severity--${gate.severity}`}>{gate.severity}</span>
          </div>
        </div>
        <p className="gboard-detail__summary">{gate.summary}</p>

        <h4 className="gboard-detail__heading">Evidence</h4>
        {gate.evidence.length === 0 ? (
          <p className="gboard-detail__empty">No evidence recorded for this gate.</p>
        ) : (
          <ul className="gboard-evidence">
            {gate.evidence.map((item, index) => (
              <li key={`${item.kind}-${item.ref ?? item.message ?? index}`}>
                <span className="badge badge--neutral">{item.kind}</span>
                {item.ref !== undefined && <code>{item.ref}</code>}
                {item.message !== undefined && <span>{item.message}</span>}
                {item.data !== undefined && <code>{JSON.stringify(item.data)}</code>}
              </li>
            ))}
          </ul>
        )}

        <h4 className="gboard-detail__heading">Suggestions</h4>
        {gate.suggestions.length === 0 ? (
          <p className="gboard-detail__empty">No suggestions recorded for this gate.</p>
        ) : (
          <ul className="gboard-suggestions">
            {gate.suggestions.map((suggestion, index) => (
              <li key={`${suggestion.message}-${index}`}>
                <span>{suggestion.message}</span>
                {suggestion.patch !== undefined && (
                  <code>
                    {suggestion.patch.path} · {suggestion.patch.ops.length} JSON Patch op(s)
                  </code>
                )}
              </li>
            ))}
          </ul>
        )}

        <h4 className="gboard-detail__heading">Referenced IR ids</h4>
        {gate.refs.length === 0 ? (
          <p className="gboard-detail__empty">This gate does not reference any IR ids.</p>
        ) : (
          <ul className="gboard-refs">
            {gate.refs.map((ref) => (
              <li key={ref}>
                <code>{ref}</code>
              </li>
            ))}
          </ul>
        )}
      </td>
    </tr>
  );
}

function GroupTable({
  group,
  expandedId,
  onToggle,
  idBase,
}: {
  group: GateGroup;
  expandedId: string | null;
  onToggle: (id: string) => void;
  idBase: string;
}) {
  const rows = group.gates;
  const percent = Math.round(group.passRate * 100);
  if (rows.length === 0) {
    return (
      <section className="panel gboard-group" aria-labelledby={`${idBase}-heading`}>
        <GroupHeading group={group} percent={percent} idBase={idBase} />
        <p className="gboard-group__empty">No checks in this group match the active filters.</p>
      </section>
    );
  }
  return (
    <section className="panel gboard-group" aria-labelledby={`${idBase}-heading`}>
      <GroupHeading group={group} percent={percent} idBase={idBase} />
      {group.unowned && (
        <p className="gboard-group__note">
          <CircleHelp size={14} aria-hidden="true" />
          These gates declare no owner_agent, so no specialist is woken automatically. A coordinator
          must review and assign them.
        </p>
      )}
      <table className="gboard-table">
        <caption className="visually-hidden">
          {group.label} gates: {group.passCount} of {group.total} passing
        </caption>
        <thead>
          <tr className="gboard-table__header">
            <th scope="col">GATE</th>
            <th scope="col">RESULT</th>
            <th scope="col">SEVERITY</th>
            <th scope="col">DURATION</th>
            <th scope="col">
              <span className="visually-hidden">Details</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((gate) => {
            const detailId = `${idBase}-${elementIdFor(gate.id)}-details`;
            const open = expandedId === gate.id;
            return (
              <Fragment key={gate.id}>
                <tr className={`gboard-row gboard-row--${gate.status.toLowerCase()}`}>
                  <th scope="row" className="gboard-row__name">
                    <span className="gboard-row__title">{gateTitle(gate)}</span>
                    <code>{gate.id}</code>
                  </th>
                  <td>
                    <StatusPill status={gate.status} />
                  </td>
                  <td>
                    <span className={`severity severity--${gate.severity}`}>{gate.severity}</span>
                  </td>
                  <td>
                    <span className="gboard-duration">
                      <Clock3 size={12} aria-hidden="true" />
                      {formatDuration(gate.duration_ms)}
                    </span>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="button button--quiet gboard-toggle"
                      aria-expanded={open}
                      aria-controls={detailId}
                      onClick={() => onToggle(gate.id)}
                    >
                      {open ? "Hide" : "Details"}
                      <ChevronDown
                        size={14}
                        aria-hidden="true"
                        className={
                          open ? "gboard-toggle__chevron is-open" : "gboard-toggle__chevron"
                        }
                      />
                    </button>
                  </td>
                </tr>
                {open && (
                  <Fragment>
                    <DetailRow gate={gate} colSpan={5} />
                  </Fragment>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

function GroupHeading({
  group,
  percent,
  idBase,
}: {
  group: GateGroup;
  percent: number;
  idBase: string;
}) {
  return (
    <div className="gboard-group__heading">
      <div>
        <div className="panel__eyebrow">{group.unowned ? "UNASSIGNED" : "OWNED DOMAIN"}</div>
        <h3 id={`${idBase}-heading`}>
          {group.label} <span className="heading-count">{group.total}</span>
        </h3>
        <p className="gboard-group__description">{group.description}</p>
      </div>
      <div className="gboard-rate">
        <div className="gboard-rate__label">
          <span>Pass rate</span>
          <strong>
            {group.passCount}/{group.total}
          </strong>
        </div>
        <div
          className="gboard-rate__track"
          role="progressbar"
          aria-label={`${group.label} pass rate`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
        >
          <span style={{ width: `${percent}%` }} />
        </div>
        {group.blockingFailCount > 0 && (
          <span className="gboard-rate__flag">
            <AlertTriangle size={12} aria-hidden="true" />
            {group.blockingFailCount} blocking
          </span>
        )}
      </div>
    </div>
  );
}

export interface GateBoardProps {
  gates: GateResult[];
  dataMode: DataMode;
}

export function GateBoard({ gates, dataMode }: GateBoardProps) {
  const [filter, setFilter] = useState<GateFilterState>(DEFAULT_GATE_FILTER);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const reactId = useId();
  const groups = useMemo(() => groupGates(gates), [gates]);
  const visibleGroups = useMemo(
    () =>
      groups
        .map((group) => ({ ...group, gates: filterGates(group.gates, filter) }))
        .filter((group) => group.gates.length > 0),
    [groups, filter],
  );
  const statusCounts = useMemo(() => countByStatus(gates), [gates]);
  const severityCounts = useMemo(() => countBySeverity(gates), [gates]);
  const visibleCount = visibleGroups.reduce((sum, group) => sum + group.gates.length, 0);
  const blockingFailures = gates.filter(
    (gate) => (gate.status === "FAIL" || gate.status === "ERROR") && gate.severity === "blocking",
  ).length;

  const toggle = (id: string) => setExpandedId((current) => (current === id ? null : id));

  return (
    <div className="view-stack">
      <div className="view-intro">
        <div>
          <span className="eyebrow">QUALITY &amp; SAFETY</span>
          <h2>Gate board</h2>
          <p>
            Every gate result in this snapshot, grouped by its owning specialist domain. Values come
            from real GateResult records — nothing is inferred.
          </p>
        </div>
        <span className={`badge ${blockingFailures > 0 ? "badge--danger" : "badge--neutral"}`}>
          <ShieldCheck size={13} aria-hidden="true" />
          {gates.length} gates
        </span>
      </div>

      {dataMode === "demo" && (
        <div className="info-banner">
          <CircleHelp size={16} aria-hidden="true" />
          <span>
            Preview snapshot: these gate records are simulated fixture data. No plugin evaluated
            this revision.
          </span>
        </div>
      )}

      {gates.length === 0 ? (
        <div className="info-banner">
          <CircleHelp size={16} aria-hidden="true" />
          <span>
            No gate results exist for this project revision. Run the daemon gate runner to populate
            <code> /gates/results</code>.
          </span>
        </div>
      ) : (
        <>
          <section className="panel gboard-filters" aria-labelledby={`${reactId}-filters`}>
            <h3 id={`${reactId}-filters`} className="gboard-filters__title">
              Filter gates
            </h3>
            <fieldset className="gboard-filter-row">
              <legend className="gboard-filter-row__label">Severity</legend>
              <div className="filter-tabs">
                {SEVERITY_FILTERS.map(({ id, label }) => (
                  <button
                    type="button"
                    key={id}
                    className={`filter-tab ${filter.severity === id ? "is-active" : ""}`}
                    aria-pressed={filter.severity === id}
                    onClick={() => setFilter((current) => ({ ...current, severity: id }))}
                  >
                    {label}
                    <span>{severityCounts[id]}</span>
                  </button>
                ))}
              </div>
            </fieldset>
            <fieldset className="gboard-filter-row">
              <legend className="gboard-filter-row__label">Result</legend>
              <div className="filter-tabs">
                {STATUS_FILTERS.map(({ id, label }) => (
                  <button
                    type="button"
                    key={id}
                    className={`filter-tab ${filter.status === id ? "is-active" : ""}`}
                    aria-pressed={filter.status === id}
                    onClick={() => setFilter((current) => ({ ...current, status: id }))}
                  >
                    {label}
                    <span>{id === "all" ? gates.length : statusCounts[id]}</span>
                  </button>
                ))}
              </div>
            </fieldset>
          </section>

          <p className="visually-hidden" role="status" aria-live="polite">
            Showing {visibleCount} of {gates.length} gates across {visibleGroups.length} domains.
          </p>

          {visibleGroups.length === 0 ? (
            <div className="info-banner">
              <CircleHelp size={16} aria-hidden="true" />
              <span>No gates match the active filters. Clear a filter to see more.</span>
            </div>
          ) : (
            visibleGroups.map((group) => (
              <GroupTable
                key={group.domain}
                group={group}
                expandedId={expandedId}
                onToggle={toggle}
                idBase={`${reactId}-${group.domain}`}
              />
            ))
          )}
        </>
      )}
    </div>
  );
}
