"""Codex外部呼び出しの実装(Phase 1-C): Anthropic Claude APIを呼び出す`CodexAdapter`実装。

`executor.codex_adapter.CodexAdapter` Protocolにのみ準拠し、Executor本体は
ここでAnthropic Claude APIを呼び出していることを知らない(Adapter Pattern, F00)。
HTTP通信は標準ライブラリ`urllib`のみを用い、外部SDK(`anthropic`パッケージ等)には
依存しない(GitHub Manager `UrllibHttpTransport`・Connector `UrllibHttpClient`と同じ方針)。

APIキーは`ConfigurationClient`経由(`executor.api_key`、Configuration.extra経由)でのみ
取得し、ログ・例外メッセージには一切含めない(6節)。モデル名は既存の"codex"カテゴリ
(`CodexConfig.model`)から取得する。`executor.models.ModifiedFile`/`GeneratedTest`はファイル内容を
持たないDomain Model(Design Freeze時点の既存定義)であるため、実際にファイル内容を
生成するのではなく、変更対象ファイルの一覧(path/change_type/summary)をClaude APIに
JSON形式で出力させる。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from executor.codex_adapter import CodexConfig
from executor.errors import CodexGenerationError
from executor.models import ChangeType, GeneratedTest, ImplementationContext, ModifiedFile
from foundation.errors import ConfigurationError, ExternalServiceError
from foundation.interfaces import ConfigurationClient
from foundation.logger import get_logger
from foundation.result import Result

__all__ = [
    "AnthropicHttpResponse",
    "AnthropicHttpTransport",
    "UrllibAnthropicHttpTransport",
    "ClaudeCodexAdapter",
]

# configuration_manager(M17)の7固定カテゴリ(system/github/slack/discord/codex/fable/
# monitoring)のうち"codex"は型付きdataclass(CodexConfig: model/timeout/max_retryのみ)で
# あり、api_keyのような追加キーを保持できない。そのためAPIキーはExecutor自身の
# module_name("executor")経由でConfiguration.extra(汎用キー・バリュー領域)から取得し、
# モデル名のみ既存の"codex"カテゴリから取得する(GitHub Manager/Connectorが自モジュール名で
# 秘匿情報を取得するのと同じ規約)。
_CODEX_CATEGORY_NAME = "codex"
_SECRET_MODULE_NAME = "executor"
_ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"
_ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_MODEL = "claude-opus-4-8"
_DEFAULT_TIMEOUT_SECONDS = 120
_DEFAULT_MAX_RETRY = 2
_MAX_TOKENS = 8192

_logger = get_logger("claude_codex_adapter")

_MODIFIED_FILES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "change_type": {"type": "string", "enum": [ChangeType.CREATED, ChangeType.MODIFIED]},
                    "summary": {"type": "string"},
                },
                "required": ["path", "change_type", "summary"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["files"],
    "additionalProperties": False,
}

_GENERATED_TESTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "target_path": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["path", "target_path", "summary"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["tests"],
    "additionalProperties": False,
}

_IMPLEMENTATION_SYSTEM_PROMPT = (
    "あなたはソフトウェア実装アシスタントです。与えられた設計内容(JSON)を分析し、"
    "実装のために変更すべきファイルの一覧を出力してください。各ファイルについて、"
    "リポジトリルートからの相対パス(path)、変更種別(created または modified)、"
    "変更内容の要約(summary)を含めてください。指定されたJSON Schemaに厳密に従い、"
    "スキーマ外の説明文は出力しないでください。"
)

_TESTS_SYSTEM_PROMPT = (
    "あなたはソフトウェアテスト設計アシスタントです。与えられた実装済みファイルの一覧を"
    "分析し、対応するテストコードのファイル一覧を出力してください。各テストについて、"
    "生成先の相対パス(path)、テスト対象ファイルの相対パス(target_path)、"
    "テスト内容の要約(summary)を含めてください。指定されたJSON Schemaに厳密に従ってください。"
)


@dataclass(frozen=True)
class AnthropicHttpResponse:
    """AnthropicHttpTransport呼び出しの結果。"""

    status_code: int
    json_body: Any


class AnthropicHttpTransport(Protocol):
    """Anthropic Claude APIへの低レベルHTTP通信を抽象化するProtocol。

    テストではこのProtocolを満たすフェイク実装を注入し、実際のネットワーク通信は行わない。
    """

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any] | None,
        timeout: float,
    ) -> AnthropicHttpResponse: ...


class UrllibAnthropicHttpTransport:
    """標準ライブラリ`urllib`のみを用いたAnthropic Claude APIへの既定HTTP実装。"""

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any] | None,
        timeout: float,
    ) -> AnthropicHttpResponse:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                response_body = response.read().decode("utf-8")
                parsed = json.loads(response_body) if response_body else {}
                return AnthropicHttpResponse(status_code=response.status, json_body=parsed)
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8")
            try:
                parsed = json.loads(response_body) if response_body else {}
            except json.JSONDecodeError:
                parsed = {"message": response_body}
            return AnthropicHttpResponse(status_code=exc.code, json_body=parsed)


class ClaudeCodexAdapter:
    """Claude API(Anthropic Messages API)を呼び出す`CodexAdapter`実装(Phase 1-C)。

    `CodexConfig`(モデル名・タイムアウト・リトライ回数)と`ConfigurationClient`経由の
    APIキー(`codex.api_key`)を保持する。APIキー自体はログ・例外メッセージに含めない。
    """

    def __init__(
        self,
        configuration_client: ConfigurationClient,
        codex_config: CodexConfig | None = None,
        transport: AnthropicHttpTransport | None = None,
    ) -> None:
        api_key_result = configuration_client.get(_SECRET_MODULE_NAME, "api_key")
        if not api_key_result.success or not api_key_result.value:
            raise ConfigurationError("executor.api_keyをConfigurationClientから取得できませんでした。")
        self._api_key = str(api_key_result.value)  # ログ・例外メッセージに含めない

        if codex_config is None:
            model_result = configuration_client.get(_CODEX_CATEGORY_NAME, "model")
            model = str(model_result.value) if model_result.success and model_result.value else _DEFAULT_MODEL
            codex_config = CodexConfig(model=model, timeout=_DEFAULT_TIMEOUT_SECONDS, max_retry=_DEFAULT_MAX_RETRY)
        self._config = codex_config
        self._transport = transport or UrllibAnthropicHttpTransport()

    def generate_implementation(self, context: ImplementationContext) -> Result[tuple[ModifiedFile, ...]]:
        """設計内容に基づき実装コードを生成し、変更ファイル一覧を返す。"""
        _logger.info("claude_codex_generate_implementation", extra={"design_id": context.design_id})
        try:
            payload = self._request_json(
                system_prompt=_IMPLEMENTATION_SYSTEM_PROMPT,
                user_content=self._build_implementation_prompt(context),
                schema=_MODIFIED_FILES_SCHEMA,
            )
        except Exception as exc:  # noqa: BLE001 - 外部呼び出し失敗を一律CodexGenerationErrorへ変換する
            wrapped = CodexGenerationError("Claude APIへの実装生成呼び出しに失敗しました")
            wrapped.__cause__ = exc
            return Result(success=False, error=wrapped)

        modified_files = tuple(
            ModifiedFile(
                path=Path(item["path"]),
                change_type=item["change_type"],
                summary=item["summary"],
            )
            for item in payload.get("files", [])
        )
        return Result(success=True, value=modified_files)

    def generate_tests(
        self, context: ImplementationContext, modified_files: tuple[ModifiedFile, ...]
    ) -> Result[tuple[GeneratedTest, ...]]:
        """生成済み実装に対応するテストコードを生成する。テストの実行は行わない。"""
        _logger.info(
            "claude_codex_generate_tests",
            extra={"design_id": context.design_id, "modified_file_count": len(modified_files)},
        )
        try:
            payload = self._request_json(
                system_prompt=_TESTS_SYSTEM_PROMPT,
                user_content=self._build_tests_prompt(context, modified_files),
                schema=_GENERATED_TESTS_SCHEMA,
            )
        except Exception as exc:  # noqa: BLE001 - 外部呼び出し失敗を一律CodexGenerationErrorへ変換する
            wrapped = CodexGenerationError("Claude APIへのテスト生成呼び出しに失敗しました")
            wrapped.__cause__ = exc
            return Result(success=False, error=wrapped)

        generated_tests = tuple(
            GeneratedTest(
                path=Path(item["path"]),
                target_path=Path(item["target_path"]),
                summary=item["summary"],
            )
            for item in payload.get("tests", [])
        )
        return Result(success=True, value=generated_tests)

    def verify_api_key(self) -> Result[bool]:
        """スモークテスト専用: モデル情報取得(読み取り専用・トークン消費なし)でAPIキーの疎通を確認する。

        `CodexAdapter` Protocolの対象外(実装生成のための呼び出しは行わない)。
        """
        url = f"{_ANTHROPIC_MODELS_URL}/{self._config.model}"
        try:
            response = self._transport.request("GET", url, self._headers(), None, self._config.timeout)
        except Exception as exc:  # noqa: BLE001 - ネットワークエラー等を一律Resultへ変換する
            return Result(success=False, error=ExternalServiceError(f"Claude Models APIへの疎通確認に失敗しました: {exc}"))
        if response.status_code >= 400:
            return Result(
                success=False,
                error=ExternalServiceError(f"Claude Models APIがエラーを返しました(status={response.status_code})"),
            )
        return Result(success=True, value=True)

    # -- 内部ヘルパー ---------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "content-type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
        }

    def _request_json(self, system_prompt: str, user_content: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Claude Messages APIを呼び出し、`output_config.format`で強制したJSONをdictとして返す。

        `max_retry`回まで再試行する。最終的に失敗した場合は例外を送出する
        (呼び出し元が`CodexGenerationError`へラップする)。
        """
        body = {
            "model": self._config.model,
            "max_tokens": _MAX_TOKENS,
            "system": system_prompt,
            "thinking": {"type": "adaptive"},
            "output_config": {
                "effort": "high",
                "format": {"type": "json_schema", "schema": schema},
            },
            "messages": [{"role": "user", "content": user_content}],
        }

        last_error: Exception = ExternalServiceError("Claude API呼び出しに失敗しました(不明なエラー)")
        attempts = max(1, self._config.max_retry + 1)
        for _ in range(attempts):
            try:
                response = self._transport.request(
                    "POST", _ANTHROPIC_MESSAGES_URL, self._headers(), body, self._config.timeout
                )
            except Exception as exc:  # noqa: BLE001 - ネットワークエラー等を再試行対象にする
                last_error = exc
                continue

            if response.status_code >= 500:
                last_error = ExternalServiceError(f"Claude APIがサーバエラーを返しました(status={response.status_code})")
                continue
            if response.status_code >= 400:
                error_message = ""
                if isinstance(response.json_body, dict):
                    error_message = response.json_body.get("error", {}).get("message", "")
                raise ExternalServiceError(f"Claude APIがエラーを返しました(status={response.status_code}): {error_message}")

            return self._parse_response(response.json_body)

        raise last_error

    @staticmethod
    def _parse_response(response_body: Any) -> dict[str, Any]:
        if not isinstance(response_body, dict):
            raise ExternalServiceError("Claude APIレスポンスの形式が不正です")
        if response_body.get("stop_reason") == "refusal":
            raise ExternalServiceError("Claude APIがrefusalを返しました")
        content_blocks = response_body.get("content", [])
        text = next((block.get("text", "") for block in content_blocks if block.get("type") == "text"), "")
        if not text:
            raise ExternalServiceError("Claude APIレスポンスにtextブロックが含まれていません")
        return json.loads(text)

    @staticmethod
    def _build_implementation_prompt(context: ImplementationContext) -> str:
        payload = {
            "workflow_id": context.workflow_id,
            "design_id": context.design_id,
            "design_document_metadata": context.design_document.metadata,
            "project_context": context.project_context,
            "repository": {
                "repository_id": context.repository_information.repository_id,
                "default_branch": context.repository_information.default_branch,
            },
            "execution_plan": context.execution_plan,
        }
        return json.dumps(payload, ensure_ascii=False, default=str)

    @staticmethod
    def _build_tests_prompt(context: ImplementationContext, modified_files: tuple[ModifiedFile, ...]) -> str:
        payload = {
            "workflow_id": context.workflow_id,
            "design_id": context.design_id,
            "modified_files": [
                {"path": str(f.path), "change_type": f.change_type, "summary": f.summary} for f in modified_files
            ],
            "project_context": context.project_context,
        }
        return json.dumps(payload, ensure_ascii=False, default=str)
