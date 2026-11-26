import unittest

from gsc.history import compare_query_page_rows, previous_window


class HistoricalComparisonTests(unittest.TestCase):
    def test_previous_window_is_same_length_and_adjacent(self):
        self.assertEqual(
            previous_window("2026-10-27", "2026-11-23"),
            ("2026-09-29", "2026-10-26"),
        )

    def test_invalid_window_is_rejected(self):
        with self.assertRaises(ValueError):
            previous_window("2026-11-24", "2026-11-23")

    def test_comparison_flags_click_loss_and_position_worsening(self):
        current = [{
            "keys": ["how to choose a school", "https://example.com/schools"],
            "clicks": 2, "impressions": 80, "ctr": 0.025, "position": 8.5,
        }]
        previous = [{
            "keys": ["how to choose a school", "https://example.com/schools"],
            "clicks": 5, "impressions": 100, "ctr": 0.05, "position": 5.0,
        }]
        row = compare_query_page_rows(current, previous)[0]
        self.assertEqual(row["clicks_delta"], -3)
        self.assertEqual(row["impressions_delta"], -20)
        self.assertAlmostEqual(row["ctr_delta"], -0.025)
        self.assertAlmostEqual(row["position_delta"], 3.5)
        self.assertFalse(row["newly_visible"])
        self.assertFalse(row["lost_visibility"])

    def test_comparison_distinguishes_new_and_missing_rows(self):
        current = [{"keys": ["new query", "https://example.com/new"],
                    "clicks": 1, "impressions": 4, "ctr": .25, "position": 12}]
        previous = [{"keys": ["old query", "https://example.com/old"],
                     "clicks": 2, "impressions": 9, "ctr": .22, "position": 7}]
        rows = compare_query_page_rows(current, previous)
        self.assertTrue(next(x for x in rows if x["query"] == "new query")["newly_visible"])
        self.assertTrue(next(x for x in rows if x["query"] == "old query")["lost_visibility"])

    def test_report_gives_action_for_forbidden_property(self):
        import tempfile
        from pathlib import Path
        from gsc.collector import write_daily_report
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_daily_report([{
                "property": "sc-domain:example.com",
                "permission_level": "siteUnverifiedUser",
                "error": "RuntimeError",
                "error_message": "Search Console API returned HTTP 403 (reason=forbidden)",
            }], out, "2026-10-27", "2026-11-23")
            report = (out / "daily-seo-report.md").read_text(encoding="utf-8")
            self.assertIn("Users and permissions", report)
            self.assertIn("at least **Restricted** access", report)
            self.assertIn("siteUnverifiedUser", report)

    def test_comparison_exports_machine_readable_csv_and_json(self):
        import tempfile
        from pathlib import Path
        from gsc.history import write_comparison_outputs
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            rows = write_comparison_outputs(
                "sc-domain:example.com",
                [{"keys": ["query", "https://example.com/"], "clicks": 1, "impressions": 10, "ctr": .1, "position": 4}],
                [{"keys": ["query", "https://example.com/"], "clicks": 3, "impressions": 20, "ctr": .15, "position": 3}],
                out,
                "example",
            )
            self.assertEqual(len(rows), 1)
            self.assertTrue((out / "example-historical-comparison.csv").exists())
            self.assertTrue((out / "example-historical-comparison.json").exists())


if __name__ == "__main__":
    unittest.main()
