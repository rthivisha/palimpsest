"""Backend factory for instantiating the configured PALIMPSEST LLM backend."""
from typing import Optional

from backend.app.config import settings
from backend.app.llm.base import BaseLLMBackend
from backend.app.llm.fake import FakeLLMBackend
from backend.app.llm.llamacpp_backend import LlamaCppBackend
from backend.app.llm.ollama_backend import OllamaBackend


def is_llamacpp_available() -> bool:
    """Checks if llama_cpp package is importable and model GGUF exists on disk."""
    import os
    try:
        import llama_cpp  # noqa: F401
        return os.path.exists(settings.LLAMACPP_MODEL_PATH)
    except ImportError:
        return False


def get_backend(backend_name: Optional[str] = None) -> BaseLLMBackend:
    """Instantiates the requested LLM backend.

    Args:
        backend_name: "fake", "ollama", or "llamacpp". If None, defaults to settings.PALIMPSEST_BACKEND.

    Returns:
        Instance of BaseLLMBackend.

    Raises:
        ValueError: If backend_name is unrecognized.
    """
    name = (backend_name or settings.PALIMPSEST_BACKEND).lower().strip()
    if name == "fake":
        return FakeLLMBackend()
    elif name == "ollama":
        return OllamaBackend()
    elif name in ("llamacpp", "llama_cpp", "llama-cpp"):
        return LlamaCppBackend()
    else:
        raise ValueError(
            f"Unknown model backend: '{name}'. Supported backends are: 'fake', 'ollama', 'llamacpp'"
        )
