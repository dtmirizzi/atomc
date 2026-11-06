import type { GateResult } from "@atomc/daemon-client";
import {
  Activity,
  AlertTriangle,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Box,
  Boxes,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  Code2,
  Cpu,
  FileCode2,
  FolderOpen,
  Gauge,
  GitBranch,
  Grid2X2,
  HardDrive,
  LayoutDashboard,
  LifeBuoy,
  LoaderCircle,
  LockKeyhole,
  type LucideIcon,
  MoreHorizontal,
  PackageCheck,
  PanelLeftClose,
  Play,
  RefreshCw,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  TerminalSquare,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { createDaemonStudioApi } from "./daemon-api.js";
import type {
  ActivityItem,
  AgentCard,
  BoardSnapshot,
  DagNode,
  RunState,
  StudioApi,
  TelemetryNotice,
} from "./model.js";
import { createDemoApi } from "./model.js";
import { TelemetryView } from "./telemetry/TelemetryView.js";
import { Viewer3DView } from "./viewer3d/Viewer3DView.js";

type ViewId =
  | "overview"
  | "pipeline"
  | "gates"
  | "agents"
  | "artifacts"
  | "viewer3d"
  | "telemetry";
type GateFilter = "all" | "failed" | "passed" | "skipped";

const navItems: Array<{ id: ViewId; label: string; icon: LucideIcon; count?: string }> = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "pipeline", label: "Build graph", icon: GitBranch },
  { id: "gates", label: "Gate results", icon: ShieldCheck, count: "1" },
  { id: "agents", label: "Agent team", icon: Sparkles },
  { id: "artifacts", label: "Artifacts", icon: Boxes },
  { id: "viewer3d", label: "3D viewer", icon: Box },
  { id: "telemetry", label: "Telemetry", icon: TerminalSquare },
];

const stateLabels: Record<RunState, string> = {
  idle: "Idle",
  queued: "Queued",
  running: "Running",
  passed: "Passed",
  failed: "Failed",
  stale: "Stale",
};

const gateTitles: Record<string, string> = {
  "erc.no_unconnected": "Unconnected pins",
  "fw.qmk_compile": "QMK firmware compile",
  "fw.matrix_scan": "Matrix scan pin map",
  "layout.testpads.nets_covered": "Test-pad net coverage",
  "mech.plate_switch_cutouts_14mm": "Switch plate cutouts",
  "bom.all_in_stock": "BOM availability",
};

function gateTitle(gate: GateResult): string {
  return gateTitles[gate.id] ?? gate.id.replace(/^gate:/, "").replaceAll(".", " ");
}

function GateStatus({ status }: { status: GateResult["status"] }) {
  const Icon =
    status === "PASS"
      ? Check
      : status === "FAIL"
        ? X
        : status === "ERROR"
          ? AlertTriangle
          : status === "SKIP"
            ? ChevronRight
            : LoaderCircle;
  return (
    <span className={`status status--${status.toLowerCase()}`}>
      <Icon size={13} strokeWidth={2.4} aria-hidden="true" />
      {status === "ERROR"
        ? "Error"
        : status === "SKIP"
          ? "Skipped"
          : status === "PASS"
            ? "Passed"
            : status === "FAIL"
              ? "Failed"
              : "Running"}
    </span>
  );
}

function NodeStatus({ state }: { state: RunState }) {
  return (
    <span className={`node-state node-state--${state}`}>
      {state === "passed" && <Check size={12} aria-hidden="true" />}
      {state === "running" && <LoaderCircle size={12} className="spin" aria-hidden="true" />}
      {stateLabels[state]}
    </span>
  );
}

function Avatar({ agent }: { agent: AgentCard }) {
  return (
    <span className={`avatar avatar--${agent.tint}`} aria-hidden="true">
      {agent.initials}
    </span>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
  detail,
  tone = "default",
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail: string;
  tone?: "default" | "danger" | "success";
}) {
  return (
    <div className={`metric metric--${tone}`}>
      <span className="metric__icon">
        <Icon size={16} aria-hidden="true" />
      </span>
      <div className="metric__copy">
        <span className="metric__label">{label}</span>
        <strong className="metric__value">{value}</strong>
        <span className="metric__detail">{detail}</span>
      </div>
    </div>
  );
}

function Pipeline({ nodes, onSelect }: { nodes: DagNode[]; onSelect: (node: DagNode) => void }) {
  return (
    <fieldset className="pipeline">
      <legend className="visually-hidden">Build pipeline nodes</legend>
      {nodes.map((node) => {
        const Icon = nodeIcon(node.plugin);
        return (
          <div className="pipeline__segment" key={node.id}>
            <button
              type="button"
              className={`pipeline-node pipeline-node--${node.state}`}
              onClick={() => onSelect(node)}
            >
              <span className="pipeline-node__top">
                <span className="pipeline-node__icon">
                  <Icon size={17} aria-hidden="true" />
                </span>
                <MoreHorizontal size={16} className="muted-icon" aria-hidden="true" />
              </span>
              <span className="pipeline-node__name">
                {node.id.split(".").slice(1).join(" ") || node.id}
              </span>
              <span className="pipeline-node__plugin">{node.plugin}</span>
              <span className="pipeline-node__bottom">
                <NodeStatus state={node.state} />
                {node.durationMs !== undefined && (
                  <span className="node-duration">{formatDuration(node.durationMs)}</span>
                )}
              </span>
            </button>
          </div>
        );
      })}
    </fieldset>
  );
}

