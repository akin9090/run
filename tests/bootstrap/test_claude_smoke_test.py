"""Phase 1-C: claude_smoke_test.pyの引数解析・エラーパスのテスト(実ネットワーク接続は行わない)。"""

import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from bootstrap.claude_smoke_test import main


class ClaudeSmokeTestMainTest(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_main_returns_1_when_anthropic_api_key_missing(self) -> None:
        buffer = io.StringIO()
        with redirect_stderr(buffer):
            exit_code = main([])

        self.assertEqual(exit_code, 1)
        self.assertIn("ANTHROPIC_API_KEY", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
