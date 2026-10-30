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
    count_nodes_training,
    extract_variables,
    get_ast_depth,
    format_expr,
)
from backend.app.core.verifier import (
    verify_equivalence,
    STATUS_VERIFIED,
    STATUS_SAT,
    STATUS_UNKNOWN,
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

    def test_flat_chain_2400_terms_rejected_cleanly(self):
        """A flat chain of 2,400 terms (x+x+...+x) is rejected cleanly without RecursionError.

        Verifies that no RecursionError occurs in the parser, depth check, or Z3 conversion.
        The gate enforces the depth limit iteratively and rejects with SafetyViolationError.
        """
        expr = "x" + "+x" * 2399  # 4799 chars <= 5000 chars, depth = 2402 > 100
        # 1. Gate check via is_safe_ast
        safe, err = is_safe_ast(expr)
        assert not safe
        assert "AST depth exceeds limit" in err

        # 2. Gate check via validate_ast raises SafetyViolationError directly without RecursionError
        with pytest.raises(SafetyViolationError) as exc_info:
            validate_ast(expr)
        assert "depth exceeds limit" in str(exc_info.value).lower()

        # 3. Z3 verifier catches the violation cleanly and returns STATUS_INVALID without RecursionError
        res = verify_equivalence(expr, "x")
        assert res["status"] == STATUS_INVALID
        assert "depth exceeds limit" in res["error"].lower()

    def test_rejects_negative_shift_amounts(self):
        """Negative constant shift amounts must be rejected by the safety gate."""
        disallowed_shifts = [
            "x << -1",
            "x >> -2",
            "x << (-5)",
            "x >> (-64)",
        ]
        for expr in disallowed_shifts:
            safe, err = is_safe_ast(expr)
            assert not safe, f"Expected negative shift '{expr}' to be rejected"
            with pytest.raises(SafetyViolationError):
                validate_ast(expr)


# ==============================================================================
# 2. AST Utilities Tests
# ==============================================================================

class TestAstUtils:
    """Verifies AST analysis, node counting, and variable extraction."""

    def test_count_nodes_accurate(self):
        """Counts strictly BinOp, UnaryOp, Name, and Constant nodes."""
        # "x" -> Name (1 node)
        assert count_nodes("x") == 1

        # "x + y" -> BinOp(+), Name(x), Name(y) (3 nodes)
        assert count_nodes("x + y") == 3

        # "(x ^ y) + 2 * (x & y)" -> 4 BinOps (+, ^, *, &), 1 Constant (2), 4 Names (x, y, x, y) = 9 nodes
        assert count_nodes("(x ^ y) + 2 * (x & y)") == 9

        # Unary ~x -> UnaryOp(~), Name(x) = 2 nodes
        assert count_nodes("~x") == 2

    def test_count_nodes_training(self):
        """Counts AST nodes using training notebook counter including operators (13 for demo, 4 for x + y)."""
        assert count_nodes_training("(x ^ y) + 2 * (x & y)") == 13
        assert count_nodes_training("x + y") == 4
        assert count_nodes_training("x") == 1
        assert count_nodes_training("~x") == 3

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
        res = verify_equivalence("x + y", "x ^ y", witness_policy="bounded")
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
        # The witness values must be bounded and small
        assert wx < 16 and wy < 16

    def test_demo_witness_is_small(self):
        """Asserts that the demo expression witness values are small under bounded policy (ULT(v, 2) yields x=1, y=1)."""
        res = verify_equivalence("(x ^ y) + 2 * (x & y)", "x ^ y", witness_policy="bounded")
        assert res["status"] == STATUS_SAT
        assert res["witness"] == {"x": 1, "y": 1}
        assert res["expected"] == 2
        assert res["actual"] == 0

    def test_witness_policy_z3_default(self):
        """Asserts that z3_default witness policy queries raw unconstrained solver directly."""
        res = verify_equivalence("(x ^ y) + 2 * (x & y)", "x ^ y", witness_policy="z3_default")
        assert res["status"] == STATUS_SAT
        assert "x" in res["witness"] and "y" in res["witness"]
        assert res["expected"] != res["actual"]

    def test_candidate_wrong_only_on_large_inputs(self):
        """A candidate wrong only on large inputs returns SAT via fallback."""
        # For x < 16, x >> 32 == 0, so x ^ (x >> 32) == x (bounded query is UNSAT).
        # Fallback to unconstrained query must detect discrepancy when x >= 4294967296 and return SAT.
        orig = "x"
        cand = "x ^ (x >> 32)"
        res = verify_equivalence(orig, cand, witness_policy="bounded")
        assert res["status"] == STATUS_SAT
        assert res["witness"]["x"] >= 16
        assert res["expected"] != res["actual"]

    def test_bounded_unsat_never_yields_verified_status(self):
        """Bounded UNSAT must never emit STATUS_VERIFIED."""
        orig = "x"
        cand = "x ^ (x >> 32)"
        res = verify_equivalence(orig, cand, witness_policy="bounded")
        assert res["status"] == "SAT"
        assert res["witness"]["x"] >= 2**32

    def test_recompute_expected_actual_python_evaluation(self):
        """For every SAT counterexample, independently recompute in plain Python with 64-bit mask."""
        import ast

        def eval_uint64(expr: str, env: dict) -> int:
            tree = ast.parse(expr, mode="eval")
            MASK = 0xFFFFFFFFFFFFFFFF

            def _eval(node: ast.AST) -> int:
                if isinstance(node, ast.Expression):
                    return _eval(node.body)
                elif isinstance(node, ast.Name):
                    return env[node.id] & MASK
                elif isinstance(node.value if isinstance(node, ast.Constant) else None, int):
                    return node.value & MASK
                elif isinstance(node, ast.UnaryOp):
                    v = _eval(node.operand)
                    if isinstance(node.op, ast.Invert):
                        return (~v) & MASK
                    elif isinstance(node.op, ast.USub):
                        return (-v) & MASK
                elif isinstance(node, ast.BinOp):
                    l = _eval(node.left)
                    r = _eval(node.right)
                    if isinstance(node.op, ast.Add):
                        return (l + r) & MASK
                    elif isinstance(node.op, ast.Sub):
                        return (l - r) & MASK
                    elif isinstance(node.op, ast.Mult):
                        return (l * r) & MASK
                    elif isinstance(node.op, ast.BitAnd):
                        return (l & r) & MASK
                    elif isinstance(node.op, ast.BitOr):
                        return (l | r) & MASK
                    elif isinstance(node.op, ast.BitXor):
                        return (l ^ r) & MASK
                    elif isinstance(node.op, ast.LShift):
                        return (l << r) & MASK if r < 64 else 0
                    elif isinstance(node.op, ast.RShift):
                        return (l >> r) & MASK if r < 64 else 0
                raise ValueError(f"Unsupported node: {node}")

            return _eval(tree)

        cases = [
            ("x + y", "x ^ y"),
            ("(x ^ y) + 2 * (x & y)", "x ^ y"),
            ("x", "x ^ (x >> 32)"),
            ("x + y", "x + z"),
        ]
        for orig, cand in cases:
            res = verify_equivalence(orig, cand)
            assert res["status"] == STATUS_SAT
            expected_py = eval_uint64(orig, res["witness"])
            actual_py = eval_uint64(cand, res["witness"])
            assert expected_py == res["expected"], f"Expected mismatch for {orig} under witness {res['witness']}"
            assert actual_py == res["actual"], f"Actual mismatch for {cand} under witness {res['witness']}"
            assert expected_py != actual_py

    def test_candidate_with_variable_not_in_original(self):
        """Candidate containing a variable not present in original is handled cleanly."""
        res = verify_equivalence("x + y", "x + z")
        assert res["status"] == STATUS_SAT
        assert "x" in res["witness"]
        assert "y" in res["witness"]
        assert "z" in res["witness"]

    def test_unary_operators_and_identities(self):
        """Tests unary bitwise inversion (~) and arithmetic negation (-)."""
        # Double bitwise NOT
        res_not = verify_equivalence("~(~x)", "x")
        assert res_not["status"] == STATUS_VERIFIED

        # Double negation
        res_neg = verify_equivalence("-(-x)", "x")
        assert res_neg["status"] == STATUS_VERIFIED

        # Negation algebraic identity: -(x - y) == y - x
        res_sub = verify_equivalence("-(x - y)", "y - x")
        assert res_sub["status"] == STATUS_VERIFIED

    def test_shifts_z3_default_semantics(self):
        """Under default Z3 semantics, shifts >= 64 evaluate to 0."""
        # x << 64 == 0
        assert verify_equivalence("x << 64", "0", shift_semantics="z3")["status"] == STATUS_VERIFIED

        # x >> 64 == 0
        assert verify_equivalence("x >> 64", "0", shift_semantics="z3")["status"] == STATUS_VERIFIED

        # x << 65 == 0
        assert verify_equivalence("x << 65", "0", shift_semantics="z3")["status"] == STATUS_VERIFIED

    def test_shifts_x86_mask_semantics(self):
        """Under x86 hardware semantics, shifts >= 64 are masked to 6 bits (0-63)."""
        # x << 64 == x << 0 == x
        assert verify_equivalence("x << 64", "x", shift_semantics="x86_mask")["status"] == STATUS_VERIFIED

        # x >> 64 == x >> 0 == x
        assert verify_equivalence("x >> 64", "x", shift_semantics="x86_mask")["status"] == STATUS_VERIFIED

        # x << 65 == x << 1
        assert verify_equivalence("x << 65", "x << 1", shift_semantics="x86_mask")["status"] == STATUS_VERIFIED

        # x >> 66 == x >> 2
        assert verify_equivalence("x >> 66", "x >> 2", shift_semantics="x86_mask")["status"] == STATUS_VERIFIED

    def test_shifts_by_64_or_more_in_both_semantics_modes(self):
        """Verifies shift amounts >= 64 across both Z3 default and x86_mask modes."""
        # 1. In 'z3' mode: shifts >= 64 yield 0
        assert verify_equivalence("x << 64", "0", shift_semantics="z3")["status"] == STATUS_VERIFIED
        assert verify_equivalence("x >> 64", "0", shift_semantics="z3")["status"] == STATUS_VERIFIED
        assert verify_equivalence("x << 70", "0", shift_semantics="z3")["status"] == STATUS_VERIFIED
        assert verify_equivalence("x >> 128", "0", shift_semantics="z3")["status"] == STATUS_VERIFIED

        # 2. In 'x86_mask' mode: shift amounts are masked with & 63
        # 64 & 63 == 0 -> x << 0 == x
        assert verify_equivalence("x << 64", "x", shift_semantics="x86_mask")["status"] == STATUS_VERIFIED
        assert verify_equivalence("x >> 64", "x", shift_semantics="x86_mask")["status"] == STATUS_VERIFIED
        # 70 & 63 == 6 -> x << 6
        assert verify_equivalence("x << 70", "x << 6", shift_semantics="x86_mask")["status"] == STATUS_VERIFIED
        # 128 & 63 == 0 -> x >> 0 == x
        assert verify_equivalence("x >> 128", "x", shift_semantics="x86_mask")["status"] == STATUS_VERIFIED

    def test_timeout_returns_unknown(self):
        """Solver timeout returns STATUS_UNKNOWN gracefully."""
        # A timeout of 0 ms forces an immediate timeout in Z3
        res = verify_equivalence("x * y * z", "z * y * x", timeout_ms=0)
        assert res["status"] in ("UNKNOWN", STATUS_UNKNOWN)

    def test_64bit_overflow_wrapping(self):
        """Verifies that 64-bit addition wraps cleanly to 0 without overflow error."""
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

    def test_rshift_semantics_logical_vs_arithmetic(self):
        """Tests RSHIFT_SEMANTICS: logical (LShR / zero-fill) vs arithmetic (bvsashr / sign-extend)."""
        # 1. Under logical right shift (default for formal proofs):
        # 0xFFFFFFFFFFFFFFFF >> 1 == 0x7FFFFFFFFFFFFFFF
        res_logic = verify_equivalence("0xFFFFFFFFFFFFFFFF >> 1", "0x7FFFFFFFFFFFFFFF", rshift_semantics="logical")
        assert res_logic["status"] == STATUS_VERIFIED

        # 2. Under arithmetic right shift (training verifier behavior):
        # 0xFFFFFFFFFFFFFFFF >> 1 preserves sign bit, staying 0xFFFFFFFFFFFFFFFF
        res_arith = verify_equivalence("0xFFFFFFFFFFFFFFFF >> 1", "0xFFFFFFFFFFFFFFFF", rshift_semantics="arithmetic")
        assert res_arith["status"] == STATUS_VERIFIED

        # 3. Discrepancy check: 0xFFFFFFFFFFFFFFFF >> 1 is NOT 0x7FFFFFFFFFFFFFFF under arithmetic:
        res_diff = verify_equivalence("0xFFFFFFFFFFFFFFFF >> 1", "0x7FFFFFFFFFFFFFFF", rshift_semantics="arithmetic")
        assert res_diff["status"] == STATUS_SAT

    def test_invalid_syntax_returns_invalid_status(self):
        """Expressions violating safety or syntax return STATUS_INVALID without raising."""
        res1 = verify_equivalence("__import__('os').system('calc')", "x + y")
        assert res1["status"] == STATUS_INVALID
        assert "Disallowed" in res1["error"]

        res2 = verify_equivalence("x + y", "3.14 + x")
        assert res2["status"] == STATUS_INVALID

        res3 = verify_equivalence("x +", "x")
        assert res3["status"] == STATUS_INVALID
