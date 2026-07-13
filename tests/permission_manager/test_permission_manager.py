import unittest

from foundation.errors import ConfigurationError, PermissionDeniedError, ValidationError
from foundation.interfaces import ConfigurationClient
from foundation.result import Result
from permission_manager.default_permissions import DEFAULT_PERMISSIONS, SHADOW_MODE_PERMISSIONS
from permission_manager.models import Effect, Module, Operation, PermissionEntry
from permission_manager.permission_manager import PermissionManager


class _SuccessConfigurationClient(ConfigurationClient):
    """get()が新しい権限定義を返す成功系フェイク。"""

    def __init__(self, permissions: tuple[PermissionEntry, ...]) -> None:
        self._permissions = permissions

    def get(self, module_name: str, key: str) -> Result:
        return Result(success=True, value=self._permissions)


class _FailingConfigurationClient(ConfigurationClient):
    """get()が常に失敗するフェイク。"""

    def __init__(self, message: str = "configuration source unavailable") -> None:
        self._message = message

    def get(self, module_name: str, key: str) -> Result:
        return Result(success=False, value=None, error=ConfigurationError(self._message))


class CheckPermissionAllowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = PermissionManager()

    def test_check_permission_allows_planner_execution_plan_create(self) -> None:
        result = self.manager.check_permission(Module.PLANNER, Operation.EXECUTION_PLAN_CREATE)
        self.assertTrue(result.success)
        self.assertTrue(result.value)
        self.assertIsNone(result.error)

    def test_check_permission_allows_designer_design_create(self) -> None:
        result = self.manager.check_permission(Module.DESIGNER, Operation.DESIGN_CREATE)
        self.assertTrue(result.success)
        self.assertTrue(result.value)

    def test_check_permission_allows_executor_pull_request_create(self) -> None:
        result = self.manager.check_permission(Module.EXECUTOR, Operation.PULL_REQUEST_CREATE)
        self.assertTrue(result.success)
        self.assertTrue(result.value)

    def test_check_permission_allows_reviewer_review_create(self) -> None:
        result = self.manager.check_permission(Module.REVIEWER, Operation.REVIEW_CREATE)
        self.assertTrue(result.success)
        self.assertTrue(result.value)

    def test_check_permission_allows_scheduler_workflow_start(self) -> None:
        result = self.manager.check_permission(Module.SCHEDULER, Operation.WORKFLOW_START)
        self.assertTrue(result.success)
        self.assertTrue(result.value)

    def test_check_permission_allows_knowledge_manager_knowledge_update(self) -> None:
        result = self.manager.check_permission(Module.KNOWLEDGE_MANAGER, Operation.KNOWLEDGE_UPDATE)
        self.assertTrue(result.success)
        self.assertTrue(result.value)

    def test_check_permission_allows_command_router_command_dispatch(self) -> None:
        result = self.manager.check_permission(Module.COMMAND_ROUTER, Operation.COMMAND_DISPATCH)
        self.assertTrue(result.success)
        self.assertTrue(result.value)

    def test_check_permission_returns_result_bool_with_value_true_on_allow(self) -> None:
        result = self.manager.check_permission(Module.PLANNER, Operation.EXECUTION_PLAN_CREATE)
        self.assertIsInstance(result, Result)
        self.assertIs(result.value, True)


class CheckPermissionDenyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = PermissionManager()

    def test_check_permission_denies_undefined_module_operation_pair(self) -> None:
        result = self.manager.check_permission(Module.PLANNER, Operation.DESIGN_CREATE)
        self.assertTrue(result.success)
        self.assertFalse(result.value)

    def test_check_permission_denies_when_operation_belongs_to_other_module(self) -> None:
        result = self.manager.check_permission(Module.DESIGNER, Operation.EXECUTION_PLAN_CREATE)
        self.assertTrue(result.success)
        self.assertFalse(result.value)

    def test_check_permission_denied_result_contains_permission_denied_error_with_reason(
        self,
    ) -> None:
        result = self.manager.check_permission(Module.PLANNER, Operation.DESIGN_CREATE)
        self.assertIsInstance(result.error, PermissionDeniedError)
        self.assertTrue(result.error.message)


class CheckPermissionFailsafeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = PermissionManager()

    def test_check_permission_denies_when_permission_table_is_empty(self) -> None:
        self.manager._permissions = ()
        result = self.manager.check_permission(Module.PLANNER, Operation.EXECUTION_PLAN_CREATE)
        self.assertTrue(result.success)
        self.assertFalse(result.value)
        self.assertIsInstance(result.error, PermissionDeniedError)

    def test_check_permission_denies_when_configuration_client_fetch_fails(self) -> None:
        manager = PermissionManager(config_client=_FailingConfigurationClient())
        reload_result = manager.reload()
        self.assertFalse(reload_result.success)

        # フェッチ失敗により最新の権限情報が一切得られない状況を再現する。
        manager._permissions = ()
        result = manager.check_permission(Module.PLANNER, Operation.EXECUTION_PLAN_CREATE)
        self.assertTrue(result.success)
        self.assertFalse(result.value)
        self.assertIsInstance(result.error, PermissionDeniedError)

    def test_check_permission_never_returns_allow_on_ambiguous_or_error_state(self) -> None:
        self.manager._permissions = ()
        for module in Module:
            for operation in Operation:
                result = self.manager.check_permission(module, operation)
                self.assertFalse(result.value)

    def test_list_permissions_returns_empty_list_when_permission_table_unavailable(self) -> None:
        self.manager._permissions = ()
        result = self.manager.list_permissions(Module.PLANNER)
        self.assertTrue(result.success)
        self.assertEqual(result.value, [])

    def test_list_permissions_never_returns_operations_not_explicitly_allowed(self) -> None:
        result = self.manager.list_permissions(Module.PLANNER)
        self.assertEqual(result.value, [Operation.EXECUTION_PLAN_CREATE])
        self.assertNotIn(Operation.DESIGN_CREATE, result.value)


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


class ListPermissionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = PermissionManager()

    def test_list_permissions_returns_single_operation_for_planner(self) -> None:
        result = self.manager.list_permissions(Module.PLANNER)
        self.assertTrue(result.success)
        self.assertEqual(result.value, [Operation.EXECUTION_PLAN_CREATE])

    def test_list_permissions_returns_empty_list_for_module_with_no_allowed_operations(
        self,
    ) -> None:
        # デフォルトの7件からReviewerのエントリを除いたテーブルを用いて、
        # 許可Operationが0件のModuleに対してlist_permissionsが空リストを返すことを検証する。
        reduced = tuple(entry for entry in DEFAULT_PERMISSIONS if entry.module is not Module.REVIEWER)
        self.manager._permissions = reduced
        result = self.manager.list_permissions(Module.REVIEWER)
        self.assertTrue(result.success)
        self.assertEqual(result.value, [])


class ReloadTest(unittest.TestCase):
    def test_reload_success_replaces_permission_table_with_configuration_client_data(
        self,
    ) -> None:
        new_permissions = (PermissionEntry(Module.PLANNER, Operation.DESIGN_CREATE, Effect.ALLOW),)
        manager = PermissionManager(config_client=_SuccessConfigurationClient(new_permissions))

        result = manager.reload()

        self.assertTrue(result.success)
        self.assertTrue(result.value)
        self.assertEqual(manager._permissions, new_permissions)

        allowed = manager.check_permission(Module.PLANNER, Operation.DESIGN_CREATE)
        self.assertTrue(allowed.value)
        previously_allowed = manager.check_permission(Module.PLANNER, Operation.EXECUTION_PLAN_CREATE)
        self.assertFalse(previously_allowed.value)

    def test_reload_failure_keeps_previous_permission_table_intact(self) -> None:
        manager = PermissionManager(config_client=_FailingConfigurationClient())
        original = manager._permissions

        manager.reload()

        self.assertEqual(manager._permissions, original)
        self.assertEqual(manager._permissions, DEFAULT_PERMISSIONS)

    def test_reload_failure_returns_result_success_false(self) -> None:
        manager = PermissionManager(config_client=_FailingConfigurationClient("boom"))

        result = manager.reload()

        self.assertFalse(result.success)
        self.assertFalse(result.value)
        self.assertIsInstance(result.error, ConfigurationError)

    def test_reload_without_configuration_client_keeps_default_permissions(self) -> None:
        manager = PermissionManager()

        result = manager.reload()

        self.assertTrue(result.success)
        self.assertEqual(manager._permissions, DEFAULT_PERMISSIONS)


