<!--
Conventional Commit summary of this PR, e.g. "feat(core-ir): validate refs on load".
Reference the work package: "WP-1.1 core-ir-py".
-->

## Summary

<!-- What changed and why. Link `PLAN.md` sections / contracts where relevant. -->

## Work package

<!-- e.g. WP-1.1 `core-ir-py` -->

## Definition of done

- [ ] Commits are Conventional Commits; branch is up to date with `main`
- [ ] Package tests pass (`uv run pytest` and/or `pnpm --filter <pkg> test`)
- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass (Python)
- [ ] `uv run mypy` passes (Python, strict)
- [ ] `pnpm exec turbo run typecheck` passes (TS) and `pnpm exec biome check <paths>` is clean
- [ ] `pnpm exec turbo run contract` passes if contracts/IR schema are touched
- [ ] Versions remain in lock-step: `python3 scripts/release/sync-versions.py --check`
- [ ] Changeset added for user-visible changes (`pnpm changeset`)
- [ ] Docs updated (README/handoff/architecture) where behaviour changed
- [ ] No edits outside owned paths; root changes requested in the handoff if needed

## Verification

<!-- Exact commands a reviewer can run, plus the CI run link. -->

## Handoff

<!-- Link the work-package handoff, e.g. docs/plan/handoffs/WP-1.1.md, if applicable. -->
