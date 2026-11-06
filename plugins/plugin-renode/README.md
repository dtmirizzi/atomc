# plugin-renode

Derives Renode platform/run scripts from the atomc system IR and runs **honest** emulation gates.
Renode is a regression aid: it never claims USB HID or matrix behaviour that the generic STM32F4
model does not demonstrate.

## Surface

| Kind | Id | Behaviour |
| --- | --- | --- |
| watch | `renode:generate` | invalidated by `/firmware` and `/simulation`; regenerates scripts |
| tool | `renode_generate` | writes `<slug>.repl` + `<slug>.resc`, records paths under `/simulation/platform` |
| gate | `gate:fw.renode_boot` | `SKIP` if binary/MCU/ELF missing; `PASS` only on a configured banner with no fault; otherwise `FAIL` |
| gate | `gate:fw.matrix_scan` | always `SKIP` — requires HIL board + pogo fixture |

The `renode_generate` tool name uses `_` rather than `.` because the frozen manifest schema
(`atomc-plugin.schema.json`) restricts tool names to `^[a-z0-9]+(?:[_-][a-z0-9]+)*$`.

## Generated files

- `.repl` — `using "platforms/cpus/stm32f4.repl"` plus `//` comments enumerating the matrix GPIO
  ports and the IR peripheral map. Renode `.repl` comments **must** be `//`; `#` breaks loading.
- `.resc` — loads the `kind: elf` artifact from `/firmware/targets/*/artifacts` and `start`s the
  machine. The run window is enforced by the subprocess timeout, not by the script.

Generation is pure and byte-deterministic for the same IR plus the same explicit
`repl_path`/`elf_path`/`timeout_s` arguments.

## Boot markers

`gate:fw.renode_boot` looks for the first of `DEFAULT_BOOT_MARKERS` (`QMK`, `atomc`) in captured
stdout/stderr, or the list in `ext.renode.boot_markers` when present. A run with no banner is a
`FAIL`, not a silent pass.

## Test

```bash
uv run pytest plugins/plugin-renode/python
uv run ruff check plugins/plugin-renode/python
uv run ruff format --check plugins/plugin-renode/python
uv run mypy plugins/plugin-renode/python/src
```

Tests need **no** Renode install: the subprocess runner is injected with a fake in tests.

See `docs/hil-checklist.md` in this package for what must be proven on real hardware.
