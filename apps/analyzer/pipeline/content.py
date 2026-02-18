import logging
import re

from .crawler import CrawlResult
from .utils import count_words, safe_score

logger = logging.getLogger("apps")

try:
    import textstat
except ImportError:
    textstat = None


def score_content(crawl: CrawlResult) -> tuple[float, dict]:
    if not crawl.ok:
        return 0.0, {"error": crawl.error}

    soup = crawl.soup
    text = crawl.text
    details = {"checks": {}, "findings": []}
    score = 0.0

    # H1 present and singular (10 pts)
    h1_tags = soup.find_all("h1")
    h1_count = len(h1_tags)
    if h1_count == 1:
        score += 10
        details["checks"]["h1_singular"] = True
    else:
        details["checks"]["h1_singular"] = False
        if h1_count == 0:
            details["findings"].append("no_h1")
        else:
            details["findings"].append("multiple_h1")

    # Proper H-tag hierarchy (10 pts)
    headings = []
    for level in range(1, 7):
        for tag in soup.find_all(f"h{level}"):
            headings.append(level)
    hierarchy_ok = True
    for i in range(1, len(headings)):
        if headings[i] - headings[i - 1] > 1:
            hierarchy_ok = False
            break
    if hierarchy_ok and headings:
        score += 10
        details["checks"]["heading_hierarchy"] = True
    else:
        details["checks"]["heading_hierarchy"] = False
        details["findings"].append("broken_heading_hierarchy")

    # FAQ section present (15 pts)
    faq_found = False
    for tag in soup.find_all(re.compile(r"^h[2-4]$")):
        if tag.get_text() and "faq" in tag.get_text().lower():
            faq_found = True
            break
    if not faq_found:
        faq_found = bool(soup.find(class_=re.compile(r"faq", re.I)))
    if not faq_found:
        faq_found = bool(soup.find(id=re.compile(r"faq", re.I)))
    if faq_found:
        score += 15
        details["checks"]["faq_section"] = True
    else:
        details["checks"]["faq_section"] = False
        details["findings"].append("no_faq_section")

    # Lists present (10 pts)
    lists = soup.find_all(["ul", "ol"])
    if lists:
        score += 10
        details["checks"]["lists_present"] = True
        details["checks"]["list_count"] = len(lists)
    else:
        details["checks"]["lists_present"] = False
        details["findings"].append("no_lists")

    # Tables present (5 pts)
    tables = soup.find_all("table")
    if tables:
        score += 5
        details["checks"]["tables_present"] = True
    else:
        details["checks"]["tables_present"] = False
        details["findings"].append("no_tables")

    # Word count scaled, max at 1500+ (15 pts)
    word_count = count_words(text)
    details["checks"]["word_count"] = word_count
    if word_count >= 1500:
        score += 15
    elif word_count >= 800:
        score += 10
    elif word_count >= 300:
        score += 5
    else:
        details["findings"].append("low_word_count")

    # Readability via Flesch-Kincaid (15 pts)
    if textstat and len(text) > 100:
        fk_grade = textstat.flesch_kincaid_grade(text)
        details["checks"]["fk_grade"] = round(fk_grade, 1)
        if 6 <= fk_grade <= 12:
            score += 15
        elif 4 <= fk_grade <= 14:
            score += 10
        else:
            score += 5
            details["findings"].append("poor_readability")
    else:
        details["checks"]["fk_grade"] = None
        score += 7  # Neutral if can't compute

    # Paragraph structure — avg 40-150 words (10 pts)
    paragraphs = soup.find_all("p")
    para_word_counts = [count_words(p.get_text()) for p in paragraphs if p.get_text(strip=True)]
    if para_word_counts:
        avg_para = sum(para_word_counts) / len(para_word_counts)
        details["checks"]["avg_paragraph_words"] = round(avg_para, 1)
        details["checks"]["paragraph_count"] = len(para_word_counts)
        if 40 <= avg_para <= 150:
            score += 10
        elif 20 <= avg_para <= 200:
            score += 5
        else:
            details["findings"].append("poor_paragraph_structure")
    else:
        details["checks"]["avg_paragraph_words"] = 0
        details["findings"].append("no_paragraphs")

    # Internal links >= 3 (10 pts)
    internal_link_count = len(crawl.internal_links)
    details["checks"]["internal_link_count"] = internal_link_count
    if internal_link_count >= 3:
        score += 10
        details["checks"]["internal_links_sufficient"] = True
    else:
        details["checks"]["internal_links_sufficient"] = False
        details["findings"].append("few_internal_links")

    details["score"] = safe_score(score)
    return safe_score(score), details
