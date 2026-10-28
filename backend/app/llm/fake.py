"""Scripted Fake LLM Backend for development, tests, and offline demos.

Why this module exists:
To allow building, unit-testing, and demonstrating the entire LangGraph loop
and UI without requiring an active Ollama service, GPU, or model weights.

Stateless behavior:
- On initial turn (1 user prompt in context): proposes `x ^ y` (a near-miss guess).
- On retry turn (Z3 failure witness in context): proposes `x + y` (the verified fix).
- Can also be initialized with custom sequence of guesses or an always-wrong candidate
  to verify loop termination on max iterations.
- Supports FAKE_SCENARIO env var: 'always_wrong', 'garbage', 'slow'.
"""
import os
import time
from typing import Callable, Dict, List, Optional
from backend.app.llm.base import BaseLLMBackend, LLMBackendError


DEFAULT_THINK_TURN1 = (
    "<think>\n"
    "AST Nodes: 9. Scanning expression for linear MBA expansions. "
    "Detected XOR and AND components. Estimating reduced candidate...\n"
    "</think>\n"
    "x ^ y"
)

DEFAULT_THINK_TURN2 = (
    "<think>\n"
    "Counterexample witness received. Discrepancy isolates evaluated bitwise operator. "
    "Restoring exact canonical linear MBA identity.\n"
    "</think>\n"
    "x + y"
)


class FakeLLMBackend(BaseLLMBackend):
    """Deterministic, scripted LLM backend that simulates realistic SLM completions."""

    def __init__(
        self,
        scripted_candidates: Optional[List[str]] = None,
        always_candidate: Optional[str] = None,
        custom_raw_outputs: Optional[List[str]] = None,
        scenario: Optional[str] = None,
    ):
        """
        Args:
            scripted_candidates: Optional explicit list of candidate expressions to return in order.
            always_candidate: If set, always returns this candidate on every call.
            custom_raw_outputs: Optional raw strings with custom <think> blocks to return in order.
            scenario: Optional scenario override ('always_wrong', 'garbage', 'slow'). If None, reads FAKE_SCENARIO env var.
        """
        self.scripted_candidates = scripted_candidates
        self.always_candidate = always_candidate
        self.custom_raw_outputs = custom_raw_outputs
        self.scenario = scenario
        self.call_count = 0

    def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 512,
        should_cancel: Optional[Callable[[], bool]] = None,
        seed: Optional[int] = None,
    ) -> str:
        """Returns scripted completion based on message count, scenario, or provided sequence."""
        if should_cancel and should_cancel():
            raise LLMBackendError("Inference cancelled by client disconnect")

        scenario = self.scenario or os.environ.get("FAKE_SCENARIO")

        # Handle 'slow' scenario: sleeps in 0.1s increments checking should_cancel
        if scenario == "slow":
            for _ in range(50):  # 5.0 seconds max
                if should_cancel and should_cancel():
                    raise LLMBackendError("Inference cancelled by client disconnect")
                time.sleep(0.1)

        self.call_count += 1

        # 1. Custom raw outputs take highest priority
        if self.custom_raw_outputs and len(self.custom_raw_outputs) >= self.call_count:
            return self.custom_raw_outputs[self.call_count - 1]

        # 2. Scenario-based outputs
        if scenario == "always_wrong":
            return (
                f"<think>\nAlways wrong candidate evaluation {self.call_count}...\n</think>\n"
                "x ^ y"
            )
        elif scenario == "garbage":
            return (
                f"<think>\nGenerating invalid syntax {self.call_count}...\n</think>\n"
                "def foo(): pass; 123"
            )

        # 3. Always candidate
        if self.always_candidate:
            return (
                f"<think>\nFake model candidate evaluation {self.call_count}...\n</think>\n"
                f"{self.always_candidate}"
            )

        # 4. Scripted sequence
        if self.scripted_candidates and len(self.scripted_candidates) >= self.call_count:
            cand = self.scripted_candidates[self.call_count - 1]
            return f"<think>\nProposing candidate {self.call_count}: {cand}\n</think>\n{cand}"

        # 5. Default 2-turn demo:
        # If messages list has no feedback turn, return turn 1 near miss: x ^ y
        # If messages list contains Z3 counterexample feedback, return turn 2 fix: x + y
        has_feedback = any("Z3_VERIFICATION_FAILED" in m.get("content", "") for m in messages)
        if not has_feedback:
            return DEFAULT_THINK_TURN1
        else:
            return DEFAULT_THINK_TURN2

