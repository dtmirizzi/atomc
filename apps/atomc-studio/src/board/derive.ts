import type { AgentName, GateResult, GateSeverity, GateStatus } from "@atomc/daemon-client";

export type GateDomain = "ee" | "fw" | "mech" | "ops" | "unowned";

export const GATE_DOMAIN_ORDER: readonly GateDomain[] = ["ee", "fw", "mech", "ops", "unowned"];

interface DomainMeta {
  label: string;
  description: string;
}

const DOMAIN_META: Record<GateDomain, DomainMeta> = {
  ee: { label: "Electrical", description: "Circuit, ERC and layout checks" },
  fw: { label: "Firmware", description: "QMK build and simulation checks" },
  mech: { label: "Mechanical", description: "Enclosure, plate and jig checks" },
  ops: { label: "Supply chain", description: "BOM, budget and fabrication checks" },
  unowned: {
    label: "Unowned",
    description: "No owner_agent assigned — coordinator review required",
  },
};

export function domainOf(owner: AgentName | null): GateDomain {
  switch (owner) {
    case "ee-agent":
      return "ee";
    case "fw-agent":
      return "fw";
    case "mech-agent":
      return "mech";
    case "ops-agent":
      return "ops";
    default:
      return "unowned";
  }
}

export interface GateGroup {
  domain: GateDomain;
  label: string;
  description: string;
  gates: GateResult[];
  total: number;
  passCount: number;
  blockingFailCount: number;
  /** Passing gates ÷ total gates in the group, over the unfiltered group. */
  passRate: number;
  unowned: boolean;
}

export function groupGates(gates: GateResult[]): GateGroup[] {
  const buckets = new Map<GateDomain, GateResult[]>();
  for (const gate of gates) {
    const domain = domainOf(gate.owner_agent);
    const list = buckets.get(domain);
    if (list === undefined) buckets.set(domain, [gate]);
    else list.push(gate);
  }
  return GATE_DOMAIN_ORDER.filter((domain) => buckets.has(domain)).map((domain) => {
    const list = buckets.get(domain) ?? [];
    const total = list.length;
    const passCount = list.filter((gate) => gate.status === "PASS").length;
    return {
      domain,
      label: DOMAIN_META[domain].label,
      description: DOMAIN_META[domain].description,
      gates: list,
      total,
      passCount,
      blockingFailCount: list.filter(
        (gate) =>
          (gate.status === "FAIL" || gate.status === "ERROR") && gate.severity === "blocking",
      ).length,
      passRate: total === 0 ? 0 : passCount / total,
      unowned: domain === "unowned",
    };
  });
}

export interface GateFilterState {
  severity: GateSeverity | "all";
  status: GateStatus | "all";
}

export const DEFAULT_GATE_FILTER: GateFilterState = { severity: "all", status: "all" };

export function filterGates(gates: GateResult[], filter: GateFilterState): GateResult[] {
  return gates.filter(
    (gate) =>
      (filter.severity === "all" || gate.severity === filter.severity) &&
      (filter.status === "all" || gate.status === filter.status),
  );
}

export function countByStatus(gates: GateResult[]): Record<GateStatus, number> {
  return {
    PASS: gates.filter((gate) => gate.status === "PASS").length,
    FAIL: gates.filter((gate) => gate.status === "FAIL").length,
    SKIP: gates.filter((gate) => gate.status === "SKIP").length,
    ERROR: gates.filter((gate) => gate.status === "ERROR").length,
  };
}

export function countBySeverity(gates: GateResult[]): Record<GateSeverity | "all", number> {
  return {
    all: gates.length,
    blocking: gates.filter((gate) => gate.severity === "blocking").length,
    advisory: gates.filter((gate) => gate.severity === "advisory").length,
  };
}

export function passRate(gates: GateResult[]): number {
  if (gates.length === 0) return 0;
  return gates.filter((gate) => gate.status === "PASS").length / gates.length;
}

const GATE_TITLES: Record<string, string> = {
  "erc.no_unconnected": "Unconnected pins",
  "fw.qmk_compile": "QMK firmware compile",
  "fw.matrix_scan": "Matrix scan pin map",
  "layout.testpads.nets_covered": "Test-pad net coverage",
  "mech.plate_switch_cutouts_14mm": "Switch plate cutouts",
  "bom.all_in_stock": "BOM availability",
};

export function gateTitle(gate: GateResult): string {
  const id = gate.id.replace(/^gate:/, "");
  return GATE_TITLES[id] ?? id.replaceAll(".", " ");
}

export function formatDuration(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

export function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date
    .toISOString()
    .replace("T", " ")
    .replace(/\.\d{3}Z$/, "Z");
}

export function elementIdFor(gateId: string): string {
  return gateId.replace(/[^a-zA-Z0-9_-]/g, "-");
}
