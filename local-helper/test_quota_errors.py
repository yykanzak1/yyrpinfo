import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import server


class QuotaErrorExtractionTests(unittest.TestCase):
    def test_nested_opencode_zen_free_usage_limit_is_preserved(self):
        payload = {
            "statusCode": 429,
            "error": {
                "type": "FreeUsageLimitError",
                "message": "Rate limit exceeded. Please try again later.",
            },
        }

        message = server._event_error_text(payload)

        self.assertIn("429", message)
        self.assertIn("FreeUsageLimitError", message)
        self.assertIn("Rate limit exceeded", message)

    def test_plain_error_string_is_preserved(self):
        self.assertEqual(server._event_error_text("FreeUsageLimitError"), "FreeUsageLimitError")


if __name__ == "__main__":
    unittest.main()
