"""adaptersモジュールの単体テスト(Task 3)。

2026-07統合レビューで判明した、パイプライン間の既知の型不整合3件をそれぞれ検証する。

1. Planner `ExecutionPlan.id` ⇔ Architect `analyzer.py` が読む `execution_plan.plan_id`
   (`src/architect/analyzer.py` line 52, および `architect.models.ExecutionPlan` Protocol)
2. Design Auditor `ApprovedDesign`(metadata非保持)⇔ Executor `_validate_approval()` が読む
   `getattr(approved_design, "metadata", None)`(`src/executor/executor.py` line 170)
3. Executor `ImplementationResult`(外側、`modified_files`保持)⇔ Reviewer
   `reviewer.checks`(内側のFoundation `Implementation`の`.metadata`を直接属性アクセス)
   と PR Creator `pr_creator.template._changed_file_paths()`(外側の`modified_files`を
   要求)という、互いに相容れない2つの要求を同時に満たす必要がある不整合
   (Task 5レビューで判明。従来はReviewer側の要求のみを満たすため内側の`Implementation`
   だけを渡しており、PR本文の"Changes"欄が常に空になっていた)。

いずれも実際のソースコード(src/実装)を正として検証し、ダミーの属性追加は行わない(YAGNI)。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from architect.analyzer import analyze_plan
from bootstrap.adapters import (
    NotificationChannelConnectorBridge,
    to_architect_execution_plan,
    to_connector_outbound_message,
    to_executor_approved_design,
    to_executor_implementation_view,
)
from connector.connector import SlackDiscordConnector
from connector.types import DeliveryResult as ConnectorDeliveryResult
from connector.types import MessageContentType, Platform
from design_auditor.types import ApprovedDesign
from executor.executor import Executor
from executor.models import ExecutionReport, ImplementationResult, ModifiedFile, RepositoryInfo
from executor.repository_guard import RepositoryGuard
from foundation.errors import ExternalServiceError
from foundation.result import Result
from foundation.types import Design, Implementation
from foundation.utils import utc_now
from notification.errors import UnsupportedChannelError
from notification.types import Channel, EventType, NotificationMessage
from planner.types import ExecutionPlan
from pr_creator import template as pr_template
from reviewer import checks as reviewer_checks
from tests.connector.fakes import FakeConfigurationClient, FakeMessageAdapter
from tests.executor.fakes import FakeCodexAdapter


def _make_execution_plan(**overrides: object) -> ExecutionPlan:
    defaults: dict[str, object] = dict(
        id="plan-1",
        created_at=utc_now(),
        updated_at=utc_now(),
        metadata={},
        objective="LP改善",
        task_list=[],
        dependencies={},
        expected_output="改善後のLPドラフト",
    )
    defaults.update(overrides)
    return ExecutionPlan(**defaults)  # type: ignore[arg-type]


class ToArchitectExecutionPlanTest(unittest.TestCase):
    """`analyzer.py`が実際に読む属性(objective/task_list/plan_id/dependencies)を検証する。"""

    def test_wrapped_plan_exposes_plan_id_matching_source_id(self) -> None:
        plan = _make_execution_plan(id="plan-42")

        wrapped = to_architect_execution_plan(plan)

        self.assertEqual(wrapped.plan_id, "plan-42")
        self.assertEqual(wrapped.plan_id, plan.id)

    def test_wrapped_plan_exposes_objective_task_list_and_dependencies(self) -> None:
        plan = _make_execution_plan(
            objective="LP改善",
            task_list=["task-a", "task-b"],
            dependencies={"task-a": ["task-b"]},
        )

        wrapped = to_architect_execution_plan(plan)

        self.assertEqual(wrapped.objective, plan.objective)
        self.assertEqual(wrapped.task_list, plan.task_list)
        self.assertEqual(wrapped.dependencies, plan.dependencies)

    def test_wrapped_plan_exposes_expected_output_and_priority_for_protocol_conformance(
        self,
    ) -> None:
        """`architect.models.ExecutionPlan` Protocolは`expected_output`/`priority`も
        要求する(analyzer.py自体は現時点でこの2つを読まないが、analyze_plan()の型注釈上の
        契約であるため構造的に満たしておく)。"""
        plan = _make_execution_plan(expected_output="改善後のLPドラフト")

        wrapped = to_architect_execution_plan(plan)

        self.assertEqual(wrapped.expected_output, plan.expected_output)
        self.assertEqual(wrapped.priority, {})

    def test_to_architect_execution_plan_satisfies_real_analyze_plan(self) -> None:
        """ボーナス統合テスト: 実際に`architect.analyzer.analyze_plan()`を呼び出し、
        アダプタが本物の消費者を満たすことを直接証明する。"""
        plan = _make_execution_plan(
            objective="LP改善",
            task_list=["task-a"],
            dependencies={"task-a": ["task-b"]},
        )
        wrapped = to_architect_execution_plan(plan)

        result = analyze_plan(
            workflow_id="workflow-1",
            execution_plan=wrapped,
            knowledge=[],
            project_context=None,
            architecture_guidelines=None,
        )

        self.assertTrue(result.success)
        assert result.value is not None
        self.assertEqual(result.value.source_execution_plan_id, plan.id)
        self.assertEqual(result.value.constraints, ["task-a depends on task-b"])


class ToExecutorApprovedDesignTest(unittest.TestCase):
    """`_validate_approval()`が実際に読む`metadata`辞書(approval_status/design_id)を検証する。"""

    def test_wrapped_approved_design_exposes_approval_metadata(self) -> None:
        approved = ApprovedDesign(
            design_id="design-1",
            audit_id="audit-1",
            approved_at=utc_now(),
            comments=[],
        )

        wrapped = to_executor_approved_design(approved)

        self.assertEqual(wrapped.metadata["approval_status"], "approved")
        self.assertEqual(wrapped.metadata["design_id"], "design-1")

    def test_wrapped_approved_design_delegates_other_attributes_to_source(self) -> None:
        """metadata以外にexecutor.py側から将来アクセスされ得る属性
        (design_id/audit_id/approved_at/comments)も、sourceへ委譲して読めること。"""
        approved = ApprovedDesign(
            design_id="design-1",
            audit_id="audit-1",
            approved_at=utc_now(),
            comments=["LGTM"],
        )

        wrapped = to_executor_approved_design(approved)

        self.assertIs(wrapped.source, approved)
        self.assertEqual(wrapped.design_id, approved.design_id)
        self.assertEqual(wrapped.audit_id, approved.audit_id)
        self.assertEqual(wrapped.approved_at, approved.approved_at)
        self.assertEqual(wrapped.comments, approved.comments)

    def test_matches_executor_validate_approval_getattr_pattern(self) -> None:
        """`Executor._validate_approval()`と同一のgetattrパターンで直接検証する。"""
        approved = ApprovedDesign(
            design_id="design-1",
            audit_id="audit-1",
            approved_at=utc_now(),
            comments=[],
        )
        wrapped = to_executor_approved_design(approved)

        metadata = getattr(wrapped, "metadata", None) or {}
        self.assertEqual(metadata.get("approval_status"), "approved")
        self.assertEqual(metadata.get("design_id"), "design-1")

    def test_to_executor_approved_design_satisfies_real_load_design(self) -> None:
        """ボーナス統合テスト: 実際に`Executor.load_design()`を呼び出し、
        アダプタが承認検証(4.3)を通過することを直接証明する。"""
        design_document = Design(id="design-1")
        approved = ApprovedDesign(
            design_id="design-1",
            audit_id="audit-1",
            approved_at=utc_now(),
            comments=[],
        )
        wrapped = to_executor_approved_design(approved)
        executor = Executor(codex_adapter=FakeCodexAdapter(), repository_guard=RepositoryGuard())

        result = executor.load_design(
            workflow_id="workflow-1",
            approved_design=wrapped,
            design_document=design_document,
            project_context={},
            repository_information=RepositoryInfo(repository_id="repo-1", root_path=Path("."), default_branch="main"),
        )

        self.assertTrue(result.success)

    def test_to_executor_approved_design_rejects_mismatched_design_id(self) -> None:
        """design_document.idとapproved_design.design_idが不一致の場合は
        load_design()が失敗すること(委譲が正しく機能している裏付け)。"""
        design_document = Design(id="design-999")
        approved = ApprovedDesign(
            design_id="design-1",
            audit_id="audit-1",
            approved_at=utc_now(),
            comments=[],
        )
        wrapped = to_executor_approved_design(approved)
        executor = Executor(codex_adapter=FakeCodexAdapter(), repository_guard=RepositoryGuard())

        result = executor.load_design(
            workflow_id="workflow-1",
            approved_design=wrapped,
            design_document=design_document,
            project_context={},
            repository_information=RepositoryInfo(repository_id="repo-1", root_path=Path("."), default_branch="main"),
        )

        self.assertFalse(result.success)


def _make_implementation_result(**overrides: object) -> ImplementationResult:
    modified_files = overrides.pop("modified_files", None) or (
        ModifiedFile(path=Path("src/foo.py"), change_type="modified", summary="foo更新"),
        ModifiedFile(path=Path("src/bar.py"), change_type="created", summary="bar新規作成"),
    )
    implementation = overrides.pop("implementation", None) or Implementation(
        id="impl-1",
        created_at=utc_now(),
        updated_at=utc_now(),
        metadata={"summary": "LP改善", "design_deviations": ["逸脱A"]},
    )
    generated_tests = overrides.pop("generated_tests", None) or ()
    execution_report = overrides.pop("execution_report", None) or ExecutionReport(
        workflow_id="workflow-1",
        design_id="design-1",
        repository_id="repo-1",
        modified_files=modified_files,
        generated_tests=generated_tests,
        summary="2 file(s) modified, 0 test(s) generated.",
        created_at=utc_now(),
    )
    return ImplementationResult(
        implementation=implementation,
        modified_files=modified_files,
        generated_tests=generated_tests,
        execution_report=execution_report,
    )


class ToExecutorImplementationViewTest(unittest.TestCase):
    """`ExecutorImplementationView`(Task 5 レビュー是正)が、Reviewer
    `reviewer.checks`の要求(内側のFoundation `Implementation.metadata`への直接属性
    アクセス)と、PR Creator `pr_creator.template._changed_file_paths()`の要求(外側の
    `ImplementationResult.modified_files`)を同時に満たすことを検証する。"""

    def test_wrapped_view_exposes_metadata_delegated_from_inner_implementation(self) -> None:
        implementation_result = _make_implementation_result()

        wrapped = to_executor_implementation_view(implementation_result)

        self.assertEqual(wrapped.metadata, implementation_result.implementation.metadata)
        self.assertEqual(wrapped.metadata["summary"], "LP改善")

    def test_wrapped_view_exposes_modified_files_from_outer_implementation_result(self) -> None:
        implementation_result = _make_implementation_result()

        wrapped = to_executor_implementation_view(implementation_result)

        self.assertEqual(wrapped.modified_files, implementation_result.modified_files)
        self.assertEqual(len(wrapped.modified_files), 2)

    def test_inner_implementation_has_no_modified_files_attribute(self) -> None:
        """回帰防止: 内側のFoundation `Implementation`自体には`modified_files`が
        存在しないことを直接確認する(このため、内側だけを渡すとPR CreatorのChanges
        欄が常に空になっていた)。"""
        implementation_result = _make_implementation_result()

        self.assertIsNone(getattr(implementation_result.implementation, "modified_files", None))

    def test_matches_real_reviewer_checks_metadata_access_pattern(self) -> None:
        """ボーナス統合テスト: 実際の`reviewer.checks.check_mvp_compliance()`/
        `check_design_alignment()`(`implementation_result.metadata`への直接属性
        アクセス)を、モックなしでラップ済みビューに対して直接呼び出す。"""
        implementation_result = _make_implementation_result()
        wrapped = to_executor_implementation_view(implementation_result)

        mvp_assessment = reviewer_checks.check_mvp_compliance(wrapped)
        design_issues = reviewer_checks.check_design_alignment(design_document=None, implementation_result=wrapped)

        self.assertTrue(mvp_assessment.is_mvp_compliant)
        self.assertEqual(len(design_issues), 1)
        self.assertIn("逸脱A", design_issues[0].description)

    def test_matches_real_pr_creator_template_changed_file_paths(self) -> None:
        """ボーナス統合テスト: 実際の`pr_creator.template._changed_file_paths()`を、
        モックなしでラップ済みビューに対して直接呼び出す。"""
        implementation_result = _make_implementation_result()
        wrapped = to_executor_implementation_view(implementation_result)

        changed_paths = pr_template._changed_file_paths(wrapped)

        self.assertEqual(changed_paths, [str(Path("src/foo.py")), str(Path("src/bar.py"))])


def _make_notification_message(**overrides: object) -> NotificationMessage:
    defaults: dict[str, object] = dict(
        workflow_id="wf-001",
        event_type=EventType.PULL_REQUEST_CREATED,
        channel=Channel.SLACK,
        recipient="#dev-notifications",
        subject="Pull Request Created",
        body="実装が完了しました。PR #152 を作成しました。",
        template_id="pull_request_created",
    )
    defaults.update(overrides)
    return NotificationMessage(**defaults)  # type: ignore[arg-type]


class ToConnectorOutboundMessageTest(unittest.TestCase):
    """`to_connector_outbound_message()`が`NotificationMessage`を`OutboundMessage`へ
    正しく変換することを検証する。"""

    def test_maps_slack_channel_to_slack_platform(self) -> None:
        message = _make_notification_message(channel=Channel.SLACK)

        result = to_connector_outbound_message(message)

        self.assertTrue(result.success)
        assert result.value is not None
        self.assertEqual(result.value.platform, Platform.SLACK)

    def test_maps_discord_channel_to_discord_platform(self) -> None:
        message = _make_notification_message(channel=Channel.DISCORD)

        result = to_connector_outbound_message(message)

        self.assertTrue(result.success)
        assert result.value is not None
        self.assertEqual(result.value.platform, Platform.DISCORD)

    def test_uses_recipient_as_channel_id(self) -> None:
        message = _make_notification_message(recipient="#dev-notifications")

        result = to_connector_outbound_message(message)

        assert result.value is not None
        self.assertEqual(result.value.channel_id, "#dev-notifications")

    def test_combines_subject_and_body_as_text_and_defaults_content_type_to_text(self) -> None:
        message = _make_notification_message(
            subject="Pull Request Created",
            body="実装が完了しました。PR #152 を作成しました。",
        )

        result = to_connector_outbound_message(message)

        assert result.value is not None
        self.assertEqual(result.value.content_type, MessageContentType.TEXT)
        self.assertIn("Pull Request Created", result.value.text or "")
        self.assertIn("PR #152 を作成しました", result.value.text or "")

    def test_returns_unsupported_channel_error_for_email(self) -> None:
        message = _make_notification_message(channel=Channel.EMAIL)

        result = to_connector_outbound_message(message)

        self.assertFalse(result.success)
        self.assertIsInstance(result.error, UnsupportedChannelError)


class NotificationChannelConnectorBridgeTest(unittest.TestCase):
    """`NotificationChannelConnectorBridge`が Notification の`ChannelConnector`
    Protocol(`send(message: NotificationMessage) -> Result[bool]`)を、
    Connector(M21)の`SlackDiscordConnector`へ委譲することで満たすことを検証する。"""

    @staticmethod
    def _make_connector(deliver_result: Result[ConnectorDeliveryResult]) -> tuple[SlackDiscordConnector, FakeMessageAdapter]:
        slack_adapter = FakeMessageAdapter(Platform.SLACK, deliver_result=deliver_result)
        discord_adapter = FakeMessageAdapter(Platform.DISCORD, deliver_result=deliver_result)
        connector = SlackDiscordConnector(
            FakeConfigurationClient(),
            slack_adapter=slack_adapter,
            discord_adapter=discord_adapter,
        )
        return connector, slack_adapter

    def test_send_returns_true_when_connector_reports_delivered(self) -> None:
        delivery = ConnectorDeliveryResult(platform=Platform.SLACK, channel_id="#dev-notifications", delivered=True)
        connector, _ = self._make_connector(Result(success=True, value=delivery))
        bridge = NotificationChannelConnectorBridge(connector)
        message = _make_notification_message(channel=Channel.SLACK)

        result = bridge.send(message)

        self.assertTrue(result.success)
        self.assertTrue(result.value)

    def test_send_returns_false_when_connector_reports_not_delivered(self) -> None:
        delivery = ConnectorDeliveryResult(platform=Platform.SLACK, channel_id="#dev-notifications", delivered=False)
        connector, _ = self._make_connector(Result(success=True, value=delivery))
        bridge = NotificationChannelConnectorBridge(connector)
        message = _make_notification_message(channel=Channel.SLACK)

        result = bridge.send(message)

        self.assertTrue(result.success)
        self.assertFalse(result.value)

    def test_send_propagates_connector_failure_result(self) -> None:
        connector, _ = self._make_connector(Result(success=False, error=ExternalServiceError("boom")))
        bridge = NotificationChannelConnectorBridge(connector)
        message = _make_notification_message(channel=Channel.SLACK)

        result = bridge.send(message)

        self.assertFalse(result.success)
        self.assertIsInstance(result.error, ExternalServiceError)

    def test_send_returns_unsupported_channel_error_for_email_without_calling_connector(self) -> None:
        delivery = ConnectorDeliveryResult(platform=Platform.SLACK, channel_id="x", delivered=True)
        connector, slack_adapter = self._make_connector(Result(success=True, value=delivery))
        bridge = NotificationChannelConnectorBridge(connector)
        message = _make_notification_message(channel=Channel.EMAIL)

        result = bridge.send(message)

        self.assertFalse(result.success)
        self.assertIsInstance(result.error, UnsupportedChannelError)
        self.assertEqual(slack_adapter.deliver_calls, [])

    def test_send_delegates_to_real_slack_discord_connector_with_correct_outbound_message(self) -> None:
        """ボーナス統合テスト: 実際の`SlackDiscordConnector.send()`を呼び出し、
        Adapterへ渡される`OutboundMessage`の内容を直接検証する。"""
        delivery = ConnectorDeliveryResult(platform=Platform.SLACK, channel_id="#dev-notifications", delivered=True)
        connector, slack_adapter = self._make_connector(Result(success=True, value=delivery))
        bridge = NotificationChannelConnectorBridge(connector)
        message = _make_notification_message(
            channel=Channel.SLACK,
            recipient="#dev-notifications",
            subject="Pull Request Created",
            body="実装が完了しました。PR #152 を作成しました。",
        )

        result = bridge.send(message)

        self.assertTrue(result.success)
        self.assertEqual(len(slack_adapter.deliver_calls), 1)
        delivered_message = slack_adapter.deliver_calls[0]
        self.assertEqual(delivered_message.platform, Platform.SLACK)
        self.assertEqual(delivered_message.channel_id, "#dev-notifications")
        self.assertEqual(delivered_message.content_type, MessageContentType.TEXT)
        self.assertIn("PR #152 を作成しました", delivered_message.text or "")


if __name__ == "__main__":
    unittest.main()
