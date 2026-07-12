"""Phase 1-B: Connector(M21) SlackAdapterの実接続を確認する手動スモークテスト。

`check_connection()`はSlack `auth.test` APIを呼ぶのみで、メッセージ投稿は行わない
(read-only相当)。実際のメッセージ送信(`deliver()`)を試す場合は、本スクリプトで
接続を確認した後、別途判断の上で行うこと。

テストスイート(unittest discover)には含めず、SLACK_BOT_TOKENが揃った時点で
ユーザーが手動実行する想定。

使い方:
    SLACK_BOT_TOKEN=xoxb-xxx PYTHONPATH=src python -m bootstrap.slack_smoke_test
"""

import sys

from bootstrap.wiring import build_application


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001 - 引数なし、argparseと揃えた形にするための保持
    try:
        app = build_application(use_real_slack=True)
    except RuntimeError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1

    result = app.connector._slack_adapter.check_connection()  # noqa: SLF001 - スモークテスト専用の直接確認
    if not result.success:
        print(f"check_connection failed: {result.error}", file=sys.stderr)
        return 1

    if not result.value:
        print("check_connection returned False: Slack API did not report ok=true", file=sys.stderr)
        return 1

    print("OK: Slack auth.test succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
