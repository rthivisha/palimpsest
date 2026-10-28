"""Route handler for POST /api/run.

Provides real-time SSE streaming of the neurosymbolic de-obfuscation synthesis loop.
"""
import asyncio
import logging
import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from backend.app.config import settings
from backend.app.core.ast_utils import count_nodes
from backend.app.core.outcomes import RunOutcome, determine_verified_outcome
from backend.app.core.safety import is_safe_ast
from backend.app.core.verifier import (
    STATUS_INVALID,
    STATUS_SAT,
    STATUS_UNKNOWN,
    STATUS_VERIFIED,
    verify_equivalence,
)
from backend.app.llm.base import BaseLLMBackend, LLMBackendError
from backend.app.llm.factory import get_backend
from backend.app.llm.prompts import (
    build_messages,
    extract_candidate,
    extract_think,
    format_z3_feedback,
)
from backend.app.schemas import RunRequest, format_sse_event, stringify_verification_values
from backend.app.telemetry.db import telemetry_db

logger = logging.getLogger("palimpsest.api.run")

router = APIRouter()

# Global single-slot concurrency lock
# Enforces that only 1 local CPU de-obfuscation run executes at a time
run_lock = threading.Lock()

# Registry of active run cancellation events: run_id -> threading.Event
active_runs: Dict[str, threading.Event] = {}


