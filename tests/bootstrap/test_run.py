import io
import unittest
from contextlib import redirect_stdout

from bootstrap.run import main


class MainTest(unittest.TestCase):
    def test_main_prints_review_outcome_for_valid_instruction(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = main(["LP改善", "--business-goal", "LINE登録数最大化"])

        self.assertEqual(exit_code, 0)
        self.assertIn("next_module", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
