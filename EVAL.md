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

### Mutually Exclusive Outcome Categories (Unified `RunOutcome` Enum)

All synthesis attempts, evaluation rows, and baselines evaluate to exactly one outcome from the unified outcome enum:

| Outcome Enum | Description |
| :--- | :--- |
| **`verified`** | Z3 solver returned `UNSAT` (`QF_BV_UNSAT_64BIT_VERIFIED`) AND candidate AST node count is strictly smaller than original (`cand_nodes < obf_nodes`), or for `IDEMPOTENT` rows, no larger than original (`cand_nodes <= obf_nodes`). |
| **`verified-not-simpler`** | Z3 solver returned `UNSAT`, but candidate AST node count is NOT simpler than original (`cand_nodes >= obf_nodes`, or for idempotent rows `cand_nodes > obf_nodes`). Reported in UI as "Verified equivalent, but not simpler" and excluded from success numerator. |
| **`failed-exhausted`** | Model exhausted all $K$ CEGIS loop attempts, receiving formal counterexamples on each iteration, without proposing an equivalent candidate. In reporting, `failed-exhausted` benchmark rows are broken down by their last-attempt verification status (`SAT` / `UNKNOWN` / `INVALID`). |
| **`unknown-timeout`** | (Eval/Z3-Only Baseline / Attempt-Level) Z3 solver or model inference exceeded allocated time budget, returning `UNKNOWN`. |
| **`invalid`** | (Eval/Z3-Only Baseline / Attempt-Level) Model proposed invalid Python syntax or non-MBA operators failing the AST whitelist. |
| **`rejected-unsafe`** | Initial input expression rejected by the AST security gate whitelist. |
| **`depth-rejected`** | Obfuscated input or candidate exceeded `MAX_AST_DEPTH` (default 100). |
| **`unconvertible`** | In `--z3-only` baseline mode, expression could not be parsed or safely transformed into Z3 bit-vectors. |

### Sub-Category Tracking by Tier
In addition to the primary outcomes, the harness reports specific transformation classes:
1. **IDEMPOTENT**: Expressions where the input was already in minimal canonical form or simplified to identity.
2. **CONSTANT_FOLDING**: Expressions that completely collapse to invariant integer constants (e.g., `0`, `1`, `42`).
Both categories are reported separately and broken down by **tier** (`linear`, `non-linear`, `polynomial`).

---

## 5. Statistical Rigor: 95% Wilson Score Intervals

The metric **"Success within $K$ attempts (CEGIS)"** is reported for $K \in \{1, 3, 5\}$:

$$\text{Success within } K \text{ attempts} = \frac{\sum_{i=1}^{N} \mathbb{I}(\text{attempts}_i \le K \land \text{status}_i = \text{verified})}{N}$$

Success strictly requires both formal Z3 UNSAT equivalence and AST node reduction (`cand_nodes < obf_nodes`, or `cand_nodes <= obf_nodes` for IDEMPOTENT rows). Rows classified as `verified-not-simpler` remain in the universal denominator $N$ but do not count toward success.

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

### Terminal Output Format (Format Only, No Data)
> [!NOTE]
> All evaluation reports must be generated by code directly from the evaluation SQLite database, never hand-typed. No real benchmark results exist yet; the layout below illustrates the exact output format produced by `backend/eval/harness.py`.

```text
================================================================================
PALIMPSEST FORMAL BENCHMARK REPORT (MODEL CEGIS EVALUATION)
[format only, no data — generated by code from eval database]
================================================================================
Seed:               <seed_int>
Backend:            <backend_str> (<model_name>)
GGUF SHA-256:       <sha256_hash>
Base Temperature:   <base_temp> (repeated-candidate bump: +<bump_inc>)
History Mode:       <last|all>
System Prompt:      <prompt_content_or_none>
Shift Semantics:    <z3|x86_masked>
Max AST Depth:      <max_depth_int>
Tool Role:          <user|tool>
Num Predict:        <num_predict_int>
Database State:     <sqlite_file_path>
Evaluated Split:    --split <validation|external> (N=<total_rows>)
================================================================================

Success within 1 attempt (CEGIS):  <val_1>%  (95% CI: [<ci_low_1>%, <ci_high_1>%])
Success within 3 attempts (CEGIS): <val_3>%  (95% CI: [<ci_low_3>%, <ci_high_3>%])
Success within 5 attempts (CEGIS): <val_5>%  (95% CI: [<ci_low_5>%, <ci_high_5>%])

Outcome Breakdown (Universal Denominator N=<total_rows>):
  verified:            <cnt>  (<pct>%)  [Z3 QF_BV UNSAT Verified & Simpler]
  verified-not-simpler:<cnt>  (<pct>%)  [UNSAT but candidate AST >= original]
  failed-exhausted:    <cnt>  (<pct>%)  [All K attempts exhausted]
    ├── Last attempt SAT (Counterexample): <cnt>  (<pct>%)
    ├── Last attempt UNKNOWN (Timeout):     <cnt>  (<pct>%)
    └── Last attempt INVALID (Syntax):      <cnt>  (<pct>%)
  depth-rejected:      <cnt>  (<pct>%)  [AST depth > MAX_AST_DEPTH gate rejection]

Transformation Classes by Tier:
  Idempotent Expressions:    <cnt> (Linear: <c>, Non-Linear: <c>, Polynomial: <c>)
  Constant Folding:          <cnt> (Linear: <c>, Non-Linear: <c>, Polynomial: <c>)

Latency & Performance by Tier:
  Tier: Linear (<split>, n=<tier_count>)
    Z3 Latency:      p50 = <val> ms | p95 = <val> ms
    Model Latency:   p50 = <val> ms | p95 = <val> ms
  Tier: Non-Linear (<split>, n=<tier_count>)
    Z3 Latency:      p50 = <val> ms | p95 = <val> ms
    Model Latency:   p50 = <val> ms | p95 = <val> ms

Mean Attempts (Successful):  <val>
Mean AST Node Reduction:     <val>%
================================================================================
```

### Separate Z3-Only Baseline Report (Format Only, No Data)
> [!IMPORTANT]
> The `--z3-only` baseline runs independently and produces its own separate report. Its rows must never share a denominator with model synthesis rows.

```text
================================================================================
PALIMPSEST Z3-ONLY SIMPLIFIER BASELINE REPORT
[format only, no data — generated by code from eval database]
================================================================================
Solver:             Z3 SMT Solver (simplify / ctx-solver-simplify tactics)
Timeout per row:    <timeout_seconds>s
Database State:     <sqlite_file_path>
Evaluated Split:    --z3-only --split <validation|external> (N=<total_rows>)
================================================================================

Simplification Rate: <val>% (95% CI: [<ci_low>%, <ci_high>%])

Outcome Breakdown (Universal Denominator N=<total_rows>):
  verified:             <cnt>  (<pct>%)  [Z3 simplified & strictly fewer AST nodes]
  verified-not-simpler: <cnt>  (<pct>%)  [Equivalent but AST node count unchanged]
  unknown-timeout:      <cnt>  (<pct>%)  [Solver tactic timed out]
  unconvertible:        <cnt>  (<pct>%)  [Expression AST could not convert to Z3 BV]

Latency (p50 / p95):
  Z3 Simplifier Latency: p50 = <val> ms | p95 = <val> ms
================================================================================
```
