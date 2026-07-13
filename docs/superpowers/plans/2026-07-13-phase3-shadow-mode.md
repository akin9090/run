# Phase 3: Shadow Mode開始 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ロードマップのPhase 3(Shadow Mode開始)の2成果物(Permission Manager Shadow
Modeプロファイル、Monitoring→Notification実アラート配線)と、`run_workflow()`のReviewer
判断結果をNotification経由で人間に届ける配線を実装する。

**Architecture:** 既存モジュール(Permission Manager/Monitoring/Notification)には
新しい振る舞いを追加せず、`bootstrap`層(composition root)で3つの独立した橋渡しを追加する。
`PermissionManager`にのみ後方互換な任意引数を1つ追加する。

**Tech Stack:** Python 3.13、標準ライブラリのみ、`unittest`。

## Global Constraints

- `run_workflow()`のシグネチャ(`app`/`request`/`business_goal`)は変更しない。`shadow_mode`
  のような分岐フラグは追加しない。
- `PermissionManager.reload()`の実装・既存テストには一切変更を加えない。
- Notification送信の失敗は、呼び出し元(`monitoring_smoke_test.py`を除く)の主要な処理結果に
  影響させない(ログ警告のみ)。
- 自動Unit Testは実ネットワーク通信を一切行わない(フェイクのみ)。
- 全体テストスイート(`PYTHONPATH=src python -m unittest discover -s tests -t .`)・
  `ruff check src tests`・`black --check src tests`が最終的に全て成功すること。
- 参照設計書: `docs/superpowers/specs/2026-07-13-phase3-shadow-mode-design.md`

---

### Task 1: Permission Manager Shadow Modeプロファイル

**Files:**
- Modify: `src/permission_manager/default_permissions.py`
- Modify: `src/permission_manager/permission_manager.py`
- Test: `tests/permission_manager/test_permission_manager.py`

**Interfaces:**
- Consumes: `permission_manager.models.Module`/`Operation`/`Effect`/`PermissionEntry`(既存)
- Produces: `permission_manager.default_permissions.SHADOW_MODE_PERMISSIONS: tuple[PermissionEntry, ...]`、
  `PermissionManager.__init__(self, config_client=None, permissions: tuple[PermissionEntry, ...] | None = None)`

- [ ] **Step 1: 失敗するテストを書く**

`tests/permission_manager/test_permission_manager.py`の`CheckPermissionAllowTest`クラスの下、
`ListPermissionsTest`クラスの前に以下を追加する。

```python
from permission_manager.default_permissions import DEFAULT_PERMISSIONS, SHADOW_MODE_PERMISSIONS


class ShadowModePermissionsTest(unittest.TestCase):
    def test_shadow_mode_permissions_denies_executor_pull_request_create(self) -> None:
        manager = PermissionManager(permissions=SHADOW_MODE_PERMISSIONS)

        result = manager.check_permission(Module.EXECUTOR, Operation.PULL_REQUEST_CREATE)

        self.assertTrue(result.success)
        self.assertFalse(result.value)
        self.assertIsInstance(result.error, PermissionDeniedError)

    def test_shadow_mode_permissions_still_allows_planner_execution_plan_create(self) -> None:
        manager = PermissionManager(permissions=SHADOW_MODE_PERMISSIONS)

        result = manager.check_permission(Module.PLANNER, Operation.EXECUTION_PLAN_CREATE)

        self.assertTrue(result.success)
        self.assertTrue(result.value)

    def test_shadow_mode_permissions_is_default_permissions_minus_pull_request_create(self) -> None:
        expected = tuple(
            entry
            for entry in DEFAULT_PERMISSIONS
            if not (entry.module is Module.EXECUTOR and entry.operation is Operation.PULL_REQUEST_CREATE)
        )
        self.assertEqual(SHADOW_MODE_PERMISSIONS, expected)

    def test_default_constructor_without_permissions_arg_uses_default_permissions(self) -> None:
        manager = PermissionManager()
        self.assertEqual(manager._permissions, DEFAULT_PERMISSIONS)
```