class BaseModuleTest(unittest.TestCase):
    def test_name_returns_permission_manager(self) -> None:
        manager = PermissionManager()
        self.assertEqual(manager.name(), "permission_manager")

    def test_health_check_returns_true_when_permissions_loaded(self) -> None:
        manager = PermissionManager()
        result = manager.health_check()
        self.assertTrue(result.success)
        self.assertTrue(result.value)

    def test_health_check_returns_false_when_permissions_table_empty(self) -> None:
        manager = PermissionManager()
        manager._permissions = ()
        result = manager.health_check()
        self.assertFalse(result.value)


class InputValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = PermissionManager()

    def test_check_permission_raises_validation_error_result_for_invalid_module_type(
        self,
    ) -> None:
        result = self.manager.check_permission(123, Operation.EXECUTION_PLAN_CREATE)  # type: ignore[arg-type]
        self.assertFalse(result.success)
        self.assertIsInstance(result.error, ValidationError)

    def test_check_permission_raises_validation_error_result_for_invalid_operation_type(
        self,
    ) -> None:
        result = self.manager.check_permission(Module.PLANNER, "NotAnOperation")  # type: ignore[arg-type]
        self.assertFalse(result.success)
        self.assertIsInstance(result.error, ValidationError)


class LoggingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = PermissionManager()

    def test_check_permission_logs_timestamp_module_operation_result_reason(self) -> None:
        with self.assertLogs("permission_manager", level="INFO") as captured:
            self.manager.check_permission(Module.PLANNER, Operation.EXECUTION_PLAN_CREATE)

        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertIn("module=Planner", message)
        self.assertIn("operation=ExecutionPlan作成", message)
        self.assertIn("result=Allow", message)
        self.assertIn("reason=", message)

    def test_check_permission_log_message_does_not_contain_raw_configuration_payload(
        self,
    ) -> None:
        with self.assertLogs("permission_manager", level="INFO") as captured:
            self.manager.check_permission(Module.PLANNER, Operation.EXECUTION_PLAN_CREATE)

        message = captured.records[0].getMessage()
        self.assertNotIn("PermissionEntry(", message)
        self.assertNotIn(repr(DEFAULT_PERMISSIONS), message)

    def test_reload_failure_logs_configuration_error_reason_only(self) -> None:
        manager = PermissionManager(config_client=_FailingConfigurationClient("config unavailable"))

        with self.assertLogs("permission_manager", level="WARNING") as captured:
            manager.reload()

        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertIn("module=permission_manager", message)
        self.assertIn("operation=reload", message)
        self.assertIn("result=Failure", message)
        self.assertIn("reason=config unavailable", message)


class DefaultPermissionsDataIntegrityTest(unittest.TestCase):
    def test_default_permissions_matches_design_section_3_4_table_exactly(self) -> None:
        expected = {
            Module.PLANNER: Operation.EXECUTION_PLAN_CREATE,
            Module.DESIGNER: Operation.DESIGN_CREATE,
            Module.EXECUTOR: Operation.PULL_REQUEST_CREATE,
            Module.REVIEWER: Operation.REVIEW_CREATE,
            Module.SCHEDULER: Operation.WORKFLOW_START,
            Module.KNOWLEDGE_MANAGER: Operation.KNOWLEDGE_UPDATE,
            Module.COMMAND_ROUTER: Operation.COMMAND_DISPATCH,
        }

        self.assertEqual(len(DEFAULT_PERMISSIONS), 7)

        actual = {entry.module: entry.operation for entry in DEFAULT_PERMISSIONS}
        self.assertEqual(actual, expected)

        for entry in DEFAULT_PERMISSIONS:
            self.assertIs(entry.effect, Effect.ALLOW)


if __name__ == "__main__":
    unittest.main()
