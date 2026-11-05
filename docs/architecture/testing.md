# Testing model

"Green" for atomc means more than unit tests. Because the product spans two languages, five hardware
kernels and a multi-agent loop, the test strategy is layered and each layer has a required CI gate.

| Layer | Tooling | Where | Gate in CI |
| ----- | ------- | ----- | ---------- |
| **Unit (Py)** | pytest 9, hypothesis, `pytest-asyncio` | each Py package | required |
| **Unit (TS)** | vitest 5 | each TS package | required |
| **Static** | ruff + `mypy --strict`; biome + `tsc (tsgo) --noEmit` | root | required |
| **Schema contract** | Pydantic → JSON Schema → TS types; round-trip every fixture; committed `schema.json` snapshot | `tests/contract` | required |
| **RPC contract** | daemon in-proc, driven by the TS client; golden request/response JSON | `tests/contract` | required |
| **Plugin conformance** | `conformance()` loads a manifest and checks watches/gates/tools are registered and callable | plugin dirs | required |
| **Golden artifacts** | `.repl`, `.resc`, BOM CSV, jig `.step` bbox/volume/pogo coordinates vs committed goldens | `tests/e2e` | required (Linux) |
| **Hardware kernel smoke** | atopile compile; build123d jig; Renode boots firmware and asserts UART banner | `tests/e2e`, Docker | required Linux; nightly macOS |
| **Swarm harness** | deterministic fake provider + versioned recorded-session fixtures replayed by a `ReplayProvider`; fixture daemon E2E of the `runAgent` loop; seeded budget invariants; secret-free session report; live run nightly with cap | `packages/swarm-harness` | required (fake/replay), nightly (live) |
| **Vendor adapters** | `httpx` + recorded cassettes (`respx`) | `plugins/plugin-sourcing` | required (cassettes) |
| **Mutation/fuzz** | hypothesis on IR patches + JSON-patch transactions | core-ir, daemon | required |
| **Perf budget** | warm-kernel example build < 10 s; IR transact p99 < 20 ms | nightly | advisory |
| **Docs** | VitePress build, link check, schema browser renders | `docs.yml` | required |

## Coverage floors

| Package | Floor |
| ------- | ----- |
| `core-ir`, `daemon`, `plugin-sdk`, `swarm-harness` | 85 % lines |
| plugins | 70 % lines |

## Why goldens and cassettes

The hardware kernels and vendor APIs are the flakiest part of the system. Goldens pin the byte-level
outputs of Renode scripts, fab quotes and generated CAD geometry; cassettes pin vendor HTTP. Live
calls only happen nightly with secrets present. This keeps PRs deterministic while still exercising
the real integrations on a schedule.
