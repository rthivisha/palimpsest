"""Unit tests for PALIMPSEST Core: Safety Gate, AST Utils, and Z3 Verifier.

Tests:
1. Safety Gate:
   - Rejects dangerous syntax: __import__, function calls, attribute access, strings,
     floats, lambdas, subscripts, list/dict expressions.
   - Enforces length limit (5,000 characters).
   - Enforces tree depth limit (100).
   - Accepts valid 64-bit integer bitwise-arithmetic expressions.
2. AST Utilities:
   - Accurately counts AST nodes for canonical and obfuscated expressions.
   - Extracts unique variable identifiers from multi-variable expressions.
   - Computes tree depth.
3. Formal Z3 64-bit Verifier:
   - Proves known MBA identities equivalent (QF_BV_UNSAT_64BIT_VERIFIED).
   - Generates concrete counterexample witness for invalid candidates (SAT).
   - Verifies 64-bit wrapping and overflow behavior.
   - Verifies logical right shift (LShR) behavior.
   - Handles malformed inputs gracefully with STATUS_INVALID without crashing.
"""
import pytest

from backend.app.core.safety import (
    validate_ast,
    is_safe_ast,
    SafetyViolationError,
    MAX_EXPRESSION_LENGTH,
)
from backend.app.core.ast_utils import (
    count_nodes,
    extract_variables,
    get_ast_depth,
    format_expr,
)
from backend.app.core.verifier import (
    verify_equivalence,
    STATUS_VERIFIED,
    STATUS_SAT,
    STATUS_INVALID,
)


# ==============================================================================
# 1. Safety Gatekeeper Tests
# ==============================================================================

