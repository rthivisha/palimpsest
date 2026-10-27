"""Unit tests for PALIMPSEST LLM Backends, Prompt Exactness, and Model Integration.

Verifies:
1. Exact character-for-character reproduction of teammate's fine-tuning dataset format.
2. Ollama backend streaming, error handling (unreachable daemon, timeouts), and cancellation.
3. llama-cpp-python backend lazy loading, model file existence checks, and cancellation.
4. Backend factory instantiation and error handling.
"""
import io
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from backend.app.llm.base import BaseLLMBackend, LLMBackendError
from backend.app.llm.factory import get_backend
from backend.app.llm.fake import FakeLLMBackend
from backend.app.llm.llamacpp_backend import LlamaCppBackend
from backend.app.llm.ollama_backend import OllamaBackend
from backend.app.llm.prompts import (
    PROMPT_PREFIX,
    build_messages,
    clean_expression_line,
    extract_candidate,
    extract_think,
    format_initial_prompt,
    format_z3_feedback,
    render_chatml_prompt,
)


class TestPromptFormatTrainingExact:
    """Verifies character-for-character reproduction of the teammate's training data."""

    def test_initial_prompt_exact_prefix_and_newlines(self):
        """User prompt must match: 'De-obfuscate this 64-bit MBA expression:\\n{expr}'."""
        expr = "(x ^ y) + 2 * (x & y)"
        prompt = format_initial_prompt(expr)
        assert prompt == f"De-obfuscate this 64-bit MBA expression:\n{expr}"
        assert prompt.startswith("De-obfuscate this 64-bit MBA expression:\n")

    def test_z3_feedback_format_exact_match(self):
        """CEGIS feedback turn must match:

        Z3_VERIFICATION_FAILED: SAT
        Counterexample Witness: {'x': 1, 'y': 1}
        Expected: 2, Actual: 0
        """
        witness = {"x": 1, "y": 1}
        expected = 2
        actual = 0
        feedback = format_z3_feedback(witness=witness, expected=expected, actual=actual, status="SAT")

        expected_text = (
            "Z3_VERIFICATION_FAILED: SAT\n"
            "Counterexample Witness: {'x': 1, 'y': 1}\n"
            "Expected: 2, Actual: 0"
        )
        assert feedback == expected_text

    def test_z3_feedback_preserves_large_64bit_integers(self):
        """Integers > 2^53 - 1 must be formatted as raw Python integers without truncation."""
        witness = {"x": 18446744073709551615, "y": 9223372036854775808}
        expected = 18446744073709551615
        actual = 0
        feedback = format_z3_feedback(witness=witness, expected=expected, actual=actual, status="SAT")

        assert "18446744073709551615" in feedback
        assert "9223372036854775808" in feedback
        # Assert no scientific notation
        assert "e+" not in feedback.lower()

    def test_multi_turn_message_builder_structure(self):
        """Verifies multi-turn message history format for the fine-tuned model."""
        history = [
            {
                "iteration": 1,
                "candidate": "x ^ y",
                "raw_output": "<think>\nEstimating reduction...\n</think>\nx ^ y",
                "status": "SAT",
                "witness": {"x": 1, "y": 1},
                "expected": 2,
                "actual": 0,
            }
        ]
        messages = build_messages(
            obfuscated_expr="(x ^ y) + 2 * (x & y)",
            history=history,
            tool_role="user",
        )
        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "De-obfuscate this 64-bit MBA expression:\n(x ^ y) + 2 * (x & y)"
        assert messages[1]["role"] == "assistant"
        assert "<think>" in messages[1]["content"]
        assert messages[2]["role"] == "user"
        assert "Z3_VERIFICATION_FAILED: SAT" in messages[2]["content"]

    def test_captured_messages_sent_to_backend_exact_match(self):
        """Captures messages actually passed from nodes.py to backend.generate and verifies exact match."""
        from backend.app.graph.nodes import make_propose_node

        captured_calls = []

        class SpyBackend(BaseLLMBackend):
            def generate(self, messages, temperature=0.2, max_tokens=512, should_cancel=None):
                captured_calls.append(list(messages))
                if len(captured_calls) == 1:
                    return "<think>\nAnalyzing MBA expression...\n</think>\n(x + y) - 1"
                return "<think>\nApplying counterexample repair...\n</think>\nx + y"

        backend = SpyBackend()
        propose_node = make_propose_node(backend)

        # Turn 1: Initial invocation
        state_t1 = {
            "obfuscated_expr": "(x ^ y) + 2 * (x & y)",
            "history": [],
            "temperature": 0.2,
        }
        res_t1 = propose_node(state_t1)
        assert res_t1["current_candidate"] == "(x + y) - 1"
        assert len(captured_calls) == 1

        # Turn 1 exact prompt comparison
        expected_t1_messages = [
            {
                "role": "user",
                "content": "De-obfuscate this 64-bit MBA expression:\n(x ^ y) + 2 * (x & y)",
            }
        ]
        assert captured_calls[0] == expected_t1_messages
        assert captured_calls[0][0]["content"] == "De-obfuscate this 64-bit MBA expression:\n(x ^ y) + 2 * (x & y)"

        # Turn 2: Follow-up after Z3 counterexample feedback
        history_t2 = [
            {
                "iteration": 1,
                "candidate": "(x + y) - 1",
                "raw_output": "<think>\nAnalyzing MBA expression...\n</think>\n(x + y) - 1",
                "status": "SAT",
                "witness": {"x": 1, "y": 1},
                "expected": 2,
                "actual": 0,
            }
        ]
        state_t2 = {
            "obfuscated_expr": "(x ^ y) + 2 * (x & y)",
            "history": history_t2,
            "temperature": 0.2,
        }
        res_t2 = propose_node(state_t2)
        assert res_t2["current_candidate"] == "x + y"
        assert len(captured_calls) == 2

        # Turn 2 exact prompt comparison
        expected_t2_messages = [
            {
                "role": "user",
                "content": "De-obfuscate this 64-bit MBA expression:\n(x ^ y) + 2 * (x & y)",
            },
            {
                "role": "assistant",
                "content": "<think>\nAnalyzing MBA expression...\n</think>\n(x + y) - 1",
            },
            {
                "role": "user",
                "content": "Z3_VERIFICATION_FAILED: SAT\nCounterexample Witness: {'x': 1, 'y': 1}\nExpected: 2, Actual: 0",
            },
        ]
        assert captured_calls[1] == expected_t2_messages
        assert captured_calls[1][2]["content"] == (
            "Z3_VERIFICATION_FAILED: SAT\n"
            "Counterexample Witness: {'x': 1, 'y': 1}\n"
            "Expected: 2, Actual: 0"
        )

    def test_golden_string_rendered_2turn_chatml_both_backends(self):
        """Golden-string test verifying 2-turn rendered ChatML for Ollama and llama-cpp backends.

        Ensures character-for-character compliance with fine-tuning contract:
        - Starts strictly with `<|im_start|>user\\n` on index 0 (no leading whitespace or newline).
        - Exactly one newline after each `<|im_end|>`.
        - Ends with `<|im_start|>assistant\\n` priming generation.
        """
        history_t2 = [
            {
                "iteration": 1,
                "candidate": "(x + y) - 1",
                "raw_output": "<think>\nAnalyzing MBA expression...\n</think>\n(x + y) - 1",
                "status": "SAT",
                "witness": {"x": 1, "y": 1},
                "expected": 2,
                "actual": 0,
            }
        ]
        messages = build_messages(
            obfuscated_expr="(x ^ y) + 2 * (x & y)",
            history=history_t2,
            tool_role="user",
            system_prompt="",
            history_mode="last",
        )

        golden_2turn_chatml = (
            "<|im_start|>user\n"
            "De-obfuscate this 64-bit MBA expression:\n"
            "(x ^ y) + 2 * (x & y)<|im_end|>\n"
            "<|im_start|>assistant\n"
            "<think>\n"
            "Analyzing MBA expression...\n"
            "</think>\n"
            "(x + y) - 1<|im_end|>\n"
            "<|im_start|>user\n"
            "Z3_VERIFICATION_FAILED: SAT\n"
            "Counterexample Witness: {'x': 1, 'y': 1}\n"
            "Expected: 2, Actual: 0<|im_end|>\n"
            "<|im_start|>assistant\n"
        )

        rendered = render_chatml_prompt(messages)

        # 1. Exact character-for-character equality
        assert rendered == golden_2turn_chatml

        # 2. Assert no leading newline or leading whitespace
        assert rendered.startswith("<|im_start|>user\n")
        assert not rendered.startswith("\n")
        assert not rendered.startswith(" ")

        # 3. Assert exactly one newline after each <|im_end|>
        assert "<|im_end|>\n<|im_start|>" in rendered
        assert "<|im_end|>\n\n<|im_start|>" not in rendered
        assert "<|im_end|><|im_start|>" not in rendered

        # 4. Assert ends with assistant priming token
        assert rendered.endswith("<|im_start|>assistant\n")

    def test_configurable_repeated_candidate_temperature_bump(self):
        """Verifies configurable temperature bump on repeated candidate generation."""
        from backend.app.graph.nodes import make_propose_node

        mock_backend = MagicMock(spec=BaseLLMBackend)
        mock_backend.generate.return_value = "x + y"

        # Custom bump of 0.25
        node = make_propose_node(mock_backend, temp_retry_increment=0.25)
        state = {
            "obfuscated_expr": "x + y",
            "history": [{"iteration": 1, "candidate": "x + y"}],
            "temperature": 0.2,
        }
        res = node(state)
        assert res["temperature"] == 0.45  # 0.2 + 0.25

    def test_candidate_extraction_with_and_without_think(self):
        """Extracts simplified candidate following </think> accurately."""
        output_with_think = (
            "<think>\n"
            "Step 1: Fold Linear MBA identity back to canonical form.\n"
            "</think>\n"
            "x + y"
        )
        assert extract_think(output_with_think) == "Step 1: Fold Linear MBA identity back to canonical form."
        assert extract_candidate(output_with_think) == "x + y"

        # Model output with code backticks
        output_with_backticks = (
            "<think>\nReduction done.\n</think>\n"
            "```python\n"
            "`x + y`\n"
            "```"
        )
        assert extract_candidate(output_with_backticks) == "x + y"

        # Raw output without think block
        raw_output = "x + y"
        assert extract_think(raw_output) is None
        assert extract_candidate(raw_output) == "x + y"


