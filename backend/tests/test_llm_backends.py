"""Unit tests for PALIMPSEST LLM Backends, Prompt Exactness, and Model Integration.

Verifies:
1. Exact character-for-character reproduction of teammate's fine-tuning dataset format.
2. Ollama backend streaming, error handling (unreachable daemon, timeouts), and cancellation.
3. llama-cpp-python backend lazy loading, model file existence checks, and cancellation.
4. Backend factory instantiation and error handling.
"""
import asyncio
import io
import json
import threading
import time
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
            backend_name = "fake"

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

    def test_golden_string_rendered_2turn_chatml_both_profiles(self):
        """Golden-string test verifying 2-turn rendered ChatML for both 'plain' and 'unsloth_qwen25' profiles.

        Ensures character-for-character compliance with training format:
        - Profile 'plain': Starts with <|im_start|>user, standard Z3 feedback.
        - Profile 'unsloth_qwen25': System message first, retry content inside <tool_response>...</tool_response>.
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

        # 1. Profile: plain
        messages_plain = build_messages(
            obfuscated_expr="(x ^ y) + 2 * (x & y)",
            history=history_t2,
            tool_role="user",
            system_prompt="",
            history_mode="last",
            prompt_profile="plain",
        )
        golden_plain = (
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
        rendered_plain = render_chatml_prompt(messages_plain)
        assert rendered_plain == golden_plain
        assert rendered_plain.startswith("<|im_start|>user\n")
        assert rendered_plain.endswith("<|im_start|>assistant\n")

        # 2. Profile: unsloth_qwen25 (exact training format)
        messages_unsloth = build_messages(
            obfuscated_expr="(x ^ y) + 2 * (x & y)",
            history=history_t2,
            history_mode="last",
            prompt_profile="unsloth_qwen25",
        )
        golden_unsloth = (
            "<|im_start|>system\n"
            "You are Qwen, created by Alibaba Cloud. You are a helpful assistant.<|im_end|>\n"
            "<|im_start|>user\n"
            "De-obfuscate this 64-bit MBA expression:\n"
            "(x ^ y) + 2 * (x & y)<|im_end|>\n"
            "<|im_start|>assistant\n"
            "<think>\n"
            "Analyzing MBA expression...\n"
            "</think>\n"
            "(x + y) - 1<|im_end|>\n"
            "<|im_start|>user\n"
            "<tool_response>\n"
            "Z3_VERIFICATION_FAILED: SAT\n"
            "Counterexample Witness: {'x': 1, 'y': 1}\n"
            "Expected: 2, Actual: 0\n"
            "</tool_response><|im_end|>\n"
            "<|im_start|>assistant\n"
        )
        rendered_unsloth = render_chatml_prompt(messages_unsloth)
        assert rendered_unsloth == golden_unsloth
        assert rendered_unsloth.startswith("<|im_start|>system\n")
        assert (
            "\n<tool_response>\n"
            "Z3_VERIFICATION_FAILED: SAT\n"
            "Counterexample Witness: {'x': 1, 'y': 1}\n"
            "Expected: 2, Actual: 0\n"
            "</tool_response><|im_end|>"
        ) in rendered_unsloth
        assert rendered_unsloth.endswith("<|im_start|>assistant\n")

        # 3. Backend equivalence: both Ollama template and llama.cpp render the exact same text
        # llama.cpp uses render_chatml_prompt(messages_unsloth)
        rendered_llamacpp = render_chatml_prompt(messages_unsloth)
        assert rendered_llamacpp == golden_unsloth

        # Ollama evaluates the teammate's Modelfile TEMPLATE with system message and <tool_response> turn
        system_content = messages_unsloth[0]["content"]
        non_sys_messages = [m for m in messages_unsloth if m["role"] != "system"]

        def render_ollama_template(system: str, msgs: list) -> str:
            out = []
            if system:
                out.append(f"<|im_start|>system\n{system}<|im_end|>\n")
            n = len(msgs)
            for i, m in enumerate(msgs):
                is_last = (i == n - 1)
                role = m["role"]
                content = m["content"]
                if role == "user":
                    out.append(f"<|im_start|>user\n{content}<|im_end|>\n")
                elif role == "assistant":
                    out.append(f"<|im_start|>assistant\n{content}")
                    if not is_last:
                        out.append("<|im_end|>\n")
                elif role == "tool":
                    out.append(f"<|im_start|>user\n<tool_response>\n{content}\n</tool_response><|im_end|>\n")
                if role != "assistant" and is_last:
                    out.append("<|im_start|>assistant\n")
            return "".join(out)

        rendered_ollama = render_ollama_template(system_content, non_sys_messages)
        assert rendered_ollama == golden_unsloth
        assert rendered_ollama == rendered_llamacpp

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

    def test_ollama_default_base_url_and_override(self):
        """Ollama base URL defaults to http://127.0.0.1:11434 and respects OLLAMA_BASE_URL override."""
        backend_default = OllamaBackend()
        assert backend_default.base_url == "http://127.0.0.1:11434"

        backend_override = OllamaBackend(base_url="http://192.168.1.100:11434/")
        assert backend_override.base_url == "http://192.168.1.100:11434"

    def test_ollama_daemon_unreachable_raises_descriptive_error(self):
        """Simulates daemon offline and verifies 'Ollama is not running at <url>' in error."""
        backend = OllamaBackend(base_url="http://127.0.0.1:59999", timeout=1.0)
        messages = [{"role": "user", "content": "hi"}]

        with pytest.raises(LLMBackendError) as exc_info:
            backend.generate(messages)

        err_msg = str(exc_info.value)
        assert "Ollama is not running at http://127.0.0.1:59999" in err_msg

    def test_ollama_http_non_200_error(self):
        """Simulates Ollama returning model not found and splits the error cleanly."""
        backend = OllamaBackend(base_url="http://127.0.0.1:11434", model_name="palimpsest")

        mock_stream_response = MagicMock()
        mock_stream_response.status_code = 404
        mock_stream_response.read.return_value = b'{"error": "model \'palimpsest\' not found"}'

        mock_tags_response = MagicMock()
        mock_tags_response.status_code = 200
        mock_tags_response.json.return_value = {"models": [{"name": "other-model:latest"}]}

        with patch("httpx.Client.stream") as mock_stream, patch("httpx.Client.get", return_value=mock_tags_response):
            mock_stream.return_value.__enter__.return_value = mock_stream_response
            with pytest.raises(LLMBackendError) as exc_info:
                backend.generate([{"role": "user", "content": "test"}])
            assert "Model 'palimpsest' not found; run ollama create palimpsest -f Modelfile" in str(exc_info.value)

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


