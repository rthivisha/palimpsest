"""Prompt construction and candidate extraction routines.

Why this module exists:
To achieve high accuracy with our fine-tuned Qwen model, the runtime messages
MUST reproduce the training dataset format character-for-character:

First user turn:
    De-obfuscate this 64-bit MBA expression:
    {expression}

Retry (CEGIS feedback) turn:
    Z3_VERIFICATION_FAILED: SAT
    Counterexample Witness: {'x': 1, 'y': 1}
    Expected: 2, Actual: 0

Candidate Extraction:
The model output format is:
    <think>
    [step-by-step reasoning]
    </think>
    <expression>
The candidate expression is extracted defensively as the last non-empty line
following the closing `</think>` tag.
"""
import re
from typing import Any, Dict, List, Optional

from backend.app.config import settings

PROMPT_PREFIX = "De-obfuscate this 64-bit MBA expression:\n"
QWEN25_DEFAULT_SYSTEM_MESSAGE = "You are Qwen, created by Alibaba Cloud. You are a helpful assistant."


def get_default_prompt_profile_for_backend(backend: Optional[Any] = None) -> str:
    """Returns the default prompt profile: unsloth_qwen25 for ollama/llamacpp, plain for fake."""
    b_name = ""
    if isinstance(backend, str):
        b_name = backend.lower().strip()
    elif backend is not None:
        b_name = getattr(backend, "backend_name", type(backend).__name__).lower().strip()
    elif settings.PALIMPSEST_BACKEND:
        b_name = settings.PALIMPSEST_BACKEND.lower().strip()

    if "fake" in b_name or "mock" in b_name or "stub" in b_name:
        return "plain"
    if "ollama" in b_name or "llama" in b_name:
        return "unsloth_qwen25"
    return getattr(settings, "PROMPT_PROFILE", "unsloth_qwen25")


def format_initial_prompt(expression: str) -> str:
    """Formats the first user turn matching training data format character-for-character."""
    return f"{PROMPT_PREFIX}{expression.strip()}"


def format_z3_feedback(
    witness: Optional[Dict[str, int]] = None,
    expected: Optional[int] = None,
    actual: Optional[int] = None,
    status: str = "SAT",
    error: Optional[str] = None,
) -> str:
    """Formats the Z3 counterexample feedback turn matching training format."""
    if status == "SAT":
        return (
            f"Z3_VERIFICATION_FAILED: SAT\n"
            f"Counterexample Witness: {witness or {}}\n"
            f"Expected: {expected}, Actual: {actual}"
        )
    clean_err = " ".join(str(error or "Verification failed").splitlines())[:200].strip()
    return f"Z3_VERIFICATION_FAILED: {status}\nError: {clean_err}"


def build_messages(
    obfuscated_expr: str,
    history: List[Dict[str, Any]],
    tool_role: str = "user",
    system_prompt: str = "",
    history_mode: str = "last",
    prompt_profile: Optional[str] = None,
    backend: Optional[Any] = None,
) -> List[Dict[str, str]]:
    """Builds the complete message history for the model backend.

    Args:
        obfuscated_expr: The original expression being de-obfuscated.
        history: List of past attempt dicts (each with candidate, raw_output, status, witness, expected, actual).
        tool_role: Role for the verification feedback turn ('user' or 'tool').
        system_prompt: Optional system message. If empty, uses profile default.
        history_mode: 'last' (default, matches training: only replay the latest failure)
                      or 'all' (appends all prior failure turns).
        prompt_profile: 'plain' or 'unsloth_qwen25' (defaults to unsloth_qwen25 for ollama/llamacpp, plain for fake).
        backend: Optional backend instance or backend name used to resolve profile default.

    Returns:
        List of message dictionaries matching ChatML expectations.
    """
    if prompt_profile and prompt_profile.strip():
        profile = prompt_profile.lower().strip()
    else:
        profile = get_default_prompt_profile_for_backend(backend)

    messages: List[Dict[str, str]] = []

    # 1. System Message
    if profile == "unsloth_qwen25":
        sys_msg = system_prompt.strip() if system_prompt and system_prompt.strip() else QWEN25_DEFAULT_SYSTEM_MESSAGE
        messages.append({"role": "system", "content": sys_msg})
    elif system_prompt and system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})

    # 2. Turn 1: Initial User Prompt
    messages.append({
        "role": "user",
        "content": format_initial_prompt(obfuscated_expr)
    })

    # If no prior attempts exist, return the initial 1-turn prompt
    if not history:
        return messages

    # Filter attempts that were failures (SAT, UNKNOWN, INVALID)
    failed_attempts = [
        att for att in history
        if att.get("status") != "QF_BV_UNSAT_64BIT_VERIFIED"
    ]
    if not failed_attempts:
        return messages

    # Determine which attempts to include
    if history_mode == "last":
        # Fine-tuning dataset only ever showed the single most recent failed attempt
        selected_attempts = [failed_attempts[-1]]
    else:
        selected_attempts = failed_attempts

    # Append assistant and feedback turns
    for att in selected_attempts:
        raw_output = att.get("raw_output") or att.get("candidate", "")
        # Assistant prior attempt turn
        messages.append({
            "role": "assistant",
            "content": raw_output
        })

        # Feedback turn
        witness = att.get("witness") or {}
        expected = att.get("expected")
        actual = att.get("actual")
        status = att.get("status", "SAT")
        error = att.get("error")
        feedback_text = format_z3_feedback(witness, expected, actual, status=status, error=error)

        if profile == "unsloth_qwen25":
            # Exact training format: user turn wrapped in <tool_response>...</tool_response>
            fb_content = f"<tool_response>\n{feedback_text}\n</tool_response>"
            messages.append({
                "role": "user",
                "content": fb_content
            })
        else:
            messages.append({
                "role": tool_role,
                "content": feedback_text
            })

    return messages


