# WP-3.3 — `harness-agents` handoff

Branch: `wp/3.3-harness-agents` · Status: **done, green** · Depends on `@atomc/swarm-harness`
(WP-3.2 core) and the frozen contracts `docs/architecture/contracts/{agent-protocol,gate-result,ir-schema,plugin-manifest}.md`.

> **Note on the brief.** `docs/plan/briefs/WP-3.3.md` does not exist in the repository or in any git
> history (verified with `git log --all -- docs/plan/briefs/WP-3.3.md`, which is empty). This WP was
> therefore scoped directly from `PLAN.md` §8 line for WP-3.3, the agent protocol contract, and the
> pre-existing `packages/swarm-harness/ts/vitest.config.ts` coverage exclusion for
> `src/pi-ai-provider.ts`. No contract was modified and no root file was edited. If a real brief was
> intended to exist, its scope should be diffed against this handoff before merge.

## What was built

All changes are inside the owned paths: `packages/swarm-harness/ts/src/**`,
`packages/swarm-harness/ts/test/**`, `packages/swarm-harness/README.md`.

| Source | Responsibility |
|---|---|
| `src/agents/prompts.ts` | Shared agent rules plus the four specialist system prompts (`EE_/FW_/MECH_/OPS_AGENT_PROMPT`). |
| `src/agents/definitions.ts` | Frozen `AGENT_DEFINITIONS`, `DEFAULT_AGENT_MODEL`, gate routing (`routeGateToAgents`, `MULTI_OWNER_GATES`, `normalizeGateId`). |
| `src/agents/registry.ts` | `AgentRegistry`, `defaultAgentRegistry`, `AgentDefinitionError`; validates scopes, prompts and model config. |
| `src/agents/index.ts` | Agent subpath re-exports. |
| `src/multimodal.ts` | Datasheet/3D-render inspection: `INSPECTION_TOOLS`, `inspectionToolGrants`, `MultimodalInspector`, `loadImageAttachment`, `sniffImageMimeType`, `HarnessInspectionDaemon`. |
| `src/pi-ai-provider.ts` | Structural `PiAiProvider` (`ModelProvider`), `toPiAiContext`, `toModelDecision`, `toTurnUsage`, `encode/decodeToolName`, `extractJsonObject`. |
| `src/types.ts` | Added `ModelAttachment` and the optional `ModelRequest.attachments` field. |
| `src/index.ts` | Re-exports the new public surface. |
| `README.md` | New "Specialist agents", "Multimodal inspection" sections; rewrote the providers section for `PiAiProvider`. |

### The four agents (contract values, not invented)

| Agent | Lock scopes / produces | Gates | Tool allow-list |
|---|---|---|---|
| `ee-agent` | `/electrical`, `/layout`, `/keyboard` | `erc.no_unconnected`, `erc.assertions`, `layout.testpads.min_count`, `layout.testpads.nets_covered`, `kb.layout_matches_keymap`, `kb.diode_per_switch`, `kb.usb_cc_pulldowns` | `atopile:*` + inspection |
| `fw-agent` | `/firmware`, `/simulation` | `fw.qmk_compile`, `fw.matrix_pins_match_ir`, `fw.renode_boot`, `fw.matrix_scan` | `qmk:*`, `renode:*` + inspection |
| `mech-agent` | `/mechanical` | `mech.plate_switch_cutouts_14mm`, `mech.case_usb_cutout_aligned`, `mech.pogo_spacing_ge_2p54`, `mech.jig_no_collision`, `mech.enclosure_clearance` | `cad-jig:*` + inspection |
| `ops-agent` | `/sourcing`, `/fabrication`, `/orders` | `bom.all_in_stock`, `bom.cost_under_budget`, `bom.lead_time_under_days`, `fab.quote_under_budget` | `sourcing:*`, `orders:*` + inspection |

Lock scopes, holder format and gate ownership come from `agent-protocol.md` and `PLAN.md` §1.2.
`bom.cost_under_budget` is routed to **both** `ops-agent` and `ee-agent` per PLAN.

### Multimodal inspection

Two harness-owned read-only tools, `harness:inspect_datasheet` and `harness:inspect_render`, return a
`ModelAttachment` (base64 image). `HarnessInspectionDaemon` decorates any `HarnessDaemon`, serves those
two calls locally and forwards everything else. Images are sniffed by magic bytes/extension, capped at
8 MiB, and restricted to `image/png|jpeg|webp|gif`. Documents must be rasterised by the producing
plugin (stated in the tool description and README).

### pi-ai provider

`src/pi-ai-provider.ts` implements `ModelProvider` against a **structural, injected** port compatible
with `@mariozechner/pi-ai` (`completeSimple`, `getModel`). It deliberately does **not** import the SDK,
so the harness stays installable with zero vendor dependencies and deterministic tests inject a fake
`complete`. `toPiAiContext` builds the pi-ai `Context` (system prompt + decision protocol, failure
summary, scoped IR, tools, attachments); `toModelDecision` maps tool calls and JSON decisions back to
`ModelDecision` and converts usage to integer-USD-minor.

## Public API for WP-3.4 (registry + provider)

WP-3.4 can consume these from `@atomc/swarm-harness`:

