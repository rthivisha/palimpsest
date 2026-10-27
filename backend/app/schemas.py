"""Pydantic schemas and serialization utilities for PALIMPSEST API."""
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class RunRequest(BaseModel):
    """Payload for POST /api/run initiating a de-obfuscation synthesis run."""
    expression: str = Field(
        ...,
        description="Scrambled 64-bit MBA expression to de-obfuscate.",
        max_length=5000,
    )
    max_iterations: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum synthesis attempts before terminating (1 to 10).",
    )
    backend: Optional[str] = Field(
        default=None,
        description="Override default backend ('fake', 'ollama', 'llamacpp').",
    )

    @field_validator("expression")
    @classmethod
    def validate_expression_non_empty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Expression cannot be empty or whitespace.")
        return s


def stringify_verification_values(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures all 64-bit integers in verification payloads are serialized as strings.

    Why this matters:
    JavaScript's Number type cannot safely represent integers greater than 2^53 - 1
    (9,007,199,254,740,991). 64-bit unsigned bit-vectors reach up to 18,446,744,073,709,551,615.
    Sending raw JSON numbers would silently truncate bits in the frontend browser.
    """
    clean = dict(data)
    if "witness" in clean and isinstance(clean["witness"], dict):
        clean["witness"] = {k: str(v) for k, v in clean["witness"].items()}
    if "expected" in clean and clean["expected"] is not None:
        clean["expected"] = str(clean["expected"])
    if "actual" in clean and clean["actual"] is not None:
        clean["actual"] = str(clean["actual"])
    return clean


def format_sse_event(event_type: str, data: Dict[str, Any]) -> str:
    """Formats an event dictionary into SSE wire protocol format:

    event: <event_type>
    data: <json_string>

    """
    json_str = json.dumps(data)
    return f"event: {event_type}\ndata: {json_str}\n\n"