`from permission_manager.default_permissions import DEFAULT_PERMISSIONS, SHADOW_MODE_PERMISSIONS`
は既存の1行目のimport(`from permission_manager.default_permissions import DEFAULT_PERMISSIONS`)を
置き換える形で追加する(重複import防止のため既存行を編集する)。

- [ ] **Step 2: テストが失敗することを確認する**

Run: `PYTHONPATH=src python -m unittest tests.permission_manager.test_permission_manager -v`
Expected: FAIL(`ImportError: cannot import name 'SHADOW_MODE_PERMISSIONS'`)

- [ ] **Step 3: 最小限の実装を書く**

`src/permission_manager/default_permissions.py`の末尾に追記:

```python
# Phase 3 Shadow Mode: DEFAULT_PERMISSIONSから「Executorによる Pull Request作成」の
# Allowエントリのみを除いた一時的な制限プロファイル。「表に無い組み合わせ=Deny」という
# 既存のフェイルセーフ方針(設計書4.3)により、Denyエントリを明示的に追加する必要はない。
SHADOW_MODE_PERMISSIONS: tuple[PermissionEntry, ...] = tuple(
    entry
    for entry in DEFAULT_PERMISSIONS
    if not (entry.module is Module.EXECUTOR and entry.operation is Operation.PULL_REQUEST_CREATE)
)
```

`src/permission_manager/permission_manager.py`の`__init__`を以下に置き換える:

```python
    def __init__(
        self,
        config_client: ConfigurationClient | None = None,
        permissions: tuple[PermissionEntry, ...] | None = None,
    ) -> None:
        """
        Args:
            config_client: F03 ConfigurationClient実装。Noneの場合はDEFAULT_PERMISSIONSのみで動作する
                (MVPでは起動時にreload()を呼ばない限りDEFAULT_PERMISSIONSが唯一の定義元)。
            permissions: 初期権限テーブルの差し替え(Phase 3 Shadow Mode等)。省略時は
                DEFAULT_PERMISSIONSを使う。`reload()`の挙動には影響しない。
        """
        self._config_client = config_client
        self._logger = get_logger(MODULE_NAME)
        self._permissions: tuple[PermissionEntry, ...] = permissions if permissions is not None else DEFAULT_PERMISSIONS
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `PYTHONPATH=src python -m unittest tests.permission_manager.test_permission_manager -v`
Expected: PASS(全件)

- [ ] **Step 5: コミット**

```bash
git add src/permission_manager/default_permissions.py src/permission_manager/permission_manager.py tests/permission_manager/test_permission_manager.py
git commit -m "feat: Permission ManagerにShadow Modeプロファイル(SHADOW_MODE_PERMISSIONS)を追加"
```

---

### Task 2: `bootstrap/wiring.py`にShadow Modeフラグを追加

**Files:**
- Modify: `src/bootstrap/wiring.py`
- Test: `tests/bootstrap/test_wiring.py`

**Interfaces:**
- Consumes: Task 1の`permission_manager.default_permissions.SHADOW_MODE_PERMISSIONS`
- Produces: `build_application(*, ..., shadow_mode: bool = False)`

- [ ] **Step 1: 失敗するテストを書く**

`tests/bootstrap/test_wiring.py`のファイル先頭のimport群(`from notification.types import Channel`の下)に
以下の2行を追加する(Ruffの E402 = ファイル先頭以外でのimport規約に抵触しないよう、
既存のimport群と同じ位置にまとめること):

```python
from permission_manager.default_permissions import DEFAULT_PERMISSIONS, SHADOW_MODE_PERMISSIONS
from permission_manager.models import Module, Operation
```

続いて、`UseRealCodexTest`クラスの後、`if __name__ ==`より前に以下を追加する。

```python
class ShadowModeTest(unittest.TestCase):
    """Phase 3: `shadow_mode=True`時にPermission ManagerがShadow Modeプロファイル
    (`SHADOW_MODE_PERMISSIONS`)で構築されることを確認する。"""

    def test_default_wiring_uses_default_permissions(self) -> None:
        app = build_application()

        self.assertEqual(app.permission_manager._permissions, DEFAULT_PERMISSIONS)  # noqa: SLF001

    def test_shadow_mode_wires_shadow_mode_permissions(self) -> None:
        app = build_application(shadow_mode=True)

        self.assertEqual(app.permission_manager._permissions, SHADOW_MODE_PERMISSIONS)  # noqa: SLF001

    def test_shadow_mode_denies_executor_pull_request_create(self) -> None:
        app = build_application(shadow_mode=True)

        result = app.permission_manager.check_permission(Module.EXECUTOR, Operation.PULL_REQUEST_CREATE)

        self.assertTrue(result.success)
        self.assertFalse(result.value)
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `PYTHONPATH=src python -m unittest tests.bootstrap.test_wiring -v`
Expected: FAIL(`build_application() got an unexpected keyword argument 'shadow_mode'`)

