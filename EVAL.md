# PALIMPSEST Evaluation Specification (EVAL.md)

This document specifies the rigorous evaluation methodology, outcome accounting, dataset partitioning, baseline definitions, and reporting requirements for evaluating the PALIMPSEST neurosymbolic 64-bit Mixed Boolean-Arithmetic (MBA) de-obfuscation engine.

---

## 1. Evaluation Architecture & Pipeline Integrity

The evaluation harness (`backend/eval/run_eval.py`) executes directly against the production runtime components to guarantee zero divergence between benchmark measurements and real-world behavior:

1. **Real Graph & Message Builder**: The harness invokes `prompts.build_messages` and executes the compiled LangGraph state machine (`backend.app.graph.build.build_graph`) without mocks or mock edge routers.
2. **Strict Refusal of Mock Backends**: The harness **strictly refuses** to evaluate against `FakeLLMBackend` by default. If `PALIMPSEST_BACKEND=fake` is active, the harness aborts immediately with exit code `2` and an explicit refusal message unless the operator explicitly passes `--allow-fake`. This prevents accidental publication of synthetic numbers.
3. **Dedicated SQLite State Persistence**: Evaluation runs are tracked in their own dedicated SQLite database file (e.g. `eval_results.db`), completely isolated from the production `telemetry.db`. The schema captures per-row attempts, Z3 solver latencies, inference latencies, candidate expressions, and counterexamples.
4. **Resumption via `--resume`**: Supplying `--resume <path_to_db>` reads completed expression IDs from the SQLite database and resumes execution at the next uncompleted row, ensuring uninterrupted recovery from hardware restarts or timeouts without duplicate computation.
5. **Bounded Execution**: `--limit N` enables profiling on small subsets without mutating the persistent dataset.

---

## 2. Dataset Partitions & Row Types

The evaluation corpus (`backend/data/samples.jsonl`) contains distinct partitions. The legacy `is_held_out` flag is dropped in favor of explicit row types and split filtering:

