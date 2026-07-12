"""外部サービス(GitHub/Slack/Discord/Codex/Fable)への実接続を伴わない、
Phase 0(配線層検証)専用のスタブ実装。

すべて「常に成功するResult/適切なレスポンスを返す」ことのみを保証する。Phase 1で各スタブは
実サービス接続クラス(例: RealGitHubHttpTransport)へ個別に置き換える。
本番のShadow Mode/デモ用途にも流用できるが、実際の外部呼び出しは一切行わない。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from connector.http_client import HttpResponse
from executor.models import GeneratedTest, ImplementationContext, ModifiedFile
from foundation.logger import get_logger
from foundation.result import Result
from github_manager.client import HttpResponse as GitHubHttpResponse
from tester.models import CommandExecutionResult
from weekly_reviewer.fable_client import FableClient
from weekly_reviewer.models import (
    BusinessAlignmentStatus,
    BusinessEvaluation,
    MvpEvaluation,
    TechnicalDebtFinding,
    WeeklyAnalysis,
)

_logger = get_logger("bootstrap.stub_services")


class StubCodexAdapter:
    """Executor(M09)のCodexAdapter Protocolに準拠するスタブ。

    外部のCodex呼び出しは一切行わず、常に成功するResultを返す。
    """

    def generate_implementation(self, context: ImplementationContext) -> Result[tuple[ModifiedFile, ...]]:
        """設計内容に基づき実装コードを生成し、変更ファイル一覧を返す。"""
        _logger.info("stub_codex_generate_implementation")
        stub_file = ModifiedFile(
            path=Path("stub.py"),
            change_type="created",
            summary="stub generated implementation",
        )
        return Result(success=True, value=(stub_file,))

    def generate_tests(
        self, context: ImplementationContext, modified_files: tuple[ModifiedFile, ...]
    ) -> Result[tuple[GeneratedTest, ...]]:
        """生成済み実装に対応するテストコードを生成する。テストの実行は行わない。"""
        _logger.info("stub_codex_generate_tests files_count=%d", len(modified_files))
        stub_test = GeneratedTest(
            path=Path("test_stub.py"),
            target_path=Path("stub.py"),
            summary="stub generated test",
        )
        return Result(success=True, value=(stub_test,))


class StubCommandExecutor:
    """Tester(M10)のCommandExecutor Protocolに準拠するスタブ。

    外部コマンド実行は行わず、常に成功したCommandExecutionResultを返す。
    """

    def run(self, command: list[str], timeout_seconds: int) -> CommandExecutionResult:
        """外部コマンドを実行する(実装では常に成功)。"""
        _logger.info("stub_command_executor_run command_count=%d", len(command))
        return CommandExecutionResult(
            exit_code=0,
            stdout="stub output",
            stderr="",
            duration_seconds=0.1,
        )


class StubHttpTransport:
    """GitHub Manager(M20)のHttpTransport Protocolに準拠するスタブ。

    GitHub REST APIへの実接続は行わず、常に成功するHttpResponseを返す。
    """

    def request(self, method: str, url: str, headers: dict[str, str], timeout: float) -> GitHubHttpResponse:
        """HTTP リクエストを実行する(実装では常に成功)。"""
        _logger.info("stub_http_transport_request method=%s", method)
        return GitHubHttpResponse(
            status_code=200,
            json_body={"full_name": "stub/repo", "default_branch": "main"},
        )


class StubHttpClient:
    """Connector(M21)のHttpClient Protocolに準拠するスタブ。

    Slack/Discord APIへの実接続は行わず、常に成功するHttpResponseを返す。
    """

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> HttpResponse:
        """HTTP リクエストを実行する(実装では常に成功)。"""
        _logger.info("stub_http_client_request method=%s url=%s", method, url)
        return HttpResponse(
            status_code=200,
            json_body={"ok": True},
        )


class StubFableClient(FableClient):
    """Weekly Reviewer(M13)のFableClient抽象クラスに準拠するスタブ。

    Fableレビューエンジンへの実接続は行わず、常に成功するResultを返す。
    """

    def review_business_alignment(self, business_goal: str, weekly_analysis: WeeklyAnalysis) -> Result[BusinessEvaluation]:
        """設計書3.3節Business Goal評価。"""
        _logger.info("stub_fable_review_business_alignment goal_length=%d", len(business_goal))
        return Result(
            success=True,
            value=BusinessEvaluation(
                business_goal=business_goal,
                alignment_status=BusinessAlignmentStatus.ALIGNED,
            ),
        )

    def review_mvp_fitness(self, weekly_analysis: WeeklyAnalysis) -> Result[MvpEvaluation]:
        """設計書3.3節MVP評価。"""
        _logger.info("stub_fable_review_mvp_fitness")
        return Result(
            success=True,
            value=MvpEvaluation(),
        )

    def review_technical_debt(
        self,
        weekly_analysis: WeeklyAnalysis,
        review_reports: list[Any],
        technical_debt_reports: list[dict],
    ) -> Result[TechnicalDebtFinding]:
        """設計書3.3節Technical Debt評価。"""
        _logger.info(
            "stub_fable_review_technical_debt review_count=%d debt_count=%d",
            len(review_reports),
            len(technical_debt_reports),
        )
        return Result(
            success=True,
            value=TechnicalDebtFinding(),
        )

    def recommend_priorities(
        self,
        weekly_analysis: WeeklyAnalysis,
        business_evaluation: BusinessEvaluation,
        mvp_evaluation: MvpEvaluation,
        technical_debt: TechnicalDebtFinding,
    ) -> Result[tuple[list[str], list[str], list[str], list[str]]]:
        """設計書3.3節Development Direction評価。戻り値は
        (achievements, risks, recommendations, top_priority_next_week)の順のタプル。"""
        _logger.info("stub_fable_recommend_priorities")
        return Result(
            success=True,
            value=([], [], [], []),
        )