```ts
// Routing a gate failure to the agent(s) to wake.
import { routeGateToAgents, defaultAgentRegistry } from "@atomc/swarm-harness";
const agents: AgentName[] = routeGateToAgents(gate.id); // "gate:" prefix optional
const registry = defaultAgentRegistry();
registry.agentsForGate(gate.id); // AgentDefinition[]
registry.require("ee-agent");    // throws AgentDefinitionError if absent
registry.register({ ...definition, model, budget }); // validated override

// Provider for a run (inject the real pi-ai functions at the integration layer).
import { PiAiProvider } from "@atomc/swarm-harness";
const provider = new PiAiProvider({
  systemPrompt: registry.require(agent).systemPrompt,
  model: getModel("openrouter", "..."), complete: completeSimple, apiKey,
});

// Optional: serve multimodal inspection in front of the daemon client.
import { HarnessInspectionDaemon, MultimodalInspector } from "@atomc/swarm-harness";
const daemon = new HarnessInspectionDaemon(adapter, new MultimodalInspector(reader));
```

`runAgent({ definition: registry.require(agent), daemon, provider, failure, ... })` is unchanged from
WP-3.2.

## Tests — 97 total (52 new across 3 files)

- `test/agents.test.ts` — definition coverage/order, exact lock scopes, `produces ⊆ lockScopes` and
  no `/meta`, inspection grants, gate assignment, prompt content, default model, lookup, gate routing
  (single/shared/unknown), `AgentRegistry` seeding/override/lookup/routing, and every validation
  failure path.
- `test/multimodal.test.ts` — mime sniffing (magic bytes + extension), attachment creation/validation,
  `loadImageAttachment` (sniff/explicit/empty/oversized/undetectable/allow-list), inspector,
  tool contracts, and `HarnessInspectionDaemon` (merge, local serve, delegate, malformed args,
  transparent delegation of the whole daemon surface).
- `test/pi-ai-provider.test.ts` — tool-name encode/decode, `toPiAiTool`, `toPiAiContext`
  (system/decision/summary/attachments/no-tools), `toTurnUsage`, `extractJsonObject`,
  `toModelDecision` (tool/verify/patch/give_up + error/aborted/malformed), and `PiAiProvider.nextTurn`
  option pass-through with a fake `complete`.

Coverage (v8): **96.67 % stmts / 90.18 % branches / 100 % functions / 96.64 % lines** (threshold 85).
`src/index.ts`, `src/daemon-adapter.ts` and `src/pi-ai-provider.ts` remain excluded per
`vitest.config.ts`; the provider's pure helpers are still exercised by tests.

## How to verify (exact commands, repo root)

```bash
pnpm install --frozen-lockfile
pnpm --filter @atomc/core-ir build
pnpm --filter @atomc/daemon-client build
pnpm --filter @atomc/swarm-harness typecheck
pnpm --filter @atomc/swarm-harness test
pnpm --filter @atomc/swarm-harness test:coverage   # delete packages/swarm-harness/ts/coverage afterwards
pnpm --filter @atomc/swarm-harness build
pnpm exec biome check packages/swarm-harness/ts/src packages/swarm-harness/ts/test
pnpm exec turbo run build typecheck test
```

All of the above were run and pass locally (macOS arm64, Node 25.1.0, pnpm 10.30.3).

## Design decisions

- **No new dependency and no lockfile change.** The pi-ai adapter uses a structural port instead of
  importing `@mariozechner/pi-ai`. This keeps `pnpm-lock.yaml` (orchestrator-owned) untouched, keeps CI
  installs vendor-free, and lets tests inject a fake. Real wiring is a two-line integration change.
- **`produces === lockScopes` for the specialists.** The plugin manifests (Phase 4) will set the
  authoritative `produces`; the definitions mirror the contract scopes and the registry enforces
  `produces ⊆ lockScopes`.
- **Inspection tools are harness-owned (`harness:*`), read-only, and decorate the daemon.** This makes
  them usable through the existing `runAgent` tool path without inventing a Phase 4 plugin or widening
  any agent's write scopes.
- **Prompts are data.** They live in `prompts.ts`, are exported, and are joined with `SHARED_AGENT_RULES`
  so CLI/Studio can show exactly what an agent was told.
- **Gate routing is a function, not just a field**, so shared ownership (`bom.cost_under_budget`) is
  representable and unknown gates return `[]` for the coordinator to escalate.

## Deviations from contract

None. Lock scopes, holder id format, agent ids, gate ids/owners, IR node names and `produces`/`/meta`
rules all match the frozen contracts. The only additive protocol change is the optional
`ModelRequest.attachments` field, which does not alter existing behavior.

## Open issues

- **`runAgent` does not yet feed tool results or attachments back into the model context.** The runner
  passes `transcript: []` to `ModelProvider.nextTurn` (WP-3.2 behavior), so an inspection call's image
  is written to the transcript but not surfaced on the next turn. Wiring the accumulated turns /
  `attachments` through `ModelRequest` is the natural next step and is deliberately **not** done here to
  avoid changing the core loop owned/relied on by WP-3.4/WP-3.5.
- Real `@mariozechner/pi-ai` wiring (`getModel`/`completeSimple`, API-key handling, streaming token
  accounting) is left to the integration layer that constructs `PiAiProvider`. No live model call is
  made or tested in this package.
- `dagTargets` are intentionally omitted from the definitions: the Phase 4 watch/DAG node ids are not
  frozen yet, so each run defaults to the daemon's affected-node scheduling rather than guessing ids.
- `permittedTools` use plugin namespaces (`atopile:*`, `qmk:*`, …) plus the two `harness:*` grants.
  Exact tool names will exist only once Phase 4 plugins land; the runner already re-checks against the
  daemon's advertised tools.

## Root changes needed

**None.** No root file, lockfile, workspace manifest or CI file was edited.

## Missing-brief follow-up

The orchestrator should either add `docs/plan/briefs/WP-3.3.md` retroactively (matching this scope) or
confirm that PLAN §8's one-line definition was the intended brief. The scope implemented is the
maximal reading of that line without touching Phase 4 plugin code.
