# @atomc/swarm-harness

Transactional swarm state machine for atomc. Implements the agent loop frozen in
[`docs/architecture/contracts/agent-protocol.md`](../../../docs/architecture/contracts/agent-protocol.md):
agents never self-report success — convergence reads real `GateResult`s from the daemon.

```
IDLE → PLAN → CLAIM_LOCK → ACT → VERIFY → RELEASE → (PASS / RETRY / ESCALATE)
                     ↑                │
                     └──── RETRY_TURN ┘   (bounded in-run gate retries)
```

Every exit path (pass, give-up, error, budget, abort, lock conflict) releases acquired locks in a
`finally` block. Optimistic revision conflicts re-read the IR and re-prompt the model instead of
resending a stale patch.

## Install

```bash
pnpm add @atomc/swarm-harness
```

Runtime dependencies: `@atomc/core-ir` (patch op types), `@atomc/daemon-client` (typed RPC + error
classes), `zod`. ESM and CJS builds ship with `.d.ts` types.

## Registering an agent

Specialists (WP-3.3) register an `AgentDefinition`; the harness does the transactional work. Lock
scopes and `produces` come from the plugin manifest, gate ownership from `gate-result.md`.

```ts
import { runAgent, TranscriptWriter, DaemonClientAdapter } from "@atomc/swarm-harness";
import { DaemonClient } from "@atomc/daemon-client";

const client = await DaemonClient.connect({ url, token });
const daemon = new DaemonClientAdapter(client);

const result = await runAgent({
  definition: {
    id: "ee-agent",
    systemPrompt: "You are the electrical specialist…",
    permittedTools: ["atopile:*", "sourcing:solve"],
    lockScopes: ["/electrical", "/layout", "/keyboard"],
    gates: ["erc.no_unconnected", "layout.testpads.nets_covered"],
    dagTargets: ["atopile.compile"],
    model: { provider: "openrouter", model: "deepseek/deepseek-v4.1-flash", thinking: "medium" },
    budget: { maxTurns: 12, maxCostMinor: 250, maxTokens: 200_000 },
  },
  failure,                 // a GateResult FAIL routed to this agent
  daemon,
  provider,                // injected ModelProvider (see below)
  projectRoot: process.cwd(),
  runId: "converge-42",
  onEvent: (event) => console.log(event.kind), // stream to CLI/Studio
});
```

`result.outcome` is `PASS | RETRY | ESCALATE | ABORTED`. Only `PASS` means every owned gate returned
`PASS`/`SKIP`/advisory-`FAIL`; a crashed gate (`ERROR`) escalates to the orchestrator.

## Specialist agents

The four contract specialists ship as frozen, validated `AgentDefinition`s:

| Agent | Locks / produces | Gates (owner) | Tool namespace |
|---|---|---|---|
| `ee-agent` | `/electrical`, `/layout`, `/keyboard` | `erc.*`, `layout.testpads.*`, `kb.*` | `atopile:*` |
| `fw-agent` | `/firmware`, `/simulation` | `fw.qmk_compile`, `fw.matrix_pins_match_ir`, `fw.renode_boot`, `fw.matrix_scan` | `qmk:*`, `renode:*` |
| `mech-agent` | `/mechanical` | `mech.*` | `cad-jig:*` |
| `ops-agent` | `/sourcing`, `/fabrication`, `/orders` | `bom.*`, `fab.quote_under_budget` | `sourcing:*`, `orders:*` |

```ts
import {
  AGENT_DEFINITIONS,
  AgentRegistry,
  defaultAgentRegistry,
  routeGateToAgents,
} from "@atomc/swarm-harness";

AGENT_DEFINITIONS["ee-agent"].lockScopes; // ["/electrical", "/layout", "/keyboard"]
routeGateToAgents("gate:bom.cost_under_budget"); // ["ops-agent", "ee-agent"]

const registry = new AgentRegistry(); // or defaultAgentRegistry()
registry.register({ ...AGENT_DEFINITIONS["ee-agent"], model: { provider: "openrouter", model: "x" } });
registry.agentsForGate("gate:fw.qmk_compile"); // [fw-agent definition]
```

