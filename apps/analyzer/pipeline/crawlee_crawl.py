"""Crawlee-based site crawler (HTTP + BeautifulSoup) for the analyzer.

Runs *in-process* (no API key, no credits) using Crawlee's BeautifulSoupCrawler:
it fetches the start URL and follows same-site links up to a page cap, returning
a list of ``{"url", "html", "status"}`` dicts that ``crawler.py`` adapts into
``CrawlResult``. HTTP-only — it does not render JavaScript, so SPA/JS-only
content won't be seen (that's the engine trade-off chosen for this integration).

Stateless: a fresh in-memory storage client per call so repeated analyses never
share a request queue / dedup set. Because it crawls from our own server IP,
sites behind Cloudflare / anti-bot may block it — callers fall back to the
direct crawler (+ scraper API) on failure.
"""

import asyncio
import logging
import os
import re

logger = logging.getLogger("apps")

DEFAULT_LIMIT = 13
# Hard wall-clock guard so a slow/looping crawl can't hang the analysis thread.
DEFAULT_TIMEOUT = 90

# Same-site hrefs that are not pages, so following them only burns the page cap
# and reports a crawl failure for a site that is perfectly healthy.
#
# /cdn-cgi/ is Cloudflare's own namespace. Its email-protection links are the
# common case: Cloudflare rewrites every mailto: into
# /cdn-cgi/l/email-protection#<hex>, which is decoded by JavaScript in the
# browser and 404s / times out for an HTTP crawler. Crawlee retries, exhausts
# them, and logs an error — that is SIGNALOR-Z, raised against a prospect's site
# during an outreach benchmark rather than against anything of ours.
#
# The rest are binary or non-navigational targets that would spend the cap
# without yielding text to score.
# Anchored deliberately: Crawlee tests these with ``pattern.match(url)``, which
# matches from the START of the full URL, so a bare "/cdn-cgi/" would never fire.
SKIP_URL_PATTERNS = [
    re.compile(r".*/cdn-cgi/.*", re.I),
    # The query/fragment tail is optional and matched explicitly: patterns are
    # tested against the raw extracted href, before any fragment normalisation,
    # so "/whitepaper.pdf#page=2" must still be recognised as a download.
    re.compile(
        r".*\.(?:pdf|zip|gz|tar|docx?|xlsx?|pptx?|csv|mp[34]|avi|mov|wav|dmg|exe|svg|ico)"
        r"(?:[?#].*)?$",
        re.I,
    ),
]


class CrawleeError(Exception):
    """Raised when the Crawlee crawl cannot run or yields nothing."""


class ForeignHostError(CrawleeError):
    """A crawl produced pages belonging to a host other than the one requested.

    Never expected. It means crawl state crossed run boundaries, and returning
    the pages anyway is how one company's site got scored — and reported — as
    another's. Raising aborts to the direct crawler instead.
    """


def host_of(url: str) -> str:
    """Comparison key for "same site": lowercase hostname, no ``www.``.

    The single definition of site identity for the crawl layer. Everything that
    decides whether a page belongs to a crawl uses this, so the answer cannot
    differ between the producer and its consumers.
    """
    from urllib.parse import urlparse

    try:
        hostname = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    return hostname.removeprefix("www.")


def is_configured() -> bool:
    """Crawlee needs no key, so it's available unless explicitly disabled via
    ``SIGNALOR_USE_CRAWLEE`` (defaults on)."""
    return os.getenv("SIGNALOR_USE_CRAWLEE", "true").strip().lower() not in ("0", "false", "no", "off")


def crawl(url: str, limit: int = DEFAULT_LIMIT, timeout: int = DEFAULT_TIMEOUT) -> list[dict]:
    """Crawl ``url`` and return a list of ``{"url", "html", "status"}`` page dicts.

    Raises :class:`CrawleeError` on failure so callers can fall back. Safe to call
    from sync code (Celery worker / daemon thread); if an event loop is already
    running it executes in a dedicated thread.
    """
    try:
        try:
            asyncio.get_running_loop()
            loop_running = True
        except RuntimeError:
            loop_running = False

        if loop_running:
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(lambda: asyncio.run(_crawl_async(url, limit, timeout))).result()
        return asyncio.run(_crawl_async(url, limit, timeout))
    except CrawleeError:
        raise
    except Exception as exc:
        raise CrawleeError(f"Crawlee crawl failed: {exc}") from exc


