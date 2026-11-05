# WP-3.3 — `harness-agents` handoff

Branch: `wp/3.3-harness-agents` · Status: **done, green** · Depends on `@atomc/swarm-harness`
(WP-3.2 core) and the frozen contracts `docs/architecture/contracts/{agent-protocol,rpc,gate-result,plugin-manifest}.md`.

This WP implements `docs/plan/briefs/WP-3.3.md` (specialist definitions and a real pi-ai provider
adapter) plus the review follow-up items: no provider coverage exclusion, AbortSignal forwarding,
duplicate/invalid-config rejection, filesystem-safe inspection, and a compile-checked pi-ai
integration. `pnpm-lock.yaml` is intentionally untouched — see **Root changes needed**.

## What was built

| Source | Responsibility |
|---|---|
| `src/agents/prompts.ts` | Shared rules plus the four specialist prompts (`EE_/FW_/MECH_/OPS_AGENT_PROMPT`). |
| `src/agents/definitions.ts` | Frozen `AGENT_DEFINITIONS`, `DEFAULT_AGENT_MODEL`, gate routing (`routeGateToAgents`, `MULTI_OWNER_GATES`, `normalizeGateId`). |
| `src/agents/registry.ts` | `AgentRegistry`, `defaultAgentRegistry`, `AgentDefinitionError`; rejects duplicates and invalid scope/tool/budget config. |
| `src/providers/pi-ai.ts` | Real, typed `PiAiProvider` over `@mariozechner/pi-ai` v0.73.x plus the secret-free `createPiAiProvider` factory and pure mapping helpers. |
| `src/multimodal.ts` | Inspection tools, attachments, `ProjectImageReader` (root-confined), `HarnessInspectionDaemon`, `isModelAttachment`. |
| `src/runner.ts` | Forwards `AbortSignal`; accumulates real tool turns + inspection images into subsequent `ModelRequest`s. |
| `src/types.ts` | Added `ModelAttachment`, `ModelRequest.attachments` and `ModelRequest.signal`. |
| `src/index.ts` | Re-exports the new public surface. |
| `README.md` | Updated specialist, inspection (safe reader) and provider (real pi-ai, env keys, frozen model id) sections. |

### The four agents (contract values)

| Agent | Locks / produces | Gates | Tool allow-list |
|---|---|---|---|
| `ee-agent` | `/electrical`, `/layout`, `/keyboard` | `erc.*`, `layout.testpads.*`, `kb.*` | `atopile:*` + inspection |
| `fw-agent` | `/firmware`, `/simulation` | `fw.qmk_compile`, `fw.matrix_pins_match_ir`, `fw.renode_boot`, `fw.matrix_scan` | `qmk:*`, `renode:*` + inspection |
| `mech-agent` | `/mechanical` | `mech.*` | `cad-jig:*` + inspection |
| `ops-agent` | `/sourcing`, `/fabrication`, `/orders` | `bom.*`, `fab.quote_under_budget` | `sourcing:*`, `orders:*` + inspection |

Registry rules: agent id must be one of the four; lock scopes JSON pointers under a real node; `/meta`
forbidden; `produces ⊆ lockScopes`; tool grants must match `*`/`plugin:*`/`plugin:tool`; budgets must be
positive/ non-negative integers; gates and DAG targets non-empty; **duplicate ids are rejected**
(constructor and `register`).

## Provider adapter (`src/providers/pi-ai.ts`)

Real import of `completeSimple`, `getModel`, `Type`, `Context`, `AssistantMessage`, `Model`, `Usage` from
`@mariozechner/pi-ai`. The injected transport seam is `PiAiComplete = (model: Model<Api>, context: Context,
options?: SimpleStreamOptions) => Promise<AssistantMessage>` and the module exports
`DEFAULT_PI_AI_COMPLETE: PiAiComplete = completeSimple` — a compile-level compatibility check, so no cast
is needed on the real function.

Mapping:
- `toPiAiContext(request, {systemPrompt, model})` → pi-ai `Context` (system prompt + decision protocol,
  failure summary, scoped IR reads, `Type.Unsafe` tool schemas, prior tool turns as assistant/toolResult
  pairs, attachments as image parts).
