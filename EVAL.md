# PALIMPSEST Evaluation Specification (EVAL.md)

This document specifies the methodology, operational semantics, statistical rigor, and metric definitions for evaluating the neurosymbolic MBA expression de-obfuscation engine.

---

## 1. Evaluation Architecture & Pipeline Overview

The benchmark harness evaluates PALIMPSEST across test partitions from `backend/data/samples.jsonl`. Each evaluation row represents a distinct 64-bit Mixed Boolean-Arithmetic (MBA) expression or opaque predicate with its known ground truth canonical form and tier classification.

### Execution Modes
1. **Live Model Mode (Default)**: Executes against local model backends (`PALIMPSEST_BACKEND=ollama` or `PALIMPSEST_BACKEND=llamacpp`).
2. **Refusal of Mock Backends**: The evaluation harness **strictly refuses** to evaluate against `fake` or scripted mock backends by default. If `PALIMPSEST_BACKEND=fake` is detected without an explicit `--allow-fake` flag, the harness terminates immediately with an exit code of `2` and a fatal error message. This prevents accidental publication of synthetic test numbers.
3. **Z3-Only Baseline Mode**: Bypasses LLM hypothesis generation and attempts direct equivalence proving against candidate identities via Z3 BitVec tactics alone, measuring baseline SMT capabilities without neurosymbolic search.

---

## 2. Categorization & Outcome Accounting

Each expression evaluated by the harness is categorized into one of five mutually exclusive outcomes:

1. **PROVEN_EQUIVALENT**: Formally verified by Z3 (`QF_BV_UNSAT_64BIT_VERIFIED`) within $K$ attempts and within the per-query timeout budget.
2. **FAILED_EXHAUSTED**: Model failed to propose an equivalent candidate within $K$ CEGIS loop attempts, receiving formal counterexamples on each iteration.
3. **TIMEOUT_UNKNOWN**: Z3 solver or model inference exceeded allocated time budget (bounded timeout plus overhead), returning `UNKNOWN`.
4. **INVALID_SYNTAX**: Model produced invalid syntax or non-MBA operators that failed the AST parser or safety gate.
5. **DEPTH_REJECTED (Distinct Category)**: The input expression or candidate exceeded `MAX_AST_DEPTH` (default 100) or character limits. Depth gate rejections are accounted for in **their own distinct category** and are **never lumped into solver timeouts or model synthesis failures**.

---

## 3. Statistical Metrics & Confidence Bounds

### A. Success Rate @ $K$ ($K \in \{1, 3, 5\}$)
Success Rate @ $K$ measures the fraction of expressions where formal equivalence is proven on or before attempt $K$:
$$\text{Pass}@K = \frac{\sum_{i=1}^{N} \mathbb{I}(\text{attempts}_i \le K \land \text{status}_i = \text{PROVEN})}{N}$$

### B. Wilson Score Confidence Intervals
Because benchmark sample sizes vary and success rates approach asymptotic boundaries (0% or 100%), normal approximation intervals ($\hat{p} \pm 1.96 \sqrt{\hat{p}(1-\hat{p})/n}$) are statistically invalid. PALIMPSEST strictly reports **95% Wilson Score Intervals** for all pass rates:

$$w = \frac{\hat{p} + \frac{z^2}{2n} \pm z \sqrt{\frac{\hat{p}(1-\hat{p})}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}}$$

where $z = 1.95996$ for a 95% confidence level, $n$ is the total evaluated sample count, and $\hat{p}$ is the sample success proportion.

### C. Secondary Metrics
- **Mean Attempts to Success**: Average iterations required among successful proofs.
- **Mean AST Reduction**: Average compression ratio: $1 - (\text{nodes}_{\text{final}} / \text{nodes}_{\text{orig}})$.
- **Z3 Solver Latency (Median & 95th Percentile)**: In milliseconds, reported separately from neural inference latency.
- **Neural Inference Latency (Median & 95th Percentile)**: Token generation time per CEGIS turn.

---

## 4. Benchmark Dataset & Partitioning

### Held-Out Evaluation Protocol
1. **In-Distribution Set**: MBA identities matching the transformation rules present in the fine-tuning training corpus.
2. **Held-Out Set**: Novel MBA compositions, higher-order polynomial expansions, and unseen opaque predicates. Held-out rows verify that the model has learned algebraic generalization rather than rote memorization of training identities.
3. **Dataset Row Format (`backend/data/samples.jsonl`)**:
   ```json
   {
     "id": "mba_lin_001",
     "tier": "linear",
     "expression": "(x ^ y) + 2 * (x & y)",
     "canonical": "x + y",
     "ground_truth_nodes": 3,
     "variables": ["x", "y"],
     "is_held_out": true
   }
   ```

---

## 5. Command-Line Interface & Operational Controls

The evaluation harness (`backend/eval/run_eval.py`) provides the following operational controls:

| Argument | Flag | Default | Description |
| :--- | :--- | :--- | :--- |
| `--dataset` | `-d` | `backend/data/samples.jsonl` | Path to JSONL dataset. |
| `--output` | `-o` | `eval_results.json` | Destination path for benchmark results JSON. |
| `--max-k` | `-k` | `5` | Maximum CEGIS attempts evaluated ($K=1, 3, 5$). |
| `--limit` | `-n` | `None` (All) | Limit evaluation to first $N$ rows for rapid profiling. |
| `--resume` | `-r` | `False` | Resumes an interrupted run, skipping already completed row IDs in output file. |
| `--allow-fake` | | `False` | Explicit override required to run on `FakeLLMBackend`. Default is strict refusal. |
| `--held-out-only` | | `False` | Filters evaluation strictly to rows with `"is_held_out": true`. |
| `--z3-only` | | `False` | Runs symbolic SMT baseline mode without LLM generation. |

### Checkpointing via `--resume`
To safeguard against hardware interruptions or daemon disconnects during long benchmark sweeps over thousands of rows:
1. Every completed expression row is written immediately to a `.checkpoint.jsonl` file.
2. Supplying `--resume` checks the output and checkpoint files, loads completed IDs, and resumes at the next pending row without duplicating inference or solver computations.

---

## 6. Output Reporting Standard

The evaluation harness produces both a structured machine-readable JSON artifact and a formatted terminal summary:

```text
================================================================================
PALIMPSEST NEUROSYMBOLIC BENCHMARK REPORT
Model: palimpsest (Ollama) | Samples Evaluated: 200 | Timeout Budget: 3000ms
================================================================================
Pass@1:  64.50%  (95% CI: [57.65%, 70.83%])
Pass@3:  81.00%  (95% CI: [75.02%, 85.83%])
Pass@5:  86.50%  (95% CI: [81.09%, 90.62%])

Mean Attempts (Successful):  1.42
Mean AST Reduction:          58.4%
Z3 Latency (Median / P95):   34.2 ms / 185.0 ms
LLM Latency (Median / P95):  3.12 s / 5.48 s
--------------------------------------------------------------------------------
Outcome Breakdown:
  PROVEN_EQUIVALENT: 173  (86.50%)
  FAILED_EXHAUSTED:   18  ( 9.00%)
  TIMEOUT_UNKNOWN:     5  ( 2.50%)
  INVALID_SYNTAX:      1  ( 0.50%)
  DEPTH_REJECTED:      3  ( 1.50%)  [Reported independently of solver/model errors]
================================================================================
```
