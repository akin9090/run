# CHANGELOG

すべての日付は Design Freeze 作業日を基準とする。本プロジェクトの絶対ルール(引継ぎドキュメント 2章)に従い、Design Freeze後の変更はここに追記し、次バージョン(v1.1等)として扱う。

## v1.0 (Design Freeze)

Design Freeze完了に向けた設計監査で、以下の修正を実施した。いずれも既存の詳細設計書または引継ぎドキュメント自身の記述に基づく是正であり、AIによる独自の仕様追加・推測による変更は行っていない。

### 追加

- **M00 Foundation** を新規に詳細設計書として作成。他モジュールが参照する F00(設計原則)/F01(Domain Model)/F02(Common Interface)/F03(Configuration Access Pattern)を初めて明文化した。従来はディレクトリ構成のみで、責務・Interfaceの記述が存在しなかった。

### 変更

- **M01 State Manager** / **M02 Task Queue**: 簡易フォーマットの設計監査を、M04以降で採用されている統一フォーマット(Overview/Responsibilities/Design/Constraints/Design Audit[F00-F03・重厚壮大化監査・実装可能性]/Summary)に再構成した。責務・API・データモデルの実質的な内容に変更はない。
- **M09 Executor (Codex)**: 責務から「テスト実行」「Build実行」「Lint実行」「Pull Request作成」を削除した。引継ぎドキュメント5章で既に決定されていた「Executorは実装のみ担当する」「Testerはテストのみ担当する」「PR CreatorはPR生成のみ担当する」という設計方針と、M09旧版の記述(2.1担当・3.2実装手順・3.5処理フロー)が矛盾していたための是正。Data FlowをArchitect→Design Auditor→Executor→Tester→PR Creator→Reviewerに統一した。
- **M10 Tester**: 処理フロー図の「Quality Gate PASS→Reviewer」を「Quality Gate PASS→PR Creator」に修正した。M11 PR Creatorの処理フロー定義(Tester→PR Creator→Reviewer)と矛盾していたための是正。
- **M05 Command Router**: Command Type表・Routingテーブルから「STATUS→Scheduler」の転送を削除し、「STATUS→State Manager」に変更した。M14 Schedulerとの相互依存(Scheduler→Command Router、Command Router→Scheduler の双方向)が「依存関係は一方向のみ」の原則に抵触していたための是正。依存方向はScheduler→Command Routerの一方向のみに確定した。
- **M14 Scheduler**: Command Routerとの依存方向がScheduler→Command Routerの一方向であることを明記した(機能変更なし)。

### 追加(実装仕様書作成時に発見した見落としの是正)

- **M00 Foundation** のF01 Domain Model一覧に **Repository** Domain(Repository/Branch/Commit/File/Diff情報)を追加した。M20 GitHub Managerの設計監査(F01)が既に「Repository Domain を利用する」と明記していたにもかかわらず、M00初版のF01一覧に定義漏れがあったための是正。実装仕様書(IS)作成時の整合性確認で発覚した。

### 統合

- **M03 Knowledge Manager** と **M18 Knowledge Manager** を統合した。両モジュールが同名・同責務(知識の一元管理・提供)で並存しており、「モジュール間の責務重複を禁止する」原則に抵触していたための是正。
  - 統合後の正式モジュールはM03とする(State Manager・Task Queueに続く基盤モジュールとして、番号順の位置づけが自然なため)。
  - M18は欠番とし、ファイルは統合先(M03)へのリダイレクトスタブとして残置する(モジュール名・番号を勝手に振り直さない)。
  - 統合にあたり、旧M03にあった「AIへのコンテキスト提供」責務は撤回した。これはContext Manager(M19)の責務(Knowledge Manager・Configuration Manager・GitHub Managerを参照してContextを生成すること)と重複していたため。Knowledge Managerは知識の提供(get/search/list)のみを担当し、Context生成は行わない。

## v1.0.1 (実装・統合レビューでの是正)