class TestSafetyGate:
    """Verifies that the AST security gate strictly rejects untrusted or malicious constructs."""

    def test_accepts_valid_mba_expressions(self):
        """Standard MBA expressions containing allowed operators must pass."""
        valid_expressions = [
            "x + y",
            "(x ^ y) + 2 * (x & y)",
            "~x + 1",
            "-rax + (rbx << 2) - (rcx >> 1)",
            "((x | y) - (x & y)) * 0 + z",
            "0x1000 + rax - 0x20",
        ]
        for expr in valid_expressions:
            safe, err = is_safe_ast(expr)
            assert safe, f"Expected '{expr}' to be safe, but got error: {err}"
            # validate_ast must return without raising
            tree = validate_ast(expr)
            assert tree is not None

    def test_rejects_function_calls(self):
        """Any function or method invocation must be rejected."""
        dangerous = [
            "exit()",
            "print('attack')",
            "__import__('os').system('calc')",
            "open('/etc/passwd')",
        ]
        for expr in dangerous:
            safe, err = is_safe_ast(expr)
            assert not safe, f"Expected call '{expr}' to be rejected"
            with pytest.raises(SafetyViolationError):
                validate_ast(expr)

    def test_rejects_attribute_access(self):
        """Attribute lookups (e.g. object introspection) must be rejected."""
        dangerous = [
            "x.__class__",
            "(1).__class__.__bases__",
            "x.attr",
        ]
        for expr in dangerous:
            safe, err = is_safe_ast(expr)
            assert not safe, f"Expected attribute lookup '{expr}' to be rejected"
            with pytest.raises(SafetyViolationError):
                validate_ast(expr)

    def test_rejects_non_integer_constants(self):
        """Strings, floats, and booleans must be strictly rejected."""
        invalid_constants = [
            "'hello' + x",
            "3.14 + y",
            "True + x",
            "False & y",
        ]
        for expr in invalid_constants:
            safe, err = is_safe_ast(expr)
            assert not safe, f"Expected constant in '{expr}' to be rejected"
            with pytest.raises(SafetyViolationError):
                validate_ast(expr)

    def test_rejects_lambdas_and_subscripts(self):
        """Lambdas, subscripts, and collection literals must be rejected."""
        disallowed = [
            "(lambda x: x + 1)(y)",
            "x[0] + y",
            "[1, 2, 3] + x",
            "{'a': 1} + x",
        ]
        for expr in disallowed:
            safe, err = is_safe_ast(expr)
            assert not safe, f"Expected '{expr}' to be rejected"
            with pytest.raises(SafetyViolationError):
                validate_ast(expr)

    def test_rejects_oversized_expressions(self):
        """Expressions exceeding 5,000 characters must be rejected."""
        oversized = "x" + " + x" * (MAX_EXPRESSION_LENGTH // 4 + 10)
        assert len(oversized) > MAX_EXPRESSION_LENGTH
        safe, err = is_safe_ast(oversized)
        assert not safe
        assert "maximum character limit" in err

    def test_rejects_deeply_nested_ast(self):
        """Expressions with nesting depth > 100 must be rejected."""
        # Unary ~ nested 120 layers creates an AST tree of depth > 100
        deep = "~" * 120 + "x"
        safe, err = is_safe_ast(deep)
        assert not safe
        assert "AST depth exceeds limit" in err


# ==============================================================================
# 2. AST Utilities Tests
# ==============================================================================

class TestAstUtils:
    """Verifies AST analysis, node counting, and variable extraction."""

    def test_count_nodes_accurate(self):
        """Counts nodes for simple and composite expressions."""
        # "x" -> Expression -> Name -> Load (3 nodes in ast.walk)
        cnt_x = count_nodes("x")
        assert cnt_x > 0

        # "x + y" must have more nodes than "x"
        cnt_add = count_nodes("x + y")
        assert cnt_add > cnt_x

        # Obfuscated identity must have strictly more nodes than canonical target
        canonical = "x + y"
        obfuscated = "(x ^ y) + 2 * (x & y)"
        assert count_nodes(obfuscated) > count_nodes(canonical)

    def test_extract_variables(self):
        """Discovers all variable identifiers without duplicates."""
        expr1 = "(rax ^ rbx) + 2 * (rax & rbx) - rcx"
        vars1 = extract_variables(expr1)
        assert vars1 == ["rax", "rbx", "rcx"]

        expr2 = "x + 0x1000 - y * z"
        vars2 = extract_variables(expr2)
        assert vars2 == ["x", "y", "z"]

    def test_get_ast_depth(self):
        """Computes tree depth correctly."""
        depth_flat = get_ast_depth("x + y")
        depth_nested = get_ast_depth("((x + 1) + 2) + 3")
        assert depth_nested > depth_flat

    def test_format_expr(self):
        """Normalizes expression string using ast.unparse."""
        formatted = format_expr("  x  +   y  ")
        assert formatted == "x + y"


# ==============================================================================
# 3. Formal Z3 64-Bit Verifier Tests
# ==============================================================================

class TestZ3Verifier:
    """Verifies formal SMT equivalence checking over 64-bit BitVecs."""

    def test_known_mba_identities_verified(self):
        """Known MBA theorems must return QF_BV_UNSAT_64BIT_VERIFIED (UNSAT)."""
        identities = [
            # Classic linear MBA addition identity
            ("(x ^ y) + 2 * (x & y)", "x + y"),
            # Linear MBA subtraction identity
            ("(x ^ y) - 2 * (~x & y)", "x - y"),
            # XOR identity from OR and AND
            ("(x | y) - (x & y)", "x ^ y"),
            # Double negation identity
            ("~(~x)", "x"),
            # Opaque zero identity: (x & ~x) is always 0
            ("((x & ~x) * z) + (x | y)", "x | y"),
            # Register arithmetic and constant folding
            ("rax + 0x1000", "(rax + 0x800) + 0x800"),
        ]
        for obf, target in identities:
            res = verify_equivalence(obf, target)
            assert res["status"] == STATUS_VERIFIED, (
                f"Expected '{obf}' == '{target}' to be verified, got {res}"
            )
            assert res["witness"] == {}
            assert res["expected"] is None
            assert res["actual"] is None
            assert res["diff_bits"] is None
            assert res["latency_ms"] >= 0.0

    def test_inequivalent_candidates_return_sat_with_witness(self):
        """An incorrect guess must return SAT and provide a concrete counterexample witness."""
        # Original: x + y. Incorrect candidate: x ^ y.
        # Differ whenever both x and y have bit 1 set (e.g. x=1, y=1: 1+1=2, 1^1=0).
        res = verify_equivalence("x + y", "x ^ y")
        assert res["status"] == STATUS_SAT
        assert "x" in res["witness"]
        assert "y" in res["witness"]
        assert res["expected"] is not None
        assert res["actual"] is not None
        assert res["expected"] != res["actual"]

        # Check that diff_bits is a 64-character binary string
        assert isinstance(res["diff_bits"], str)
        assert len(res["diff_bits"]) == 64
        # At least one bit must differ
        assert "1" in res["diff_bits"]

        # Validate that evaluating the witness independently produces the same discrepancy
        wx = res["witness"]["x"]
        wy = res["witness"]["y"]
        expected_calc = (wx + wy) & 0xFFFFFFFFFFFFFFFF
        actual_calc = (wx ^ wy) & 0xFFFFFFFFFFFFFFFF
        assert res["expected"] == expected_calc
        assert res["actual"] == actual_calc

    def test_64bit_overflow_wrapping(self):
        """Verifies that addition modulo 2^64 wraps cleanly to 0 without overflow error."""
        # 0xFFFFFFFFFFFFFFFF + 1 == 0 in 64-bit unsigned arithmetic
        res = verify_equivalence("x + 0xFFFFFFFFFFFFFFFF + 1", "x")
        assert res["status"] == STATUS_VERIFIED

    def test_logical_right_shift(self):
        """Verifies that '>>' acts as a logical right shift (LShR), shifting in zeros."""
        # Under logical right shift, ~0 (0xFFFFFFFFFFFFFFFF) >> 1 is 0x7FFFFFFFFFFFFFFF.
        # Under arithmetic shift, it would remain 0xFFFFFFFFFFFFFFFF (-1).
        # We test that 0xFFFFFFFFFFFFFFFF >> 1 equals 0x7FFFFFFFFFFFFFFF:
        res = verify_equivalence("0xFFFFFFFFFFFFFFFF >> 1", "0x7FFFFFFFFFFFFFFF")
        assert res["status"] == STATUS_VERIFIED

    def test_invalid_syntax_returns_invalid_status(self):
        """Expressions violating safety or syntax return STATUS_INVALID without raising."""
        res1 = verify_equivalence("__import__('os').system('calc')", "x + y")
        assert res1["status"] == STATUS_INVALID
        assert "Disallowed" in res1["error"]

        res2 = verify_equivalence("x + y", "3.14 + x")
        assert res2["status"] == STATUS_INVALID

        res3 = verify_equivalence("x +", "x")
        assert res3["status"] == STATUS_INVALID
