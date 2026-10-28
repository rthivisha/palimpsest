"""Diagnostic script comparing single-turn candidate verification across system prompts.

LABEL: DIAGNOSTIC, NOT A BENCHMARK.
This script executes the demo MBA expression (x ^ y) + 2 * (x & y) across 20 trials
with max_iterations=1 and a fixed seed, comparing:
1. Empty SYSTEM_PROMPT ("") - Palimpsest fine-tuning default.
2. Qwen default SYSTEM_PROMPT ("You are a helpful assistant.").

Reports attempt-1 verified counts. No synthetic numbers are generated.
"""
import argparse
import os
import random
import sys
from datetime import datetime, timezone

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.config import settings
from backend.app.core.verifier import STATUS_VERIFIED, verify_equivalence
from backend.app.llm.base import BaseLLMBackend, LLMBackendError
from backend.app.llm.factory import get_backend
from backend.app.llm.fake import FakeLLMBackend
from backend.app.llm.prompts import build_messages, extract_candidate

DEMO_EXPRESSION = "(x ^ y) + 2 * (x & y)"
CANONICAL_TARGET = "x + y"
QWEN_DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."


def run_trials_for_condition(
    backend: BaseLLMBackend,
    expression: str,
    system_prompt: str,
    trials: int,
    seed: int,
) -> int:
    """Runs N trials under a given system prompt condition, counting attempt-1 verifications."""
    verified_count = 0
    for i in range(trials):
        # Derive deterministic seed per trial
        trial_seed = seed + i
        messages = build_messages(expression, history=[], system_prompt=system_prompt)
        try:
            raw_output = backend.generate(
                messages,
                temperature=0.2,
                max_tokens=settings.NUM_PREDICT,
                seed=trial_seed,
            )
        except LLMBackendError as exc:
            raise exc

        candidate = extract_candidate(raw_output)
        if not candidate:
            continue

        verif = verify_equivalence(expression, candidate)
        if verif["status"] == STATUS_VERIFIED:
            verified_count += 1

    return verified_count


def main():
    parser = argparse.ArgumentParser(
        description="PALIMPSEST System Prompt Diagnostic Script (diagnostic, not a benchmark)"
    )
    parser.add_argument(
        "--backend",
        "-b",
        default=settings.PALIMPSEST_BACKEND,
        help=f"Backend to evaluate (default: {settings.PALIMPSEST_BACKEND})",
    )
    parser.add_argument(
        "--trials",
        "-n",
        type=int,
        default=20,
        help="Number of trials per condition (default: 20)",
    )
    parser.add_argument(
        "--seed",
        "-s",
        type=int,
        default=42,
        help="Fixed seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--allow-fake",
        action="store_true",
        help="Allow running with FakeLLMBackend for testing the diagnostic script itself",
    )
    args = parser.parse_args()

    random.seed(args.seed)
    backend_name = args.backend.lower().strip()

    if backend_name == "fake" and not args.allow_fake:
        print(
            "ERROR: Diagnostic script refused to run against 'fake' backend without --allow-fake. "
            "To test this script offline, pass --allow-fake explicitly.",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        backend = get_backend(backend_name)
    except Exception as exc:
        print(f"ERROR: Failed to initialize backend '{backend_name}': {exc}", file=sys.stderr)
        sys.exit(1)

    print("=" * 80)
    print("PALIMPSEST SYSTEM PROMPT DIAGNOSTIC REPORT")
    print("[DIAGNOSTIC TOOL ONLY — NOT A SCIENTIFIC BENCHMARK]")
    print("=" * 80)
    print(f"Timestamp:       {datetime.now(timezone.utc).isoformat()}")
    print(f"Expression:      {DEMO_EXPRESSION}")
    print(f"Canonical:       {CANONICAL_TARGET}")
    print(f"Backend:         {backend_name}")
    print(f"Trials:          {args.trials}")
    print(f"Max Iterations:  1 (single-turn attempt-1 verification only)")
    print(f"Fixed Seed:      {args.seed}")
    if isinstance(backend, FakeLLMBackend):
        print("WARNING:         Running with FakeLLMBackend (scripted responses, not a real SLM)")
    print("=" * 80)

    try:
        # Condition 1: Empty System Prompt (Palimpsest Default)
        print("Running Condition 1: Empty System Prompt (\"\")...")
        c1_verified = run_trials_for_condition(
            backend=backend,
            expression=DEMO_EXPRESSION,
            system_prompt="",
            trials=args.trials,
            seed=args.seed,
        )

        # Condition 2: Qwen Default System Prompt
        print("Running Condition 2: Qwen Default System Prompt (\"You are a helpful assistant.\")...")
        c2_verified = run_trials_for_condition(
            backend=backend,
            expression=DEMO_EXPRESSION,
            system_prompt=QWEN_DEFAULT_SYSTEM_PROMPT,
            trials=args.trials,
            seed=args.seed,
        )
    except LLMBackendError as exc:
        print(f"\nDIAGNOSTIC ABORTED: {exc}", file=sys.stderr)
        sys.exit(1)

    c1_pct = round((c1_verified / max(1, args.trials)) * 100, 1)
    c2_pct = round((c2_verified / max(1, args.trials)) * 100, 1)

    print("\n" + "=" * 80)
    print("DIAGNOSTIC RESULTS SUMMARY (Single-Turn Attempt-1 Verification)")
    print("=" * 80)
    print(f"Condition 1 [Empty System Prompt]:          {c1_verified:>2}/{args.trials} verified ({c1_pct:>5.1f}%)")
    print(f"Condition 2 [Qwen Default System Prompt]:   {c2_verified:>2}/{args.trials} verified ({c2_pct:>5.1f}%)")
    print("=" * 80)
    print("Note: This diagnostic script verifies single-turn behavior on a single MBA identity.")
    print("It is explicitly labelled 'diagnostic, not a benchmark' and must not be cited as such.")
    print("=" * 80)


if __name__ == "__main__":
    main()
