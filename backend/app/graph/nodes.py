"""Node implementations for the PALIMPSEST LangGraph synthesis loop.

Each function takes the current `PalimpsestState` and returns a dict of state updates:
1. `parse_ast_node`: Validates safety gate and calculates initial AST size.
2. `propose_node`: Formats ChatML context, queries the model backend, and extracts candidate.
3. `verify_node`: Performs formal Z3 64-bit BitVec miter check and updates attempt history.
4. `finalize_success_node`: Marks proof complete and computes AST compression ratio.
5. `finalize_fail_node`: Marks run failed when iteration limit is reached without proof.
"""
from typing import Any, Callable, Dict, Optional

from backend.app.config import settings
from backend.app.core.safety import is_safe_ast
from backend.app.core.ast_utils import count_nodes
from backend.app.core.outcomes import RunOutcome, determine_verified_outcome
from backend.app.core.verifier import (
    verify_equivalence,
    STATUS_VERIFIED,
    STATUS_SAT,
    STATUS_UNKNOWN,
    STATUS_INVALID,
)
from backend.app.graph.state import PalimpsestState, AttemptRecord
from backend.app.llm.base import BaseLLMBackend
from backend.app.llm.prompts import (
    build_messages,
    extract_candidate,
    extract_think,
)


def parse_ast_node(state: PalimpsestState) -> Dict[str, Any]:
    """Node 1: Security gatekeeper & AST initialization.

    Parses the user expression through the safety gate.
    If unsafe, marks REJECTED_UNSAFE immediately to halt execution.
    """
    expr = state.get("obfuscated_expr", "")
    safe, err = is_safe_ast(expr)

    if not safe:
        outcome = RunOutcome.DEPTH_REJECTED if "depth" in str(err).lower() else RunOutcome.REJECTED_UNSAFE
        return {
            "obf_nodes": 0,
            "iteration": 0,
            "history": [],
            "final_status": "REJECTED_UNSAFE",
            "outcome": outcome.value,
            "error_message": f"Security Gate Rejection: {err}",
            "temperature": 0.2,
        }

    # Expression is verified safe: compute AST node count
    node_count = count_nodes(expr)
    return {
        "obf_nodes": node_count,
        "iteration": 0,
        "history": [],
        "final_status": None,
        "outcome": None,
        "error_message": None,
        "temperature": 0.2,
    }


