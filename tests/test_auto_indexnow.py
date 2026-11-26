import unittest
from datetime import datetime, timedelta, timezone

from scripts.auto_indexnow import _covered, parse_lastmod, should_submit


class AutomaticIndexNowTests(unittest.TestCase):
    def test_lastmod_parses_date_and_timezone(self):
        self.assertEqual(parse_lastmod("2026-11-26").date().isoformat(), "2026-11-26")
        self.assertEqual(parse_lastmod("2026-11-26T10:00:00Z").hour, 10)
        self.assertIsNone(parse_lastmod("not-a-date"))

    def test_only_newer_lastmod_is_submitted_after_first_seen(self):
        previous = "2026-11-25T10:00:00+00:00"
        self.assertFalse(should_submit(parse_lastmod("2026-11-25T10:00:00Z"), previous, datetime.now(timezone.utc)))
        self.assertTrue(should_submit(parse_lastmod("2026-11-26T10:00:00Z"), previous, datetime.now(timezone.utc)))

    def test_first_run_only_submits_recent_lastmod(self):
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=2)
        self.assertTrue(should_submit(now - timedelta(hours=1), None, cutoff))
        self.assertFalse(should_submit(now - timedelta(days=10), None, cutoff))

    def test_property_host_and_path_boundaries(self):
        self.assertTrue(_covered("sc-domain:example.com", "https://www.example.com/new"))
        self.assertFalse(_covered("sc-domain:example.com", "https://notexample.com/new"))
        self.assertTrue(_covered("https://example.com/blog/", "https://example.com/blog/post"))
        self.assertFalse(_covered("https://example.com/blog", "https://example.com/blogger/post"))


if __name__ == "__main__":
    unittest.main()
