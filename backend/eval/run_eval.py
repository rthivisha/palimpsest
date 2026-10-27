"""Command-line interface for the PALIMPSEST formal evaluation harness."""
import argparse
import hashlib
import os
import sys

from backend.app.config import settings
from backend.eval.harness import EvalConfig, EvalHarness


def get_gguf_sha256(path: str) -> str:
    """Computes SHA-256 of the GGUF model weights if file exists."""
    if not path or not os.path.exists(path):
        return "[GGUF file not found or running via Ollama daemon]"
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(
        description="PALIMPSEST Neurosymbolic MBA Evaluation Harness (EVAL.md standard)"
    )
    parser.add_argument("--dataset", "-d", default="backend/data/samples.jsonl", help="Path to JSONL dataset")
    parser.add_argument("--db", default="eval_results.db", help="Dedicated SQLite database for eval results")
    parser.add_argument("--split", "-s", default="validation", help="Partition split (default: validation)")
    parser.add_argument("--external", action="store_true", help="Evaluate external non-generator partition")
    parser.add_argument("--max-k", "-k", type=int, default=5, help="Maximum CEGIS attempts (K_max=5)")
    parser.add_argument("--limit", "-n", type=int, default=None, help="Limit number of rows evaluated")
    parser.add_argument("--resume", "-r", action="store_true", help="Resume interrupted evaluation run")
    parser.add_argument("--allow-fake", action="store_true", help="Explicit override to permit FakeLLMBackend")
    parser.add_argument("--z3-only", action="store_true", help="Run Z3-simplifier baseline without SLM generation")
    parser.add_argument("--seed", type=int, default=42, help="Fixed random seed (default: 42)")

    args = parser.parse_args()

    cfg = EvalConfig(
        dataset_path=args.dataset,
        db_path=args.db,
        backend_name=settings.PALIMPSEST_BACKEND,
        split=args.split,
        external=args.external,
        max_k=args.max_k,
        limit=args.limit,
        resume=args.resume,
        allow_fake=args.allow_fake,
        z3_only=args.z3_only,
        seed=args.seed,
    )

    # Print reproducibility header exactly as required by EVAL.md
    print("=" * 80)
    print("PALIMPSEST FORMAL BENCHMARK REPORT")
    print("=" * 80)
    print(f"Seed:               {cfg.seed}")
    print(f"Backend:            {settings.PALIMPSEST_BACKEND}")
    print(f"GGUF SHA-256:       {get_gguf_sha256(settings.LLAMACPP_MODEL_PATH)}")
    print(f"Base Temperature:   0.20 (repeated-candidate bump: +{settings.TEMP_RETRY_INCREMENT})")
    print(f"History Mode:       {settings.HISTORY_MODE}")
    print(f"System Prompt:      {repr(settings.SYSTEM_PROMPT) if settings.SYSTEM_PROMPT else '[none]'}")
    print(f"Shift Semantics:    z3 (default 64-bit BitVec)")
    print(f"Max AST Depth:      {settings.MAX_AST_DEPTH}")
    print(f"Tool Role:          {settings.TOOL_ROLE}")
    print(f"Num Predict:        {settings.NUM_PREDICT}")
    print(f"Database State:     {cfg.db_path}")
    split_desc = "--external (non-generator rows)" if cfg.external else f"--split {cfg.split}"
    print(f"Evaluated Split:    {split_desc}")
    print("=" * 80)

    try:
        harness = EvalHarness(cfg)
    except RuntimeError as exc:
        print(f"\nFATAL REFUSAL: {exc}", file=sys.stderr)
        sys.exit(2)

    summary = harness.run()

    print("\nBenchmark Summary Results:")
    print(f"Total Evaluated (Denominator N): {summary['total_evaluated']}")
    print(f"Success within 1 attempt (CEGIS):  {summary.get('success_within_1_attempt_pct', 0.0)}%  (95% CI: {summary.get('success_within_1_ci95')})")
    print(f"Success within 3 attempts (CEGIS): {summary.get('success_within_3_attempts_pct', 0.0)}%  (95% CI: {summary.get('success_within_3_ci95')})")
    print(f"Success within 5 attempts (CEGIS): {summary.get('success_within_5_attempts_pct', 0.0)}%  (95% CI: {summary.get('success_within_5_ci95')})")
    print("\nOutcome Breakdown:")
    for status, count in summary.get("outcomes", {}).items():
        pct = round((count / max(1, summary['total_evaluated'])) * 100, 2)
        print(f"  {status:<18}: {count:>4}  ({pct:>6.2f}%)")
    print("=" * 80)


if __name__ == "__main__":
    main()
