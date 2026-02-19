import json
import logging
import re
from urllib.parse import urlparse

from .crawler import CrawlResult
from .utils import extract_brand_name, extract_domain, safe_score

logger = logging.getLogger("apps")


# ── Industry-specific probe templates ─────────────────────────────────────
# {industry} is replaced with detected industry keywords (NOT the brand name)
INDUSTRY_PROBES = {
    "software_developer": [
        "Who are the best freelance software developers to hire in 2024?",
        "What portfolio websites do top software engineers use?",
        "What should I look for when hiring a full-stack developer?",
        "Who are the most recommended web developers for startups?",
        "What are the best platforms to find expert software engineers?",
    ],
    "saas": [
        "What are the best {industry} tools available today?",
        "Compare the top {industry} platforms for businesses",
        "Which {industry} solution would you recommend for a growing company?",
        "What are the leading {industry} providers in 2024?",
        "What should I consider when choosing a {industry} platform?",
    ],
    "ecommerce": [
        "What are the best online stores for {industry}?",
        "Which {industry} brands offer the best value?",
        "What are the most trusted {industry} shops online?",
        "Compare the top {industry} retailers",
        "Where should I buy {industry} products online?",
    ],
    "agency": [
        "What are the best {industry} agencies to hire?",
        "Who are the top-rated {industry} companies?",
        "Which {industry} firms deliver the best results?",
        "What should I look for in a {industry} agency?",
        "Compare the leading {industry} service providers",
    ],
    "health": [
        "What are the most trusted {industry} resources online?",
        "Which websites provide reliable {industry} information?",
        "What are the best {industry} services available?",
        "Who are the leading {industry} providers?",
        "What should I look for in a {industry} provider?",
    ],
    "education": [
        "What are the best {industry} courses and resources?",
        "Which platforms offer the best {industry} training?",
        "What are the top {industry} learning websites?",
        "Compare the best online {industry} programs",
        "Where can I learn {industry} effectively online?",
    ],
    "default": [
        "What are the best {industry} services available today?",
        "Who are the top providers in the {industry} space?",
        "What should I look for when choosing a {industry} provider?",
        "Compare the leading {industry} companies and platforms",
        "Which {industry} solutions do experts recommend?",
    ],
}


def _detect_industry_keywords(soup, text: str) -> tuple[str, str]:
    """
    Detect industry category and keywords from page content.
    Returns (category_key, industry_description) — NO brand name included.
    """
    meta_desc = soup.find("meta", attrs={"name": "description"})
    desc = meta_desc["content"].strip().lower() if meta_desc and meta_desc.get("content") else ""
    title = ""
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        title = title_tag.string.strip().lower()

    combined = f"{title} {desc} {text[:1500].lower()}"

    # Industry detection with keyword extraction
    patterns = [
        ("software_developer", ["developer", "software engineer", "full stack", "frontend", "backend", "programmer", "coder", "portfolio"],
         "software development"),
        ("saas", ["saas", "software as a service", "cloud platform", "subscription", "api", "dashboard"],
         None),  # Will extract from content
        ("ecommerce", ["shop", "store", "buy", "product", "cart", "price", "ecommerce"],
         None),
        ("agency", ["agency", "consulting", "services", "firm", "solutions provider"],
         None),
        ("health", ["health", "medical", "doctor", "wellness", "clinic", "therapy", "healthcare"],
         "healthcare"),
        ("education", ["course", "learn", "education", "training", "tutorial", "university"],
         "education"),
        ("finance", ["finance", "banking", "investment", "fintech", "insurance", "trading"],
         "financial services"),
        ("legal", ["lawyer", "attorney", "legal", "law firm", "litigation"],
         "legal services"),
        ("news", ["news", "media", "journalism", "editorial", "press"],
         "news and media"),
        ("local_business", ["local", "restaurant", "salon", "repair", "plumber", "dentist"],
         None),
    ]

    for category, keywords, default_desc in patterns:
        hits = [kw for kw in keywords if kw in combined]
        if len(hits) >= 2:
            # Extract specific industry description from content
            if default_desc:
                industry_desc = default_desc
            else:
                # Try to build description from meta description (without brand)
                industry_desc = _extract_industry_description(soup, combined, hits)
            return category, industry_desc

    # Fallback: try to extract something useful
    industry_desc = _extract_industry_description(soup, combined, [])
    return "default", industry_desc


