# PALIMPSEST — Implementation Tasks Checklist

## Phase 0: Architecture, Planning & Setup
- [x] Initialize Git repository (`main` branch)
- [x] Configure `.gitignore` covering `.env`, `.venv`, `models/*.gguf`, `*.sqlite`, `node_modules`, etc.
- [x] Create `.env.example` with clear parameter defaults and [CONFIRM] items
- [x] Author comprehensive `ARCHITECTURE.md`
- [x] Author `TASKS.md` implementation checklist
- [ ] Create base directory structure (`backend/app`, `frontend/src`, `models/`, `data/`)
- [ ] Ask User for GitHub remote URL & perform initial commit + push
- [ ] **AWAIT USER APPROVAL TO BEGIN PHASE 1**

---

## Phase 1: Core Verification & Security Infrastructure
- [x] Implement `backend/app/core/safety.py`:
  - [x] Strict AST allowlist checker (`Expression`, `BinOp`, `UnaryOp`, `Name`, `Constant(int)`, `Load`, arithmetic & bitwise operators)
  - [x] Rejection of dangerous nodes (`Call`, `Attribute`, `Import`, strings, floats, lambdas)
  - [x] Input length limit enforcement ($\le 5000$ chars) and recursion depth check ($\le 100$)
- [x] Implement `backend/app/core/ast_utils.py`:
  - [x] AST node counter (`count_nodes`)
  - [x] AST variable extractor (`extract_variables`)
  - [x] Expression pretty-printer / normalizer
- [x] Implement `backend/app/core/verifier.py`:
  - [x] AST to Z3 BitVec 64-bit expression translator
  - [x] Constant 64-bit masking (`val & 0xFFFFFFFFFFFFFFFF`)
  - [x] Operator mapping with logical right-shift (`LShR`)
  - [x] Z3 miter solver check with configurable timeout (`3000ms`)
  - [x] Counterexample witness generation, concrete expected/actual evaluation, and 64-bit diff calculation
- [x] Implement unit tests in `backend/tests/test_core.py`:
  - [x] Test safety gate allowlist and edge case rejection
  - [x] Test known MBA identities return UNSAT
  - [x] Test wrong candidates return SAT with valid witness
  - [x] Test 64-bit overflow and shift behaviors
- [ ] Commit & Git Tag: `phase-1-complete`
- [ ] **STOP AND REQUEST USER REVIEW**

---

## Phase 2: LangGraph Orchestration & Fake Backend
- [x] Implement `backend/app/llm/base.py`:
  - [x] Base LLM backend interface `BaseLLMBackend`
  - [x] Message schemas and ChatML formatting helpers
- [x] Implement `backend/app/llm/prompts.py`:
  - [x] Prompt builder matching training format character-for-character
  - [x] Candidate extractor parsing `<think>` blocks defensive against malformed tags
- [x] Implement `backend/app/llm/fake.py`:
  - [x] Scripted fake model backend: first guess `x ^ y`, second guess `x + y`
  - [x] Formatted `<think>` output reproduction
- [x] Implement `backend/app/graph/state.py`:
  - [x] `PalimpsestState` and `AttemptRecord` TypedDict definitions
- [x] Implement `backend/app/graph/nodes.py`:
  - [x] `parse_ast_node`
  - [x] `propose_node` (with repeated candidate temperature escalation)
  - [x] `verify_node` (with AST gate and Z3 verification)
  - [x] `finalize_success_node` and `finalize_fail_node`
- [x] Implement `backend/app/graph/routers.py`:
  - [x] Conditional edge routing after verification
- [x] Implement `backend/app/graph/build.py`:
  - [x] StateGraph construction and compilation
- [x] Implement CLI demo `backend/app/cli_demo.py` demonstrating:
  - [x] Input: `(x ^ y) + 2 * (x & y)`
  - [x] Attempt 1: `x ^ y` -> SAT with witness `{'x': 1, 'y': 1}`, expected 2, actual 0
  - [x] Attempt 2: `x + y` -> UNSAT -> `VERIFIED_EQUIVALENT`
- [x] Implement tests in `backend/tests/test_graph.py`
- [ ] Commit & Git Tag: `phase-2-complete`
- [ ] **STOP AND REQUEST USER REVIEW**

---

## Phase 3: API & Telemetry
- [x] Implement `backend/app/telemetry/db.py`:
  - [x] SQLite initialization in WAL mode (`PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000`)
  - [x] Dedicated background single-writer thread and queue for `runs` and `attempts`
