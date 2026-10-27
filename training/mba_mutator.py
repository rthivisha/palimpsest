"""MBA (Mixed Boolean-Arithmetic) Mutator for dataset generation and benchmarking.

Implements rule-based algebraic rewriting and opaque predicate injection:
- Linear MBA rewrite rules: e.g. x + y = (x ^ y) + 2 * (x & y)
- Opaque Zero injection: terms that mathematically evaluate to 0 for all 64-bit inputs
- Opaque One injection: terms that mathematically evaluate to 1 or -1
- Constant unfolding: decomposing constants into equivalent algebraic operations
"""
import ast
import random
from typing import Any, Dict, List, Optional, Union


# Canonical seed expressions representing clean ground truth
SEEDS: List[str] = [
    "x + y",
    "x - y",
    "x ^ y",
    "x & y",
    "x | y",
    "x + 1",
    "x - 1",
    "~x + y",
    "(x ^ y) + 1",
    "rax + rbx",
    "rax - rbx",
    "rcx ^ rdx",
    "rsi & rdi",
    "r8 | r9",
    "rax + 0x10",
    "rbx ^ 0x55",
]

OPAQUE_ZEROS: List[str] = [
    "((x & ~x) * z)",
    "((x ^ x) & y)",
    "((x | y) - (x | y))",
    "((x & y) - (y & x))",
    "((x & 0) * y)",
    "((rax ^ rax) * rbx)",
]

OPAQUE_ONES: List[str] = [
    "((x | ~x) & 1)",
    "((rax | ~rax) & 1)",
    "((x ^ ~x) & 1)",
]


def get_masked_const(val: int) -> int:
    """Clamps constant to 64-bit unsigned integer."""
    return val & 0xFFFFFFFFFFFFFFFF


class Node:
    """Simple Intermediate Representation (IR) node for expression tree manipulation."""
    def __init__(self, op: str, children: Optional[List[Any]] = None, value: Any = None):
        self.op = op
        self.children = children or []
        self.value = value

    def to_string(self) -> str:
        if self.op == "CONST":
            return str(self.value)
        elif self.op == "VAR":
            return str(self.value)
        elif self.op == "UNARY_NOT":
            child_str = self.children[0].to_string()
            return f"(~{child_str})"
        elif self.op == "UNARY_NEG":
            child_str = self.children[0].to_string()
            return f"(-{child_str})"
        elif len(self.children) == 2:
            left_str = self.children[0].to_string()
            right_str = self.children[1].to_string()
            return f"({left_str} {self.op} {right_str})"
        return str(self.value)


class Const(Node):
    def __init__(self, value: int):
        super().__init__(op="CONST", value=get_masked_const(value))


def parse_to_ir(expr_str: str) -> Node:
    """Parses a mathematical expression string into IR Node representation."""
    tree = ast.parse(expr_str.strip(), mode="eval")

    def _convert(n: ast.AST) -> Node:
        if isinstance(n, ast.Expression):
            return _convert(n.body)
        elif isinstance(n, ast.Name):
            return Node(op="VAR", value=n.id)
        elif isinstance(n, ast.Constant):
            return Const(n.value)
        elif isinstance(n, ast.UnaryOp):
            if isinstance(n.op, ast.Invert):
                return Node(op="UNARY_NOT", children=[_convert(n.operand)])
            elif isinstance(n.op, ast.USub):
                return Node(op="UNARY_NEG", children=[_convert(n.operand)])
        elif isinstance(n, ast.BinOp):
            op_map = {
                ast.Add: "+",
                ast.Sub: "-",
                ast.Mult: "*",
                ast.BitAnd: "&",
                ast.BitOr: "|",
                ast.BitXor: "^",
                ast.LShift: "<<",
                ast.RShift: ">>",
            }
            op_sym = op_map.get(type(n.op), "+")
            return Node(op=op_sym, children=[_convert(n.left), _convert(n.right)])
        return Node(op="VAR", value="x")

    return _convert(tree)


class MBAMutator:
    """Mutates expressions into syntactically complex but semantically equivalent forms."""

    def __init__(self) -> None:
        pass

    def mutate(self, seed: str, tier: int = 1) -> Dict[str, Any]:
        """Applies curriculum-tiered obfuscation to a seed expression.

        Tier 1: Linear MBA identity rewrite (e.g. x + y -> (x ^ y) + 2 * (x & y)).
        Tier 2: Tier 1 + Opaque zero/one injection.
        Tier 3: Tier 2 + nested expansion and constant folding decomposition.
        """
        ledger: List[str] = []
        current = seed

        # Tier 1: Linear MBA expansion
        if "+" in current and random.random() < 0.85:
            # Replace a + b with (a ^ b) + 2 * (a & b)
            parts = current.split("+", 1)
            lhs = parts[0].strip()
            rhs = parts[1].strip()
            current = f"(({lhs} ^ {rhs}) + 2 * ({lhs} & {rhs}))"
            ledger.append(f"Linear MBA: {lhs} + {rhs} -> (({lhs} ^ {rhs}) + 2 * ({lhs} & {rhs}))")
        elif "-" in current and random.random() < 0.85:
            # Replace a - b with (a ^ ~b) + 1 + ~b
            parts = current.split("-", 1)
            lhs = parts[0].strip()
            rhs = parts[1].strip()
            current = f"(({lhs} ^ {rhs}) - 2 * (~{lhs} & {rhs}))"
            ledger.append(f"Linear MBA: {lhs} - {rhs} -> (({lhs} ^ {rhs}) - 2 * (~{lhs} & {rhs}))")
        elif "^" in current and random.random() < 0.85:
            # Replace a ^ b with (a | b) - (a & b)
            parts = current.split("^", 1)
            lhs = parts[0].strip()
            rhs = parts[1].strip()
            current = f"(({lhs} | {rhs}) - ({lhs} & {rhs}))"
            ledger.append(f"Linear MBA: {lhs} ^ {rhs} -> (({lhs} | {rhs}) - ({lhs} & {rhs}))")

        # Tier 2: Add Opaque Zero terms
        if tier >= 2:
            oz = random.choice(OPAQUE_ZEROS)
            current = f"({current} + {oz})"
            ledger.append(f"Opaque Zero: {oz} == 0")

        # Tier 3: Additional nested expansion
        if tier >= 3:
            oz2 = random.choice(OPAQUE_ZEROS)
            current = f"({current} ^ {oz2})"
            ledger.append(f"Opaque Zero: {oz2} == 0")

        return {
            "obfuscated_expr": current,
            "mutation_ledger": ledger,
        }

    def unfold_constants(self, ir_node: Node) -> Node:
        """Decomposes immediate constants into equivalent arithmetic expressions."""
        if ir_node.op == "CONST":
            val = ir_node.value
            delta = random.choice([1, 2, 4, 8, 16, 0x10, 0x20])
            part1 = Node(op="CONST", value=(val - delta) & 0xFFFFFFFFFFFFFFFF)
            part2 = Node(op="CONST", value=delta)
            return Node(op="+", children=[part1, part2])
        if ir_node.children:
            ir_node.children = [self.unfold_constants(c) for c in ir_node.children]
        return ir_node

    def inject_opaque_zeros(self, ir_node: Node) -> Node:
        """Appends an opaque zero to the root node."""
        oz_str = random.choice(OPAQUE_ZEROS)
        oz_node = parse_to_ir(oz_str)
        return Node(op="+", children=[ir_node, oz_node])
