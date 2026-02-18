import logging
import re

from .crawler import CrawlResult, check_file_exists, fetch_file_content
from .utils import safe_score

logger = logging.getLogger("apps")

AI_BOT_AGENTS = [
    "GPTBot", "Google-Extended", "anthropic-ai", "ClaudeBot",
    "PerplexityBot", "ChatGPT-User", "CCBot",
]


def _check_robots_allows_ai(robots_txt: str) -> tuple[bool, list[str]]:
    blocked = []
    if not robots_txt:
        return True, []  # No robots.txt = allow all

    lines = robots_txt.lower().splitlines()
    current_agent = None
    for line in lines:
        line = line.strip()
        if line.startswith("user-agent:"):
            current_agent = line.split(":", 1)[1].strip()
        elif line.startswith("disallow:") and current_agent:
            path = line.split(":", 1)[1].strip()
            if path == "/" or path == "/*":
                for bot in AI_BOT_AGENTS:
                    if current_agent == "*" or bot.lower() in current_agent:
                        blocked.append(bot)

    allows = len(blocked) == 0
    return allows, blocked


def score_technical(crawl: CrawlResult) -> tuple[float, dict]:
    if not crawl.ok:
        return 0.0, {"error": crawl.error}

    soup = crawl.soup
    details = {"checks": {}, "findings": []}
    score = 0.0

    # llms.txt exists (20 pts)
    has_llms_txt = check_file_exists(crawl.url, "llms.txt")
    details["checks"]["llms_txt"] = has_llms_txt
    if has_llms_txt:
        score += 20
    else:
        details["findings"].append("no_llms_txt")

    # robots.txt allows AI bots (20 pts)
    robots_txt = fetch_file_content(crawl.url, "robots.txt")
    has_robots = bool(robots_txt.strip())
    details["checks"]["has_robots_txt"] = has_robots
    if has_robots:
        allows_ai, blocked_bots = _check_robots_allows_ai(robots_txt)
        details["checks"]["ai_bots_allowed"] = allows_ai
        details["checks"]["blocked_bots"] = blocked_bots
        if allows_ai:
            score += 20
        else:
            details["findings"].append("ai_bots_blocked")
    else:
        score += 20  # No robots.txt = allow all
        details["checks"]["ai_bots_allowed"] = True

    # sitemap.xml (10 pts)
    has_sitemap = check_file_exists(crawl.url, "sitemap.xml")
    details["checks"]["has_sitemap"] = has_sitemap
    if has_sitemap:
        score += 10
    else:
        details["findings"].append("no_sitemap")

    # Meta robots ok (10 pts)
    meta_robots = soup.find("meta", attrs={"name": "robots"})
    robots_content = meta_robots.get("content", "").lower() if meta_robots else ""
    noindex = "noindex" in robots_content
    nofollow = "nofollow" in robots_content
    details["checks"]["meta_robots_ok"] = not noindex
    if not noindex:
        score += 10
    else:
        details["findings"].append("meta_noindex")

    # HTTPS (5 pts)
    details["checks"]["is_https"] = crawl.is_https
    if crawl.is_https:
        score += 5
    else:
        details["findings"].append("no_https")

    # Load time < 3s (15 pts)
    details["checks"]["load_time"] = round(crawl.load_time, 2)
    if crawl.load_time < 1.5:
        score += 15
    elif crawl.load_time < 3.0:
        score += 10
    elif crawl.load_time < 5.0:
        score += 5
    else:
        details["findings"].append("slow_load_time")

    # Viewport meta (10 pts)
    viewport = soup.find("meta", attrs={"name": "viewport"})
    details["checks"]["has_viewport"] = viewport is not None
    if viewport:
        score += 10
    else:
        details["findings"].append("no_viewport")

    # Canonical tag (10 pts)
    canonical = soup.find("link", attrs={"rel": "canonical"})
    details["checks"]["has_canonical"] = canonical is not None
    if canonical:
        score += 10
    else:
        details["findings"].append("no_canonical")

    score = safe_score(score)
    details["score"] = score
    return score, details
