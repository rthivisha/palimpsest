PALIMPSEST (Codename: VEX-MORPH)
A fully local, proof-first, neurosymbolic 64-bit Mixed Boolean-Arithmetic (MBA) de-obfuscation engine with formal SMT equivalence proofs.

PALIMPSEST is a local, zero-trust system for simplifying obfuscated arithmetic and bitwise expressions by combining a small local language model with Microsoft Z3 formal verification. The model proposes candidate rewrites, the solver checks them, and a CEGIS-style retry loop feeds back counterexamples until an equivalence-verified canonical form is reached.

> [!NOTE]
> **Scope & Verification**: Trained on a fixed family of MBA patterns; expressions outside it may not verify. Z3 rejects any unproven answer. Equivalence proven by Z3 (QF_BV, 64-bit).

This repository implements the exact workflow shown in the live UI:

parse AST
propose a candidate rewrite
verify via Z3
recover a SAT counterexample
retry with witness-guided repair
accept only formally verified equivalence
Overview
PALIMPSEST addresses a common reverse-engineering problem: real-world obfuscators rewrite simple expressions into large identities that are hard to simplify by inspection. Examples include:

Mixed Boolean-Arithmetic (MBA)
opaque zero terms
control-flow flattening patterns
algebraic identity rewrites that preserve semantic output but hide the true expression
Instead of trusting a monolithic LLM guess, PALIMPSEST enforces a strict proof-first loop:

Parse the input into a security-guarded AST.
Proposal stage: a small local model suggests a simplified candidate.
Verification stage: Z3 checks equivalence over 64-bit bit-vectors (QF_BV).
Counterexample loop: if z3 finds SAT, it emits a witness and the model retries.
Accept only proven equivalent outputs.
Why PALIMPSEST
Obfuscated arithmetic and bitwise expressions often hide a simple identity like x + y inside a large algebraic rewrite. Generic decompilers and monolithic LLMs often fail because they do not prove equivalence.

PALIMPSEST avoids that trap by enforcing a strict proof-first loop:

parse input into a constrained AST
propose a candidate simplification with a local model
verify equivalence in Z3 over 64-bit bit-vectors (QF_BV)
extract SAT counterexamples when the rewrite is wrong
feed the witness back into the model for repair
output only results that pass formal verification
UI / Product Snapshot
The dashboard mirrors the architecture of the project and exposes a live proof workflow:

De-obfuscator
History & Insights
Dataset Explorer
Z3 QF_BV status
LangGraph execution graph
proof banner with canonical form and AST reduction
live counterexample diagnostics
Example UI state
Original obfuscated input: (x ^ y) + 2 * (x & y)
Candidate (iteration 1): (x + y) - 1
Z3 result: SAT
Counterexample witness: {'x': 0, 'y': 1}
Retry candidate: x + y
Final result: VERIFIED EQUIVALENT
Current Repository Capabilities
FastAPI backend with local orchestration
LangGraph-based graph loop and retry routing
Z3 verification for 64-bit arithmetic / bitwise equivalence
local model support for fake, ollama, and llamacpp
Vite + React frontend for live execution and proof visualization
SQLite telemetry for runs and attempt history
test coverage for API, graph routing, and verification behavior
Repository Layout
Text
palimpsest/
├── .env.example
├── ARCHITECTURE.md
├── LICENSE
├── README.md
├── TASKS.md
├── backend/
│   ├── app/
│   ├── requirements.txt
│   └── tests/
├── examples/
│   ├── README.md
│   └── sample_mba_cases.json
├── frontend/
│   ├── package.json
│   └── src/
├── models/
├── package.json
├── pytest.ini
├── training/
│   ├── ast_slicer.py
│   ├── dataset_generator.py
│   ├── mba_mutator.py
│   └── z3_verifier.py
├── .gitignore
├── Modelfile
├── scripts/
└── palimpsest.sqlite   # generated locally
Architecture Overview
Mermaid
flowchart TD
    User([User / UI]) --> API[FastAPI API]
    API --> Graph[LangGraph Orchestrator]
    Graph --> Parse[parse_ast]
    Parse --> Safe{Safe AST?}
    Safe -->|No| Reject[REJECTED_UNSAFE]
    Safe -->|Yes| Propose[propose]
    Propose --> Model[Local Model Backend]
    Model --> Candidate[Candidate Expression]
    Candidate --> Verify[verify]
    Verify --> Check{Equivalent?}
    Check -->|SAT| Retry[Counterexample Feedback]
    Retry --> Propose
    Check -->|UNSAT| Success[Verified Equivalent]
