# Conformance

The TypeScript SDK provides `conformance()` and input-schema validation helpers; the Python SDK provides manifest/conformance test helpers. Both operate against fixture manifests or a fake host. Built-in hardware plugins have not landed yet, so the project does not claim plugin conformance for atopile/Renode/CAD/sourcing adapters.

## What the kit checks

- **Manifest validity** against the [manifest schema](/plugins/manifest).
- **Tool input validation** against each declared JSON Schema.
- **Registration/runtime checks** when tests supply the plugin implementation and fake host.
- **Gate repeatability** when plugin tests run the same gate twice against the same revision/artifacts/cache.

## Running it

```bash
# TypeScript plugin package
pnpm --filter @atomc/plugin-sdk test

# Python plugin SDK
uv run pytest packages/plugin-sdk/python/tests
```

The SDK helper tests run in CI. When built-in hardware plugins land, each plugin package must add its own conformance tests. The current suite does not test hardware plugins that are not present.
