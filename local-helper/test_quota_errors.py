import os
import sys
import unittest
from unittest.mock import MagicMock, patch

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


class AbortSessionTests(unittest.TestCase):
    def test_abort_posts_to_current_opencode_session(self):
        response = MagicMock()
        with patch.object(server, "_session_id", "session-123"), patch.object(
            server, "upstream", return_value=response
        ) as upstream:
            result = server.abort_current_session()

        upstream.assert_called_once_with("POST", "/session/session-123/abort", timeout=10)
        response.close.assert_called_once_with()
        self.assertTrue(result["ok"])

    def test_abort_without_session_does_not_call_upstream(self):
        with patch.object(server, "_session_id", None), patch.object(server, "upstream") as upstream:
            result = server.abort_current_session()

        upstream.assert_not_called()
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