The registry validates every definition: ids must be one of the four contract agents, lock scopes
must be JSON pointers under a real IR node, `produces` must sit inside the lock scopes, and `/meta` is
forbidden. Override model routing, budgets or prompts per agent without forking the package.

## Multimodal inspection

Two harness-owned, read-only tools give agents eyes on rendered artifacts:
`harness:inspect_datasheet` (pinouts, package dimensions, electrical limits) and
`harness:inspect_render` (board/plate/case/jig geometry). They are granted to every specialist and
return a `ModelAttachment` (base64 image) that the provider inlines as an image content part.
Documents must be rasterised by the producing plugin first; only `image/png|jpeg|webp|gif` up to
8 MiB are accepted.

```ts
import { HarnessInspectionDaemon, MultimodalInspector } from "@atomc/swarm-harness";
import { readFile } from "node:fs/promises";

const inspector = new MultimodalInspector({ readFile: async (p) => new Uint8Array(await readFile(p)) });
const daemon = new HarnessInspectionDaemon(daemonClientAdapter, inspector);
// pass `daemon` to runAgent: inspection calls are served locally, everything else is forwarded.
```

## Providers and model routing

The harness depends on the narrow `ModelProvider` port, not on a vendor SDK:

```ts
interface ModelProvider {
  readonly id: string;
  nextTurn(request: ModelRequest): Promise<ModelDecision>;
}
```

`ModelDecision` is one of `patch` (an `AgentPatchProposal`), `tool` (a `plugin:tool` call), `verify`,
or `give_up`. Tool calls are checked against the agent allow-list (`"*"`, `"plugin:*"`, or exact
`"plugin:tool"`) before the daemon is asked to run them. Patches must land inside a declared lock
scope and at the current `_meta.rev`.

Adapters (real LLM, recorded replay) live outside the deterministic core and are injected. The
package ships a structural `PiAiProvider` for `@mariozechner/pi-ai` that never imports the vendor SDK
— integrators pass `getModel(...)` and `completeSimple` in:

```ts
import { PiAiProvider } from "@atomc/swarm-harness";
import { completeSimple, getModel } from "@mariozechner/pi-ai";

const provider = new PiAiProvider({
  systemPrompt: AGENT_DEFINITIONS["ee-agent"].systemPrompt,
  model: getModel("openrouter", "deepseek/deepseek-v4-flash"),
  complete: completeSimple,
  apiKey: process.env.OPENROUTER_API_KEY,
  reasoning: "medium",
});
```

`toPiAiContext` (pure) turns a `ModelRequest` — failure summary, scoped IR reads, tool descriptors and
attachments — into a pi-ai `Context`; `toModelDecision` maps the reply back to a `ModelDecision`
(tool call, `patch`, `verify`, `give_up`) and converts usage to integer-USD-minor accounting. Tool
names are encoded as `"<plugin>__<tool>"`. Tests inject a fake `complete` and never touch the network
or the SDK.

## Spend and turn caps

`AgentBudget` caps `maxTurns` and integer-USD-minor `maxCostMinor` (and optional `maxTokens`).
Per-turn `usage` is summed; exceeding any cap moves the run to `ESCALATE`. `AbortSignal` cancels
between turns and daemon calls.

## Transcripts

Each session appends JSONL to `.atomc/sessions/<run>/<agent>.jsonl`, rotated at 8 MiB
(configurable). Entries are redacted before they hit disk: sensitive keys (`token`, `secret`,
`authorization`, …) become `[REDACTED]` and bearer/API-key-shaped strings are scrubbed.

```ts
const transcript = new TranscriptWriter({
  projectRoot: process.cwd(),
  runId: "converge-42",
  agentId: "ee-agent",
});
```

## Replay and convergence

`runAgent` is deterministic given `(IR rev, gate results, provider decisions)`. The scripted
`FakeProvider` replays recorded sessions in CI; `onEvent` frames (`state`, `lock.*`, `patch.*`,
`tool.*`, `gate.result`) can be asserted directly. WP-3.4's converger calls `runAgent` per routed
gate failure and uses the `RETRY`/`ESCALATE` outcomes to decide whether to re-wake an agent or raise
a human checkpoint.
