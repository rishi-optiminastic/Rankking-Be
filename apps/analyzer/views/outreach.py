"""Public endpoints for the sales outreach benchmark.

Deliberately outside the dashboard and behind no login: the people using this
are doing outbound, not managing an account, and a sign-in wall would make it
useless for them.

"No login" is not "no gate", though. Generating a benchmark spends real LLM
credits on every call, so an unauthenticated endpoint that anyone can find is
an invitation to burn the OpenRouter budget. Access is a single shared key held
in ``OUTREACH_BENCHMARK_KEY``: the founder pastes it once, nobody manages
accounts, and a crawler that stumbles onto the URL gets a 403. Reads are open,
so a finished report can be shared by link with a prospect.

Leaving the key unset disables creation entirely, which is the right default
for any environment that has not deliberately turned this on.
"""

from __future__ import annotations

import hmac
import logging
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions.throttling import ExpensiveThrottle, PollingThrottle

from ..models import AnalysisRun
from ..url_guard import SSRFValidationError, validate_public_url

logger = logging.getLogger("apps")

_KEY_HEADER = "X-Outreach-Key"


def _public_url(raw: str) -> tuple[str, str]:
    """(url, "") for a usable public address, else ("", reason).

    A founder pastes "acme.com", not a scheme, so the scheme is added the same
    way the analyze serializer does it. The SSRF check is the important half:
    this endpoint takes an arbitrary URL from the internet and then fetches it
    server-side, which is exactly the shape that reaches internal addresses and
    cloud metadata endpoints if left unguarded.
    """
    url = raw.strip()
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    try:
        return validate_public_url(url), ""
    except SSRFValidationError:
        return "", "That URL can't be analyzed — enter a public website address."


def _configured_key() -> str:
    return (getattr(settings, "OUTREACH_BENCHMARK_KEY", "") or "").strip()


def _key_ok(request) -> bool:
    """Constant-time comparison so the key can't be recovered by timing."""
    expected = _configured_key()
    if not expected:
        return False
    supplied = (request.headers.get(_KEY_HEADER) or "").strip()
    return bool(supplied) and hmac.compare_digest(supplied, expected)


def _reuse_window() -> timedelta:
    """How long a finished benchmark stands in for an identical new one.

    Zero (or negative) disables reuse entirely, which is the escape hatch if a
    demo ever needs every click to generate afresh.
    """
    return timedelta(hours=float(getattr(settings, "OUTREACH_REUSE_HOURS", 24) or 0))


def _host(url: str) -> str:
    """Comparison key for "same company". The benchmark only ever crawls the
    homepage (OUTREACH_MAX_PAGES = 1) and fires domain-level buyer prompts, so
    two URLs with the same host produce the same report by construction."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _reusable_benchmark(url: str) -> AnalysisRun | None:
    """The most recent finished benchmark for this domain inside the window.

    Every generated benchmark costs ~18 search-enabled answer-engine calls, and
    this endpoint is hand-driven: the same person re-running the same domain
    several times in a morning was paying full price for a report that cannot
    have changed. What answer engines say about a company moves over days, not
    minutes, so serving the stored report back is the same answer for free.

    Deliberately matched in Python rather than with a LIKE on the URL: hosts need
    normalising (scheme, www, trailing slash) and the window is small. Streamed
    with ``iterator`` rather than sliced to a fixed count — a slice would have
    silently stopped reusing anything once the window held more runs than the
    limit, with no signal that it had stopped working.
    """
    window = _reuse_window()
    if window <= timedelta(0):
        return None
    host = _host(url)
    if not host:
        return None
    recent = AnalysisRun.objects.filter(
        run_type=AnalysisRun.RunType.OUTREACH,
        status=AnalysisRun.Status.COMPLETE,
        created_at__gte=timezone.now() - window,
        # A run built from caller-pinned prompts answers a narrower question
        # than "what do buyers ask about this domain". Serving it to a request
        # that pinned nothing would hand back a report measuring a question the
        # caller never asked. The reverse case (this request pins prompts) is
        # refused by the caller.
        onboarding_prompts=[],
    ).order_by("-created_at")
    for run in recent.iterator(chunk_size=200):
        # An empty report is a "complete" run that produced nothing usable
        # (the credit-exhaustion case); reusing it would cache a bad answer.
        if run.outreach_report and _host(run.url) == host:
            return run
    return None


def _serialize(run: AnalysisRun) -> dict:
    return {
        "slug": run.slug,
        "url": run.url,
        "brand_name": run.brand_name,
        "status": run.status,
        "progress": run.progress,
        "phase": run.phase,
        "error_message": run.error_message,
        "report": run.outreach_report or {},
    }


class OutreachBenchmarkCreateView(APIView):
    """POST /api/analyzer/outreach/ {url} — start a benchmark for one domain."""

    permission_classes = [AllowAny]
    throttle_classes = [ExpensiveThrottle]

    def post(self, request):
        if not _key_ok(request):
            # Same response whether the key is wrong or the feature is off: a
            # probe should not learn which.
            return Response({"detail": "Not authorized."}, status=status.HTTP_403_FORBIDDEN)

        raw_url = str(request.data.get("url") or "").strip()
        if not raw_url:
            return Response({"detail": "A url is required."}, status=status.HTTP_400_BAD_REQUEST)

        url, err = _public_url(raw_url)
        if err:
            return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)

        prompts = request.data.get("prompts")
        pinned = [str(p).strip() for p in prompts if str(p).strip()][:12] if isinstance(prompts, list) else []

        # Serve a recent identical benchmark instead of buying it twice. Skipped
        # when the caller pinned their own prompts (a different question, so a
        # different report) or explicitly asked for a fresh run. 200, not 201:
        # nothing was created.
        force = str(request.data.get("force") or "").strip().lower() in {"1", "true", "yes"}
        if not pinned and not force:
            cached = _reusable_benchmark(url)
            if cached is not None:
                logger.info("outreach: reusing benchmark %s for %s", cached.slug, url)
                return Response(_serialize(cached), status=status.HTTP_200_OK)

        run = AnalysisRun.objects.create(
            url=url,
            run_type=AnalysisRun.RunType.OUTREACH,
            status=AnalysisRun.Status.PENDING,
            onboarding_prompts=pinned,
        )

        from core import queue

        if queue.is_eager():
            # No broker (local dev): run inline rather than silently never running.
            from ..services.outreach_benchmark import run_outreach_benchmark

            run_outreach_benchmark(run.id)
            run.refresh_from_db()
        else:
            queue.send(queue.OUTREACH_BENCHMARK, run.id)

        return Response(_serialize(run), status=status.HTTP_201_CREATED)


class OutreachBenchmarkDetailView(APIView):
    """GET /api/analyzer/outreach/<slug>/ — poll progress, then read the report.

    Open by design: the slug is an unguessable 8-byte token, and a finished
    benchmark is meant to be sent to the prospect it describes.
    """

    permission_classes = [AllowAny]
    throttle_classes = [PollingThrottle]

    def get(self, request, slug):
        run = (
            AnalysisRun.objects.filter(slug=slug, run_type=AnalysisRun.RunType.OUTREACH)
            .only(
                "slug",
                "url",
                "brand_name",
                "status",
                "progress",
                "phase",
                "error_message",
                "outreach_report",
                "updated_at",
            )
            .first()
        )
        if run is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        # Same self-heal as the dashboard's pollers: a worker that dies mid-run
        # would otherwise leave this page spinning forever.
        from ..run_guard import maybe_fail_stale

        run = maybe_fail_stale(run)
        return Response(_serialize(run))
