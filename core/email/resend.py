"""Resend as the single email transport for the backend.

Every email this service sends used to leave through SendGrid by one of two
routes: a hand-rolled HTTPS POST in ``analyzer.email_utils`` (welcome, weekly),
and Django's SMTP backend pointed at ``smtp.sendgrid.net`` (digest, drip,
billing, enterprise). The frontend meanwhile sends sign-in OTPs through Resend —
the one path with observable production delivery. Two vendors, three code paths,
and only one of them demonstrably working.

This module is the single seam. ``send()`` is the transport; ``ResendEmailBackend``
adapts it to ``django.core.mail`` so every existing ``send_mail`` /
``EmailMessage`` / ``EmailMultiAlternatives`` call site keeps working untouched.

Stdlib ``urllib`` on purpose: it mirrors what the SendGrid helper already did and
adds no dependency for what is one JSON POST.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger("apps")

ENDPOINT = "https://api.resend.com/emails"
TIMEOUT_SECONDS = 10


def api_key() -> str:
    """Read at call time, not import time, so tests and settings reloads apply."""
    return os.getenv("RESEND_API_KEY", "")


def _payload(
    to: list[str], subject: str, html: str, plain: str, from_email: str
) -> dict[str, object]:
    body: dict[str, object] = {"from": from_email, "to": to, "subject": subject}
    # Resend rejects a request carrying neither; send whichever we actually have,
    # and both when both exist so text-only clients still get something readable.
    if html:
        body["html"] = html
    if plain:
        body["text"] = plain
    if not html and not plain:
        body["text"] = ""
    return body


def send(
    to: str | list[str],
    subject: str,
    *,
    html: str = "",
    plain: str = "",
    from_email: str = "",
) -> bool:
    """POST one message to Resend. Returns True on success, never raises.

    Callers treat email as best-effort throughout this codebase — a failed
    digest must not fail the analysis that produced it — so transport problems
    are logged and reported, not thrown.
    """
    key = api_key()
    recipients = [to] if isinstance(to, str) else list(to)
    recipients = [r for r in recipients if r]
    if not recipients:
        logger.error("Resend: no recipient for %r", subject)
        return False
    if not key:
        logger.error("RESEND_API_KEY not set — email to %s skipped (%r)", recipients, subject)
        return False

    sender = from_email or default_from()
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(_payload(recipients, subject, html, plain, sender)).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            logger.info("Email sent to %s (status=%s, subject=%r)", recipients, resp.status, subject)
            return True
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.error("Resend HTTP %s to %s (%r): %s", exc.code, recipients, subject, detail)
        return False
    except Exception:
        logger.exception("Unexpected error sending to %s (%r)", recipients, subject)
        return False


def default_from() -> str:
    from django.conf import settings

    return getattr(settings, "DEFAULT_FROM_EMAIL", "") or "hello@signalor.ai"


def _bodies(message) -> tuple[str, str]:
    """Split a Django message into (html, plain).

    ``EmailMultiAlternatives`` keeps the HTML in ``alternatives``; a plain
    ``EmailMessage`` may itself be html when ``content_subtype`` says so.
    """
    html = ""
    for content, mimetype in getattr(message, "alternatives", None) or []:
        if mimetype == "text/html":
            html = content
            break
    body = message.body or ""
    if not html and getattr(message, "content_subtype", "plain") == "html":
        return body, ""
    return html, body


class ResendEmailBackend(BaseEmailBackend):
    """Route ``django.core.mail`` through Resend instead of SMTP.

    Set as ``EMAIL_BACKEND``, this converts every existing call site in the app
    without touching one of them.
    """

    def send_messages(self, email_messages) -> int:
        if not email_messages:
            return 0
        sent = 0
        for message in email_messages:
            html, plain = _bodies(message)
            ok = send(
                list(message.to or []),
                message.subject or "",
                html=html,
                plain=plain,
                from_email=message.from_email or default_from(),
            )
            if ok:
                sent += 1
            elif not self.fail_silently:
                # Matching Django's contract would mean raising here, but every
                # caller in this codebase treats email as best-effort and none
                # catch. Logged in `send`; the count tells a caller that cares.
                continue
        return sent
