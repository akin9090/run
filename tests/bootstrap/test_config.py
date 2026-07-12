"""`bootstrap.config.build_configuration_manager()`と`config/default.json`の検証(Task 2)。

各モジュールが実際に呼び出す`ConfigurationClient.get(module_name, key)`のキーが
`config/default.json`経由で解決できることを確認する。キー名はすべて各モジュールの
呼び出し箇所(ソースコード)から確認した実在のキーであり、推測値ではない。
"""

import unittest

from bootstrap.config import build_configuration_manager


class BuildConfigurationManagerTest(unittest.TestCase):
    def test_load_succeeds_with_default_config_file(self) -> None:
        manager = build_configuration_manager()
        result = manager.load(manager._source)  # noqa: SLF001 - 初回loadの動作確認のみ
        self.assertTrue(result.success, msg=result.error)

    # --- state_manager (src/state_manager/manager.py:38, store.py:27) ---
    def test_state_manager_lock_timeout_seconds_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("state_manager", "lock_timeout_seconds")
        self.assertTrue(result.success, msg=result.error)

    def test_state_manager_backend_path_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("state_manager", "backend_path")
        self.assertTrue(result.success, msg=result.error)

    # --- permission_manager (src/permission_manager/permission_manager.py:125) ---
    def test_permission_manager_permissions_key_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("permission_manager", "permissions")
        self.assertTrue(result.success, msg=result.error)

    # --- pr_creator (src/pr_creator/pr_creator.py:464) ---
    def test_pr_creator_github_access_token_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("pr_creator", "github_access_token")
        self.assertTrue(result.success, msg=result.error)

    # --- github_manager (src/github_manager/client.py:92) ---
    def test_github_manager_github_access_token_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("github_manager", "github_access_token")
        self.assertTrue(result.success, msg=result.error)

    # --- connector (src/connector/slack_adapter.py:41, discord_adapter.py:39,42) ---
    def test_connector_slack_bot_token_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("connector", "slack_bot_token")
        self.assertTrue(result.success, msg=result.error)

    def test_connector_discord_bot_token_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("connector", "discord_bot_token")
        self.assertTrue(result.success, msg=result.error)

    def test_connector_discord_bot_user_id_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("connector", "discord_bot_user_id")
        self.assertTrue(result.success, msg=result.error)

    # --- reviewer (src/reviewer/config.py:27,31) ---
    def test_reviewer_min_business_score_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("reviewer", "min_business_score")
        self.assertTrue(result.success, msg=result.error)

    def test_reviewer_blocker_severity_blocks_approval_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("reviewer", "blocker_severity_blocks_approval")
        self.assertTrue(result.success, msg=result.error)

    # --- task_queue (src/task_queue/queue_manager.py:39-41,128,226,340) ---
    def test_task_queue_max_parallel_executions_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("task_queue", "max_parallel_executions")
        self.assertTrue(result.success, msg=result.error)

    def test_task_queue_max_retry_count_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("task_queue", "max_retry_count")
        self.assertTrue(result.success, msg=result.error)

    def test_task_queue_worker_timeout_seconds_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("task_queue", "worker_timeout_seconds")
        self.assertTrue(result.success, msg=result.error)

    # --- monitoring (module_name="Monitoring", capital M: src/monitoring/health_checker.py:158,
    #     keys defined in src/monitoring/constants.py:42-45) ---
    def test_monitoring_execution_time_threshold_minutes_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("Monitoring", "execution_time_threshold_minutes")
        self.assertTrue(result.success, msg=result.error)

    def test_monitoring_failure_rate_threshold_percent_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("Monitoring", "failure_rate_threshold_percent")
        self.assertTrue(result.success, msg=result.error)

    def test_monitoring_retry_count_threshold_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("Monitoring", "retry_count_threshold")
        self.assertTrue(result.success, msg=result.error)

    def test_monitoring_heartbeat_freshness_seconds_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("Monitoring", "heartbeat_freshness_seconds")
        self.assertTrue(result.success, msg=result.error)

    # --- context_manager (src/context_manager/collector.py:62; note the literal key
    #     name is the dotted string "system.environment", not the "system" category) ---
    def test_context_manager_system_environment_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("context_manager", "system.environment")
        self.assertTrue(result.success, msg=result.error)

    # --- command_router (src/command_router/routing_table.py:45; optional override,
    #     falls back to the static ROUTING_TABLE when unset, added for completeness) ---
    def test_command_router_routing_table_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("command_router", "routing_table")
        self.assertTrue(result.success, msg=result.error)

    # --- design_auditor / architect / notification health_check probes
    #     (src/design_auditor/module.py:61, src/architect/module.py:54,
    #     src/notification/service.py:61) ---
    def test_design_auditor_health_check_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("design_auditor", "health_check")
        self.assertTrue(result.success, msg=result.error)

    def test_architect_health_check_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("architect", "health_check")
        self.assertTrue(result.success, msg=result.error)

    def test_notification_health_check_resolves(self) -> None:
        manager = build_configuration_manager()
        manager.load(manager._source)  # noqa: SLF001
        result = manager.get("notification", "health_check")
        self.assertTrue(result.success, msg=result.error)


if __name__ == "__main__":
    unittest.main()
