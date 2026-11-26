import unittest
from unittest.mock import patch
import gsc.collector as collector
from gsc.collector import build_opportunities, bucket, settled_window


class ScoringTests(unittest.TestCase):
    def test_position_bucket(self):
        self.assertEqual(bucket(1.9), 1)
        self.assertEqual(bucket(101), 100)

    def test_only_question_queries_and_minimum_impressions(self):
        rows = [
            {"keys": ["how to fix indexing", "https://example.com/a"], "clicks": 2, "impressions": 100, "ctr": .02, "position": 5},
            {"keys": ["blue shoes", "https://example.com/b"], "clicks": 8, "impressions": 100, "ctr": .08, "position": 5},
            {"keys": ["why low volume", "https://example.com/c"], "clicks": 0, "impressions": 5, "ctr": 0, "position": 5},
        ]
        result = build_opportunities("sc-domain:example.com", rows, minimum=20)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].query, "how to fix indexing")
        self.assertGreater(result[0].estimated_click_gap, 0)

    def test_gap_uses_position_baseline(self):
        rows = [
            {"keys": ["what is x", "https://example.com/a"], "clicks": 1, "impressions": 100, "ctr": .01, "position": 4},
            {"keys": ["other query", "https://example.com/b"], "clicks": 20, "impressions": 100, "ctr": .20, "position": 4},
        ]
        result = build_opportunities("sc-domain:example.com", rows, minimum=1)
        self.assertEqual(len(result), 1)
        self.assertGreater(result[0].estimated_click_gap, 0)

    def test_query_pagination_stops_when_page_is_short(self):
        api = collector.SearchConsole.__new__(collector.SearchConsole)
        calls = []
        def fake_request(url, method="GET", payload=None):
            calls.append(payload["startRow"])
            return {"rows": [{"keys": ["q", "p"]}] if payload["startRow"] == 0 else []}
        with patch.object(collector, "PAGE_SIZE", 2), patch.object(api, "_request", side_effect=fake_request):
            rows, truncated = api.query_all("sc-domain:example.com", "2026-01-01", "2026-01-28")
        self.assertEqual(calls, [0])
        self.assertEqual(len(rows), 1)
        self.assertFalse(truncated)

    def test_query_pagination_marks_cap_as_truncated(self):
        api = collector.SearchConsole.__new__(collector.SearchConsole)
        calls = []
        def fake_request(url, method="GET", payload=None):
            calls.append(payload["startRow"])
            return {"rows": [{"keys": ["q", "p"]}, {"keys": ["q2", "p2"]}]}
        with patch.object(collector, "PAGE_SIZE", 2), patch.object(collector, "MAX_ROWS_PER_PROPERTY", 4), patch.object(api, "_request", side_effect=fake_request):
            rows, truncated = api.query_all("sc-domain:example.com", "2026-01-01", "2026-01-28")
        self.assertEqual(calls, [0, 2])
        self.assertEqual(len(rows), 4)
        self.assertTrue(truncated)

    def test_date_range_limit(self):
        with self.assertRaises(ValueError):
            settled_window("2026-01-01", "2026-05-01")

    def test_api_errors_include_sanitized_google_reason(self):
        class FakeResponse:
            status_code = 403
            ok = False
            headers = {}
            def json(self):
                return {"error": {"message": "API disabled for https://console.example.test and owner@example.com",
                                  "errors": [{"reason": "accessNotConfigured"}]}}
        class FakeSession:
            def request(self, *args, **kwargs):
                return FakeResponse()
        api = collector.SearchConsole.__new__(collector.SearchConsole)
        api.session = FakeSession()
        with self.assertRaisesRegex(RuntimeError, r"accessNotConfigured") as caught:
            api._request("https://example.test/api")
        self.assertNotIn("console.example.test", str(caught.exception))
        self.assertNotIn("owner@example.com", str(caught.exception))
        self.assertIn("[URL]", str(caught.exception))
        self.assertIn("[email]", str(caught.exception))

    def test_daily_report_contains_prioritized_question_plan(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            property_url = "sc-domain:example.com"
            (out / f"{collector.safe_name(property_url)}-opportunities.json").write_text(json.dumps([
                {"property": property_url, "query": "how to improve seo", "page": "https://example.com/seo",
                 "clicks": 3, "impressions": 100, "ctr": 0.03, "average_position": 6.2,
                 "estimated_click_gap": 4.0, "priority_score": 8.0}
            ]), encoding="utf-8")
            collector.write_daily_report([{"property": property_url, "rows_returned": 100}], out, "2026-10-01", "2026-10-28")
            report = (out / "daily-seo-report.md").read_text(encoding="utf-8")
            self.assertIn("how to improve seo", report)
            self.assertIn("Page-level work queue", report)

    def test_daily_report_includes_non_question_query_rows(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            property_url = "sc-domain:example.com"
            slug = collector.safe_name(property_url)
            (out / f"{slug}-search-performance.json").write_text(json.dumps([
                {"query": "best accounting software", "page": "https://example.com/accounting",
                 "clicks": 4, "impressions": 250, "ctr": 0.016, "position": 8.0}
            ]), encoding="utf-8")
            collector.write_daily_report([{"property": property_url, "rows_returned": 1}], out, "2026-10-01", "2026-10-28")
            report = (out / "daily-seo-report.md").read_text(encoding="utf-8")
            self.assertIn("best accounting software", report)
            self.assertIn("Search query and landing-page opportunities", report)
            self.assertIn("250", report)

    def test_write_outputs_exports_raw_query_page_rows(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            collector.write_outputs(
                "sc-domain:example.com",
                [{"keys": ["how to choose a laptop", "https://example.com/laptops"],
                  "clicks": 2, "impressions": 80, "ctr": 0.025, "position": 5.5}],
                False, "2026-10-01", "2026-10-28", out
            )
            raw = out / f"{collector.safe_name('sc-domain:example.com')}-search-performance.json"
            self.assertTrue(raw.exists())
            self.assertIn("how to choose a laptop", raw.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
