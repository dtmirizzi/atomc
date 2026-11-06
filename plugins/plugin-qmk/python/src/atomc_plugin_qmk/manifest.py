"""Manifest for the ``plugin-qmk`` atomc plugin.

The source-tree manifest lives at ``plugins/plugin-qmk/atomc-plugin.json`` so the daemon can
discover it without importing Python. This module carries the same document as a Python literal
for the installed entry point; ``tests/test_manifest.py`` asserts the two stay byte-identical
after JSON canonicalisation.
"""

from __future__ import annotations

from typing import Any

PLUGIN_NAME = "qmk"
PLUGIN_VERSION = "0.1.0"

MANIFEST: dict[str, Any] = {
    "manifest_version": "0.1.0",
    "name": PLUGIN_NAME,
    "version": PLUGIN_VERSION,
    "description": "IR to QMK keyboard definition derivation and qmk compile verification",
    "atomc": ">=0.0.1 <0.2.0",
    "runtime": {"python": "atomc_plugin_qmk:plugin", "ts": "./dist/qmk.js"},
    "watches": [
        {"id": "qmk:keyboard", "ir": ["/keyboard"]},
        {"id": "qmk:firmware", "ir": ["/firmware"]},
    ],
    "produces": ["/firmware"],
    "gates": [
        {
            "id": "gate:fw.matrix_pins_match_ir",
            "severity": "blocking",
            "owner_agent": "fw-agent",
            "after": ["qmk:keyboard"],
            "handler": "matrix_pins_match_ir",
        },
        {
            "id": "gate:fw.qmk_compile",
            "severity": "blocking",
            "owner_agent": "fw-agent",
            "after": ["qmk:keyboard", "qmk:firmware"],
            "handler": "run_qmk_compile",
        },
    ],
    "tools": [
        {
            "name": "qmk_generate",
            "description": "Derive QMK keyboard.json and the default keymap from the IR",
            "input_schema": {
                "type": "object",
                "properties": {"keymap": {"type": "string", "default": "default"}},
                "additionalProperties": False,
            },
            "agents": ["fw-agent"],
            "mutates": False,
            "handler": "qmk_generate_tool",
        },
        {
            "name": "qmk_compile",
            "description": "Derive QMK sources and compile firmware through the qmk CLI",
            "input_schema": {
                "type": "object",
                "properties": {
                    "keymap": {"type": "string", "default": "default"},
                    "qmk_home": {"type": "string"},
                },
                "additionalProperties": False,
            },
            "agents": ["fw-agent"],
            "mutates": True,
            "handler": "qmk_compile_tool",
        },
    ],
    "cli": [],
    "ui": [],
}

__all__ = ["MANIFEST", "PLUGIN_NAME", "PLUGIN_VERSION"]
