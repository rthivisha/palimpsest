"""Graph builder and compiler for PALIMPSEST.

Assembles the LangGraph StateGraph, registers nodes and conditional routes,
and returns a compiled graph executable.
"""
from typing import Optional
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from backend.app.graph.state import PalimpsestState
from backend.app.graph.nodes import (
    parse_ast_node,
    make_propose_node,
    verify_node,
    finalize_success_node,
    finalize_fail_node,
)
from backend.app.graph.routers import route_after_parse, route_after_verify
from backend.app.llm.base import BaseLLMBackend
from backend.app.llm.fake import FakeLLMBackend


def build_graph(backend: Optional[BaseLLMBackend] = None) -> CompiledStateGraph:
    """Builds and compiles the PALIMPSEST LangGraph de-obfuscation workflow.

    Args:
        backend: The model backend to bind to the propose node.
                 Defaults to FakeLLMBackend if None.

    Returns:
        CompiledStateGraph ready for execution or streaming.
    """
    if backend is None:
        backend = FakeLLMBackend()

    # 1. Initialize StateGraph with our typed state
    workflow = StateGraph(PalimpsestState)

    # 2. Register Nodes
    workflow.add_node("parse_ast", parse_ast_node)
    workflow.add_node("propose", make_propose_node(backend))
    workflow.add_node("verify", verify_node)
    workflow.add_node("finalize_success", finalize_success_node)
    workflow.add_node("finalize_fail", finalize_fail_node)

    # 3. Entry point
    workflow.set_entry_point("parse_ast")

    # 4. Routing after parse_ast
    workflow.add_conditional_edges(
        "parse_ast",
        route_after_parse,
        {
            "propose": "propose",
            END: END,
        }
    )

    # 5. Fixed transition from propose -> verify
    workflow.add_edge("propose", "verify")

    # 6. Routing after verify (the CEGIS loop)
    workflow.add_conditional_edges(
        "verify",
        route_after_verify,
        {
            "finalize_success": "finalize_success",
            "finalize_fail": "finalize_fail",
            "propose": "propose",
        }
    )

    # 7. Terminal edges to END
    workflow.add_edge("finalize_success", END)
    workflow.add_edge("finalize_fail", END)

    # 8. Compile state machine
    return workflow.compile()
