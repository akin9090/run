"""Tests for Phase 0 stub implementations of external service adapters."""

import unittest
from datetime import date
from pathlib import Path

from bootstrap.stub_services import (
    StubCodexAdapter,
    StubCommandExecutor,
    StubFableClient,
    StubHttpClient,
    StubHttpTransport,
)
from connector.http_client import HttpResponse
from executor.models import GeneratedTest, ImplementationContext, ModifiedFile, RepositoryInfo
from foundation.result import Result
from foundation.types import Design, Review
from github_manager.client import HttpResponse as GitHubHttpResponse
from tester.models import CommandExecutionResult
from weekly_reviewer.models import (
    BusinessAlignmentStatus,
    BusinessEvaluation,
    MvpEvaluation,
    ReviewPeriod,
    TechnicalDebtFinding,
    WeeklyAnalysis,
)


class StubCodexAdapterTest(unittest.TestCase):
    """StubCodexAdapter should satisfy CodexAdapter Protocol."""

    def test_generate_implementation_returns_result_with_tuple_of_modified_files(self) -> None:
        adapter = StubCodexAdapter()
        # Create a minimal context with required fields
        context = ImplementationContext(
            workflow_id="test-workflow-1",
            design_id="test-design-1",
            approved_design=Design(),
            design_document=Design(),
            project_context={},
            repository_information=RepositoryInfo(
                repository_id="test-repo",
                root_path=Path("/tmp/test"),
                default_branch="main",
            ),
        )
        result = adapter.generate_implementation(context)

        self.assertIsInstance(result, Result)
        self.assertTrue(result.success)
        self.assertIsInstance(result.value, tuple)
        # All elements should be ModifiedFile instances
        for item in result.value:
            self.assertIsInstance(item, ModifiedFile)

    def test_generate_tests_returns_result_with_tuple_of_generated_tests(self) -> None:
        adapter = StubCodexAdapter()
        context = ImplementationContext(
            workflow_id="test-workflow-1",
            design_id="test-design-1",
            approved_design=Design(),
            design_document=Design(),
            project_context={},
            repository_information=RepositoryInfo(
                repository_id="test-repo",
                root_path=Path("/tmp/test"),
                default_branch="main",
            ),
        )
        modified_files = (ModifiedFile(path=Path("stub.py"), change_type="created", summary="stub"),)

        result = adapter.generate_tests(context, modified_files)

        self.assertIsInstance(result, Result)
        self.assertTrue(result.success)
        self.assertIsInstance(result.value, tuple)
        # All elements should be GeneratedTest instances
        for item in result.value:
            self.assertIsInstance(item, GeneratedTest)


class StubCommandExecutorTest(unittest.TestCase):
    """StubCommandExecutor should satisfy CommandExecutor Protocol."""

    def test_run_returns_command_execution_result(self) -> None:
        executor = StubCommandExecutor()
        result = executor.run(["make", "build"], 60)

        self.assertIsInstance(result, CommandExecutionResult)
        self.assertEqual(result.exit_code, 0)
        self.assertIsInstance(result.stdout, str)
        self.assertIsInstance(result.stderr, str)
        self.assertIsInstance(result.duration_seconds, float)
        self.assertGreaterEqual(result.duration_seconds, 0)


class StubHttpTransportTest(unittest.TestCase):
    """StubHttpTransport should satisfy HttpTransport Protocol."""

    def test_request_returns_http_response(self) -> None:
        transport = StubHttpTransport()
        response = transport.request(
            "GET",
            "https://api.github.com/repos/example/example",
            {"Authorization": "Bearer token"},
            30.0,
        )

        self.assertIsInstance(response, GitHubHttpResponse)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json_body, dict)

    def test_request_with_different_methods(self) -> None:
        transport = StubHttpTransport()
        for method in ["GET", "POST", "PUT", "DELETE"]:
            response = transport.request(method, "https://api.github.com/repos/test/test", {}, 30.0)
            self.assertEqual(response.status_code, 200)


class StubHttpClientTest(unittest.TestCase):
    """StubHttpClient should satisfy HttpClient Protocol."""

    def test_request_returns_http_response(self) -> None:
        client = StubHttpClient()
        response = client.request(
            "POST",
            "https://slack.com/api/chat.postMessage",
            {"Content-Type": "application/json"},
            json_body={"text": "hello"},
        )

        self.assertIsInstance(response, HttpResponse)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json_body, dict)

    def test_request_with_all_parameters(self) -> None:
        client = StubHttpClient()
        response = client.request(
            "POST",
            "https://slack.com/api/files.upload",
            {"Content-Type": "multipart/form-data"},
            json_body={"text": "file"},
            files={"file": ("test.txt", b"content")},
        )

        self.assertEqual(response.status_code, 200)


class StubFableClientTest(unittest.TestCase):
    """StubFableClient should satisfy FableClient Protocol."""

    def _create_weekly_analysis(self) -> WeeklyAnalysis:
        """Helper to create a WeeklyAnalysis with required fields."""
        return WeeklyAnalysis(
            project_id="test-project",
            review_period=ReviewPeriod(start_date=date(2026, 7, 1), end_date=date(2026, 7, 8)),
            merged_pull_requests=[],
            pull_request_summaries=[],
        )

    def test_review_business_alignment_returns_result(self) -> None:
        client = StubFableClient()
        analysis = self._create_weekly_analysis()
        result = client.review_business_alignment("improve code quality", analysis)

        self.assertIsInstance(result, Result)
        self.assertTrue(result.success)
        self.assertIsInstance(result.value, BusinessEvaluation)

    def test_review_mvp_fitness_returns_result(self) -> None:
        client = StubFableClient()
        analysis = self._create_weekly_analysis()
        result = client.review_mvp_fitness(analysis)

        self.assertIsInstance(result, Result)
        self.assertTrue(result.success)
        self.assertIsInstance(result.value, MvpEvaluation)

    def test_review_technical_debt_returns_result(self) -> None:
        client = StubFableClient()
        analysis = self._create_weekly_analysis()
        reviews: list[Review] = []
        debt_reports: list[dict] = []
        result = client.review_technical_debt(analysis, reviews, debt_reports)

        self.assertIsInstance(result, Result)
        self.assertTrue(result.success)
        self.assertIsInstance(result.value, TechnicalDebtFinding)

    def test_recommend_priorities_returns_result_with_four_lists(self) -> None:
        client = StubFableClient()
        analysis = self._create_weekly_analysis()
        business_eval = BusinessEvaluation(business_goal="test", alignment_status=BusinessAlignmentStatus.ALIGNED)
        mvp_eval = MvpEvaluation()
        debt = TechnicalDebtFinding()

        result = client.recommend_priorities(analysis, business_eval, mvp_eval, debt)

        self.assertIsInstance(result, Result)
        self.assertTrue(result.success)
        self.assertIsInstance(result.value, tuple)
        self.assertEqual(len(result.value), 4)
        for item in result.value:
            self.assertIsInstance(item, list)


if __name__ == "__main__":
    unittest.main()
