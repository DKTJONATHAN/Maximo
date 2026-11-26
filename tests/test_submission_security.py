import unittest

from scripts.submit_sitemap import validate_target


class SitemapTargetValidationTests(unittest.TestCase):
    def test_domain_property_accepts_its_subdomain(self):
        validate_target("sc-domain:example.com", "https://www.example.com/sitemap.xml")

    def test_domain_property_rejects_foreign_host(self):
        with self.assertRaises(ValueError):
            validate_target("sc-domain:example.com", "https://other.test/sitemap.xml")

    def test_url_prefix_property_requires_matching_host_and_path(self):
        validate_target("https://example.com/blog/", "https://example.com/blog/sitemap.xml")
        with self.assertRaises(ValueError):
            validate_target("https://example.com/blog/", "https://example.com/shop/sitemap.xml")
        with self.assertRaises(ValueError):
            validate_target("https://example.com/", "https://evil.test/sitemap.xml")


if __name__ == "__main__":
    unittest.main()
