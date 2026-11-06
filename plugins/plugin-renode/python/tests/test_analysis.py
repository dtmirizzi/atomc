"""Boot-output classification and evidence bounding."""

from __future__ import annotations

from atomc_plugin_renode.analysis import MAX_EVIDENCE_CHARS, classify_boot, tail
from atomc_plugin_renode.runner import RenodeRunResult

MARKERS = ("QMK", "atomc")


def _result(
    stdout: str = "",
    stderr: str = "",
    *,
    exit_code: int | None = 0,
    timed_out: bool = False,
) -> RenodeRunResult:
    return RenodeRunResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        duration_ms=10,
    )


def test_banner_passes() -> None:
    verdict = classify_boot(_result(stdout="booting... QMK ready\n"), MARKERS)
    assert verdict.status == "PASS"
    assert "QMK" in verdict.summary


def test_banner_passes_even_after_timeout() -> None:
    verdict = classify_boot(_result(stdout="atomc up", timed_out=True), MARKERS)
    assert verdict.status == "PASS"


def test_hardfault_fails() -> None:
    verdict = classify_boot(_result(stdout="[ERROR] HardFault exception\n"), MARKERS)
    assert verdict.status == "FAIL"
    assert verdict.fault is True


def test_timeout_without_banner_fails() -> None:
    verdict = classify_boot(_result(stdout="starting", timed_out=True), MARKERS)
    assert verdict.status == "FAIL"
    assert "timeout" in verdict.summary


def test_nonzero_exit_fails() -> None:
    verdict = classify_boot(_result(exit_code=2), MARKERS)
    assert verdict.status == "FAIL"
    assert "exit" in verdict.summary


def test_clean_but_bannerless_fails() -> None:
    verdict = classify_boot(_result(stdout="machine created"), MARKERS)
    assert verdict.status == "FAIL"


def test_tail_bounds_output() -> None:
    text = "x" * (MAX_EVIDENCE_CHARS + 500)
    bounded = tail(text)
    assert len(bounded) == MAX_EVIDENCE_CHARS
    assert text.endswith(bounded)


def test_tail_short_and_zero() -> None:
    assert tail("abc") == "abc"
    assert tail("abc", 0) == ""
