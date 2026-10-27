"""Conditional edge routers for the PALIMPSEST LangGraph synthesis loop.

Decides the control flow after:
1. `parse_ast`: Whether to halt on unsafe input or proceed to proposal.
2. `verify`: Whether to finalize on verified proof, finalize on retry exhaustion,
   or cycle back to propose with counterexample feedback.
"""
from langgraph.graph import END

from backend.app.config import settings
from backend.app.core.verifier import STATUS_VERIFIED
from backend.app.graph.state import PalimpsestState


def route_after_parse(state: PalimpsestState) -> str:
    """Routes after parse_ast node: abort if input violates security gate."""
    if state.get("final_status") == "REJECTED_UNSAFE":
        return END
    return "propose"


def route_after_verify(state: PalimpsestState) -> str:
    """Routes after verify node:

    - If Z3 returns UNSAT (verified equivalent) -> finalize_success
    - Else if iteration count reaches max_iterations limit -> finalize_fail
    - Else -> cycle back to propose (the CEGIS inductive loop)
    """
    verif = state.get("verification_result") or {}
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", settings.MAX_ITERATIONS)

    if verif.get("status") == STATUS_VERIFIED:
        return "finalize_success"
    elif iteration >= max_iter:
        return "finalize_fail"
    else:
        return "propose"
