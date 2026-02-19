import logging

logger = logging.getLogger("apps")

RECOMMENDATION_RULES = {
    # ── Content Structure ─────────────────────────────────────────────────
    "no_h1": {
        "pillar": "content",
        "priority": "critical",
        "title": "Add an H1 Tag",
        "description": "Your page is missing an H1 tag. This is the first thing AI models look at to understand your page topic.",
        "action": "Add a single H1 tag wrapping your page title: <h1>Your Page Title</h1>. Ensure it clearly describes the page content.",
        "impact_estimate": "Could improve your score by ~5 points",
        "category": "content",
    },
    "multiple_h1": {
        "pillar": "content",
        "priority": "high",
        "title": "Use Only One H1 Tag",
        "description": "Your page has multiple H1 tags. AI models expect a single, clear page title.",
        "action": "Keep only one H1 tag for your main page title. Convert other H1 tags to H2 or H3.",
        "impact_estimate": "Could improve your score by ~3 points",
        "category": "content",
    },
    "broken_heading_hierarchy": {
        "pillar": "content",
        "priority": "high",
        "title": "Fix Heading Hierarchy",
        "description": "Your heading tags skip levels (e.g., H1 -> H3). AI models use heading hierarchy to understand content structure.",
        "action": "Ensure headings follow a logical order: H1 -> H2 -> H3. Never skip levels.",
        "impact_estimate": "Could improve your score by ~5 points",
        "category": "content",
    },
    "no_faq_section": {
        "pillar": "content",
        "priority": "high",
        "title": "Add an FAQ Section",
        "description": "No FAQ section detected. Princeton GEO research shows FAQ content directly maps to how LLMs extract answers. Pages with FAQ schema show 40% higher AI visibility.",
        "action": "Add an FAQ section with Q&A pairs. Use <h2>FAQ</h2> or <h2>Frequently Asked Questions</h2> followed by question/answer pairs. Also add FAQPage schema markup.",
        "impact_estimate": "Could improve your score by ~8 points (+40% AI visibility with schema)",
        "category": "content",
    },
    "no_lists": {
        "pillar": "content",
        "priority": "medium",
        "title": "Add Structured Lists",
        "description": "No bullet or numbered lists found. Lists help AI models parse and cite specific items.",
        "action": "Add <ul> or <ol> lists to present key points, features, or steps in your content.",
        "impact_estimate": "Could improve your score by ~4 points",
        "category": "content",
    },
    "no_answer_first": {
        "pillar": "content",
        "priority": "high",
        "title": "Use Answer-First Format",
        "description": "Your content doesn't start with a direct answer. AI models prefer content that leads with a clear, concise answer before expanding on details.",
        "action": "Restructure your opening paragraph to directly answer the main question your page addresses. Start with 'X is...' or 'The answer is...' before diving into details. This is what AI models extract first.",
        "impact_estimate": "Could improve your score by ~5 points",
        "category": "content",
    },
    "few_internal_links": {
        "pillar": "content",
        "priority": "medium",
        "title": "Add More Internal Links",
        "description": "Fewer than 3 internal links found. Internal links help AI models understand your site structure and content relationships.",
        "action": "Add at least 3 internal links to related pages on your site within your content.",
        "impact_estimate": "Could improve your score by ~5 points",
        "category": "content",
    },

    # ── GEO Content Quality (Princeton Research Methods) ──────────────────

    # Method 1: Citations (+40% visibility boost — highest impact)
    "no_citations": {
        "pillar": "content",
        "priority": "critical",
        "title": "Add Authoritative Citations (Research: +40% Visibility)",
        "description": "No citations or references found. The Princeton GEO study found that adding authoritative citations provides the HIGHEST visibility boost of all methods — up to 40%. AI systems strongly prefer well-researched content with credible sources.",
        "action": "Add 3-5 citations per major section. Use formats like:\n- 'According to a 2024 Stanford study, AI tools improve productivity by 55% (Chen et al., 2024)'\n- 'Research from McKinsey shows that...'\n- 'As published in Nature...'\nAlso consider adding a References/Sources section at the end.",
        "impact_estimate": "Could improve your score by ~12 points (highest-impact GEO method)",
        "category": "content",
    },

    # Method 2: Statistics (+37% visibility boost)
    "no_statistics": {
        "pillar": "content",
        "priority": "critical",
        "title": "Add Statistics and Data Points (Research: +37% Visibility)",
        "description": "No statistics or quantitative data found. The Princeton study shows statistics addition provides a 37% visibility boost — the second most effective GEO method. AI systems prioritize factual, verifiable information.",
        "action": "Include specific numbers throughout your content:\n- '67% of Fortune 500 companies now use AI chatbots'\n- 'Revenue increased by $2.3 million in Q3 2024'\n- 'The average response time improved from 4.2s to 0.8s'\nAlways cite the source of statistics for maximum credibility.",
        "impact_estimate": "Could improve your score by ~10 points (2nd highest-impact GEO method)",
        "category": "content",
    },

    # Method 3: Expert Quotes (+30% visibility boost)
    "no_expert_quotes": {
        "pillar": "content",
        "priority": "high",
        "title": "Add Expert Quotes with Attribution (Research: +30% Visibility)",
        "description": "No expert quotes detected. Adding properly attributed quotes from recognized experts boosts AI visibility by up to 30%. Quotes provide extractable, citable content that AI models prefer.",
        "action": "Add 1-3 expert quotes with proper attribution:\n- '\"AI will be the great equalizer for small businesses,\" predicts Sam Altman, CEO of OpenAI.'\n- Use <blockquote> tags for longer quotes\n- Include the expert's title/credentials for maximum E-E-A-T impact",
        "impact_estimate": "Could improve your score by ~8 points",
        "category": "content",
    },

    # Method 4: Authoritative Tone (+25% visibility boost)
    "weak_authoritative_tone": {
        "pillar": "content",
        "priority": "high",
        "title": "Strengthen Authoritative Tone (Research: +25% Visibility)",
        "description": "Your content uses hedging or uncertain language instead of confident, authoritative writing. The Princeton study found authoritative tone boosts visibility by 25%. AI models assess content quality partly through linguistic signals of authority.",
        "action": "Replace uncertain language with confident statements:\n- AVOID: 'This might help with SEO, I think'\n- USE: 'This strategy demonstrably improves SEO performance'\n- AVOID: 'Maybe you should consider...'\n- USE: 'Based on our analysis of 10,000 websites, implementing structured data increases organic traffic by 30%'\nBack up confident claims with data.",
        "impact_estimate": "Could improve your score by ~8 points",
        "category": "content",
    },

    # Method 5: Readability (+20% visibility boost)
    "poor_readability": {
        "pillar": "content",
        "priority": "medium",
        "title": "Improve Readability (Research: +20% Visibility)",
        "description": "Your content readability is outside the optimal range. The Princeton study shows easy-to-understand content gets a 20% visibility boost. AI aims to provide helpful answers to users of all knowledge levels.",
        "action": "Aim for 8th-12th grade reading level (Flesch-Kincaid):\n- Use shorter sentences (15-20 words average)\n- Replace jargon with plain language, or explain it: 'RAG (Retrieval-Augmented Generation) works like a research assistant'\n- Use bullet points for complex lists\n- Break long paragraphs into 2-3 sentences each",
        "impact_estimate": "Could improve your score by ~7 points",
        "category": "content",
    },

    # Method 6: Technical Terms (+18% visibility boost)
    "no_technical_terms": {
        "pillar": "content",
        "priority": "medium",
        "title": "Include Domain-Specific Terminology (Research: +18% Visibility)",
        "description": "No technical terms or domain-specific terminology detected. Including appropriate technical terms signals expertise and helps AI match your content to specialized queries (+18% visibility boost).",
        "action": "Include domain-specific terms with definitions:\n- 'Core Web Vitals: LCP (Largest Contentful Paint), CLS (Cumulative Layout Shift)'\n- Define acronyms on first use: 'Retrieval-Augmented Generation (RAG)'\n- Use industry-standard terminology naturally throughout\n- Balance: use technical terms but explain them for accessibility",
        "impact_estimate": "Could improve your score by ~5 points",
        "category": "content",
    },

    # Method 7: Vocabulary Diversity (+15% visibility boost)
    "low_vocabulary_diversity": {
        "pillar": "content",
        "priority": "medium",
        "title": "Increase Vocabulary Diversity (Research: +15% Visibility)",
        "description": "Your content has low vocabulary diversity (repetitive word usage). Diverse vocabulary indicates depth of knowledge and makes content more distinguishable to AI models (+15% visibility).",
        "action": "Improve vocabulary variety:\n- Use synonyms instead of repeating the same terms\n- Vary your sentence structures\n- Include contextual variations (e.g., 'AI', 'artificial intelligence', 'machine learning systems')\n- Use industry-specific jargon mixed with plain language",
        "impact_estimate": "Could improve your score by ~5 points",
        "category": "content",
    },

    # Method 8: Fluency
    "low_word_count": {
        "pillar": "content",
        "priority": "high",
        "title": "Expand Content Length",
        "description": "Your page has thin content (<800 words). Thin content rarely gets cited by AI models. The Princeton study shows comprehensive, fluent content gets 15-30% more AI visibility.",
        "action": "Expand your content to 1,500+ words. Cover the topic comprehensively with:\n- Multiple sections with clear headings\n- Examples and case studies\n- Statistics and citations\n- FAQ section at the end",
        "impact_estimate": "Could improve your score by ~2 points (also unlocks other GEO methods)",
        "category": "content",
    },
    "poor_paragraph_structure": {
        "pillar": "content",
        "priority": "medium",
        "title": "Improve Paragraph Structure",
        "description": "Paragraphs are too long or too short. The Princeton study recommends 2-3 sentences per paragraph for optimal AI readability.",
        "action": "Break long paragraphs into focused chunks of 20-80 words each. Each paragraph should cover one idea with a clear topic sentence.",
        "impact_estimate": "Could improve your score by ~2 points",
        "category": "content",
    },

    # Method 9: Keyword Stuffing Penalty
    "keyword_stuffing": {
        "pillar": "content",
        "priority": "critical",
        "title": "Remove Keyword Stuffing (Research: -10% Visibility Penalty)",
        "description": "Keyword stuffing detected! Unlike traditional SEO, the Princeton study found keyword stuffing ACTIVELY DECREASES AI visibility by 10%. This is one of the few methods that actually hurts your score.",
        "action": "Remove repetitive keyword usage:\n- BAD: 'SEO optimization for SEO is the best SEO strategy. Our SEO experts provide SEO services.'\n- GOOD: 'Search engine optimization is essential for online visibility. Our experts help businesses improve their search rankings through strategic content development.'\nWrite naturally and use synonyms.",
        "impact_estimate": "Removing stuffing could recover ~5 points and prevent visibility penalty",
        "category": "content",
    },

    # ── Schema pillar ─────────────────────────────────────────────────────
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
        "title": "Add FAQPage Schema (+40% AI Visibility)",
        "description": "No FAQPage schema found. The Princeton study specifically highlights FAQPage schema as providing up to 40% higher AI visibility.",
        "action": 'Add FAQPage schema markup to your FAQ section: {"@type":"FAQPage","mainEntity":[{"@type":"Question","name":"...","acceptedAnswer":{"@type":"Answer","text":"..."}}]}',
        "impact_estimate": "Could improve your score by ~15 points (+40% AI visibility)",
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
    "incomplete_article_schema": {
        "pillar": "schema",
        "priority": "high",
        "title": "Complete Article Schema Properties",
        "description": "Your Article schema is missing required properties (headline, author, datePublished). Incomplete schemas score lower.",
        "action": "Add missing properties: headline (title), author (Person with name), datePublished (ISO date), and optionally image, publisher, dateModified.",
        "impact_estimate": "Could improve your score by ~8 points",
        "category": "schema",
    },
    "incomplete_organization_schema": {
        "pillar": "schema",
        "priority": "high",
        "title": "Complete Organization Schema Properties",
        "description": "Your Organization schema is missing key properties. Add logo, sameAs (social links), description, and contactPoint.",
        "action": 'Fill in: {"name":"...","url":"...","logo":"...","sameAs":["linkedin","twitter"],"description":"...","contactPoint":{"@type":"ContactPoint","telephone":"...","contactType":"customer service"}}',
        "impact_estimate": "Could improve your score by ~8 points",
        "category": "schema",
    },
    "incomplete_faqpage_schema": {
        "pillar": "schema",
        "priority": "high",
        "title": "Complete FAQPage Schema Properties",
        "description": "Your FAQPage schema is missing the mainEntity array with Question/Answer pairs.",
        "action": 'Add mainEntity with Q&A pairs: {"@type":"FAQPage","mainEntity":[{"@type":"Question","name":"How does X work?","acceptedAnswer":{"@type":"Answer","text":"X works by..."}}]}',
        "impact_estimate": "Could improve your score by ~8 points",
        "category": "schema",
    },
    "incomplete_product_schema": {
        "pillar": "schema",
        "priority": "medium",
        "title": "Complete Product Schema Properties",
        "description": "Your Product schema is missing key properties like description, offers, or reviews.",
        "action": "Add description, image, offers (with price/currency), brand, and aggregateRating to your Product schema.",
        "impact_estimate": "Could improve your score by ~5 points",
        "category": "schema",
    },
    "incomplete_blogposting_schema": {
        "pillar": "schema",
        "priority": "high",
        "title": "Complete BlogPosting Schema Properties",
        "description": "Your BlogPosting schema is missing required properties (headline, author, datePublished).",
        "action": "Add headline, author (Person), datePublished, and optionally image, publisher, dateModified.",
        "impact_estimate": "Could improve your score by ~8 points",
        "category": "schema",
    },
    "incomplete_newsarticle_schema": {
        "pillar": "schema",
        "priority": "high",
        "title": "Complete NewsArticle Schema Properties",
        "description": "Your NewsArticle schema is missing required properties.",
        "action": "Add headline, author, datePublished, and publisher to your NewsArticle schema.",
        "impact_estimate": "Could improve your score by ~8 points",
        "category": "schema",
    },
    "incomplete_howto_schema": {
        "pillar": "schema",
        "priority": "medium",
        "title": "Complete HowTo Schema Properties",
        "description": "Your HowTo schema is missing the step property with actual instructions.",
        "action": 'Add step array: {"@type":"HowTo","name":"...","step":[{"@type":"HowToStep","text":"Step 1..."}]}',
        "impact_estimate": "Could improve your score by ~5 points",
        "category": "schema",
    },

    # ── E-E-A-T pillar ────────────────────────────────────────────────────
    "no_author": {
        "pillar": "eeat",
        "priority": "high",
        "title": "Add Author Attribution",
        "description": "No author name found. E-E-A-T signals are critical for AI trust and citation.",
        "action": 'Add visible author name using <span class="author">Author Name</span>, a meta tag <meta name="author" content="...">, or author property in Article JSON-LD.',
        "impact_estimate": "Could improve your score by ~15 points",
        "category": "eeat",
    },
    "no_author_bio": {
        "pillar": "eeat",
        "priority": "medium",
        "title": "Add Author Bio with Credentials",
        "description": "No author bio found. Author credentials and experience significantly boost AI trust.",
        "action": 'Add: <div class="author-bio"><strong>About the Author:</strong> [Name] is a [title] with [X years] experience in [field].</div>',
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "eeat",
    },
    "no_publish_date": {
        "pillar": "eeat",
        "priority": "medium",
        "title": "Add Publish Date",
        "description": "No publish date found. AI models prefer fresh, dated content.",
        "action": 'Add <time datetime="2025-01-15">January 15, 2025</time> and article:published_time meta tag.',
        "impact_estimate": "Could improve your score by ~3 points",
        "category": "eeat",
    },
    "no_updated_date": {
        "pillar": "eeat",
        "priority": "medium",
        "title": "Add Last Updated Date",
        "description": "No update date found. Freshness signals matter for AI content ranking.",
        "action": 'Add article:modified_time meta tag and visible "Last updated: [date]" on the page.',
        "impact_estimate": "Could improve your score by ~2 points",
        "category": "eeat",
    },
    "few_external_citations": {
        "pillar": "eeat",
        "priority": "high",
        "title": "Add External Citations",
        "description": "Fewer than 3 external citations. The Princeton GEO study found citations provide up to 40% visibility boost.",
        "action": "Add 3+ citations linking to authoritative external sources (research papers, industry reports, .gov, .edu domains).",
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "eeat",
    },
    "no_trust_links": {
        "pillar": "eeat",
        "priority": "high",
        "title": "Add Authoritative Source Links",
        "description": "No links to high-trust domains (.gov, .edu, Wikipedia, major publications).",
        "action": "Add links to authoritative sources like .gov, .edu, Wikipedia, Nature, PubMed, or major publications to support claims.",
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "eeat",
    },
    "low_source_diversity": {
        "pillar": "eeat",
        "priority": "medium",
        "title": "Diversify External Sources",
        "description": "External links come from fewer than 3 different domains.",
        "action": "Link to at least 3-5 different authoritative domains to demonstrate research breadth.",
        "impact_estimate": "Could improve your score by ~5 points",
        "category": "eeat",
    },
    "no_about_page": {
        "pillar": "eeat",
        "priority": "high",
        "title": "Add About Page Link",
        "description": "No link to an About page found. Transparency about who runs the site is a core trust signal.",
        "action": "Add an About page explaining your organization, team, mission, and qualifications. Link it from navigation or footer.",
        "impact_estimate": "Could improve your score by ~3 points",
        "category": "eeat",
    },
    "no_first_hand_experience": {
        "pillar": "eeat",
        "priority": "high",
        "title": "Add First-Hand Experience Signals",
        "description": "Your content lacks first-hand experience indicators. The first 'E' in E-E-A-T stands for Experience.",
        "action": "Add personal experience: 'In our testing...', 'We found that...', 'Based on our experience...'. Include case studies, original data, screenshots, or hands-on reviews.",
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "eeat",
    },
    "no_expertise_indicators": {
        "pillar": "eeat",
        "priority": "medium",
        "title": "Demonstrate Deeper Expertise",
        "description": "Content lacks depth signals that show genuine expertise.",
        "action": "Add expert-level details: explain WHY things work, include pro tips, address common mistakes, use specific examples and data points.",
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "eeat",
    },
    "low_authority": {
        "pillar": "eeat",
        "priority": "high",
        "title": "Build Content Authority",
        "description": "Your content doesn't demonstrate strong authoritativeness in its topic area.",
        "action": "Cite authoritative sources, reference industry standards, include data/statistics, mention partnerships or recognitions.",
        "impact_estimate": "Could improve your score by ~15 points",
        "category": "eeat",
    },
    "low_trust_signals": {
        "pillar": "eeat",
        "priority": "high",
        "title": "Improve Trustworthiness Signals",
        "description": "Your content lacks trust indicators that AI models look for before citing a source.",
        "action": "Add: editorial/fact-check policy, disclosure statements, contact info, clear sourcing for claims, corrections policy.",
        "impact_estimate": "Could improve your score by ~15 points",
        "category": "eeat",
    },

    # ── Technical pillar ──────────────────────────────────────────────────
    "no_llms_txt": {
        "pillar": "technical",
        "priority": "high",
        "title": "Create llms.txt File",
        "description": "No llms.txt found. This emerging standard tells AI models what your site is about.",
        "action": "Create llms.txt at your domain root. Include: site name, description, key pages, and contact info.",
        "impact_estimate": "Could improve your score by ~20 points",
        "category": "technical",
    },
    "ai_bots_blocked": {
        "pillar": "technical",
        "priority": "critical",
        "title": "Unblock AI Crawlers in robots.txt",
        "description": "Your robots.txt blocks AI crawlers. This prevents AI models from indexing your content.",
        "action": "Update robots.txt to allow AI bots:\nUser-agent: GPTBot\nAllow: /\nUser-agent: Google-Extended\nAllow: /\nUser-agent: anthropic-ai\nAllow: /",
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
        "description": "No canonical URL tag found. Helps prevent duplicate content issues.",
        "action": 'Add <link rel="canonical" href="https://yoursite.com/page-url"> to your <head>.',
        "impact_estimate": "Could improve your score by ~10 points",
        "category": "technical",
    },

    # ── Entity pillar ─────────────────────────────────────────────────────
    "brand_not_in_ai": {
        "pillar": "entity",
        "priority": "high",
        "title": "Improve AI Brand Visibility",
        "description": "Your brand doesn't appear in AI responses for your category.",
        "action": "Get mentioned in third-party publications, review sites, and industry directories to build brand authority.",
        "impact_estimate": "Could improve your score by ~20 points",
        "category": "entity",
    },
    "no_social_profiles": {
        "pillar": "entity",
        "priority": "low",
        "title": "Link Social Media Profiles",
        "description": "No social media profile links found on your page.",
        "action": "Link social profiles (LinkedIn, Twitter/X, Facebook) from your page footer to strengthen brand entity signals.",
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

    # ── Crawl failure findings ────────────────────────────────────────────
    "crawl_blocked_403": {
        "pillar": "technical",
        "priority": "critical",
        "title": "Your Site Blocks Automated Access (HTTP 403)",
        "description": "Your server returned a 403 Forbidden error, which means it blocks automated requests. If your site blocks our crawler, it likely blocks AI crawlers (GPTBot, ClaudeBot, PerplexityBot) too — meaning AI search engines cannot index your content.",
        "action": "Check your server configuration, CDN (Cloudflare, AWS WAF), or hosting provider settings. Ensure legitimate bots are allowed. Add specific allow rules for AI crawlers in your firewall/WAF settings.",
        "impact_estimate": "Critical — AI engines cannot see your content at all",
        "category": "technical",
    },
    "crawl_timeout": {
        "pillar": "technical",
        "priority": "critical",
        "title": "Your Site Is Too Slow to Crawl",
        "description": "Your page took too long to respond (>15 seconds). AI crawlers have strict timeouts — if your site is this slow, AI search engines will skip it entirely.",
        "action": "Investigate server performance: check hosting plan, enable caching, optimize database queries, use a CDN. Aim for <3 second response time.",
        "impact_estimate": "Critical — slow sites get skipped by AI crawlers",
        "category": "technical",
    },
}

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# Numeric impact scores for smart ranking (higher = more impactful)
# Based on Princeton GEO research effectiveness data + pillar weight
IMPACT_SCORES = {
    # Content — Princeton research ranked methods
    "no_citations": 95,         # +40% visibility — highest impact
    "no_statistics": 90,        # +37% visibility
    "keyword_stuffing": 88,     # -10% penalty — actively hurts
    "no_expert_quotes": 75,     # +30% visibility
    "weak_authoritative_tone": 70,  # +25% visibility
    "poor_readability": 60,     # +20% visibility
    "no_technical_terms": 50,   # +18% visibility
    "low_vocabulary_diversity": 45,  # +15% visibility
    "no_faq_section": 72,       # FAQ + schema = +40% AI visibility
    "no_answer_first": 65,      # Direct answers get cited more
    "low_word_count": 55,       # Thin content rarely cited
    "no_h1": 40,
    "multiple_h1": 20,
    "broken_heading_hierarchy": 25,
    "no_lists": 15,
    "poor_paragraph_structure": 15,
    "few_internal_links": 15,
    # Schema
    "no_jsonld": 85,            # No schema at all — critical
    "no_faqpage_schema": 70,    # +40% AI visibility per research
    "no_article_schema": 55,
    "no_organization_schema": 55,
    "invalid_jsonld_structure": 40,
    "incomplete_article_schema": 30,
    "incomplete_organization_schema": 30,
    "incomplete_faqpage_schema": 30,
    "incomplete_product_schema": 20,
    "incomplete_blogposting_schema": 25,
    "incomplete_newsarticle_schema": 25,
    "incomplete_howto_schema": 20,
    # E-E-A-T
    "no_citations_eeat": 80,    # Overlaps with content citations
    "few_external_citations": 75,
    "no_trust_links": 70,
    "no_first_hand_experience": 68,
    "low_authority": 65,
    "low_trust_signals": 65,
    "no_about_page": 50,
    "no_author": 60,
    "no_author_bio": 40,
    "no_expertise_indicators": 45,
    "low_source_diversity": 35,
    "no_publish_date": 20,
    "no_updated_date": 15,
    # Technical
    "ai_bots_blocked": 92,      # Blocking AI = zero visibility
    "meta_noindex": 90,         # Blocking indexing = zero visibility
    "no_llms_txt": 60,
    "no_https": 55,
    "slow_load_time": 45,
    "no_sitemap": 35,
    "no_viewport": 20,
    "no_canonical": 20,
    # Entity
    "brand_not_in_ai": 65,
    "no_wikipedia_presence": 50,
    "no_social_profiles": 15,
    # Crawl failures
    "crawl_blocked_403": 98,    # Can't be indexed at all
    "crawl_timeout": 96,        # Too slow for any crawler
}

MAX_RECOMMENDATIONS = 10


def generate_recommendations(pillar_details: dict[str, dict]) -> list[dict]:
    """
    Generate top 5-7 highest-impact recommendations.

    Uses numeric impact scores based on Princeton GEO research effectiveness
    data to rank and select only the most impactful improvements.
    """
    candidates = []

    for _pillar_name, details in pillar_details.items():
        findings = details.get("findings", [])
        for finding in findings:
            rule = RECOMMENDATION_RULES.get(finding)
            if rule:
                rec = dict(rule)
                rec["impact_score"] = IMPACT_SCORES.get(finding, 10)
                candidates.append(rec)

    # Sort by impact score (highest first), then by priority as tiebreaker
    candidates.sort(
        key=lambda r: (-r["impact_score"], PRIORITY_ORDER.get(r["priority"], 99))
    )

    # Take top N recommendations
    top = candidates[:MAX_RECOMMENDATIONS]

    # Remove internal impact_score before returning
    for rec in top:
        rec.pop("impact_score", None)

    return top
