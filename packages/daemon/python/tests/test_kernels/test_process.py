"""Supervised worker-process behavior: spawn, serialize, timeout, crash, restart, cleanup."""

from __future__ import annotations

import multiprocessing
from concurrent.futures import ThreadPoolExecutor

import pytest
from atomcd.kernels.errors import (
    WorkerCallError,
    WorkerCrashedError,
    WorkerStartError,
    WorkerTimeoutError,
)
from atomcd.kernels.process import WorkerProcess

FAKE = "atomcd.kernels.testing:make_fake_engine"


def test_start_ping_and_graceful_close() -> None:
    worker = WorkerProcess(FAKE, name="test")
    try:
        worker.start()
        assert worker.alive
        pid = worker.pid
        result = worker.request("ping")
        assert result["pong"] is True
        assert result["pid"] == pid
        assert worker.request("echo", {"x": 1}) == {"op": "echo", "kwargs": {"x": 1}}
        assert worker.start_count == 1
    finally:
        worker.close()
    assert worker.alive is False
    assert worker.closed is True


def test_requests_are_serialized_on_one_worker() -> None:
    worker = WorkerProcess(FAKE, name="test")
    try:
        worker.start()
        pid = worker.pid
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(worker.request, "sleep", {"seconds": 0.05}) for _ in range(5)]
            results = [future.result(timeout=10) for future in futures]
        assert all(result["slept"] == 0.05 for result in results)
        assert worker.start_count == 1
        assert worker.pid == pid
        assert worker.restart_count == 0
    finally:
        worker.close()


def test_timeout_terminates_and_respawns() -> None:
    worker = WorkerProcess(FAKE, name="test", job_timeout_s=0.4)
    try:
        worker.start()
        original_pid = worker.pid
        with pytest.raises(WorkerTimeoutError):
            worker.request("sleep", {"seconds": 3.0})
        assert worker.restart_count == 1
        assert worker.alive is False
        assert worker.request("ping")["pid"] != original_pid
        assert worker.restart_count == 1  # respawn already accounted for
    finally:
        worker.close()


def test_crash_is_detected_and_worker_restarts() -> None:
    worker = WorkerProcess(FAKE, name="test")
    try:
        worker.start()
        original_pid = worker.pid
        with pytest.raises(WorkerCrashedError):
            worker.request("crash")
        assert worker.restart_count == 1
        assert worker.request("ping")["pid"] != original_pid
    finally:
        worker.close()


def test_structured_call_error_keeps_worker_alive() -> None:
    worker = WorkerProcess(FAKE, name="test")
    try:
        worker.start()
        pid = worker.pid
        with pytest.raises(WorkerCallError) as excinfo:
            worker.request("boom")
        assert excinfo.value.kind == "RuntimeError"
        assert worker.alive is True
        assert worker.pid == pid
        assert worker.restart_count == 0
    finally:
        worker.close()


def test_max_restarts_is_enforced() -> None:
    worker = WorkerProcess(FAKE, name="test", max_restarts=0)
    try:
        worker.start()
        with pytest.raises(WorkerCrashedError):
            worker.request("crash")
        with pytest.raises(WorkerStartError):
            worker.request("ping")
    finally:
        worker.close()


def test_startup_failure_reports_start_error() -> None:
    worker = WorkerProcess("atomcd.kernels.testing:does_not_exist", name="test")
    with pytest.raises(WorkerStartError):
        worker.start()
    assert worker.alive is False


def test_invalid_factory_path_reports_start_error() -> None:
    worker = WorkerProcess("not-a-valid-path", name="test")
    with pytest.raises(WorkerStartError):
        worker.start()


def test_close_leaves_no_orphan() -> None:
    worker = WorkerProcess(FAKE, name="test")
    worker.start()
    pid = worker.pid
    assert pid is not None
    worker.close()
    assert not worker.alive
    assert pid not in {child.pid for child in multiprocessing.active_children()}


def test_request_after_close_is_rejected() -> None:
    worker = WorkerProcess(FAKE, name="test")
    worker.start()
    worker.close()
    with pytest.raises(WorkerCrashedError):
        worker.request("ping")
