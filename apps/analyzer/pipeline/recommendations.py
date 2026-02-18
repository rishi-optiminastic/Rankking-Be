import logging

logger = logging.getLogger("apps")

RECOMMENDATION_RULES = {
    # Content pillar
    "no_h1": {
        "pillar": "content",
        "priority": "critical",
        "title": "Add an H1 Tag",
        "description": "Your page is missing an H1 tag. This is the first thing AI models look at to understand your page topic.",
        "action": "Add a single H1 tag wrapping your page title: <h1>Your Page Title</h1>. Ensure it clearly describes the page content.",
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "content",
    },
    "multiple_h1": {
        "pillar": "content",
        "priority": "high",
        "title": "Use Only One H1 Tag",
        "description": "Your page has multiple H1 tags. AI models expect a single, clear page title.",
        "action": "Keep only one H1 tag for your main page title. Convert other H1 tags to H2 or H3.",
        "impact_estimate": "Could improve your score by ~5 points",
        "category": "content",
    },
    "broken_heading_hierarchy": {
        "pillar": "content",
        "priority": "high",
        "title": "Fix Heading Hierarchy",
        "description": "Your heading tags skip levels (e.g., H1 → H3). AI models use heading hierarchy to understand content structure.",
        "action": "Ensure headings follow a logical order: H1 → H2 → H3. Never skip levels.",
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "content",
    },
    "no_faq_section": {
        "pillar": "content",
        "priority": "high",
        "title": "Add an FAQ Section",
        "description": "No FAQ section detected. FAQ content directly maps to how LLMs extract answers for users.",
        "action": "Add an FAQ section with Q&A pairs. Use <h2>FAQ</h2> or <h2>Frequently Asked Questions</h2> followed by question/answer pairs.",
        "impact_estimate": "Could improve your score by ~15 points",
        "category": "content",
    },
    "no_lists": {
        "pillar": "content",
        "priority": "medium",
        "title": "Add Structured Lists",
        "description": "No bullet or numbered lists found. Lists help AI models parse and cite specific items.",
        "action": "Add <ul> or <ol> lists to present key points, features, or steps in your content.",
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "content",
    },
    "no_tables": {
        "pillar": "content",
        "priority": "low",
        "title": "Add Data Tables",
        "description": "No tables found. Tables help AI extract structured comparisons and data.",
        "action": "Where appropriate, present comparative data or specifications in <table> format.",
        "impact_estimate": "Could improve your score by ~5 points",
        "category": "content",
    },
    "low_word_count": {
        "pillar": "content",
        "priority": "high",
        "title": "Expand Content Length",
        "description": "Your page has thin content (<800 words). Thin content rarely gets cited by AI models.",
        "action": "Expand your content to 1,500+ words. Cover the topic comprehensively with sections, examples, and explanations.",
        "impact_estimate": "Could improve your score by ~15 points",
        "category": "content",
    },
    "poor_readability": {
        "pillar": "content",
        "priority": "medium",
        "title": "Improve Readability",
        "description": "Your content readability is outside the optimal range (8th-12th grade level).",
        "action": "Simplify your writing. Aim for 8th-12th grade reading level. Use shorter sentences, simpler words, and bullet points.",
        "impact_estimate": "Could improve your score by ~5 points",
        "category": "content",
    },
    "poor_paragraph_structure": {
        "pillar": "content",
        "priority": "medium",
        "title": "Improve Paragraph Structure",
        "description": "Paragraphs are too long or too short. Ideal paragraphs are 40-150 words.",
        "action": "Break long paragraphs into focused chunks of 40-150 words each. Each paragraph should cover one idea.",
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "content",
    },
    "few_internal_links": {
        "pillar": "content",
        "priority": "medium",
        "title": "Add More Internal Links",
        "description": "Fewer than 3 internal links found. Internal links help AI models understand your site structure.",
        "action": "Add at least 3 internal links to related pages on your site within your content.",
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "content",
    },

    # Schema pillar
    "no_jsonld": {
        "pillar": "schema",
        "priority": "critical",
        "title": "Add JSON-LD Structured Data",
        "description": "No structured data markup found. Schema markup is essential for AI to understand your content type.",
        "action": 'Add structured data using JSON-LD. At minimum, include Organization schema: <script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Your Company","url":"https://yoursite.com"}</script>',
        "impact_estimate": "Could improve your score by ~25 points",
        "category": "schema",
    },
    "no_faqpage_schema": {
        "pillar": "schema",
        "priority": "high",
        "title": "Add FAQPage Schema",
        "description": "No FAQPage schema found. Pages with FAQ schema show 30-40% higher AI visibility.",
        "action": 'Add FAQPage schema markup to your FAQ section. Use: {"@type":"FAQPage","mainEntity":[{"@type":"Question","name":"...","acceptedAnswer":{"@type":"Answer","text":"..."}}]}',
        "impact_estimate": "Could improve your score by ~15 points",
        "category": "schema",
    },
    "no_article_schema": {
        "pillar": "schema",
        "priority": "high",
        "title": "Add Article Schema",
        "description": "No Article/BlogPosting schema found. Article schema helps AI understand your content's authorship and topic.",
        "action": 'Add Article schema: {"@type":"Article","headline":"...","author":{"@type":"Person","name":"..."},"datePublished":"...","publisher":{"@type":"Organization","name":"..."}}',
        "impact_estimate": "Could improve your score by ~15 points",
        "category": "schema",
    },
    "no_organization_schema": {
        "pillar": "schema",
        "priority": "high",
        "title": "Add Organization Schema",
        "description": "No Organization schema found. This is critical for AI brand recognition.",
        "action": 'Add Organization schema with name, url, logo, and sameAs (social profiles).',
        "impact_estimate": "Could improve your score by ~15 points",
        "category": "schema",
    },
    "invalid_jsonld_structure": {
        "pillar": "schema",
        "priority": "medium",
        "title": "Fix JSON-LD Structure",
        "description": "Your JSON-LD markup has structural issues (missing @context).",
        "action": 'Ensure all JSON-LD blocks include "@context": "https://schema.org" at the top level.',
        "impact_estimate": "Could improve your score by ~15 points",
        "category": "schema",
    },

    # E-E-A-T pillar
    "no_author": {
        "pillar": "eeat",
        "priority": "high",
        "title": "Add Author Attribution",
        "description": "No author name found. E-E-A-T signals are critical for AI trust and citation.",
        "action": 'Add visible author name using <span class="author">Author Name</span> or a meta tag: <meta name="author" content="Author Name">.',
        "impact_estimate": "Could improve your score by ~15 points",
        "category": "eeat",
    },
    "no_author_bio": {
        "pillar": "eeat",
        "priority": "medium",
        "title": "Add Author Bio",
        "description": "No author bio found. Author credentials boost AI trust signals.",
        "action": 'Add an author bio section with credentials: <div class="author-bio">Author Name is a [credentials]...</div>',
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "eeat",
    },
    "no_publish_date": {
        "pillar": "eeat",
        "priority": "medium",
        "title": "Add Publish Date",
        "description": "No publish date found. AI models prefer fresh, dated content.",
        "action": 'Add a visible publish date using <time datetime="2025-01-15">January 15, 2025</time> or add article:published_time meta tag.',
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "eeat",
    },
    "no_updated_date": {
        "pillar": "eeat",
        "priority": "medium",
        "title": "Add Last Updated Date",
        "description": "No update date found. Showing when content was last updated signals freshness to AI.",
        "action": 'Add article:modified_time meta tag or a visible "Last updated: [date]" on the page.',
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "eeat",
    },
    "few_external_citations": {
        "pillar": "eeat",
        "priority": "high",
        "title": "Add External Citations",
        "description": "Fewer than 3 external citations. AI models trust content that references credible sources.",
        "action": "Add 3+ citations linking to authoritative external sources (research papers, industry reports, government sites).",
        "impact_estimate": "Could improve your score by ~15 points",
        "category": "eeat",
    },
    "no_trust_links": {
        "pillar": "eeat",
        "priority": "high",
        "title": "Add Authoritative Source Links",
        "description": "No links to high-trust domains (.gov, .edu, Wikipedia, etc.) found.",
        "action": "Add links to authoritative sources like .gov, .edu, Wikipedia, or major publications to support your claims.",
        "impact_estimate": "Could improve your score by ~15 points",
        "category": "eeat",
    },
    "low_source_diversity": {
        "pillar": "eeat",
        "priority": "medium",
        "title": "Diversify External Sources",
        "description": "External links come from fewer than 3 different domains.",
        "action": "Link to at least 3 different authoritative domains to demonstrate research breadth.",
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "eeat",
    },
    "no_expertise_indicators": {
        "pillar": "eeat",
        "priority": "medium",
        "title": "Add Expertise Indicators",
        "description": "No expertise signals found (credentials, certifications, years of experience).",
        "action": "Mention relevant credentials, certifications, or expertise of content authors.",
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "eeat",
    },

    # Technical pillar
    "no_llms_txt": {
        "pillar": "technical",
        "priority": "high",
        "title": "Create llms.txt File",
        "description": "No llms.txt found. This emerging standard tells AI models what your site is about.",
        "action": "Create an llms.txt file at your domain root (e.g., yoursite.com/llms.txt). Include: site name, description, key pages, and contact info.",
        "impact_estimate": "Could improve your score by ~20 points",
        "category": "technical",
    },
    "ai_bots_blocked": {
        "pillar": "technical",
        "priority": "critical",
        "title": "Unblock AI Crawlers in robots.txt",
        "description": "Your robots.txt blocks AI crawlers. This prevents AI models from indexing your content.",
        "action": "Update your robots.txt to allow AI bots. Add:\nUser-agent: GPTBot\nAllow: /\nUser-agent: Google-Extended\nAllow: /\nUser-agent: anthropic-ai\nAllow: /",
        "impact_estimate": "Could improve your score by ~20 points",
        "category": "technical",
    },
    "no_sitemap": {
        "pillar": "technical",
        "priority": "medium",
        "title": "Add sitemap.xml",
        "description": "No sitemap.xml found. AI crawlers use sitemaps to discover content.",
        "action": "Add a sitemap.xml to your domain root. Most CMS platforms generate these automatically.",
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "technical",
    },
    "meta_noindex": {
        "pillar": "technical",
        "priority": "critical",
        "title": "Remove noindex Meta Tag",
        "description": "Your page has a noindex meta tag, preventing AI models from indexing it.",
        "action": 'Remove <meta name="robots" content="noindex"> or change to content="index, follow".',
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "technical",
    },
    "no_https": {
        "pillar": "technical",
        "priority": "high",
        "title": "Enable HTTPS",
        "description": "Your site does not use HTTPS. Secure connections are a trust signal.",
        "action": "Install an SSL certificate and redirect HTTP to HTTPS.",
        "impact_estimate": "Could improve your score by ~5 points",
        "category": "technical",
    },
    "slow_load_time": {
        "pillar": "technical",
        "priority": "medium",
        "title": "Improve Page Load Speed",
        "description": "Your page takes over 5 seconds to load. Fast pages are prioritized by AI crawlers.",
        "action": "Optimize images, enable compression, use a CDN, and minimize JavaScript.",
        "impact_estimate": "Could improve your score by ~15 points",
        "category": "technical",
    },
    "no_viewport": {
        "pillar": "technical",
        "priority": "medium",
        "title": "Add Viewport Meta Tag",
        "description": "No viewport meta tag found. This affects mobile-friendliness.",
        "action": 'Add <meta name="viewport" content="width=device-width, initial-scale=1"> to your <head>.',
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "technical",
    },
    "no_canonical": {
        "pillar": "technical",
        "priority": "medium",
        "title": "Add Canonical Tag",
        "description": "No canonical URL tag found. This helps prevent duplicate content issues.",
        "action": 'Add <link rel="canonical" href="https://yoursite.com/page-url"> to your <head>.',
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "technical",
    },

    # Entity pillar
    "brand_not_in_ai": {
        "pillar": "entity",
        "priority": "high",
        "title": "Improve AI Brand Visibility",
        "description": "Your brand doesn't appear in AI responses for your category.",
        "action": "Focus on getting mentioned in third-party publications, review sites, and industry directories to build brand authority.",
        "impact_estimate": "Could improve your score by ~20 points",
        "category": "entity",
    },
    "no_social_profiles": {
        "pillar": "entity",
        "priority": "low",
        "title": "Link Social Media Profiles",
        "description": "No social media profile links found on your page.",
        "action": "Link your social media profiles (LinkedIn, Twitter/X, Facebook) from your page footer to strengthen brand entity signals.",
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "entity",
    },
    "no_wikipedia_presence": {
        "pillar": "entity",
        "priority": "medium",
        "title": "Build Wikipedia Presence",
        "description": "Your brand was not found on Wikipedia. Wikipedia presence strongly influences AI knowledge.",
        "action": "Work toward Wikipedia notability through press coverage, awards, and industry recognition.",
        "impact_estimate": "Could improve your score by ~25 points",
        "category": "entity",
    },
}

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def generate_recommendations(pillar_details: dict[str, dict]) -> list[dict]:
    """Generate recommendations from all pillar detail findings."""
    recommendations = []

    for _pillar_name, details in pillar_details.items():
        findings = details.get("findings", [])
        for finding in findings:
            rule = RECOMMENDATION_RULES.get(finding)
            if rule:
                recommendations.append(dict(rule))

    # Sort by priority
    recommendations.sort(key=lambda r: PRIORITY_ORDER.get(r["priority"], 99))
    return recommendations