- [ ] **Step 3: 最小限の実装を書く**

`src/bootstrap/wiring.py`のimport群に追加(`from executor.executor import Executor`の下あたり、
アルファベット順を保つ):

```python
from permission_manager.default_permissions import SHADOW_MODE_PERMISSIONS
```

`build_application()`の関数シグネチャを以下に置き換える:

```python
def build_application(
    *,
    use_real_github: bool = False,
    use_real_slack: bool = False,
    use_real_codex: bool = False,
    shadow_mode: bool = False,
) -> Application:
```

docstringの末尾(既存の`use_real_codex=True`の段落の後)に追記:

```
    `shadow_mode=True`の場合、Permission Manager(M04)はDEFAULT_PERMISSIONSではなく
    `SHADOW_MODE_PERMISSIONS`(Executorの Pull Request作成のみを除いたプロファイル)で
    構築される。外部サービスへの接続には影響しない(Permission Managerの権限テーブルの
    みを切り替える)。
```

`permission_manager = PermissionManager(config_client=config)`の行を以下に置き換える:

```python
    permission_manager = PermissionManager(
        config_client=config,
        permissions=SHADOW_MODE_PERMISSIONS if shadow_mode else None,
    )
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `PYTHONPATH=src python -m unittest tests.bootstrap.test_wiring -v`
Expected: PASS(全件)

- [ ] **Step 5: コミット**

```bash
git add src/bootstrap/wiring.py tests/bootstrap/test_wiring.py
git commit -m "feat: build_application()にshadow_modeフラグを追加"
```

---

### Task 3: ロードマップ文言の修正

**Files:**
- Modify: `docs/ROADMAP_v1.1.md`

**Interfaces:**
- Consumes: なし(ドキュメントのみ)
- Produces: なし

- [ ] **Step 1: 該当箇所を修正する**

`docs/ROADMAP_v1.1.md`のPhase 3セクション、「**成果物**:」の1行目
(`- Permission Managerの\`DEFAULT_PERMISSIONS\`をShadow Mode用に一時的に絞ったプロファイル
として\`config/default.json\`の\`permission_manager.extra\`領域に定義`)を、以下に置き換える:

```markdown
- Permission Managerの`DEFAULT_PERMISSIONS`をShadow Mode用に一時的に絞ったプロファイル
  (`SHADOW_MODE_PERMISSIONS`)として`src/permission_manager/default_permissions.py`に
  定義し、`PermissionManager`のコンストラクタ引数(`permissions`)経由で差し替え可能にする
  (2026-07実装時の是正: `PermissionManager.reload()`はConfigurationClientの戻り値を
  そのまま`PermissionEntry`として扱うため、JSONプリミティブしか保持できない
  `config/default.json`からは読み込めない。詳細は
  `docs/superpowers/specs/2026-07-13-phase3-shadow-mode-design.md`参照)
```

