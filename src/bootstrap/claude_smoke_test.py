"""Phase 1-C: Executor(M09) ClaudeCodexAdapterの実接続を確認する手動スモークテスト。

`verify_api_key()`はAnthropic Models API(読み取り専用・トークン消費なし)を呼ぶのみで、
実装生成(`generate_implementation()`/`generate_tests()`、Claude APIの利用課金が発生する)
は行わない。

テストスイート(unittest discover)には含めず、ANTHROPIC_API_KEYが揃った時点で
ユーザーが手動実行する想定。

使い方:
    ANTHROPIC_API_KEY=sk-ant-xxx PYTHONPATH=src python -m bootstrap.claude_smoke_test
"""

import sys

from bootstrap.wiring import build_application


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001 - 引数なし、argparseと揃えた形にするための保持
    try:
        app = build_application(use_real_codex=True)
    except RuntimeError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1

    result = app.executor._codex_adapter.verify_api_key()  # noqa: SLF001 - スモークテスト専用の直接確認
    if not result.success:
        print(f"verify_api_key failed: {result.error}", file=sys.stderr)
        return 1

    print("OK: Claude Models API verification succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
