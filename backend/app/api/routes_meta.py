"""Route handlers for system health, aggregate statistics, and MBA examples."""
import z3
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException

from backend.app.config import settings
from backend.app.telemetry.db import telemetry_db

router = APIRouter()

ALLOWED_STATS_BACKENDS = {"fake", "ollama", "llamacpp"}


CURATED_EXAMPLES: List[Dict[str, Any]] = [
    {
        "id": "linear_mba_xor_and",
        "title": "Linear MBA Addition",
        "category": "Linear MBA",
        "expression": "(x ^ y) + 2 * (x & y)",
        "expected_simplified": "x + y",
        "description": "Standard binary adder identity mapping XOR and AND components to addition.",
        "variables": ["x", "y"],
        "transformation_steps": [
            "Step 1: Recognize fundamental binary adder relation: x + y = (x ^ y) + (x & y) + (x & y).",
            "Step 2: Observe that (x ^ y) computes the bitwise half-sum (bits where exactly one operand is 1).",
            "Step 3: Group the dual carry terms: (x & y) + (x & y) = 2 * (x & y).",
            "Step 4: Combine components: half-sum + carry = canonical addition x + y.",
        ],
    },
    {
        "id": "opaque_predicate_sub",
        "title": "Opaque Predicate Annihilation",
        "category": "Opaque Predicates",
        "expression": "x + y + ((x | y) - (x & y) - (x ^ y)) * 42",
        "expected_simplified": "x + y",
        "description": "The term ((x | y) - (x & y) - (x ^ y)) mathematically evaluates to 0 for all 64-bit inputs.",
        "variables": ["x", "y"],
        "transformation_steps": [
            "Step 1: Isolate the nested bracket sub-expression: ((x | y) - (x & y) - (x ^ y)).",
            "Step 2: Apply bitwise set-union identity: (x | y) - (x & y) = (x ^ y).",
            "Step 3: Substitute back: (x ^ y) - (x ^ y) = 0 across all 64-bit bit-vectors.",
            "Step 4: Multiply by scaling coefficient: 0 * 42 = 0, completely annihilating the dead term.",
            "Step 5: The active live expression reduces to canonical x + y.",
        ],
    },
    {
        "id": "multivariable_transform",
        "title": "Three-Variable MBA",
        "category": "Multi-variable",
        "expression": "(x ^ y) + (y ^ z) + 2 * (x & y) + 2 * (y & z) - 2 * y",
        "expected_simplified": "x + z",
        "description": "Cross-variable cancellations where intermediate variable y cancels out entirely.",
        "variables": ["x", "y", "z"],
        "transformation_steps": [
            "Step 1: Group the x and y terms: (x ^ y) + 2 * (x & y) = x + y.",
            "Step 2: Group the y and z terms: (y ^ z) + 2 * (y & z) = y + z.",
            "Step 3: Sum the expanded pairs: (x + y) + (y + z) = x + 2 * y + z.",
            "Step 4: Cancel the trailing subtraction: x + 2 * y + z - 2 * y = x + z.",
        ],
    },
    {
        "id": "bitwise_demorgan",
        "title": "De Morgan Inversion",
        "category": "Bitwise Identities",
        "expression": "~(~x | ~y)",
        "expected_simplified": "x & y",
        "description": "De Morgan's law over 64-bit bit-vectors transforming inverted disjunction to conjunction.",
        "variables": ["x", "y"],
        "transformation_steps": [
            "Step 1: Start with inverted disjunctive expression: ~(~x | ~y).",
            "Step 2: Apply De Morgan's Duality: ~(A | B) = ~A & ~B.",
            "Step 3: Let A = ~x and B = ~y: ~(~x) & ~(~y).",
            "Step 4: Eliminate double bitwise inversions: x & y.",
        ],
    },
    {
        "id": "zero_annihilation",
        "title": "Self-Annihilating Null Term",
        "category": "Opaque Predicates",
        "expression": "rax + (rax & ~rax) * 1337",
        "expected_simplified": "rax",
        "description": "The term (rax & ~rax) is identically zero for all 64-bit bit patterns.",
        "variables": ["rax"],
        "transformation_steps": [
            "Step 1: Examine the opaque sub-expression: (rax & ~rax).",
            "Step 2: By bitwise definition, a bit cannot simultaneously be 1 and 0: k & ~k = 0 for every bit.",
            "Step 3: Therefore (rax & ~rax) = 0 across all 64-bit unsigned register states.",
            "Step 4: Scale by constant: 0 * 1337 = 0.",
            "Step 5: Output simplifies to canonical rax.",
        ],
    },
]


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Returns runtime health status for solver, backends, and telemetry."""
    import os
    import httpx

    z3_version = z3.get_version_string()
    backend_name = settings.PALIMPSEST_BACKEND

    # Model name resolution
    if backend_name == "ollama":
        model_name = settings.OLLAMA_MODEL
    elif backend_name in ("llamacpp", "llama_cpp", "llama-cpp"):
        model_name = os.path.basename(settings.LLAMACPP_MODEL_PATH)
    else:
        model_name = "fake-scripted"

    # Real model reachable check
    model_reachable = True
    model_unreachable_reason = None
    if backend_name == "ollama":
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                res = await client.get(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    target = settings.OLLAMA_MODEL
                    found = any(target == m or m.startswith(f"{target}:") for m in models)
                    if found:
                        model_reachable = True
                    else:
                        model_reachable = False
                        model_unreachable_reason = f"Model '{target}' not found; run ollama create {target} -f Modelfile"
                else:
                    model_reachable = False
                    model_unreachable_reason = f"Ollama is not running at {settings.OLLAMA_BASE_URL}"
        except Exception:
            model_reachable = False
            model_unreachable_reason = f"Ollama is not running at {settings.OLLAMA_BASE_URL}"
    elif backend_name in ("llamacpp", "llama_cpp", "llama-cpp"):
        model_reachable = os.path.exists(settings.LLAMACPP_MODEL_PATH)
        if not model_reachable:
            model_unreachable_reason = f"Model file not found at {settings.LLAMACPP_MODEL_PATH}"

    fake_hint = (
        "Scripted demo model: only the Classic 2-Turn Demo is solvable"
        if backend_name == "fake"
        else None
    )

    return {
        "status": "ok",
        "backend": backend_name,
        "model_name": model_name,
        "model_reachable": model_reachable,
        "model_unreachable_reason": model_unreachable_reason,
        "fake_hint": fake_hint,
        "z3_version": z3_version,
        "z3_logic": "QF_BV (64-bit unsigned)",
        "langsmith_tracing": settings.LANGSMITH_TRACING,
    }


@router.get("/stats")
async def get_stats(
    exclude_fake: bool = False,
    backend: Optional[str] = None,
) -> Dict[str, Any]:
    """Returns aggregate synthesis statistics over past de-obfuscation runs."""
    if backend is not None:
        clean = backend.lower().strip()
        if clean not in ALLOWED_STATS_BACKENDS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid backend '{backend}'. Must be one of: {sorted(ALLOWED_STATS_BACKENDS)}",
            )
        backend = clean
    return telemetry_db.get_stats(exclude_fake=exclude_fake, backend=backend)


@router.get("/examples")
async def get_examples() -> List[Dict[str, Any]]:
    """Returns curated MBA expression examples for demo presets."""
    return CURATED_EXAMPLES
