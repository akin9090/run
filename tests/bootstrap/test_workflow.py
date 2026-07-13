"""合成Workflow(Planner→Architect→Design Auditor→Executor→Tester→PR Creator→
Reviewer)が最後まで直列に成功で流れることを検証する統合テスト。

外部サービスへの実接続は一切発生しない(すべてStub経由、`build_application()`の
既定配線をそのまま利用する)。
"""

import unittest
from pathlib import Path

from architect.models import ValidatedDesign
from bootstrap.adapters import (
    to_architect_execution_plan,
    to_executor_approved_design,
    to_executor_implementation_view,
)
from bootstrap.wiring import build_application
from bootstrap.workflow import run_workflow
from executor.models import RepositoryInfo
from planner.types import NormalizedRequest
from pr_creator.models import BranchInformation, CreatePullRequestInput, RepositoryInformation
from reviewer.domain import ReviewDecision


class RunWorkflowTest(unittest.TestCase):
    def test_synthetic_workflow_completes_through_reviewer(self) -> None:
        app = build_application()
        request = NormalizedRequest(
            workflow_id="wf-bootstrap-1",
            command="LP改善",
            request_text="LPの登録導線を改善してください。既存のデザインは維持すること。",
        )

        result = run_workflow(app, request, business_goal="LINE登録数最大化")

        self.assertTrue(result.success, msg=str(result.error))
        self.assertIsNotNone(result.value)
        outcome = result.value
        self.assertIsInstance(outcome.decision, ReviewDecision)
        self.assertIn(outcome.next_module, ("merge_manager", "executor"))
        self.assertTrue(outcome.review_id)

    def test_review_completed_notification_is_sent_to_configured_channel(self) -> None:
        app = build_application()
        request = NormalizedRequest(
            workflow_id="wf-bootstrap-notify",
            command="LP改善",
            request_text="LPの登録導線を改善してください。既存のデザインは維持すること。",
        )

        result = run_workflow(app, request, business_goal="LINE登録数最大化")

        self.assertTrue(result.success, msg=str(result.error))
        histories_result = app.notification._history_store.list_all()  # noqa: SLF001 - 配信確認のみ
        self.assertTrue(histories_result.success)
        self.assertTrue(
            any(h.workflow_id == "wf-bootstrap-notify" for h in histories_result.value),
            msg="review_completed通知がNotificationHistoryStoreに記録されていない",
        )


