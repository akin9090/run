"""配線層(Phase 0)のCLIエントリポイント。

外部サービスに一切接続せず、1つの合成Workflowを最後まで実行して結果を表示する。
"""

import argparse
import sys

from bootstrap.wiring import build_application
from bootstrap.workflow import run_workflow
from foundation.utils import generate_id
from planner.types import NormalizedRequest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Development Pipeline bootstrap runner")
    parser.add_argument("instruction", help="自然言語の実行指示(例: 'LP改善')")
    parser.add_argument("--business-goal", default="", help="事業目的(例: 'LINE登録数最大化')")
    args = parser.parse_args(argv)

    app = build_application()
    request = NormalizedRequest(
        workflow_id=generate_id(),
        command=args.instruction,
        request_text=args.instruction,
    )

    result = run_workflow(app, request, business_goal=args.business_goal)
    if not result.success:
        print(f"workflow failed: {result.error}", file=sys.stderr)
        return 1

    print(result.value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
