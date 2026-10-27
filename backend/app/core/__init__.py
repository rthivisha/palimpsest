"""Core symbolic and verification modules for PALIMPSEST.

Contains:
- safety: AST security gate preventing dangerous execution.
- ast_utils: AST node counting, variable extraction, and formatting.
- verifier: Formal Z3 SMT 64-bit BitVec miter equivalence verifier.
"""
from backend.app.core.safety import validate_ast, is_safe_ast, SafetyViolationError
from backend.app.core.ast_utils import count_nodes, extract_variables, get_ast_depth
from backend.app.core.verifier import verify_equivalence

__all__ = [
    "validate_ast",
    "is_safe_ast",
    "SafetyViolationError",
    "count_nodes",
    "extract_variables",
    "get_ast_depth",
    "verify_equivalence",
]
