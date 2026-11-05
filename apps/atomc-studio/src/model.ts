import type { AgentName, GateResult } from "@atomc/daemon-client";

export type ConnectionState = "connecting" | "connected" | "offline";
export type RunState = "idle" | "queued" | "running" | "passed" | "failed" | "stale";

export interface DagNode {
  id: string;
  plugin: string;
  state: RunState;
  durationMs?: number;
  artifactCount?: number;
}

export interface AgentCard {
  id: AgentName;
  label: string;
  initials: string;
  specialty: string;
  state: "idle" | "working" | "waiting" | "done";
  task: string;
  spentCents: number;
  capCents: number;
  tint: string;
}

export interface ActivityItem {
  id: string;
  time: string;
  title: string;
  detail: string;
  tone: "success" | "info" | "warning" | "neutral";
}

export interface BoardSnapshot {
  projectName: string;
  projectPath: string;
  connection: ConnectionState;
  revision: number;
  lastBuild: string;
  nodes: DagNode[];
  gates: GateResult[];
  agents: AgentCard[];
  activity: ActivityItem[];
}

export interface StudioApi {
  load(): Promise<BoardSnapshot>;
  runBuild(): Promise<BoardSnapshot>;
}

const specialists: AgentCard[] = [
  {
    id: "ee-agent",
    label: "Electrical",
    initials: "EE",
    specialty: "Circuit & PCB",
    state: "done",
    task: "ERC and layout checks passed",
    spentCents: 12,
    capCents: 75,
    tint: "violet",
  },
  {
    id: "fw-agent",
    label: "Firmware",
    initials: "FW",
    specialty: "QMK & simulation",
    state: "working",
    task: "Checking matrix scan pins",
    spentCents: 23,
    capCents: 75,
    tint: "cyan",
  },
  {
    id: "mech-agent",
    label: "Mechanical",
    initials: "ME",
    specialty: "Case & test jig",
    state: "waiting",
    task: "Waiting for layout artifact",
    spentCents: 0,
    capCents: 50,
    tint: "amber",
  },
  {
    id: "ops-agent",
    label: "Supply chain",
    initials: "SC",
    specialty: "BOM & fabrication",
    state: "idle",
    task: "Ready for sourcing gates",
    spentCents: 0,
    capCents: 50,
    tint: "green",
  },
];

const gate = (
  id: string,
  status: GateResult["status"],
  owner_agent: AgentName,
  summary: string,
  severity: GateResult["severity"] = "blocking",
): GateResult => ({
  id,
  status,
  severity,
  plugin: "atopile@0.15.9",
  owner_agent,
  evaluated_at: new Date(Date.now() - 35_000).toISOString(),
  ir_rev: 128,
  duration_ms: 340,
  summary,
  evidence: [],
  suggestions: [],
  refs: [],
});

export function createDemoSnapshot(): BoardSnapshot {
  return {
    projectName: "atomc-keeb",
    projectPath: "~/work/atomc/examples/atomc-keeb",
    connection: "offline",
    revision: 128,
    lastBuild: "2m ago",
    nodes: [
      {
        id: "atopile.compile",
        plugin: "atopile",
        state: "passed",
        durationMs: 1840,
        artifactCount: 4,
      },
      {
        id: "erc.electrical",
        plugin: "atopile",
        state: "passed",
        durationMs: 620,
        artifactCount: 0,
      },
      { id: "qmk.compile", plugin: "qmk", state: "passed", durationMs: 4210, artifactCount: 2 },
      {
        id: "fw.matrix_scan",
        plugin: "renode",
        state: "running",
        durationMs: 920,
        artifactCount: 0,
      },
      { id: "cad.plate_case", plugin: "cad-jig", state: "queued", artifactCount: 0 },
      { id: "sourcing.bom", plugin: "sourcing", state: "idle", artifactCount: 0 },
    ],
    gates: [
      gate("erc.no_unconnected", "PASS", "ee-agent", "No unconnected pins"),
      gate("fw.qmk_compile", "PASS", "fw-agent", "QMK firmware builds for STM32F411"),
      gate(
        "fw.matrix_scan",
        "FAIL",
        "fw-agent",
        "Column pin C13 is absent from the IR",
        "blocking",
      ),
      gate(
        "layout.testpads.nets_covered",
        "PASS",
        "ee-agent",
        "All 16 matrix nets reach test pads",
      ),
      gate(
        "mech.plate_switch_cutouts_14mm",
        "SKIP",
        "mech-agent",
        "Waiting for current board outline",
        "advisory",
      ),
      gate(
        "bom.all_in_stock",
        "SKIP",
        "ops-agent",
        "Sourcing has not run for this revision",
        "advisory",
      ),
    ],
    agents: structuredClone(specialists),
    activity: [
      {
        id: "a-1",
        time: "10:42:18",
        title: "Matrix scan gate failed",
        detail: "fw.matrix_scan · C13 is not mapped in /keyboard",
        tone: "warning",
      },
      {
        id: "a-2",
        time: "10:42:13",
        title: "Firmware agent picked up the issue",
        detail: "@fw-agent · turn 2 · $0.23 / $0.75",
        tone: "info",
      },
      {
        id: "a-3",
        time: "10:41:56",
        title: "QMK compile passed",
        detail: "qmk.compile · STM32F411CEU6 · 4.21s",
        tone: "success",
      },
      {
        id: "a-4",
        time: "10:41:42",
        title: "Electrical checks passed",
        detail: "ERC clean · 48 keys · 16 matrix nets",
        tone: "success",
      },
      {
        id: "a-5",
        time: "10:40:02",
        title: "Build started",
        detail: "run #bld_8f24 · IR revision 128",
        tone: "neutral",
      },
    ],
  };
}

export function createDemoApi(now: () => Date = () => new Date()): StudioApi {
  let snapshot = createDemoSnapshot();
  return {
    async load() {
      return structuredClone(snapshot);
    },
    async runBuild() {
      snapshot = {
        ...snapshot,
        lastBuild: "just now",
        activity: [
          {
            id: `build-${now().getTime()}`,
            time: now().toLocaleTimeString(),
            title: "Build queued",
            detail: "DAG run requested from Studio",
            tone: "info",
          },
          ...snapshot.activity,
        ],
      };
      return structuredClone(snapshot);
    },
  };
}
