"""atomc Renode plugin.

Public entry point: ``plugin`` (a class decorated with ``@atomc_plugin``). Importing this package
validates the manifest but performs no I/O, network access or Renode execution.
"""

from __future__ import annotations

from .analysis import MAX_EVIDENCE_CHARS, BootVerdict, classify_boot, tail
from .derive import (
    DEFAULT_BOOT_MARKERS,
    DEFAULT_TIMEOUT_S,
    RENODE_BASE_PLATFORM,
    DerivationError,
    GeneratedScripts,
    boot_markers,
    firmware_view,
    generate_repl,
    generate_resc,
    generate_scripts,
    matrix_view,
    peripherals_view,
    split_pin,
    unsupported_mcu_reason,
)
from .manifest_data import MANIFEST
from .plugin import MATRIX_SCAN_SKIP_REASON, RenodePlugin, manifest_path, plugin
from .runner import (
    RenodeRunner,
    RenodeRunResult,
    SubprocessRenodeRunner,
    find_renode_binary,
    headless_args,
)

__all__ = [
    "DEFAULT_BOOT_MARKERS",
    "DEFAULT_TIMEOUT_S",
    "MANIFEST",
    "MATRIX_SCAN_SKIP_REASON",
    "MAX_EVIDENCE_CHARS",
    "RENODE_BASE_PLATFORM",
    "BootVerdict",
    "DerivationError",
    "GeneratedScripts",
    "RenodePlugin",
    "RenodeRunResult",
    "RenodeRunner",
    "SubprocessRenodeRunner",
    "boot_markers",
    "classify_boot",
    "find_renode_binary",
    "firmware_view",
    "generate_repl",
    "generate_resc",
    "generate_scripts",
    "headless_args",
    "manifest_path",
    "matrix_view",
    "peripherals_view",
    "plugin",
    "split_pin",
    "tail",
    "unsupported_mcu_reason",
]
