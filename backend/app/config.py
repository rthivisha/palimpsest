"""Application configuration settings for PALIMPSEST.

Uses pydantic-settings to read settings from environment variables and `.env`.
All defaults match the constraints outlined in the project brief.
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Model Backend Selection: "fake", "ollama", or "llamacpp"
    PALIMPSEST_BACKEND: str = "fake"
    # Optional fallback backend when primary is unreachable: e.g. "llamacpp"
    BACKEND_FALLBACK: Optional[str] = None

    # Ollama Backend Options
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "palimpsest"
    OLLAMA_KEEP_ALIVE: str = "5m"
    NUM_PREDICT: int = 512
    MODEL_WARMUP: bool = False

    # llama-cpp-python Options
    LLAMACPP_MODEL_PATH: str = "models/palimpsest-q4_k_m.gguf"
    LLAMACPP_N_THREADS: int = os.cpu_count() or 4

    # Formal Verification Limits
    Z3_TIMEOUT_MS: int = 3000
    MAX_ITERATIONS: int = 5
    SHIFT_SEMANTICS: str = "z3"  # "z3" (default: shift >= 64 is 0) or "x86_mask" (shift & 63)
    RSHIFT_SEMANTICS: str = "logical"  # "logical" (default: 0-fill LShR) or "arithmetic" (z3py >> sign-extend)
    WITNESS_POLICY: str = "z3_default"  # "z3_default" (default: raw Z3 model) or "bounded" (try [2, 16] first)
    MODEL_TIMEOUT_SECONDS: int = 30

    # AST Complexity and Safety Limits
    MAX_AST_DEPTH: int = 100
    MAX_EXPR_CHARS: int = 5000

    # [CONFIRM] Items & Tunables
    PROMPT_PROFILE: str = "unsloth_qwen25"  # "unsloth_qwen25" (default for ollama/llamacpp) or "plain" (default for fake)
    # Role used for the Z3 feedback turn: "user" (default) or "tool"
    TOOL_ROLE: str = "user"
    # System prompt (default empty; Qwen default system prompt is suppressed if empty)
    SYSTEM_PROMPT: str = ""
    # History replay mode: "last" (replay only latest failure) or "all"
    HISTORY_MODE: str = "last"
    # Temperature bump applied if model proposes an identical candidate twice
    TEMP_RETRY_INCREMENT: float = 0.1

    # Optional LangSmith Tracing
    LANGSMITH_TRACING: bool = False
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_API_KEY: Optional[str] = None
    LANGSMITH_PROJECT: str = "palimpsest"

    # Telemetry Database
    DATABASE_PATH: str = "palimpsest.sqlite"

    # API Server
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Global settings singleton
settings = Settings()

