# Swarm recording fixtures (WP-3.5)

Committed recordings of `ModelProvider` decisions, replayed deterministically in
CI. No live model, network, API key or vendor service is involved.

## Layout

```
test/fixtures/
├── recordings.ts        # zod schema, validation, redaction, ReplayProvider
├── fixture-daemon.ts    # deterministic in-memory HarnessDaemon
├── report.ts            # secret-free session report utility
├── support.ts           # shared test helpers
├── sessions/*.json      # the recordings
└── README.md            # this file
```

## Format (`sessions/*.json`)

`handlebars`-free, versioned JSON. Validated by `RecordedSessionSchema` before
use; a file that fails validation throws `RecordingValidationError` naming the
fixture.

```jsonc
{
  "schema_version": 1,
  "id": "ee-erc-pass", // kebab-case, unique
  "description": "what the session proves",
  "agent": "ee-agent", // one of the four frozen agent ids
  "model": { "provider": "fake", "model": "recorded-1" },
  "failure": {
    /* GateFailure that woke the agent */
  },
  "turns": [
    {
      "turn": 0, // 0-based; must be contiguous from 0
      "decision": {
        "kind": "patch",
        "proposal": {
          /* … */
        },
        "usage": { "costMinor": 5 }
      },
      "request": { "remainingCostMinor": 100, "toolNames": [] } // optional
    }
  ]
}
```

Rules enforced by the schema:

- `schema_version` is exactly `1` (bump `RECORDING_SCHEMA_VERSION` and migrate on
  any breaking change).
- `agent` is one of `ee-agent`, `fw-agent`, `mech-agent`, `ops-agent`.
- `kind: "patch"` requires `proposal`; `kind: "tool"` requires `tool`.
- JSON Patch ops must be valid RFC 6902 ops (`isJsonPatchOp`).
- `turn` values are contiguous and 0-based.

## Replay

`createReplayProvider(session)` returns a `ModelProvider` that answers the
`n`-th `nextTurn` with the `n`-th recorded decision and asserts the request's
`turn` matches. Decisions are deep-cloned so tests cannot mutate the fixture.
When the recording is exhausted the provider returns
`{ kind: "give_up", reason: "recording exhausted" }`, keeping `runAgent` bounded.

## Recording a new fixture

There is **no** automated recorder against a live provider on purpose (no
credentials, no nondeterministic sessions in PR CI). Add a fixture by hand:

1. Capture the gate failure and the decisions a specialist should take.
2. Copy an existing file in `sessions/`, give it a new kebab-case `id`, and edit
   the turns; keep `turn` contiguous from `0`.
3. Run `pnpm --filter @atomc/swarm-harness test`. `recordings.test.ts` loads and
   validates every file in `sessions/`, so a malformed fixture fails loudly.
4. Never paste tokens, API keys or datasheet secrets. `redactRecording` scrubs
   sensitive keys and bearer-shaped strings defensively, but fixtures must be
   clean at rest.

## Nightly live runs

Live-model sessions remain a separate, opt-in, budget-capped nightly job. They
are **not** part of the PR-required suite and are not implemented here; see
`docs/architecture/testing.md`.
