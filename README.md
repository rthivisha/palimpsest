# PALIMPSEST (Codename VEX-MORPH)

> **A Fully Local, Neurosymbolic 64-bit Mixed Boolean-Arithmetic (MBA) De-obfuscation Engine with Formal SMT Equivalence Proofs.**

---

## 1. Overview

**PALIMPSEST** de-obfuscates scrambled 64-bit Mixed Boolean-Arithmetic (MBA) expressions and **mathematically proves** the simplified result is equivalent to the original across all unsigned 64-bit bit-vectors.

- **Propose (Fast Guess)**: A small, fine-tuned language model proposes a simplified candidate expression.
- **Judge (Formal Proof)**: Microsoft Z3 SMT solver (Quantifier-Free Bit-Vectors, `QF_BV`) evaluates whether any 64-bit input exists where the original and candidate differ:
  - **UNSAT**: No counterexample exists. The simplification is mathematically proven.
  - **SAT**: Z3 extracts a concrete 64-bit counterexample (witness values, expected output, actual output, and a 64-bit bitwise diff).
- **CEGIS Loop**: LangGraph coordinates a Counterexample-Guided Inductive Synthesis loop, feeding the solver's counterexample back to the model until it finds the proven identity or exhausts its iteration budget.

---

## 2. Quickstart & How to Run

### Prerequisites
- **Python**: 3.10+ (tested on Python 3.11)
- **Node.js**: v18+ (tested on Node v24)
- **C/C++ Build Tools**: Not required (pure Python Z3 and prebuilt wheels)

### One-Time Setup
```bash
# 1. Set up Python virtual environment
python -m venv .venv
.venv\Scripts\activate  # On Windows (.venv/bin/activate on Linux/macOS)
pip install -r backend/requirements.txt  # Or pip install -e .

# 2. Install Node dependencies (root and frontend)
npm install
npm --prefix frontend install
```

### Running Both Servers (One Command)
Run both the FastAPI backend and Vite frontend concurrently with a single command from the project root:

```bash
npm run dev
```

This concurrently launches:
1. **Backend Server**: Uvicorn listening at `http://127.0.0.1:8000`
2. **Frontend UI**: Vite dev server at `http://localhost:5173`
   - Automatically proxies `/api/*` requests to port 8000 (`changeOrigin: true`).

Open your browser to:
```
http://localhost:5173
```

---

## 3. UI Features & Forensic Cyber-Lab Interface

1. **Command Center**:
   - Monospace expression input supporting 64-bit bitwise (`&`, `|`, `^`, `~`) and arithmetic (`+`, `-`, `*`, `<<`, `>>`) operators.
   - Expression presets for classic MBA identities (e.g. `(x ^ y) + 2 * (x & y)`).
   - CEGIS iteration slider (1 to 10 loops).
   - Concurrency backoff handling: Displays *"previous run still finishing"* on HTTP 429 and honors `Retry-After`.
2. **Live Loop Graph (`@xyflow/react`)**:
   - Real-time visualization of the LangGraph state machine (`parse_ast` &rarr; `propose` &rarr; `verify` &rarr; `router` &rarr; `finalize_success` / `finalize_fail`).
   - Active node glowing highlights, animated edges, and backward counterexample packet animation on retry.
   - Respects `prefers-reduced-motion`.
3. **Attempt Timeline**:
   - Per-attempt breakdown showing candidate expressions, Z3 solver latency in milliseconds, collapsible neural `<think>` reasoning, and injected retry feedback.
4. **Counterexample 64-bit Bit Visualizer**:
   - For `SAT` results, displays concrete witness inputs, expected vs actual values (in decimal and hexadecimal), and a 64-bit binary row diff highlighting differing bits.
5. **Proof & Compression Banner**:
   - **On Success**: Green `EQUIVALENCE PROVEN BY Z3 (QF_BV, 64-bit)` badge, copyable code, and AST node reduction metrics (e.g. 9 &rarr; 3 nodes, 66.7% compression).
   - **On Failure**: Honest red `NOT VERIFIED. No answer accepted.` banner. Unverified guesses are never presented as solutions.
6. **Explain Mode**:
   - Beginner-friendly tooltips explaining MBA, CEGIS, Bit-Vectors, and SMT solving in plain English.
7. **History & Insights**:
   - Local SQLite telemetry viewer showing past runs, success rates, attempt distributions (Recharts), and one-click replay in the live graph.
8. **Dataset Explorer**:
   - Curated benchmark rows demonstrating algebraic identities and opaque predicates.

---

## 4. Running Tests

```bash
# Run backend test suite with timeout and duration profiling
pytest -v --durations=10

# Check frontend TypeScript compilation and build
npm run build:frontend
```

---

## 5. Security & Safety

- **AST Allowlist**: Python's AST parser rejects function calls, attribute access, imports, lambdas, non-integer constants, and recursion depth $> 100$.
- **Isolated Z3 Contexts**: Verification runs with dedicated `z3.Context()` instances to prevent solver state pollution.
- **Single-Slot Inference Lock**: Concurrent execution requests receive HTTP 429 with `Retry-After: 5` to protect local hardware.

---

## 6. Model Integration Guide (Ollama & llama-cpp)

PALIMPSEST supports three backend engines:
- `fake`: Deterministic, offline scripted simulator for instant testing and CI without weights.
- `ollama`: (Recommended) High-performance local inference daemon using Ollama with streaming cancellation.
- `llamacpp`: In-process Python bindings for direct GGUF inference with multi-threading.

### Step-by-Step Instructions: Integrating the Fine-Tuned Model

#### Option A: Ollama Daemon (Recommended)

1. **Place Model Weights**:
   Ensure your fine-tuned quantized model is located in the `models/` directory:
   ```bash
   models/palimpsest-q4_k_m.gguf
   ```

2. **Create the Ollama Model**:
   With Ollama running (`ollama serve`), run the following command from the project root:
   ```bash
   ollama create palimpsest -f Modelfile
   ```
   This compiles the ChatML template and stop tokens matching the training dataset format:
   - Stop tokens: `<|im_end|>`, `<|im_start|>`
   - Sampling: `temperature 0.2`, `top_p 0.95`, `num_ctx 2048`

3. **Configure Environment**:
   In your `.env` file (or environment variables), set:
   ```bash
   PALIMPSEST_BACKEND=ollama
   OLLAMA_MODEL=palimpsest
   OLLAMA_BASE_URL=http://localhost:11434
   ```

4. **Verify Integration**:
   Run the CLI de-obfuscation demo against the live Ollama model:
   ```bash
   .venv\Scripts\python backend/app/cli_demo.py "(x ^ y) + 2 * (x & y)" --backend ollama
   ```
   Or launch the full application with `npm run dev` and select expressions in the web UI.

#### Option B: Direct GGUF Inference with llama-cpp-python

1. **Install Python Bindings**:
   ```bash
   pip install llama-cpp-python
   ```

2. **Configure Environment**:
   In your `.env` file, set:
   ```bash
   PALIMPSEST_BACKEND=llamacpp
   LLAMACPP_MODEL_PATH=models/palimpsest-q4_k_m.gguf
   LLAMACPP_N_THREADS=8
   ```

3. **Run Smoke Test**:
   ```bash
   pytest backend/tests/test_llm_backends.py -v
   ```

- **Air-Gapped Telemetry**: SQLite database runs locally in WAL mode with a dedicated background writer thread. Cloud telemetry (LangSmith) is disabled by default.