System Components
parse_ast: validates the expression and rejects unsafe input
propose: local model proposes a candidate rewrite
verify: Z3 checks equivalence in QF_BV
router: decides whether to retry or finalize
finalize_success: emits the proven canonical form
finalize_fail: emits a failure state when retries are exhausted
Features
local-only model execution
strict AST validation and safety gate
64-bit QF_BV verification using Z3
proof-first output only
iterative retry loop on SAT counterexamples
live web UI with execution graph and proof display
SQLite telemetry and run history
benchmark examples and automated tests
Quickstart
Prerequisites
Python 3.10+
Node.js 18+
npm
Optional: Ollama or a local llama.cpp GGUF model
### 1. Clone the repository
```bash
git clone https://github.com/rthivisha/palimpsest.git
cd palimpsest
```

### 2. Create and activate a virtual environment

**PowerShell (Windows):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Command Prompt (Windows):**
```cmd
python -m venv .venv
.\.venv\Scripts\activate.bat
```

**macOS / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies
```bash
pip install -r backend/requirements.txt
```

### 4. Install frontend dependencies
```bash
npm install
npm --prefix frontend install
```

### 5. Configure environment variables

**PowerShell / Command Prompt:**
```cmd
copy .env.example .env
```

**macOS / Linux:**
```bash
cp .env.example .env
```

Then edit `.env` as needed. The default backend is `fake`, which is safe for local testing, UI demos, and CI flows.

### 6. Run the app
```bash
npm run dev
```

This launches:
- FastAPI backend: `http://127.0.0.1:8000`
- Vite frontend: `http://127.0.0.1:5173`

Open `http://127.0.0.1:5173` in your browser.