Design Freeze v1.0確定後、実装(src/・tests/)着手および統合レビューにより判明した、モジュール間の実際の結合(呼び出し互換性)に関する不整合を是正した。単体テスト(モジュール単位のフェイクによる検証)では検出できず、Integration Test相当のレビューで初めて判明したものである。

### 変更(Foundation / Configuration Manager)

- **M00 Foundation** `ConfigurationClient`(F03)の`get()`を`@staticmethod`から通常のインスタンスメソッドへ是正した。初版は`@staticmethod`と宣言していたが、Configuration Manager(M17)の実体および20モジュール中18モジュールがインスタンス経由(DIで注入されたインスタンス)で利用する実装になっており、契約と実体が矛盾していた。Context Manager(M19)・Monitoring(M16)の2モジュールが`type[ConfigurationClient]`(クラス参照)で受け取っていた箇所も、大多数の実装に合わせてインスタンス型に統一した。
- **M17 Configuration Manager**: `get(module_name, key)`が7つの固定カテゴリ(system/github/slack/discord/codex/fable/monitoring)のみを受け付け、それ以外のmodule_name(State Manager・Permission Manager等、各モジュールが自分自身の名前をmodule_nameとして渡す用途)を一律`NotFoundError`としていた。F03の契約はFoundation側で`module_name: str`と汎用的に定義されており、他モジュールの大多数(15モジュール以上)が「自モジュール名をmodule_nameとして渡す」前提で実装済みだったため、`Configuration.extra`(7カテゴリ以外の設定値を保持する汎用領域)を追加し、7カテゴリ以外のmodule_nameもここから解決できるようにした。
- **M17 Configuration Manager**: 未使用のまま放置されていた`ConfigurationVersion`データクラス(公開APIとして再エクスポートされていたが呼び出し元が皆無)を削除した。バージョン情報は既存の`Configuration.version`フィールドで代替済みであり、重複実装だったため。
- **M16 Monitoring**: `check_module()`内でハートビート鮮度閾値(300秒)がハードコードされ、設計書4.4「閾値はConfigurationにより管理する」に反していた。`CONFIG_KEY_HEARTBEAT_FRESHNESS_SECONDS`を追加し、他の閾値(Execution Time等)と同様にConfigurationClient経由で取得するよう是正した。
- **M19 Context Manager**: `WorkflowScope.repository`フィールド追加(GitHub Managerの`build_repository_context()`呼び出しに必要な引数)を、実装コードだけでなく`implementation_spec/IS19_Context_Manager_実装仕様書.md`にも反映した(初回修正時にコードのみ更新し、仕様書側が古いままになっていた)。

### 変更(Architect / Design Auditor)

- **M07 Architect**: `designer.py`の`create_design()`が`DesignDocument.metadata`を常に空(`{}`)のまま返しており、Design Auditor(M08)の4監査(要件充足・Architecture整合性・MVP適合性・品質)がいずれも`metadata`から監査対象情報を読み取れず、`audit()`が`workflow_id`欠落による`NotFoundError`で必ず失敗する状態だった。`build_metadata()`を追加し、DesignRequirement由来の`workflow_id`/`requirements`/`requirements_covered`/`features`/`content`をIS08の実装解釈メモに定義された既存スキーマ通りに格納するよう是正した(design_auditor側の実装・スキーマは変更せず、Architect側の出力を仕様に合わせた)。
- **M07 Architect**: 品質評価・過剰設計判定(`architecture_notes`/`quality_notes`)はDesign Auditorの責務であり、Architectが自己申告することは「Architectはレビューしない」(M07 4.3)に反するため、意図的に`metadata`へ設定しない方針とした(design_auditor側の安全側デフォルト「キー欠落時は違反なしとして扱う」に委ねる)。

### 変更(Notification / Slack Discord Connector)

