"""Security gatekeeper for PALIMPSEST expressions.

Why this module exists:
PALIMPSEST processes untrusted mathematical strings from external users and
neural language model outputs. To prevent Remote Code Execution (RCE) and
Denial of Service (DoS) attacks, we MUST NEVER evaluate these expressions with
Python's built-in `eval()` or `exec()`.

Instead, this module inspects the Python Abstract Syntax Tree (AST) before
any expression is allowed to reach the Z3 SMT solver. Only purely algebraic,
64-bit integer bitwise operations are permitted. Any attempt to invoke functions
(e.g., `__import__('os').system('calc')`), access object attributes (e.g.,
`().__class__`), or create excessively deep recursion trees is rejected immediately.
"""
import ast
from typing import Optional, Set, Tuple, Type


# Maximum allowed characters for an input expression string.
# Prevents memory exhaustion attacks from oversized payload strings.
MAX_EXPRESSION_LENGTH: int = 5000

# Maximum allowed AST tree depth.
# Deeply nested trees (like `((((...(x)...))))`) can cause recursion limit
# crashes in Python and stack exhaustion inside Z3.
MAX_AST_DEPTH: int = 100


class SafetyViolationError(ValueError):
    """Raised when an expression contains disallowed or potentially malicious syntax."""
    pass


# Whitelist of allowed structural AST nodes.
# Only simple mathematical expressions and identifiers are permitted.
ALLOWED_NODE_TYPES: Set[Type[ast.AST]] = {
    ast.Expression,   # Top-level container when parsing in mode='eval'
    ast.BinOp,        # Binary operation, e.g. x + y, a & b
    ast.UnaryOp,      # Unary operation, e.g. ~x, -y
    ast.Name,         # Variable identifier, e.g. x, rax, r8
    ast.Constant,     # Literal value (checked separately to ensure it is strictly an integer)
    ast.Load,         # Read-only variable loading context
}

# Whitelist of allowed binary operators for Mixed Boolean-Arithmetic (MBA).
ALLOWED_BIN_OPS: Set[Type[ast.operator]] = {
    ast.Add,          # Addition (+)
    ast.Sub,          # Subtraction (-)
    ast.Mult,         # Multiplication (*)
    ast.BitAnd,       # Bitwise AND (&)
    ast.BitOr,        # Bitwise OR (|)
    ast.BitXor,       # Bitwise XOR (^)
    ast.LShift,       # Left shift (<<)
    ast.RShift,       # Right shift (>>)
}

# Whitelist of allowed unary operators.
ALLOWED_UNARY_OPS: Set[Type[ast.unaryop]] = {
    ast.Invert,       # Bitwise NOT (~)
    ast.USub,         # Unary negation (-)
}


def compute_tree_depth(node: ast.AST) -> int:
    """Recursively computes the maximum depth of an AST tree.

    A single leaf node has a depth of 1. Each parent level adds 1.
    """
    children = list(ast.iter_child_nodes(node))
    if not children:
        return 1
    return 1 + max(compute_tree_depth(child) for child in children)


def validate_ast(expr_str: str) -> ast.Expression:
    """Parses and validates an expression string against the strict AST whitelist.

    Args:
        expr_str: The raw expression string to validate.

    Returns:
        The validated ast.Expression node if safe.

    Raises:
        SafetyViolationError: If parsing fails, length is exceeded, tree is too deep,
                              or any disallowed node type/operator is detected.
    """
    if not isinstance(expr_str, str):
        raise SafetyViolationError(f"Expression must be a string, got {type(expr_str).__name__}")

    stripped = expr_str.strip()
    if not stripped:
        raise SafetyViolationError("Expression cannot be empty.")

    # 1. Enforce length boundary
    if len(stripped) > MAX_EXPRESSION_LENGTH:
        raise SafetyViolationError(
            f"Expression exceeds maximum character limit ({len(stripped)} > {MAX_EXPRESSION_LENGTH})."
        )

    # 2. Parse the expression using Python's AST in 'eval' mode.
    # Note: ast.parse does NOT execute code; it only produces a parse tree.
    try:
        tree = ast.parse(stripped, mode="eval")
    except SyntaxError as e:
        raise SafetyViolationError(f"Syntax error parsing expression: {e.msg} at line {e.lineno}, col {e.offset}")

    # 3. Enforce maximum recursion depth
    depth = compute_tree_depth(tree)
    if depth > MAX_AST_DEPTH:
        raise SafetyViolationError(
            f"AST depth exceeds limit ({depth} > {MAX_AST_DEPTH}). Possible nested recursion attack."
        )

    # 4. Walk the entire AST and enforce the whitelist
    for node in ast.walk(tree):
        node_type = type(node)

        # Reject any node type not in our structural whitelist or operator whitelists
        if (
            node_type not in ALLOWED_NODE_TYPES
            and node_type not in ALLOWED_BIN_OPS
            and node_type not in ALLOWED_UNARY_OPS
        ):
            raise SafetyViolationError(
                f"Disallowed AST syntax '{node_type.__name__}'. "
                f"PALIMPSEST only permits pure 64-bit integer arithmetic and bitwise expressions."
            )

        # Enforce operator whitelist on BinOp nodes
        if isinstance(node, ast.BinOp):
            if type(node.op) not in ALLOWED_BIN_OPS:
                raise SafetyViolationError(
                    f"Disallowed binary operator '{type(node.op).__name__}'. Allowed: +, -, *, &, |, ^, <<, >>."
                )

        # Enforce operator whitelist on UnaryOp nodes
        elif isinstance(node, ast.UnaryOp):
            if type(node.op) not in ALLOWED_UNARY_OPS:
                raise SafetyViolationError(
                    f"Disallowed unary operator '{type(node.op).__name__}'. Allowed: ~, -"
                )

        # Enforce integer-only constants (no floats, strings, booleans, or complex)
        elif isinstance(node, ast.Constant):
            # In Python, bool is a subclass of int (isinstance(True, int) is True).
            # We strictly require type(value) is int to forbid booleans like True/False.
            if type(node.value) is not int or isinstance(node.value, bool):
                raise SafetyViolationError(
                    f"Disallowed constant '{node.value}' of type {type(node.value).__name__}. "
                    f"Only integers are permitted."
                )

    return tree


def is_safe_ast(expr_str: str) -> Tuple[bool, Optional[str]]:
    """Safe wrapper around validate_ast returning a boolean and error description.

    Useful when you want to check an expression without catching exceptions.

    Returns:
        (True, None) if the expression is safe.
        (False, error_message) if the expression is rejected.
    """
    try:
        validate_ast(expr_str)
        return True, None
    except SafetyViolationError as err:
        return False, str(err)
    except Exception as err:
        return False, f"Unexpected validation error: {err}"