## Environment Variables
The project reads configuration from `.env` via `pydantic-settings`.

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PALIMPSEST_BACKEND` | `fake` | Backend type: `fake`, `ollama`, or `llamacpp` |
| `OLLAMA_MODEL` | `palimpsest` | Model name for Ollama |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama endpoint URL |
| `PROMPT_PROFILE` | `unsloth_qwen25` | Prompt profile (`unsloth_qwen25` for ollama/llamacpp, `plain` for fake) |
| `WITNESS_POLICY` | `z3_default` | Counterexample witness policy (`z3_default` raw model or `bounded`) |
| `RSHIFT_SEMANTICS` | `logical` | Right-shift semantics (`logical` zero-fill LShR or `arithmetic`) |
| `SHIFT_SEMANTICS` | `z3` | Bitshift overflow semantics (`z3` zero on >= 64, or `x86_mask`) |
| `Z3_TIMEOUT_MS` | `3000` | Solver timeout in milliseconds |
| `NUM_PREDICT` | `512` | Max generated tokens per model response |
| `OLLAMA_KEEP_ALIVE` | `5m` | Ollama model memory residency duration |
| `MODEL_WARMUP` | `false` | Warm up model on server startup |
| `TEMP_RETRY_INCREMENT` | `0.1` | Temperature bump on repeat candidate guess |
| `MAX_ITERATIONS` | `5` | Maximum CEGIS retry iterations |
| `HISTORY_MODE` | `last` | History replay mode (`last` failure only or `all`) |
| `LLAMACPP_MODEL_PATH` | `models/palimpsest-q4_k_m.gguf` | Path to GGUF model file |
| `LLAMACPP_N_THREADS` | `4` | llama.cpp worker threads |
| `HOST` | `127.0.0.1` | API bind host |
| `PORT` | `8000` | API bind port |
Supported Model Backends
Fake backend
Use this for development, CI, and deterministic demos.

env
PALIMPSEST_BACKEND=fake
Ollama backend
env
PALIMPSEST_BACKEND=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=palimpsest
llama.cpp backend
env
PALIMPSEST_BACKEND=llamacpp
LLAMACPP_MODEL_PATH=models/palimpsest-q4_k_m.gguf
LLAMACPP_N_THREADS=4
Model Integration Guide
Option A: Ollama daemon
Place your model in models/.
Ensure Ollama is running:
bash
ollama serve
Create the local model:
bash
ollama create palimpsest -f Modelfile
Configure .env:
bash
PALIMPSEST_BACKEND=ollama
OLLAMA_MODEL=palimpsest
OLLAMA_BASE_URL=http://127.0.0.1:11434
Run the demo CLI:
bash
python backend/app/cli_demo.py "(x ^ y) + 2 * (x & y)" --backend ollama
Option B: Direct GGUF via llama.cpp
bash
pip install llama-cpp-python
Then set:

bash
PALIMPSEST_BACKEND=llamacpp
LLAMACPP_MODEL_PATH=models/palimpsest-q4_k_m.gguf
LLAMACPP_N_THREADS=8

### Troubleshooting: Ollama

If the UI reports **"MODEL OFFLINE: Ollama is not running at http://127.0.0.1:11434"** or synthesis fails to connect:

#### 1. Windows System Tray App & Startup on Login
- The official Windows installer runs Ollama as a background service in your Windows System Tray (notification area near the clock).
- If the Ollama icon is missing from the tray, search for **Ollama** in your Start Menu and launch it.
- To ensure Ollama is always active, right-click the Ollama tray icon and enable **Run at login** (or enable it under Task Manager > Startup apps).
- Alternatively, launch the daemon directly from any terminal:
  ```cmd
  ollama serve
  ```

#### 2. Run the Palimpsest System Doctor (`npm run doctor`)
To diagnose your full environment, virtualenv, ports, and Ollama status in one step:

**PowerShell (Windows):**
```powershell
npm run doctor
```

**Command Prompt (Windows):**
```cmd
npm run doctor
```

The doctor validates:
- Node.js runtime (>= 18.0.0)
- Python virtual environment (`.venv`)
- GGUF weights file presence (`models/palimpsest-q4_k_m.gguf`)
- Ports 8000 and 5173 status (free or owned by Palimpsest)
- Ollama daemon reachability at `OLLAMA_BASE_URL`
- Model catalog registration for `palimpsest`
- Active `.env` settings

#### 3. Register the Model (`npm run model:setup`)
If Ollama is running but `palimpsest` is missing from the model catalog, run the automated setup command (which checks that `models/palimpsest-q4_k_m.gguf` is present before creating the model):

**PowerShell (Windows):**
```powershell
npm run model:setup
```

**Command Prompt (Windows):**
```cmd
npm run model:setup
```

Or manually:
```cmd
ollama create palimpsest -f Modelfile
```

#### 4. Optional Fallback to llama.cpp (`BACKEND_FALLBACK=llamacpp`)
If you want automatic fallback to local CPU inference when Ollama is offline or stopping:
1. Set in `.env`:
   ```env
   BACKEND_FALLBACK=llamacpp
   ```
2. When active, Palimpsest runs `models/palimpsest-q4_k_m.gguf` directly and displays a visible **LLAMA.CPP (fallback)** badge on the dashboard header and Proof Banner. It never falls back silently or to the fake backend.

#### 5. Verify Daemon Health & Catalog
Confirm the daemon is listening and inspect installed models:

**PowerShell / Command Prompt:**
```cmd
curl.exe http://127.0.0.1:11434/api/tags
curl.exe http://127.0.0.1:8000/api/health
```

The `/api/health` response provides actionable diagnosis:
```json
{
  "status": "ok",
  "backend": "ollama",
  "model_name": "palimpsest",
  "model_status": "ready",
  "model_reachable": true,
  "model_unreachable_reason": null,
  "hint": null,
  "fix_command": null,
  "is_fallback": false
}
```
If `model_status` is `"ollama_not_running"` or `"model_missing"`, the UI displays a recovery panel with copyable commands and a "Check again" button.
Ollama CLI Proof Example
This is the proof pattern the project is designed to produce: a near-miss candidate is rejected by Z3, the solver extracts the witness, and the model repairs itself until the expression is formally verified.

Text
> Node Executed: [parse_ast]
> AST Parsed Successfully.
Initial Semantic AST Nodes (BinOp/UnaryOp/Name/Constant): 9

> Node Executed: [propose]
[Iteration 1] Model proposed candidate: '(x + y) - 1'
Reasoning summary: AST Nodes: 13. Initial structural reduction and operator estimation...

> Node Executed: [verify]
Z3 Miter Check Status: SAT (78.89 ms)
Counterexample Witness Discovered (Bounded Bv < 16): {'x': 0, 'y': 1}
Evaluation: Expected 1, Actual 0
Bit Discrepancy (64-bit diff): 0000000000000000000000000000000000000000000000000000000000000001
--> Recycling witness back into model context for retry...

> Node Executed: [propose]
[Iteration 2] Model proposed candidate: 'x + y'
Reasoning summary: Counterexample witness assignment (x=0, y=1) evaluated candidate '(x + y) - 1' to the incorrect value 0. Plugging assignment into candidate isolates the bitwise discrepancy in the evaluated operator. Restoring for algebraic identity yields verified canonical expression x + y...

> Node Executed: [verify]
> Node Executed: [finalize_success]

========================================
[+] RESULT: VERIFIED EQUIVALENT
[+] Proven Canonical Form: x + y
[+] AST Nodes: Final 3 (Reduced by 66.67%)
[+] Equivalence proven by Z3 (QF_BV, 64-bit)
========================================
This demonstrates the exact retry loop the project is designed to run.

Sample Data and Test Cases
Benchmark examples are included under:

examples/sample_mba_cases.json
examples/README.md
The test suite is located here:

backend/tests/test_api.py
backend/tests/test_core.py
backend/tests/test_graph.py
Run the backend suite:

bash
pytest -v --durations=10
Run a frontend build validation:

bash
npm run build:frontend
Technical Design Documents
The architecture and design notes are documented in:

ARCHITECTURE.md
TASKS.md
These cover the runtime protocol, state machine, safety constraints, verification contract, and model integration strategy.

Security and Safety
PALIMPSEST is built around strict local execution and formal verification.

Safety controls include:

AST allowlisting
strict length and depth limits
no eval() or arbitrary code execution
isolated Z3 verification contexts
single-run locking for local inference resources
local-only SQLite telemetry
License
This project is licensed under the MIT License.

See the LICENSE file for details.

Repository
GitHub: https://github.com/rthivisha/palimpsest
Summary
PALIMPSEST is a local, proof-first de-obfuscation system for 64-bit MBA expressions. It is intended to be an auditable, air-gapped alternative to model-only rewriting where correctness is enforced by formal verification rather than guesswork.

## Results & Evaluation Status

> [!IMPORTANT]
> **No held-out evaluation yet; training-row diagnostics only.**
> Official benchmark figures will be generated strictly by code execution from the evaluation SQLite database once the held-out evaluation protocol is run.

Example Benchmark Data
JSON
{
  "metadata": {
    "project": "PALIMPSEST",
    "codename": "VEX-MORPH",
    "description": "Benchmark sample expressions for MBA simplification and equivalence verification."
  },
  "cases": [
    {
      "id": "mba_add_identity_01",
      "name": "XOR + carry identity",
      "original": "(x ^ y) + 2 * (x & y)",
      "expected": "x + y",
      "category": "linear_mba",
      "notes": "Classic identity for addition via XOR and carry bits."
    },
    {
      "id": "mba_add_identity_02",
      "name": "OR + AND identity",
      "original": "(x | y) + (x & y)",
      "expected": "x + y",
      "category": "linear_mba",
      "notes": "Equivalent to x + y for unsigned 64-bit integers."
    },
    {
      "id": "mba_xor_identity_01",
      "name": "XOR via OR minus AND",
      "original": "(x | y) - (x & y)",
      "expected": "x ^ y",
      "category": "bitwise_mba",
      "notes": "Standard identity used in mixed arithmetic / bitwise simplification."
    },
    {
      "id": "mba_opaque_zero_01",
      "name": "Opaque zero cancellation",
      "original": "((x | y) - (x ^ y)) - (x & y)",
      "expected": "0",
      "category": "opaque_zero",
      "notes": "Algebraically zero for all valid 64-bit inputs."
    },
    {
      "id": "mba_counterexample_01",
      "name": "Near-miss candidate",
      "original": "(x ^ y) + 2 * (x & y)",
      "candidate": "x ^ y",
      "expected_status": "SAT",
      "notes": "Near-miss candidate fails with a witness like x=0, y=1."
    }
  ]
}
MIT License
md
MIT License

Copyright (c) 2025 PALIMPSEST contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
