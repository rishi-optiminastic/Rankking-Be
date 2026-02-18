import re
import logging
from urllib.parse import urlparse

from .crawler import CrawlResult
from .utils import safe_score

logger = logging.getLogger("apps")

TRUST_DOMAINS = {
    "wikipedia.org", "gov", "edu", "bbc.com", "nytimes.com",
    "reuters.com", "nature.com", "pubmed.ncbi.nlm.nih.gov",
    "scholar.google.com", "forbes.com", "hbr.org",
}


def _is_trust_link(href: str) -> bool:
    try:
        domain = urlparse(href).netloc.lower()
        for trust in TRUST_DOMAINS:
            if domain.endswith(trust):
                return True
    except Exception:
        pass
    return False


def score_eeat(crawl: CrawlResult) -> tuple[float, dict]:
    if not crawl.ok:
        return 0.0, {"error": crawl.error}

    soup = crawl.soup
    html = crawl.html.lower()
    details = {"checks": {}, "findings": []}
    score = 0.0

    # Author name (15 pts)
    author_found = False
    author_meta = soup.find("meta", attrs={"name": "author"})
    if author_meta and author_meta.get("content"):
        author_found = True
    if not author_found:
        for cls in ["author", "byline", "writer"]:
            el = soup.find(class_=re.compile(cls, re.I))
            if el and el.get_text(strip=True):
                author_found = True
                break
    if not author_found:
        el = soup.find(attrs={"rel": "author"})
        if el:
            author_found = True

    if author_found:
        score += 15
        details["checks"]["author_name"] = True
    else:
        details["checks"]["author_name"] = False
        details["findings"].append("no_author")

    # Author bio (10 pts)
    bio_found = False
    for cls in ["author-bio", "author-description", "bio", "about-author"]:
        el = soup.find(class_=re.compile(cls, re.I))
        if el and len(el.get_text(strip=True)) > 30:
            bio_found = True
            break
    if bio_found:
        score += 10
        details["checks"]["author_bio"] = True
    else:
        details["checks"]["author_bio"] = False
        details["findings"].append("no_author_bio")

    # Publish date (10 pts)
    pub_date = False
    time_tag = soup.find("time", attrs={"datetime": True})
    if time_tag:
        pub_date = True
    if not pub_date:
        pub_date = bool(soup.find("meta", property="article:published_time"))
    if pub_date:
        score += 10
        details["checks"]["publish_date"] = True
    else:
        details["checks"]["publish_date"] = False
        details["findings"].append("no_publish_date")

    # Updated date (10 pts)
    updated = bool(soup.find("meta", property="article:modified_time"))
    if not updated:
        updated = "updated" in html and re.search(r"updated.*\d{4}", html) is not None
    if updated:
        score += 10
        details["checks"]["updated_date"] = True
    else:
        details["checks"]["updated_date"] = False
        details["findings"].append("no_updated_date")

    # External citations >= 3 (15 pts)
    external_links = []
    parsed_base = urlparse(crawl.url)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        try:
            parsed = urlparse(href)
            if parsed.netloc and parsed.netloc != parsed_base.netloc:
                external_links.append(href)
        except Exception:
            continue
    ext_count = len(external_links)
    details["checks"]["external_citation_count"] = ext_count
    if ext_count >= 3:
        score += 15
        details["checks"]["external_citations"] = True
    else:
        details["checks"]["external_citations"] = False
        details["findings"].append("few_external_citations")

    # Trust links (15 pts)
    trust_links = [l for l in external_links if _is_trust_link(l)]
    trust_count = len(trust_links)
    details["checks"]["trust_link_count"] = trust_count
    if trust_count >= 1:
        score += 15
        details["checks"]["trust_links"] = True
    else:
        details["checks"]["trust_links"] = False
        details["findings"].append("no_trust_links")

    # Source diversity (10 pts) — different domains in external links
    ext_domains = set()
    for l in external_links:
        try:
            ext_domains.add(urlparse(l).netloc)
        except Exception:
            pass
    details["checks"]["source_diversity"] = len(ext_domains)
    if len(ext_domains) >= 3:
        score += 10
        details["checks"]["diverse_sources"] = True
    else:
        details["checks"]["diverse_sources"] = False
        details["findings"].append("low_source_diversity")

    # Editorial mentions (5 pts) — "according to", "research shows", etc.
    editorial_patterns = [
        r"according to", r"research shows", r"studies suggest",
        r"experts say", r"data from", r"published in",
    ]
    editorial_count = sum(1 for p in editorial_patterns if re.search(p, html))
    details["checks"]["editorial_mentions"] = editorial_count
    if editorial_count >= 2:
        score += 5
        details["checks"]["has_editorial"] = True
    else:
        details["checks"]["has_editorial"] = False

    # Expertise indicators (10 pts) — credentials, certifications
    expertise_patterns = [
        r"ph\.?d", r"m\.?d\.?", r"certified", r"licensed",
        r"years of experience", r"expert in", r"specialist",
    ]
    expertise_count = sum(1 for p in expertise_patterns if re.search(p, html))
    details["checks"]["expertise_indicators"] = expertise_count
    if expertise_count >= 1:
        score += 10
        details["checks"]["has_expertise"] = True
    else:
        details["checks"]["has_expertise"] = False
        details["findings"].append("no_expertise_indicators")

    score = safe_score(score)
    details["score"] = score
    return score, details
