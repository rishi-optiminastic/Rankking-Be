import json
import logging

from .crawler import CrawlResult
from .utils import safe_score

logger = logging.getLogger("apps")

SCHEMA_TYPES_POINTS = {
    "FAQPage": 15,
    "Article": 15,
    "NewsArticle": 15,
    "BlogPosting": 15,
    "Organization": 15,
    "Product": 10,
    "HowTo": 10,
    "BreadcrumbList": 10,
}


def _extract_jsonld(soup) -> list[dict]:
    schemas = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                schemas.extend(data)
            elif isinstance(data, dict):
                schemas.append(data)
        except (json.JSONDecodeError, TypeError):
            continue
    return schemas


def _get_types(schema: dict) -> set[str]:
    types = set()
    t = schema.get("@type", "")
    if isinstance(t, list):
        types.update(t)
    elif isinstance(t, str):
        types.add(t)
    # Check @graph
    for item in schema.get("@graph", []):
        if isinstance(item, dict):
            types.update(_get_types(item))
    return types


def score_schema(crawl: CrawlResult) -> tuple[float, dict]:
    if not crawl.ok:
        return 0.0, {"error": crawl.error}

    soup = crawl.soup
    details = {"checks": {}, "findings": [], "types_found": []}
    score = 0.0

    schemas = _extract_jsonld(soup)

    # JSON-LD present (10 pts)
    if schemas:
        score += 10
        details["checks"]["jsonld_present"] = True
    else:
        details["checks"]["jsonld_present"] = False
        details["findings"].append("no_jsonld")
        details["score"] = 0.0
        return 0.0, details

    # Collect all types
    all_types = set()
    for s in schemas:
        all_types.update(_get_types(s))

    details["types_found"] = sorted(all_types)

    # Score individual types
    type_score = 0
    for schema_type, points in SCHEMA_TYPES_POINTS.items():
        if schema_type in all_types:
            type_score += points
            details["checks"][f"has_{schema_type}"] = True
        else:
            details["checks"][f"has_{schema_type}"] = False

    # Cap type score at 75 (since JSON-LD present = 10, validity = 15)
    type_score = min(type_score, 75)
    score += type_score

    # Check missing important types
    if "FAQPage" not in all_types:
        details["findings"].append("no_faqpage_schema")
    if "Article" not in all_types and "BlogPosting" not in all_types and "NewsArticle" not in all_types:
        details["findings"].append("no_article_schema")
    if "Organization" not in all_types:
        details["findings"].append("no_organization_schema")

    # Validity check (15 pts) — basic structural validation
    valid = True
    for s in schemas:
        if "@context" not in s and "@graph" not in s:
            valid = False
            break
    if valid:
        score += 15
        details["checks"]["valid_structure"] = True
    else:
        details["checks"]["valid_structure"] = False
        details["findings"].append("invalid_jsonld_structure")

    score = safe_score(score)
    details["score"] = score
    return score, details