- [ ] **Step 2: 差分を確認する**

Run: `git diff docs/ROADMAP_v1.1.md`
Expected: 該当1ブロックのみが変更されている

- [ ] **Step 3: コミット**

```bash
git add docs/ROADMAP_v1.1.md
git commit -m "docs: ロードマップのPhase 3成果物記述を実装内容に合わせて修正"
```

---

### Task 4: Monitoring→Notification 橋渡し関数 + 設定値追加

**Files:**
- Modify: `src/bootstrap/adapters.py`
- Modify: `config/default.json`
- Test: `tests/bootstrap/test_adapters.py`

**Interfaces:**
- Consumes: `monitoring.models.MonitoringReport`(既存)、`notification.types.Channel`/`EventType`/`NotificationEvent`(既存)
- Produces: `bootstrap.adapters.monitoring_report_to_notification_event(report: MonitoringReport, recipient: str, channel: Channel) -> NotificationEvent | None`

- [ ] **Step 1: 失敗するテストを書く**

`tests/bootstrap/test_adapters.py`は既に`from foundation.utils import utc_now`と
`from notification.types import Channel, EventType, NotificationMessage`をimport済みなので、
これらは再利用する(重複追加しないこと)。ファイル先頭の`from bootstrap.adapters import (...)`
の括弧内に`monitoring_report_to_notification_event`を追記し、新たに
`from monitoring.models import HealthStatus, Metrics, MonitoringReport, PerformanceSummary, SystemResourceStatus`
の1行を追加する。

以下のテストコードを末尾(`if __name__ ==`より前)に追加する(`now = datetime.now(timezone.utc)`
ではなく、既存importの`utc_now()`を使うこと)。

