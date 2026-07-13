# AI Development Pipeline 本番運用ロードマップ (v1.1)

> **スコープについての注記**: 本書は複数の独立したサブシステム(配線層・5つの外部サービス接続・CI/CD・段階的ロールアウト)にまたがるため、`writing-plans`スキールが定める「1機能=1実装計画」の粒度ではなく、フェーズ単位のロードマップとして構成する。**各フェーズを実際に着手する際は、そのフェーズ単独で`writing-plans`スキルによるbite-sized TDD計画書を別途作成すること。**

**現在地**: Design Freeze v1.0確定済み、全21モジュールをPython 3.13で実装(src/)、unittest 809件PASS、モジュール間結合レビューで発見した18件超の不整合を是正済み、git初期化・ローカルコミット済み。

**このロードマップのゴール**: 上記の「動くコードの集合」を、Slack/Discordから指示するだけでAIがPRまで作成する実運用パイプラインへ引き上げる。

**大方針**: 引継ぎドキュメントの絶対ルール「MVP優先・重厚壮大化しない」に従い、全外部サービスを同時に本接続するのではなく、**1接続ずつ・段階的に**進める。各フェーズは単独でデモ可能な状態を維持する。

---

## 現状の欠落点(なぜ「実装済み」で終わらないか)

21モジュールは個別に実装・単体テスト済みだが、以下が未整備なため、まだ「動くパイプライン」ではない。

1. **配線層が存在しない**: どのモジュールも他モジュールをDI(依存性注入)で受け取る設計だが、実際に21個のインスタンスを生成して繋ぎ込む`main.py`相当のコードがリポジトリのどこにも無い。
2. **外部サービスは全てフェイク**: GitHub API・Slack API・Discord API・Codex・Fableへの実接続コードはゼロ(意図的にProtocol/Adapterで隔離されている)。
3. **Secret管理が未整備**: `config/default.json`はプレースホルダのみ。
4. **CI/CDが無い**: pushやPR作成をトリガーにテストを自動実行する仕組みが無い。
5. **リモートリポジトリが無い**: ローカルgitのみ。

---

## Phase 0: 配線層の構築(最優先・全フェーズの前提条件)

**目的**: 外部サービスに一切繋がずとも、21モジュールをインメモリで実際に接続し、1つのWorkflow(例: Slackコマンド相当の文字列入力→Planner→Architect→Design Auditor→Executor→Tester→PR Creator→Reviewer)が例外なく最後まで流れることを実証する。

**成果物**:
- `src/bootstrap/` (新設): 各モジュールのインスタンス化とDI配線を行う`Application`クラス
- `src/bootstrap/wiring.py`: Foundation `BaseModule`実装の生成順序(Foundation→State Manager/Task Queue/Knowledge Manager/Permission Manager/Configuration Manager→Command Router→業務モジュール群→周辺モジュール群)を1箇所に集約
- 全モジュール間のフェイクではない「実オブジェクト同士」の結合テスト(`tests/bootstrap/test_end_to_end_synthetic.py`): 外部サービスはこの時点でも全てフェイク(Slack/Discord/GitHub/Codex/Fable)のまま、モジュール自体は全て実装コードを使う

**このフェーズで解決すべき既知の未解決事項**(統合レビューIS20/IS21等で「要確認事項」として残されたもの):
- Notification→Connectorの実配線アダプタ(`NotificationMessage`⇔`OutboundMessage`変換)— **既にバックグラウンドタスク`task_a1d98d6b`として着手済み**
- GitHub Managerの`build_repository_context()`が`target_files`/`changed_files`を常に空リストで返す制約の解消方針(Executorの`ExecutionReport.modified_files`から補完するか、設計上の制約として維持するかの決定)
- Configuration Managerの`extra`領域を使い、各モジュールの実運用設定(リトライ回数・タイムアウト等)を`config/default.json`に実値として追加

**完了条件**: Slackを一切使わず、CLIから`echo "LP改善" | python -m bootstrap.run`のような形で1 Workflowが例外なくPRCreator(フェイク)まで到達する。

---

## Phase 1: 外部サービス実接続(1つずつ)

Phase 0の配線層ができて初めて着手可能。優先順位は「止まると全体が動かなくなる依存度の高さ」順。

### 1-A. GitHub(最優先)

**理由**: PR Creator・GitHub Manager・Executor・Weekly Reviewerが依存する、パイプラインの中核。

**成果物**:
- `src/github_manager/client.py`の`GitHubClient` Protocol実装として、実HTTPクライアント(`urllib`または`requests`、コーディング規約に照らし追加依存の要否を判断)による`RealGitHubClient`を追加
- Personal Access Token(GitHub App推奨)による認証、Configuration Manager経由でのToken取得(`config.get("github_manager", "access_token")`、ログ出力禁止を徹底)
- テスト用GitHubリポジトリ(実在の空リポジトリ)に対する疎通確認スクリプト

