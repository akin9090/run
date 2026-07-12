"""21モジュール(M00〜M21、M18はM03への統合により欠番)のうち、Foundation(M00)
を除く20モジュールを依存順に実インスタンス化する配線層本体。

Foundation(M00)は全モジュールが依存する共通基盤(`BaseModule`/`Result[T]`等の
Common Interface)であり、それ自体が実行時にインスタンス化されるコンポーネントでは
ないため、`Application`/`Application.all_modules()`には含まれない。

依存順序: Foundation(暗黙、共通基盤として利用) → Configuration Manager → 他モジュール
(全てconfig経由でConfigurationClientを共有) → Cross-module依存を持つモジュール
(Context Manager, GitHub Manager経由のPR Creator/Connector、Command Router経由の
Scheduler等)。

各コンストラクタ引数は、事前調査(各モジュールの`__init__`実読)に基づき実際の
シグネチャに一致させている。詳細は`.superpowers/sdd/task-4-report.md`を参照。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from architect.module import ArchitectModule
from bootstrap.adapters import NotificationChannelConnectorBridge
from bootstrap.config import build_configuration_manager
from bootstrap.stub_services import (
    StubCodexAdapter,
    StubCommandExecutor,
    StubFableClient,
    StubHttpClient,
    StubHttpTransport,
    StubPRCreatorHttpTransport,
)
from command_router.router import CommandRouter
from configuration_manager.manager import ConfigurationManager
from connector.connector import SlackDiscordConnector
from connector.discord_adapter import DiscordAdapter
from connector.slack_adapter import SlackAdapter
from context_manager.manager import ContextManager
from design_auditor.module import DesignAuditor
from executor.executor import Executor
from executor.repository_guard import RepositoryGuard
from foundation.base_module import BaseModule
from foundation.logger import get_logger
from foundation.result import Result
from github_manager.client import GitHubClient
from github_manager.github_manager import GitHubManager
from knowledge_manager.knowledge_manager import KnowledgeManager
from knowledge_manager.store import KnowledgeStore
from monitoring.collector import MetricsCollector
from monitoring.health_checker import HealthChecker
from monitoring.monitoring_module import MonitoringModule
from monitoring.reporter import ReportGenerator
from notification.history import NotificationHistoryStore
from notification.service import NotificationModule
from notification.types import Channel
from permission_manager.permission_manager import PermissionManager
from planner.planner import Planner
from pr_creator.github_client import GitHubPullRequestClient
from pr_creator.pr_creator import PRCreator
from reviewer.reviewer import ReviewerModule
from scheduler.command_router_client import RawCommand
from scheduler.scheduler_module import SchedulerModule
from state_manager.manager import StateManager
from task_queue.queue_manager import TaskQueueManager
from tester.models import TesterConfig
from tester.tester import Tester
from weekly_reviewer.models import WeeklyReviewerConfig
from weekly_reviewer.weekly_reviewer import WeeklyReviewer


class _CommandRouterClientAdapter:
    """SchedulerModule(M14)が要求する`CommandRouterClient` Protocolの実装。

    Scheduler→Command Routerの一方向依存のみを持つ(設計書M05/M14の循環依存解消方針)。
    実体は`CommandRouter.receive()`をそのまま呼び出す薄いアダプタであり、`classify`/
    `route`/`dispatch`等の他インターフェースは呼び出さない。
    """

    def __init__(self, command_router: CommandRouter) -> None:
        self._command_router = command_router

    def receive(self, raw_command: RawCommand) -> Result[Any]:
        return self._command_router.receive(raw_command)


@dataclass
class Application:
    """21モジュールのうちFoundation(M00)を除く20モジュールの実インスタンスを束ねる。

    Foundationは全モジュールが依存する共通基盤であり、それ自体は実行時に
    インスタンス化されるコンポーネントではないため、フィールド・
    `all_modules()`のいずれにも含まれない。
    """

    configuration_manager: ConfigurationManager
    state_manager: StateManager
    task_queue: TaskQueueManager
    knowledge_manager: KnowledgeManager
    permission_manager: PermissionManager
    planner: Planner
    architect: ArchitectModule
    design_auditor: DesignAuditor
    executor: Executor
    tester: Tester
    pr_creator: PRCreator
    reviewer: ReviewerModule
    weekly_reviewer: WeeklyReviewer
    github_manager: GitHubManager
    context_manager: ContextManager
    connector: SlackDiscordConnector
    notification: NotificationModule
    monitoring: MonitoringModule
    scheduler: SchedulerModule
    command_router: CommandRouter

    def all_modules(self) -> list[BaseModule]:
        return [
            self.configuration_manager,
            self.state_manager,
            self.task_queue,
            self.knowledge_manager,
            self.permission_manager,
            self.planner,
            self.architect,
            self.design_auditor,
            self.executor,
            self.tester,
            self.pr_creator,
            self.reviewer,
            self.weekly_reviewer,
            self.github_manager,
            self.context_manager,
            self.connector,
            self.notification,
            self.monitoring,
            self.scheduler,
            self.command_router,
        ]


def build_application(*, use_real_github: bool = False, use_real_slack: bool = False) -> Application:
    """21モジュール(Foundationを除く20モジュール)を配線した`Application`を返す。

    `use_real_github=True`の場合、GitHub Manager(M20)はスタブHttpTransportではなく
    実際のGitHub REST API(標準ライブラリ`urllib`のみを用いる`UrllibHttpTransport`、
    `src/github_manager/client.py`に既存)へ接続する。トークンは環境変数`GITHUB_TOKEN`
    からのみ取得し(値そのものをコード・設定ファイルに書き込まない)、未設定の場合は
    `RuntimeError`を送出する。GitHub Managerは設計上Read Onlyのみ(3.5節)であり、
    PR Creator(書き込み経路)は本フラグの対象外(引き続きスタブのまま)。

    `use_real_slack=True`の場合、Connector(M21)のSlackAdapterはスタブHttpClientでは
    なく実際のSlack Web API(標準ライブラリ`urllib`のみを用いる`UrllibHttpClient`、
    `src/connector/http_client.py`に既存)へ接続する。トークンは環境変数
    `SLACK_BOT_TOKEN`からのみ取得し、未設定の場合は`RuntimeError`を送出する。
    DiscordAdapterは本フラグの対象外(引き続きスタブのまま、Phase 1-D相当)。
    """
    startup_parameters: dict[str, str] = {}
    if use_real_github:
        github_token = os.environ.get("GITHUB_TOKEN", "")
        if not github_token:
            raise RuntimeError("use_real_github=True の場合、環境変数 GITHUB_TOKEN の設定が必要です。")
        startup_parameters["github_manager.github_access_token"] = github_token
    if use_real_slack:
        slack_token = os.environ.get("SLACK_BOT_TOKEN", "")
        if not slack_token:
            raise RuntimeError("use_real_slack=True の場合、環境変数 SLACK_BOT_TOKEN の設定が必要です。")
        startup_parameters["connector.slack_bot_token"] = slack_token

    config = build_configuration_manager(startup_parameters=startup_parameters)
    load_result = config.load(
        config._source
    )  # noqa: SLF001 - 初回load(build_configuration_manager()はunloaded状態で返す仕様)
    if not load_result.success:
        raise RuntimeError(f"configuration load failed: {load_result.error}")

    state_manager = StateManager(config_client=config)
    task_queue = TaskQueueManager(config_client=config)
    knowledge_manager = KnowledgeManager(store=KnowledgeStore())
    permission_manager = PermissionManager(config_client=config)
    planner = Planner(config_client=config)
    architect = ArchitectModule(config_client=config)
    design_auditor = DesignAuditor(config_client=config)
    executor = Executor(codex_adapter=StubCodexAdapter(), repository_guard=RepositoryGuard())

    # TesterConfig(src/tester/models.py)は全フィールド必須(既定値なし)。config/default.jsonに
    # "tester"セクションは存在しないため、StubCommandExecutorが実行内容を無視することを踏まえた
    # プレースホルダのコマンド列を明示的に埋める(新規configキーは追加しない)。
    tester_config = TesterConfig(
        build_command=["stub-build"],
        lint_command=["stub-lint"],
        unit_test_command=["stub-unit-test"],
        integration_test_command=["stub-integration-test"],
        regression_test_command=["stub-regression-test"],
        static_analysis_command=["stub-static-analysis"],
        command_timeout_seconds=60,
    )
    tester = Tester(config=tester_config, logger=get_logger("tester"), command_executor=StubCommandExecutor())

    if use_real_github:
        # transport省略時はGitHubClientの既定実装(標準ライブラリ`urllib`のみを用いる
        # UrllibHttpTransport)が使われ、実際のGitHub REST APIへ接続する。
        github_client = GitHubClient(configuration_client=config)
    else:
        github_client = GitHubClient(configuration_client=config, transport=StubHttpTransport())
    github_manager = GitHubManager(client=github_client)

    # PRCreator.github_client: config/default.jsonの`pr_creator.github_access_token`は
    # 空文字列であり(github_manager.github_access_tokenとは異なりTask 4時点では
    # プレースホルダ化されていない)、github_client未設定のままだと`_resolve_client()`が
    # `create_pr()`呼び出し時にConfigurationError("github_access_tokenを取得できません
    # でした。")を返す(2026-07 Workflow統合時に判明)。トークンをプレースホルダ化するだけでは
    # `_resolve_client()`がtransport未指定の`GitHubPullRequestClient`(既定=
    # UrllibHttpTransport、実ネットワーク接続)を構築してしまい、Phase 0の「外部サービスに
    # 一切接続しない」方針に反するため採用しない。代わりにGitHubManager(M20)と同じ方針で、
    # スタブHttpTransportを注入した`GitHubPullRequestClient`をここで明示的に構築し、
    # 遅延解決(_resolve_client()のconfig参照)経路そのものを回避する。
    pr_creator_github_client = GitHubPullRequestClient(
        access_token="phase0-stub-token", transport=StubPRCreatorHttpTransport()
    )
    pr_creator = PRCreator(configuration_client=config, github_client=pr_creator_github_client)
    reviewer = ReviewerModule(configuration_client=config)

    # WeeklyReviewerConfig(src/weekly_reviewer/models.py)は全フィールドに既定値
    # (review_period_days=7, business_goal=None)を持つため、引数なしで構築できる。
    weekly_reviewer_config = WeeklyReviewerConfig()
    weekly_reviewer = WeeklyReviewer(
        config=weekly_reviewer_config,
        logger=get_logger("weekly_reviewer"),
        fable_client=StubFableClient(),
    )

    context_manager = ContextManager(
        knowledge_manager=knowledge_manager,
        github_manager=github_manager,
        configuration_client=config,
    )

    # SlackDiscordConnector.health_check()は内部でAdapter.check_connection()経由の
    # HTTPリクエストを実行する。Adapterの既定http_client(UrllibHttpClient)のまま構築すると
    # 実ネットワーク接続・実トークンなしの環境ではhealth_check()がFalseを返すため、
    # use_real_slackがFalseの間はStubHttpClient(Connector(M21)向けスタブ)を明示的に
    # 注入したAdapterを使う。DiscordAdapterはPhase 1-D相当のため常にスタブのまま。
    if use_real_slack:
        slack_adapter: SlackAdapter = SlackAdapter(config_client=config)
    else:
        slack_adapter = SlackAdapter(config_client=config, http_client=StubHttpClient())
    connector = SlackDiscordConnector(
        config_client=config,
        slack_adapter=slack_adapter,
        discord_adapter=DiscordAdapter(config_client=config, http_client=StubHttpClient()),
    )

    # Notification(M15) ChannelConnector Protocolと Connector(M21) SlackDiscordConnector
    # の実際のシグネチャ差(send()の引数型・戻り値型)は、bootstrap/adapters.py
    # NotificationChannelConnectorBridgeが吸収する。to_connector_outbound_message()が
    # メッセージ単位でChannel→Platformを解決するため、Slack/Discordの両チャネルを
    # 単一のbridgeインスタンスで賄える(チャネルごとに別インスタンスを用意する必要はない)。
    notification_connector_bridge = NotificationChannelConnectorBridge(connector)
    notification = NotificationModule(
        config_client=config,
        channel_connectors={
            Channel.SLACK: notification_connector_bridge,
            Channel.DISCORD: notification_connector_bridge,
        },
        history_store=NotificationHistoryStore(),
    )

    monitoring = MonitoringModule(
        collector=MetricsCollector(),
        health_checker=HealthChecker(configuration_client=config),
        reporter=ReportGenerator(),
    )

    # SchedulerModuleはCommand Routerを直接importしない一方向依存(設計書M05/M14)を要求する。
    # command_routerは先に構築し、CommandRouterClient Protocolを満たす薄いアダプタ経由で渡す。
    command_router = CommandRouter(handlers={}, config_client=config)
    scheduler = SchedulerModule(
        command_router_client=_CommandRouterClientAdapter(command_router),
        configuration_client=config,
    )

    return Application(
        configuration_manager=config,
        state_manager=state_manager,
        task_queue=task_queue,
        knowledge_manager=knowledge_manager,
        permission_manager=permission_manager,
        planner=planner,
        architect=architect,
        design_auditor=design_auditor,
        executor=executor,
        tester=tester,
        pr_creator=pr_creator,
        reviewer=reviewer,
        weekly_reviewer=weekly_reviewer,
        github_manager=github_manager,
        context_manager=context_manager,
        connector=connector,
        notification=notification,
        monitoring=monitoring,
        scheduler=scheduler,
        command_router=command_router,
    )
