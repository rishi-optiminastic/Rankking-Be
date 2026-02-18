import json
import logging
import re
from urllib.parse import urlparse

import requests

from .crawler import CrawlResult
from .utils import extract_brand_name, safe_score

logger = logging.getLogger("apps")

SOCIAL_DOMAINS = {
    "linkedin.com", "twitter.com", "x.com", "facebook.com",
    "instagram.com", "youtube.com", "github.com", "tiktok.com",
}

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"


def _check_wikipedia(brand_name: str) -> bool:
    try:
        resp = requests.get(
            WIKIPEDIA_API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": brand_name,
                "srlimit": 3,
                "format": "json",
            },
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("query", {}).get("search", [])
            for r in results:
                if brand_name.lower() in r.get("title", "").lower():
                    return True
    except Exception as exc:
        logger.warning("Wikipedia check failed for %s: %s", brand_name, exc)
    return False


def _check_knowledge_panel_gemini(brand_name: str, industry: str) -> tuple[bool, float]:
    """Use Gemini to check if brand has a knowledge panel / is well-known."""
    try:
        import google.generativeai as genai

        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = (
            f"Is '{brand_name}' a well-known brand/company in the {industry or 'technology'} industry? "
            f"Does it have a Google Knowledge Panel? "
            f"Reply with JSON: {{\"well_known\": true/false, \"confidence\": 0.0-1.0, \"description\": \"brief\"}}"
        )
        response = model.generate_content(prompt)
        text = response.text.strip()
        # Try to extract JSON
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return data.get("well_known", False), data.get("confidence", 0.0)
    except Exception as exc:
        logger.warning("Gemini knowledge panel check failed: %s", exc)
    return False, 0.0


def _check_third_party_mentions(brand_name: str) -> tuple[int, float]:
    """Use Gemini to estimate third-party mentions."""
    try:
        import google.generativeai as genai

        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = (
            f"How often is '{brand_name}' mentioned in third-party publications, review sites, "
            f"and industry directories? Rate from 0-10. "
            f"Reply with JSON: {{\"mention_score\": 0-10, \"confidence\": 0.0-1.0}}"
        )
        response = model.generate_content(prompt)
        text = response.text.strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return data.get("mention_score", 0), data.get("confidence", 0.0)
    except Exception as exc:
        logger.warning("Gemini third-party check failed: %s", exc)
    return 0, 0.0


def score_entity(crawl: CrawlResult, industry: str = "") -> tuple[float, dict]:
    if not crawl.ok:
        return 0.0, {"error": crawl.error}

    soup = crawl.soup
    details = {"checks": {}, "findings": []}
    score = 0.0

    brand_name = extract_brand_name(soup, crawl.url)
    details["checks"]["brand_name"] = brand_name

    # Brand extraction (5 pts) — always get some points if we found a name
    if brand_name:
        score += 5
        details["checks"]["brand_extracted"] = True
    else:
        details["checks"]["brand_extracted"] = False

    # Wikipedia API check (25 pts)
    has_wiki = _check_wikipedia(brand_name)
    details["checks"]["wikipedia_presence"] = has_wiki
    if has_wiki:
        score += 25
    else:
        details["findings"].append("no_wikipedia_presence")

    # Knowledge Panel via Gemini (25 pts)
    well_known, kp_confidence = _check_knowledge_panel_gemini(brand_name, industry)
    details["checks"]["knowledge_panel"] = well_known
    details["checks"]["kp_confidence"] = kp_confidence
    if well_known:
        score += 25
    else:
        details["findings"].append("brand_not_in_ai")

    # Third-party mentions via Gemini (25 pts)
    mention_score, mention_confidence = _check_third_party_mentions(brand_name)
    details["checks"]["third_party_score"] = mention_score
    details["checks"]["mention_confidence"] = mention_confidence
    tp_points = min(25, mention_score * 2.5)
    score += tp_points

    # Social media links (10 pts)
    social_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        try:
            domain = urlparse(href).netloc.lower()
            for sd in SOCIAL_DOMAINS:
                if domain.endswith(sd):
                    social_links.append(sd)
                    break
        except Exception:
            continue
    unique_socials = set(social_links)
    details["checks"]["social_profiles"] = list(unique_socials)
    details["checks"]["social_count"] = len(unique_socials)
    if len(unique_socials) >= 2:
        score += 10
    elif len(unique_socials) == 1:
        score += 5
    else:
        details["findings"].append("no_social_profiles")

    # Domain maturity (10 pts) — approximated by domain length/quality
    domain = urlparse(crawl.url).netloc
    details["checks"]["domain"] = domain
    if len(domain.replace("www.", "").split(".")[0]) <= 15:
        score += 10  # Short, clean domain names suggest maturity

    score = safe_score(score)
    details["score"] = score
    return score, details
