"""State schema for the PALIMPSEST LangGraph synthesis loop.

`PalimpsestState` carries the state across each stage of the CEGIS loop:
AST parsing -> Proposing hypothesis -> Z3 formal verification -> Routing -> Finalization.
"""
from typing import Any, Callable, Dict, List, Optional, TypedDict


class AttemptRecord(TypedDict):
    """Telemetry record for a single de-obfuscation attempt."""
    iteration: int
    candidate: str
    raw_output: str
    think: Optional[str]
    status: str                    # "QF_BV_UNSAT_64BIT_VERIFIED" | "SAT" | "UNKNOWN" | "INVALID"
    latency_ms: float
    witness: Optional[Dict[str, int]]
    expected: Optional[int]
    actual: Optional[int]
    diff_bits: Optional[str]        # 64-char binary string of (expected ^ actual)


class PalimpsestState(TypedDict):
    """The central state of the LangGraph state machine."""
    obfuscated_expr: str            # Original scrambled input
    obf_nodes: int                  # AST node count of the original expression
    iteration: int                  # Current attempt number (0-indexed before propose)
    max_iterations: int             # Maximum allowed retry attempts (default: 5)
    current_candidate: Optional[str]
    current_raw_output: Optional[str]
    current_think: Optional[str]
    verification_result: Optional[Dict[str, Any]]
    history: List[AttemptRecord]    # Ordered list of all attempts made so far
    final_status: Optional[str]     # "VERIFIED_EQUIVALENT" | "FAILED" | "REJECTED_UNSAFE"
    final_expr: Optional[str]       # Simplified expression on success, None on failure
    final_nodes: Optional[int]      # AST node count of the final expression
    compression_pct: Optional[float]# AST reduction percentage: round((1 - final/orig) * 100, 2)
    error_message: Optional[str]    # Detailed error message if rejected or failed
    temperature: float              # Current sampling temperature
    feedback_message: Optional[str] # Formatted feedback string from Z3 for the next prompt

