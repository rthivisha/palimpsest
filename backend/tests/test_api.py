"""Unit tests for PALIMPSEST API, SSE streaming, Concurrency, and Telemetry.

Covers:
1. Exact SSE event ordering & payload key sets.
2. Unsafe input emitting final(REJECTED_UNSAFE).
3. Failing run ending in finalize_fail with no trailing retry.
4. Single error event on backend failure.
5. Large integer (> 2^53 - 1) string round-trip and prompt integer preservation.
6. HTTP 429 on concurrent run requests.
7. Client disconnect and cancellation handling.
8. Host-header check middleware (Vite proxy support).
9. REST endpoints (/api/health, /api/history, /api/runs/{id}, /api/stats, /api/examples).
10. Concurrent Z3 verification across threads with isolated contexts.
"""
import asyncio
import json
import threading
import time
from typing import Any, Dict, List, Tuple
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.api.routes_run import run_lock
from backend.app.core.verifier import verify_equivalence
from backend.app.llm.base import LLMBackendError
from backend.app.llm.fake import FakeLLMBackend
from backend.app.llm.prompts import build_messages
from backend.app.main import app
from backend.app.schemas import stringify_verification_values
from backend.app.telemetry.db import TelemetryDB, telemetry_db


@pytest.fixture(autouse=True)
def ensure_run_lock_released():
    """Guarantees that the global inference lock is free before and after each test."""
    if run_lock.locked():
        try:
            run_lock.release()
        except RuntimeError:
            pass
    yield
    if run_lock.locked():
        try:
            run_lock.release()
        except RuntimeError:
            pass


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Provides an isolated SQLite database instance for testing."""
    test_db_path = str(tmp_path / "test_palimpsest.sqlite")
    test_db = TelemetryDB(db_path=test_db_path)
    test_db.init_db()
    test_db.start_writer()

    # Patch global telemetry_db across modules
    monkeypatch.setattr("backend.app.api.routes_run.telemetry_db", test_db)
    monkeypatch.setattr("backend.app.api.routes_history.telemetry_db", test_db)
    monkeypatch.setattr("backend.app.api.routes_meta.telemetry_db", test_db)
    monkeypatch.setattr("backend.app.main.telemetry_db", test_db)

    yield test_db
    test_db.stop_writer(wait=True)


def parse_sse_events(sse_text: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Parses raw SSE stream text into a list of (event_type, payload_dict) tuples."""
    events = []
    blocks = sse_text.split("\n\n")
    for block in blocks:
        block = block.strip()
        if not block or block.startswith(":"):
            # Ignore empty blocks and SSE comments (heartbeat pings)
            continue
        event_name = None
        data_payload = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_payload = json.loads(line[len("data:"):].strip())
        if event_name:
            events.append((event_name, data_payload))
    return events


# ==============================================================================
# 1. SSE Event Ordering & Lifecycle Tests
# ==============================================================================