### 1-B. Slack(次点)

**理由**: 引継ぎドキュメントが掲げる主要な利用シーン「Slackから指示するだけ」の入口。

**成果物**:
- `src/connector/slack_adapter.py`の実HTTP実装(Slack Events API + Web API)
- Slack Appの作成・Bot Token発行(ユーザー側作業。トークンは環境変数経由でのみ受け渡し、リポジトリに含めない)
- Command Router連携確認(Slackコマンド→NormalizedCommand変換の実データでの検証)

### 1-C. Codex(Executor実行エンジン)

**理由**: 実装コード生成そのものを担うため、Phase 1-A/1-Bが機能してもコード生成ができなければPRの中身が空になる。

**成果物**:
- `src/executor/codex_adapter.py`の`CodexAdapter` Protocol実装として、実Codex CLI/API呼び出しクラスを追加
- 単一の小さなタスク(例: 1関数追加)での試験実行

### 1-D. Discord(任意・低優先)

Slackが機能すれば必須ではない。ユーザーの実利用チャネルに応じて着手判断。

### 1-E. Fable(Weekly Reviewer、最低優先)

週次実行のみで日次フローをブロックしないため、Phase 1の中で最後に着手してよい。

---

## Phase 2: CI/CD構築

**目的**: このリポジトリ自身の変更(および将来Executorが作るPR)に対して、テスト・Lintを自動実行する。

**成果物**:
- `.github/workflows/ci.yml`: push/PR時に`pytest`(または`unittest`)・`ruff check`・`black --check`を実行
- Design Freezeの絶対ルール「設計書を唯一の正とする」を機械的に補助する簡易チェック(例: `src/`配下の変更が`design/`の同名モジュールの責務記述と矛盾しないかを見るのは人手レビューに委ねる。自動化はテスト/Lintのみに限定し過剰なゲートを増やさない)

---

## Phase 3: 段階的ロールアウト

**方針**: 一度に全リポジトリ・全チャネルを対象にしない。

1. **Shadow Mode**: 実際のPR作成は行わず、Command Router〜Reviewerまでの判断結果をログ・Slack通知のみで出力し、人間が結果を検証する期間を設ける
2. **限定スコープ**: 1つの小さなテスト用リポジトリのみを対象にPermission Manager側のOperation許可を絞る
3. **本番拡大**: 実績を見ながら対象リポジトリ・チャネルを拡大

**成果物**:
- Permission Managerの`DEFAULT_PERMISSIONS`をShadow Mode用に一時的に絞ったプロファイル
  (`SHADOW_MODE_PERMISSIONS`)として`src/permission_manager/default_permissions.py`に
  定義し、`PermissionManager`のコンストラクタ引数(`permissions`)経由で差し替え可能にする
  (2026-07実装時の是正: `PermissionManager.reload()`はConfigurationClientの戻り値を
  そのまま`PermissionEntry`として扱うため、JSONプリミティブしか保持できない
  `config/default.json`からは読み込めない。詳細は
  `docs/superpowers/specs/2026-07-13-phase3-shadow-mode-design.md`参照)
- Monitoring→Notificationの実アラート配線確認(障害時に人間へ通知が届くこと自体の動作確認)

---

## Phase 4: 実サービスありのIntegration Test

Phase 1が最低1系統(GitHub)完了した時点で着手可能。

**成果物**:
- `tests/integration/`(新設、既存の`tests/`とは別ディレクトリ): 実GitHub上のテスト専用リポジトリに対し、Planner→...→PR Creatorの一連の流れを実行し、実際にPRが作成されることを確認する自動テスト(CI常時実行ではなく、手動または低頻度スケジュール実行を想定。外部サービスのレート制限・コストに配慮)

---

## 推奨する着手順序

Phase 0(配線層)→ Phase 1-A(GitHub)→ Phase 2(CI/CD、この時点でリポジトリ自身の品質ゲートが機能し始める)→ Phase 1-B(Slack)→ Phase 3(Shadow Mode開始)→ Phase 1-C(Codex)→ Phase 4(Integration Test)→ Phase 1-D/1-E(Discord/Fable)→ Phase 3本番拡大。

## 次にやること

このロードマップのうち、**Phase 0(配線層の構築)** から着手するのが最も合理的(全フェーズの前提条件であり、外部サービスのアカウント準備を待たずに今すぐ着手できるため)。着手する際は、`writing-plans`スキルでPhase 0単独のbite-sized TDD実装計画書を作成する。
