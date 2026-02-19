import logging
import threading

from .models import (
    AIVisibilityProbe,
    AnalysisRun,
    Competitor,
    PageScore,
    Recommendation,
)
from .pipeline.aggregator import compute_composite, detect_industry
from .pipeline.ai_visibility import score_ai_visibility
from .pipeline.competitors import discover_competitors, score_competitor
from .pipeline.content import score_content
from .pipeline.crawler import crawl_page
from .pipeline.eeat import score_eeat
from .pipeline.entity import score_entity
from .pipeline.llm import start_log_collection, get_collected_logs
from .pipeline.recommendations import generate_recommendations
from .pipeline.schema import score_schema
from .pipeline.technical import score_technical

logger = logging.getLogger("apps")


def _update_status(run: AnalysisRun, status: str, progress: int = 0):
    run.status = status
    run.progress = progress
    run.save(update_fields=["status", "progress", "updated_at"])


def _run_partial_analysis(run: AnalysisRun, crawl):
    """
    Run partial analysis when crawler fails to get HTML.
    Still checks: robots.txt, sitemap, llms.txt, HTTPS, load time.
    Also runs entity + AI visibility via Gemini (don't need HTML).
    """
    logger.info("Run %d: crawl failed (%s), running partial analysis", run.id, crawl.error)
    start_log_collection()

    _update_status(run, AnalysisRun.Status.ANALYZING, 20)

    # Content, schema, eeat all need HTML — score 0 with explanation
    content_score, content_details = 0.0, {
        "checks": {"crawl_failed": True},
        "findings": [],
        "note": f"Page content could not be accessed: {crawl.error}",
    }
    schema_score_val, schema_details = 0.0, {
        "checks": {"crawl_failed": True},
        "findings": [],
        "note": f"Schema markup could not be checked: {crawl.error}",
    }
    eeat_score_val, eeat_details = 0.0, {
        "checks": {"crawl_failed": True},
        "findings": [],
        "note": f"E-E-A-T signals could not be analyzed: {crawl.error}",
    }

    _update_status(run, AnalysisRun.Status.ANALYZING, 40)

    # Technical — works without HTML (robots.txt, sitemap, llms.txt, HTTPS)
    technical_score_val, technical_details = score_technical(crawl)
    _update_status(run, AnalysisRun.Status.ANALYZING, 55)

    # Entity — uses Gemini, can work with just URL + brand name
    entity_score_val, entity_details = 0.0, {}
    try:
        entity_score_val, entity_details = score_entity(crawl)
        _update_status(run, AnalysisRun.Status.ANALYZING, 70)
    except Exception as exc:
        logger.warning("Entity scoring failed for run %d: %s", run.id, exc)
        entity_details = {"error": str(exc)}

    # AI visibility — uses Gemini, can work with just URL
    ai_vis_score, ai_vis_details, probes_data = 0.0, {}, []
    try:
        ai_vis_score, ai_vis_details, probes_data = score_ai_visibility(crawl)
        _update_status(run, AnalysisRun.Status.ANALYZING, 80)
    except Exception as exc:
        logger.warning("AI visibility failed for run %d: %s", run.id, exc)
        ai_vis_details = {"error": str(exc)}

    for probe in probes_data:
        AIVisibilityProbe.objects.create(analysis_run=run, **probe)

    _update_status(run, AnalysisRun.Status.SCORING, 85)

    # Composite — some pillars will be 0 but that's accurate
    composite = compute_composite(
        content_score, schema_score_val, eeat_score_val,
        technical_score_val, entity_score_val, ai_vis_score,
    )

    PageScore.objects.create(
        analysis_run=run,
        url=run.url,
        content_score=content_score,
        content_details=content_details,
        schema_score=schema_score_val,
        schema_details=schema_details,
        eeat_score=eeat_score_val,
        eeat_details=eeat_details,
        technical_score=technical_score_val,
        technical_details=technical_details,
        entity_score=entity_score_val,
        entity_details=entity_details,
        ai_visibility_score=ai_vis_score,
        ai_visibility_details=ai_vis_details,
        composite_score=composite,
    )

    # Recommendations — technical findings + crawl-failed finding
    pillar_details = {
        "content": content_details,
        "schema": schema_details,
        "eeat": eeat_details,
        "technical": technical_details,
        "entity": entity_details,
        "ai_visibility": ai_vis_details,
    }
    # Add a special finding about the crawl failure
    technical_details.setdefault("findings", [])
    if crawl.status_code == 403:
        technical_details["findings"].append("crawl_blocked_403")
    elif "timed out" in crawl.error.lower():
        technical_details["findings"].append("crawl_timeout")

    recs = generate_recommendations(pillar_details)
    for rec in recs:
        Recommendation.objects.create(analysis_run=run, **rec)

    # Finalize as complete (partial), not failed
    run.composite_score = composite
    run.status = AnalysisRun.Status.COMPLETE
    run.progress = 100
    run.error_message = f"Partial results: {crawl.error}. Content, schema, and E-E-A-T could not be analyzed."
    run.llm_logs = get_collected_logs()
    run.save()
    logger.info("Partial analysis complete for run %d: score %.1f", run.id, composite)


