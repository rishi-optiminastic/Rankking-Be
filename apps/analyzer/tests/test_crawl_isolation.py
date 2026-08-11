"""Cross-run crawl contamination — the sees.ai/signalor.ai incident.

A long-lived worker shared Crawlee's default request queue across crawls, so one
run's leftover pages could be served as the NEXT run's crawl. The adapter then
promoted a foreign-host page to "homepage", which put the wrong brand name and
the wrong buyer prompts on a customer-facing report. These tests pin the two
independent guards: foreign-host pages never survive the adapter, and the
prompt-generation cache is partitioned per domain.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.analyzer.pipeline.crawler import _crawl_site_via_crawlee

SIGNALOR_HTML = (
    '<html><head><meta property="og:site_name" content="SignalorAI">'
    "<title>SignalorAI</title></head><body>AI visibility</body></html>"
)
SEES_HTML = (
    "<html><head><title>sees.ai | Precision insight</title></head><body>drone inspection</body></html>"
)


def _page(url: str, html: str) -> dict:
    return {"url": url, "html": html, "status": 200}


class ForeignHostPageTests(SimpleTestCase):
    """The adapter must never let another domain's page into the result."""

    def test_leaked_foreign_pages_alone_force_the_fallback(self):
        """Only leftover signalor pages arrive for a sees.ai crawl -> None,
        so crawl_site falls back to the direct crawler instead of scoring
        the wrong site."""
        leaked = [
            _page("https://signalor.ai/", SIGNALOR_HTML),
            _page("https://signalor.ai/pricing", SIGNALOR_HTML),
        ]
        with patch("apps.analyzer.pipeline.crawler.crawlee_crawl.crawl", return_value=leaked):
            self.assertIsNone(_crawl_site_via_crawlee("https://sees.ai", max_pages=5))

    def test_mixed_pages_keep_only_the_requested_host(self):
        pages = [
            _page("https://signalor.ai/", SIGNALOR_HTML),
            _page("https://sees.ai/", SEES_HTML),
            _page("https://signalor.ai/blog", SIGNALOR_HTML),
        ]
        with patch("apps.analyzer.pipeline.crawler.crawlee_crawl.crawl", return_value=pages):
            crawled = _crawl_site_via_crawlee("https://sees.ai", max_pages=5)
        self.assertIsNotNone(crawled)
        homepage, _site_map, additional = crawled
        self.assertEqual(homepage.url, "https://sees.ai/")
        self.assertEqual(additional, [])

    def test_www_variant_is_the_same_host(self):
        pages = [_page("https://www.sees.ai/", SEES_HTML)]
        with patch("apps.analyzer.pipeline.crawler.crawlee_crawl.crawl", return_value=pages):
            crawled = _crawl_site_via_crawlee("https://sees.ai", max_pages=5)
        self.assertIsNotNone(crawled)


class CacheScopeTests(SimpleTestCase):
    """cache_scope must partition lookup and store, and leave routing's purpose alone."""

    def test_scope_partitions_the_cache_purpose(self):
        from core.llm.client import ask_llm

        with (
            patch("core.llm.cache_port.lookup", return_value=None) as lookup,
            patch("core.llm.cache_port.store") as store,
            patch("core.llm.client.ask_llm_with_citations", return_value=("answer", [])),
        ):
            ask_llm("q", purpose="Generate Brand Prompts", cache=True, cache_scope="sees.ai")

        self.assertEqual(lookup.call_args.kwargs["purpose"], "Generate Brand Prompts#sees.ai")
        self.assertEqual(store.call_args.kwargs["purpose"], "Generate Brand Prompts#sees.ai")

    def test_no_scope_keeps_the_bare_purpose(self):
        from core.llm.client import ask_llm

        with (
            patch("core.llm.cache_port.lookup", return_value=None) as lookup,
            patch("core.llm.client.ask_llm_with_citations", return_value=("answer", [])),
        ):
            ask_llm("q", purpose="Generate Brand Prompts", cache=True)

        self.assertEqual(lookup.call_args.kwargs["purpose"], "Generate Brand Prompts")

    def test_two_domains_never_share_a_partition(self):
        """The incident in one assertion: with scoping, a sees.ai lookup can
        never be answered by a signalor.ai entry, because their cache purposes
        differ before similarity is even consulted."""
        from core.llm.client import ask_llm

        seen: list[str] = []

        def record(prompt, *, purpose, model_key, org=None):
            seen.append(purpose)
            return None

        with (
            patch("core.llm.cache_port.lookup", side_effect=record),
            patch("core.llm.cache_port.store"),
            patch("core.llm.client.ask_llm_with_citations", return_value=("answer", [])),
        ):
            ask_llm("q1", purpose="Generate Brand Prompts", cache=True, cache_scope="signalor.ai")
            ask_llm("q2", purpose="Generate Brand Prompts", cache=True, cache_scope="sees.ai")

        self.assertEqual(len(set(seen)), 2)


class GenerateBrandPromptsScopeTests(SimpleTestCase):
    def test_generation_is_scoped_to_the_brand_domain(self):
        from apps.analyzer.pipeline.prompt_tracker import generate_brand_prompts

        with patch("core.llm.structured.ask_llm", return_value="") as ask:
            generate_brand_prompts(brand_name="sees.ai", brand_url="https://www.sees.ai", count=6)

        self.assertEqual(ask.call_args.kwargs.get("cache_scope"), "sees.ai")
