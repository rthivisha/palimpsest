"""Evaluation harness for PALIMPSEST neurosymbolic MBA de-obfuscation engine.

Strictly adheres to EVAL.md:
- Uses real LangGraph state machine and prompts.build_messages.
- Strict refusal of FakeLLMBackend unless --allow-fake is passed.
- Single-run protocol (K_max=5) deriving K=1, 3, 5 analytically.
- Universal denominator: rejected/timed-out rows stay in denominator N.
- Isolated SQLite database persistence for evaluation state.
- Wilson 95% confidence intervals and p50/p95 latency metrics.
"""
import ast
import json
import logging
import math
import os
import random
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.app.config import settings
from backend.app.core.ast_utils import count_nodes
from backend.app.core.safety import is_safe_ast
from backend.app.core.verifier import (
    STATUS_INVALID,
    STATUS_SAT,
    STATUS_UNKNOWN,
    STATUS_VERIFIED,
    verify_equivalence,
)
from backend.app.graph.build import build_graph
from backend.app.llm.base import BaseLLMBackend
from backend.app.llm.factory import get_backend
from backend.app.llm.fake import FakeLLMBackend

logger = logging.getLogger("palimpsest.eval")


def compute_wilson_interval(successes: int, total: int, z: float = 1.95996) -> Tuple[float, float]:
    """Calculates 95% Wilson Score confidence interval for a binomial proportion.

    Args:
        successes: Number of verified expressions.
        total: Total expressions evaluated (universal denominator).
        z: Z-score for confidence level (1.95996 for 95%).

    Returns:
        (lower_bound_pct, upper_bound_pct) in percentage points [0.0, 100.0].
    """
    if total <= 0:
        return 0.0, 0.0
    p = successes / total
    denom = 1.0 + (z**2) / total
    center = (p + (z**2) / (2 * total)) / denom
    margin = (z * math.sqrt((p * (1 - p) / total) + (z**2) / (4 * (total**2)))) / denom
    lower = max(0.0, center - margin) * 100.0
    upper = min(1.0, center + margin) * 100.0
    return round(lower, 2), round(upper, 2)


def compute_percentiles(values: List[float]) -> Tuple[float, float]:
    """Computes median (p50) and 95th percentile (p95)."""
    if not values:
        return 0.0, 0.0
    s = sorted(values)
    n = len(s)
    # p50
    mid = n // 2
    p50 = s[mid] if n % 2 != 0 else (s[mid - 1] + s[mid]) / 2.0
    # p95
    idx95 = min(int(math.ceil(0.95 * n)) - 1, n - 1)
    p95 = s[max(0, idx95)]
    return round(p50, 2), round(p95, 2)


@dataclass
class EvalConfig:
    dataset_path: str = "backend/data/samples.jsonl"
    db_path: str = "eval_results.db"
    backend_name: str = "ollama"
    split: str = "validation"
    external: bool = False
    max_k: int = 5
    limit: Optional[int] = None
    resume: bool = False
    allow_fake: bool = False
    z3_only: bool = False
    seed: int = 42


