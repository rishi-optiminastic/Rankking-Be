"""
Search demand for tracked prompts, sourced from DataForSEO Google Ads.

Powers the Volume column on the prompt tracker: roughly how many people ask
Google this each month, which is what separates a prompt worth winning from one
nobody runs.

Three cost controls, because this endpoint bills per task and prompts repeat
heavily across brands:

1. Terms Google Ads would reject (over 80 chars / 10 words) never leave the
   process. Many conversational prompts fall here.
2. A term already priced for any other run inside ``VOLUME_TTL`` is copied
   rather than re-fetched.
3. Whatever remains goes out in one batched call per 1000 terms.

Every prompt considered gets ``search_volume_checked_at`` stamped, including the
ineligible ones, so a prompt is never re-attempted on each run.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from apps.analyzer.models import PromptTrack
from apps.integrations.services.dataforseo import (
    DataForSEOError,
    DataForSEONotConfigured,
    fetch_search_volume,
    is_volume_eligible,
)

logger = logging.getLogger("apps")

# Google reports a rolling 12-month average, so it barely moves week to week.
VOLUME_TTL = timedelta(days=30)


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _pending(run_id: int) -> list[PromptTrack]:
    """Prompts on this run whose volume is missing or stale."""
    cutoff = timezone.now() - VOLUME_TTL
    return list(
        PromptTrack.objects.filter(analysis_run_id=run_id, deleted_at__isnull=True)
        .exclude(search_volume_checked_at__gte=cutoff)
        .only("id", "prompt_text", "search_volume", "search_volume_checked_at")
    )


def _known_volumes(terms: set[str]) -> dict[str, int]:
    """Volumes already paid for on another run and still inside the TTL."""
    if not terms:
        return {}
    cutoff = timezone.now() - VOLUME_TTL
    rows = (
        PromptTrack.objects.filter(
            search_volume__isnull=False,
            search_volume_checked_at__gte=cutoff,
        )
        .values_list("prompt_text", "search_volume")
        .iterator()
    )
    # Filtering in Python rather than with a case-insensitive IN: the term set is
    # small and bounded by one run's prompts, while a large __in of long TextField
    # values makes for an ugly query plan.
    found: dict[str, int] = {}
    for text, volume in rows:
        term = _normalize(text)
        if term in terms and term not in found:
            found[term] = volume
    return found


def _resolve(terms: set[str]) -> tuple[dict[str, int], bool]:
    """
    Volume per term, reusing cached figures and fetching only the rest.

    Returns ``(volumes, measured)``. ``measured`` is False when the lookup could
    not be performed at all — the caller must not read a missing term as zero
    demand in that case, because it is an outage rather than an answer.
    """
    cached = _known_volumes(terms)
    missing = {t for t in terms if t not in cached and is_volume_eligible(t)}
    if not missing:
        return cached, True

    try:
        fetched = fetch_search_volume(missing)
    except DataForSEONotConfigured:
        logger.info("prompt volume: DataForSEO credentials not set, skipping lookup")
        return cached, False
    except DataForSEOError as exc:
        # Enrichment, not core analysis. A billing or upstream failure leaves the
        # column empty instead of failing the run that owns these prompts.
        logger.warning("prompt volume: DataForSEO lookup failed: %s", exc)
        return cached, False

    return {**cached, **fetched}, True


def backfill_run_volumes(run_id: int) -> int:
    """
    Fill in search volume for a run's tracked prompts. Returns rows updated.

    Safe to call repeatedly: the TTL check means a second call inside the window
    is a no-op that costs nothing.
    """
    pending = _pending(run_id)
    if not pending:
        return 0

    volumes, measured = _resolve({_normalize(p.prompt_text) for p in pending})
    now = timezone.now()
    updated: list[PromptTrack] = []
    for prompt in pending:
        term = _normalize(prompt.prompt_text)
        if term in volumes:
            prompt.search_volume = volumes[term]
        elif not is_volume_eligible(term):
            # Google Ads would refuse the term, so there is nothing to wait for.
            # Stamped as checked to stop it being reconsidered on every run.
            prompt.search_volume = None
        elif measured:
            # Asked, and Google reported nothing back: genuine zero demand.
            prompt.search_volume = 0
        else:
            # The lookup itself failed. Leave the row alone so the next run
            # retries it — writing 0 here would record an outage as a finding.
            continue
        prompt.search_volume_checked_at = now
        updated.append(prompt)

    if not updated:
        return 0
    PromptTrack.objects.bulk_update(updated, ["search_volume", "search_volume_checked_at"], batch_size=200)
    logger.info("prompt volume: updated %d prompt(s) for run %d", len(updated), run_id)
    return len(updated)
