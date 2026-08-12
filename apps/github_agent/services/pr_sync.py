"""Reconcile a fix job's PR state with GitHub.

The merged/closed transition normally arrives on the ``pull_request`` webhook
(services/webhook._handle_pull_request). That is the fast path and stays the
primary one — but it is also a single point of failure: if the App's webhook is
not configured, cannot reach this deployment, or a delivery is simply dropped,
the job sits at "open" forever and the task page keeps showing "PR Open" for a
pull request the user merged minutes ago, with no way to correct itself.

So reads reconcile too. Polling the jobs endpoint asks GitHub for the real state
of any job still believed open, which makes the UI eventually correct regardless
of webhook delivery. Bounded deliberately: only open jobs, only a handful per
request, and no more than once per ``_TTL`` seconds per job, so a page that
polls every few seconds cannot turn into a GitHub rate-limit problem.
"""

from __future__ import annotations

import logging

from django.core.cache import cache

from ..models import GithubFixJob

logger = logging.getLogger("apps")

# Per-job floor between GitHub lookups. A merge the webhook missed surfaces
# within this window instead of never.
_TTL = 60
# Cap per request so one page load can't fan out into dozens of GitHub calls.
# The TTL is set as a side effect of the check, so successive polls rotate
# through the remaining jobs rather than re-checking the same first five.
_MAX_PER_REQUEST = 5

# Statuses whose truth still lives on GitHub. MERGED is terminal — a merge
# cannot be undone — so it is never spent on an API call.
_RECONCILABLE = frozenset({GithubFixJob.Status.OPEN, GithubFixJob.Status.CLOSED})


def _recently_checked(job_id: int) -> bool:
    key = f"gh-pr-sync:{job_id}"
    if cache.get(key):
        return True
    try:
        cache.set(key, 1, _TTL)
    except Exception:
        # A cache outage must not stop reconciliation; it only removes the floor.
        logger.warning("pr_sync: cache unavailable for job %s", job_id, exc_info=True)
    return False


def _state_from_github(job: GithubFixJob) -> str | None:
    """GitHub's current state for the job's PR, as a GithubFixJob.Status value."""
    installation = getattr(job, "installation", None)
    repo = getattr(installation, "repo_full_name", "") or ""
    if not installation or not repo or not job.pr_number:
        return None

    from apps.integrations.github.client import GithubClient

    pr = GithubClient(installation.installation_id, repo).get_pull_request(job.pr_number)
    if not pr:
        return None
    if pr.get("merged_at") or pr.get("merged"):
        return GithubFixJob.Status.MERGED
    if pr.get("state") == "closed":
        return GithubFixJob.Status.CLOSED
    if pr.get("state") == "open":
        # Explicit, so a job stranded on CLOSED by a missed webhook can come back
        # when the PR is reopened. Returning None here would leave it stuck.
        return GithubFixJob.Status.OPEN
    return None


def reconcile(jobs: list[GithubFixJob]) -> list[GithubFixJob]:
    """Refresh any still-open job whose PR has since been merged or closed.

    Never raises: a GitHub hiccup degrades to the stored status rather than
    failing the poll the whole task page depends on.
    """
    checked = 0
    for job in jobs:
        if checked >= _MAX_PER_REQUEST:
            break
        # CLOSED is reconcilable too: a PR can be reopened, and a job left on
        # CLOSED by a missed webhook would otherwise never be revisited. MERGED
        # is genuinely final and never re-checked.
        if job.status not in _RECONCILABLE or not job.pr_number:
            continue
        if _recently_checked(job.id):
            continue
        checked += 1
        try:
            state = _state_from_github(job)
        except Exception:
            logger.warning("pr_sync: could not read PR #%s state", job.pr_number, exc_info=True)
            continue
        if state and state != job.status:
            job.status = state
            job.save(update_fields=["status", "updated_at"])
            logger.info("pr_sync: job %s PR #%s -> %s", job.id, job.pr_number, state)
    return jobs
