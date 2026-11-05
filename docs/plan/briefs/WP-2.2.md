# WP-2.2 `plugin-sdk-py` — Python plugin SDK

Read `_common.md`, `PLAN.md` §§2, 4, 9, `plugin-manifest.md`, `rpc.md`, and `gate-result.md` fully. The manifest and RPC contracts are frozen. WP-2.1 is writing the canonical generated manifest JSON Schema at `packages/plugin-sdk/schema/atomc-plugin.schema.json`; you may scaffold from the frozen manifest doc, but do not declare complete until your validators consume that shared schema from the merged WP-2.1 branch. Coordinate/poll for its schema early; do not invent Python-only fields.

## Owned paths
- `packages/plugin-sdk/python/**`
- `packages/plugin-sdk/README-python.md`

Do not edit TS SDK, daemon, contracts, root workspace/lock files. If root uv workspace changes are needed, list them in the handoff for the orchestrator.

## Deliverables
1. Distribution `atomc-plugin-sdk` under `packages/plugin-sdk/python/` (hatchling, `src/atomc_plugin_sdk`, `py.typed`). Dependencies: `pydantic>=2.14` (already in core IR), `jsonschema` latest stable only if needed for the shared schema; otherwise validate JSON Schema with the existing standard-supported validator chosen explicitly. Add `atomc-core-ir` as a workspace dependency only for `PluginHost` transaction types if appropriate; avoid cyclic imports.
2. `manifest.py`: load `atomc-plugin.json` and validate against the exact shared `atomc-plugin.schema.json` using Draft 2020-12; expose `load_manifest(path|dict)`, `validate_manifest(data) -> PluginManifest`, stable path-oriented errors. Verify schema `manifest_version` and fail clearly if missing/unsupported. Tests must point at the canonical WP-2.1 schema once available (no copied divergent schema committed).
3. `plugin.py`: `@atomc_plugin(manifest=...)` decorator/factory that attaches parsed manifest as `__atomc_manifest__`, supports class/factory/instance use as documented, and has no import-time plugin side effects. Export a `PluginHost` Protocol with `ir_get`, `ir_transact` (path, base_rev, ops relative to path, holder), `artifact_root`, `logger`, `cache`, and event interface; types should not import daemon internals.
4. `conformance.py`: pytest-friendly `conformance(plugin)` validates manifest, checks all declared handlers exist and signatures are callable, rejects undeclared handlers, duplicate names, invalid produces scopes, and malformed tool/gate definitions. Return structured findings or raise a concise `PluginConformanceError`.
5. Tests: manifest valid/invalid fixtures shared with TS if feasible; schema strictness, unknown keys, missing runtime, invalid pointers/scope, duplicate IDs, handler mismatch, simple fake host and plugin conformance. No network, hardware or daemon required.
6. `README-python.md`: install/use authoring guide, explain the shared JSON Schema origin and how this SDK stays aligned with TS.

## Definition of done
`uv sync --all-packages`, `uv run pytest packages/plugin-sdk/python -q`, `uv run ruff check packages/plugin-sdk/python`, `uv run ruff format --check packages/plugin-sdk/python`, `uv run mypy --strict packages/plugin-sdk/python/src/atomc_plugin_sdk` all green. Add `docs/plan/handoffs/WP-2.2.md`, commit/push `wp/2.2-plugin-sdk-py`. Handoff must state schema path/commit consumed and any needed root changes.
