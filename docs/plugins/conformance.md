# Conformance

::: info Planned
The conformance kit ships with the plugin SDK in Phase 2 (WP-2.1/WP-2.2). Every built-in plugin will
run it in CI.
:::

`@atomc/plugin-sdk` and `atomc-plugin-sdk` will ship a `conformance()` helper that loads a manifest
and checks the plugin is well-formed and callable before it ever touches real hardware.

## What the kit checks

- **Manifest validity** against the [manifest schema](/plugins/manifest).
- **Runtime resolvable** — the `runtime.python` / `runtime.ts` entrypoint actually exports a plugin.
- **Registration complete** — every `watches[].id`, `gates[].id` and `tools[].name` declared in the
  manifest is registered at runtime, and nothing is registered that the manifest does not declare.
- **Write scope respected** — the plugin declares `produces[]`, and a static check flags writes
  outside it.
- **Tools callable** — each tool's `input_schema` validates a canonical happy-path input and the
  handler runs against a fake host.
- **Gates deterministic** — a gate run twice on the same `(IR rev, artifacts, cache)` yields the same
  `status`, and emits a schema-valid [`GateResult`](/architecture/contracts/gate-result).

## Running it

```bash
# TypeScript plugins
pnpm test        # includes conformance()

# Python plugins
uv run pytest    # the plugin-sdk registers conformance as a pytest plugin
```

Built-in plugins are required to run conformance in CI; third-party plugins are encouraged to.