class TestSSEStreaming:
    """Verifies strict event ordering, frozen event sequences, and payload contracts."""

    def test_exact_event_ordering_success_run(self, temp_db):
        """Verifies that payload events arrive BEFORE node_finished in a normal 2-turn run."""
        client = TestClient(app)
        response = client.post(
            "/api/run",
            json={"expression": "(x ^ y) + 2 * (x & y)", "max_iterations": 5},
        )
        assert response.status_code == 200
        events = parse_sse_events(response.text)

        event_names = [e[0] for e in events]
        expected_sequence = [
            "run_started",
            "node_started",   # parse_ast
            "node_finished",  # parse_ast
            # Iteration 1 (SAT)
            "node_started",   # propose
            "proposal",
            "node_finished",  # propose
            "node_started",   # verify
            "verification",
            "node_finished",  # verify
            "retry",
            # Iteration 2 (UNSAT / Verified)
            "node_started",   # propose
            "proposal",
            "node_finished",  # propose
            "node_started",   # verify
            "verification",
            "node_finished",  # verify
            "node_started",   # finalize_success
            "node_finished",  # finalize_success
            "final",
        ]
        assert event_names == expected_sequence

        # Verify that payload events occurred strictly BEFORE node_finished
        for i, (name, _) in enumerate(events):
            if name == "proposal":
                assert events[i - 1] == ("node_started", {"node": "propose"})
                assert events[i + 1] == ("node_finished", {"node": "propose"})
            elif name == "verification":
                assert events[i - 1] == ("node_started", {"node": "verify"})
                assert events[i + 1] == ("node_finished", {"node": "verify"})

        # Check final event payload
        final_payload = events[-1][1]
        assert final_payload["status"] == "VERIFIED_EQUIVALENT"
        assert final_payload["final_expr"] == "x + y"
        assert final_payload["obf_nodes"] == 9
        assert final_payload["final_nodes"] == 3
        assert final_payload["compression_pct"] == 66.67
        assert final_payload["attempts"] == 2
        assert final_payload["reason"] is None

    def test_rejected_unsafe_emits_final(self, temp_db):
        """Unsafe inputs are rejected by the gate, ending in final(REJECTED_UNSAFE) with obf_nodes=0."""
        client = TestClient(app)
        response = client.post(
            "/api/run",
            json={"expression": "__import__('os').system('calc')", "max_iterations": 5},
        )
        assert response.status_code == 200
        events = parse_sse_events(response.text)

        event_names = [e[0] for e in events]
        assert event_names == [
            "run_started",
            "node_started",   # parse_ast
            "node_finished",  # parse_ast
            "final",
        ]

        run_started_payload = events[0][1]
        assert run_started_payload["obf_nodes"] == 0

        final_payload = events[-1][1]
        assert final_payload["status"] == "REJECTED_UNSAFE"
        assert final_payload["obf_nodes"] == 0
        assert final_payload["final_expr"] is None
        assert final_payload["attempts"] == 0
        assert "Security Gate Rejection" in final_payload["reason"]

    def test_failing_run_ends_in_finalize_fail_no_trailing_retry(self, temp_db, monkeypatch):
        """A failing run exhausts max iterations, ends in finalize_fail, and emits NO trailing retry."""
        monkeypatch.setenv("FAKE_SCENARIO", "always_wrong")
        client = TestClient(app)
        response = client.post(
            "/api/run",
            json={"expression": "(x ^ y) + 2 * (x & y)", "max_iterations": 2},
        )
        assert response.status_code == 200
        events = parse_sse_events(response.text)

        event_names = [e[0] for e in events]
        expected_sequence = [
            "run_started",
            "node_started",   # parse_ast
            "node_finished",  # parse_ast
            # Iteration 1
            "node_started",   # propose
            "proposal",
            "node_finished",  # propose
            "node_started",   # verify
            "verification",
            "node_finished",  # verify
            "retry",          # Retry after iteration 1
            # Iteration 2 (Max iterations reached)
            "node_started",   # propose
            "proposal",
            "node_finished",  # propose
            "node_started",   # verify
            "verification",
            "node_finished",  # verify
            # NO trailing retry! Directly to finalize_fail
            "node_started",   # finalize_fail
            "node_finished",  # finalize_fail
            "final",
        ]
        assert event_names == expected_sequence

        final_payload = events[-1][1]
        assert final_payload["status"] == "FAILED"
        assert final_payload["attempts"] == 2
        assert final_payload["final_expr"] is None
        assert "Max iterations reached" in final_payload["reason"]

    def test_single_error_event_on_backend_failure(self, temp_db):
        """When the LLM backend crashes, exactly one error event is emitted, terminating the stream."""
        client = TestClient(app)

        with patch.object(FakeLLMBackend, "generate", side_effect=LLMBackendError("Ollama daemon unreachable")):
            response = client.post(
                "/api/run",
                json={"expression": "x + y", "max_iterations": 3},
            )
            assert response.status_code == 200
            events = parse_sse_events(response.text)

            event_names = [e[0] for e in events]
            assert event_names == [
                "run_started",
                "node_started",   # parse_ast
                "node_finished",  # parse_ast
                "node_started",   # propose
                "error",          # Single error event terminates stream
            ]

            error_payload = events[-1][1]
            assert "Ollama daemon unreachable" in error_payload["error"]

    def test_exact_payload_key_sets(self, temp_db):
        """Every event emitted strictly adheres to the frozen payload key schema."""
        expected_keys = {
            "run_started": {"run_id", "expression", "obf_nodes", "max_iterations", "backend"},
            "node_started": {"node"},
            "node_finished": {"node"},
            "proposal": {"iteration", "raw_output", "think", "candidate"},
            "verification": {"iteration", "candidate", "status", "latency_ms", "witness", "expected", "actual", "diff_bits"},
            "retry": {"iteration", "feedback_message"},
            "final": {"status", "final_expr", "obf_nodes", "final_nodes", "compression_pct", "total_ms", "attempts", "reason"},
        }

        client = TestClient(app)
        response = client.post(
            "/api/run",
            json={"expression": "(x ^ y) + 2 * (x & y)", "max_iterations": 5},
        )
        assert response.status_code == 200
        events = parse_sse_events(response.text)

        for event_name, payload in events:
            assert event_name in expected_keys, f"Unexpected event name: {event_name}"
            assert set(payload.keys()) == expected_keys[event_name], f"Key mismatch on {event_name}"


# ==============================================================================
# 2. String Serialization & Prompt Invariant Tests
# ==============================================================================

