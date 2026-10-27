"""AST utilities for PALIMPSEST expressions.

Provides helper routines to:
- Count AST nodes (used to compute expression compression percentage: 1 - final_nodes / obf_nodes)
- Extract all variable identifiers present in an expression (e.g. ['x', 'y'] or ['rax', 'rbx'])
- Calculate tree depth to prevent deep recursion
- Normalize and unparse AST trees into canonical mathematical strings
"""
import ast
from typing import List, Set, Union


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
    """Counts the total number of AST nodes in an expression.

    Why this matters:
    In PALIMPSEST, our metric for de-obfuscation effectiveness is the AST
    compression ratio:
        compression_pct = (1.0 - (target_nodes / obf_nodes)) * 100
    By counting the nodes in the AST, we get an objective, format-independent
    measure of expression size (unlike character count, which depends on whitespace).

    Args:
        expr_or_node: Either a mathematical expression string or a parsed ast.AST.

    Returns:
        The integer count of AST nodes.
    """
    tree = get_ast_node(expr_or_node)
    # ast.walk recursively yields all nodes in the tree in no specified order.
    # We count every visited AST node.
    return sum(1 for _ in ast.walk(tree))


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
    """Calculates the maximum depth of the expression AST.

    Args:
        expr_or_node: Expression string or parsed ast.AST.

    Returns:
        The maximum tree depth as an integer.
    """
    tree = get_ast_node(expr_or_node)

    def _depth(node: ast.AST) -> int:
        children = list(ast.iter_child_nodes(node))
        if not children:
            return 1
        return 1 + max(_depth(child) for child in children)

    return _depth(tree)


def format_expr(expr_or_node: Union[str, ast.AST]) -> str:
    """Converts an AST node into a clean, canonical expression string.

    Uses Python's ast.unparse to strip non-semantic formatting, comments,
    and redundant wrapping.
    """
    tree = get_ast_node(expr_or_node)
    # If the root is ast.Expression, unparse its body directly
    if isinstance(tree, ast.Expression):
        return ast.unparse(tree.body)
    return ast.unparse(tree)