def _extract_industry_description(soup, combined: str, keyword_hits: list[str]) -> str:
    """Extract an industry description without including the brand name."""
    # Look for common patterns in headings that describe what the site does
    h1 = soup.find("h1")
    h2s = soup.find_all("h2")[:5]

    # Check for service/product descriptions in headings
    service_keywords = [
        "services", "solutions", "products", "features", "what we do",
        "how it works", "offerings", "capabilities",
    ]

    for h in [h1] + h2s:
        if h and h.get_text(strip=True):
            h_text = h.get_text(strip=True).lower()
            for kw in service_keywords:
                if kw in h_text:
                    return h_text[:60]

    # Use keyword hits to build description
    if keyword_hits:
        return " and ".join(keyword_hits[:3])

    # Last resort: use meta keywords
    meta_kw = soup.find("meta", attrs={"name": "keywords"})
    if meta_kw and meta_kw.get("content"):
        keywords = meta_kw["content"].strip()
        return keywords[:60]

    return "this type of service"


def _build_site_context(soup, url: str, text: str) -> str:
    """Build rich context for Gemini probe generation (no brand name)."""
    parts = []

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        parts.append(f"Description: {meta_desc['content'].strip()}")

    h1 = soup.find("h1")
    if h1:
        parts.append(f"Main heading: {h1.get_text(strip=True)}")

    h2s = [h.get_text(strip=True) for h in soup.find_all("h2")[:5]]
    if h2s:
        parts.append(f"Sections: {', '.join(h2s)}")

    parts.append(f"Content: {text[:500]}")
    return "\n".join(parts)


def _generate_probes_llm(brand_name: str, site_context: str, industry_desc: str) -> list[str]:
    """Use LLM (via OpenRouter) to generate 5 category-specific probe prompts."""
    try:
        from .llm import ask_llm

        prompt = (
            f"I need to test whether the brand '{brand_name}' appears in AI search results.\n\n"
            f"Their website is about: {industry_desc}\n"
            f"Site context:\n{site_context}\n\n"
            f"Generate exactly 5 questions that a potential CUSTOMER would naturally ask "
            f"an AI assistant (ChatGPT, Perplexity, Gemini) about this INDUSTRY/CATEGORY.\n\n"
            f"CRITICAL RULES:\n"
            f"- Questions must be about the CATEGORY/INDUSTRY, NOT about the brand\n"
            f"- Do NOT include the brand name '{brand_name}' anywhere in the questions\n"
            f"- Do NOT include any person's name in the questions\n"
            f"- Questions should be what a real user would ask when looking for this type of service\n"
            f"- Vary intent: discovery, comparison, recommendation, best-of, how-to-choose\n"
            f"- Be specific to the actual niche, not generic\n\n"
            f"GOOD examples (for a payment processing company):\n"
            f'- "What are the best payment processing platforms for online businesses?"\n'
            f'- "Compare the top payment gateways for SaaS companies"\n\n'
            f"BAD examples:\n"
            f'- "Tell me about [Brand Name]" (mentions brand)\n'
            f'- "What are the best companies?" (too generic)\n\n'
            f"Reply ONLY with a JSON array of 5 strings."
        )
        text = ask_llm(prompt, preferred_provider="gemini", max_tokens=1024, purpose="AI Probe Generation")

        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            probes = json.loads(match.group())
            if isinstance(probes, list) and len(probes) >= 3:
                # Extra safety: filter out any probe that contains the brand name
                clean_probes = []
                brand_lower = brand_name.lower()
                brand_parts = [p for p in brand_lower.split() if len(p) >= 4]
                for p in probes[:5]:
                    p_lower = str(p).lower()
                    if brand_lower in p_lower:
                        continue
                    if any(part in p_lower for part in brand_parts):
                        continue
                    clean_probes.append(str(p))
                if len(clean_probes) >= 3:
                    return clean_probes[:5]
    except Exception as exc:
        logger.warning("Probe generation failed: %s", exc)

    return []


