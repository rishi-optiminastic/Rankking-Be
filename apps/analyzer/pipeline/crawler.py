import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .utils import extract_internal_links, extract_text

logger = logging.getLogger("apps")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 5


@dataclass
class CrawlResult:
    url: str
    status_code: int = 0
    html: str = ""
    soup: BeautifulSoup | None = None
    text: str = ""
    internal_links: list[str] = field(default_factory=list)
    load_time: float = 0.0
    error: str = ""
    is_https: bool = False

    @property
    def ok(self) -> bool:
        return self.status_code == 200 and self.soup is not None


def crawl_page(url: str) -> CrawlResult:
    result = CrawlResult(url=url)
    parsed = urlparse(url)
    result.is_https = parsed.scheme == "https"

    try:
        start = time.time()
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
            allow_redirects=True,
        )
        result.load_time = time.time() - start
        result.status_code = resp.status_code

        if resp.status_code != 200:
            result.error = f"HTTP {resp.status_code}"
            return result

        result.html = resp.text
        result.soup = BeautifulSoup(resp.text, "html.parser")
        text_soup = BeautifulSoup(resp.text, "html.parser")
        result.text = extract_text(text_soup)
        result.internal_links = extract_internal_links(result.soup, url)

    except requests.Timeout:
        result.error = "Request timed out"
        logger.warning("Crawl timeout: %s", url)
    except requests.RequestException as exc:
        result.error = str(exc)
        logger.warning("Crawl error for %s: %s", url, exc)

    return result


def check_file_exists(base_url: str, path: str) -> bool:
    parsed = urlparse(base_url)
    url = f"{parsed.scheme}://{parsed.netloc}/{path.lstrip('/')}"
    try:
        resp = requests.head(
            url, headers={"User-Agent": USER_AGENT}, timeout=3, allow_redirects=True
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False


def fetch_file_content(base_url: str, path: str) -> str:
    parsed = urlparse(base_url)
    url = f"{parsed.scheme}://{parsed.netloc}/{path.lstrip('/')}"
    try:
        resp = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=3, allow_redirects=True
        )
        if resp.status_code == 200:
            return resp.text
    except requests.RequestException:
        pass
    return ""