```python
def _make_monitoring_report(*, overall_healthy: bool, failures: list[str], warnings: list[str]) -> MonitoringReport:
    now = utc_now()
    health_status = HealthStatus(
        id="health-1",
        created_at=now,
        updated_at=now,
        metadata={},
        evaluated_at=now,
        overall_healthy=overall_healthy,
        module_health=[],
        warnings=warnings,
        failures=failures,
    )
    metrics = Metrics(
        id="metrics-1",
        created_at=now,
        updated_at=now,
        metadata={},
        collected_at=now,
        system_resources=SystemResourceStatus(
            cpu_percent=0.0, memory_percent=0.0, disk_percent=0.0, network_io_bytes_per_sec=0.0
        ),
        workflow_metrics=[],
        module_metrics=[],
    )
    return MonitoringReport(
        id="report-1",
        created_at=now,
        updated_at=now,
        metadata={},
        health_status=health_status,
        metrics=metrics,
        failures=failures,
        warnings=warnings,
        performance_summary=PerformanceSummary(
            average_execution_time_seconds=0.0, success_rate=0.0, failure_rate=0.0, total_workflows=0
        ),
    )


class MonitoringReportToNotificationEventTest(unittest.TestCase):
    def test_returns_none_when_report_is_healthy(self) -> None:
        report = _make_monitoring_report(overall_healthy=True, failures=[], warnings=[])

        event = monitoring_report_to_notification_event(report, recipient="ops-channel", channel=Channel.SLACK)

        self.assertIsNone(event)

    def test_returns_system_error_event_when_report_is_unhealthy(self) -> None:
        report = _make_monitoring_report(
            overall_healthy=False, failures=["workflow wf-1 failed"], warnings=["Executor: retry count exceeded"]
        )

        event = monitoring_report_to_notification_event(report, recipient="ops-channel", channel=Channel.SLACK)

        self.assertIsNotNone(event)
        self.assertEqual(event.workflow_id, "report-1")
        self.assertEqual(event.event_type, EventType.SYSTEM_ERROR)
        self.assertEqual(event.recipient, "ops-channel")
        self.assertEqual(event.notification_template, "system_error_template")
        self.assertEqual(event.configuration, {"channel": "slack"})
        self.assertEqual(event.event_result["failures"], "workflow wf-1 failed")
        self.assertEqual(event.event_result["warnings"], "Executor: retry count exceeded")

    def test_returns_placeholder_text_when_no_failures_or_warnings(self) -> None:
        report = _make_monitoring_report(overall_healthy=False, failures=[], warnings=[])

        event = monitoring_report_to_notification_event(report, recipient="ops-channel", channel=Channel.SLACK)

        self.assertIsNotNone(event)
        self.assertEqual(event.event_result["failures"], "(none)")
        self.assertEqual(event.event_result["warnings"], "(none)")
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `PYTHONPATH=src python -m unittest tests.bootstrap.test_adapters -v`
Expected: FAIL(`ImportError: cannot import name 'monitoring_report_to_notification_event'`)

- [ ] **Step 3: 最小限の実装を書く**

`src/bootstrap/adapters.py`のimport群を修正する。既存の
`from notification.errors import UnsupportedChannelError`の下に追加:

```python
from monitoring.models import MonitoringReport
```

既存の`from notification.types import Channel, NotificationMessage`を以下に置き換える:

```python
from notification.types import Channel, EventType, NotificationEvent, NotificationMessage
```

`__all__`リストに`"monitoring_report_to_notification_event"`を追加する。

ファイル末尾(`NotificationChannelConnectorBridge`クラスの後)に追記:

```python
def monitoring_report_to_notification_event(
    report: MonitoringReport, recipient: str, channel: Channel
) -> NotificationEvent | None:
    """MonitoringReportが不健全な場合のみ、Notification(M15)向けのSYSTEM_ERROR
    NotificationEventを組み立てる(Phase 3: Monitoring→Notification実アラート配線)。

    Monitoring(M16)はRead Only設計であり通知送信を行わないため、この橋渡しは
    composition root(bootstrap層)の責務とする。健全な場合は通知不要のためNoneを返す。

    `workflow_id`はMonitoringReport自体がWorkflow単位のドメインではないため、
    `report.id`を相関ID代わりに用いる。
    """
    if report.health_status.overall_healthy:
        return None

    return NotificationEvent(
        workflow_id=report.id,
        event_type=EventType.SYSTEM_ERROR,
        event_result={
            "failures": "; ".join(report.failures) if report.failures else "(none)",
            "warnings": "; ".join(report.warnings) if report.warnings else "(none)",
        },
        recipient=recipient,
        notification_template="system_error_template",
        configuration={"channel": channel.value},
    )
```

`config/default.json`の`"notification"`セクション(ファイル末尾、最後のキーであるため
閉じ括弧の後にカンマは付かない):

```json
  "notification": {
    "health_check": true
  }
}
```

を以下に置き換える(こちらも`"notification"`がファイル内最後のキーのままなので、
閉じ括弧`}`の後にカンマを付けないこと):

```json
  "notification": {
    "health_check": true,
    "default_recipient": "",
    "default_channel": "slack",
    "system_error_template": "[Monitoring] システム異常を検知しました。failures={failures} warnings={warnings}",
    "review_completed_template": "[Workflow] レビュー完了: decision={decision} next_module={next_module}"
  }
}
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `PYTHONPATH=src python -m unittest tests.bootstrap.test_adapters -v`
Expected: PASS(全件)

- [ ] **Step 5: コミット**

```bash
git add src/bootstrap/adapters.py config/default.json tests/bootstrap/test_adapters.py
git commit -m "feat: Monitoring→Notification橋渡し関数と通知設定値を追加"
```

---

### Task 5: `monitoring_smoke_test.py`(手動スモークテスト)

**Files:**
- Create: `src/bootstrap/monitoring_smoke_test.py`
- Test: `tests/bootstrap/test_monitoring_smoke_test.py`

