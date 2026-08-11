"""RabbitMQ-backed Celery task for the full analyze / re-analyze pipeline.

Lives in ``analysis_tasks`` (not ``celery_tasks``) so it is autodiscovered by
the RabbitMQ app (``config.celery_rabbit:analysis_app``) and NOT by the Redis
app — keeping analysis on RabbitMQ and the sitemap audit on Redis.

Bound with ``@analysis_app.task`` (not ``@shared_task``, which would also
register it on the Redis app). On failure the run is marked FAILED and the task
returns WITHOUT re-raising, so Celery does not retry — re-running a partial,
non-idempotent analysis would re-spend LLM / DataForSEO credits.
"""

from __future__ import annotations

import logging

from config.celery_rabbit import analysis_app

logger = logging.getLogger("apps")


@analysis_app.task(name="analyzer.run_scheduled_analysis", bind=True)
def run_scheduled_analysis_task(self, schedule_id: int) -> None:
    """Run one due ScheduledAnalysis on a worker.

    The whole job moves here, not just the analysis call: ``run_analysis_task``
    below is deliberately fire-and-forget with no completion hook, so enqueueing
    only the analysis would leave the task sync + digest running against a run
    that hasn't started. Keeping the sequence intact on the worker needs no hook.

    Like its sibling, this never re-raises — the analysis pipeline is not
    idempotent, and a Celery retry would re-spend LLM / DataForSEO credits. The
    schedule is already rescheduled by the claim, so a failure costs one cycle
    rather than wedging the brand.
    """
    from django.db import close_old_connections

    from apps.analyzer.scheduled_runs import execute_scheduled_analysis

    close_old_connections()
    try:
        execute_scheduled_analysis(schedule_id)
    except Exception as exc:
        logger.exception("scheduled analysis %d failed on worker: %s", schedule_id, exc)


@analysis_app.task(name="analyzer.run_analysis", bind=True)
def run_analysis_task(self, run_id: int) -> None:
    """Run the single-page analysis pipeline for ``run_id`` on a worker."""
    from django.db import close_old_connections

    from apps.analyzer.models import AnalysisRun
    from apps.analyzer.tasks import run_single_page_analysis


    close_old_connections()
    try:
        run_single_page_analysis(run_id)
    except Exception as exc:
        logger.exception("analysis run %d failed on worker: %s", run_id, exc)
        # Backstop: the pipeline marks FAILED in its own except blocks, but if a
        # crash escapes it, make sure the FE doesn't see a permanently-stuck run.
        try:
            AnalysisRun.objects.filter(pk=run_id).update(
                status=AnalysisRun.Status.FAILED,
                error_message=str(exc)[:500],
            )
        except Exception:
            logger.exception("analysis run %d: also failed to mark row as FAILED", run_id)
        # No re-raise → no Celery retry.


@analysis_app.task(name="analyzer.backfill_prompt_volume", bind=True)
def backfill_prompt_volume_task(self, run_id: int) -> None:
    """Fill in DataForSEO search volume for a run's tracked prompts.

    Unlike its siblings this one IS idempotent — the service re-checks a TTL
    before spending anything — but it still swallows its exception, because a
    missing Volume column must never mark an otherwise good analysis as failed.
    """
    from django.db import close_old_connections

    from apps.analyzer.services.prompt_volume import backfill_run_volumes

    close_old_connections()
    try:
        backfill_run_volumes(run_id)
    except Exception as exc:
        logger.warning("prompt volume backfill failed for run %d: %s", run_id, exc)


@analysis_app.task(name="analyzer.run_outreach_benchmark", bind=True)
def run_outreach_benchmark_task(self, run_id: int) -> None:
    """Build the sales outreach benchmark for ``run_id`` on a worker.

    Same no-re-raise contract as its siblings: the benchmark spends real LLM
    credits and is not idempotent, so a Celery retry would pay twice for the
    same report.
    """
    from django.db import close_old_connections

    from apps.analyzer.models import AnalysisRun
    from apps.analyzer.services.outreach_benchmark import run_outreach_benchmark

    close_old_connections()
    try:
        run_outreach_benchmark(run_id)
    except Exception as exc:
        logger.exception("outreach benchmark %d failed on worker: %s", run_id, exc)
        try:
            AnalysisRun.objects.filter(pk=run_id).update(
                status=AnalysisRun.Status.FAILED,
                error_message=str(exc)[:500],
            )
        except Exception:
            logger.exception("outreach benchmark %d: also failed to mark row as FAILED", run_id)
