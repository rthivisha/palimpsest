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
from backend.app.core.verifier import verify_equivalence, STATUS_VERIFIED, STATUS_SAT
from backend.app.graph.state import PalimpsestState, AttemptRecord
from backend.app.llm.base import BaseLLMBackend
from backend.app.llm.prompts import (
    build_messages,
    extract_candidate,
    extract_think,
    format_z3_feedback,
)


def parse_ast_node(state: PalimpsestState) -> Dict[str, Any]:
    """Node 1: Security gatekeeper & AST initialization.

    Parses the user expression through the safety gate.
    If unsafe, marks REJECTED_UNSAFE immediately to halt execution.
    """
    expr = state.get("obfuscated_expr", "")
    safe, err = is_safe_ast(expr)

    if not safe:
        return {
            "obf_nodes": 0,
            "iteration": 0,
            "history": [],
            "final_status": "REJECTED_UNSAFE",
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
        "error_message": None,
        "temperature": 0.2,
    }


def make_propose_node(backend: BaseLLMBackend) -> Callable[[PalimpsestState], Dict[str, Any]]:
    """Factory creating the `propose` node bound to a specific LLM backend."""

    def propose_node(state: PalimpsestState) -> Dict[str, Any]:
        """Node 2: Generates candidate simplification using the model backend."""
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
        )

        # 2. Invoke model backend
        raw_output = backend.generate(
            messages=messages,
            temperature=current_temp,
            max_tokens=512,
        )

        # 3. Extract candidate expression and thinking block
        candidate = extract_candidate(raw_output)
        think = extract_think(raw_output)

        # 4. Temperature escalation if model repeats an already failed candidate
        prior_candidates = [att["candidate"] for att in history]
        if candidate and candidate in prior_candidates:
            # Raise temperature slightly to encourage exploration away from known failure
            next_temp = round(current_temp + settings.TEMP_RETRY_INCREMENT, 2)
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


def verify_node(state: PalimpsestState) -> Dict[str, Any]:
    """Node 3: Formal Z3 64-bit BitVec miter check.

    Judges whether candidate is equivalent to original.
    Equivalence proven by Z3 (QF_BV, 64-bit) if UNSAT.
    Records concrete counterexample witness if SAT.
    """
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
    )

    # Format feedback message for the CEGIS loop if not verified
    feedback_msg: Optional[str] = None
    if verif["status"] == STATUS_SAT:
        feedback_msg = format_z3_feedback(
            witness=verif["witness"],
            expected=verif["expected"],
            actual=verif["actual"],
            status="SAT",
        )
    elif verif["status"] != STATUS_VERIFIED:
        err_detail = verif.get("error") or "Verification failed"
        feedback_msg = f"Z3_VERIFICATION_FAILED: {verif['status']}\nError: {err_detail}"

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
        "feedback_message": feedback_msg,
    }


def finalize_success_node(state: PalimpsestState) -> Dict[str, Any]:
    """Node 4: Success termination.

    Triggered when Z3 formally proves equivalence (QF_BV_UNSAT_64BIT_VERIFIED).
    Computes final AST reduction percentage.
    """
    final_expr = state.get("current_candidate") or ""
    orig_nodes = state.get("obf_nodes", 1)
    final_nodes = count_nodes(final_expr) if final_expr else orig_nodes

    # Compression = 1 - final_nodes / obf_nodes
    compression_pct = round((1.0 - (final_nodes / max(orig_nodes, 1))) * 100.0, 2)

    return {
        "final_status": "VERIFIED_EQUIVALENT",
        "final_expr": final_expr,
        "final_nodes": final_nodes,
        "compression_pct": compression_pct,
        "error_message": None,
    }


def finalize_fail_node(state: PalimpsestState) -> Dict[str, Any]:
    """Node 5: Failure termination.

    Triggered when retry limit is exhausted without mathematical proof.
    Honest reporting: zero unverified answers accepted.
    """
    max_iter = state.get("max_iterations", settings.MAX_ITERATIONS)
    return {
        "final_status": "FAILED",
        "final_expr": None,
        "final_nodes": None,
        "compression_pct": 0.0,
        "error_message": f"Could not prove equivalence within {max_iter} attempts. No unverified answer accepted.",
    }