**Interfaces:**
- Consumes: Task 4の`bootstrap.adapters.monitoring_report_to_notification_event`、
  `bootstrap.wiring.build_application(use_real_slack=True)`(既存)
- Produces: `bootstrap.monitoring_smoke_test.main(argv=None) -> int`

- [ ] **Step 1: 失敗するテストを書く**

`tests/bootstrap/test_monitoring_smoke_test.py`を新規作成する(既存の
`tests/bootstrap/test_slack_smoke_test.py`と同じ形式):

```python
"""Phase 3: monitoring_smoke_test.pyの引数解析・エラーパスのテスト(実ネットワーク接続は行わない)。"""

import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from bootstrap.monitoring_smoke_test import main


class MonitoringSmokeTestMainTest(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_main_returns_1_when_slack_bot_token_missing(self) -> None:
        buffer = io.StringIO()
        with redirect_stderr(buffer):
            exit_code = main([])

        self.assertEqual(exit_code, 1)
        self.assertIn("SLACK_BOT_TOKEN", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `PYTHONPATH=src python -m unittest tests.bootstrap.test_monitoring_smoke_test -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'bootstrap.monitoring_smoke_test'`)

- [ ] **Step 3: 最小限の実装を書く**

`src/bootstrap/monitoring_smoke_test.py`を新規作成する:

```python
"""Phase 3: Monitoring(M16)→Notification(M15)の実アラート配線を確認する手動スモークテスト。

意図的に不健全なMetrics(failure_rate=100%、config/default.jsonの
`Monitoring.failure_rate_threshold_percent`=20を超過)を組み立ててMonitoringの
analyze()/report()に通し、`bootstrap.adapters.monitoring_report_to_notification_event()`
経由でNotificationモジュールへ渡し、実Slackへの配信を確認する。

テストスイート(unittest discover)には含めず、SLACK_BOT_TOKENが揃った時点で
ユーザーが手動実行する想定。

使い方:
    SLACK_BOT_TOKEN=xoxb-xxx PYTHONPATH=src python -m bootstrap.monitoring_smoke_test
"""

import sys

from bootstrap.adapters import monitoring_report_to_notification_event
from bootstrap.wiring import build_application
from foundation.utils import utc_now
from monitoring.constants import MonitoredModuleName
from monitoring.models import Metrics, ModuleMetrics, SystemResourceStatus
from notification.types import Channel