- **M15 Notification**: `ChannelConnector`(`notification/channels.py`)の抽象メソッド名を`dispatch()`から`send()`へ是正した。`notification/service.py`が`connector.dispatch(message)`を呼び出す一方、実配信を担うConnector(M21)の公開インターフェースは設計書3.6のとおり`receive()`/`send()`/`health()`のみで`dispatch()`が存在せず、実際に接続すると`AttributeError`になる不整合だったための是正。`service.py`の呼び出し箇所とテスト用フェイク(`tests/notification/fakes.py`)も`send()`名に合わせて更新した。

### 変更(Scheduler / Command Router)

- **M14 Scheduler**: `command_router_client.py`が`ExecutionRequest`をdict形式(`request_id`/`workflow_id`等のキー)に変換してCommand Router(M05)の`receive()`へ渡していたが、Command Router側の`receive()`/`normalize()`は`RawCommand`(dataclass)の属性アクセス(`raw.command`等)を前提としており、実際に接続すると`AttributeError`になる不整合だった。Scheduler側にCommand Router設計書3.1節と同一形状(command_id/source/user_id/timestamp/command/attachments/metadata)の`RawCommand`を独自定義し(具象クラスはimportせずダックタイピングで契約を満たす)、`_to_raw_command()`をこの形状で変換するよう是正した。
- **M05 Command Router**: `receive()`/`normalize()`の引数型を具象クラス`RawCommand`から構造的契約`RawCommandLike`(Protocol)へ変更し、Scheduler等の他モジュールがRawCommand契約を満たす値であれば具象クラスをimportせずに渡せることを明示した(振る舞いの変更なし)。

### 変更(Executor / Tester / PR Creator / Reviewer / Weekly Reviewer / GitHub Manager)

Executor(M09)→Tester(M10)→PR Creator(M11)→Reviewer(M12)→Weekly Reviewer(M13)の実装パイプライン全体を横断的にレビューし、各モジュール単体のテストでは検出できなかったデータ受け渡しの不整合を是正した。

- **M11 PR Creator** `quality_gate.py`が期待するキー(`build_passed`等のbool 6項目、`test_report.metadata`直下)と、Tester(M10)が実際に生成する成果物(`tester.models.TestReport`、判定結果は`quality_gate_result.status`("PASS"/"FAIL")に保持)が一致せず、品質ゲート判定が常にFAILしPR作成に到達できなかった。品質ゲートの6項目判定自体はTesterの責務(M10 2.1)であるため、PR Creator側を「Testerが既に判定した`quality_gate_result.status`を確認するのみ」に是正し、独自の再判定を廃止した(Tester側は変更なし)。
- **M11 PR Creator** `create_pr()`が生成する`PullRequest.metadata`に、Reviewer(M12)の`review()`が必須とする`design_document`/`implementation_result`/`test_report`/`business_goal`が含まれておらず、`Reviewer.review()`が必ず`ValidationError`になっていた。`CreatePullRequestInput.project_context`経由でこれらを受け取り`PullRequest.metadata`へ転記するよう是正した(Reviewerは他モジュールの内部型に依存しない設計(IS12)のため、Reviewer側は変更せず、PR Creator側でmetadataを整えた)。
- **M11 PR Creator** `checks.check_business_alignment`が参照する`pull_request.metadata["summary"]`が存在せず(全文Markdownの`body`キーのみ存在)、事業目的キーワード一致チェックが常に無効化されていた。`create_pr()`でPRテンプレートの`summary`を`metadata["summary"]`としても格納するよう是正した(Reviewer側は変更なし)。
- **M11 PR Creator** `template.py`の変更ファイル一覧生成が、存在しない`Implementation.metadata["changed_files"]`を参照しており常に空になっていた。変更ファイルの実体はExecutor(M09)の`ImplementationResult.modified_files`にあるため、`implementation_result`をExecutorの実際の成果物として扱い`modified_files`から変更ファイル一覧を取得するよう是正した(`Implementation.metadata["changed_files"]`が明示的に与えられた場合は後方互換のフォールバックとして残した)。同様にTest Result欄も、存在しない`test_report.metadata["test_result_summary"]`ではなくTesterが実際に生成する`TestReport.summary`を参照するよう是正した。
- **M20 GitHub Manager** `get_pull_request()`がGitHub REST APIレスポンスに含まれる`merged`/`merged_at`を破棄しており、Weekly Reviewer(M13)の`collect()`(`weekly_reviewer.collector`)が必要とするMerge済み判定用フィールドを誰も供給していなかった。`PullRequestMetadata.metadata`へ`merged`/`merged_at`を格納するよう是正した(追加のAPI呼び出しは発生しない。`weekly_reviewer.collector`側は変更なし)。
- **M11 PR Creator と M20 GitHub Manager の役割分担**: PR Creatorが独自にGitHub書き込みAPI(`github_client.py`)を実装している点は、GitHub Manager(M20)の設計書2.2節が「Pull Request作成」を明示的に対象外としているため適切な分離であり是正不要と判断した。読み取り系の`get_pull_request()`はPR Creator・GitHub Managerの双方に存在するが、GitHub Managerの`PullRequestMetadata`は最小取得方針(M20 4.4)によりPull Request URLを含まない設計であり、PR Creatorの作成直後URL確認に転用できないため、現状の分離を維持した(理由を`pr_creator/github_client.py`にコメントとして明記)。

