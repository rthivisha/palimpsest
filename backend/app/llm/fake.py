"""Scripted Fake LLM Backend for development, tests, and offline demos.

Why this module exists:
To allow building, unit-testing, and demonstrating the entire LangGraph loop
and UI without requiring an active Ollama service, GPU, or model weights.

Stateless behavior:
- On initial turn (1 user prompt in context): proposes `x ^ y` (a near-miss guess).
- On retry turn (Z3 failure witness in context): proposes `x + y` (the provably equivalent fix).
- Can also be initialized with custom sequence of guesses or an always-wrong candidate
  to verify loop termination on max iterations.
"""
from typing import Dict, List, Optional
from backend.app.llm.base import BaseLLMBackend


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
    ):
        """
        Args:
            scripted_candidates: Optional explicit list of candidate expressions to return in order.
            always_candidate: If set, always returns this candidate on every call.
            custom_raw_outputs: Optional raw strings with custom <think> blocks to return in order.
        """
        self.scripted_candidates = scripted_candidates
        self.always_candidate = always_candidate
        self.custom_raw_outputs = custom_raw_outputs
        self.call_count = 0

    def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> str:
        """Returns scripted completion based on message count or provided sequence."""
        self.call_count += 1

        # 1. Custom raw outputs take highest priority
        if self.custom_raw_outputs and len(self.custom_raw_outputs) >= self.call_count:
            return self.custom_raw_outputs[self.call_count - 1]

        # 2. Always candidate
        if self.always_candidate:
            return (
                f"<think>\nFake model candidate evaluation {self.call_count}...\n</think>\n"
                f"{self.always_candidate}"
            )

        # 3. Scripted sequence
        if self.scripted_candidates and len(self.scripted_candidates) >= self.call_count:
            cand = self.scripted_candidates[self.call_count - 1]
            return f"<think>\nProposing candidate {self.call_count}: {cand}\n</think>\n{cand}"

        # 4. Default 2-turn demo:
        # If messages list only has user prompt (1 message), return turn 1 near miss: x ^ y
        # If messages list has feedback (>= 3 messages), return turn 2 fix: x + y
        if len(messages) <= 1:
            return DEFAULT_THINK_TURN1
        else:
            return DEFAULT_THINK_TURN2

