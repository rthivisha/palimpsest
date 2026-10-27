"""Base class and common interfaces for PALIMPSEST LLM backends.

All backends (fake, ollama, llama-cpp) implement this unified interface.
They accept standard ChatML-style message dictionaries:
    [{"role": "user" | "assistant" | "tool" | "system", "content": "..."}]
and return the raw completion string.
"""
from abc import ABC, abstractmethod
from typing import Dict, List


class LLMBackendError(Exception):
    """Raised when an LLM backend fails to generate or is unreachable."""
    pass


class BaseLLMBackend(ABC):
    """Abstract interface for local language model backends."""

    @abstractmethod
    def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> str:
        """Generates a completion given a sequence of ChatML-style messages.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            temperature: Sampling temperature (default 0.2 for low variance).
            max_tokens: Maximum tokens to generate (default 512).

        Returns:
            The raw model output string (including any <think> reasoning blocks).
        """
        pass

