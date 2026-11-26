import shutil
import subprocess
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path


class DashboardParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.script_depth = 0
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.script_depth += 1

    def handle_endtag(self, tag):
        if tag == "script" and self.script_depth:
            self.script_depth -= 1

    def handle_data(self, data):
        if self.script_depth:
            self.scripts.append(data)


class DashboardHtmlTests(unittest.TestCase):
    def test_dashboard_has_required_sections_and_valid_html(self):
        path = Path("docs/dashboard.html")
        html = path.read_text(encoding="utf-8")
        parser = DashboardParser()
        parser.feed(html)
        parser.close()
        self.assertIn("Website command centre", html)
        self.assertIn("Sitemap health", html)
        self.assertIn("Indexing diagnostics", html)
        self.assertIn("Activity & alerts", html)
        self.assertIn("./data/dashboard.json", html)
        self.assertIn("setInterval(load,300000)", html)

    def test_dashboard_javascript_parses(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed")
        parser = DashboardParser()
        parser.feed(Path("docs/dashboard.html").read_text(encoding="utf-8"))
        script = "".join(parser.scripts)
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8") as handle:
            handle.write(script)
            handle.flush()
            result = subprocess.run([node, "--check", handle.name], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
