"""llama-cpp-python Backend for direct GGUF inference in PALIMPSEST.

Features:
- Lazy loading: The `llama_cpp` module is only imported when this backend is
  instantiated or called, ensuring the rest of the application runs cleanly
  even if llama-cpp-python is not installed.
- Multi-threading: Leverages CPU core parallelism via `n_threads`.
- Singleton/Instance Model Caching: Avoids reloading multi-gigabyte GGUF weights
  between individual CEGIS iterations.
- Cooperative Cancellation: Checks `should_cancel()` on every token yielded
  by the streaming chat completion iterator.
"""
import logging
import os
from typing import Any, Callable, Dict, List, Optional

from backend.app.config import settings
from backend.app.llm.base import BaseLLMBackend, LLMBackendError

logger = logging.getLogger("palimpsest.llm.llamacpp")


class LlamaCppBackend(BaseLLMBackend):
    """Local LLM backend using llama-cpp-python for direct in-process GGUF inference."""

    _cached_llm: Optional[Any] = None
    _cached_model_path: Optional[str] = None

    def __init__(
        self,
        model_path: Optional[str] = None,
        n_threads: Optional[int] = None,
        n_ctx: int = 2048,
        num_predict: Optional[int] = None,
    ):
        """
        Args:
            model_path: Path to .gguf weights (defaults to settings.LLAMACPP_MODEL_PATH).
            n_threads: Number of CPU threads (defaults to settings.LLAMACPP_N_THREADS).
            n_ctx: Context window size in tokens (defaults to 2048).
            num_predict: Default max completion tokens (defaults to settings.NUM_PREDICT = 512).
        """
        self.model_path = model_path or settings.LLAMACPP_MODEL_PATH
        self.n_threads = n_threads or settings.LLAMACPP_N_THREADS
        self.n_ctx = n_ctx
        self.num_predict = num_predict if num_predict is not None else settings.NUM_PREDICT
        self._llm: Optional[Any] = None

    def _ensure_model_loaded(self) -> Any:
        """Lazily imports llama-cpp-python and loads the GGUF model into memory."""
        if (
            LlamaCppBackend._cached_llm is not None
            and LlamaCppBackend._cached_model_path == self.model_path
        ):
            self._llm = LlamaCppBackend._cached_llm
            return self._llm

        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise LLMBackendError(
                "llama-cpp-python is not installed. To use direct GGUF inference, install it via: "
                "pip install llama-cpp-python (or use Ollama by setting PALIMPSEST_BACKEND=ollama in .env)."
            ) from exc

        if not os.path.exists(self.model_path):
            raise LLMBackendError(
                f"GGUF model file not found at '{self.model_path}'. "
                f"Please place your .gguf model in models/ or update LLAMACPP_MODEL_PATH in .env."
            )

        try:
            logger.info(
                "Loading GGUF model from %s with %d threads...",
                self.model_path,
                self.n_threads,
            )
            self._llm = Llama(
                model_path=self.model_path,
                n_threads=self.n_threads,
                n_ctx=self.n_ctx,
                verbose=False,
            )
            LlamaCppBackend._cached_llm = self._llm
            LlamaCppBackend._cached_model_path = self.model_path
            return self._llm
        except Exception as exc:
            raise LLMBackendError(f"Failed to load GGUF model '{self.model_path}': {exc}") from exc

    def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
        seed: Optional[int] = None,
    ) -> str:
        """Generates completion via llama-cpp chat completion, checking cancellation per token."""
        if should_cancel and should_cancel():
            raise LLMBackendError("Inference cancelled by client disconnect")

        effective_max_tokens = max_tokens if max_tokens is not None else self.num_predict
        llm = self._ensure_model_loaded()

        try:
            kwargs = {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": effective_max_tokens,
                "stream": True,
                "stop": ["<|im_end|>", "<|im_start|>"],
            }
            if seed is not None:
                kwargs["seed"] = seed

            stream = llm.create_chat_completion(**kwargs)

            generated_chunks: List[str] = []
            for chunk in stream:
                if should_cancel and should_cancel():
                    raise LLMBackendError("Inference cancelled by client disconnect")

                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        generated_chunks.append(content)

            return "".join(generated_chunks).strip()
        except LLMBackendError:
            raise
        except Exception as exc:
            raise LLMBackendError(f"llama-cpp generation error: {exc}") from exc
