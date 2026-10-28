"""Unified outcome enumerations for PALIMPSEST synthesis and evaluation runs.

Provides a single authoritative Enum defining all terminal execution outcomes:
- verified: Z3 proven equivalent AND candidate AST node count < original (or <= original for IDEMPOTENT).
- verified-not-simpler: Z3 proven equivalent BUT candidate AST node count not simpler.
- failed-exhausted: CEGIS iteration limit reached without equivalence proof.
- unknown-timeout: Z3 solver or inference timed out / returned unknown.
- invalid: Candidate AST failed syntax or safety gate checks.
- rejected-unsafe: Initial input rejected by AST safety gate.
- depth-rejected: AST recursion depth limit exceeded (> 100).
- unconvertible: Z3-only AST or BitVec translation failure.
"""
from enum import Enum


class RunOutcome(str, Enum):
    VERIFIED = "verified"
    VERIFIED_NOT_SIMPLER = "verified-not-simpler"
    FAILED_EXHAUSTED = "failed-exhausted"
    UNKNOWN_TIMEOUT = "unknown-timeout"
    INVALID = "invalid"
    REJECTED_UNSAFE = "rejected-unsafe"
    DEPTH_REJECTED = "depth-rejected"
    UNCONVERTIBLE = "unconvertible"


# Alias for evaluation context
EvalOutcome = RunOutcome


def determine_verified_outcome(
    obf_nodes: int,
    cand_nodes: int,
    is_idempotent: bool = False,
) -> RunOutcome:
    """Determines whether a verified candidate qualifies as 'verified' or 'verified-not-simpler'.

    Rules:
    - Standard rows: candidate node count must be strictly less than original (cand_nodes < obf_nodes).
    - Idempotent rows: candidate node count must be no larger than original (cand_nodes <= obf_nodes).
    """
    if is_idempotent:
        return RunOutcome.VERIFIED if cand_nodes <= obf_nodes else RunOutcome.VERIFIED_NOT_SIMPLER
    return RunOutcome.VERIFIED if cand_nodes < obf_nodes else RunOutcome.VERIFIED_NOT_SIMPLER