class RunWorkflowPrBodyTest(unittest.TestCase):
    """PR CreatorのCreatePullRequestInputへ渡す`implementation_result`が、Reviewerの
    要求(`.metadata`直接アクセス)とPR Creatorの要求(`.modified_files`)を同時に満たし、
    結果としてPR本文の"Changes"欄が空にならないことを検証する
    (2026-07 統合レビューで判明した不整合の是正の再発防止)。

    `run_workflow()`は最終`ReviewOutcome`のみを返しPR本文を公開しないため、
    `run_workflow()`と同一の手順(Planner→...→Executor→PR Creator)をこのテスト内で
    再現し、`app.pr_creator.create_pr()`が実際に返す`pull_request.metadata["body"]`を
    直接検証する。"""

    def test_pr_body_changes_section_contains_modified_files(self) -> None:
        app = build_application()
        request = NormalizedRequest(
            workflow_id="wf-bootstrap-pr-body",
            command="LP改善",
            request_text="LPの登録導線を改善してください。既存のデザインは維持すること。",
        )

        requirement_result = app.planner.analyze(request)
        self.assertTrue(requirement_result.success, msg=str(requirement_result.error))

        tasks_result = app.planner.create_tasks(requirement_result.value)
        self.assertTrue(tasks_result.success, msg=str(tasks_result.error))

        prioritized_result = app.planner.prioritize(tasks_result.value)
        self.assertTrue(prioritized_result.success, msg=str(prioritized_result.error))

        plan_result = app.planner.create_execution_plan(prioritized_result.value)
        self.assertTrue(plan_result.success, msg=str(plan_result.error))
        execution_plan = plan_result.value

        design_requirement_result = app.architect.analyze_plan(
            workflow_id=request.workflow_id,
            execution_plan=to_architect_execution_plan(execution_plan),
        )
        self.assertTrue(design_requirement_result.success, msg=str(design_requirement_result.error))

        design_result = app.architect.create_design(design_requirement_result.value)
        self.assertTrue(design_result.success, msg=str(design_result.error))
        design_document = design_result.value

        validation_result = app.architect.validate_design(design_document)
        self.assertTrue(validation_result.success, msg=str(validation_result.error))

        published_design_result = app.architect.publish_design(
            ValidatedDesign(design_document=design_document, validation_result=validation_result.value)
        )
        self.assertTrue(published_design_result.success, msg=str(published_design_result.error))
        published_design = published_design_result.value

        audit_report_result = app.design_auditor.audit(published_design)
        self.assertTrue(audit_report_result.success, msg=str(audit_report_result.error))
        audit_report = audit_report_result.value

        publish_outcome_result = app.design_auditor.publish_result(audit_report)
        self.assertTrue(publish_outcome_result.success, msg=str(publish_outcome_result.error))
        approved_design = publish_outcome_result.value

        context_result = app.executor.load_design(
            workflow_id=request.workflow_id,
            approved_design=to_executor_approved_design(approved_design),
            design_document=published_design,
            project_context={},
            repository_information=RepositoryInfo(
                repository_id="stub/repo",
                root_path=Path("/tmp/stub-repo"),
                default_branch="main",
            ),
        )
        self.assertTrue(context_result.success, msg=str(context_result.error))

        implementation_result = app.executor.implement(context_result.value)
        self.assertTrue(implementation_result.success, msg=str(implementation_result.error))
        implementation_result_value = implementation_result.value

        # Executorスタブ(bootstrap.stub_services.StubCodexAdapter)は常に"stub.py"を
        # 変更ファイルとして返す(2026-07 統合レビュー是正の検証対象そのもの)。
        self.assertTrue(implementation_result_value.modified_files)
        expected_changed_path = str(implementation_result_value.modified_files[0].path)
        self.assertEqual(expected_changed_path, "stub.py")

        test_result = app.tester.execute_tests(implementation_result_value.implementation)
        self.assertTrue(test_result.success, msg=str(test_result.error))

        quality_gate_result = app.tester.validate_quality(test_result.value)
        self.assertTrue(quality_gate_result.success, msg=str(quality_gate_result.error))

        test_report_result = app.tester.publish_report(quality_gate_result.value)
        self.assertTrue(test_report_result.success, msg=str(test_report_result.error))
        test_report = test_report_result.value

        pr_input = CreatePullRequestInput(
            workflow_id=request.workflow_id,
            implementation_result=to_executor_implementation_view(implementation_result_value),
            test_report=test_report,
            repository_information=RepositoryInformation(owner="stub", name="repo", default_branch="main"),
            branch_information=BranchInformation(base_branch="main", head_branch=f"bootstrap/{request.workflow_id}"),
            project_context={
                "design_document": published_design,
                "execution_plan": execution_plan,
                "audit_report": audit_report,
                "business_goal": "LINE登録数最大化",
            },
        )
        pr_result = app.pr_creator.create_pr(pr_input)
        self.assertTrue(pr_result.success, msg=str(pr_result.error))

        body = pr_result.value.metadata["body"]
        self.assertIn("## Changes", body)
        self.assertIn(expected_changed_path, body)
        self.assertNotIn("(変更ファイルなし)", body)

        # Reviewerが要求する`.metadata`直接アクセスも同時に満たせていることを確認する
        # (`ExecutorImplementationView`が両立させたい2つの契約の、もう片方)。
        review_report_result = app.reviewer.review(pr_result.value)
        self.assertTrue(review_report_result.success, msg=str(review_report_result.error))


if __name__ == "__main__":
    unittest.main()
