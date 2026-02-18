import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import (
    AIVisibilityProbe,
    AnalysisRun,
    Competitor,
    PageScore,
    Recommendation,
)
from .pipeline.aggregator import compute_composite
from .pipeline.ai_visibility import score_ai_visibility
from .pipeline.competitors import discover_competitors, score_competitor
from .pipeline.content import score_content
from .pipeline.crawler import crawl_page
from .pipeline.eeat import score_eeat
from .pipeline.entity import score_entity
from .pipeline.recommendations import generate_recommendations
from .pipeline.schema import score_schema
from .pipeline.technical import score_technical

logger = logging.getLogger("apps")


def _update_status(run: AnalysisRun, status: str, progress: int = 0):
    run.status = status
    run.progress = progress
    run.save(update_fields=["status", "progress", "updated_at"])


def run_single_page_analysis(run_id: int):
    """Full analysis pipeline for a single page."""
    try:
        run = AnalysisRun.objects.get(pk=run_id)
    except AnalysisRun.DoesNotExist:
        logger.error("AnalysisRun %d not found", run_id)
        return

    try:
        # Phase 1: Crawl
        _update_status(run, AnalysisRun.Status.CRAWLING, 5)
        crawl = crawl_page(run.url)
        if not crawl.ok:
            run.status = AnalysisRun.Status.FAILED
            run.error_message = f"Crawl failed: {crawl.error}"
            run.save()
            return

        _update_status(run, AnalysisRun.Status.ANALYZING, 15)

        # Phase 2: Static pillars (parallel)
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
        )

        page_score = PageScore.objects.create(
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
                # Score competitor
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
        run.save()
        logger.info("Analysis complete for run %d: score %.1f", run_id, composite)

    except Exception as exc:
        logger.error("Analysis failed for run %d: %s", run_id, exc, exc_info=True)
        run.status = AnalysisRun.Status.FAILED
        run.error_message = str(exc)
        run.save()


def run_full_site_analysis(run_id: int):
    """Full site audit — crawl up to 20 pages and analyze each."""
    try:
        run = AnalysisRun.objects.get(pk=run_id)
    except AnalysisRun.DoesNotExist:
        return

    try:
        _update_status(run, AnalysisRun.Status.CRAWLING, 5)

        # Crawl main page first
        main_crawl = crawl_page(run.url)
        if not main_crawl.ok:
            run.status = AnalysisRun.Status.FAILED
            run.error_message = f"Crawl failed: {main_crawl.error}"
            run.save()
            return

        # Collect internal links (cap at 20)
        pages_to_crawl = [run.url]
        for link in main_crawl.internal_links[:19]:
            if link not in pages_to_crawl:
                pages_to_crawl.append(link)
            if len(pages_to_crawl) >= 20:
                break

        _update_status(run, AnalysisRun.Status.ANALYZING, 15)

        all_composites = []

        # Process pages with ThreadPoolExecutor
        def analyze_page(url):
            crawl = crawl_page(url)
            if not crawl.ok:
                return None

            cs, cd = score_content(crawl)
            ss, sd = score_schema(crawl)
            es, ed = score_eeat(crawl)
            ts, td = score_technical(crawl)

            # Skip Gemini for sub-pages to save API calls
            composite = compute_composite(cs, ss, es, ts, 0, 0)

            return {
                "url": url,
                "content_score": cs, "content_details": cd,
                "schema_score": ss, "schema_details": sd,
                "eeat_score": es, "eeat_details": ed,
                "technical_score": ts, "technical_details": td,
                "entity_score": 0, "entity_details": {},
                "ai_visibility_score": 0, "ai_visibility_details": {},
                "composite_score": composite,
            }

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(analyze_page, url): url for url in pages_to_crawl}
            completed = 0
            for future in as_completed(futures):
                completed += 1
                progress = 15 + int(completed / len(pages_to_crawl) * 60)
                _update_status(run, AnalysisRun.Status.ANALYZING, progress)

                result = future.result()
                if result:
                    PageScore.objects.create(analysis_run=run, **result)
                    all_composites.append(result["composite_score"])

        # Run Gemini on main page only
        _update_status(run, AnalysisRun.Status.SCORING, 80)
        try:
            entity_score_val, entity_details = score_entity(main_crawl)
            ai_vis_score, ai_vis_details, probes_data = score_ai_visibility(main_crawl)

            for probe in probes_data:
                AIVisibilityProbe.objects.create(analysis_run=run, **probe)

            # Update main page score with Gemini results
            main_page = run.page_scores.filter(url=run.url).first()
            if main_page:
                main_page.entity_score = entity_score_val
                main_page.entity_details = entity_details
                main_page.ai_visibility_score = ai_vis_score
                main_page.ai_visibility_details = ai_vis_details
                main_page.composite_score = compute_composite(
                    main_page.content_score, main_page.schema_score,
                    main_page.eeat_score, main_page.technical_score,
                    entity_score_val, ai_vis_score,
                )
                main_page.save()
        except Exception as exc:
            logger.warning("Gemini analysis failed for run %d: %s", run_id, exc)

        # Generate recommendations from main page
        main_page = run.page_scores.filter(url=run.url).first()
        if main_page:
            pillar_details = {
                "content": main_page.content_details,
                "schema": main_page.schema_details,
                "eeat": main_page.eeat_details,
                "technical": main_page.technical_details,
                "entity": main_page.entity_details,
                "ai_visibility": main_page.ai_visibility_details,
            }
            recs = generate_recommendations(pillar_details)
            for rec in recs:
                Recommendation.objects.create(analysis_run=run, **rec)

        # Competitor discovery
        try:
            competitor_list = discover_competitors(main_crawl)
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
                        comp_page = PageScore.objects.create(analysis_run=run, **page_data)
                        comp.page_score = comp_page
                        comp.composite_score = comp_composite
                        comp.scored = True
                        comp.save()
                except Exception:
                    pass
        except Exception:
            pass

        # Compute site-level composite
        site_composite = (
            sum(all_composites) / len(all_composites) if all_composites else 0.0
        )
        run.composite_score = site_composite
        run.status = AnalysisRun.Status.COMPLETE
        run.progress = 100
        run.save()

    except Exception as exc:
        logger.error("Full site analysis failed for run %d: %s", run_id, exc, exc_info=True)
        run.status = AnalysisRun.Status.FAILED
        run.error_message = str(exc)
        run.save()


def start_analysis_task(run_id: int):
    """Start the appropriate analysis in a background thread."""
    try:
        run = AnalysisRun.objects.get(pk=run_id)
    except AnalysisRun.DoesNotExist:
        return

    if run.run_type == AnalysisRun.RunType.FULL_SITE:
        target = run_full_site_analysis
    else:
        target = run_single_page_analysis

    thread = threading.Thread(target=target, args=(run_id,), daemon=True)
    thread.start()