- `toModelDecision(message)` → `ModelDecision` for tool calls and JSON `patch`/`verify`/`give_up`;
  error/aborted stops and malformed output throw.
- `toTurnUsage(usage)` → integer-USD-minor `TurnUsage`.
- Tool names encode as `"<plugin>__<tool>"` (`encodeToolName`/`decodeToolName`).

Secret flow and cancellation:
- `createPiAiProvider(config, deps)` takes a **secret-free** config (`apiKeyEnv`, not the key) plus
  injected `env` and `complete`. The key is read from `env[apiKeyEnv]`, held privately, and never placed
  on a config object, an `AgentDefinition`, a transcript or a browser URL.
- Transport errors are scrubbed of the configured key before they propagate.
- `nextTurn` forwards `request.signal ?? providerDefaultSignal` to pi-ai's `SimpleStreamOptions.signal`.

## Multimodal inspection (filesystem-safe)

Two read-only tools, `harness:inspect_datasheet` / `harness:inspect_render`, return a `ModelAttachment`
(base64 image). `ProjectImageReader`:
- rejects absolute paths (`/...`, `C:\...`) and any `..` traversal before touching the filesystem;
- resolves `realpath` for both root and target and rejects targets that escape the project root (symlink
  escape blocked);
- enforces an injectable byte cap (default 8 MiB) and the `image/png|jpeg|webp|gif` allow-list.

`MultimodalInspector` accepts any `ArtifactReader`; hosts that cannot use Node's `fs` must supply a
reader with the same containment guarantees. `HarnessInspectionDaemon` serves the two tools locally and
forwards everything else.

## Runner plumbing (additive, semantics unchanged)

`runAgent` now snapshots accumulated `AgentTurn[]` and `ModelAttachment[]` into each `ModelRequest`,
forwards `options.signal`, and collects a tool result as an attachment when it structurally matches
`ModelAttachment` (via `isModelAttachment`). Tool rejections/errors are also recorded as turns so the
model can recover. State-machine, lock, gate and budget semantics are untouched.

## Public API for WP-3.4

```ts
// Routing a gate failure to the agent(s) to wake.
import { routeGateToAgents, defaultAgentRegistry } from "@atomc/swarm-harness";
const agents: AgentName[] = routeGateToAgents(gate.id); // "gate:" prefix optional
const registry = defaultAgentRegistry();
registry.agentsForGate(gate.id); // AgentDefinition[]
registry.require("ee-agent");    // throws AgentDefinitionError if absent

// Real provider for a run (inject pi-ai values at the integration layer).
import { completeSimple, getModel } from "@mariozechner/pi-ai";
import { createPiAiProvider } from "@atomc/swarm-harness";
const model = { ...getModel("openrouter", "deepseek/deepseek-v4-flash"), id: "deepseek/deepseek-v4.1-flash" };
const provider = createPiAiProvider(
  { systemPrompt: registry.require(agent).systemPrompt, model, apiKeyEnv: "OPENROUTER_API_KEY", reasoning: "medium" },
  { env: process.env, complete: completeSimple },
);

// Optional: serve multimodal inspection in front of the daemon client.
import { HarnessInspectionDaemon, MultimodalInspector, ProjectImageReader } from "@atomc/swarm-harness";
const reader = new ProjectImageReader(process.cwd(), { readFile, realpath });
const daemon = new HarnessInspectionDaemon(adapter, new MultimodalInspector(reader));

runAgent({ definition: registry.require(agent), daemon, provider, failure, signal, ... });
```

## Tests — 110 total (11 files)

- `test/agents.test.ts` — definitions, scopes, produces, grants, gates, prompts, default model, lookup,
  routing, duplicate rejection, and invalid tool/budget/scope config.
- `test/multimodal.test.ts` — mime sniffing, attachments, loading limits, inspection tool contracts,
  `HarnessInspectionDaemon` delegation/local serving, and `ProjectImageReader` traversal / absolute-path /
  symlink-escape / byte-cap cases.
- `test/providers/pi-ai.test.ts` — compile-level `completeSimple` seam, name encoding, context mapping
  (prompt/summary/tools/attachments/transcript), usage accounting, decision mapping + malformed output,
  AbortSignal forwarding/fallback, and key redaction in transport errors.