def run_synthesis_worker(
    run_id: str,
    expression: str,
    max_iterations: int,
    backend_name: str,
    obf_nodes: int,
    loop: asyncio.AbstractEventLoop,
    event_queue: asyncio.Queue,
    cancel_event: threading.Event,
    backend: Optional[BaseLLMBackend] = None,
    temp_retry_increment: Optional[float] = None,
    model_name: Optional[str] = None,
) -> None:
    """Worker thread running the formal synthesis loop and dispatching threadsafe events."""
    start_time = time.perf_counter()

    def dispatch(event_type: Optional[str], payload: Optional[Dict[str, Any]] = None) -> None:
        try:
            if not loop.is_closed():
                loop.call_soon_threadsafe(event_queue.put_nowait, (event_type, payload))
        except (RuntimeError, Exception) as exc:
            logger.debug("Dispatch suppressed (event loop closed or unreachable): %s", exc)

    def should_cancel() -> bool:
        return cancel_event.is_set()

    try:
        llm = backend or get_backend(backend_name)

        # 1. Emit run_started with backend and model_name
        dispatch("run_started", {
            "run_id": run_id,
            "expression": expression,
            "obf_nodes": obf_nodes,
            "max_iterations": max_iterations,
            "backend": backend_name,
            "model_name": model_name,
        })

        # 2. Node: parse_ast
        dispatch("node_started", {"node": "parse_ast"})
        safe, err_msg = is_safe_ast(expression)
        dispatch("node_finished", {"node": "parse_ast"})

        if not safe:
            total_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if "depth" in str(err_msg).lower():
                outcome = RunOutcome.DEPTH_REJECTED
                reason = f"Security Gate Rejection: {err_msg}"
            elif "syntax error" in str(err_msg).lower() or "unconvertible" in str(err_msg).lower():
                outcome = RunOutcome.UNCONVERTIBLE
                reason = f"Unconvertible expression: {err_msg}"
            else:
                outcome = RunOutcome.REJECTED_UNSAFE
                reason = f"Security Gate Rejection: {err_msg}"
            dispatch("final", {
                "status": "REJECTED_UNSAFE",
                "outcome": outcome.value,
                "final_expr": None,
                "obf_nodes": 0,
                "final_nodes": None,
                "compression_pct": 0.0,
                "total_ms": total_ms,
                "attempts": 0,
                "reason": reason,
                "backend": backend_name,
                "model_name": model_name,
            })
            telemetry_db.update_run({
                "run_id": run_id,
                "final_status": "REJECTED_UNSAFE",
                "outcome": outcome.value,
                "reason": reason,
                "total_ms": total_ms,
                "attempts": 0,
            })
            return

        # 3. CEGIS Propose -> Verify -> Retry loop
        history = []
        temperature = 0.2

        for iteration in range(1, max_iterations + 1):
            if should_cancel():
                total_ms = round((time.perf_counter() - start_time) * 1000, 2)
                telemetry_db.update_run({
                    "run_id": run_id,
                    "final_status": "CANCELLED",
                    "total_ms": total_ms,
                    "attempts": iteration - 1,
                })
                return

            # --- Propose Node ---
            dispatch("node_started", {"node": "propose"})

            messages = build_messages(
                obfuscated_expr=expression,
                history=history,
                tool_role=settings.TOOL_ROLE,
                system_prompt=settings.SYSTEM_PROMPT,
                history_mode=settings.HISTORY_MODE,
            )

            raw_output = llm.generate(
                messages=messages,
                temperature=temperature,
                max_tokens=512,
                should_cancel=should_cancel,
            )

            candidate = extract_candidate(raw_output)
            think = extract_think(raw_output)

            # Configurable temperature bump if candidate repeats
            prior_candidates = [att["candidate"] for att in history]
            bump = temp_retry_increment if temp_retry_increment is not None else settings.TEMP_RETRY_INCREMENT
            if candidate and candidate in prior_candidates:
                temperature = round(temperature + bump, 2)

            # Freeze: Payload emitted BEFORE node_finished
            dispatch("proposal", {
                "iteration": iteration,
                "raw_output": raw_output,
                "think": think,
                "candidate": candidate,
            })
            dispatch("node_finished", {"node": "propose"})

            if should_cancel():
                total_ms = round((time.perf_counter() - start_time) * 1000, 2)
                telemetry_db.update_run({
                    "run_id": run_id,
                    "final_status": "CANCELLED",
                    "total_ms": total_ms,
                    "attempts": iteration,
                })
                return

            # --- Verify Node ---
            dispatch("node_started", {"node": "verify"})

            verif = verify_equivalence(
                original_expr=expression,
                candidate_expr=candidate or "",
                timeout_ms=settings.Z3_TIMEOUT_MS,
                shift_semantics=settings.SHIFT_SEMANTICS,
            )

            # Build record for prompt replay and telemetry
            attempt_record = {
                "iteration": iteration,
                "candidate": candidate or "",
                "raw_output": raw_output,
                "think": think,
                "status": verif["status"],
                "latency_ms": verif["latency_ms"],
                "witness": verif["witness"],
                "expected": verif["expected"],
                "actual": verif["actual"],
                "diff_bits": verif["diff_bits"],
            }
            history.append(attempt_record)

            # Record attempt in database
            telemetry_db.record_attempt({
                "run_id": run_id,
                **attempt_record,
            })

            # Freeze: Payload emitted BEFORE node_finished with string serialization
            verif_payload = stringify_verification_values({
                "iteration": iteration,
                "candidate": candidate,
                "status": verif["status"],
                "latency_ms": verif["latency_ms"],
                "witness": verif["witness"],
                "expected": verif["expected"],
                "actual": verif["actual"],
                "diff_bits": verif["diff_bits"],
            })
            dispatch("verification", verif_payload)
            dispatch("node_finished", {"node": "verify"})

            # Routing decision
            if verif["status"] == STATUS_VERIFIED:
                # --- Finalize Success ---
                dispatch("node_started", {"node": "finalize_success"})
                cand_nodes = count_nodes(candidate or "")
                raw_comp = (1.0 - (cand_nodes / max(obf_nodes, 1))) * 100
                compression_pct = round(max(0.0, raw_comp), 2)
                total_ms = round((time.perf_counter() - start_time) * 1000, 2)
                dispatch("node_finished", {"node": "finalize_success"})

                outcome = determine_verified_outcome(obf_nodes, cand_nodes, is_idempotent=False)
                reason = None if outcome == RunOutcome.VERIFIED else "Verified equivalent, but not simpler"

                dispatch("final", {
                    "status": "VERIFIED_EQUIVALENT",
                    "outcome": outcome.value,
                    "final_expr": candidate,
                    "obf_nodes": obf_nodes,
                    "final_nodes": cand_nodes,
                    "compression_pct": compression_pct,
                    "total_ms": total_ms,
                    "attempts": iteration,
                    "reason": reason,
                    "backend": backend_name,
                    "model_name": model_name,
                })
                telemetry_db.update_run({
                    "run_id": run_id,
                    "final_status": "VERIFIED_EQUIVALENT",
                    "outcome": outcome.value,
                    "reason": reason,
                    "final_expr": candidate,
                    "final_nodes": cand_nodes,
                    "compression_pct": compression_pct,
                    "attempts": iteration,
                    "total_ms": total_ms,
                })
                return

            elif iteration < max_iterations:
                # Prepare feedback message for next iteration
                feedback_msg = format_z3_feedback(
                    witness=verif.get("witness"),
                    expected=verif.get("expected"),
                    actual=verif.get("actual"),
                    status=verif["status"],
                    error=verif.get("error"),
                )

                dispatch("retry", {
                    "iteration": iteration,
                    "feedback_message": feedback_msg,
                })
            else:
                # --- Finalize Fail (Max iterations reached) ---
                # NOTE: Exactly as specified, no trailing retry event is emitted
                dispatch("node_started", {"node": "finalize_fail"})
                total_ms = round((time.perf_counter() - start_time) * 1000, 2)
                dispatch("node_finished", {"node": "finalize_fail"})

                last_status = verif.get("status", "SAT")
                if last_status == "UNKNOWN":
                    outcome = RunOutcome.UNKNOWN_TIMEOUT
                    fail_reason = "Z3 solver timeout or resource limit reached"
                elif last_status == "INVALID":
                    outcome = RunOutcome.INVALID
                    fail_reason = "Model candidate failed syntax or safety gate checks"
                else:
                    outcome = RunOutcome.FAILED_EXHAUSTED
                    fail_reason = "Max iterations reached without proving equivalence"

                dispatch("final", {
                    "status": "FAILED",
                    "outcome": outcome.value,
                    "final_expr": None,
                    "obf_nodes": obf_nodes,
                    "final_nodes": None,
                    "compression_pct": 0.0,
                    "total_ms": total_ms,
                    "attempts": iteration,
                    "reason": fail_reason,
                    "backend": backend_name,
                    "model_name": model_name,
                })
                telemetry_db.update_run({
                    "run_id": run_id,
                    "final_status": "FAILED",
                    "outcome": outcome.value,
                    "reason": fail_reason,
                    "attempts": iteration,
                    "total_ms": total_ms,
                })
                return

    except Exception as exc:
        total_ms = round((time.perf_counter() - start_time) * 1000, 2)
        if should_cancel():
            telemetry_db.update_run({
                "run_id": run_id,
                "final_status": "CANCELLED",
                "outcome": "cancelled",
                "reason": "Execution aborted by user",
                "total_ms": total_ms,
            })
        else:
            logger.error("Synthesis worker crashed: %s", exc)
            # Emit single error event terminating the stream
            dispatch("error", {"error": str(exc)})
            telemetry_db.update_run({
                "run_id": run_id,
                "final_status": "ERROR",
                "outcome": "error",
                "reason": str(exc),
                "total_ms": total_ms,
            })
    finally:
        # Signal queue that worker is finished
        dispatch(None, None)
        active_runs.pop(run_id, None)
        try:
            run_lock.release()
        except RuntimeError:
            pass