def _build_brand_aliases(brand_name: str, url: str) -> list[str]:
    """Build a list of brand name variations to match against."""
    aliases = set()
    brand_lower = brand_name.lower().strip()

    # Original name
    aliases.add(brand_lower)

    # Without common suffixes
    for suffix in [" inc", " inc.", " llc", " ltd", " ltd.", " corp", " corp.", " co", " co."]:
        if brand_lower.endswith(suffix):
            aliases.add(brand_lower[: -len(suffix)].strip())

    # Domain name as alias (e.g., "stripe" from stripe.com)
    domain = extract_domain(url)
    domain_name = domain.split(".")[0].lower()
    if len(domain_name) >= 3:
        aliases.add(domain_name)

    # CamelCase split (e.g., "CarbonCut" → "carbon cut")
    camel_split = re.sub(r"([a-z])([A-Z])", r"\1 \2", brand_name).lower()
    if camel_split != brand_lower:
        aliases.add(camel_split)

    # No spaces version (e.g., "carbon cut" → "carboncut")
    no_spaces = brand_lower.replace(" ", "").replace("-", "")
    if len(no_spaces) >= 3:
        aliases.add(no_spaces)

    # Filter out too-short aliases and overly long ones (likely page titles, not brands)
    return [a for a in aliases if 3 <= len(a) <= 40]


def _match_brand(aliases: list[str], text: str) -> tuple[bool, float, str]:
    """Check if any brand alias appears in text."""
    text_lower = text.lower()

    # 1. Exact word-boundary match
    for alias in aliases:
        pattern = r'(?<![a-z])' + re.escape(alias) + r'(?![a-z])'
        if re.search(pattern, text_lower):
            return True, 1.0, "exact"

    # 2. Substring match (lower confidence)
    for alias in aliases:
        if len(alias) >= 5 and alias in text_lower:
            return True, 0.8, "substring"

    # 3. URL/domain match — check if the site's URL appears
    for alias in aliases:
        if "." not in alias and len(alias) >= 4:
            # Check for domain mention like "stripe.com"
            domain_pattern = re.escape(alias) + r'\.\w{2,4}'
            if re.search(domain_pattern, text_lower):
                return True, 0.9, "domain"

    # 4. Fuzzy match
    try:
        import Levenshtein

        words = text_lower.split()
        cleaned_words = [w.strip(".,;:!?()[]{}\"'") for w in words]

        for alias in aliases:
            if " " not in alias:
                for word in cleaned_words:
                    if len(word) >= 3 and Levenshtein.ratio(alias, word) > 0.85:
                        return True, 0.7, "fuzzy"
            else:
                alias_parts = alias.split()
                for i in range(len(cleaned_words) - len(alias_parts) + 1):
                    chunk = " ".join(cleaned_words[i:i + len(alias_parts)])
                    if Levenshtein.ratio(alias, chunk) > 0.85:
                        return True, 0.7, "fuzzy_ngram"
    except ImportError:
        pass

    return False, 0.0, "none"


def _analyze_mention_quality(text: str, aliases: list[str]) -> dict:
    """Analyze HOW the brand is mentioned — position, sentiment, context."""
    text_lower = text.lower()

    result = {
        "position_score": 0.0,
        "sentiment": "neutral",
        "context": "listed",
        "prominence": 0.0,
    }

    # Find first mention position
    first_pos = len(text_lower)
    for alias in aliases:
        pos = text_lower.find(alias)
        if pos != -1 and pos < first_pos:
            first_pos = pos

    if first_pos == len(text_lower):
        return result

    # Position score
    position_ratio = first_pos / max(len(text_lower), 1)
    result["position_score"] = max(0.0, 1.0 - position_ratio)

    # Surrounding context
    context_start = max(0, first_pos - 200)
    context_end = min(len(text_lower), first_pos + 300)
    surrounding = text_lower[context_start:context_end]

    # Sentiment
    positive = ["recommend", "best", "top", "leading", "excellent", "popular",
                "trusted", "innovative", "standout", "preferred", "outstanding", "great"]
    negative = ["avoid", "worst", "poor", "weak", "lacking", "limited", "issue", "problem"]

    pos_hits = sum(1 for s in positive if s in surrounding)
    neg_hits = sum(1 for s in negative if s in surrounding)

    if pos_hits > neg_hits:
        result["sentiment"] = "positive"
    elif neg_hits > pos_hits:
        result["sentiment"] = "negative"

    # Context type
    if any(w in surrounding for w in ["recommend", "suggest", "best choice", "top pick"]):
        result["context"] = "recommended"
    elif any(w in surrounding for w in ["compare", "versus", "vs", "alternative"]):
        result["context"] = "compared"
    elif any(w in surrounding for w in ["#1", "number one", "first", "leading"]):
        result["context"] = "top_mentioned"

    # Prominence
    context_bonus = {"recommended": 0.3, "top_mentioned": 0.25, "compared": 0.1, "listed": 0.0}
    sentiment_bonus = {"positive": 0.2, "neutral": 0.0, "negative": -0.2}
    result["prominence"] = min(1.0, max(0.0,
        result["position_score"] * 0.5
        + context_bonus.get(result["context"], 0)
        + sentiment_bonus.get(result["sentiment"], 0)
    ))

    return result