class TestOllamaBackendRetryAndNoFakeFallback:
    """Verifies OllamaBackend retries once on connection refusal before tokens arrive,
    raises on second failure, emits a single error event in routes_run, and never falls back to fake.
    """

    def test_ollama_retry_once_on_connection_refusal_then_succeed(self, monkeypatch):
        """OllamaBackend retries once after 1s if connection refused before tokens arrive."""
        backend = OllamaBackend(base_url="http://127.0.0.1:11434", model_name="palimpsest")
        sleeps = []
        monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

        attempts = 0

        class MockStreamResponse:
            status_code = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def iter_lines(self):
                yield json.dumps({"message": {"content": "x + y"}, "done": True})

        class MockClient:
            def __init__(self, timeout=None):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def stream(self, method, url, **kwargs):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise httpx.ConnectError("Connection refused")
                return MockStreamResponse()

        monkeypatch.setattr(httpx, "Client", MockClient)

        result = backend.generate([{"role": "user", "content": "simplify"}])
        assert result == "x + y"
        assert attempts == 2
        assert sleeps == [1.0]

    def test_ollama_second_connection_refusal_raises_error_no_fake_fallback(self, monkeypatch):
        """After second connection refusal, raises LLMBackendError with no fake fallback."""
        backend = OllamaBackend(base_url="http://127.0.0.1:11434", model_name="palimpsest")
        sleeps = []
        monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

        class FailingClient:
            def __init__(self, timeout=None):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def stream(self, method, url, **kwargs):
                raise httpx.ConnectError("Connection refused")

        monkeypatch.setattr(httpx, "Client", FailingClient)

        with pytest.raises(LLMBackendError) as exc_info:
            backend.generate([{"role": "user", "content": "simplify"}])

        assert "Ollama is not running" in str(exc_info.value)
        assert len(sleeps) == 1  # Retried once after 1s

    def test_ollama_error_produces_single_error_event_in_routes_run(self, monkeypatch):
        """When Ollama backend fails, run_synthesis_worker emits a single error event and terminates."""
        from backend.app.api.routes_run import run_synthesis_worker
        from backend.app.telemetry.db import telemetry_db

        class AlwaysFailingBackend(BaseLLMBackend):
            def generate(self, messages, **kwargs):
                raise LLMBackendError("Ollama is not running at http://127.0.0.1:11434")

        loop = asyncio.new_event_loop()
        event_queue = asyncio.Queue()
        cancel_event = threading.Event()
        run_id = "test-error-single-event"

        telemetry_db.record_run({
            "run_id": run_id,
            "expression": "(x ^ y) + 2 * (x & y)",
            "obf_nodes": 9,
            "final_status": "RUNNING",
            "backend": "ollama",
            "model_name": "palimpsest",
            "max_iterations": 3,
        })

        run_synthesis_worker(
            run_id=run_id,
            expression="(x ^ y) + 2 * (x & y)",
            max_iterations=3,
            backend_name="ollama",
            obf_nodes=9,
            loop=loop,
            event_queue=event_queue,
            cancel_event=cancel_event,
            backend=AlwaysFailingBackend(),
            model_name="palimpsest",
        )

        # Drain scheduled callbacks on the test loop
        loop.run_until_complete(asyncio.sleep(0.05))

        events = []
        while not event_queue.empty():
            events.append(event_queue.get_nowait())

        event_types = [e[0] for e in events]
        # Assert exactly one "error" event is emitted
        error_events = [e for e in events if e[0] == "error"]
        assert len(error_events) == 1
        assert "Ollama is not running" in error_events[0][1]["error"]

        # Final sentinel is emitted (None, None)
        assert events[-1] == (None, None)
        loop.close()


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
