import os
import unittest
from unittest.mock import patch

from agent.config import RedditConfig
from agent.reddit import RedditError, check_connection


class FoundationTests(unittest.TestCase):
    def test_missing_config(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "REDDIT_CLIENT_ID"):
                RedditConfig.from_env()

    def test_config_does_not_print_secrets(self):
        config = RedditConfig("private-id", "private-secret", "test-agent")
        self.assertNotIn("private-secret", repr(config))
        self.assertNotIn("private-id", repr(config))

    @patch("agent.reddit.OAuthRedditProvider._request_json", side_effect=[{"access_token": "secret-token"}, {"read": {"description": "read"}}])
    def test_oauth_check_makes_two_requests(self, request):
        self.assertTrue(check_connection(RedditConfig("id", "secret", "test-agent")))
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.args[0].full_url, "https://oauth.reddit.com/api/v1/scopes")

    @patch("agent.reddit.OAuthRedditProvider._request_json", return_value={"error": "invalid_client"})
    def test_failed_auth_does_not_continue(self, request):
        with self.assertRaises(RedditError):
            check_connection(RedditConfig("id", "secret", "test-agent"))
        self.assertEqual(request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
