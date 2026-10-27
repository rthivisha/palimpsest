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
- [ ] Implement `backend/app/telemetry/db.py`:
  - [ ] SQLite initialization in WAL mode (`PRAGMA journal_mode=WAL`)
  - [ ] Asynchronous non-blocking write queue for `runs` and `attempts`
- [ ] Implement FastAPI application in `backend/app/main.py`:
  - [ ] CORS middleware (localhost only)
  - [ ] Threadpool execution for CPU-bound Z3/LLM operations
- [ ] Implement API routes:
  - [ ] `POST /api/run`: SSE event stream emitting `run_started`, `node_started`, `node_finished`, `proposal`, `verification`, `retry`, `final`, `error`
  - [ ] Client disconnect detection and task cancellation
  - [ ] `GET /api/history` and `GET /api/runs/{id}`
  - [ ] `GET /api/stats`
  - [ ] `GET /api/health`
  - [ ] `GET /api/examples`
- [ ] Implement API tests in `backend/tests/test_api.py` verifying SSE event ordering
- [ ] Commit & Git Tag: `phase-3-complete`
- [ ] **STOP AND REQUEST USER REVIEW**

---

## Phase 4: Frontend Development
- [ ] Initialize Vite + React + TypeScript in `frontend/`
- [ ] Configure Tailwind CSS, Framer Motion, and Lucide icons
- [ ] Implement state management and SSE streaming hook `useRunStream`
- [ ] Build UI Components:
  - [ ] **Cyber-Lab Header**: Theme, local backend badge, LangSmith cloud warning badge
  - [ ] **Command Center**: Expression input, presets, iteration slider, De-obfuscate action
  - [ ] **Live Loop Graph (`@xyflow/react`)**: Interactive node glow, active state, animated counterexample packet
  - [ ] **Attempt Timeline**: Collapsible reasoning cards, status badges, Z3 latency indicators
  - [ ] **Counterexample Bit Visualizer**: 64-bit row diff highlighting mismatched bits
  - [ ] **Proof & Compression Banner**: Green Z3 verified badge, honest red failure state, node reduction percentage
  - [ ] **Explain Mode Overlay**: Tooltips for MBA, CEGIS, Bit-Vectors, and SMT solving
  - [ ] **History & Insights Page**: Past run table and Recharts analytics (success rate, latency)
- [ ] Root setup: `package.json` with `concurrently` running backend + frontend
- [ ] Verify complete end-to-end loop with `fake` backend
- [ ] Commit & Git Tag: `phase-4-complete`
- [ ] **STOP AND REQUEST USER REVIEW**

---

## Phase 5: Real Model Integration (Ollama & llama-cpp)
- [ ] Implement `backend/app/llm/ollama_backend.py` with error handling if daemon is unreachable
- [ ] Implement `backend/app/llm/llamacpp_backend.py` with lazy loading and multi-threading
- [ ] Create `Modelfile` with ChatML template and stop tokens matching teammate's training
- [ ] Implement prompt format unit tests verifying exact character-for-character reproduction of training data
- [ ] Update documentation with step-by-step model import instructions:
  - [ ] `ollama create palimpsest -f Modelfile`
  - [ ] Fallback instructions for `llama-cpp-python`
- [ ] Commit & Git Tag: `phase-5-complete`
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
