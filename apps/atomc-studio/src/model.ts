import type { AgentName, GateResult } from "@atomc/daemon-client";
import type {
  ComponentSummary,
  FabricationSubtree,
  OrdersSubtree,
  SourcingSubtree,
} from "./sourcing/types.js";
import { padFixtureIr } from "./viewer3d/fixtures.js";

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

/** Where a snapshot's data comes from, so the UI never implies more than it knows. */
export type DataMode = "demo" | "daemon";

/** Honest labeling for data Studio cannot currently source. */
export interface TelemetryNotice {
  kind: "demo" | "unavailable";
  label: string;
  detail: string;
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
  /** "demo" snapshots are illustrative; "daemon" snapshots come from RPC reads. */
  dataMode: DataMode;
  /** Raw system IR used by the 3D viewer. Absent when a snapshot cannot supply it. */
  systemJson?: unknown;
  /** What the agent panels actually know; never inferred from gate ownership. */
  telemetry: TelemetryNotice;
  /** IR `/sourcing` subtree, when a project carries one. Absent in most projects today. */
  sourcing?: SourcingSubtree | null;
  /** IR `/fabrication` subtree, when present. */
  fabrication?: FabricationSubtree | null;
  /** IR `/orders` subtree, when present. */
  orders?: OrdersSubtree | null;
  /** Minimal `/electrical/components` projection used to join BOM lines to footprints. */
  components?: ComponentSummary[];
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
  owner_agent: AgentName | null,
  summary: string,
  severity: GateResult["severity"] = "blocking",
  detail: Pick<GateResult, "evidence" | "suggestions" | "refs"> = {
    evidence: [],
    suggestions: [],
    refs: [],
  },
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
  ...detail,
});

export function createDemoSnapshot(): BoardSnapshot {
  return {
    projectName: "atomc-keeb",
    projectPath: "~/work/atomc/examples/atomc-keeb",
    connection: "offline",
    revision: 128,
    lastBuild: "Simulated · nothing was built",
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
        {
          evidence: [
            { kind: "json", message: "keyboard.matrix.col_pins does not list C13" },
            { kind: "artifact", ref: "art:renode-matrix-scan" },
          ],
          suggestions: [
            {
              message: "Add C13 to keyboard.matrix.col_pins and re-run the matrix scan.",
              patch: {
                path: "/keyboard/matrix/col_pins",
                ops: [{ op: "add", path: "/12", value: "C13" }],
              },
            },
          ],
          refs: ["key:K0_12", "pad:TP_COL13"],
        },
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
    sourcing: {
      currency: "USD",
      build_qty: 5,
      budget: { per_unit_minor: 4500, total_minor: 22500 },
      bom: [
        {
          id: "bom:U1",
          component_refs: ["comp:U1"],
          mpn: "STM32F411CEU6",
          qty_per_unit: 1,
          chosen_offer_ref: "offer:U1_lcsc",
          offers: [
            {
              id: "offer:U1_lcsc",
              vendor: "lcsc",
              sku: "C60442",
              stock: 320,
              lead_time_days: 7,
              moq: 1,
              price_breaks: [
                { qty: 1, unit_price_minor: 420 },
                { qty: 5, unit_price_minor: 390 },
              ],
              currency: "USD",
              fetched_at: "2026-11-04T00:00:00Z",
              url: "https://example.com/C60442",
            },
          ],
        },
        {
          id: "bom:U2",
          component_refs: ["comp:U2"],
          mpn: "AP2112K-3.3TRG1",
          qty_per_unit: 1,
          chosen_offer_ref: "offer:U2_lcsc",
          offers: [
            {
              id: "offer:U2_lcsc",
              vendor: "lcsc",
              sku: "C51118",
              stock: 1500,
              lead_time_days: 7,
              moq: 1,
              price_breaks: [{ qty: 1, unit_price_minor: 8 }],
              currency: "USD",
              fetched_at: "2026-11-04T00:00:00Z",
            },
          ],
        },
        {
          id: "bom:J1",
          component_refs: ["comp:J1"],
          mpn: "USB4085-GF-A",
          qty_per_unit: 1,
          offers: [
            {
              id: "offer:J1_lcsc",
              vendor: "lcsc",
              sku: "C165948",
              stock: 40,
              lead_time_days: 14,
              moq: 1,
              price_breaks: [{ qty: 1, unit_price_minor: 95 }],
              currency: "USD",
              fetched_at: "2026-11-04T00:00:00Z",
            },
          ],
        },
      ],
    },
    components: [
      { id: "comp:U1", designator: "U1", mpn: "STM32F411CEU6", footprint: "QFN-48_7x7mm" },
      { id: "comp:U2", designator: "U2", mpn: "AP2112K-3.3TRG1", footprint: "SOT-23-5" },
      { id: "comp:J1", designator: "J1", mpn: "USB4085-GF-A", footprint: "USB-C-16P" },
    ],
    dataMode: "demo",
    systemJson: padFixtureIr,
    telemetry: {
      kind: "demo",
      label: "Simulated specialist activity",
      detail:
        "Sample agent states, tasks and spend are illustrative only; no agent runs or model spend occurred.",
    },
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
        activity: [
          {
            id: `build-${now().getTime()}`,
            time: now().toLocaleTimeString("en-US", { timeZone: "UTC" }),
            title: "Preview: build action selected",
            detail: "No daemon was called and no build was queued.",
            tone: "info",
          },
          ...snapshot.activity,
        ],
      };
      return structuredClone(snapshot);
    },
  };
}
