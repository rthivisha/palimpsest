"""Ollama LLM Backend for PALIMPSEST neurosymbolic de-obfuscation.

Interacts with a local Ollama daemon via its HTTP chat API (/api/chat).
Features:
- Streaming token consumption with cooperative client cancellation checks
  at each token boundary.
- Robust error handling for connection refusals, timeouts, and daemon errors.
- Automatic stop token and temperature configuration matching the teammate's
  fine-tuned model requirements.
"""
import json
import logging
from typing import Callable, Dict, List, Optional

import httpx

from backend.app.config import settings
from backend.app.llm.base import BaseLLMBackend, LLMBackendError

logger = logging.getLogger("palimpsest.llm.ollama")


class OllamaBackend(BaseLLMBackend):
    """Local LLM backend communicating with an Ollama daemon."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: Optional[float] = None,
        num_predict: Optional[int] = None,
        keep_alive: Optional[str] = None,
    ):
        """
        Args:
            base_url: Base URL for Ollama daemon (defaults to settings.OLLAMA_BASE_URL).
            model_name: Name of the Ollama model (defaults to settings.OLLAMA_MODEL).
            timeout: Inference timeout in seconds (defaults to settings.MODEL_TIMEOUT_SECONDS).
            num_predict: Maximum completion tokens (defaults to settings.NUM_PREDICT = 512).
            keep_alive: Model keep-alive window in memory (defaults to settings.OLLAMA_KEEP_ALIVE).
        """
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model_name = model_name or settings.OLLAMA_MODEL
        self.timeout = timeout if timeout is not None else float(settings.MODEL_TIMEOUT_SECONDS)
        self.num_predict = num_predict if num_predict is not None else settings.NUM_PREDICT
        self.keep_alive = keep_alive or settings.OLLAMA_KEEP_ALIVE

    def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> str:
        """Streams completion tokens from Ollama, checking for cancellation between tokens."""
        if should_cancel and should_cancel():
            raise LLMBackendError("Inference cancelled by client disconnect")

        effective_max_tokens = max_tokens if max_tokens is not None else self.num_predict

        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": temperature,
                "num_predict": effective_max_tokens,
                "num_ctx": 4096,
                "stop": ["<|im_end|>", "<|im_start|>"],
            },
        }

        generated_chunks: List[str] = []

        try:
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        error_body = response.read().decode("utf-8", errors="ignore")
                        # Distinguish model not found from other errors using /api/tags
                        try:
                            tags_resp = client.get(f"{self.base_url}/api/tags", timeout=2.0)
                            if tags_resp.status_code == 200:
                                models = [m.get("name", "") for m in tags_resp.json().get("models", [])]
                                found = any(self.model_name == m or m.startswith(f"{self.model_name}:") for m in models)
                                if not found or response.status_code == 404 or "not found" in error_body.lower():
                                    raise LLMBackendError(
                                        f"Model '{self.model_name}' not found; run ollama create {self.model_name} -f Modelfile"
                                    )
                        except LLMBackendError:
                            raise
                        except Exception:
                            pass

                        if response.status_code == 404 or "not found" in error_body.lower():
                            raise LLMBackendError(
                                f"Model '{self.model_name}' not found; run ollama create {self.model_name} -f Modelfile"
                            )
                        raise LLMBackendError(
                            f"Ollama returned HTTP {response.status_code}: {error_body.strip()}"
                        )

                    for line in response.iter_lines():
                        if should_cancel and should_cancel():
                            raise LLMBackendError("Inference cancelled by client disconnect")

                        if not line:
                            continue

                        try:
                            chunk_data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        content = chunk_data.get("message", {}).get("content", "")
                        if content:
                            generated_chunks.append(content)

                        if chunk_data.get("done", False):
                            break

        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise LLMBackendError(
                f"Ollama is not running at {self.base_url}"
            ) from exc
        except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as exc:
            raise LLMBackendError(
                f"Ollama inference timed out after {self.timeout}s. Error: {exc}"
            ) from exc
        except LLMBackendError:
            raise
        except Exception as exc:
            raise LLMBackendError(f"Unexpected error communicating with Ollama: {exc}") from exc

        return "".join(generated_chunks).strip()

