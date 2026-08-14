"""Email utilities. Every send here leaves through Resend (see core.email.resend).

The digest still goes via ``django.core.mail``; that is the same transport now,
because ``EMAIL_BACKEND`` is ``ResendEmailBackend``.
"""

import logging
import os

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from core.email.resend import send as resend_send

logger = logging.getLogger("apps")

FRONTEND_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")


def send_digest_email(to_email: str, context: dict):
    """Send a GEO score digest email."""
    context["frontend_url"] = FRONTEND_URL
    context["dashboard_url"] = f"{FRONTEND_URL}/dashboard/{context.get('slug', '')}"

    try:
        html_body = render_to_string("analyzer/digest_email.html", context)
    except Exception:
        logger.exception("Failed to render digest email template")
        html_body = _fallback_html(context)

    score = context.get("score", 0)
    brand = context.get("brand_name", "Your site")

    try:
        send_mail(
            subject=f"Signalor GEO Report: {brand} scored {score}/100",
            message=_plain_text(context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            html_message=html_body,
            fail_silently=False,
        )
    except Exception:
        logger.exception(f"Failed to send digest email to {to_email}")


def _plain_text(ctx: dict) -> str:
    lines = [
        f"GEO Score Report for {ctx.get('brand_name', 'your site')}",
        f"URL: {ctx.get('url', '')}",
        f"Current Score: {ctx.get('score', 0)}/100",
    ]
    if ctx.get("score_change") is not None:
        sign = "+" if ctx["score_change"] >= 0 else ""
        lines.append(f"Change: {sign}{ctx['score_change']} points")
    if ctx.get("recommendations"):
        lines.append("\nTop Recommendations:")
        for rec in ctx["recommendations"]:
            lines.append(f"  - [{rec['priority']}] {rec['title']}")
    lines.append(f"\nView full report: {ctx.get('dashboard_url', '')}")
    return "\n".join(lines)


def _fallback_html(ctx: dict) -> str:
    return f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <h2>GEO Score Report</h2>
        <p><strong>{ctx.get('brand_name', 'Your site')}</strong></p>
        <p style="font-size:48px;font-weight:bold;color:#2563eb;">{ctx.get('score', 0)}/100</p>
        <p><a href="{ctx.get('dashboard_url', '#')}">View Full Report</a></p>
    </div>
    """


# ── Delivery (welcome + weekly emails) ────────────────────────────────────────

_FROM = "Signalor <hello@signalor.ai>"
_EMAIL_LOGO_URL = os.getenv(
    "EMAIL_LOGO_URL",
    "https://res.cloudinary.com/dui7h1n3d/image/upload/v1779273045/icon_mitiu2.svg",
)


def _sg_send(to_email: str, subject: str, html: str, plain: str) -> bool:
    """Send one transactional email. Returns True on success.

    Kept under its original name so the ten-odd call sites and their tests stay
    untouched; the body is now Resend rather than a hand-rolled SendGrid POST.
    """
    return resend_send(to_email, subject, html=html, plain=plain, from_email=_FROM)


def send_welcome_email(to_email: str, first_name: str = "", dashboard_slug: str = "") -> bool:
    """Send the post-first-analysis welcome email via SendGrid."""
    dashboard_url = (
        f"{FRONTEND_URL}/dashboard/{dashboard_slug}" if dashboard_slug else f"{FRONTEND_URL}/dashboard"
    )
    context = {
        "first_name": first_name,
        "dashboard_url": dashboard_url,
        "logo_url": _EMAIL_LOGO_URL,
        "frontend_url": FRONTEND_URL,
    }
    try:
        html = render_to_string("emails/welcome_email.html", context)
    except Exception:
        logger.exception("Failed to render welcome_email.html for %s", to_email)
        greeting = f"Hi {first_name}," if first_name else "Hi,"
        html = (
            f'<div style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px;">'
            f"<p>{greeting}</p><p>Your Signalor brand analysis is ready.</p>"
            f'<p><a href="{dashboard_url}">View My AI Dashboard →</a></p>'
            f"<p>— The Signalor Team</p></div>"
        )

    greeting = f"Hi {first_name}," if first_name else "Hi,"
    plain = (
        f"{greeting}\n\nYour Signalor brand analysis is ready.\n\n"
        f"View your dashboard:\n{dashboard_url}\n\n— The Signalor Team\nhello@signalor.ai"
    )
    return _sg_send(
        to_email,
        subject="Welcome to Signalor — your AI visibility report is ready",
        html=html,
        plain=plain,
    )


def send_weekly_email(to_email: str, context: dict) -> bool:
    """Send the weekly analytics report email via SendGrid."""
    slug = context.get("slug", "")
    dashboard_url = f"{FRONTEND_URL}/dashboard/{slug}" if slug else f"{FRONTEND_URL}/dashboard"
    context["logo_url"] = _EMAIL_LOGO_URL
    context["dashboard_url"] = dashboard_url
    context["frontend_url"] = FRONTEND_URL

    try:
        html = render_to_string("emails/weekly_report.html", context)
    except Exception:
        logger.exception("Failed to render weekly_report.html for %s", to_email)
        html = _weekly_fallback_html(context)

    brand = context.get("brand_name", "your site")
    score = context.get("score", 0)
    plain = (
        f"Weekly AI Visibility Report — {brand}\n\n"
        f"GEO Score: {score}/100\n\n"
        f"View full report: {dashboard_url}\n\n"
        "— The Signalor Team\nhello@signalor.ai"
    )
    return _sg_send(
        to_email,
        subject=f"Your weekly AI visibility report — {brand}",
        html=html,
        plain=plain,
    )


def _weekly_fallback_html(ctx: dict) -> str:
    return (
        '<div style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:24px;">'
        f'<h2>Weekly Report: {ctx.get("brand_name", "")}</h2>'
        f'<p>GEO Score: <strong>{ctx.get("score", 0)}/100</strong></p>'
        f'<p><a href="{ctx.get("dashboard_url", "#")}">Open Full Dashboard →</a></p>'
        "</div>"
    )