class TestOllamaBackend:
    """Verifies Ollama HTTP backend streaming and error handling."""

    def test_ollama_daemon_unreachable_raises_descriptive_error(self):
        """Simulates daemon offline and verifies helpful instructions in error."""
        backend = OllamaBackend(base_url="http://127.0.0.1:59999", timeout=1.0)
        messages = [{"role": "user", "content": "hi"}]

        with pytest.raises(LLMBackendError) as exc_info:
            backend.generate(messages)

        err_msg = str(exc_info.value)
        assert "Ollama daemon unreachable" in err_msg
        assert "ollama serve" in err_msg
        assert "Modelfile" in err_msg

    def test_ollama_http_non_200_error(self):
        """Simulates Ollama returning HTTP 404 (model not found)."""
        backend = OllamaBackend(base_url="http://localhost:11434")

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.read.return_value = b'{"error": "model \'missing-model\' not found"}'

        with patch("httpx.Client.stream") as mock_stream:
            mock_stream.return_value.__enter__.return_value = mock_response
            with pytest.raises(LLMBackendError) as exc_info:
                backend.generate([{"role": "user", "content": "test"}])
            assert "HTTP 404" in str(exc_info.value)
            assert "model 'missing-model' not found" in str(exc_info.value)

    def test_ollama_streaming_success(self):
        """Verifies parsing of Ollama streaming chunks into full completion string."""
        backend = OllamaBackend(base_url="http://localhost:11434")

        chunks = [
            json.dumps({"message": {"content": "<think>\n"}, "done": False}),
            json.dumps({"message": {"content": "Simplifying MBA\n"}, "done": False}),
            json.dumps({"message": {"content": "</think>\n"}, "done": False}),
            json.dumps({"message": {"content": "x + y"}, "done": True}),
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = chunks

        with patch("httpx.Client.stream") as mock_stream:
            mock_stream.return_value.__enter__.return_value = mock_response
            result = backend.generate([{"role": "user", "content": "test"}])

        assert result == "<think>\nSimplifying MBA\n</think>\nx + y"
        mock_stream.assert_called_once()
        _, kwargs = mock_stream.call_args
        assert kwargs["json"]["options"]["num_predict"] == 512
        assert kwargs["json"]["keep_alive"] == "5m"

    def test_ollama_cooperative_cancellation_mid_stream(self):
        """Verifies inference halts at token boundary when should_cancel returns True."""
        backend = OllamaBackend(base_url="http://localhost:11434")

        chunks = [
            json.dumps({"message": {"content": "<think>\n"}, "done": False}),
            json.dumps({"message": {"content": "Token 1"}, "done": False}),
            json.dumps({"message": {"content": "Token 2"}, "done": False}),
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = chunks

        cancelled = False

        def should_cancel():
            nonlocal cancelled
            return cancelled

        # Set cancelled after first token
        def iter_with_cancel():
            nonlocal cancelled
            yield chunks[0]
            cancelled = True
            yield chunks[1]

        mock_response.iter_lines.side_effect = iter_with_cancel

        with patch("httpx.Client.stream") as mock_stream:
            mock_stream.return_value.__enter__.return_value = mock_response
            with pytest.raises(LLMBackendError) as exc_info:
                backend.generate([{"role": "user", "content": "test"}], should_cancel=should_cancel)
            assert "cancelled by client disconnect" in str(exc_info.value).lower()


class TestLlamaCppBackend:
    """Verifies llama-cpp-python lazy loading, validation, and cancellation."""

    def test_missing_llama_cpp_library_raises_descriptive_error(self):
        """If llama-cpp-python is not installed, raises LLMBackendError with pip instructions."""
        backend = LlamaCppBackend(model_path="models/test.gguf")

        with patch.dict("sys.modules", {"llama_cpp": None}):
            # Ensure no cached model
            LlamaCppBackend._cached_llm = None
            LlamaCppBackend._cached_model_path = None
            with pytest.raises(LLMBackendError) as exc_info:
                backend.generate([{"role": "user", "content": "test"}])
            err_msg = str(exc_info.value)
            assert "llama-cpp-python is not installed" in err_msg
            assert "pip install llama-cpp-python" in err_msg

    def test_missing_model_file_raises_error(self, tmp_path):
        """If model file does not exist, raises descriptive error."""
        non_existent_model = str(tmp_path / "does_not_exist.gguf")
        backend = LlamaCppBackend(model_path=non_existent_model)

        LlamaCppBackend._cached_llm = None
        LlamaCppBackend._cached_model_path = None

        # Mock successful llama_cpp import
        mock_llama_mod = MagicMock()
        with patch.dict("sys.modules", {"llama_cpp": mock_llama_mod}):
            with pytest.raises(LLMBackendError) as exc_info:
                backend._ensure_model_loaded()
            assert "GGUF model file not found" in str(exc_info.value)
            assert non_existent_model in str(exc_info.value)

    def test_llamacpp_passes_num_predict_config(self, tmp_path):
        """LlamaCppBackend passes configured num_predict (512) to create_chat_completion."""
        model_file = tmp_path / "model.gguf"
        model_file.write_text("dummy")

        backend = LlamaCppBackend(model_path=str(model_file), num_predict=512)
        mock_llm = MagicMock()
        mock_llm.create_chat_completion.return_value = [{"choices": [{"delta": {"content": "x + y"}}]}]

        with patch.object(backend, "_ensure_model_loaded", return_value=mock_llm):
            res = backend.generate([{"role": "user", "content": "simplify"}])

        assert res == "x + y"
        mock_llm.create_chat_completion.assert_called_once()
        _, kwargs = mock_llm.create_chat_completion.call_args
        assert kwargs["max_tokens"] == 512

    def test_llamacpp_cancellation_mid_stream(self, tmp_path):
        """Verifies llama-cpp streaming cancels when should_cancel is set."""
        fake_model = tmp_path / "model.gguf"
        fake_model.write_bytes(b"GGUF")

        backend = LlamaCppBackend(model_path=str(fake_model))
        LlamaCppBackend._cached_llm = None

        mock_llm = MagicMock()
        mock_chunks = [
            {"choices": [{"delta": {"content": "<think>\n"}}]},
            {"choices": [{"delta": {"content": "simplifying"}}]},
        ]
        mock_llm.create_chat_completion.return_value = iter(mock_chunks)

        with patch.object(backend, "_ensure_model_loaded", return_value=mock_llm):
            cancelled = True
            with pytest.raises(LLMBackendError) as exc_info:
                backend.generate(
                    [{"role": "user", "content": "test"}],
                    should_cancel=lambda: cancelled,
                )
            assert "cancelled by client disconnect" in str(exc_info.value).lower()


class TestBackendFactory:
    """Verifies backend factory behavior."""

    def test_factory_returns_expected_backends(self):
        fake = get_backend("fake")
        assert isinstance(fake, FakeLLMBackend)

        ollama = get_backend("ollama")
        assert isinstance(ollama, OllamaBackend)

        llamacpp = get_backend("llamacpp")
        assert isinstance(llamacpp, LlamaCppBackend)

    def test_factory_rejects_unknown_backend(self):
        with pytest.raises(ValueError) as exc_info:
            get_backend("nonexistent_backend")
        assert "Unknown model backend" in str(exc_info.value)
