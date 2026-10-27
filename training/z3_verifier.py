"""Z3 Verifier compatibility module for training scripts.

Re-exports the 64-bit BitVec formal equivalence verifier from the core backend.
"""
from backend.app.core.verifier import (
    verify_equivalence,
    STATUS_VERIFIED,
    STATUS_SAT,
    STATUS_UNKNOWN,
    STATUS_INVALID,
)

__all__ = [
    "verify_equivalence",
    "STATUS_VERIFIED",
    "STATUS_SAT",
    "STATUS_UNKNOWN",
    "STATUS_INVALID",
]
