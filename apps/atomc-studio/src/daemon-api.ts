import type { AgentName, GateResult } from "@atomc/daemon-client";
import type { AgentCard, BoardSnapshot, DagNode, RunState, StudioApi } from "./model.js";

/** Browser-safe subset of the daemon client methods used by Studio. */
export interface StudioRpcClient {
  getIR(path?: string): Promise<{ rev: number; value: unknown }>;
  dagStatus(): Promise<{ nodes: Array<{ id: string; plugin: string; state: string }> }>;
  listGates(): Promise<GateResult[]>;
  listTools(agent?: AgentName): Promise<unknown[]>;
  runDAG(params?: { targets?: string[]; force?: boolean }): Promise<{ run_id: string }>;
}

/** Secure host-provided connector. Electron/desktop hosts should use contextBridge, never URL tokens. */
export interface StudioHostBridge {
  connectDaemon(options: { url: string }): Promise<StudioRpcClient>;
}

declare global {
  interface Window {
    atomcStudioHost?: StudioHostBridge;
  }
}

export interface StudioDaemonOptions {
  url?: string;
  projectName: string;
  projectPath: string;
  clientFactory: (url: string) => Promise<StudioRpcClient>;
}

const agents: AgentCard[] = [
  {
    id: "ee-agent",
    label: "Electrical",
    initials: "EE",
    specialty: "Circuit & PCB",
    state: "idle",
    task: "Ready",
    spentCents: 0,
    capCents: 75,
    tint: "violet",
  },
  {
    id: "fw-agent",
    label: "Firmware",
    initials: "FW",
    specialty: "QMK & simulation",
    state: "idle",
    task: "Ready",
    spentCents: 0,
    capCents: 75,
    tint: "cyan",
  },
  {
    id: "mech-agent",
    label: "Mechanical",
    initials: "ME",
    specialty: "Case & test jig",
    state: "idle",
    task: "Ready",
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
    task: "Ready",
    spentCents: 0,
    capCents: 50,
    tint: "green",
  },
];

function nodeState(state: string): RunState {
  switch (state) {
    case "queued":
      return "queued";
    case "running":
      return "running";
    case "ok":
      return "passed";
    case "failed":
      return "failed";
    case "stale":
      return "stale";
    default:
      return "idle";
  }
}

export function createDaemonStudioApi(options: StudioDaemonOptions): StudioApi {
  const url = options.url ?? "ws://127.0.0.1:7437/rpc";
  const factory = options.clientFactory;
  let clientPromise: Promise<StudioRpcClient> | undefined;
  const getClient = () => {
    if (clientPromise === undefined) {
      const pending = factory(url);
      const tracked = pending.catch((error: unknown) => {
        if (clientPromise === tracked) clientPromise = undefined;
        throw error;
      });
      clientPromise = tracked;
    }
    return clientPromise;
  };

  const load = async (): Promise<BoardSnapshot> => {
    const client = await getClient();
    const [ir, status, gates] = await Promise.all([
      client.getIR("/"),
      client.dagStatus(),
      client.listGates(),
    ]);
    const nodes: DagNode[] = status.nodes.map((node) => ({
      id: node.id,
      plugin: node.plugin,
      state: nodeState(node.state),
    }));
    const mappedGates = gates.map((gate): GateResult => gate);
    const passed = mappedGates.filter((gate) => gate.status === "PASS").length;
    return {
      projectName: options.projectName,
      projectPath: options.projectPath,
      connection: "connected",
      revision: ir.rev,
      lastBuild: "daemon connected",
      nodes,
      gates: mappedGates,
      agents: structuredClone(agents),
      activity: [
        {
          id: `daemon-rev-${ir.rev}`,
          time: new Date().toLocaleTimeString(),
          title: "Live daemon snapshot loaded",
          detail: `IR revision ${ir.rev} · ${nodes.length} DAG nodes · ${passed} passing gates`,
          tone: "success",
        },
      ],
    };
  };

  return {
    load,
    async runBuild() {
      const client = await getClient();
      await client.runDAG({});
      return load();
    },
  };
}