class TestStringSerialization:
    """Verifies stringification of 64-bit integers in API vs raw preservation in prompts."""

    def test_large_integer_string_round_trip(self):
        """Witness, expected, and actual values > 2^53 - 1 are stringified in SSE JSON."""
        data = {
            "iteration": 1,
            "witness": {"x": 18446744073709551615, "y": 9223372036854775808},
            "expected": 18446744073709551615,
            "actual": 0,
        }
        serialized = stringify_verification_values(data)
        assert serialized["witness"]["x"] == "18446744073709551615"
        assert serialized["witness"]["y"] == "9223372036854775808"
        assert serialized["expected"] == "18446744073709551615"
        assert serialized["actual"] == "0"

    def test_prompt_preserves_raw_integers(self):
        """Prompt builder preserves Python integer types matching teammate training data."""
        history = [
            {
                "iteration": 1,
                "candidate": "x ^ y",
                "raw_output": "x ^ y",
                "think": None,
                "status": "SAT",
                "latency_ms": 12.5,
                "witness": {"x": 18446744073709551615, "y": 1},
                "expected": 0,
                "actual": 18446744073709551614,
                "diff_bits": "1" * 64,
            }
        ]
        messages = build_messages(
            obfuscated_expr="x + y",
            history=history,
            tool_role="user",
        )
        prompt_content = messages[-1]["content"]
        assert "{'x': 18446744073709551615, 'y': 1}" in prompt_content
        assert "Expected: 0, Actual: 18446744073709551614" in prompt_content


# ==============================================================================
# 3. Concurrency, Locking, and Cancellation Tests
# ==============================================================================

class TestConcurrencyAndCancellation:
    """Verifies single-slot concurrency lock (HTTP 429) and cooperative client disconnect."""

    def test_concurrent_runs_return_429(self):
        """Concurrent run requests receive HTTP 429 with Retry-After: 5."""
        client = TestClient(app)

        # 1. Acquire the lock to simulate an active run
        acquired = run_lock.acquire(blocking=False)
        assert acquired, "Failed to acquire lock for test setup"

        try:
            # 2. Subsequent request must be rejected immediately with 429
            response = client.post(
                "/api/run",
                json={"expression": "x + y", "max_iterations": 3},
            )
            assert response.status_code == 429
            assert response.headers.get("retry-after") == "5"
            assert "Only 1 local run is supported" in response.json()["detail"]
        finally:
            run_lock.release()

    def test_disconnect_cancellation(self, temp_db, monkeypatch):
        """Client disconnect triggers cancellation and marks the database record as CANCELLED.

        State how:
        1. Set FAKE_SCENARIO=slow so inference sleeps in 0.1s increments checking should_cancel.
        2. The route handler instantiates cancel_event = threading.Event() and passes should_cancel to the worker.
        3. When a client disconnects or aborts, cancel_event.set() is invoked by the stream handler.
        4. Worker checks should_cancel at sleep interval, halts immediately at the node boundary,
           releases the single-slot concurrency lock, and records final_status as CANCELLED in telemetry.
        """
        monkeypatch.setenv("FAKE_SCENARIO", "slow")

        run_id = "test_cancel_disconnect_run"
        temp_db.record_run({
            "run_id": run_id,
            "expression": "(x ^ y) + 2 * (x & y)",
            "obf_nodes": 9,
            "final_status": "RUNNING",
            "backend": "fake",
            "max_iterations": 5,
        })

        cancel_event = threading.Event()
        event_queue = asyncio.Queue()
        loop = asyncio.new_event_loop()

        from backend.app.api.routes_run import run_synthesis_worker, run_lock

        # Acquire lock as route handler does
        assert run_lock.acquire(blocking=False)

        worker = threading.Thread(
            target=run_synthesis_worker,
            args=(
                run_id,
                "(x ^ y) + 2 * (x & y)",
                5,
                "fake",
                9,
                loop,
                event_queue,
                cancel_event,
            ),
        )
        worker.start()

        # Let worker enter iteration 1 FakeLLM sleep
        time.sleep(0.2)
        # Client disconnect triggers cancel_event
        cancel_event.set()

        worker.join(timeout=2.0)
        assert not worker.is_alive(), "Worker thread did not halt within timeout"

        # Lock was released in finally
        assert not run_lock.locked(), "Concurrency lock was not released on cancellation"

        temp_db.sync()
        run = temp_db.get_run(run_id)
        assert run is not None
        assert run["final_status"] == "CANCELLED"

    def test_concurrent_z3_separate_contexts(self):
        """Two concurrent threads executing verify_equivalence with isolated z3.Context() succeed."""
        results = {}

        def thread_task(name: str, expr1: str, expr2: str):
            res = verify_equivalence(expr1, expr2)
            results[name] = res

        t1 = threading.Thread(target=thread_task, args=("t1", "(x ^ y) + 2 * (x & y)", "x + y"))
        t2 = threading.Thread(target=thread_task, args=("t2", "a | b", "(a ^ b) | (a & b)"))

        t1.start()
        t2.start()
        t1.join(timeout=3.0)
        t2.join(timeout=3.0)

        assert results["t1"]["status"] == "QF_BV_UNSAT_64BIT_VERIFIED"
        assert results["t2"]["status"] == "QF_BV_UNSAT_64BIT_VERIFIED"


