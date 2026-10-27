"""PALIMPSEST CLI Interactive Demo.

Demonstrates the neurosymbolic CEGIS loop running against the deterministic fake model backend:
1. Input: (x ^ y) + 2 * (x & y)
2. Attempt 1: Model proposes 'x ^ y' -> Z3 returns SAT with small witness {'x': 15, 'y': 15} (expected 30, actual 0).
3. Attempt 2: Model receives witness feedback -> proposes 'x + y' -> Z3 returns UNSAT.
4. Equivalence Proven by Z3 (QF_BV, 64-bit) -> Compression reported.
"""
import argparse
import os
import sys

# Ensure repository root is on sys.path for direct execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.app.config import settings
from backend.app.graph.build import build_graph
from backend.app.llm.factory import get_backend


def run_cli_demo(
    expression: str = "(x ^ y) + 2 * (x & y)",
    max_iterations: int = 5,
    backend_name: str = "fake",
) -> None:
    print("=" * 70)
    print("               PALIMPSEST (VEX-MORPH) CLI DEMO")
    print("      Neurosymbolic Mixed Boolean-Arithmetic De-Obfuscator")
    print("=" * 70)
    print(f"\n[Target Expression]: {expression}")
    print(f"[Max Iterations]:    {max_iterations}")
    print(f"[Model Backend]:     {backend_name.upper()}")
    print("-" * 70)

    # Instantiate configured model backend via factory
    backend = get_backend(backend_name)
    graph = build_graph(backend)

    initial_state = {
        "obfuscated_expr": expression,
        "max_iterations": max_iterations,
        "iteration": 0,
        "history": [],
        "temperature": 0.2,
    }

    print("\n[+] Starting LangGraph CEGIS Loop...\n")

    # Stream graph updates node by node
    for event in graph.stream(initial_state):
        for node_name, state_update in event.items():
            print(f">>> Node Executed: [{node_name}]")

            if node_name == "parse_ast":
                print(f"    AST Parsed Successfully.")
                print(f"    Initial Semantic AST Nodes (BinOp/UnaryOp/Name/Constant): {state_update.get('obf_nodes')}")

            elif node_name == "propose":
                iter_num = state_update.get("iteration")
                cand = state_update.get("current_candidate")
                think = state_update.get("current_think")
                print(f"    [Iteration {iter_num}] Model proposed candidate: '{cand}'")
                if think:
                    first_think_line = think.splitlines()[0] if think.splitlines() else ""
                    print(f"    Reasoning summary: {first_think_line}...")

            elif node_name == "verify":
                verif = state_update.get("verification_result", {})
                status = verif.get("status")
                latency = verif.get("latency_ms")
                print(f"    Z3 Miter Check Status: {status} ({latency:.2f} ms)")

                if status == "SAT":
                    witness = verif.get("witness")
                    expected = verif.get("expected")
                    actual = verif.get("actual")
                    diff_bits = verif.get("diff_bits")
                    print(f"    Counterexample Witness Discovered (Bounded Bv < 16): {witness}")
                    print(f"    Evaluation: Expected {expected}, Actual {actual}")
                    print(f"    Bit Discrepancy (64-bit diff): {diff_bits}")
                    print(f"    --> Recycling witness back into model context for retry...")

                elif status == "QF_BV_UNSAT_64BIT_VERIFIED":
                    print(f"    [PROVEN] equivalence proven by Z3 (QF_BV, 64-bit)")

            elif node_name == "finalize_success":
                status = state_update.get("final_status")
                final_expr = state_update.get("final_expr")
                final_nodes = state_update.get("final_nodes")
                compression = state_update.get("compression_pct")
                print("\n" + "=" * 70)
                print(f" [+] RESULT: {status}")
                print(f" [+] Proven Canonical Form: {final_expr}")
                print(f" [+] AST Nodes: Final {final_nodes} (Reduced by {compression}%)")
                print(f" [+] Equivalence proven by Z3 (QF_BV, 64-bit)")
                print("=" * 70 + "\n")

            elif node_name == "finalize_fail":
                status = state_update.get("final_status")
                err = state_update.get("error_message")
                print("\n" + "=" * 70)
                print(f" [-] RESULT: {status}")
                print(f" [-] {err}")
                print("=" * 70 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PALIMPSEST CLI De-Obfuscator Demo")
    parser.add_argument("expression", nargs="?", default="(x ^ y) + 2 * (x & y)", help="MBA expression to de-obfuscate")
    parser.add_argument("--iterations", "-i", type=int, default=5, help="Maximum CEGIS iterations (1 to 10)")
    parser.add_argument("--backend", "-b", type=str, default=settings.PALIMPSEST_BACKEND, choices=["fake", "ollama", "llamacpp"], help="Model backend")
    args = parser.parse_args()

    run_cli_demo(args.expression, max_iterations=args.iterations, backend_name=args.backend)