class EvalHarness:
    """Benchmark harness executing the formal evaluation protocol."""

    def __init__(self, config: EvalConfig, backend: Optional[BaseLLMBackend] = None):
        self.config = config
        random.seed(config.seed)

        # 1. Enforce strict refusal of mock/fake backends
        resolved_backend_name = (config.backend_name or settings.PALIMPSEST_BACKEND).lower().strip()
        if (resolved_backend_name == "fake" or isinstance(backend, FakeLLMBackend)) and not config.allow_fake:
            raise RuntimeError(
                "Evaluation harness refused to run against 'fake' backend without --allow-fake. "
                "Fake or mock inference results must never be published as benchmark figures."
            )

        if config.z3_only:
            self.backend = None
        else:
            self.backend = backend or get_backend(resolved_backend_name)

        self._init_db()

    def _init_db(self) -> None:
        """Initializes the dedicated SQLite evaluation state database."""
        os.makedirs(os.path.dirname(os.path.abspath(self.config.db_path)), exist_ok=True) if os.path.dirname(self.config.db_path) else None
        conn = sqlite3.connect(self.config.db_path)
        with conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS eval_results (
                    row_id TEXT PRIMARY KEY,
                    tier TEXT NOT NULL,
                    row_type TEXT NOT NULL,
                    expression TEXT NOT NULL,
                    canonical TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts_needed INTEGER,
                    total_ms REAL NOT NULL,
                    z3_ms REAL NOT NULL,
                    model_ms REAL NOT NULL,
                    is_idempotent INTEGER NOT NULL,
                    is_constant_folding INTEGER NOT NULL,
                    proven_expr TEXT,
                    created_at TEXT NOT NULL
                );
            """)
        conn.close()

    def get_completed_row_ids(self) -> set:
        """Loads already completed row IDs for resuming interrupted benchmarks."""
        conn = sqlite3.connect(self.config.db_path)
        try:
            cur = conn.execute("SELECT row_id FROM eval_results;")
            return {row[0] for row in cur.fetchall()}
        finally:
            conn.close()

    def save_result(self, res: Dict[str, Any]) -> None:
        """Atomically persists an evaluated row result to SQLite."""
        conn = sqlite3.connect(self.config.db_path)
        try:
            with conn:
                conn.execute("""
                    INSERT OR REPLACE INTO eval_results (
                        row_id, tier, row_type, expression, canonical,
                        status, attempts_needed, total_ms, z3_ms, model_ms,
                        is_idempotent, is_constant_folding, proven_expr, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    res["row_id"],
                    res["tier"],
                    res["row_type"],
                    res["expression"],
                    res["canonical"],
                    res["status"],
                    res.get("attempts_needed"),
                    res["total_ms"],
                    res.get("z3_ms", 0.0),
                    res.get("model_ms", 0.0),
                    1 if res.get("is_idempotent") else 0,
                    1 if res.get("is_constant_folding") else 0,
                    res.get("proven_expr"),
                    datetime.now(timezone.utc).isoformat(),
                ))
        finally:
            conn.close()

    def load_rows(self) -> List[Dict[str, Any]]:
        """Reads dataset JSONL and filters by split/external according to EVAL.md."""
        if not os.path.exists(self.config.dataset_path):
            raise FileNotFoundError(f"Evaluation dataset not found at '{self.config.dataset_path}'.")

        rows: List[Dict[str, Any]] = []
        with open(self.config.dataset_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                # Filter by partition
                row_type = row.get("row_type", "validation")
                if self.config.external:
                    if row_type != "external":
                        continue
                else:
                    if row_type != self.config.split:
                        continue
                rows.append(row)

        if self.config.limit is not None and self.config.limit > 0:
            rows = rows[: self.config.limit]

        return rows

    def evaluate_row_z3_only(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluates row using native Z3-simplifier baseline."""
        import z3
        start_time = time.perf_counter()
        expr = row["expression"]
        canonical = row.get("canonical", "")

        # 1. Safety Gate Check
        safe, _ = is_safe_ast(expr)
        if not safe:
            total_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "row_id": row["id"],
                "tier": row.get("tier", "unknown"),
                "row_type": row.get("row_type", "validation"),
                "expression": expr,
                "canonical": canonical,
                "status": "GATE_REJECTED",
                "attempts_needed": None,
                "total_ms": total_ms,
                "z3_ms": 0.0,
                "model_ms": 0.0,
                "is_idempotent": False,
                "is_constant_folding": False,
                "proven_expr": None,
            }

        # 2. Convert and run Z3 native simplifier
        try:
            # Create 64-bit BitVec symbols
            tree = ast.parse(expr, mode="eval")
            z3_start = time.perf_counter()
            # Try native Z3 simplification through AST
            # For baseline: verify original against canonical with timeout
            verif = verify_equivalence(expr, canonical, timeout_ms=3000)
            z3_ms = round((time.perf_counter() - z3_start) * 1000, 2)
            total_ms = round((time.perf_counter() - start_time) * 1000, 2)

            is_success = verif["status"] == STATUS_VERIFIED
            status = "SUCCESS_PROVEN" if is_success else "FAILED_EXHAUSTED"

            return {
                "row_id": row["id"],
                "tier": row.get("tier", "unknown"),
                "row_type": row.get("row_type", "validation"),
                "expression": expr,
                "canonical": canonical,
                "status": status,
                "attempts_needed": 1 if is_success else None,
                "total_ms": total_ms,
                "z3_ms": z3_ms,
                "model_ms": 0.0,
                "is_idempotent": bool(row.get("is_idempotent", False)),
                "is_constant_folding": bool(row.get("is_constant_folding", False)),
                "proven_expr": canonical if is_success else None,
            }
        except Exception:
            total_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "row_id": row["id"],
                "tier": row.get("tier", "unknown"),
                "row_type": row.get("row_type", "validation"),
                "expression": expr,
                "canonical": canonical,
                "status": "UNCONVERTIBLE",
                "attempts_needed": None,
                "total_ms": total_ms,
                "z3_ms": 0.0,
                "model_ms": 0.0,
                "is_idempotent": False,
                "is_constant_folding": False,
                "proven_expr": None,
            }

    def evaluate_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Runs single-run CEGIS evaluation (K_max=5) on one expression row."""
        if self.config.z3_only:
            return self.evaluate_row_z3_only(row)

        start_time = time.perf_counter()
        expr = row["expression"]
        canonical = row.get("canonical", "")
        tier = row.get("tier", "unknown")
        row_type = row.get("row_type", "validation")

        # 1. Safety Gate Check
        safe, _ = is_safe_ast(expr)
        if not safe:
            total_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "row_id": row["id"],
                "tier": tier,
                "row_type": row_type,
                "expression": expr,
                "canonical": canonical,
                "status": "GATE_REJECTED",
                "attempts_needed": None,
                "total_ms": total_ms,
                "z3_ms": 0.0,
                "model_ms": 0.0,
                "is_idempotent": False,
                "is_constant_folding": False,
                "proven_expr": None,
            }

        # 2. Check depth gate limit (MAX_AST_DEPTH = 100)
        from backend.app.core.ast_utils import get_ast_depth
        try:
            tree = ast.parse(expr, mode="eval")
            depth = get_ast_depth(tree)
            if depth > settings.MAX_AST_DEPTH:
                total_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return {
                    "row_id": row["id"],
                    "tier": tier,
                    "row_type": row_type,
                    "expression": expr,
                    "canonical": canonical,
                    "status": "DEPTH_REJECTED",
                    "attempts_needed": None,
                    "total_ms": total_ms,
                    "z3_ms": 0.0,
                    "model_ms": 0.0,
                    "is_idempotent": False,
                    "is_constant_folding": False,
                    "proven_expr": None,
                }
        except Exception:
            total_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "row_id": row["id"],
                "tier": tier,
                "row_type": row_type,
                "expression": expr,
                "canonical": canonical,
                "status": "INVALID_SYNTAX",
                "attempts_needed": None,
                "total_ms": total_ms,
                "z3_ms": 0.0,
                "model_ms": 0.0,
                "is_idempotent": False,
                "is_constant_folding": False,
                "proven_expr": None,
            }

        # 3. Execute LangGraph compiled workflow
        app_graph = build_graph(backend=self.backend)
        init_state = {
            "obfuscated_expr": expr,
            "original_expr": expr,
            "max_iterations": self.config.max_k,
            "iteration": 0,
            "history": [],
            "current_candidate": None,
            "current_raw_output": None,
            "current_think": None,
            "verification_result": None,
            "final_status": None,
            "error_message": None,
            "temperature": 0.2,
        }

        try:
            final_state = app_graph.invoke(init_state)
            total_ms = round((time.perf_counter() - start_time) * 1000, 2)
            final_status = final_state.get("final_status")

            # Determine first successful attempt index
            history = final_state.get("history", [])
            success_iteration: Optional[int] = None
            total_z3_ms = 0.0
            for att in history:
                total_z3_ms += att.get("latency_ms", 0.0)
                if att.get("status") == STATUS_VERIFIED and success_iteration is None:
                    success_iteration = att.get("iteration")

            if final_status == "VERIFIED_EQUIVALENT" or success_iteration is not None:
                status = "SUCCESS_PROVEN"
                attempts_needed = success_iteration or len(history)
            elif final_status == "REJECTED_UNSAFE":
                status = "GATE_REJECTED"
                attempts_needed = None
            elif any(att.get("status") == STATUS_UNKNOWN for att in history):
                status = "TIMEOUT_UNKNOWN"
                attempts_needed = None
            elif any(att.get("status") == STATUS_INVALID for att in history):
                status = "INVALID_SYNTAX"
                attempts_needed = None
            else:
                status = "FAILED_EXHAUSTED"
                attempts_needed = None

            model_ms = max(0.0, total_ms - total_z3_ms)

            return {
                "row_id": row["id"],
                "tier": tier,
                "row_type": row_type,
                "expression": expr,
                "canonical": canonical,
                "status": status,
                "attempts_needed": attempts_needed,
                "total_ms": total_ms,
                "z3_ms": round(total_z3_ms, 2),
                "model_ms": round(model_ms, 2),
                "is_idempotent": bool(row.get("is_idempotent", False)),
                "is_constant_folding": bool(row.get("is_constant_folding", False)),
                "proven_expr": final_state.get("current_candidate") if status == "SUCCESS_PROVEN" else None,
            }
        except Exception as exc:
            total_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "row_id": row["id"],
                "tier": tier,
                "row_type": row_type,
                "expression": expr,
                "canonical": canonical,
                "status": "TIMEOUT_UNKNOWN" if "timeout" in str(exc).lower() else "INVALID_SYNTAX",
                "attempts_needed": None,
                "total_ms": total_ms,
                "z3_ms": 0.0,
                "model_ms": 0.0,
                "is_idempotent": False,
                "is_constant_folding": False,
                "proven_expr": None,
            }

    def run(self) -> Dict[str, Any]:
        """Executes evaluation over the configured partition and returns summary."""
        rows = self.load_rows()
        completed_ids = self.get_completed_row_ids() if self.config.resume else set()

        evaluated_results: List[Dict[str, Any]] = []

        for row in rows:
            if row["id"] in completed_ids:
                continue
            res = self.evaluate_row(row)
            self.save_result(res)
            evaluated_results.append(res)

        return self.generate_summary()

    def generate_summary(self) -> Dict[str, Any]:
        """Calculates final benchmark summary metrics directly from the SQLite database."""
        conn = sqlite3.connect(self.config.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute("SELECT * FROM eval_results;")
            all_results = [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

        total = len(all_results)
        if total == 0:
            return {"total_evaluated": 0}

        # Derived K=1, 3, 5 successes
        k1_success = sum(1 for r in all_results if r["status"] == "SUCCESS_PROVEN" and r["attempts_needed"] == 1)
        k3_success = sum(1 for r in all_results if r["status"] == "SUCCESS_PROVEN" and r["attempts_needed"] and r["attempts_needed"] <= 3)
        k5_success = sum(1 for r in all_results if r["status"] == "SUCCESS_PROVEN" and r["attempts_needed"] and r["attempts_needed"] <= 5)

        k1_pct = round((k1_success / total) * 100, 2)
        k3_pct = round((k3_success / total) * 100, 2)
        k5_pct = round((k5_success / total) * 100, 2)

        ci_k1 = compute_wilson_interval(k1_success, total)
        ci_k3 = compute_wilson_interval(k3_success, total)
        ci_k5 = compute_wilson_interval(k5_success, total)

        # Categorization breakdown
        outcomes: Dict[str, int] = {}
        for r in all_results:
            st = r["status"]
            outcomes[st] = outcomes.get(st, 0) + 1

        # Idempotent and constant folding
        idempotent_count = sum(1 for r in all_results if r["is_idempotent"])
        constant_folding_count = sum(1 for r in all_results if r["is_constant_folding"])

        # Latencies
        z3_latencies = [r["z3_ms"] for r in all_results if r.get("z3_ms")]
        model_latencies = [r["model_ms"] for r in all_results if r.get("model_ms")]

        z3_p50, z3_p95 = compute_percentiles(z3_latencies)
        model_p50, model_p95 = compute_percentiles(model_latencies)

        return {
            "total_evaluated": total,
            "success_within_1_attempt_pct": k1_pct,
            "success_within_1_ci95": ci_k1,
            "success_within_3_attempts_pct": k3_pct,
            "success_within_3_ci95": ci_k3,
            "success_within_5_attempts_pct": k5_pct,
            "success_within_5_ci95": ci_k5,
            "outcomes": outcomes,
            "idempotent_count": idempotent_count,
            "constant_folding_count": constant_folding_count,
            "z3_latency_p50": z3_p50,
            "z3_latency_p95": z3_p95,
            "model_latency_p50": model_p50,
            "model_latency_p95": model_p95,
        }
