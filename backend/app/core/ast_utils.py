"""AST utilities for PALIMPSEST expressions.

Node Counting Specification:
In PALIMPSEST, expression complexity and the de-obfuscation compression ratio
are defined strictly by counting the following four semantic AST node types:
1. `ast.BinOp`: Binary operators (+, -, *, &, |, ^, <<, >>)
2. `ast.UnaryOp`: Unary operators (~, -)
3. `ast.Name`: Variable identifiers (x, y, rax, rbx, etc.)
4. `ast.Constant`: Integer literals (1, 2, 0x100, etc.)

Non-semantic structural nodes (such as `ast.Expression` wrappers and `ast.Load` context)
are deliberately excluded from the count. Under this definition:
- Canonical 'x + y' has 3 nodes (1 BinOp + 2 Names).
- Obfuscated '(x ^ y) + 2 * (x & y)' has 9 nodes (4 BinOps + 1 Constant + 4 Names).
- The AST compression ratio is: round((1.0 - (final_nodes / obf_nodes)) * 100, 2).
"""
import ast
from typing import List, Set, Union


# Strict tuple of AST node types that contribute to node count
COUNTED_NODE_TYPES = (ast.BinOp, ast.UnaryOp, ast.Name, ast.Constant)

# Operator node types included in the training notebook's node counter
TRAINING_COUNTED_NODE_TYPES = (
    ast.BinOp,
    ast.UnaryOp,
    ast.Name,
    ast.Constant,
    ast.operator,
    ast.unaryop,
)


def get_ast_node(expr_or_node: Union[str, ast.AST]) -> ast.AST:
    """Helper to convert either a string or an AST node into an AST node.

    If given a string, parses it using mode='eval'.
    """
    if isinstance(expr_or_node, str):
        return ast.parse(expr_or_node.strip(), mode="eval")
    elif isinstance(expr_or_node, ast.AST):
        return expr_or_node
    else:
        raise TypeError(f"Expected str or ast.AST, got {type(expr_or_node).__name__}")


def count_nodes(expr_or_node: Union[str, ast.AST]) -> int:
    """Counts AST nodes representing actual semantic operations and operands.

    Strictly counts only:
    - ast.BinOp (binary operations: +, -, *, &, |, ^, <<, >>)
    - ast.UnaryOp (unary operations: ~, -)
    - ast.Name (variable identifiers: x, y, rax, etc.)
    - ast.Constant (integer literal values: 1, 2, 0x100, etc.)

    Structural wrapper nodes (ast.Expression) and context nodes (ast.Load) are excluded,
    ensuring that canonical expressions match training metrics (e.g. 'x + y' has 3 nodes:
    1 BinOp + 2 Names; '(x ^ y) + 2 * (x & y)' has 9 nodes).

    Args:
        expr_or_node: Either a mathematical expression string or a parsed ast.AST.

    Returns:
        The integer count of semantic AST nodes.
    """
    tree = get_ast_node(expr_or_node)
    return sum(1 for node in ast.walk(tree) if isinstance(node, COUNTED_NODE_TYPES))


def count_nodes_training(expr_or_node: Union[str, ast.AST]) -> int:
    """Counts AST nodes matching the training notebook's node counter.

    Includes operator nodes (ast.operator, ast.unaryop) such as ast.Add, ast.Mult,
    ast.BitXor, alongside BinOp, UnaryOp, Name, and Constant.

    Under this definition:
    - '(x ^ y) + 2 * (x & y)' yields exactly 13 nodes (9 semantic + 4 operators).
    - 'x + y' yields 4 nodes (3 semantic + 1 operator).

    Args:
        expr_or_node: Either a mathematical expression string or a parsed ast.AST.

    Returns:
        The integer count of AST nodes including operators.
    """
    tree = get_ast_node(expr_or_node)
    return sum(1 for node in ast.walk(tree) if isinstance(node, TRAINING_COUNTED_NODE_TYPES))


def extract_variables(expr_or_node: Union[str, ast.AST]) -> List[str]:
    """Extracts all unique variable identifiers from an expression in sorted order.

    Why this matters:
    Z3 needs to allocate a 64-bit BitVec for every variable that appears in either
    the original or candidate expression. This helper discovers those variables.

    Example:
        extract_variables("(rax ^ rbx) + 2 * (rax & rbx)") -> ["rax", "rbx"]

    Args:
        expr_or_node: Expression string or parsed ast.AST.

    Returns:
        A sorted list of unique variable names.
    """
    tree = get_ast_node(expr_or_node)
    names: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
    return sorted(list(names))


def get_ast_depth(expr_or_node: Union[str, ast.AST]) -> int:
    """Calculates the maximum depth of the expression AST iteratively.

    Uses an explicit stack traversal to prevent RecursionError on deeply chained expressions.

    Args:
        expr_or_node: Expression string or parsed ast.AST.

    Returns:
        The maximum tree depth as an integer.
    """
    tree = get_ast_node(expr_or_node)
    stack = [(tree, 1)]
    max_depth = 0
    while stack:
        curr, depth = stack.pop()
        if depth > max_depth:
            max_depth = depth
        for child in ast.iter_child_nodes(curr):
            stack.append((child, depth + 1))
    return max_depth


def format_expr(expr_or_node: Union[str, ast.AST]) -> str:
    """Converts an AST node into a clean, canonical expression string.

    Uses Python's ast.unparse to strip non-semantic formatting, comments,
    and redundant wrapping.
    """
    tree = get_ast_node(expr_or_node)
    if isinstance(tree, ast.Expression):
        return ast.unparse(tree.body)
    return ast.unparse(tree)