# ==============================================================================
# 4. Host-Header Middleware & REST Endpoint Tests
# ==============================================================================

class TestHostHeaderAndREST:
    """Verifies Host-header filtering for Vite proxy and all standard REST endpoints."""

    def test_host_header_middleware(self):
        """Allows localhost, 127.0.0.1, testserver, and rejects unauthorized hosts with 400."""
        client = TestClient(app)

        # Allowed host header
        res_allowed = client.get("/api/health", headers={"Host": "localhost:8000"})
        assert res_allowed.status_code == 200

        res_127 = client.get("/api/health", headers={"Host": "127.0.0.1:5173"})
        assert res_127.status_code == 200

        # Disallowed host header
        res_disallowed = client.get("/api/health", headers={"Host": "evil-domain.com"})
        assert res_disallowed.status_code == 400
        assert "Disallowed Host" in res_disallowed.text

    def test_health_endpoint(self):
        """GET /api/health returns solver, backend, and runtime status."""
        client = TestClient(app)
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["backend"] == "fake"
        assert "z3_version" in data
        assert data["z3_logic"] == "QF_BV (64-bit unsigned)"

    def test_examples_endpoint(self):
        """GET /api/examples returns curated MBA expression presets."""
        client = TestClient(app)
        res = client.get("/api/examples")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 5
        assert all("expression" in ex and "expected_simplified" in ex for ex in data)

    def test_history_and_runs_detail_endpoints(self, temp_db):
        """Verifies GET /api/history and GET /api/runs/{run_id}."""
        # Seed a run in temp_db
        temp_db.record_run({
            "run_id": "test_run_123",
            "expression": "(x ^ y) + 2 * (x & y)",
            "obf_nodes": 9,
            "final_status": "VERIFIED_EQUIVALENT",
            "final_expr": "x + y",
            "compression_pct": 66.67,
            "attempts": 2,
            "total_ms": 150.0,
            "backend": "fake",
            "max_iterations": 5,
        })
        temp_db.record_attempt({
            "run_id": "test_run_123",
            "iteration": 1,
            "candidate": "x ^ y",
            "status": "SAT",
            "latency_ms": 25.0,
            "witness": {"x": 1, "y": 1},
            "expected": 2,
            "actual": 0,
            "raw_output": "x ^ y",
        })
        temp_db.sync()

        client = TestClient(app)

        # GET /api/history
        res_hist = client.get("/api/history")
        assert res_hist.status_code == 200
        history_list = res_hist.json()
        assert len(history_list) >= 1
        assert history_list[0]["run_id"] == "test_run_123"

        # GET /api/runs/{id}
        res_detail = client.get("/api/runs/test_run_123")
        assert res_detail.status_code == 200
        run_detail = res_detail.json()
        assert run_detail["run_id"] == "test_run_123"
        assert len(run_detail["attempts_history"]) == 1
        # Witness values are stringified
        assert run_detail["attempts_history"][0]["witness"] == {"x": "1", "y": "1"}

        # GET /api/runs/{nonexistent} returns 404
        res_404 = client.get("/api/runs/nonexistent_id")
        assert res_404.status_code == 404

    def test_stats_endpoint(self, temp_db):
        """GET /api/stats computes aggregate synthesis metrics."""
        temp_db.record_run({
            "run_id": "run_1",
            "expression": "x + y",
            "obf_nodes": 3,
            "final_status": "VERIFIED_EQUIVALENT",
            "final_expr": "x + y",
            "compression_pct": 0.0,
            "attempts": 1,
            "total_ms": 100.0,
            "backend": "fake",
            "max_iterations": 5,
        })
        temp_db.record_run({
            "run_id": "run_2",
            "expression": "x + 1",
            "obf_nodes": 3,
            "final_status": "FAILED",
            "final_expr": None,
            "compression_pct": 0.0,
            "attempts": 5,
            "total_ms": 200.0,
            "backend": "fake",
            "max_iterations": 5,
        })
        temp_db.sync()

        client = TestClient(app)
        res = client.get("/api/stats")
        assert res.status_code == 200
        stats = res.json()
        assert stats["total_runs"] == 2
        assert stats["verified_runs"] == 1
        assert stats["failed_runs"] == 1
        assert stats["success_rate_pct"] == 50.0