def extract_think(raw_output: str) -> Optional[str]:
    """Extracts the reasoning text inside the `<think>...</think>` block.

    Returns:
        The content between <think> and </think>, or None if tag is absent.
    """
    if not raw_output:
        return None
    match = re.search(r"<think>(.*?)</think>", raw_output, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def clean_expression_line(line: str) -> str:
    """Cleans a single expression line from markdown backticks or commentary."""
    stripped = line.strip()
    # Strip markdown backticks like `x + y`
    if stripped.startswith("`") and stripped.endswith("`"):
        stripped = stripped.strip("`").strip()
    # Remove leading comments or bullet points if present
    stripped = re.sub(r"^[-*#\s]+", "", stripped).strip()
    return stripped


def extract_candidate(raw_output: str) -> str:
    """Defensively extracts the candidate simplified expression from raw model output.

    Rules:
    1. If `</think>` is present, takes the text strictly following the last `</think>`.
    2. Identifies the LAST non-empty line of that text.
    3. Cleans any markdown code fences or backticks.
    4. If `</think>` is missing, defensively takes the last non-empty line of the output.

    Args:
        raw_output: The raw completion string from the model backend.

    Returns:
        The extracted candidate expression string.
    """
    if not raw_output or not isinstance(raw_output, str):
        return ""

    text = raw_output.strip()

    # Case A: Closing </think> tag is present
    if "</think>" in text:
        parts = text.split("</think>")
        post_think = parts[-1].strip()
        lines = [line.strip() for line in post_think.splitlines() if line.strip()]
        if lines:
            # Find the last non-empty line that isn't a markdown code fence like ```
            for candidate_line in reversed(lines):
                cleaned = clean_expression_line(candidate_line)
                if cleaned and not cleaned.startswith("```"):
                    return cleaned

    # Case B: Defensive fallback if </think> tag is missing or nothing was found after it
    # Strip any markdown code blocks
    text_no_fences = re.sub(r"```[a-zA-Z]*", "", text)
    lines = [line.strip() for line in text_no_fences.splitlines() if line.strip()]
    if lines:
        for candidate_line in reversed(lines):
            cleaned = clean_expression_line(candidate_line)
            if cleaned and not cleaned.startswith("<think"):
                return cleaned

    return ""


def render_chatml_prompt(messages: List[Dict[str, str]]) -> str:
    """Renders a list of messages into the standard ChatML prompt format.

    Matches both Ollama's Modelfile TEMPLATE and llama-cpp's chat template:
    - Starts strictly with `<|im_start|>` on the first character (no leading newline).
    - Exactly one newline after each `<|im_end|>`.
    - Ends with `<|im_start|>assistant\n` to prime the model completion.
    """
    parts: List[str] = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        parts.append(f"<|im_start|>{role}\n{content}<|im_end|>\n")
    parts.append("<|im_start|>assistant\n")
    return "".join(parts)

