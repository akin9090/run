"""Planner→Architect→Design Auditor→Executor→Tester→PR Creator→Reviewerを
直列に呼び出す合成Workflow。Phase 0では外部サービスに一切接続しない
(Executor/Tester/PR CreatorはStub実装経由)。

各モジュールの入出力の型不整合は`bootstrap.adapters`のビュー/変換関数で吸収する
(Planner `ExecutionPlan.id` -> Architect `plan_id`、Design Auditor `ApprovedDesign`
-> Executor `metadata`)。`repository_information`/`branch_information`/
`project_context`のうち`business_goal`はいずれの前段モジュールも生成しないため、
この関数の引数として明示的に受け取り、この関数内で組み立てる。
"""

from __future__ import annotations

from pathlib import Path

from architect.models import ValidatedDesign
from bootstrap.adapters import (
    to_architect_execution_plan,
    to_executor_approved_design,
    to_executor_implementation_view,
)
from bootstrap.wiring import Application
from executor.models import RepositoryInfo
from foundation.logger import get_logger
from foundation.result import Result
from notification.types import Channel, EventType, NotificationEvent
from planner.types import NormalizedRequest
from pr_creator.models import BranchInformation, CreatePullRequestInput, RepositoryInformation
from reviewer.domain import ReviewOutcome

_logger = get_logger("bootstrap.workflow")


def run_workflow(app: Application, request: NormalizedRequest, business_goal: str) -> Result[ReviewOutcome]:
    """NormalizedRequestを起点に7モジュールを直列に呼び出し、ReviewOutcomeまで進める。

    `business_goal`は`planner.types.NormalizedRequest`にはフィールドが存在せず、
    かつPlanner/Architect/Design Auditor/Executor/Testerのいずれも生成しないため、
    Workflow全体の入力としてこの関数の引数で明示的に受け取る(PR Creatorの
    `project_context["business_goal"]`経由でReviewerまで引き継がれる)。

    いずれかのステップが失敗した場合は、その時点の`Result(success=False, error=...)`を
    そのまま返し、後続のステップは一切呼び出さない(短絡)。
    """
    # --- Planner (M06) ---
    requirement_result = app.planner.analyze(request)
    if not requirement_result.success:
        return Result(success=False, error=requirement_result.error)

    tasks_result = app.planner.create_tasks(requirement_result.value)
    if not tasks_result.success:
        return Result(success=False, error=tasks_result.error)

    prioritized_result = app.planner.prioritize(tasks_result.value)
    if not prioritized_result.success:
        return Result(success=False, error=prioritized_result.error)

    plan_result = app.planner.create_execution_plan(prioritized_result.value)
    if not plan_result.success:
        return Result(success=False, error=plan_result.error)
    execution_plan = plan_result.value

    # --- Architect (M07) ---
    design_requirement_result = app.architect.analyze_plan(
        workflow_id=request.workflow_id,
        execution_plan=to_architect_execution_plan(execution_plan),
    )
    if not design_requirement_result.success:
        return Result(success=False, error=design_requirement_result.error)

    design_result = app.architect.create_design(design_requirement_result.value)
    if not design_result.success:
        return Result(success=False, error=design_result.error)
    design_document = design_result.value

    validation_result = app.architect.validate_design(design_document)
    if not validation_result.success:
        return Result(success=False, error=validation_result.error)

    published_design_result = app.architect.publish_design(
        ValidatedDesign(design_document=design_document, validation_result=validation_result.value)
    )
    if not published_design_result.success:
        return Result(success=False, error=published_design_result.error)
    published_design = published_design_result.value

    # --- Design Auditor (M08) ---
    audit_report_result = app.design_auditor.audit(published_design)
    if not audit_report_result.success:
        return Result(success=False, error=audit_report_result.error)
    audit_report = audit_report_result.value

    publish_outcome_result = app.design_auditor.publish_result(audit_report)
    if not publish_outcome_result.success:
        return Result(success=False, error=publish_outcome_result.error)
    approved_design = publish_outcome_result.value

    # --- Executor (M09) ---
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
    if not context_result.success:
        return Result(success=False, error=context_result.error)

    implementation_result = app.executor.implement(context_result.value)
    if not implementation_result.success:
        return Result(success=False, error=implementation_result.error)
    implementation_result_value = implementation_result.value

    # --- Tester (M10) ---
    test_result = app.tester.execute_tests(implementation_result_value.implementation)
    if not test_result.success:
        return Result(success=False, error=test_result.error)

    quality_gate_result = app.tester.validate_quality(test_result.value)
    if not quality_gate_result.success:
        return Result(success=False, error=quality_gate_result.error)

    test_report_result = app.tester.publish_report(quality_gate_result.value)
    if not test_report_result.success:
        return Result(success=False, error=test_report_result.error)
    test_report = test_report_result.value

    # --- PR Creator (M11) ---
    # Reviewer(reviewer.checks)は`implementation_result.metadata`へ直接アクセスする
    # (executor.models.ImplementationResultではなく、その内側のFoundation
    # `Implementation`を期待する)。一方PR Creatorのtemplate.py `_changed_file_paths()`は
    # `modified_files`(外側のImplementationResultにのみ存在)を読むため、内側の
    # `Implementation`だけを渡すとPR本文の"Changes"欄が常に空になる。
    # `bootstrap.adapters.ExecutorImplementationView`で両方の要求を同時に満たす。
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
            "business_goal": business_goal,
        },
    )
    pr_result = app.pr_creator.create_pr(pr_input)
    if not pr_result.success:
        return Result(success=False, error=pr_result.error)

    # --- Reviewer (M12) ---
    review_report_result = app.reviewer.review(pr_result.value)
    if not review_report_result.success:
        return Result(success=False, error=review_report_result.error)

    review_outcome_result = app.reviewer.publish_review(review_report_result.value)
    if not review_outcome_result.success:
        return Result(success=False, error=review_outcome_result.error)

    _notify_review_completed(app, request.workflow_id, review_outcome_result.value)

    return review_outcome_result


def _notify_review_completed(app: Application, workflow_id: str, outcome: ReviewOutcome) -> None:
    """Reviewerの最終判断をNotification経由で人間に通知する(Phase 3 Shadow Mode)。

    通知の失敗はWorkflow全体の結果(`Result[ReviewOutcome]`)に影響させない
    (このヘルパーは戻り値を持たず、失敗時は警告ログのみ出力する)。
    """
    recipient_result = app.configuration_manager.get("notification", "default_recipient")
    channel_result = app.configuration_manager.get("notification", "default_channel")
    if not recipient_result.success or not channel_result.success:
        _logger.warning("review completed notification skipped: recipient/channel not configured")
        return

    try:
        channel = Channel(str(channel_result.value))
    except ValueError:
        _logger.warning("review completed notification skipped: invalid channel configured")
        return

    event = NotificationEvent(
        workflow_id=workflow_id,
        event_type=EventType.REVIEW_COMPLETED,
        event_result={"decision": outcome.decision.value, "next_module": outcome.next_module},
        recipient=str(recipient_result.value),
        notification_template="review_completed_template",
        configuration={"channel": channel.value},
    )

    message_result = app.notification.create_message(event)
    if not message_result.success:
        _logger.warning("review completed notification failed at create_message: %s", message_result.error)
        return

    send_result = app.notification.send(message_result.value)
    if not send_result.success:
        _logger.warning("review completed notification failed at send: %s", send_result.error)
        return

    publish_result = app.notification.publish(send_result.value)
    if not publish_result.success:
        _logger.warning("review completed notification failed at publish: %s", publish_result.error)
