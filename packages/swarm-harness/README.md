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

Adapters (real LLM, recorded replay) live outside this package. Tests use `FakeProvider`, which
scripts a decision list and never touches the network. This WP ships **no** real pi-ai/OpenRouter
adapter: wiring `@mariozechner/pi-ai` and `@mariozechner/pi-agent-core` behind `ModelProvider` is a
tracked follow-up so the deterministic core stays provider-free.

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
