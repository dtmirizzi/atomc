"""Worker child entrypoint helpers (the loop itself runs in a spawned process)."""

from __future__ import annotations

import json

import pytest
from atomcd.kernels.worker_runner import describe_host, format_exception, load_factory


def test_load_factory_resolves_dotted_path() -> None:
    factory = load_factory("json:dumps")
    assert factory is json.dumps


def test_load_factory_rejects_invalid_path() -> None:
    with pytest.raises(ValueError, match="invalid factory path"):
        load_factory("no-colon")


def test_load_factory_missing_attribute_raises() -> None:
    with pytest.raises(AttributeError):
        load_factory("json:not_here")


def test_describe_host_reports_pid() -> None:
    info = describe_host()
    assert info["pid"] > 0
    assert isinstance(info["host"], str)


def test_format_exception_includes_message() -> None:
    text = format_exception(RuntimeError("kaboom"))
    assert "RuntimeError" in text
    assert "kaboom" in text