async def _crawl_async(url: str, limit: int, timeout: int) -> list[dict]:
    import uuid

    from crawlee.crawlers import BeautifulSoupCrawler, BeautifulSoupCrawlingContext
    from crawlee.storage_clients import MemoryStorageClient
    from crawlee.storages import RequestQueue

    pages: list[dict] = []
    foreign: list[str] = []

    # A uniquely named queue per crawl, NOT Crawlee's default. The default queue
    # resolves through a process-global service locator, so in a long-lived
    # Celery worker consecutive crawls shared one queue: a URL crawled for one
    # run was "already handled" for the next (0-page crawls), and links left
    # pending when a run hit its request cap were drained by the NEXT run —
    # which is how a sees.ai benchmark crawled signalor.ai's pages and shipped
    # a report with the wrong brand on it.
    storage = MemoryStorageClient()
    queue = await RequestQueue.open(name=f"crawl-{uuid.uuid4().hex}", storage_client=storage)

    crawler = BeautifulSoupCrawler(
        max_requests_per_crawl=max(1, int(limit)),
        storage_client=storage,
        request_manager=queue,
    )

    expected_host = host_of(url)

    @crawler.router.default_handler
    async def _handler(context: BeautifulSoupCrawlingContext) -> None:
        # Refuse anything that is not the site we were asked to crawl. This is
        # the innermost guard: a page is rejected at the moment it is produced,
        # before it can reach any consumer, so no present or future caller has
        # to remember to filter. Counted, not silently skipped — a nonzero count
        # means crawl isolation broke and we want the crawl to fail loudly.
        page_host = host_of(context.request.url)
        if expected_host and page_host != expected_host:
            foreign.append(context.request.url)
            return

        # parsed_content is Crawlee's BeautifulSoup; serialising it back to HTML
        # preserves <script type="application/ld+json"> for the schema scorer.
        soup = context.parsed_content
        html = str(soup) if soup is not None else ""
        pages.append(
            {
                "url": context.request.url,
                "html": html,
                "status": getattr(context.http_response, "status_code", 0) or 0,
            }
        )
        # Follow same-site links up to the request cap, minus the ones that are
        # not pages (see SKIP_URL_PATTERNS). ``strategy`` is explicit rather than
        # left to the library default: link-following must never be the thing
        # that widens a crawl to another host.
        try:
            await context.enqueue_links(strategy="same-domain", exclude=SKIP_URL_PATTERNS)
        except Exception as exc:  # noqa: BLE001 - link discovery is best-effort
            logger.debug("crawlee enqueue_links failed for %s: %s", context.request.url, exc)

    try:
        await asyncio.wait_for(crawler.run([url]), timeout=timeout)
    except TimeoutError:
        logger.warning("Crawlee crawl timed out after %ss for %s (%d pages so far)", timeout, url, len(pages))
    finally:
        # The queue is in-memory, but drop it anyway so the service locator's
        # name registry in this process cannot accumulate one entry per crawl.
        try:
            await queue.drop()
        except Exception:  # noqa: BLE001 - cleanup is best-effort
            pass

    if foreign:
        # Isolation has failed somewhere upstream. Fail the crawl rather than
        # return a partial result: a half-foreign crawl is exactly the input
        # that produces a confident, wrong finding about the wrong company.
        logger.error(
            "Crawlee crawl for %s produced %d page(s) from other hosts (e.g. %s); aborting",
            url,
            len(foreign),
            foreign[0],
        )
        raise ForeignHostError(f"crawl for {url} returned pages from another host: {foreign[0]}")

    logger.info("Crawlee crawl finished for %s: %d pages", url, len(pages))
    return pages