これらの修正に伴い、`tests/pr_creator/test_quality_gate.py`をダックタイピング前提のテストへ全面更新し、`tests/pr_creator/test_template.py`・`tests/github_manager/test_github_manager.py`にケースを追加し、`tests/pr_creator/test_pr_creator.py`(既存実装に欠けていた`PRCreator`本体の単体テスト)を新設した。

### Design Freeze 完了条件との対応

引継ぎドキュメント7章が定めるDesign Freeze完了条件7項目に対する対応状況。

| 条件 | 対応 |
|---|---|
| 全モジュール監査済 | M00〜M03を含む全22モジュール(M18は欠番)がM04以降と同一の監査フォーマットで揃った |
| 責務確定 | M09/M10/M11、M03/M18の責務重複を解消し確定した |
| Interface確定 | M00でCommon Interface(BaseModule, Result[T])を定義し、全モジュールが整合するよう確認した |
| Data Flow確定 | Executor→Tester→PR Creator→Reviewerの一連のFlowを全モジュールで一致させた |
| Dependency確定 | Command Router⇔Schedulerの相互依存をScheduler→Command Routerの一方向に確定した |
| MVP監査完了 | 全モジュールの重厚壮大化監査(対象外機能リスト)を確認済み |
| CHANGELOG反映済 | 本ファイルとして反映済み |

詳細は `DESIGN_FREEZE_v1.0.md` を参照。

## v1.1.0 (Phase 0: 配線層)

Design Freeze v1.0確定後、22モジュール(M00〜M21、M18は欠番)全体の統合配線、およびこれらを直列に呼び出す合成Workflowの実装により、外部サービスに一切接続しない状態での端末到達(Planner→Architect→Design Auditor→Executor→Tester→PR Creator→Reviewer)を実現した。Phase 0 Bootstrap段階として、実装可能性・モジュール間結合の動作確認を主目的とする。

### 追加(Task 1: スタブ外部アダプタ)

- **`bootstrap/stub_services.py`**: Executor(M09)・Tester(M10)・PR Creator(M11)が外部サービス(Codex・Command Executor・GitHub API)へアクセスする箇所を、Phase 0での外部接続を回避するためスタブ実装で置き換えた。CodexのImplementation生成、CommandExecutorのコマンド実行、GitHub APIへのPull Request作成をそれぞれ合成データで返す。

### 追加(Task 2: ConfigurationManager 配線層)

