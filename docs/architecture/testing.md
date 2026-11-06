# Testing model

The test suite covers package units, cross-language contracts, RPC integration and desktop-browser behavior. Most tests need neither vendor credentials nor hardware. The hardware tests are scoped separately from checks that can run on every PR.

| Layer                     | Tooling                                                                                                         | Where                     | Gate in CI                                                                                                    |
| ------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------- |
| **Unit (Py)**             | pytest 9, hypothesis, `pytest-asyncio`                                                                          | each Py package           | required                                                                                                      |
| **Unit (TS)**             | vitest 5                                                                                                        | each TS package           | required                                                                                                      |
| **Static**                | ruff + `mypy --strict`; biome + `tsc (tsgo) --noEmit`                                                           | root                      | required                                                                                                      |
| **Schema contract**       | Pydantic → JSON Schema → TS types; round-trip every fixture; committed `schema.json` snapshot                   | `tests/contract`          | required                                                                                                      |
| **RPC contract**          | daemon in-proc, driven by the TS client; golden request/response JSON                                           | `tests/contract`          | required                                                                                                      |
| **Plugin conformance**    | `conformance()` loads a manifest and checks watches/gates/tools are registered and callable                     | plugin dirs               | required                                                                                                      |
| **Golden artifacts**      | `.repl`, `.resc`, BOM CSV, jig `.step` bbox/volume/pogo coordinates vs committed goldens                        | `tests/e2e`               | required (Linux)                                                                                              |
| **Hardware kernel smoke** | atopile compile; build123d jig; Renode boots firmware and asserts UART banner                                   | `tests/e2e`, Docker       | required Linux; nightly macOS                                                                                 |
| **Swarm harness**         | scripted fake provider; versioned recorded sessions replayed by a `ReplayProvider`; fixture-daemon E2E of the transactional loop; seeded budget invariants; real `atomcd serve` + WebSocket RPC `converge()` E2E through `DaemonClientAdapter` (conflict retry, abort lock cleanup); secret-free session reports | `packages/swarm-harness`, `tests/swarm`  | required (offline fakes + replay); real-daemon E2E required once the `tests/swarm` workspace entry lands; live-provider runs opt-in |
| **Vendor adapters**       | `httpx` + recorded cassettes (`respx`)                                                                          | `plugins/plugin-sourcing` | required (cassettes)                                                                                          |
| **Mutation/fuzz**         | hypothesis on IR patches + JSON-patch transactions                                                              | core-ir, daemon           | required                                                                                                      |
| **Perf budget**           | warm-kernel example build < 10 s; IR transact p99 < 20 ms                                                       | nightly                   | advisory                                                                                                      |
| **Studio unit**           | Vitest + jsdom; injected `StudioApi` fakes and no daemon/network                                                | `apps/atomc-studio`       | required with coverage floor                                                                                  |
| **Studio browser/a11y**   | Playwright Chromium, responsive viewport checks, keyboard flow, axe WCAG 2.1 A/AA                               | CI                        | required                                                                                                      |
| **Docs**                  | VitePress build, schema browser renders                                                                         | `docs.yml`                | required                                                                                                      |

## Coverage floors

| Package                                            | Floor                                                |
| -------------------------------------------------- | ---------------------------------------------------- |
| `core-ir`, `daemon`, `plugin-sdk`, `swarm-harness` | 85 % lines                                           |
| `cli`                                              | 85 % lines, functions, branches and statements       |
| `studio`                                           | 80 % lines/statements, 75 % branches, 70 % functions |
| plugins                                            | 70 % lines                                           |

## Why goldens and cassettes

The hardware kernels and vendor APIs are the flakiest part of the system. Goldens pin the byte-level
outputs of Renode scripts, fab quotes and generated CAD geometry; cassettes pin vendor HTTP. Live
calls only happen nightly with secrets present. This keeps PRs deterministic while still exercising
the real integrations on a schedule.
