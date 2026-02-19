import json
import logging

from .crawler import CrawlResult
from .utils import safe_score

logger = logging.getLogger("apps")

# Required properties per schema type — if these are missing, schema is hollow
SCHEMA_REQUIRED_PROPS = {
    "FAQPage": {"mainEntity"},
    "Article": {"headline", "author", "datePublished"},
    "NewsArticle": {"headline", "author", "datePublished"},
    "BlogPosting": {"headline", "author", "datePublished"},
    "Organization": {"name", "url"},
    "Product": {"name"},
    "HowTo": {"name", "step"},
    "BreadcrumbList": {"itemListElement"},
}

# Recommended (optional but valuable) properties per type
SCHEMA_RECOMMENDED_PROPS = {
    "FAQPage": set(),
    "Article": {"image", "publisher", "dateModified", "description"},
    "NewsArticle": {"image", "publisher", "dateModified", "description"},
    "BlogPosting": {"image", "publisher", "dateModified", "description"},
    "Organization": {"logo", "sameAs", "description", "contactPoint", "address"},
    "Product": {"description", "image", "offers", "brand", "review", "aggregateRating"},
    "HowTo": {"description", "image", "totalTime"},
    "BreadcrumbList": set(),
}

# Max points per type (split between presence + completeness)
SCHEMA_TYPE_MAX_POINTS = {
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


def _get_all_objects(schema: dict) -> list[dict]:
    """Flatten schema into individual typed objects (handles @graph)."""
    objects = []
    if "@type" in schema:
        objects.append(schema)
    for item in schema.get("@graph", []):
        if isinstance(item, dict):
            objects.extend(_get_all_objects(item))
    return objects


def _get_types(schema: dict) -> set[str]:
    types = set()
    t = schema.get("@type", "")
    if isinstance(t, list):
        types.update(t)
    elif isinstance(t, str):
        types.add(t)
    for item in schema.get("@graph", []):
        if isinstance(item, dict):
            types.update(_get_types(item))
    return types


def _compute_completeness(obj: dict, schema_type: str) -> tuple[float, dict]:
    """Score a single schema object on property completeness. Returns (0.0-1.0, report)."""
    required = SCHEMA_REQUIRED_PROPS.get(schema_type, set())
    recommended = SCHEMA_RECOMMENDED_PROPS.get(schema_type, set())
    report = {"required_present": [], "required_missing": [], "recommended_present": [], "recommended_missing": []}

    # Check required props
    for prop in required:
        val = obj.get(prop)
        if val is not None and val != "" and val != [] and val != {}:
            report["required_present"].append(prop)
        else:
            report["required_missing"].append(prop)

    # Check recommended props
    for prop in recommended:
        val = obj.get(prop)
        if val is not None and val != "" and val != [] and val != {}:
            report["recommended_present"].append(prop)
        else:
            report["recommended_missing"].append(prop)

    # Completeness: required = 70% weight, recommended = 30% weight
    req_total = len(required)
    rec_total = len(recommended)
    req_score = len(report["required_present"]) / req_total if req_total else 1.0
    rec_score = len(report["recommended_present"]) / rec_total if rec_total else 1.0

    completeness = req_score * 0.7 + rec_score * 0.3
    return completeness, report


def score_schema(crawl: CrawlResult) -> tuple[float, dict]:
    if not crawl.ok:
        return 0.0, {"error": crawl.error}

    soup = crawl.soup
    details = {"checks": {}, "findings": [], "types_found": [], "completeness": {}}
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

    # Flatten all schema objects
    all_objects = []
    for s in schemas:
        all_objects.extend(_get_all_objects(s))

    # Collect all types
    all_types = set()
    for s in schemas:
        all_types.update(_get_types(s))

    details["types_found"] = sorted(all_types)

    # Score each schema type with completeness
    type_score = 0.0
    for schema_type, max_points in SCHEMA_TYPE_MAX_POINTS.items():
        if schema_type in all_types:
            # Find the object with this type
            matching_obj = None
            for obj in all_objects:
                obj_type = obj.get("@type", "")
                obj_types = obj_type if isinstance(obj_type, list) else [obj_type]
                if schema_type in obj_types:
                    matching_obj = obj
                    break

            if matching_obj:
                completeness, report = _compute_completeness(matching_obj, schema_type)
                actual_points = max_points * completeness
                type_score += actual_points
                details["completeness"][schema_type] = {
                    "completeness": round(completeness * 100),
                    "points": round(actual_points, 1),
                    "max_points": max_points,
                    "required_present": report["required_present"],
                    "required_missing": report["required_missing"],
                    "recommended_present": report["recommended_present"],
                    "recommended_missing": report["recommended_missing"],
                }
                details["checks"][f"has_{schema_type}"] = True

                if report["required_missing"]:
                    details["findings"].append(f"incomplete_{schema_type.lower()}_schema")
            else:
                # Type exists somewhere (maybe nested) but we can't inspect it
                type_score += max_points * 0.5
                details["checks"][f"has_{schema_type}"] = True
        else:
            details["checks"][f"has_{schema_type}"] = False

    # Cap type score at 75
    type_score = min(type_score, 75)
    score += type_score

    # Check missing important types
    if "FAQPage" not in all_types:
        details["findings"].append("no_faqpage_schema")
    if "Article" not in all_types and "BlogPosting" not in all_types and "NewsArticle" not in all_types:
        details["findings"].append("no_article_schema")
    if "Organization" not in all_types:
        details["findings"].append("no_organization_schema")

    # Validity check (15 pts)
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