def make_propose_node(
    backend: BaseLLMBackend,
    temp_retry_increment: Optional[float] = None,
) -> Callable[..., Dict[str, Any]]:
    """Factory creating the `propose` node bound to a specific LLM backend."""

    def propose_node(state: PalimpsestState, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Node 2: Generates candidate simplification using the model backend."""
        # Check cancellation at node entry
        should_cancel = (config or {}).get("configurable", {}).get("should_cancel")
        if should_cancel and should_cancel():
            raise RuntimeError("Run cancelled by client disconnect")

        obf_expr = state["obfuscated_expr"]
        history = state.get("history", [])
        current_temp = state.get("temperature", 0.2)

        # 1. Build messages matching training data character-for-character
        messages = build_messages(
            obfuscated_expr=obf_expr,
            history=history,
            tool_role=settings.TOOL_ROLE,
            system_prompt=settings.SYSTEM_PROMPT,
            history_mode=settings.HISTORY_MODE,
            prompt_profile=state.get("prompt_profile"),
            backend=backend,
        )

        # 2. Invoke model backend
        raw_output = backend.generate(
            messages=messages,
            temperature=current_temp,
            max_tokens=512,
            should_cancel=should_cancel,
        )

        # 3. Extract candidate expression and thinking block
        candidate = extract_candidate(raw_output)
        think = extract_think(raw_output)

        # 4. Configurable temperature escalation if model repeats an already failed candidate
        prior_candidates = [att["candidate"] for att in history]
        bump = (
            temp_retry_increment
            if temp_retry_increment is not None
            else state.get("temp_retry_increment", settings.TEMP_RETRY_INCREMENT)
        )
        if candidate and candidate in prior_candidates:
            # Raise temperature slightly to encourage exploration away from known failure
            next_temp = round(current_temp + bump, 2)
        else:
            next_temp = current_temp

        new_iteration = state.get("iteration", 0) + 1

        return {
            "iteration": new_iteration,
            "current_candidate": candidate,
            "current_raw_output": raw_output,
            "current_think": think,
            "temperature": next_temp,
        }

    return propose_node


def verify_node(state: PalimpsestState, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Node 3: Formal Z3 64-bit BitVec miter check.

    Judges whether candidate is equivalent to original.
    Equivalence proven by Z3 (QF_BV, 64-bit) if UNSAT.
    Records concrete counterexample witness if SAT.
    """
    # Check cancellation at node entry
    should_cancel = (config or {}).get("configurable", {}).get("should_cancel")
    if should_cancel and should_cancel():
        raise RuntimeError("Run cancelled by client disconnect")

    orig_expr = state["obfuscated_expr"]
    cand_expr = state.get("current_candidate") or ""
    iteration = state.get("iteration", 1)
    raw_output = state.get("current_raw_output") or ""
    think = state.get("current_think")

    # Run formal Z3 verification
    verif = verify_equivalence(
        original_expr=orig_expr,
        candidate_expr=cand_expr,
        timeout_ms=settings.Z3_TIMEOUT_MS,
        witness_policy=state.get("witness_policy", settings.WITNESS_POLICY),
    )

    # Build telemetry record
    attempt: AttemptRecord = {
        "iteration": iteration,
        "candidate": cand_expr,
        "raw_output": raw_output,
        "think": think,
        "status": verif["status"],
        "latency_ms": verif["latency_ms"],
        "witness": verif["witness"],
        "expected": verif["expected"],
        "actual": verif["actual"],
        "diff_bits": verif["diff_bits"],
    }

    updated_history = list(state.get("history", [])) + [attempt]

    return {
        "verification_result": verif,
        "history": updated_history,
    }


def finalize_success_node(state: PalimpsestState) -> Dict[str, Any]:
    """Node 4: Success termination.

    Triggered when Z3 formally proves equivalence (QF_BV_UNSAT_64BIT_VERIFIED).
    Computes final AST reduction percentage and determines whether the candidate is simpler.
    """
    final_expr = state.get("current_candidate") or ""
    orig_nodes = state.get("obf_nodes", 1)
    final_nodes = count_nodes(final_expr) if final_expr else orig_nodes

    # Compression = 1 - final_nodes / obf_nodes
    compression_pct = round((1.0 - (final_nodes / max(orig_nodes, 1))) * 100.0, 2)
    is_idempotent = bool(state.get("is_idempotent", False))
    outcome = determine_verified_outcome(orig_nodes, final_nodes, is_idempotent)

    return {
        "final_status": "VERIFIED_EQUIVALENT",
        "outcome": outcome.value,
        "final_expr": final_expr,
        "final_nodes": final_nodes,
        "compression_pct": max(0.0, compression_pct),
        "error_message": None if outcome == RunOutcome.VERIFIED else "Verified equivalent, but not simpler",
    }


def finalize_fail_node(state: PalimpsestState) -> Dict[str, Any]:
    """Node 5: Failure termination.

    Triggered when retry limit is exhausted without mathematical proof.
    Honest reporting: zero unverified answers accepted.
    """
    history = state.get("history", [])
    last_status = history[-1].get("status") if history else "SAT"
    if last_status == "UNKNOWN":
        outcome = RunOutcome.UNKNOWN_TIMEOUT
    elif last_status == "INVALID":
        outcome = RunOutcome.INVALID
    else:
        outcome = RunOutcome.FAILED_EXHAUSTED

    max_iter = state.get("max_iterations", settings.MAX_ITERATIONS)
    return {
        "final_status": "FAILED",
        "outcome": outcome.value,
        "final_expr": None,
        "final_nodes": None,
        "compression_pct": 0.0,
        "error_message": f"Could not prove equivalence within {max_iter} attempts. No unverified answer accepted.",
    }

