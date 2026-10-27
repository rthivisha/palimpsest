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

## 2. Dataset Partitions & Partitioning Rules

The evaluation corpus (`backend/data/samples.jsonl`) contains distinct partitions:

### A. Validation Split (`--split validation`)
- Generator-produced expressions that were **strictly excluded from the fine-tuning training corpus** (derived from the teammate's clean validation split).
- **Normalised Target Guarantee**: All validation rows are held out by **normalised target**. No expression in the validation split shares an algebraically normalised canonical target form (e.g. `x + y`, `x ^ y`, `~x`) with expressions present in the fine-tuning training set. This strictly proves algebraic generalization rather than rote memorization of canonical outcomes.

### B. External Benchmark (`--external`)
- Non-generator expressions collected from literature, real-world binary obfuscators (e.g., Tigress, MBA-blast), opaque predicates, and higher-degree polynomial expansions.
- **Source and Licence Requirement**: Every external row requires explicit `source` (e.g., `"Tigress 3.1"`, `"MBA-Blast benchmark"`, `"Eyrolles 2016"`) and `licence` (e.g., `"Apache-2.0"`, `"MIT"`, `"Public Domain"`) metadata fields.
- **Safety Gate Accounting**: External expressions that violate AST complexity limits or operator whitelists are classified into their own distinct `GATE_REJECTED` category and remain in the evaluation denominator.

### Row Schema (`samples.jsonl`)
```json
{
  "id": "val_lin_0042",
  "tier": "linear",
  "row_type": "validation",
  "expression": "(x ^ y) + 2 * (x & y)",
  "canonical": "x + y",
  "normalised_target": "x + y",
  "ground_truth_nodes": 3,
  "variables": ["x", "y"],
  "source": "generator_v2",
  "licence": "internal_held_out"
}
```

---

## 3. Z3-Simplifier Baseline (`--z3-only`)

When `--z3-only` is specified, the harness executes the symbolic SMT baseline:
1. **Per-Row Timeout**: Enforces a strict per-expression timeout (e.g., 3,000 ms) matching the neural verifier budget.
2. **Safety-Gate Conversion**: Converts the obfuscated expression via the AST safety gate. If an expression cannot be parsed or safely transformed, it is categorized separately as `UNCONVERTIBLE`.
3. **Native Simplification**: Feeds the expression directly into Z3's native expression simplifier (`z3.simplify()`, `ctx-solver-simplify`, and BitVec rewrite tactics) without any language model generation.
4. **Identical Verifier**: Judges the simplified candidate using the exact same formal verifier (`verify_equivalence()`) to ensure consistent, unbiased comparison against neurosymbolic CEGIS.

---

## 4. Single-Run Protocol & Outcome Accounting

### Single-Run Execution ($K_{\max}=5$)
To minimize redundant compute, each expression row is run **exactly once** through the CEGIS loop with a maximum budget of 5 attempts ($K_{\max}=5$). Success metrics for $K \in \{1, 3, 5\}$ are derived analytically from the iteration index of the first verified equivalent candidate:
- **Success @ 1 Attempt**: Verified equivalent on attempt 1.
- **Success @ 3 Attempts**: First verified equivalent on attempt $\le 3$.
- **Success @ 5 Attempts**: First verified equivalent on attempt $\le 5$.

### Universal Denominator Rule
**Every row stays in the denominator ($N$) across all metrics.** Expressions rejected by the AST depth gate (`DEPTH_REJECTED`), security gate (`GATE_REJECTED`), or timing out (`TIMEOUT_UNKNOWN`) are never discarded from the evaluation pool.

### Mutually Exclusive Outcome Categories

| Outcome Category | Description |
| :--- | :--- |
| **SUCCESS_PROVEN** | Z3 solver returned `UNSAT` (`QF_BV_UNSAT_64BIT_VERIFIED`) within $K$ attempts. Equivalent canonical identity formally proven. |
| **FAILED_EXHAUSTED** | Model exhausted all $K$ CEGIS loop attempts, receiving formal counterexamples on each iteration, without proposing an equivalent candidate. |
| **TIMEOUT_UNKNOWN** | Z3 solver or model inference exceeded allocated time budget, returning `UNKNOWN`. |
| **INVALID_SYNTAX** | Model proposed invalid Python syntax or non-MBA operators failing the AST whitelist. |
| **DEPTH_REJECTED** | Expression or candidate exceeded `MAX_AST_DEPTH` (default 100) or character limits. Reported in its own distinct category. |
| **GATE_REJECTED** | External row violated security gate whitelist (e.g. unauthorized calls, disallowed types). Reported independently. |

### Sub-Category Tracking by Tier
In addition to the primary outcomes, the harness reports specific transformation classes:
1. **IDEMPOTENT**: Expressions where the input was already in minimal canonical form or simplified to identity.
2. **CONSTANT_FOLDING**: Expressions that completely collapse to invariant integer constants (e.g., `0`, `1`, `42`).
Both categories are reported separately and broken down by **tier** (`linear`, `non-linear`, `polynomial`).

---

## 5. Statistical Rigor: 95% Wilson Score Intervals

The metric **"Success within $K$ attempts (CEGIS)"** is reported for $K \in \{1, 3, 5\}$:

$$\text{Success within } K \text{ attempts} = \frac{\sum_{i=1}^{N} \mathbb{I}(\text{attempts}_i \le K \land \text{status}_i = \text{SUCCESS\_PROVEN})}{N}$$

Because sample proportions approach boundaries ($0\%$ or $100\%$), normal approximation intervals are invalid. PALIMPSEST strictly reports **95% Wilson Score Intervals**:

$$w = \frac{\hat{p} + \frac{z^2}{2n} \pm z \sqrt{\frac{\hat{p}(1-\hat{p})}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}}$$

where $z = 1.95996$, $n = N$ (total partition rows), and $\hat{p}$ is the sample success proportion.

### Latency Distributions (p50 and p95)
Reported separately for:
- **Z3 SMT Solver Latency (p50 / p95)** in milliseconds.
- **Model Inference Latency (p50 / p95)** in milliseconds per CEGIS turn.
Both are broken down by **tier** (`linear`, `non-linear`, `polynomial`) and **row type** (`validation` vs `external`).

---

## 6. Report Header & Reproducibility Standard

Every evaluation execution prints an exhaustive reproducibility header:
- **Seed**: Fixed integer random seed (e.g. `42`).
- **Backend & Model**: Active engine (`ollama` or `llamacpp`) and model name.
- **GGUF SHA-256**: Cryptographic hash of the `.gguf` weights.
- **Sampling Temperature**: Base temperature and repeated-candidate bump increment (`TEMP_RETRY_INCREMENT`).
- **History Mode**: Replay strategy (`last` or `all`).
- **System Prompt**: Content of `SYSTEM_PROMPT` (or `[empty]`).
- **Shift Semantics**: `SHIFT_SEMANTICS` (`z3` or `x86_masked`).
- **Max AST Depth**: `MAX_AST_DEPTH` (default 100).
- **Tool Role**: Role identifier used for Z3 feedback turns (`user` or `tool`).
- **Num Predict**: Maximum generation tokens (`NUM_PREDICT`, default 512).
- **Database State**: SQLite file path storing the evaluation results.

### Sample Terminal Output Format
```text
================================================================================
PALIMPSEST FORMAL BENCHMARK REPORT
================================================================================
Seed:               42
Backend:            ollama (palimpsest:latest)
GGUF SHA-256:       a9bb5f15c1f3012a4ec35e30a0f303661f1ab06b1d419962e91e7e5e3d6c4c23
Base Temperature:   0.20 (repeated-candidate bump: +0.10)
History Mode:       last (single-turn CEGIS counterexample replay)
System Prompt:      [none]
Shift Semantics:    z3 (default 64-bit BitVec)
Max AST Depth:      100
Tool Role:          user
Num Predict:        512
Database State:     eval_results.db
Evaluated Split:    --split validation (N=200, normalised-target held out)
================================================================================

Success within 1 attempt (CEGIS):  64.50%  (95% CI: [57.65%, 70.83%])
Success within 3 attempts (CEGIS): 81.00%  (95% CI: [75.02%, 85.83%])
Success within 5 attempts (CEGIS): 86.50%  (95% CI: [81.09%, 90.62%])

Outcome Breakdown (Universal Denominator N=200):
  SUCCESS_PROVEN:    173  (86.50%)  [Z3 QF_BV UNSAT Verified]
  FAILED_EXHAUSTED:   18  ( 9.00%)  [5 attempts exhausted]
  TIMEOUT_UNKNOWN:     5  ( 2.50%)  [Solver/inference timeout]
  INVALID_SYNTAX:      1  ( 0.50%)  [AST whitelist or syntax error]
  DEPTH_REJECTED:      3  ( 1.50%)  [AST depth > 100 gate rejection]

Transformation Classes by Tier:
  Idempotent Expressions:    12 (Linear: 8, Non-Linear: 4, Polynomial: 0)
  Constant Folding:          15 (Linear: 5, Non-Linear: 7, Polynomial: 3)

Latency & Performance by Tier:
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
