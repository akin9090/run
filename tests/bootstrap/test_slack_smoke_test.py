"""Phase 1-B: slack_smoke_test.pyの引数解析・エラーパスのテスト(実ネットワーク接続は行わない)。"""

import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from bootstrap.slack_smoke_test import main


class SlackSmokeTestMainTest(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_main_returns_1_when_slack_bot_token_missing(self) -> None:
        buffer = io.StringIO()
        with redirect_stderr(buffer):
            exit_code = main([])

        self.assertEqual(exit_code, 1)
        self.assertIn("SLACK_BOT_TOKEN", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
