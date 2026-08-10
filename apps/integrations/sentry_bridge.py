"""Sentry -> GitHub issue bridge.

Sentry's own "create a GitHub issue" alert action is a Team-plan feature and this
organisation is on the Developer plan, so the same outcome is built here: Sentry
posts new issues to a webhook, and this module opens the GitHub issue.

Trust model: the payload arrives from the public internet. It is signed with the
internal integration's Client Secret (``sentry-hook-signature``, HMAC-SHA256 over
the raw body), and an unsigned or mis-signed request is refused before anything
is parsed. Without a configured secret the endpoint is disabled outright rather
than accepting everything, which is the safe default for a URL anyone can find.
"""

from __future__ import annotations

import hashlib
import hmac
import logging

from django.conf import settings

logger = logging.getLogger("apps")

SIGNATURE_HEADER = "sentry-hook-signature"
RESOURCE_HEADER = "sentry-hook-resource"

# Applied to every issue this bridge opens, so they can be filtered, bulk-closed,
# or excluded from planning without touching hand-written issues.
ISSUE_LABELS = ["sentry", "bug"]


def _secret() -> str:
    return (getattr(settings, "SENTRY_WEBHOOK_SECRET", "") or "").strip()


def verify_signature(body: bytes, signature: str) -> bool:
    """Constant-time check of Sentry's HMAC-SHA256 body signature.

    Mirrors ``github_agent.services.webhook.verify_signature``; Sentry sends the
    bare hex digest with no "sha256=" prefix.
    """
    secret = _secret()
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def _issue_title(issue: dict) -> str:
    """Shaped as [SIGNALOR-9] ValueError: ... — greppable, and unique per Sentry issue."""
    short_id = (issue.get("shortId") or "").strip()
    title = (issue.get("title") or "Sentry issue").strip()
    return f"[{short_id}] {title}" if short_id else title


def _issue_body(issue: dict, project: str) -> str:
    """The few facts a developer needs before opening Sentry itself."""
    metadata = issue.get("metadata") or {}
    lines = [
        f"Reported automatically from Sentry (project `{project}`).",
        "",
        f"- **Culprit:** `{issue.get('culprit') or 'unknown'}`",
        f"- **Level:** {issue.get('level') or 'error'}",
        f"- **First seen:** {issue.get('firstSeen') or 'unknown'}",
        f"- **Sentry ID:** `{issue.get('shortId') or issue.get('id') or 'unknown'}`",
    ]
    value = (metadata.get("value") or "").strip()
    if value:
        lines += ["", "```", value[:1000], "```"]
    permalink = (issue.get("permalink") or issue.get("web_url") or "").strip()
    if permalink:
        lines += ["", f"[View in Sentry]({permalink})"]
    return "\n".join(lines)


def _target_installation():
    """The GitHub App installation that owns the repo issues are filed against.

    Resolved by repo rather than by organisation: this bridge reports OUR own
    backend's errors, so it targets one fixed repo (SENTRY_GITHUB_REPO), not a
    customer's.
    """
    from apps.github_agent.models import GithubInstallation

    repo = (getattr(settings, "SENTRY_GITHUB_REPO", "") or "").strip()
    if not repo:
        return None, ""
    install = GithubInstallation.objects.filter(repo_full_name__iexact=repo, is_active=True).first()
    return install, repo


def handle_issue_created(payload: dict) -> str | None:
    """Open a GitHub issue for a new Sentry issue. Returns the issue URL, or None.

    Fail-soft by contract: the caller answers Sentry 200 regardless, because a
    webhook that errors gets retried and would file duplicates. Every refusal is
    logged with its reason instead.
    """
    data = (payload.get("data") or {}).get("issue") or {}
    if not data:
        logger.warning("sentry bridge: payload had no issue data")
        return None

    install, repo = _target_installation()
    if install is None:
        logger.warning("sentry bridge: no active GitHub installation for repo %r", repo)
        return None

    from apps.integrations.github.client import GithubClient

    client = GithubClient(install.installation_id, repo)

    # Sentry retries a webhook it thinks failed, and an issue that keeps erroring
    # can notify more than once. Both would file duplicates, so an existing issue
    # carrying this short-id wins.
    short_id = (data.get("shortId") or "").strip()
    if short_id:
        marker = f"[{short_id}]"
        for existing in client.search_issues(f'in:title "{marker}"'):
            # GitHub's search tokenises loosely, so a hit is a candidate, not a
            # match. Confirm the marker is really in the title before treating
            # this as a duplicate — accepting a stray hit would silently drop
            # the alert and hand back an unrelated issue's URL.
            if marker not in (existing.get("title") or ""):
                continue
            url = existing.get("html_url") or ""
            logger.info("sentry bridge: %s already filed as %s", short_id, url)
            return url

    project = (
        ((payload.get("data") or {}).get("project") or {}).get("slug")
        or payload.get("projectSlug")
        or "signalor"
    )
    issue = client.create_issue(_issue_title(data), _issue_body(data, project), labels=list(ISSUE_LABELS))
    url = issue.get("html_url") or ""
    logger.info("sentry bridge: filed %s as %s", short_id or "issue", url)
    return url