function nodeIcon(plugin: string): LucideIcon {
  if (plugin === "qmk" || plugin === "renode") return Cpu;
  if (plugin === "cad-jig") return Grid2X2;
  if (plugin === "sourcing") return PackageCheck;
  return Code2;
}

function formatDuration(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

function GateTable({
  gates,
  filter,
  setFilter,
  onSelect,
  compact = false,
}: {
  gates: GateResult[];
  filter: GateFilter;
  setFilter: (filter: GateFilter) => void;
  onSelect: (gate: GateResult) => void;
  compact?: boolean;
}) {
  const counts = {
    all: gates.length,
    failed: gates.filter((gate) => gate.status === "FAIL" || gate.status === "ERROR").length,
    passed: gates.filter((gate) => gate.status === "PASS").length,
    skipped: gates.filter((gate) => gate.status === "SKIP").length,
  };
  const filtered = gates.filter((gate) => {
    if (filter === "failed") return gate.status === "FAIL" || gate.status === "ERROR";
    if (filter === "passed") return gate.status === "PASS";
    if (filter === "skipped") return gate.status === "SKIP";
    return true;
  });
  const filters: Array<{ id: GateFilter; label: string }> = [
    { id: "all", label: "All checks" },
    { id: "failed", label: "Failed" },
    { id: "passed", label: "Passed" },
    { id: "skipped", label: "Skipped" },
  ];
  return (
    <section
      className={`panel gates-panel ${compact ? "gates-panel--compact" : ""}`}
      aria-labelledby="gates-heading"
    >
      <div className="panel__heading">
        <div>
          <div className="panel__eyebrow">VERIFICATION</div>
          <h2 id="gates-heading">
            Gate results <span className="heading-count">{gates.length}</span>
          </h2>
        </div>
        <button
          type="button"
          className="icon-button"
          aria-label="Gate view options"
          title="Gate view options"
        >
          <SlidersHorizontal size={16} />
        </button>
      </div>
      <div className="filter-tabs" role="tablist" aria-label="Filter gate results">
        {filters.map(({ id, label }) => (
          <button
            type="button"
            key={id}
            className={`filter-tab ${filter === id ? "is-active" : ""}`}
            onClick={() => setFilter(id)}
            role="tab"
            aria-selected={filter === id}
          >
            {label}
            <span>{counts[id]}</span>
          </button>
        ))}
      </div>
      <table className="gate-table" aria-label="Verification gates">
        <thead>
          <tr className="gate-table__header">
            <th scope="col">CHECK</th>
            <th scope="col">RESULT</th>
            <th scope="col">OWNER</th>
            <th scope="col">DETAIL</th>
          </tr>
        </thead>
        <tbody>
          {filtered.length === 0 ? (
            <tr>
              <td className="empty-state" colSpan={4}>
                No checks in this filter.
              </td>
            </tr>
          ) : (
            filtered.slice(0, compact ? 5 : undefined).map((gate) => (
              <tr className={`gate-row gate-row--${gate.status.toLowerCase()}`} key={gate.id}>
                <td>
                  <button className="gate-row__button" type="button" onClick={() => onSelect(gate)}>
                    <span className="gate-row__name">
                      <span
                        className={`gate-dot gate-dot--${gate.status.toLowerCase()}`}
                        aria-hidden="true"
                      />
                      {gateTitle(gate)}
                    </span>
                    <span>
                      <GateStatus status={gate.status} />
                    </span>
                    <span className="gate-owner">
                      <Avatar agent={agentFor(gate.owner_agent)} />
                      <span>{agentFor(gate.owner_agent).label}</span>
                    </span>
                    <span className="gate-summary">
                      {gate.summary}
                      <ChevronRight size={14} aria-hidden="true" />
                    </span>
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
      {compact && (
        <button
          className="panel-link"
          type="button"
          onClick={() =>
            window.dispatchEvent(new CustomEvent("atomc:navigate", { detail: "gates" }))
          }
        >
          View all checks <ArrowRight size={14} />
        </button>
      )}
    </section>
  );
}

function agentFor(id: string | null): AgentCard {
  const idOrDefault = id ?? "ee-agent";
  const details: Record<string, { label: string; initials: string; tint: string }> = {
    "ee-agent": { label: "Electrical", initials: "EE", tint: "violet" },
    "fw-agent": { label: "Firmware", initials: "FW", tint: "cyan" },
    "mech-agent": { label: "Mechanical", initials: "ME", tint: "amber" },
    "ops-agent": { label: "Supply chain", initials: "SC", tint: "green" },
  };
  const display = details[idOrDefault] ?? { label: idOrDefault, initials: "?", tint: "violet" };
  return {
    id: idOrDefault as AgentCard["id"],
    label: display.label,
    initials: display.initials,
    specialty: "Hardware",
    state: "idle",
    task: "Ready",
    spentCents: 0,
    capCents: 1,
    tint: display.tint,
  };
}

function GateDetail({
  gate,
  close,
  isDemo,
}: {
  gate: GateResult;
  close: () => void;
  isDemo: boolean;
}) {
  const agent = agentFor(gate.owner_agent);
  return (
    <div className="scrim">
      <div className="scrim-dismiss" />
      <section
        className="detail-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={gateTitle(gate)}
        aria-labelledby="detail-title"
      >
        <div className="drawer-top">
          <span className="drawer-label">GATE DETAIL</span>
          <button
            type="button"
            className="icon-button"
            onClick={close}
            aria-label="Close gate details"
          >
            <X size={18} />
          </button>
        </div>
        <GateStatus status={gate.status} />
        <h2 id="detail-title">{gateTitle(gate)}</h2>
        <p className="drawer-summary">{gate.summary}</p>
        <div className="drawer-meta">
          <span>Gate ID</span>
          <code>{gate.id}</code>
          <span>Owner</span>
          <span className="gate-owner">
            <Avatar agent={agent} />
            {agent.label}
          </span>
          <span>IR revision</span>
          <code>r{gate.ir_rev}</code>
          <span>Severity</span>
          <span className={`severity severity--${gate.severity}`}>{gate.severity}</span>
        </div>
        {gate.status === "FAIL" && (
          <div className="suggestion-card">
            <span className="suggestion-card__icon">
              <Sparkles size={15} />
            </span>
            <div>
              <strong>Assigned to {agent.label}</strong>
              <p>The owning specialist can inspect the evidence and propose an IR-scoped fix.</p>
            </div>
          </div>
        )}
        <div className="drawer-actions">
          <button
            type="button"
            className="button button--primary"
            disabled
            title="Agent wake controls will be enabled with WP-3.4 convergence orchestration."
          >
            <Sparkles size={15} />
            Wake specialist (planned)
          </button>
          <button type="button" className="button button--quiet" onClick={close}>
            Close
          </button>
        </div>
        {isDemo && (
          <p className="drawer-footnote">
            Preview data only. Connect a local daemon to start an agent run.
          </p>
        )}
      </section>
    </div>
  );
}

function ActivityFeed({ items, compact = false }: { items: ActivityItem[]; compact?: boolean }) {
  return (
    <section className="panel activity-panel" aria-labelledby="activity-heading">
      <div className="panel__heading">
        <div>
          <div className="panel__eyebrow">RUN HISTORY</div>
          <h2 id="activity-heading">Recent activity</h2>
        </div>
        <button type="button" className="icon-button" aria-label="Activity options">
          <MoreHorizontal size={17} />
        </button>
      </div>
      <ol className="activity-list">
        {items.slice(0, compact ? 4 : undefined).map((item) => (
          <li className="activity-item" key={item.id}>
            <span className={`activity-marker activity-marker--${item.tone}`} aria-hidden="true">
              <Activity size={12} />
            </span>
            <div className="activity-item__content">
              <strong>{item.title}</strong>
              <p>{item.detail}</p>
            </div>
            <time>{item.time}</time>
          </li>
        ))}
      </ol>
    </section>
  );
}

function AgentTeam({
  agents,
  isDemo,
  compact = false,
}: {
  agents: AgentCard[];
  isDemo: boolean;
  compact?: boolean;
}) {
  return (
    <section className="panel agents-panel" aria-labelledby="agents-heading">
      <div className="panel__heading">
        <div>
          <div className="panel__eyebrow">AUTONOMOUS TEAM</div>
          <h2 id="agents-heading">
            Specialists{" "}
            <span className="heading-count">
              {agents.filter((agent) => agent.state === "working").length} active
            </span>
          </h2>
        </div>
        <button
          type="button"
          className="icon-button"
          aria-label="Specialist settings"
          title="Specialist settings"
        >
          <Settings2 size={16} />
        </button>
      </div>
      <div className="agent-list">
        {agents.slice(0, compact ? 3 : undefined).map((agent) => {
          const spend = Math.min(100, (agent.spentCents / Math.max(1, agent.capCents)) * 100);
          return (
            <article className={`agent-card agent-card--${agent.state}`} key={agent.id}>
              <Avatar agent={agent} />
              <div className="agent-card__main">
                <div className="agent-card__title">
                  <strong>{agent.label}</strong>
                  <span className={`agent-state agent-state--${agent.state}`}>
                    <span />
                    {agent.state}
                  </span>
                </div>
                <span className="agent-card__specialty">{agent.specialty}</span>
                <p>{agent.task}</p>
                <div className="spend-row">
                  <span>Session spend</span>
                  <span>
                    ${(agent.spentCents / 100).toFixed(2)}{" "}
                    <span className="spend-cap">/ ${(agent.capCents / 100).toFixed(2)}</span>
                  </span>
                </div>
                <div
                  className="spend-track"
                  role="progressbar"
                  aria-label={`${agent.label} session spend`}
                  aria-valuemin={0}
                  aria-valuemax={agent.capCents}
                  aria-valuenow={agent.spentCents}
                >
                  <span style={{ width: `${spend}%` }} />
                </div>
              </div>
            </article>
          );
        })}
      </div>
      {isDemo && (
        <div className="demo-note">
          <CircleHelp size={14} />
          Demo run data · no model calls or spend occurred
        </div>
      )}
    </section>
  );
}

function PipelineView({
  nodes,
  onSelect,
  revision,
}: {
  nodes: DagNode[];
  onSelect: (node: DagNode) => void;
  revision: number;
}) {
  const anyRunning = nodes.some((node) => node.state === "running");
  const anyQueued = nodes.some((node) => node.state === "queued");
  const pipelineState = anyRunning
    ? "In progress"
    : anyQueued
      ? "Queued"
      : nodes.length > 0
        ? "Idle"
        : "No nodes";
  return (
    <div className="view-stack">
      <div className="view-intro">
        <div>
          <span className="eyebrow">BUILD GRAPH</span>
          <h2>Build pipeline</h2>
          <p>Execution state of DAG nodes in this snapshot. Dependency edges are not included.</p>
        </div>
        <span className="badge badge--neutral">
          <GitBranch size={14} />
          {nodes.length} nodes
        </span>
      </div>
      <section className="panel pipeline-panel">
        <div className="panel__heading">
          <div>
            <div className="panel__eyebrow">DAG NODES · IR REVISION {revision}</div>
            <h2>Hardware compile graph</h2>
          </div>
          <span className={`badge ${anyRunning ? "badge--warning" : "badge--neutral"}`}>
            <LoaderCircle size={13} className={anyRunning ? "spin" : undefined} />
            {pipelineState}
          </span>
        </div>
        <Pipeline nodes={nodes} onSelect={onSelect} />
      </section>
      <div className="node-grid">
        {nodes.map((node) => (
          <button
            type="button"
            className="node-detail-card"
            key={node.id}
            onClick={() => onSelect(node)}
          >
            <div className="node-detail-card__top">
              <span className="node-detail-card__icon">
                <Cpu size={16} />
              </span>
              <NodeStatus state={node.state} />
            </div>
            <strong>{node.id}</strong>
            <span className="node-detail-card__description">
              {node.plugin} kernel ·{" "}
              {node.durationMs ? formatDuration(node.durationMs) : "Not started"}
            </span>
          </button>
        ))}
      </div>
      <div className="info-banner">
        <LockKeyhole size={16} />
        <span>
          Each DAG node runs against a content-hashed IR revision. A failed gate wakes only its
          owning specialist.
        </span>
      </div>
    </div>
  );
}

function AgentsView({
  agents,
  isDemo,
  telemetry,
}: {
  agents: AgentCard[];
  isDemo: boolean;
  telemetry: TelemetryNotice;
}) {
  return (
    <div className="view-stack">
      <div className="view-intro">
        <div>
          <span className="eyebrow">SWARM RUNTIME</span>
          <h2>Specialist agents</h2>
          <p>Scoped agents work on owned IR subtrees, under spend and turn limits.</p>
        </div>
        <span className="badge badge--neutral">
          <LockKeyhole size={13} />
          Scoped access
        </span>
      </div>
      <div className={"info-banner"}>
        <CircleHelp size={16} />
        <span>
          <strong>{telemetry.label}.</strong> {telemetry.detail}
        </span>
      </div>
      <AgentTeam agents={agents} isDemo={isDemo} />
      <div className="agent-principles">
        <article>
          <ShieldCheck size={18} />
          <strong>Gate-driven</strong>
          <p>Only daemon gate results can make a run pass.</p>
        </article>
        <article>
          <LockKeyhole size={18} />
          <strong>Transactional</strong>
          <p>Subtree locks and revision checks protect concurrent changes.</p>
        </article>
        <article>
          <Gauge size={18} />
          <strong>Budgeted</strong>
          <p>Turn, token and cost caps are enforced per agent run.</p>
        </article>
      </div>
    </div>
  );
}

function ArtifactView({
  nodes,
  isDemo,
  revision,
}: {
  nodes: DagNode[];
  isDemo: boolean;
  revision: number;
}) {
  const artifacts = nodes.filter((node) => (node.artifactCount ?? 0) > 0);
  return (
    <div className="view-stack">
      <div className="view-intro">
        <div>
          <span className="eyebrow">BUILD OUTPUTS</span>
          <h2>Artifacts</h2>
          <p>Generated files associated with the current IR revision.</p>
        </div>
        <span className="badge badge--neutral">
          <HardDrive size={14} />
          IR r{revision}
        </span>
      </div>
      {isDemo && (
        <div className="info-banner">
          <CircleHelp size={16} />
          Fixture entries only; no files have been generated by this preview.
        </div>
      )}
      {!isDemo && artifacts.length === 0 && (
        <div className="info-banner">
          <CircleHelp size={16} />
          The daemon RPC does not report per-node artifacts; this list stays empty until it does.
        </div>
      )}
      <div className="artifact-list">
        {artifacts.map((node) => (
          <article className="artifact-row" key={node.id}>
            <span className="artifact-icon">
              <FileCode2 size={18} />
            </span>
            <div className="artifact-copy">
              <strong>{node.id} output</strong>
              <span>
                {node.plugin} · {node.id} · IR revision {revision}
              </span>
            </div>
            <span className="artifact-size">{node.artifactCount} files</span>
            <button
              type="button"
              className="icon-button"
              aria-label={`Download ${node.id} output`}
              disabled
            >
              <ArrowDownToLine size={16} />
            </button>
          </article>
        ))}
      </div>
      <div className="empty-artifacts">
        <PackageCheck size={19} />
        <strong>{artifacts.length} artifact groups in this snapshot</strong>
        <span>CAD exports and sourcing reports appear here when their DAG nodes complete.</span>
      </div>
    </div>
  );
}

function Overview({
  snapshot,
  gateFilter,
  setGateFilter,
  onGateSelect,
  onNodeSelect,
  navigate,
  isDemo,
  onBuild,
}: {
  snapshot: BoardSnapshot;
  gateFilter: GateFilter;
  setGateFilter: (filter: GateFilter) => void;
  onGateSelect: (gate: GateResult) => void;
  onNodeSelect: (node: DagNode) => void;
  navigate: (view: ViewId) => void;
  isDemo: boolean;
  onBuild: () => void;
}) {
  const failed = snapshot.gates.filter(
    (gate) => gate.status === "FAIL" || gate.status === "ERROR",
  ).length;
  const passed = snapshot.gates.filter((gate) => gate.status === "PASS").length;
  const running = snapshot.nodes.filter((node) => node.state === "running").length;
  return (
    <>
      <div className="welcome-row">
        <div>
          <span className="eyebrow">
            PROJECT OVERVIEW <span className="eyebrow-sep">/</span> IR r{snapshot.revision}
          </span>
          <h1>
            Good morning, engineer<span className="title-dot">.</span>
          </h1>
          <p>
            Here’s the current health of <strong>{snapshot.projectName}</strong>.
          </p>
        </div>
        <div className="welcome-actions">
          <button
            type="button"
            className="button button--quiet"
            onClick={() => navigate("pipeline")}
          >
            <GitBranch size={15} />
            Build graph
          </button>
          <button
            type="button"
            className="button button--primary"
            onClick={onBuild}
            disabled={isDemo}
            title={isDemo ? "Connect a local daemon to run a real build" : "Start a hardware build"}
          >
            <Play size={15} fill="currentColor" />
            Run build
          </button>
        </div>
      </div>
      {isDemo && (
        <div className="preview-banner">
          <span className="preview-banner__icon">
            <CircleHelp size={15} />
          </span>
          <div>
            <strong>Preview workspace</strong>
            <span>
              This fixture shows the Studio interface. It is not connected to a daemon; no build or
              model run has occurred.
            </span>
          </div>
          <span className="preview-banner__tag">DEMO DATA</span>
        </div>
      )}
      <section className="metrics-grid" aria-label="Project summary">
        <Metric
          icon={ShieldCheck}
          label="Gate health"
          value={`${passed} / ${snapshot.gates.length}`}
          detail={
            failed ? `${failed} blocking issue needs attention` : "All blocking checks passed"
          }
          tone={failed ? "danger" : "success"}
        />
        <Metric
          icon={GitBranch}
          label="Build pipeline"
          value={`${running} running`}
          detail={`${snapshot.nodes.filter((n) => n.state === "passed").length} of ${snapshot.nodes.length} nodes complete`}
        />
        <Metric
          icon={Sparkles}
          label="Active specialists"
          value={`${snapshot.agents.filter((a) => a.state === "working").length} of ${snapshot.agents.length}`}
          detail="Spend limits enforced per run"
        />
        <Metric
          icon={Clock3}
          label="Last build"
          value={snapshot.lastBuild}
          detail={`IR revision ${snapshot.revision}`}
        />
      </section>
      {failed > 0 && (
        <button type="button" className="issue-banner" onClick={() => navigate("gates")}>
          <span className="issue-banner__icon">
            <AlertTriangle size={17} />
          </span>
          <span>
            <strong>{failed} gate needs attention</strong>
            <small>{snapshot.gates.find((gate) => gate.status === "FAIL")?.summary}</small>
          </span>
          <span className="issue-banner__link">
            Review issue <ArrowRight size={14} />
          </span>
        </button>
      )}
      <section className="panel pipeline-panel">
        <div className="panel__heading">
          <div>
            <div className="panel__eyebrow">LATEST BUILD · IR REVISION {snapshot.revision}</div>
            <h2>
              Hardware pipeline{" "}
              <span className="heading-subtle">· {snapshot.nodes.length} nodes</span>
            </h2>
          </div>
          <button type="button" className="text-button" onClick={() => navigate("pipeline")}>
            Open graph <ArrowUpRight size={14} />
          </button>
        </div>
        <Pipeline nodes={snapshot.nodes} onSelect={onNodeSelect} />
      </section>
      <div className="content-grid">
        <GateTable
          gates={snapshot.gates}
          filter={gateFilter}
          setFilter={setGateFilter}
          onSelect={onGateSelect}
          compact
        />
        <div className="right-stack">
          <AgentTeam agents={snapshot.agents} isDemo={isDemo} compact />
          <ActivityFeed items={snapshot.activity} compact />
        </div>
      </div>
    </>
  );
}

function formatUpdated(date: Date): string {
  return new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit" }).format(date);
}

export interface StudioAppProps {
  api?: StudioApi;
  demo?: boolean;
}

function defaultStudioProps(): { api: StudioApi; demo: boolean } {
  const params = new URLSearchParams(window.location.search);
  if (params.get("demo") !== "false") return { api: createDemoApi(), demo: true };

  const projectName = params.get("project") ?? "atomc-project";
  const projectPath = params.get("path") ?? ".";
  const bridge = window.atomcStudioHost;
  if (!bridge) {
    const api: StudioApi = {
      async load() {
        throw new Error(
          "No trusted Studio host is connected. Embed Studio with window.atomcStudioHost.connectDaemon().",
        );
      },
      async runBuild() {
        throw new Error("No trusted Studio host is connected.");
      },
    };
    return { api, demo: false };
  }

  const configuredUrl = params.get("rpc") ?? "ws://127.0.0.1:7437/rpc";
  return {
    api: createDaemonStudioApi({
      projectName,
      projectPath,
      url: configuredUrl,
      clientFactory: (url) => bridge.connectDaemon({ url }),
    }),
    demo: false,
  };
}

export function StudioApp(props: StudioAppProps) {
  const defaults = useMemo(defaultStudioProps, []);
  const api = props.api ?? defaults.api;
  const demo = props.demo ?? defaults.demo;
  const [snapshot, setSnapshot] = useState<BoardSnapshot>();
  const [activeView, setActiveView] = useState<ViewId>("overview");
  const [gateFilter, setGateFilter] = useState<GateFilter>("all");
  const [selectedGate, setSelectedGate] = useState<GateResult>();
  const [selectedNode, setSelectedNode] = useState<DagNode>();
  const [toast, setToast] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [updatedAt, setUpdatedAt] = useState(new Date());
  const [loadError, setLoadError] = useState(false);
  const isDemo = demo;

  const refresh = useCallback(async () => {
    try {
      setSnapshot(await api.load());
      setLoadError(false);
      setUpdatedAt(new Date());
    } catch {
      setLoadError(true);
      setToast("Could not load project state. Check the local daemon connection.");
    }
  }, [api]);

  useEffect(() => {
    void refresh();
  }, [refresh]);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 4200);
    return () => window.clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    const handler = (event: Event) => {
      const view = (event as CustomEvent<ViewId>).detail;
      if (view) setActiveView(view);
    };
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSelectedGate(undefined);
        setSelectedNode(undefined);
        setMobileMenuOpen(false);
      }
    };
    window.addEventListener("atomc:navigate", handler);
    window.addEventListener("keydown", dismiss);
    return () => {
      window.removeEventListener("atomc:navigate", handler);
      window.removeEventListener("keydown", dismiss);
    };
  }, []);

  const currentNav = navItems.find((item) => item.id === activeView) ?? navItems[0];
  if (!currentNav) throw new Error(`Unknown Studio view: ${activeView}`);
  const filteredCount = snapshot?.gates.length ?? 0;

  const handleBuild = async () => {
    if (isDemo) {
      setToast("Preview mode: no daemon is connected, so no build was started.");
      return;
    }
    try {
      setSnapshot(await api.runBuild());
      setToast("Build request sent to the daemon.");
    } catch {
      setToast("Build could not start. Check daemon status and try again.");
    }
  };

  const selectNode = (node: DagNode) => {
    setSelectedNode(node);
    const linkedGate = snapshot?.gates.find((gate) =>
      gate.id.includes(node.id.split(".")[0] ?? ""),
    );
    if (linkedGate) setSelectedGate(linkedGate);
    else setToast(`${node.id} · ${stateLabels[node.state]}`);
  };

  if (!snapshot) {
    return (
      <main className="loading-screen" role={loadError ? "alert" : "status"}>
        <span className="brand-mark">
          <Cpu size={19} />
        </span>
        <span>{loadError ? "Could not load project state." : "Opening project workspace…"}</span>
        {loadError && (
          <button type="button" className="button button--quiet" onClick={() => void refresh()}>
            Retry connection
          </button>
        )}
      </main>
    );
  }

  return (
    <div
      className={`studio-shell ${sidebarCollapsed ? "studio-shell--collapsed" : ""} ${mobileMenuOpen ? "studio-shell--mobile-open" : ""}`}
    >
      {mobileMenuOpen && (
        <button
          type="button"
          className="mobile-scrim"
          onClick={() => setMobileMenuOpen(false)}
          aria-label="Close navigation"
        />
      )}
      <aside className="sidebar" aria-label="Studio navigation">
        <div className="brand-lockup">
          <span className="brand-mark">
            <Cpu size={19} strokeWidth={2.2} />
          </span>
          <span className="brand-name">
            atomc<span>studio</span>
          </span>
          <button
            type="button"
            className="sidebar-collapse"
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          >
            <PanelLeftClose size={16} />
          </button>
        </div>
        <button type="button" className="project-switcher">
          <span className="project-avatar" aria-hidden="true">
            K
          </span>
          <span className="project-switcher__text">
            <strong>{snapshot.projectName}</strong>
            <small>Local workspace</small>
          </span>
          <ChevronDown size={15} aria-hidden="true" />
        </button>
        <div className="sidebar-label">WORKSPACE</div>
        <nav className="primary-nav" aria-label="Project views">
          {navItems.map(({ id, label, icon: Icon, count }) => (
            <button
              type="button"
              key={id}
              className={`nav-item ${activeView === id ? "is-active" : ""}`}
              onClick={() => {
                setActiveView(id);
                setMobileMenuOpen(false);
              }}
              aria-current={activeView === id ? "page" : undefined}
              title={sidebarCollapsed ? label : undefined}
            >
              <Icon size={17} />
              <span>{label}</span>
              {count && <span className="nav-count">{count}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-label sidebar-label--spaced">PROJECT</div>
        <nav className="secondary-nav" aria-label="Project tools">
          <button
            type="button"
            className="nav-item"
            onClick={() => setToast("Project files are available in the local workspace.")}
          >
            <FolderOpen size={16} />
            <span>Source files</span>
          </button>
          <button
            type="button"
            className="nav-item"
            onClick={() => setToast("Terminal integration is planned for a future Studio release.")}
          >
            <TerminalSquare size={16} />
            <span>Terminal</span>
            <span className="nav-soon">SOON</span>
          </button>
        </nav>
        <div className="sidebar-bottom">
          <div className="connection-card">
            <span className={`connection-light connection-light--${snapshot.connection}`} />
            <span className="connection-card__text">
              <strong>
                {snapshot.connection === "connected" ? "Daemon connected" : "Daemon offline"}
              </strong>
              <small>{isDemo ? "Preview mode" : snapshot.connection}</small>
            </span>
            <button
              type="button"
              className="icon-button connection-help"
              aria-label="Daemon connection details"
              onClick={() =>
                setToast(
                  isDemo
                    ? "Preview mode uses fixture data. Connect from the local atomc Studio host."
                    : "Daemon connection details.",
                )
              }
            >
              <CircleHelp size={15} />
            </button>
          </div>
          <button
            type="button"
            className="nav-item sidebar-settings"
            onClick={() => setToast("Studio settings will be available once connected.")}
          >
            <Settings2 size={16} />
            <span>Settings</span>
          </button>
          <div className="user-profile">
            <span className="user-avatar">D</span>
            <span>
              <strong>Developer</strong>
              <small>Local session</small>
            </span>
            <MoreHorizontal size={16} />
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumbs">
            <span>atomc</span>
            <ChevronRight size={14} />
            <strong>{snapshot.projectName}</strong>
            <ChevronRight size={14} />
            <span>{currentNav.label}</span>
          </div>
          <div className="topbar__actions">
            <span className={`connection-pill connection-pill--${snapshot.connection}`}>
              <span />
              {snapshot.connection === "connected" ? "Connected" : "Offline"}
            </span>
            <span className="topbar-divider" />
            <span className="updated-label">Updated {formatUpdated(updatedAt)}</span>
            <button
              type="button"
              className="icon-button topbar-refresh"
              aria-label="Refresh project snapshot"
              onClick={() => void refresh()}
            >
              <RefreshCw size={15} />
            </button>
            <button
              type="button"
              className="icon-button"
              aria-label="Help and support"
              onClick={() => setToast("Visit dtmirizzi.github.io/atomc for docs and guides.")}
            >
              <LifeBuoy size={16} />
            </button>
            <span className="topbar-user">D</span>
          </div>
        </header>
        <div className="main-scroll">
          <div className="workspace-content">
            <div className="page-toolbar">
              <div className="breadcrumbs-mobile">
                {snapshot.projectName} <ChevronRight size={13} /> {currentNav.label}
              </div>
              <div className="project-path">
                <FolderOpen size={13} />
                {snapshot.projectPath}
              </div>
              <button
                type="button"
                className="text-button"
                onClick={() =>
                  setToast("Open a local project from the atomc CLI with `atomc studio`.")
                }
              >
                <FolderOpen size={14} />
                Open project
              </button>
            </div>
            {activeView === "overview" && (
              <Overview
                snapshot={snapshot}
                gateFilter={gateFilter}
                setGateFilter={setGateFilter}
                onGateSelect={setSelectedGate}
                onNodeSelect={selectNode}
                navigate={(view) => {
                  setActiveView(view);
                  setGateFilter("all");
                }}
                isDemo={isDemo}
                onBuild={handleBuild}
              />
            )}
            {activeView === "pipeline" && (
              <PipelineView
                nodes={snapshot.nodes}
                onSelect={selectNode}
                revision={snapshot.revision}
              />
            )}
            {activeView === "gates" && (
              <div className="view-stack">
                <div className="view-intro">
                  <div>
                    <span className="eyebrow">QUALITY & SAFETY</span>
                    <h2>Gate results</h2>
                    <p>{filteredCount} deterministic checks evaluate the current IR revision.</p>
                  </div>
                  <span className="badge badge--danger">
                    <AlertTriangle size={13} />
                    {
                      snapshot.gates.filter(
                        (gate) => gate.status === "FAIL" && gate.severity === "blocking",
                      ).length
                    }{" "}
                    blockers
                  </span>
                </div>
                <GateTable
                  gates={snapshot.gates}
                  filter={gateFilter}
                  setFilter={setGateFilter}
                  onSelect={setSelectedGate}
                />
              </div>
            )}
            {activeView === "agents" && (
              <AgentsView agents={snapshot.agents} isDemo={isDemo} telemetry={snapshot.telemetry} />
            )}
            {activeView === "artifacts" && (
              <ArtifactView nodes={snapshot.nodes} isDemo={isDemo} revision={snapshot.revision} />
            )}
            {activeView === "viewer3d" && <Viewer3DView snapshot={snapshot} />}
            {activeView === "telemetry" && <TelemetryView mode={snapshot.dataMode} />}
            <footer className="workspace-footer">
              <span>
                <LockKeyhole size={12} />
                Local-first · your designs stay on this machine
              </span>
              <span>
                atomc v0.0.1 <span className="footer-sep">·</span>{" "}
                <button
                  type="button"
                  onClick={() =>
                    setToast("Open the repository to report an issue or request a feature.")
                  }
                >
                  Feedback <ArrowUpRight size={11} />
                </button>
              </span>
            </footer>
          </div>
        </div>
      </main>
      {selectedGate && (
        <GateDetail gate={selectedGate} close={() => setSelectedGate(undefined)} isDemo={isDemo} />
      )}
      {selectedNode && !selectedGate && (
        <div className="scrim">
          <div className="scrim-dismiss" />
          <section
            className="detail-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="node-detail-title"
          >
            <div className="drawer-top">
              <span className="drawer-label">DAG NODE</span>
              <button
                type="button"
                className="icon-button"
                onClick={() => setSelectedNode(undefined)}
                aria-label="Close node details"
              >
                <X size={18} />
              </button>
            </div>
            <NodeStatus state={selectedNode.state} />
            <h2 id="node-detail-title">{selectedNode.id}</h2>
            <p className="drawer-summary">
              Executed by the <strong>{selectedNode.plugin}</strong> plugin kernel.
            </p>
            <div className="drawer-meta">
              <span>State</span>
              <NodeStatus state={selectedNode.state} />
              <span>Duration</span>
              <code>
                {selectedNode.durationMs ? formatDuration(selectedNode.durationMs) : "Not started"}
              </code>
              <span>Artifacts</span>
              <code>{selectedNode.artifactCount ?? 0}</code>
            </div>
            <button
              type="button"
              className="button button--quiet drawer-close"
              onClick={() => setSelectedNode(undefined)}
            >
              Close details
            </button>
          </section>
        </div>
      )}
      {toast && (
        <div className="toast" role="status" aria-live="polite">
          <span className="toast-check">
            <CheckCircle2 size={16} />
          </span>
          {toast}
          <button type="button" onClick={() => setToast("")} aria-label="Dismiss notification">
            <X size={15} />
          </button>
        </div>
      )}
      <button
        type="button"
        className="mobile-menu"
        onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        aria-label="Toggle navigation"
        aria-expanded={mobileMenuOpen}
      >
        <PanelLeftClose size={19} />
      </button>
    </div>
  );
}