- [x] Implement FastAPI application in `backend/app/main.py`:
  - [x] Host-header check middleware (localhost, 127.0.0.1, testserver)
  - [x] CORS middleware (localhost only)
  - [x] Lifespan database writer thread management
- [x] Implement API routes:
  - [x] `POST /api/run`: Real-time SSE event stream emitting `run_started`, `node_started`, `node_finished`, `proposal`, `verification`, `retry`, `final`, `error`
  - [x] Cooperative client disconnect detection and cancellation
  - [x] Single-slot concurrency lock rejecting simultaneous runs with HTTP 429 (`Retry-After: 5`)
  - [x] String serialization for 64-bit integer values in SSE and REST JSON
  - [x] `GET /api/history` and `GET /api/runs/{id}`
  - [x] `GET /api/stats`
  - [x] `GET /api/health`
  - [x] `GET /api/examples`
- [x] Implement comprehensive API tests in `backend/tests/test_api.py` (55/55 tests passing)
- [ ] Commit & User Review (Tags handled by user; do not tag)
- [ ] **STOP AND REQUEST USER REVIEW**

---

## Phase 4: Frontend Development
- [x] Initialize Vite + React + TypeScript in `frontend/`
- [x] Configure Tailwind CSS, Framer Motion, and Lucide icons
- [x] Implement state management and SSE streaming hook `useRunStream`:
  - [x] UI handles HTTP 429 response with message 'previous run still finishing' and honors Retry-After header
- [x] Build UI Components:
  - [x] **Cyber-Lab Header**: Theme, local backend badge, LangSmith cloud warning badge
  - [x] **Command Center**: Expression input, presets, iteration slider, De-obfuscate action
  - [x] **Live Loop Graph (`@xyflow/react`)**: Interactive node glow, active state, animated counterexample packet
  - [x] **Attempt Timeline**: Collapsible reasoning cards, status badges, Z3 latency indicators
  - [x] **Counterexample Bit Visualizer**: 64-bit row diff highlighting mismatched bits
  - [x] **Proof & Compression Banner**: Green Z3 verified badge, honest red failure state, node reduction percentage
  - [x] **Explain Mode Overlay**: Tooltips for MBA, CEGIS, Bit-Vectors, and SMT solving
  - [x] **History & Insights Page**: Past run table and Recharts analytics (success rate, latency)
- [x] Root setup: `package.json` with `concurrently` running backend + frontend
- [x] Verify complete end-to-end loop with `fake` backend
- [ ] Commit & User Review (Tags handled by user; do not tag)
- [ ] **STOP AND REQUEST USER REVIEW**

---

## Phase 5: Real Model Integration (Ollama & llama-cpp)
- [x] Implement `backend/app/llm/ollama_backend.py` with error handling if daemon is unreachable
- [x] Implement `backend/app/llm/llamacpp_backend.py` with lazy loading and multi-threading
- [x] Create `Modelfile` with ChatML template and stop tokens matching teammate's training
- [x] Implement prompt format unit tests verifying exact character-for-character reproduction of training data
- [x] Update documentation with step-by-step model import instructions:
  - [x] `ollama create palimpsest -f Modelfile`
  - [x] Fallback instructions for `llama-cpp-python`
- [ ] Commit & User Review (Tags handled by user; do not tag)
- [ ] **STOP AND REQUEST USER REVIEW**

---

## Phase 6: Evaluation & Polish
- [ ] Generate representative `backend/data/samples.jsonl` with diverse MBA tiers and opaque predicates
- [ ] Implement `backend/eval/run_eval.py`:
  - [ ] Benchmark test suite on $N$ dataset rows
  - [ ] Metric calculations: success rate @ $K$ attempts, average attempts, average Z3 latency
  - [ ] Held-out evaluation mode for non-generator expressions
- [ ] Create root `README.md` with architectural overview, setup guides, and honest capability boundaries
- [ ] Create GitHub Actions CI workflow running backend tests and frontend build on push
- [ ] Final validation and smoke test across all backends
- [ ] Commit & Git Tag: `phase-6-complete`
- [ ] **FINAL REVIEW & PROJECT COMPLETION**

---

## Version Control Log

| Phase | Tag | Commit Hash | Summary |
| :--- | :--- | :--- | :--- |
| Phase 0 | `phase-0-plan` | `c43b1e6` | Repository initialization, .gitignore, ARCHITECTURE.md, TASKS.md |
| Phase 1 | `phase-1-complete` | `9eff72c` | AST safety gate, Z3 64-bit BitVec verifier, AST utils, test suite |
| Phase 2 | `phase-2-complete` | `78b2d5b` | LangGraph CEGIS loop, bounded witness verifier, semantic node counter, CLI demo |