def _fire_probe(prompt: str, brand_aliases: list[str]) -> tuple[str, bool, float, dict]:
    """Fire a single probe across multiple LLM providers via OpenRouter."""
    try:
        from .llm import ask_multiple_llms

        # Ask all 3 providers the same question
        responses = ask_multiple_llms(prompt, purpose="AI Visibility Probe")

        # Combine all responses for matching
        all_text = "\n\n".join(f"[{provider}]: {resp}" for provider, resp in responses.items() if resp)
        if not all_text:
            return "", False, 0.0, {}

        # Check brand mention across all responses
        found, match_confidence, match_type = _match_brand(brand_aliases, all_text)

        quality = {"position_score": 0, "sentiment": "neutral", "context": "none", "prominence": 0}
        if found:
            quality = _analyze_mention_quality(all_text, brand_aliases)

        # Count how many providers mentioned the brand
        provider_mentions = 0
        for provider, resp in responses.items():
            if resp:
                pf_found, _, _ = _match_brand(brand_aliases, resp)
                if pf_found:
                    provider_mentions += 1

        # Boost confidence if multiple providers mention the brand
        if found:
            provider_ratio = provider_mentions / max(len(responses), 1)
            prominence_multiplier = 0.5 + quality["prominence"] * 0.5
            final_confidence = match_confidence * prominence_multiplier * (0.7 + 0.3 * provider_ratio)
        else:
            final_confidence = 0.0

        quality["providers_checked"] = len(responses)
        quality["providers_mentioned"] = provider_mentions

        return all_text[:2000], found, final_confidence, quality
    except Exception as exc:
        logger.warning("Multi-LLM probe failed: %s", exc)
        return "", False, 0.0, {}


def score_ai_visibility(crawl: CrawlResult) -> tuple[float, dict, list[dict]]:
    """Returns (score, details, probes_data)."""
    if not crawl.ok:
        return 0.0, {"error": crawl.error}, []

    soup = crawl.soup
    brand_name = extract_brand_name(soup, crawl.url)
    brand_aliases = _build_brand_aliases(brand_name, crawl.url)

    # Detect industry keywords — NOT the brand name
    category, industry_desc = _detect_industry_keywords(soup, crawl.text)
    site_context = _build_site_context(soup, crawl.url, crawl.text)

    details = {
        "checks": {
            "brand_name": brand_name,
            "brand_aliases": brand_aliases[:5],
            "industry_detected": industry_desc,
            "category": category,
        },
        "findings": [],
    }
    probes_data = []
    score = 0.0

    # Try LLM-generated probes first
    probe_prompts = _generate_probes_llm(brand_name, site_context, industry_desc)

    if probe_prompts:
        details["checks"]["probe_source"] = "gemini"
    else:
        # Fallback: use industry-specific templates with category keywords
        templates = INDUSTRY_PROBES.get(category, INDUSTRY_PROBES["default"])
        probe_prompts = [t.format(industry=industry_desc) for t in templates]
        details["checks"]["probe_source"] = "fallback"

    details["checks"]["probes_generated"] = len(probe_prompts)

    # Score probes
    max_per_probe = 100.0 / max(len(probe_prompts), 1)

    for prompt in probe_prompts:
        response_text, mentioned, confidence, quality = _fire_probe(prompt, brand_aliases)

        probe_score = 0.0
        if mentioned:
            base_points = max_per_probe * 0.6
            quality_points = max_per_probe * 0.4 * quality.get("prominence", 0.5)
            probe_score = base_points + quality_points

        score += probe_score

        probes_data.append({
            "prompt_used": prompt,
            "llm_response": response_text[:2000],
            "brand_mentioned": mentioned,
            "confidence": round(confidence, 2),
        })

    mentions = sum(1 for p in probes_data if p["brand_mentioned"])
    details["checks"]["probes_total"] = len(probes_data)
    details["checks"]["probes_mentioned"] = mentions

    if mentions == 0:
        details["findings"].append("brand_not_in_ai")

    score = safe_score(score)
    details["score"] = score
    return score, details, probes_data
