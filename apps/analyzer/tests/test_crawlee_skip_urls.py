"""Links the Crawlee crawler must not follow.

Cloudflare rewrites every mailto: into /cdn-cgi/l/email-protection#<hex>, which
only resolves in a browser. Following it burnt the page cap and reported a crawl
failure against a healthy prospect site (SIGNALOR-Z).
"""

from django.test import SimpleTestCase

from apps.analyzer.pipeline.crawlee_crawl import SKIP_URL_PATTERNS


def _skipped(url: str) -> bool:
    """Exactly how Crawlee evaluates ``exclude``: ``pattern.match`` on the full URL.

    Deliberately ``match`` and not ``search`` — Crawlee anchors at the start of
    the string (BasicCrawler._check_url_patterns), so an unanchored pattern would
    silently never fire and this test would pass against a fix that does nothing.
    """
    return any(p.match(url) is not None for p in SKIP_URL_PATTERNS)


class SkipUrlPatternTests(SimpleTestCase):
    def test_cloudflare_email_protection_links_are_skipped(self):
        self.assertTrue(_skipped("https://zokri.com/cdn-cgi/l/email-protection#d1a1a3b8a7b0"))

    def test_any_cdn_cgi_path_is_skipped(self):
        self.assertTrue(_skipped("https://example.com/cdn-cgi/challenge-platform/x.js"))

    def test_binary_downloads_are_skipped(self):
        for url in (
            "https://example.com/whitepaper.pdf",
            "https://example.com/deck.pptx?v=2",
            "https://example.com/logo.svg",
            # Patterns run against the raw href, before fragment normalisation.
            "https://example.com/whitepaper.pdf#page=2",
        ):
            self.assertTrue(_skipped(url), url)

    def test_real_pages_are_still_followed(self):
        for url in (
            "https://example.com/",
            "https://example.com/pricing",
            "https://example.com/blog/how-we-cut-costs",
            # Substring traps: these are pages, not Cloudflare or downloads.
            "https://example.com/pdfs-explained",
            "https://example.com/cdn-cgi-guide",
        ):
            self.assertFalse(_skipped(url), url)
