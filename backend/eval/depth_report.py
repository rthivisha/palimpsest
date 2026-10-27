"""Dataset AST depth, node count, and length analyzer for PALIMPSEST.

Analyzes expressions from a JSONL file and computes:
- AST Depth (min / median / max)
- AST Node Count (min / median / max)
- Expression Length in Characters (min / median / max)

All analysis is performed iteratively using an explicit stack to prevent
RecursionError on deeply nested or flat binary operation chains.
"""
import argparse
import ast
import json
import os
import statistics
import sys
from typing import Any, Dict, List, Tuple


def compute_ast_depth_iterative(node: ast.AST) -> int:
    """Computes the maximum AST depth iteratively using an explicit traversal stack."""
    if not node:
        return 0
    max_depth = 0
    stack: List[Tuple[ast.AST, int]] = [(node, 1)]
    while stack:
        curr, depth = stack.pop()
        if depth > max_depth:
            max_depth = depth
        for child in ast.iter_child_nodes(curr):
            stack.append((child, depth + 1))
    return max_depth


def count_ast_nodes_iterative(node: ast.AST) -> int:
    """Counts semantic AST nodes (BinOp, UnaryOp, Name, Constant) iteratively."""
    if not node:
        return 0
    count = 0
    stack: List[ast.AST] = [node]
    while stack:
        curr = stack.pop()
        if isinstance(curr, (ast.BinOp, ast.UnaryOp, ast.Name, ast.Constant)):
            count += 1
        for child in ast.iter_child_nodes(curr):
            stack.append(child)
    return count


def extract_expression_from_line(line: str) -> str:
    """Extracts the expression string from a raw JSONL line.

    Supports:
    - JSON object with 'expression', 'obfuscated', 'obfuscated_expr', or 'input'
    - Bare text expression string
    """
    stripped = line.strip()
    if not stripped:
        return ""

    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            data = json.loads(stripped)
            for key in ("expression", "obfuscated", "obfuscated_expr", "input", "expr"):
                if key in data and isinstance(data[key], str):
                    return data[key].strip()
        except json.JSONDecodeError:
            pass

    return stripped


def analyze_jsonl_file(file_path: str) -> Dict[str, Any]:
    """Reads a JSONL file and computes iterative AST metrics."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    depths: List[int] = []
    node_counts: List[int] = []
    char_lengths: List[int] = []
    parse_errors = 0
    total_lines = 0

    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            expr_str = extract_expression_from_line(line)
            if not expr_str:
                continue

            total_lines += 1
            char_lengths.append(len(expr_str))

            try:
                tree = ast.parse(expr_str, mode="eval")
                depth = compute_ast_depth_iterative(tree)
                nodes = count_ast_nodes_iterative(tree)
                depths.append(depth)
                node_counts.append(nodes)
            except SyntaxError as e:
                parse_errors += 1
                sys.stderr.write(f"SyntaxError on line {line_num}: {e}\n")

    if not depths:
        return {
            "file": file_path,
            "total_lines": total_lines,
            "valid_expressions": 0,
            "parse_errors": parse_errors,
        }

    return {
        "file": file_path,
        "total_lines": total_lines,
        "valid_expressions": len(depths),
        "parse_errors": parse_errors,
        "ast_depth": {
            "min": min(depths),
            "median": statistics.median(depths),
            "max": max(depths),
        },
        "node_count": {
            "min": min(node_counts),
            "median": statistics.median(node_counts),
            "max": max(node_counts),
        },
        "char_length": {
            "min": min(char_lengths),
            "median": statistics.median(char_lengths),
            "max": max(char_lengths),
        },
    }


def format_report(metrics: Dict[str, Any]) -> str:
    """Formats the metrics report as a clean table."""
    if metrics.get("valid_expressions", 0) == 0:
        return f"File: {metrics.get('file')}\nNo valid expressions parsed (Errors: {metrics.get('parse_errors')})."

    d = metrics["ast_depth"]
    n = metrics["node_count"]
    c = metrics["char_length"]

    return (
        f"============================================================\n"
        f"PALIMPSEST AST Depth & Dataset Report\n"
        f"File: {metrics['file']}\n"
        f"Expressions Analyzed: {metrics['valid_expressions']} (Parse Errors: {metrics['parse_errors']})\n"
        f"------------------------------------------------------------\n"
        f"{'Metric':<25} | {'Min':>8} | {'Median':>10} | {'Max':>8}\n"
        f"------------------------------------------------------------\n"
        f"{'AST Depth':<25} | {d['min']:>8} | {d['median']:>10.1f} | {d['max']:>8}\n"
        f"{'Node Count (semantic)':<25} | {n['min']:>8} | {n['median']:>10.1f} | {n['max']:>8}\n"
        f"{'Expression Length (chars)':<25} | {c['min']:>8} | {c['median']:>10.1f} | {c['max']:>8}\n"
        f"============================================================"
    )


def main():
    parser = argparse.ArgumentParser(description="Analyze AST depth, nodes, and lengths in JSONL dataset")
    parser.add_argument("file", help="Path to the JSONL dataset file")
    args = parser.parse_args()

    try:
        report = analyze_jsonl_file(args.file)
        print(format_report(report))
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

