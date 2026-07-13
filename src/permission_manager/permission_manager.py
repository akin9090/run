"""Permission Manager (M04) 本体。

Module × Operation の組み合わせのみで実行可否を判定する。認証・OAuth・ログイン管理・
Secret管理・業務ロジックは一切扱わない(IS04 1. モジュール概要 / 設計書1.)。

責務外操作の禁止(設計書4.1 / IS04 5.3): 本モジュールは foundation.* と
default_permissions.py / models.py のみに依存し、GitHub API・Slack・Discord・Codex実行・
Workflow変更・Task変更のいずれのクライアントもimportしない。
"""

from __future__ import annotations

import logging

from foundation.base_module import BaseModule
from foundation.errors import ConfigurationError, PermissionDeniedError, ValidationError
from foundation.interfaces import ConfigurationClient
from foundation.logger import get_logger
from foundation.result import Result
from foundation.validation import require_in, require_not_none

from .default_permissions import DEFAULT_PERMISSIONS
from .models import Effect, Module, Operation, PermissionEntry

MODULE_NAME = "permission_manager"

# 判定理由(設計書4.4 / IS04 5.2)。ログ・Result.errorの両方でこの文言を使い回す。
_REASON_FAILSAFE_EMPTY_TABLE = "permission情報が取得できないためフェイルセーフとしてDenyを返す"
_REASON_ALLOW = "Module×OperationがPermissionテーブルにAllow登録されている"
_REASON_DENY_UNDEFINED = "Module×Operationの組み合わせが許可テーブルに存在しないためDeny"


class PermissionManager(BaseModule):
    """Module × Operation のみで実行可否を判定する。認証・業務ロジックは扱わない。"""

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

    def name(self) -> str:
        """BaseModule必須実装。'permission_manager' を返す。"""
        return MODULE_NAME

    def health_check(self) -> Result[bool]:
        """権限テーブルがロード済み(空でない)ことを確認する。"""
        return Result(success=True, value=bool(self._permissions))

    def check_permission(self, module: Module, operation: Operation) -> Result[bool]:
        """
        指定Moduleが指定Operationを実行可能か判定する(設計書3.3 check_permission)。

        Returns:
            Result[bool]:
                - value: True=Allow / False=Deny
                - success: 判定処理自体が正常に完了した場合はTrue(Denyも正常な判定結果でありsuccess=True)。
                  module/operationの型不正等、判定不能な入力エラーの場合のみsuccess=False。
                - error: Denyの場合、理由(reason)を保持する
                  `foundation.exceptions.PermissionDeniedError` を設定する(success=Trueのまま)。
                  Allowの場合はerror=None。
        """
        try:
            require_not_none(module, "module")
            require_not_none(operation, "operation")
            require_in(module, list(Module), "module")
            require_in(operation, list(Operation), "operation")
        except ValidationError as exc:
            return Result(success=False, value=None, error=exc)

        if not self._permissions:
            reason = _REASON_FAILSAFE_EMPTY_TABLE
            self._log_decision(module, operation, Effect.DENY, reason)
            return Result(success=True, value=False, error=PermissionDeniedError(reason))

        is_allowed = any(
            entry.module == module and entry.operation == operation and entry.effect is Effect.ALLOW
            for entry in self._permissions
        )

        if is_allowed:
            reason = _REASON_ALLOW
            self._log_decision(module, operation, Effect.ALLOW, reason)
            return Result(success=True, value=True, error=None)

        reason = _REASON_DENY_UNDEFINED
        self._log_decision(module, operation, Effect.DENY, reason)
        return Result(success=True, value=False, error=PermissionDeniedError(reason))

    def list_permissions(self, module: Module) -> Result[list[Operation]]:
        """
        指定Moduleに許可されているOperation一覧を取得する(設計書3.3 list_permissions)。

        Returns:
            Result[list[Operation]]:
                - value: 許可されたOperationのリスト(許可が1件もない場合は空リスト)
                - フェイルセーフ時(権限情報取得不可)も空リストを返す(許可側へ倒さない)
        """
        if not self._permissions:
            return Result(success=True, value=[])

        operations = [
            entry.operation for entry in self._permissions if entry.module == module and entry.effect is Effect.ALLOW
        ]
        return Result(success=True, value=operations)

    def reload(self) -> Result[bool]:
        """
        Permission定義を再読込する(設計書3.3 reload。MVPではシステム起動時のみ利用)。

        - config_clientが設定されている場合、ConfigurationClient.get("permission_manager", "permissions")
          経由で最新定義の取得を試みる。
        - 取得に失敗した場合、現在保持しているテーブル(初回はDEFAULT_PERMISSIONS)を維持したまま
          Result(success=False, value=False, error=ConfigurationError(...)) を返す。
        - 取得に成功した場合、内部テーブルを新しい定義で置き換え Result(success=True, value=True, error=None) を返す。
        """
        if self._config_client is None:
            # config_client未設定時はDEFAULT_PERMISSIONSを維持したまま何もしない。
            return Result(success=True, value=True, error=None)

        result = self._config_client.get(MODULE_NAME, "permissions")

        if not result.success or result.value is None:
            reason = self._extract_reason(result.error)
            self._log_reload(success=False, reason=reason)
            return Result(success=False, value=False, error=ConfigurationError(reason))

        self._permissions = tuple(result.value)
        self._log_reload(success=True, reason="ConfigurationClientから最新定義を取得し置き換えた")
        return Result(success=True, value=True, error=None)

    @staticmethod
    def _extract_reason(error: object) -> str:
        message = getattr(error, "message", None)
        if message:
            return str(message)
        return "permission定義の取得に失敗した"

    def _is_failsafe(self, reason: str) -> bool:
        return reason == _REASON_FAILSAFE_EMPTY_TABLE

    def _log_decision(self, module: Module, operation: Operation, effect: Effect, reason: str) -> None:
        level = logging.WARNING if effect is Effect.DENY and self._is_failsafe(reason) else logging.INFO
        self._logger.log(
            level,
            "module=%s operation=%s result=%s reason=%s",
            module.value,
            operation.value,
            effect.value,
            reason,
        )

    def _log_reload(self, *, success: bool, reason: str) -> None:
        level = logging.INFO if success else logging.WARNING
        result_label = "Success" if success else "Failure"
        self._logger.log(
            level,
            "module=%s operation=%s result=%s reason=%s",
            MODULE_NAME,
            "reload",
            result_label,
            reason,
        )