### Partitions
1. **Validation Split (`--split validation`)**:
   - Generator-produced expressions that were **strictly excluded from the fine-tuning training corpus** (derived from the teammate's clean validation split).
   - Tests model in-distribution generalization on held-out seeds and combinations of known rewriting rules.
2. **External Benchmark (`--external`)**:
   - Non-generator expressions collected from literature, real-world binary obfuscators (e.g., Tigress, MBA-blast), opaque predicates, and higher-degree polynomial expansions.
   - Tests out-of-distribution algebraic reasoning and transferability beyond generator heuristics.

### Row Schema (`samples.jsonl`)
```json
{
  "id": "val_lin_0042",
  "tier": "linear",
  "row_type": "validation",
  "expression": "(x ^ y) + 2 * (x & y)",
  "canonical": "x + y",
  "ground_truth_nodes": 3,
  "variables": ["x", "y"]
}
```

Row types are strictly either `"validation"` or `"external"`.

---

## 3. Z3-Simplifier Baseline (`--z3-only`)

When `--z3-only` is specified, the harness runs the **Z3-simplifier baseline**:
1. Bypasses SLM candidate generation entirely.
2. Feeds the obfuscated expression directly into Z3's native expression simplifier and bit-vector rewriting tactics (`z3.simplify()`, `ctx-solver-simplify`, and BitVec algebraic rules).
3. Evaluates the resulting simplified AST for equivalence against the ground-truth canonical form.
4. Measures what percentage of expressions Z3 can simplify natively via purely symbolic rewrite rules, establishing the exact performance floor that the neurosymbolic CEGIS loop must beat.

---

## 4. Outcome Accounting & Categorization

Success in PALIMPSEST has a single mathematical definition: **formal equivalence proven by Z3 UNSAT on the miter $(A \ne B)$**. No candidate is accepted as an answer without formal SMT proof.

Each evaluated expression is classified into exactly one of five mutually exclusive outcome categories:

| Outcome Category | Description |
| :--- | :--- |
| **SUCCESS_PROVEN** | Z3 solver returned `UNSAT` (`QF_BV_UNSAT_64BIT_VERIFIED`) within $K$ attempts. Equivalent canonical identity proven. |
| **FAILED_EXHAUSTED** | Model exhausted all $K$ CEGIS loop attempts, receiving formal counterexamples on each iteration, without finding an equivalent candidate. |
| **TIMEOUT_UNKNOWN** | Z3 solver or model inference exceeded per-turn timeout budget, returning `UNKNOWN`. |
| **INVALID_SYNTAX** | Model proposed invalid Python syntax, unsupported non-MBA operators, or violated the AST whitelist. |
| **DEPTH_REJECTED** | Input expression or candidate exceeded `MAX_AST_DEPTH` (default 100) or character limits. **Reported in its own distinct category; never lumped into solver timeouts or model failures.** |

---

## 5. Statistical Metrics & Confidence Bounds

### Metric: "Success within $K$ attempts (CEGIS)"
The core evaluation metric is **"success within $K$ attempts (CEGIS)"** for $K \in \{1, 3, 5\}$ (not `pass@K`):

$$\text{Success within } K \text{ attempts} = \frac{\sum_{i=1}^{N} \mathbb{I}(\text{attempts}_i \le K \land \text{status}_i = \text{SUCCESS\_PROVEN})}{N}$$

### 95% Wilson Score Confidence Intervals
Because benchmark sample sizes vary and success rates approach asymptotic boundaries (0% or 100%), normal approximation intervals ($\hat{p} \pm 1.96 \sqrt{\hat{p}(1-\hat{p})/n}$) are statistically invalid. PALIMPSEST strictly reports **95% Wilson Score Intervals**:

$$w = \frac{\hat{p} + \frac{z^2}{2n} \pm z \sqrt{\frac{\hat{p}(1-\hat{p})}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}}$$

where $z = 1.95996$, $n$ is total partition rows, and $\hat{p}$ is the sample success proportion.

### Latency Distributions (p50 and p95)
Latency is measured with high-precision monotonic clocks and reported separately for:
- **Z3 SMT Solver Latency (p50 / p95)** in milliseconds.
- **Model Inference Latency (p50 / p95)** in milliseconds per CEGIS turn.

Both latency metrics are broken down by:
1. **Tier**: `linear`, `non-linear`, `polynomial`.
2. **Row Type**: `validation` vs `external`.

---

## 6. Report Header & Output Specification

Every evaluation execution prints a complete, reproducible metadata header:
- **Backend**: Resolved LLM backend (`ollama` or `llamacpp`).
- **GGUF SHA-256**: Cryptographic checksum of the loaded `.gguf` weights.
- **Sampling Temperature**: Base temperature (e.g., `0.2`) and repeated-candidate bump increment (`TEMP_RETRY_INCREMENT`).
- **History Mode**: Replay strategy (`last` or `all`).
- **Solver Configuration**: Z3 version, logic `QF_BV`, bit-width 64, per-check timeout budget.

### Sample Terminal Output Format
```text
================================================================================
PALIMPSEST FORMAL BENCHMARK REPORT
================================================================================
Backend:            ollama (palimpsest:latest)
GGUF SHA-256:       a9bb5f15c1f3012a4ec35e30a0f303661f1ab06b1d419962e91e7e5e3d6c4c23
Base Temperature:   0.20 (repeated-candidate bump: +0.10)
History Mode:       last (single-turn CEGIS counterexample replay)
Z3 Solver Logic:    QF_BV (64-bit unsigned, timeout=3000ms)
Database State:     eval_results.db
Evaluated Partition: --split validation (N=200)
================================================================================

Success within 1 attempt (CEGIS):  64.50%  (95% CI: [57.65%, 70.83%])
Success within 3 attempts (CEGIS): 81.00%  (95% CI: [75.02%, 85.83%])
Success within 5 attempts (CEGIS): 86.50%  (95% CI: [81.09%, 90.62%])

Outcome Breakdown:
  SUCCESS_PROVEN:    173  (86.50%)  [Z3 QF_BV UNSAT Verified]
  FAILED_EXHAUSTED:   18  ( 9.00%)  [K attempts exhausted]
  TIMEOUT_UNKNOWN:     5  ( 2.50%)  [Solver/inference timeout]
  INVALID_SYNTAX:      1  ( 0.50%)  [AST whitelist or syntax error]
  DEPTH_REJECTED:      3  ( 1.50%)  [AST depth > 100 gate rejection]

Latency & Performance by Tier & Row Type:
  Tier: Linear (validation, n=100)
    Z3 Latency:      p50 =  18.2 ms | p95 =  45.0 ms
    Model Latency:   p50 = 1240.0 ms | p95 = 2100.0 ms
  Tier: Non-Linear (validation, n=100)
    Z3 Latency:      p50 =  42.5 ms | p95 = 195.0 ms
    Model Latency:   p50 = 1850.0 ms | p95 = 3400.0 ms

Mean Attempts (Successful):  1.38
Mean AST Node Reduction:     58.4%
================================================================================
```

---

## 7. Command-Line Interface Parameters

| Option | Flag | Default | Description |
| :--- | :--- | :--- | :--- |
| `--dataset` | `-d` | `backend/data/samples.jsonl` | Path to JSONL evaluation dataset. |
| `--db` | | `eval_results.db` | Dedicated SQLite database storing eval state. |
| `--split` | `-s` | `validation` | Partition split: `validation` (held-out generator rows). |
| `--external` | | `False` | Evaluate non-generator expressions partition. |
| `--max-k` | `-k` | `5` | Maximum CEGIS attempts per expression ($K=1, 3, 5$). |
| `--limit` | `-n` | `None` | Restrict evaluation to first $N$ rows for fast checks. |
| `--resume` | `-r` | `False` | Resume evaluation from existing SQLite database. |
| `--allow-fake` | | `False` | Explicit override to permit `FakeLLMBackend`. Default strictly refuses. |
| `--z3-only` | | `False` | Run Z3 native simplifier baseline without SLM generation. |