- `test/runner-multimodal.test.ts` — signal + transcript + attachment accumulation, and rejected-tool
  turns.

Coverage (v8, provider code **included**): **96.17 % stmts / 89.89 % branches / 99.2 % funcs / 97.13 %
lines**. Exclusions are only `src/index.ts`, `src/daemon-adapter.ts` and `src/providers/index.ts`
(re-export only).

## How to verify (exact commands, repo root)

```bash
pnpm install               # or --frozen-lockfile once the lockfile importer below is integrated
pnpm --filter @atomc/core-ir build
pnpm --filter @atomc/daemon-client build
pnpm --filter @atomc/swarm-harness test
pnpm --filter @atomc/swarm-harness test:coverage   # delete packages/swarm-harness/ts/coverage afterwards
pnpm --filter @atomc/swarm-harness typecheck
pnpm --filter @atomc/swarm-harness build
pnpm exec biome check packages/swarm-harness/ts/src packages/swarm-harness/ts/test packages/swarm-harness/ts/vitest.config.ts
pnpm exec turbo run build test typecheck
```

All pass locally (macOS arm64, Node 25.1.0, pnpm 10.30.3).

## Root changes needed (pnpm-lock.yaml only)

`@mariozechner/pi-ai` is already in the pnpm catalog (PLAN §2), so `pnpm-workspace.yaml` needs no edit.
The package manifest now declares it, so `pnpm-lock.yaml` must gain the resolution. Run
`pnpm install` and commit the lockfile; the importer delta is:

```yaml
# catalogs:
    '@mariozechner/pi-ai':
      specifier: ^0.73.1
      version: 0.73.1

# importers → packages/swarm-harness/ts → dependencies:
      '@mariozechner/pi-ai':
        specifier: 'catalog:'
        version: 0.73.1(ws@8.22.1)(zod@4.6.7)
```

plus the transitive `packages:` resolutions pnpm adds (Anthropic/AWS/Google/Mistral SDKs, `openai`,
`typebox`, `partial-json`, `proxy-agent`, `undici`, etc. — ~940 lock lines). No other root file changes.

## Design decisions

- **Real adapter, injected transport.** `completeSimple` is imported and compile-checked; tests inject a
  mock transport, so the package stays deterministic and offline in CI.
- **Secret references, not secrets.** Config stores `apiKeyEnv`; the factory resolves from injected env.
- **Root-confined inspection by construction.** Absolute/traversal rejected pre-I/O; `realpath`
  containment blocks symlink escapes; injectable reader keeps it testable and host-agnostic.
- **Additive runner plumbing.** Only signal/transcript/attachment forwarding was added; the state
  machine, locks, gates and budgets are unchanged.
- **Duplicate ids are errors.** Overrides are done by constructing a registry with the desired definitions
  rather than mutating in place.

## Deviations from contract

None. Lock scopes, holder id format, agent ids, gate ids/owners, node names and `produces`/`/meta` rules
match the frozen contracts. Additive protocol changes: `ModelRequest.attachments` and
`ModelRequest.signal`. `vitest.config.ts` no longer excludes substantive provider code.

## Open issues

- The pi-ai catalog in v0.73.1 does not list `deepseek/deepseek-v4.1-flash`; the frozen id is obtained by
  overriding `id` on `getModel("openrouter", "deepseek/deepseek-v4-flash")` (as shown in the README).
  When pi-ai's catalog gains the id, the override can be dropped.
- `dagTargets` remain unset on the definitions because Phase 4 watch/DAG node ids are not frozen yet.
- `permittedTools` use plugin namespaces (`atopile:*`, …) plus the two `harness:*` grants; exact tool
  names arrive with Phase 4, and the runner re-checks against daemon discovery.
- Streaming token accounting is not implemented (single `complete` call per turn); usage is taken from
  the final assistant message.

## Notes on the brief

The brief is present in the orchestrator's main checkout (it was not yet committed to `origin/main` at
the time of this branch). This WP implements its numbered deliverables, including the review follow-up
items. No frozen contract or out-of-scope file (daemon, CLI, Studio, root, lockfile) was modified.
