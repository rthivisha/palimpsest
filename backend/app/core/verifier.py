"""Formal Z3 Equivalence Verifier for 64-bit Mixed Boolean-Arithmetic (MBA).

Why this module exists:
In neurosymbolic synthesis, a neural language model proposes an unverified candidate
simplification (e.g. "x + y"). We NEVER trust this guess blindly.

Instead, we construct an SMT "miter circuit" in Microsoft Z3 using the Quantifier-Free
Bit-Vector (QF_BV) theory:
    miter = (E_original != E_candidate)

We ask the Z3 solver: "Does there exist ANY 64-bit input combination (x, y, ...)
such that E_original != E_candidate?"

Two mathematical outcomes are possible:
1. UNSAT (Unsatisfiable):
   No counterexample exists in the entire 2^64 input space. The candidate is PROVEN
   100% equivalent to the original expression. We accept it.
2. SAT (Satisfiable):
   The solver synthesizes a concrete counterexample witness (e.g., x=1, y=1) where
   the original and candidate evaluate to different values (e.g., expected=2, actual=0).
   We extract this witness and feed it back into the CEGIS loop to guide the next proposal.
"""
import ast
import time
from typing import Any, Dict, List, Optional, Set

import z3

from backend.app.core.safety import validate_ast, SafetyViolationError
from backend.app.core.ast_utils import extract_variables


# Standard 64-bit word size used across modern architectures (x86_64, ARM64)
BIT_WIDTH: int = 64

# Bit mask to clamp integer values to unsigned 64-bit integers
UINT64_MASK: int = 0xFFFFFFFFFFFFFFFF

# Shift mask (x86-64 shifts by count mod 64)
SHIFT_MASK: int = 63

# Status string constants matching the dataset generator and runtime contract
STATUS_VERIFIED: str = "QF_BV_UNSAT_64BIT_VERIFIED"
STATUS_SAT: str = "SAT"
STATUS_UNKNOWN: str = "UNKNOWN"
STATUS_INVALID: str = "INVALID"


class Z3TranslationError(Exception):
    """Raised when an AST node cannot be mapped to a Z3 BitVec representation."""
    pass


def _ast_to_z3(node: ast.AST, var_map: Dict[str, z3.BitVecRef]) -> z3.BitVecRef:
    """Recursively converts a validated Python AST into a Z3 BitVec expression tree.

    Args:
        node: The AST node to translate.
        var_map: Mapping from variable names to shared z3.BitVec instances.

    Returns:
        A 64-bit Z3 BitVec expression.
    """
    if isinstance(node, ast.Expression):
        return _ast_to_z3(node.body, var_map)

    # Identifiers: return the shared 64-bit BitVec for this variable name
    elif isinstance(node, ast.Name):
        if node.id not in var_map:
            var_map[node.id] = z3.BitVec(node.id, BIT_WIDTH)
        return var_map[node.id]

    # Constants: mask to 64-bit unsigned integer and construct BitVecVal
    elif isinstance(node, ast.Constant):
        if type(node.value) is not int or isinstance(node.value, bool):
            raise Z3TranslationError(f"Constant must be integer, got {node.value}")
        masked_val = node.value & UINT64_MASK
        return z3.BitVecVal(masked_val, BIT_WIDTH)

    # Unary operations: bitwise NOT (~) and negation (-)
    elif isinstance(node, ast.UnaryOp):
        operand_bv = _ast_to_z3(node.operand, var_map)
        if isinstance(node.op, ast.Invert):
            # Bitwise NOT (~)
            return ~operand_bv
        elif isinstance(node.op, ast.USub):
            # Two's complement unary minus (-x)
            return -operand_bv
        else:
            raise Z3TranslationError(f"Unsupported unary operator: {type(node.op).__name__}")

    # Binary operations
    elif isinstance(node, ast.BinOp):
        left_bv = _ast_to_z3(node.left, var_map)
        right_bv = _ast_to_z3(node.right, var_map)

        if isinstance(node.op, ast.Add):
            return left_bv + right_bv
        elif isinstance(node.op, ast.Sub):
            return left_bv - right_bv
        elif isinstance(node.op, ast.Mult):
            return left_bv * right_bv
        elif isinstance(node.op, ast.BitAnd):
            return left_bv & right_bv
        elif isinstance(node.op, ast.BitOr):
            return left_bv | right_bv
        elif isinstance(node.op, ast.BitXor):
            return left_bv ^ right_bv
        elif isinstance(node.op, ast.LShift):
            # Left shift: mask shift amount to 6 bits (0-63)
            shift_amt = right_bv & z3.BitVecVal(SHIFT_MASK, BIT_WIDTH)
            return left_bv << shift_amt
        elif isinstance(node.op, ast.RShift):
            # Logical shift right (LShR): zeros are shifted in from the left
            shift_amt = right_bv & z3.BitVecVal(SHIFT_MASK, BIT_WIDTH)
            return z3.LShR(left_bv, shift_amt)
        else:
            raise Z3TranslationError(f"Unsupported binary operator: {type(node.op).__name__}")

    else:
        raise Z3TranslationError(f"Disallowed AST node encountered during Z3 translation: {type(node).__name__}")