def run_single_page_analysis(run_id: int):
    """Full analysis pipeline for a single page."""
    try:
        run = AnalysisRun.objects.get(pk=run_id)
    except AnalysisRun.DoesNotExist:
        logger.error("AnalysisRun %d not found", run_id)
        return

    try:
        start_log_collection()

        # Phase 1: Crawl
        _update_status(run, AnalysisRun.Status.CRAWLING, 5)
        crawl = crawl_page(run.url)

        if not crawl.ok:
            # Don't fail — run partial analysis instead
            _run_partial_analysis(run, crawl)
            return

        _update_status(run, AnalysisRun.Status.ANALYZING, 15)

        # Detect industry for adaptive weights
        industry = detect_industry(crawl.soup, crawl.text)
        logger.info("Run %d: detected industry = %s", run_id, industry)

        # Phase 2: Static pillars
        content_score, content_details = score_content(crawl)
        _update_status(run, AnalysisRun.Status.ANALYZING, 25)

        schema_score_val, schema_details = score_schema(crawl)
        _update_status(run, AnalysisRun.Status.ANALYZING, 35)

        eeat_score_val, eeat_details = score_eeat(crawl)
        _update_status(run, AnalysisRun.Status.ANALYZING, 45)

        technical_score_val, technical_details = score_technical(crawl)
        _update_status(run, AnalysisRun.Status.ANALYZING, 55)

        # Phase 3: Gemini pillars
        entity_score_val, entity_details = 0.0, {}
        ai_vis_score, ai_vis_details, probes_data = 0.0, {}, []

        try:
            entity_score_val, entity_details = score_entity(crawl)
            _update_status(run, AnalysisRun.Status.ANALYZING, 65)
        except Exception as exc:
            logger.warning("Entity scoring failed for run %d: %s", run_id, exc)
            entity_details = {"error": str(exc)}

        try:
            ai_vis_score, ai_vis_details, probes_data = score_ai_visibility(crawl)
            _update_status(run, AnalysisRun.Status.ANALYZING, 75)
        except Exception as exc:
            logger.warning("AI visibility failed for run %d: %s", run_id, exc)
            ai_vis_details = {"error": str(exc)}

        # Save AI probes
        for probe in probes_data:
            AIVisibilityProbe.objects.create(analysis_run=run, **probe)

        # Phase 4: Scoring
        _update_status(run, AnalysisRun.Status.SCORING, 80)

        composite = compute_composite(
            content_score, schema_score_val, eeat_score_val,
            technical_score_val, entity_score_val, ai_vis_score,
            industry=industry,
        )

        PageScore.objects.create(
            analysis_run=run,
            url=run.url,
            content_score=content_score,
            content_details=content_details,
            schema_score=schema_score_val,
            schema_details=schema_details,
            eeat_score=eeat_score_val,
            eeat_details=eeat_details,
            technical_score=technical_score_val,
            technical_details=technical_details,
            entity_score=entity_score_val,
            entity_details=entity_details,
            ai_visibility_score=ai_vis_score,
            ai_visibility_details=ai_vis_details,
            composite_score=composite,
        )

        # Phase 5: Recommendations
        pillar_details = {
            "content": content_details,
            "schema": schema_details,
            "eeat": eeat_details,
            "technical": technical_details,
            "entity": entity_details,
            "ai_visibility": ai_vis_details,
        }
        recs = generate_recommendations(pillar_details)
        for rec in recs:
            Recommendation.objects.create(analysis_run=run, **rec)

        # Phase 6: Competitor discovery & scoring
        _update_status(run, AnalysisRun.Status.SCORING, 85)
        try:
            competitor_list = discover_competitors(crawl)
            for comp_data in competitor_list:
                comp = Competitor.objects.create(
                    analysis_run=run,
                    name=comp_data["name"],
                    url=comp_data["url"],
                    industry=comp_data.get("industry", ""),
                )
                try:
                    page_data, comp_composite = score_competitor(comp_data["url"])
                    if page_data:
                        comp_page = PageScore.objects.create(
                            analysis_run=run, **page_data
                        )
                        comp.page_score = comp_page
                        comp.composite_score = comp_composite
                        comp.scored = True
                        comp.save()
                except Exception as exc:
                    logger.warning("Competitor scoring failed for %s: %s", comp_data["url"], exc)
        except Exception as exc:
            logger.warning("Competitor discovery failed for run %d: %s", run_id, exc)

        # Finalize
        run.composite_score = composite
        run.status = AnalysisRun.Status.COMPLETE
        run.progress = 100
        run.llm_logs = get_collected_logs()
        run.save()
        logger.info("Analysis complete for run %d: score %.1f", run_id, composite)

    except Exception as exc:
        logger.error("Analysis failed for run %d: %s", run_id, exc, exc_info=True)
        run.status = AnalysisRun.Status.FAILED
        run.error_message = str(exc)
        run.save()


def start_analysis_task(run_id: int):
    """Start the analysis in a background thread."""
    try:
        run = AnalysisRun.objects.get(pk=run_id)
    except AnalysisRun.DoesNotExist:
        return

    thread = threading.Thread(target=run_single_page_analysis, args=(run_id,), daemon=True)
    thread.start()
