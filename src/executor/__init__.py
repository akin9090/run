"""Executor (M09) パッケージ公開シンボル。

Build/Test/Lint実行、Pull Request作成に関するシンボルは公開しない
(Design Freeze監査によりTester/PR Creatorへ責務が一本化済み)。
"""

from executor.claude_codex_adapter import ClaudeCodexAdapter
from executor.codex_adapter import CodexAdapter, CodexConfig
from executor.errors import (
    CodexGenerationError,
    DesignDocumentNotFoundError,
    DesignNotApprovedError,
    MultiRepositoryNotAllowedError,
    RepositoryBoundaryViolationError,
)
from executor.executor import Executor
from executor.models import (
    ChangeType,
    ExecutionReport,
    GeneratedTest,
    ImplementationContext,
    ImplementationResult,
    ModifiedFile,
    RepositoryInfo,
)
from executor.repository_guard import RepositoryGuard

__all__ = [
    "Executor",
    "CodexAdapter",
    "CodexConfig",
    "ClaudeCodexAdapter",
    "RepositoryGuard",
    "ChangeType",
    "RepositoryInfo",
    "ModifiedFile",
    "GeneratedTest",
    "ImplementationContext",
    "ExecutionReport",
    "ImplementationResult",
    "DesignNotApprovedError",
    "DesignDocumentNotFoundError",
    "MultiRepositoryNotAllowedError",
    "RepositoryBoundaryViolationError",
    "CodexGenerationError",
]