- **`bootstrap/wiring.py`**: 22モジュール全体を依存関係通りにインスタンス化し、 Application 集約根を構成する `build_application()` 関数を実装した。各モジュールの必須設定(例: State Manager の backend_path)をConfigurationManager経由で取得し、通常の本番実行と同じ設定フローで初期化する。Configuration自体は Phase 0 想定の固定値セット(github_access_token欠落等で検証エラーになるが、ConfigurationManager側で graceful に処理する)を使用。

### 追加(Task 3: 型不整合アダプタ)

- **`bootstrap/adapters.py`**: Planner→Architect→Design Auditor→Executor→Tester→PR Creator→Reviewer の各ステップで型・データ形式の不整合を吸収する変換関数群を実装した。
  - `to_architect_execution_plan()`: Planner の `ExecutionPlan` → Architect が期待する形式へ変換(plan_id, requirement_list等)
  - `to_executor_approved_design()`: Design Auditor の `ApprovedDesign` → Executor の `metadata` 形式へ変換
  - `to_executor_implementation_view()`: Executor の `ImplementationResult` → PR Creator が「内側の `Implementation` と 外側の `modified_files` の両方」を参照できる統合ビューへ変換

### 追加(Task 4: 21モジュール結線・Application構築)

- 詳細設計書・実装仕様書で定義された 22モジュール全体(M00〜M21、M18は欠番)の Dependency Injection を `bootstrap/wiring.py::build_application()` に統合した。以下を確認:
  - 全モジュール(Foundation M00 含む)のコンストラクタパラメータが揃う
  - ConfigurationManager(M17)経由の設定値取得が全モジュール共通
  - State Manager(M01)・Knowledge Manager(M03)・Context Manager(M19)等の基盤層が正常に初期化される
  - Executor/Tester/PR Creator の外部サービス依存をスタブで置き換え可能
  - Unit Test 総数 871件が全て通過

### 追加(Task 5: 合成Workflow 実行確認)

- **`bootstrap/workflow.py`**: NormalizedRequest(Planner入力)を起点に、7つのモジュール(Planner→Architect→Design Auditor→Executor→Tester→PR Creator→Reviewer)を直列に呼び出し、ReviewOutcome(最終成果物)まで到達する `run_workflow()` 関数を実装した。各ステップの Result 型をチェックし、失敗時は短絡(early return)して後続をスキップする。
- Planner〜Reviewer のいずれも `business_goal` パラメータを生成しないため、Workflow関数の引数として明示的に受け取り、PR Creator経由で Reviewer まで伝播させる(project_context["business_goal"]経由)。
- Executor/Tester/PR Creator のスタブ呼び出し完了確認、および end-to-end の成功フロー(`result.success = True`)を検証。

### 追加(Task 6: CLIエントリポイント)

- **`src/bootstrap/run.py`**: argparse ベースのコマンドラインインターフェース。引数 `instruction`(自然言語指示、例:"LP改善") と `--business-goal`(事業目的、例:"LINE登録数最大化") を受け取り、以下を実行:
  1. `build_application()` で完全な Application を構築
  2. instruction を NormalizedRequest(command/request_text フィールド)へマッピング
  3. `run_workflow()` で 7モジュール合成を実行
  4. ReviewOutcome をそのまま標準出力へ表示
  5. 失敗時は stderr へエラーログを出力し、exit code 1 で終了

- **テスト** (`tests/bootstrap/test_run.py`): stdout キャプチャにより ReviewOutcome の出力確認、exit code 0 の確認。

### 検証結果

| 項目 | 結果 |
|---|---|
| Unit Test(871件既存 + 1新規) | 全 872件通過 |
| 手動スモークテスト(`python -m bootstrap.run`) | 例外なく完了、ReviewOutcome表示確認 |
| Ruff チェック | All checks passed |
| Black フォーマット | 303 files unchanged |
| 外部サービス接続 | なし(スタブのみ) |
| 設定値取得失敗の graceful handling | ConfigurationManager が検証エラーをログし、モジュール初期化継続 |
