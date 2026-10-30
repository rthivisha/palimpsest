"""Diagnostic replay tool for PALIMPSEST training rows.

STRICT INVARIANTS:
- Refuses to run on fake, stub, or fixture data. Real model backend and real training data required.
- Logs per-row results to gitignored backend/eval/out/ (row id, type, expression, each attempt's candidate, Z3 status, latency_ms).
- Prints rows run, backend, model, prompt profile, and elapsed time.
- For CEGIS replay: does a single-turn check using turns 1 to 3 from the dataset row,
  verifying the model's repair with Z3, comparing <tool_response>-wrapped feedback
  with plain feedback. Does NOT report K=1/3/5 for CEGIS replay.
- For SFT rows: runs the standard synthesis loop and reports success within 1, 3, 5 attempts.
"""
import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.config import settings
from backend.app.core.ast_utils import count_nodes, count_nodes_training
from backend.app.core.outcomes import RunOutcome, determine_verified_outcome
from backend.app.core.verifier import STATUS_VERIFIED, verify_equivalence
from backend.app.graph.build import build_graph
from backend.app.llm.base import BaseLLMBackend
from backend.app.llm.factory import get_backend
from backend.app.llm.fake import FakeLLMBackend
from backend.app.llm.prompts import (
    QWEN25_DEFAULT_SYSTEM_MESSAGE,
    extract_candidate,
    extract_think,
    build_messages,
)

logger = logging.getLogger("palimpsest.replay_training")


def is_fixture_data(dataset_path: str, rows: List[Dict[str, Any]]) -> bool:
    """Detects whether dataset_path or row contents represent stub/fixture data."""
    norm_path = os.path.normpath(dataset_path).lower()
    if "fixture" in norm_path or "stub" in norm_path:
        return True
    if len(rows) < 20:
        return True
    for r in rows[:10]:
        if r.get("source") == "fixture, not dataset" or r.get("licence") == "fixture, not dataset":
            return True
        if "fix_" in str(r.get("id", "")):
            return True
    return False


