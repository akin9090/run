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
