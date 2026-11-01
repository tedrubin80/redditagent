import unittest

from agent.rate_limit import backoff_seconds


class RateLimitTests(unittest.TestCase):
    def test_backoff_doubles_and_caps(self):
        self.assertEqual(backoff_seconds(0), 1.0)
        self.assertEqual(backoff_seconds(1), 2.0)
        self.assertEqual(backoff_seconds(2), 4.0)
        self.assertEqual(backoff_seconds(10), 32.0)


if __name__ == "__main__":
    unittest.main()
