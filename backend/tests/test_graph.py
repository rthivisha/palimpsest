"""Unit tests for LangGraph CEGIS loop, prompt construction, and candidate extraction.

Tests:
1. Prompt Builder & Candidate Extractor:
   - Prompts match the training format character-for-character.
   - Extracts candidate from <think> blocks and fallback cases.
   - Strips markdown code blocks and whitespace cleanly.
2. LangGraph Execution with Fake Backend:
   - Runs exactly 2 attempts for classic identity: x ^ y -> SAT, x + y -> UNSAT.
   - Successfully computes AST node reduction.
3. LangGraph Failure Path:
   - An always-wrong model terminates honestly with FAILED after max_iterations.
4. LangGraph Resilience:
   - Model emitting invalid syntax is handled as an INVALID attempt without crashing.
   - Malicious user input is halted immediately at parse_ast with REJECTED_UNSAFE.
"""
import pytest

from backend.app.core.outcomes import RunOutcome
from backend.app.graph.build import build_graph
from backend.app.graph.state import PalimpsestState
from backend.app.llm.fake import FakeLLMBackend
from backend.app.llm.prompts import (
    build_messages,
    extract_candidate,
    extract_think,
    format_initial_prompt,
    format_z3_feedback,
    PROMPT_PREFIX,
)


# ==============================================================================
# 1. Prompt Builder & Candidate Extractor Tests
# ==============================================================================

class TestPromptsAndExtraction:
    """Verifies that prompt generation matches training format and extraction is robust."""

    def test_initial_prompt_format(self):
        """Initial user turn must match training prefix character-for-character."""
        expr = "(x ^ y) + 2 * (x & y)"
        prompt = format_initial_prompt(expr)
        assert prompt == f"De-obfuscate this 64-bit MBA expression:\n{expr}"

    def test_z3_feedback_format(self):
        """Feedback turn must format witness, expected, and actual values exactly."""
        feedback = format_z3_feedback(
            witness={"x": 1, "y": 1},
            expected=2,
            actual=0,
            status="SAT",
        )
        expected_text = (
            "Z3_VERIFICATION_FAILED: SAT\n"
            "Counterexample Witness: {'x': 1, 'y': 1}\n"
            "Expected: 2, Actual: 0"
        )
        assert feedback == expected_text

    def test_build_messages_initial_turn(self):
        """First call produces a single user turn."""
        messages = build_messages(
            obfuscated_expr="x + y",
            history=[],
            tool_role="user",
        )
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "De-obfuscate this 64-bit MBA expression:\nx + y"

    def test_build_messages_with_retry_last_mode(self):
        """Retry messages include user prompt, assistant attempt, and feedback turn."""
        fake_history = [
            {
                "iteration": 1,
                "candidate": "x ^ y",
                "raw_output": "<think>Thinking...</think>\nx ^ y",
                "status": "SAT",
                "witness": {"x": 1, "y": 1},
                "expected": 2,
                "actual": 0,
            }
        ]
        messages = build_messages(
            obfuscated_expr="(x ^ y) + 2 * (x & y)",
            history=fake_history,
            tool_role="user",
            history_mode="last",
        )
        # Should have 3 turns: user, assistant, user (feedback)
        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "<think>Thinking...</think>\nx ^ y"
        assert messages[2]["role"] == "user"
        assert "Z3_VERIFICATION_FAILED: SAT" in messages[2]["content"]

    def test_build_messages_tool_role_override(self):
        """Setting tool_role='tool' assigns 'tool' to feedback turn."""
        fake_history = [
            {
                "iteration": 1,
                "candidate": "x ^ y",
                "raw_output": "x ^ y",
                "status": "SAT",
                "witness": {"x": 1},
                "expected": 2,
                "actual": 0,
            }
        ]
        messages = build_messages(
            obfuscated_expr="x + y",
            history=fake_history,
            tool_role="tool",
        )
        assert messages[-1]["role"] == "tool"

    def test_extract_candidate_with_think(self):
        """Extracts expression following </think> tag."""
        raw = "<think>\nStep 1: Simplify\n</think>\nx + y"
        assert extract_candidate(raw) == "x + y"
        assert extract_think(raw) == "Step 1: Simplify"

    def test_extract_candidate_without_think(self):
        """Extracts last line if </think> is absent."""
        raw = "Some reasoning notes\nx + y"
        assert extract_candidate(raw) == "x + y"
        assert extract_think(raw) is None

    def test_extract_candidate_with_markdown_backticks(self):
        """Strips markdown code fences and backticks."""
        raw1 = "<think>notes</think>\n`x + y`"
        assert extract_candidate(raw1) == "x + y"

        raw2 = "<think>notes</think>\n```python\nx + y\n```"
        assert extract_candidate(raw2) == "x + y"

    def test_extract_candidate_empty_handling(self):
        """Returns empty string on empty input."""
        assert extract_candidate("") == ""
        assert extract_candidate("   ") == ""


# ==============================================================================
# 2. LangGraph Execution Tests
# ==============================================================================