def _build_unhealthy_metrics() -> Metrics:
    now = utc_now()
    return Metrics(
        id="monitoring-smoke-test",
        created_at=now,
        updated_at=now,
        metadata={},
        collected_at=now,
        system_resources=SystemResourceStatus(
            cpu_percent=0.0, memory_percent=0.0, disk_percent=0.0, network_io_bytes_per_sec=0.0
        ),
        workflow_metrics=[],
        module_metrics=[
            ModuleMetrics(
                module=MonitoredModuleName.EXECUTOR,
                execution_time_seconds=0.0,
                success_rate=0.0,
                failure_rate=100.0,
                retry_count=0,
                queue_length=0,
            )
        ],
    )


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001 - 引数なし、他スモークテストと形式を揃える
    try:
        app = build_application(use_real_slack=True)
    except RuntimeError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1

    metrics = _build_unhealthy_metrics()
    analyze_result = app.monitoring.analyze(metrics)
    if not analyze_result.success:
        print(f"analyze failed: {analyze_result.error}", file=sys.stderr)
        return 1

    report_result = app.monitoring.report(analyze_result.value, metrics)
    if not report_result.success:
        print(f"report failed: {report_result.error}", file=sys.stderr)
        return 1

    recipient_result = app.configuration_manager.get("notification", "default_recipient")
    channel_result = app.configuration_manager.get("notification", "default_channel")
    if not recipient_result.success or not channel_result.success:
        print("configuration error: notification.default_recipient/default_channel not set", file=sys.stderr)
        return 1

    event = monitoring_report_to_notification_event(
        report_result.value,
        recipient=str(recipient_result.value),
        channel=Channel(str(channel_result.value)),
    )
    if event is None:
        print("unexpected: report was healthy (this smoke test expects unhealthy)", file=sys.stderr)
        return 1

    message_result = app.notification.create_message(event)
    if not message_result.success:
        print(f"create_message failed: {message_result.error}", file=sys.stderr)
        return 1

    send_result = app.notification.send(message_result.value)
    if not send_result.success:
        print(f"send failed: {send_result.error}", file=sys.stderr)
        return 1

    print(f"OK: notification delivery_result={send_result.value.status.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `PYTHONPATH=src python -m unittest tests.bootstrap.test_monitoring_smoke_test -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src/bootstrap/monitoring_smoke_test.py tests/bootstrap/test_monitoring_smoke_test.py
git commit -m "feat: Monitoring→Notification実接続確認用スモークテストを追加"
```

---

### Task 6: `run_workflow()`のReviewer判断結果をNotificationへ配信

**Files:**
- Modify: `src/bootstrap/workflow.py`
- Test: `tests/bootstrap/test_workflow.py`

**Interfaces:**
- Consumes: Task 4で追加した`config/default.json`の`notification.default_recipient`/
  `default_channel`/`review_completed_template`
- Produces: なし(`run_workflow()`の戻り値の型は変更しない)

- [ ] **Step 1: 失敗するテストを書く**

`tests/bootstrap/test_workflow.py`の`RunWorkflowTest`クラスに以下のテストメソッドを追加する
(クラス内、既存の`test_synthetic_workflow_completes_through_reviewer`の下):

```python
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
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `PYTHONPATH=src python -m unittest tests.bootstrap.test_workflow -v`
Expected: FAIL(`histories`が空、またはAssertionError)

- [ ] **Step 3: 最小限の実装を書く**

`src/bootstrap/workflow.py`のimport群の末尾に追加:

```python
from foundation.logger import get_logger
from notification.types import Channel, EventType, NotificationEvent
```

`run_workflow()`関数定義の直前(モジュールレベル)に以下を追加:

```python
_logger = get_logger("bootstrap.workflow")
```

ファイル末尾(`run_workflow()`関数の後)に追記:

```python
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
```

`run_workflow()`関数末尾の以下の部分:

```python
    # --- Reviewer (M12) ---
    review_report_result = app.reviewer.review(pr_result.value)
    if not review_report_result.success:
        return Result(success=False, error=review_report_result.error)

    return app.reviewer.publish_review(review_report_result.value)
```

を、以下に置き換える:

```python
    # --- Reviewer (M12) ---
    review_report_result = app.reviewer.review(pr_result.value)
    if not review_report_result.success:
        return Result(success=False, error=review_report_result.error)

    review_outcome_result = app.reviewer.publish_review(review_report_result.value)
    if not review_outcome_result.success:
        return Result(success=False, error=review_outcome_result.error)

    _notify_review_completed(app, request.workflow_id, review_outcome_result.value)

    return review_outcome_result
```

`ReviewOutcome`型は既にファイル冒頭で`from reviewer.domain import ReviewOutcome`済みか確認し、
未importであれば追加する(`_notify_review_completed`の型注釈で使用するため)。

- [ ] **Step 4: テストが通ることを確認する**

Run: `PYTHONPATH=src python -m unittest tests.bootstrap.test_workflow -v`
Expected: PASS(全件、既存の`RunWorkflowTest`/`RunWorkflowPrBodyTest`含む)

- [ ] **Step 5: コミット**

```bash
git add src/bootstrap/workflow.py tests/bootstrap/test_workflow.py
git commit -m "feat: run_workflow()のReviewer判断結果をNotification経由で配信"
```

---

### Task 7: 全体検証 + CHANGELOG更新

**Files:**
- Modify: `docs/CHANGELOG.md`

**Interfaces:**
- Consumes: なし
- Produces: なし

- [ ] **Step 1: 全体テストスイートを実行する**

Run: `PYTHONPATH=src python -m unittest discover -s tests -t .`
Expected: 全件PASS(既存898件 + 本フェーズ新規分)

- [ ] **Step 2: Ruff/Blackを実行する**

Run: `ruff check src tests && black --check src tests`
Expected: 両方成功(`All checks passed!` / `would be left unchanged`)

- [ ] **Step 3: CHANGELOG.mdに新セクションを追記する**

`docs/CHANGELOG.md`の末尾に以下を追記する(実行後の実際のテスト総件数に置き換えること):

```markdown

## v1.6.0 (Phase 3: Shadow Mode開始)

ロードマップの推奨着手順序ではPhase 1-BとPhase 1-Cの間に位置するべきだったが、実際には
Phase 1-Cを先に完了させたため、本フェーズはその追いつき作業。

- **`src/permission_manager/default_permissions.py`**: `SHADOW_MODE_PERMISSIONS`定数
  (`DEFAULT_PERMISSIONS`からExecutorのPull Request作成のみを除いたプロファイル)を追加。
- **`src/permission_manager/permission_manager.py`**: `PermissionManager.__init__`に
  任意引数`permissions`を追加(後方互換、既定値は`DEFAULT_PERMISSIONS`)。`reload()`は
  変更していない。
- **`src/bootstrap/wiring.py`**: `build_application(shadow_mode=True)`で、Permission
  Managerが`SHADOW_MODE_PERMISSIONS`で構築されるよう切り替え可能にした。
- **`docs/ROADMAP_v1.1.md`**: Phase 3成果物の記述を、実際の実装内容(Configuration
  Manager経由のJSON設定ではなくPythonコード定数)に合わせて修正。
- **`src/bootstrap/adapters.py`**: `monitoring_report_to_notification_event()`を追加。
  Monitoring(M16、Read Only設計につき自身では通知を送信しない)のMonitoringReportが
  不健全な場合のみ、Notification(M15)向けの`SYSTEM_ERROR` NotificationEventを組み立てる
  橋渡し関数。
- **`config/default.json`**: `notification`セクションに`default_recipient`/
  `default_channel`/`system_error_template`/`review_completed_template`を追加。
- **`src/bootstrap/monitoring_smoke_test.py`**(新規): 意図的に不健全なMetricsを
  Monitoringに通し、上記橋渡し関数経由でNotification→実Slackへの配信を確認する
  手動スモークテスト。
- **`src/bootstrap/workflow.py`**: `run_workflow()`のReviewer最終判断
  (`ReviewOutcome`)を、`EventType.REVIEW_COMPLETED`としてNotification経由で
  配信する処理を追加。通知失敗はWorkflow全体の結果に影響させない(警告ログのみ)。
  `run_workflow()`の引数(シグネチャ)は変更していない。

### 検証結果

| 項目 | 結果 |
|---|---|
| Unit Test | 全<N>件通過(既存898件 + 本フェーズ新規分) |
| Ruff / Black | クリーン |
| Monitoring→Notification実アラート配線 | 動作確認予定(`python -m bootstrap.monitoring_smoke_test`をユーザー環境で`SLACK_BOT_TOKEN`設定の上で実行) |
```

`<N>`は実際に`unittest discover`が報告した総件数に置き換えること。

- [ ] **Step 4: コミット**

```bash
git add docs/CHANGELOG.md
git commit -m "docs: CHANGELOG.mdにPhase 3(Shadow Mode開始)の記録を追加"
```

---

## 完了条件

- [ ] Task 1〜7すべて完了
- [ ] `PYTHONPATH=src python -m unittest discover -s tests -t .`が全件PASS
- [ ] `ruff check src tests`と`black --check src tests`が両方成功
- [ ] `docs/CHANGELOG.md`に実際の総テスト件数が反映されている