def verify_equivalence(
    original_expr: str,
    candidate_expr: str,
    timeout_ms: int = 3000
) -> Dict[str, Any]:
    """Formally verifies whether original_expr == candidate_expr for all 64-bit inputs.

    Performs a formal miter check using Z3 QF_BV (Quantifier-Free Bit-Vectors).

    Args:
        original_expr: The original obfuscated MBA expression string.
        candidate_expr: The model-proposed simplified expression string.
        timeout_ms: Solver timeout in milliseconds (default: 3000ms).

    Returns:
        A dictionary with the following schema:
        {
            "status": "QF_BV_UNSAT_64BIT_VERIFIED" | "SAT" | "UNKNOWN" | "INVALID",
            "witness": {"x": 1, "y": 1},   # Disproving variable assignments (if SAT)
            "expected": 2,                 # Ground truth evaluation at witness (if SAT)
            "actual": 0,                   # Candidate evaluation at witness (if SAT)
            "diff_bits": "00...0010",      # 64-character binary string of (expected ^ actual)
            "latency_ms": 1.25,            # Verification duration in milliseconds
            "error": "..."                 # Error message if status == "INVALID"
        }
    """
    start_time = time.perf_counter()

    # 1. Security Gate & AST Validation
    try:
        orig_ast = validate_ast(original_expr)
        cand_ast = validate_ast(candidate_expr)
    except (SafetyViolationError, Exception) as err:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return {
            "status": STATUS_INVALID,
            "witness": {},
            "expected": None,
            "actual": None,
            "diff_bits": None,
            "latency_ms": round(latency_ms, 3),
            "error": str(err),
        }

    # 2. Variable Discovery & Shared Z3 Allocation
    # All variables present across both expressions must share the exact same Z3 BitVec symbols.
    all_vars: Set[str] = set(extract_variables(orig_ast)) | set(extract_variables(cand_ast))
    var_map: Dict[str, z3.BitVecRef] = {
        var_name: z3.BitVec(var_name, BIT_WIDTH) for var_name in all_vars
    }

    # 3. Translate ASTs to Z3 BitVec expressions
    try:
        z3_orig = _ast_to_z3(orig_ast, var_map)
        z3_cand = _ast_to_z3(cand_ast, var_map)
    except Z3TranslationError as err:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return {
            "status": STATUS_INVALID,
            "witness": {},
            "expected": None,
            "actual": None,
            "diff_bits": None,
            "latency_ms": round(latency_ms, 3),
            "error": str(err),
        }

    # 4. Construct SMT Miter: original != candidate
    solver = z3.Solver()
    solver.set("timeout", timeout_ms)
    solver.add(z3_orig != z3_cand)

    # 5. Check Equivalence
    check_res = solver.check()
    latency_ms = (time.perf_counter() - start_time) * 1000.0

    # Case A: UNSAT -> Provably equivalent
    if check_res == z3.unsat:
        return {
            "status": STATUS_VERIFIED,
            "witness": {},
            "expected": None,
            "actual": None,
            "diff_bits": None,
            "latency_ms": round(latency_ms, 3),
            "error": None,
        }

    # Case B: SAT -> Counterexample witness exists
    elif check_res == z3.sat:
        model = solver.model()
        witness: Dict[str, int] = {}

        # Extract concrete 64-bit integer values for all variables
        for var_name, z3_var in sorted(var_map.items()):
            evaluated = model.eval(z3_var, model_completion=True)
            # Default to 0 if variable is unconstrained
            val = evaluated.as_long() if hasattr(evaluated, "as_long") else 0
            witness[var_name] = val & UINT64_MASK

        # Evaluate expected (original) and actual (candidate) values under the model
        orig_eval = model.eval(z3_orig, model_completion=True)
        cand_eval = model.eval(z3_cand, model_completion=True)

        expected_val = (orig_eval.as_long() if hasattr(orig_eval, "as_long") else 0) & UINT64_MASK
        actual_val = (cand_eval.as_long() if hasattr(cand_eval, "as_long") else 0) & UINT64_MASK

        # Calculate 64-bit binary diff string: bit i is '1' if expected and actual differ
        diff_bits = format(expected_val ^ actual_val, "064b")

        return {
            "status": STATUS_SAT,
            "witness": witness,
            "expected": expected_val,
            "actual": actual_val,
            "diff_bits": diff_bits,
            "latency_ms": round(latency_ms, 3),
            "error": None,
        }

    # Case C: UNKNOWN (Timeout or solver limit reached)
    else:
        return {
            "status": STATUS_UNKNOWN,
            "witness": {},
            "expected": None,
            "actual": None,
            "diff_bits": None,
            "latency_ms": round(latency_ms, 3),
            "error": "Z3 solver returned UNKNOWN (timeout or resource limit reached)",
        }
