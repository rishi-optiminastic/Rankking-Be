import json
import logging
import re

from .crawler import CrawlResult
from .utils import extract_brand_name, safe_score

logger = logging.getLogger("apps")

PROBE_TEMPLATES = [
    "What are the best {category} companies?",
    "Can you recommend a {category} provider?",
    "Who are the top {category} services in the market?",
    "What {category} tools or platforms would you suggest?",
    "Compare the leading {category} solutions available today.",
]


def _extract_category(soup, url: str) -> str:
    """Extract the site's category/industry from meta tags and content."""
    # Try meta description
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        return meta_desc["content"][:100]

    # Try og:description
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        return og_desc["content"][:100]

    # Try title
    title = soup.find("title")
    if title and title.string:
        return title.string.strip()[:100]

    return "technology services"


def _identify_industry_gemini(site_context: str) -> str:
    """Use Gemini to identify the industry/category."""
    try:
        import google.generativeai as genai

        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = (
            f"Based on this site description, identify the industry/category in 2-4 words. "
            f"Reply with ONLY the category, no explanation.\n\n"
            f"Site context: {site_context}"
        )
        response = model.generate_content(prompt)
        return response.text.strip().strip('"').strip("'")
    except Exception as exc:
        logger.warning("Gemini industry identification failed: %s", exc)
    return "technology"


def _fuzzy_match(brand: str, text: str) -> bool:
    """Check if brand name appears in text using exact and fuzzy matching."""
    brand_lower = brand.lower()
    text_lower = text.lower()

    # Exact match
    if brand_lower in text_lower:
        return True

    # Try without common suffixes
    for suffix in [" inc", " llc", " ltd", " corp", " co"]:
        cleaned = brand_lower.replace(suffix, "").strip()
        if cleaned and cleaned in text_lower:
            return True

    # Try Levenshtein for close matches
    try:
        import Levenshtein

        words = text_lower.split()
        for word in words:
            if len(word) >= 3 and Levenshtein.ratio(brand_lower, word) > 0.8:
                return True
    except ImportError:
        pass

    return False


def _fire_probe(prompt: str, brand_name: str) -> tuple[str, bool, float]:
    """Fire a single probe at Gemini and check for brand mention."""
    try:
        import google.generativeai as genai

        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        text = response.text.strip()

        mentioned = _fuzzy_match(brand_name, text)
        confidence = 1.0 if mentioned else 0.0

        return text, mentioned, confidence
    except Exception as exc:
        logger.warning("Gemini probe failed: %s", exc)
        return "", False, 0.0


def score_ai_visibility(crawl: CrawlResult) -> tuple[float, dict, list[dict]]:
    """Returns (score, details, probes_data)."""
    if not crawl.ok:
        return 0.0, {"error": crawl.error}, []

    soup = crawl.soup
    brand_name = extract_brand_name(soup, crawl.url)
    site_context = _extract_category(soup, crawl.url)
    category = _identify_industry_gemini(site_context)

    details = {
        "checks": {
            "brand_name": brand_name,
            "category": category,
        },
        "findings": [],
    }
    probes_data = []
    score = 0.0
    points_per_probe = 20.0  # 5 probes × 20 = 100

    for template in PROBE_TEMPLATES:
        prompt = template.format(category=category)
        response_text, mentioned, confidence = _fire_probe(prompt, brand_name)

        probes_data.append({
            "prompt_used": prompt,
            "llm_response": response_text[:2000],
            "brand_mentioned": mentioned,
            "confidence": confidence,
        })

        if mentioned:
            score += points_per_probe

    mentions = sum(1 for p in probes_data if p["brand_mentioned"])
    details["checks"]["probes_total"] = len(probes_data)
    details["checks"]["probes_mentioned"] = mentions

    if mentions == 0:
        details["findings"].append("brand_not_in_ai")

    score = safe_score(score)
    details["score"] = score
    return score, details, probes_data