class TestLangGraphLoop:
    """Verifies the state machine transitions, CEGIS loop, and termination criteria."""

    def test_graph_success_flow_with_fake_backend(self):
        """Runs the standard 2-attempt CEGIS demo to proven UNSAT equivalence."""
        graph = build_graph(FakeLLMBackend())
        state: PalimpsestState = {
            "obfuscated_expr": "(x ^ y) + 2 * (x & y)",
            "max_iterations": 5,
            "iteration": 0,
            "history": [],
            "temperature": 0.2,
        }

        result = graph.invoke(state)

        # Must succeed with formal proof and node reduction (9 -> 3)
        assert result["final_status"] == "VERIFIED_EQUIVALENT"
        assert result["outcome"] == RunOutcome.VERIFIED.value
        assert result["final_expr"] == "x + y"
        assert result["obf_nodes"] == 9
        assert result["final_nodes"] == 3
        assert result["compression_pct"] == 66.67

        # Exactly 2 attempts: Attempt 1 was SAT, Attempt 2 was UNSAT
        history = result["history"]
        assert len(history) == 2
        assert history[0]["candidate"] == "x ^ y"
        assert history[0]["status"] == "SAT"
        # Assert demo witness is small (bounded by ULT(v, 16))
        assert history[0]["witness"] is not None
        assert all(0 <= val < 16 for val in history[0]["witness"].values())
        assert history[1]["candidate"] == "x + y"
        assert history[1]["status"] == "QF_BV_UNSAT_64BIT_VERIFIED"

    def test_graph_verified_not_simpler_when_candidate_nodes_not_smaller(self):
        """When candidate is proven equivalent but has equal or more AST nodes, outcome is verified-not-simpler."""
        # Original: x + y (3 nodes). Candidate: (x ^ y) + 2 * (x & y) (9 nodes)
        backend = FakeLLMBackend(always_candidate="(x ^ y) + 2 * (x & y)")
        graph = build_graph(backend)
        state: PalimpsestState = {
            "obfuscated_expr": "x + y",
            "max_iterations": 3,
            "iteration": 0,
            "history": [],
            "temperature": 0.2,
        }

        result = graph.invoke(state)
        assert result["final_status"] == "VERIFIED_EQUIVALENT"
        assert result["outcome"] == RunOutcome.VERIFIED_NOT_SIMPLER.value
        assert result["final_expr"] == "(x ^ y) + 2 * (x & y)"
        assert result["error_message"] == "Verified equivalent, but not simpler"

    def test_graph_fails_honestly_when_max_iterations_reached(self):
        """If model guesses incorrectly repeatedly, graph must terminate with failed-exhausted."""
        # Backend that always proposes wrong candidate "x ^ y"
        backend = FakeLLMBackend(always_candidate="x ^ y")
        graph = build_graph(backend)
        state: PalimpsestState = {
            "obfuscated_expr": "x + y",
            "max_iterations": 3,
            "iteration": 0,
            "history": [],
            "temperature": 0.2,
        }

        result = graph.invoke(state)

        assert result["final_status"] == "FAILED"
        assert result["outcome"] == RunOutcome.FAILED_EXHAUSTED.value
        assert result["final_expr"] is None
        assert result["compression_pct"] == 0.0
        assert len(result["history"]) == 3
        assert "No unverified answer accepted" in result["error_message"]

    def test_graph_handles_invalid_model_candidate_gracefully(self):
        """If model outputs syntax error, it counts as failed attempt without crashing."""
        # Attempt 1: invalid syntax "x +", Attempt 2: correct "x + y"
        backend = FakeLLMBackend(scripted_candidates=["x +", "x + y"])
        graph = build_graph(backend)
        state: PalimpsestState = {
            "obfuscated_expr": "(x ^ y) + 2 * (x & y)",
            "max_iterations": 5,
            "iteration": 0,
            "history": [],
            "temperature": 0.2,
        }

        result = graph.invoke(state)

        assert result["final_status"] == "VERIFIED_EQUIVALENT"
        assert result["outcome"] == RunOutcome.VERIFIED.value
        assert result["final_expr"] == "x + y"
        assert len(result["history"]) == 2
        assert result["history"][0]["status"] == "INVALID"
        assert result["history"][1]["status"] == "QF_BV_UNSAT_64BIT_VERIFIED"

    def test_graph_halts_immediately_on_malicious_user_input(self):
        """Unsafe inputs are rejected at parse_ast without reaching propose or verify."""
        backend = FakeLLMBackend()
        graph = build_graph(backend)
        state: PalimpsestState = {
            "obfuscated_expr": "__import__('os').system('calc')",
            "max_iterations": 5,
            "iteration": 0,
            "history": [],
            "temperature": 0.2,
        }

        result = graph.invoke(state)

        assert result["final_status"] == "REJECTED_UNSAFE"
        assert result["outcome"] == RunOutcome.REJECTED_UNSAFE.value
        assert len(result["history"]) == 0
        assert "Security Gate Rejection" in result["error_message"]

