"""ClaudeCodexAdapter(Phase 1-C)のテスト。実際のネットワーク通信は行わない。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from executor.claude_codex_adapter import AnthropicHttpResponse, ClaudeCodexAdapter
from executor.codex_adapter import CodexConfig
from executor.errors import CodexGenerationError
from foundation.errors import ConfigurationError
from foundation.interfaces import ConfigurationClient
from foundation.result import Result
from tests.executor.fakes import make_context

DEFAULT_API_KEY = "sk-ant-test-key-value"


class FakeConfigurationClient(ConfigurationClient):
    """固定の`executor.api_key`/`codex.model`を返すConfigurationClientのフェイク実装。"""

    def __init__(self, api_key: str | None = DEFAULT_API_KEY, model: str | None = None) -> None:
        self._api_key = api_key
        self._model = model

    def get(self, module_name: str, key: str) -> Result[Any]:
        if module_name == "executor" and key == "api_key":
            if self._api_key is None:
                return Result(success=False, error=ConfigurationError("api_key not set"))
            return Result(success=True, value=self._api_key)
        if module_name == "codex" and key == "model":
            if self._model is None:
                return Result(success=False, error=ConfigurationError("model not set"))
            return Result(success=True, value=self._model)
        return Result(success=False, error=ConfigurationError(f"unknown module/key: {module_name}.{key}"))


class FakeTransport:
    """AnthropicHttpTransport Protocolのフェイク実装。実際のネットワーク通信は行わない。"""

    def __init__(self, responses: list[AnthropicHttpResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str, dict[str, str], dict[str, Any] | None, float]] = []

    def request(
        self, method: str, url: str, headers: dict[str, str], body: dict[str, Any] | None, timeout: float
    ) -> AnthropicHttpResponse:
        self.calls.append((method, url, dict(headers), body, timeout))
        return self._responses.pop(0)


class RaisingTransport:
    """呼び出し時に例外を送出するAnthropicHttpTransportのフェイク実装(ネットワークエラー再現用)。"""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def request(
        self, method: str, url: str, headers: dict[str, str], body: dict[str, Any] | None, timeout: float
    ) -> AnthropicHttpResponse:
        raise self._exc


def _messages_response(payload: dict[str, Any]) -> AnthropicHttpResponse:
    return AnthropicHttpResponse(
        status_code=200,
        json_body={
            "content": [{"type": "text", "text": json.dumps(payload)}],
            "stop_reason": "end_turn",
        },
    )


class ClaudeCodexAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.context = make_context(self.tmp_root)

    def test_constructor_raises_configuration_error_when_api_key_missing(self) -> None:
        with self.assertRaises(ConfigurationError):
            ClaudeCodexAdapter(FakeConfigurationClient(api_key=None))

    def test_generate_implementation_returns_modified_files_parsed_from_response(self) -> None:
        transport = FakeTransport(
            [_messages_response({"files": [{"path": "src/foo.py", "change_type": "created", "summary": "add foo"}]})]
        )
        adapter = ClaudeCodexAdapter(FakeConfigurationClient(), transport=transport)

        result = adapter.generate_implementation(self.context)

        self.assertTrue(result.success)
        self.assertEqual(len(result.value), 1)
        self.assertEqual(result.value[0].path, Path("src/foo.py"))
        self.assertEqual(result.value[0].change_type, "created")
        self.assertEqual(result.value[0].summary, "add foo")

    def test_generate_implementation_sends_api_key_header_and_model(self) -> None:
        transport = FakeTransport([_messages_response({"files": []})])
        adapter = ClaudeCodexAdapter(
            FakeConfigurationClient(api_key="secret-value"),
            codex_config=CodexConfig(model="claude-opus-4-8", timeout=10, max_retry=0),
            transport=transport,
        )

        adapter.generate_implementation(self.context)

        method, url, headers, body, timeout = transport.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(headers["x-api-key"], "secret-value")
        self.assertEqual(body["model"], "claude-opus-4-8")

    def test_generate_tests_returns_generated_tests_parsed_from_response(self) -> None:
        transport = FakeTransport(
            [
                _messages_response(
                    {"tests": [{"path": "tests/test_foo.py", "target_path": "src/foo.py", "summary": "test foo"}]}
                )
            ]
        )
        adapter = ClaudeCodexAdapter(FakeConfigurationClient(), transport=transport)

        result = adapter.generate_tests(self.context, ())

        self.assertTrue(result.success)
        self.assertEqual(result.value[0].path, Path("tests/test_foo.py"))
        self.assertEqual(result.value[0].target_path, Path("src/foo.py"))

    def test_generate_implementation_returns_error_result_on_http_error_status(self) -> None:
        transport = FakeTransport(
            [AnthropicHttpResponse(status_code=401, json_body={"error": {"message": "invalid api key"}})]
        )
        adapter = ClaudeCodexAdapter(
            FakeConfigurationClient(),
            codex_config=CodexConfig(model="m", timeout=10, max_retry=0),
            transport=transport,
        )

        result = adapter.generate_implementation(self.context)

        self.assertFalse(result.success)
        self.assertIsInstance(result.error, CodexGenerationError)

    def test_generate_implementation_returns_error_result_on_refusal(self) -> None:
        transport = FakeTransport(
            [AnthropicHttpResponse(status_code=200, json_body={"content": [], "stop_reason": "refusal"})]
        )
        adapter = ClaudeCodexAdapter(
            FakeConfigurationClient(),
            codex_config=CodexConfig(model="m", timeout=10, max_retry=0),
            transport=transport,
        )

        result = adapter.generate_implementation(self.context)

        self.assertFalse(result.success)
        self.assertIsInstance(result.error, CodexGenerationError)

    def test_generate_implementation_retries_on_server_error_then_succeeds(self) -> None:
        transport = FakeTransport(
            [
                AnthropicHttpResponse(status_code=503, json_body={"error": {"message": "overloaded"}}),
                _messages_response({"files": []}),
            ]
        )
        adapter = ClaudeCodexAdapter(
            FakeConfigurationClient(),
            codex_config=CodexConfig(model="m", timeout=10, max_retry=1),
            transport=transport,
        )

        result = adapter.generate_implementation(self.context)

        self.assertTrue(result.success)
        self.assertEqual(len(transport.calls), 2)

    def test_generate_implementation_gives_up_after_max_retry_exhausted(self) -> None:
        transport = FakeTransport(
            [
                AnthropicHttpResponse(status_code=503, json_body={"error": {"message": "overloaded"}}),
                AnthropicHttpResponse(status_code=503, json_body={"error": {"message": "overloaded"}}),
            ]
        )
        adapter = ClaudeCodexAdapter(
            FakeConfigurationClient(),
            codex_config=CodexConfig(model="m", timeout=10, max_retry=1),
            transport=transport,
        )

        result = adapter.generate_implementation(self.context)

        self.assertFalse(result.success)
        self.assertEqual(len(transport.calls), 2)

    def test_generate_implementation_returns_error_result_on_network_exception(self) -> None:
        adapter = ClaudeCodexAdapter(
            FakeConfigurationClient(),
            codex_config=CodexConfig(model="m", timeout=10, max_retry=0),
            transport=RaisingTransport(TimeoutError("timed out")),
        )

        result = adapter.generate_implementation(self.context)

        self.assertFalse(result.success)
        self.assertIsInstance(result.error, CodexGenerationError)

    def test_verify_api_key_returns_true_on_200(self) -> None:
        transport = FakeTransport([AnthropicHttpResponse(status_code=200, json_body={"id": "claude-opus-4-8"})])
        adapter = ClaudeCodexAdapter(
            FakeConfigurationClient(),
            codex_config=CodexConfig(model="claude-opus-4-8", timeout=10, max_retry=0),
            transport=transport,
        )

        result = adapter.verify_api_key()

        self.assertTrue(result.success)
        self.assertTrue(result.value)
        method, url, headers, body, timeout = transport.calls[0]
        self.assertEqual(method, "GET")
        self.assertTrue(url.endswith("/claude-opus-4-8"))

    def test_verify_api_key_returns_false_on_error_status(self) -> None:
        transport = FakeTransport([AnthropicHttpResponse(status_code=401, json_body={"error": {"message": "invalid"}})])
        adapter = ClaudeCodexAdapter(
            FakeConfigurationClient(),
            codex_config=CodexConfig(model="m", timeout=10, max_retry=0),
            transport=transport,
        )

        result = adapter.verify_api_key()

        self.assertFalse(result.success)

    def test_does_not_log_api_key_or_project_context_secrets(self) -> None:
        secret = "sk-ant-super-secret-do-not-log"
        transport = FakeTransport([_messages_response({"files": []})])
        adapter = ClaudeCodexAdapter(
            FakeConfigurationClient(api_key=secret),
            codex_config=CodexConfig(model="m", timeout=10, max_retry=0),
            transport=transport,
        )
        context = make_context(self.tmp_root, project_context={"api_key": secret})

        with self.assertLogs("claude_codex_adapter", level="INFO") as captured:
            adapter.generate_implementation(context)

        combined_output = "\n".join(captured.output)
        self.assertNotIn(secret, combined_output)


if __name__ == "__main__":
    unittest.main()