@router.post("/run")
async def start_run(req: RunRequest, request: Request):
    """Initiates a de-obfuscation run and streams execution events via SSE."""
    # 1. Non-blocking acquire of the single inference slot
    if not run_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="Only 1 local run is supported concurrently. Previous run still finishing.",
            headers={"Retry-After": "5"},
        )

    try:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        backend_name = settings.PALIMPSEST_BACKEND
        if backend_name == "ollama":
            model_name = settings.OLLAMA_MODEL
        elif backend_name in ("llamacpp", "llama_cpp", "llama-cpp"):
            model_name = os.path.basename(settings.LLAMACPP_MODEL_PATH)
        else:
            model_name = "fake-scripted"

        # 2. Handler pre-calculates obf_nodes before run_started (0 if unsafe)
        safe, _ = is_safe_ast(req.expression)
        obf_nodes = count_nodes(req.expression) if safe else 0

        # 3. Record run initialization in telemetry
        telemetry_db.record_run({
            "run_id": run_id,
            "expression": req.expression,
            "obf_nodes": obf_nodes,
            "final_status": "RUNNING",
            "backend": backend_name,
            "model_name": model_name,
            "max_iterations": req.max_iterations,
        })

        # 4. Initialize thread-queue bridge
        event_queue: asyncio.Queue = asyncio.Queue()
        cancel_event = threading.Event()
        active_runs[run_id] = cancel_event
        loop = asyncio.get_running_loop()

        # 5. Spawn worker thread
        worker_thread = threading.Thread(
            target=run_synthesis_worker,
            args=(
                run_id,
                req.expression,
                req.max_iterations,
                backend_name,
                obf_nodes,
                loop,
                event_queue,
                cancel_event,
                None,
                settings.TEMP_RETRY_INCREMENT,
                model_name,
            ),
            name=f"worker-{run_id}",
            daemon=True,
        )
        worker_thread.start()

        # 6. Stream generator with ping heartbeat & disconnect detection
        async def event_generator():
            try:
                while True:
                    try:
                        item = await asyncio.wait_for(event_queue.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        # 15s heartbeat comment to prevent proxy idle drop
                        yield ": ping\n\n"
                        continue

                    event_type, payload = item
                    if event_type is None:
                        # Sentinel received: worker has finished
                        break

                    yield format_sse_event(event_type, payload)
            finally:
                # Trigger cancellation on client disconnect or stream closure
                cancel_event.set()

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
            background=BackgroundTask(cancel_event.set),
        )
    except Exception:
        # If any unexpected exception occurred before streaming starts, release lock
        try:
            run_lock.release()
        except RuntimeError:
            pass
        raise


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    """Signals cancellation to an active synthesis run."""
    cancel_evt = active_runs.get(run_id)
    if not cancel_evt:
        raise HTTPException(status_code=404, detail=f"No active run found with ID '{run_id}'.")
    cancel_evt.set()
    return {"status": "cancellation_requested", "run_id": run_id}
