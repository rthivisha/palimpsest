"""Route handlers for system health, aggregate statistics, and MBA examples."""
import z3
from typing import Any, Dict, List
from fastapi import APIRouter

from backend.app.config import settings
from backend.app.telemetry.db import telemetry_db

router = APIRouter()


CURATED_EXAMPLES: List[Dict[str, Any]] = [
    {
        "id": "linear_mba_xor_and",
        "title": "Linear MBA Addition",
        "category": "Linear MBA",
        "expression": "(x ^ y) + 2 * (x & y)",
        "expected_simplified": "x + y",
        "description": "Standard binary adder identity mapping XOR and AND components to addition.",
    },
    {
        "id": "opaque_predicate_sub",
        "title": "Opaque Predicate Annihilation",
        "category": "Opaque Predicates",
        "expression": "x + y + ((x | y) - (x & y) - (x ^ y)) * 42",
        "expected_simplified": "x + y",
        "description": "The term ((x | y) - (x & y) - (x ^ y)) mathematically evaluates to 0 for all 64-bit inputs.",
    },
    {
        "id": "multivariable_transform",
        "title": "Three-Variable MBA",
        "category": "Multi-variable",
        "expression": "(x ^ y) + (y ^ z) + 2 * (x & y) + 2 * (y & z) - 2 * y",
        "expected_simplified": "x + z",
        "description": "Cross-variable cancellations where intermediate variable y cancels out entirely.",
    },
    {
        "id": "bitwise_demorgan",
        "title": "De Morgan Inversion",
        "category": "Bitwise Identities",
        "expression": "~(~x | ~y)",
        "expected_simplified": "x & y",
        "description": "De Morgan's law over 64-bit bit-vectors transforming inverted disjunction to conjunction.",
    },
    {
        "id": "zero_annihilation",
        "title": "Self-Annihilating Null Term",
        "category": "Opaque Predicates",
        "expression": "rax + (rax & ~rax) * 1337",
        "expected_simplified": "rax",
        "description": "The term (rax & ~rax) is identically zero for all 64-bit bit patterns.",
    },
]


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Returns runtime health status for solver, backends, and telemetry."""
    z3_version = z3.get_version_string()
    backend_name = settings.PALIMPSEST_BACKEND

    # Model reachable check
    model_reachable = True
    if backend_name == "ollama":
        # In Phase 5: test ping to Ollama endpoint
        model_reachable = True
    elif backend_name == "llamacpp":
        # In Phase 5: check if file exists
        model_reachable = True

    return {
        "status": "ok",
        "backend": backend_name,
        "model_reachable": model_reachable,
        "z3_version": z3_version,
        "z3_logic": "QF_BV (64-bit unsigned)",
        "langsmith_tracing": settings.LANGSMITH_TRACING,
    }


@router.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """Returns aggregate synthesis statistics over past de-obfuscation runs."""
    return telemetry_db.get_stats()


@router.get("/examples")
async def get_examples() -> List[Dict[str, Any]]:
    """Returns curated MBA expression examples for demo presets."""
    return CURATED_EXAMPLES
