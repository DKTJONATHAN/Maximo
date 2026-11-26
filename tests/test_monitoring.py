import json
import tempfile
import unittest
from pathlib import Path

from gsc.monitoring import build_dashboard_data


class DashboardDataTests(unittest.TestCase):
    def test_dashboard_aggregates_metrics_and_classifies_site_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "sc-domain_example.com-search-performance.json").write_text(json.dumps([
                {"query": "best school", "page": "https://example.com/", "clicks": 12, "impressions": 100, "ctr": .12, "position": 4}
            ]))
            (out / "sc-domain_example.com-historical-comparison.json").write_text(json.dumps([
                {"query": "best school", "page": "https://example.com/", "clicks": 12, "previous_clicks": 8, "impressions": 100, "previous_impressions": 90, "position": 4, "previous_position": 5}
            ]))
            data = build_dashboard_data(out, [{"property": "sc-domain:example.com", "permission_level": "siteOwner"}], "2026-10-01", "2026-10-28")
            site = data["properties"][0]
            self.assertEqual(site["health"], "healthy")
            self.assertEqual(site["clicks"], 12)
            self.assertEqual(site["clicks_delta"], 4)
            self.assertEqual(data["best_performers"][0]["property"], "sc-domain:example.com")

    def test_permission_and_indexing_issues_are_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            data = build_dashboard_data(
                out,
                [{"property": "https://bad.example/", "error": "RuntimeError", "error_message": "403 forbidden"}],
                "2026-10-01", "2026-10-28",
                sitemap_results=[{"property": "https://bad.example/", "errors": 2, "warnings": 1}],
                inspection_results=[{"property": "https://bad.example/", "url": "https://bad.example/a", "status": "FAIL", "coverage_state": "Crawled - currently not indexed"}],
            )
            site = data["properties"][0]
            self.assertEqual(site["health"], "access_error")
            self.assertEqual(site["sitemap_errors"], 2)
            self.assertEqual(site["not_indexed_urls"], 1)
            self.assertTrue(data["events"])

    def test_sitemap_api_failure_is_not_reported_as_zero_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = build_dashboard_data(
                Path(tmp), [{"property": "https://example.com/"}],
                "2026-10-01", "2026-10-28",
                sitemap_results=[{"property": "https://example.com/", "error": "403"}],
            )
            self.assertEqual(data["properties"][0]["health"], "needs_attention")
            self.assertEqual(data["properties"][0]["sitemap_fetch_errors"], 1)


if __name__ == "__main__":
    unittest.main()
