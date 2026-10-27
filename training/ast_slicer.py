"""AST Slicer compatibility module for training scripts.

Re-exports AST analysis utilities from the core backend.
"""
from backend.app.core.ast_utils import count_nodes, extract_variables, get_ast_depth, format_expr

__all__ = ["count_nodes", "extract_variables", "get_ast_depth", "format_expr"]