def load_real_training_dataset(path: str) -> List[Dict[str, Any]]:
    """Loads and validates that dataset rows are real training rows, not fixtures."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Dataset file not found at: {path}")

    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    if is_fixture_data(path, rows):
        raise ValueError(
            f"replay_training_rows.py refuses to run on fixture or stub data ({path}). "
            "A real training dataset (e.g. backend/data/dataset.jsonl) is required."
        )

    return rows


def parse_row_expression_and_canonical(row: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """Extracts obfuscated expression and canonical target from diverse dataset formats."""
    # Format 1: Direct keys
    if "expression" in row:
        return row["expression"], row.get("canonical")

    # Format 2: Unsloth / ShareGPT conversations format
    convs = row.get("conversations", [])
    if convs and len(convs) >= 1:
        user_turn = convs[0].get("value", "")
        # Strip prompt prefix: "De-obfuscate this 64-bit MBA expression:\n"
        prefix = "De-obfuscate this 64-bit MBA expression:\n"
        if user_turn.startswith(prefix):
            expr = user_turn[len(prefix):].strip()
        else:
            expr = user_turn.strip()

        canonical = None
        # Canonical can be derived from final assistant turn if present
        for c in reversed(convs):
            if c.get("from") == "assistant":
                candidate = extract_candidate(c.get("value", ""))
                if candidate:
                    canonical = candidate
                    break
        return expr, canonical

    raise ValueError(f"Unable to parse expression from row keys: {list(row.keys())}")


def replay_cegis_single_turn_check(
    backend: BaseLLMBackend,
    row: Dict[str, Any],
    row_id: str,
) -> Dict[str, Any]:
    """Evaluates a single-turn CEGIS repair comparing tool_response vs plain feedback.

    Uses turns 1 to 3 from the dataset row:
    - Turn 1: user (obfuscated expression)
    - Turn 2: assistant (attempt 1 near-miss)
    - Turn 3: Z3 verification feedback (counterexample witness)
    Queries the model for Turn 4 under both feedback formats and verifies with Z3.
    """
    convs = row.get("conversations", [])
    if len(convs) < 3:
        raise ValueError(f"CEGIS row {row_id} does not have at least 3 turns (found {len(convs)}).")

    turn1_user = convs[0].get("value", "")
    turn2_assistant = convs[1].get("value", "")
    turn3_feedback = convs[2].get("value", "")

    # Clean raw feedback text if wrapped
    raw_feedback = turn3_feedback
    if raw_feedback.startswith("<tool_response>\n") and raw_feedback.endswith("\n</tool_response>"):
        raw_feedback = raw_feedback[len("<tool_response>\n"):-len("\n</tool_response>")]

    prefix = "De-obfuscate this 64-bit MBA expression:\n"
    orig_expr = turn1_user[len(prefix):].strip() if turn1_user.startswith(prefix) else turn1_user.strip()

    # Format A: unsloth_qwen25 (<tool_response> wrapped, system turn first)
    messages_tool_response = [
        {"role": "system", "content": QWEN25_DEFAULT_SYSTEM_MESSAGE},
        {"role": "user", "content": turn1_user},
        {"role": "assistant", "content": turn2_assistant},
        {"role": "user", "content": f"<tool_response>\n{raw_feedback}\n</tool_response>"},
    ]

    # Format B: plain (no system turn, plain feedback)
    messages_plain = [
        {"role": "user", "content": turn1_user},
        {"role": "assistant", "content": turn2_assistant},
        {"role": "user", "content": raw_feedback},
    ]

    # Query model under tool_response format
    t0 = time.perf_counter()
    resp_tool = backend.generate(messages=messages_tool_response, temperature=0.2, max_tokens=512)
    cand_tool = extract_candidate(resp_tool) or ""
    z3_tool = verify_equivalence(orig_expr, cand_tool) if cand_tool else {"status": "INVALID", "latency_ms": 0.0}
    time_tool_ms = round((time.perf_counter() - t0) * 1000, 2)

    # Query model under plain format
    t1 = time.perf_counter()
    resp_plain = backend.generate(messages=messages_plain, temperature=0.2, max_tokens=512)
    cand_plain = extract_candidate(resp_plain) or ""
    z3_plain = verify_equivalence(orig_expr, cand_plain) if cand_plain else {"status": "INVALID", "latency_ms": 0.0}
    time_plain_ms = round((time.perf_counter() - t1) * 1000, 2)

    tool_verified = (z3_tool["status"] == STATUS_VERIFIED)
    plain_verified = (z3_plain["status"] == STATUS_VERIFIED)

    return {
        "row_id": row_id,
        "type": "CEGIS_SINGLE_TURN_CHECK",
        "expression": orig_expr,
        "tool_response_format": {
            "candidate": cand_tool,
            "z3_status": z3_tool["status"],
            "z3_latency_ms": z3_tool.get("latency_ms", 0.0),
            "total_ms": time_tool_ms,
            "verified": tool_verified,
        },
        "plain_format": {
            "candidate": cand_plain,
            "z3_status": z3_plain["status"],
            "z3_latency_ms": z3_plain.get("latency_ms", 0.0),
            "total_ms": time_plain_ms,
            "verified": plain_verified,
        },
        "attempts": [
            {
                "format": "tool_response",
                "candidate": cand_tool,
                "z3_status": z3_tool["status"],
                "latency_ms": z3_tool.get("latency_ms", 0.0),
            },
            {
                "format": "plain",
                "candidate": cand_plain,
                "z3_status": z3_plain["status"],
                "latency_ms": z3_plain.get("latency_ms", 0.0),
            },
        ],
    }


def replay_sft_row(
    graph: Any,
    row: Dict[str, Any],
    row_id: str,
    prompt_profile: str,
) -> Dict[str, Any]:
    """Replays an SFT row through the CEGIS synthesis loop up to 5 attempts."""
    expr, canonical = parse_row_expression_and_canonical(row)
    state = {
        "obfuscated_expr": expr,
        "max_iterations": 5,
        "iteration": 0,
        "history": [],
        "temperature": 0.2,
        "prompt_profile": prompt_profile,
        "witness_policy": settings.WITNESS_POLICY,
    }

    final_state = graph.invoke(state)
    history = final_state.get("history", [])

    attempts_log = []
    success_iteration = None
    for att in history:
        att_stat = att.get("status")
        attempts_log.append({
            "iteration": att.get("iteration"),
            "candidate": att.get("candidate"),
            "z3_status": att_stat,
            "latency_ms": att.get("latency_ms", 0.0),
        })
        if att_stat == STATUS_VERIFIED and success_iteration is None:
            success_iteration = att.get("iteration")

    final_status = final_state.get("final_status")
    is_verified = (success_iteration is not None) or (final_status in (RunOutcome.VERIFIED.value, "VERIFIED_EQUIVALENT"))

    return {
        "row_id": row_id,
        "type": row.get("type", "SFT"),
        "expression": expr,
        "canonical": canonical,
        "verified": is_verified,
        "attempts_needed": success_iteration if is_verified else None,
        "attempts": attempts_log,
    }


def run_training_replay(
    dataset_path: str,
    prompt_profile: str = "unsloth_qwen25",
    backend_name: str = "ollama",
    seed: int = 42,
    sft_limit: int = 100,
    cegis_limit: int = 50,
    out_dir: str = "backend/eval/out",
) -> Dict[str, Any]:
    """Executes replay on real training dataset rows and writes JSONL log."""
    start_time = time.perf_counter()

    # Rule (c): Strictly refuse fake backends
    if backend_name.lower().strip() == "fake":
        raise ValueError(
            "replay_training_rows.py refuses to run on fake/stub backends. "
            "A real LLM backend (e.g. 'ollama' or 'llamacpp') is required."
        )

    backend = get_backend(backend_name)
    if isinstance(backend, FakeLLMBackend):
        raise ValueError(
            "replay_training_rows.py refuses to run on FakeLLMBackend instance. "
            "Real model inference is strictly required."
        )

    # Rule (c): Strictly refuse fixture or stub datasets
    all_rows = load_real_training_dataset(dataset_path)

    # Partition dataset into SFT rows and CEGIS rows
    sft_rows: List[Dict[str, Any]] = []
    cegis_rows: List[Dict[str, Any]] = []

    for r in all_rows:
        row_type = str(r.get("type", "")).upper()
        if row_type == "CEGIS":
            cegis_rows.append(r)
        else:
            sft_rows.append(r)

    # Deterministic sampling
    rng = random.Random(seed)
    sampled_sft = rng.sample(sft_rows, min(sft_limit, len(sft_rows)))
    sampled_cegis = rng.sample(cegis_rows, min(cegis_limit, len(cegis_rows)))

    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_filename = f"replay_{prompt_profile}_{backend_name}_{timestamp}.jsonl"
    log_filepath = os.path.join(out_dir, log_filename)

    graph = build_graph(backend)
    logged_records: List[Dict[str, Any]] = []

    # 1. CEGIS Replay: Single-turn check (Turns 1-3) comparing tool_response vs plain feedback
    cegis_tool_successes = 0
    cegis_plain_successes = 0

    for i, r in enumerate(sampled_cegis):
        rid = f"cegis_{i+1}"
        cegis_res = replay_cegis_single_turn_check(backend, r, row_id=rid)
        logged_records.append(cegis_res)
        if cegis_res["tool_response_format"]["verified"]:
            cegis_tool_successes += 1
        if cegis_res["plain_format"]["verified"]:
            cegis_plain_successes += 1

    # 2. SFT Rows Replay: Synthesis loop (K=1, 3, 5 derived)
    sft_k1 = 0
    sft_k3 = 0
    sft_k5 = 0

    for i, r in enumerate(sampled_sft):
        rid = f"sft_{i+1}"
        sft_res = replay_sft_row(graph, r, row_id=rid, prompt_profile=prompt_profile)
        logged_records.append(sft_res)
        attempts = sft_res["attempts_needed"]
        if sft_res["verified"] and attempts is not None:
            if attempts == 1:
                sft_k1 += 1
            if attempts <= 3:
                sft_k3 += 1
            if attempts <= 5:
                sft_k5 += 1

    # Write per-row JSONL log
    with open(log_filepath, "w", encoding="utf-8") as f:
        for rec in logged_records:
            f.write(json.dumps(rec) + "\n")

    elapsed_time = round(time.perf_counter() - start_time, 2)
    total_run = len(sampled_sft) + len(sampled_cegis)

    summary = {
        "rows_run": total_run,
        "sft_rows_run": len(sampled_sft),
        "cegis_rows_run": len(sampled_cegis),
        "backend": backend_name,
        "model": getattr(backend, "model_name", settings.OLLAMA_MODEL),
        "prompt_profile": prompt_profile,
        "elapsed_time_sec": elapsed_time,
        "log_file": log_filepath,
        "cegis_single_turn": {
            "total": len(sampled_cegis),
            "tool_response_verified": cegis_tool_successes,
            "tool_response_rate_pct": round((cegis_tool_successes / len(sampled_cegis)) * 100, 2) if sampled_cegis else 0.0,
            "plain_verified": cegis_plain_successes,
            "plain_rate_pct": round((cegis_plain_successes / len(sampled_cegis)) * 100, 2) if sampled_cegis else 0.0,
        },
        "sft_success": {
            "total": len(sampled_sft),
            "k1_count": sft_k1,
            "k1_pct": round((sft_k1 / len(sampled_sft)) * 100, 2) if sampled_sft else 0.0,
            "k3_count": sft_k3,
            "k3_pct": round((sft_k3 / len(sampled_sft)) * 100, 2) if sampled_sft else 0.0,
            "k5_count": sft_k5,
            "k5_pct": round((sft_k5 / len(sampled_sft)) * 100, 2) if sampled_sft else 0.0,
        },
    }

    return summary


def print_replay_summary(summary: Dict[str, Any]):
    """Prints the required execution summary."""
    print("=" * 80)
    print("PALIMPSEST: TRAINING ROW REPLAY (DIAGNOSTIC ON REAL MODEL)")
    print("=" * 80)
    print(f"Rows run:        {summary['rows_run']} (SFT: {summary['sft_rows_run']}, CEGIS: {summary['cegis_rows_run']})")
    print(f"Backend:         {summary['backend']}")
    print(f"Model:           {summary['model']}")
    print(f"Prompt profile:  {summary['prompt_profile']}")
    print(f"Elapsed time:    {summary['elapsed_time_sec']}s")
    print(f"Log file:        {summary['log_file']}")
    print("-" * 80)
    print("CEGIS Replay Single-Turn Check (Turns 1-3 from file):")
    cegis_data = summary["cegis_single_turn"]
    print(f"  Total evaluated:               {cegis_data['total']}")
    print(f"  <tool_response>-wrapped rate:  {cegis_data['tool_response_verified']}/{cegis_data['total']} ({cegis_data['tool_response_rate_pct']}%)")
    print(f"  Plain feedback rate:           {cegis_data['plain_verified']}/{cegis_data['total']} ({cegis_data['plain_rate_pct']}%)")
    print("-" * 80)
    print("SFT Rows Synthesis:")
    sft_data = summary["sft_success"]
    print(f"  Total evaluated:               {sft_data['total']}")
    print(f"  Success within 1 attempt  (K=1): {sft_data['k1_count']}/{sft_data['total']} ({sft_data['k1_pct']}%)")
    print(f"  Success within 3 attempts (K=3): {sft_data['k3_count']}/{sft_data['total']} ({sft_data['k3_pct']}%)")
    print(f"  Success within 5 attempts (K=5): {sft_data['k5_count']}/{sft_data['total']} ({sft_data['k5_pct']}%)")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Replay real training rows with strict validation.")
    parser.add_argument("--dataset", default="backend/data/dataset.jsonl", help="Path to real training dataset JSONL")
    parser.add_argument("--prompt-profile", choices=["plain", "unsloth_qwen25"], default="unsloth_qwen25", help="Prompt profile")
    parser.add_argument("--backend", default="ollama", help="Backend name ('ollama' or 'llamacpp')")
    parser.add_argument("--seed", type=int, default=42, help="Sampling seed")
    parser.add_argument("--sft-limit", type=int, default=100, help="Number of SFT rows")
    parser.add_argument("--cegis-limit", type=int, default=50, help="Number of CEGIS rows")
    parser.add_argument("--out-dir", default="backend/eval/out", help="Directory for JSONL per-row logs")

    args = parser.parse_args()

    summary = run_training_replay(
        dataset_path=args.dataset,
        prompt_profile=args.prompt_profile,
        backend_name=args.backend,
        seed=args.seed,
        sft_limit=args.sft_limit,
        cegis_limit=args.cegis_limit,
        out_dir=args.out_dir,
    )
    print_replay_summary(summary)


if __name__ == "__main__":
    main()
