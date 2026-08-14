"""Resend is the backend's only email transport.

Email used to leave through SendGrid by two separate routes — a hand-rolled POST
for welcome/weekly and Django SMTP for digest/drip/billing/enterprise — while the
frontend sent OTPs through Resend. These pin the single-transport rule so a
future change cannot quietly reintroduce a second vendor, and pin the
best-effort contract every caller in this codebase already relies on.
"""

import json
import urllib.error
from unittest.mock import patch

from django.core.mail import EmailMessage, EmailMultiAlternatives, send_mail
from django.test import TestCase, override_settings

from core.email import resend

TO = "someone@example.com"


class _Resp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _sent_body(urlopen) -> dict:
    """The JSON actually posted to Resend."""
    request = urlopen.call_args[0][0]
    return json.loads(request.data.decode("utf-8"))


@override_settings(DEFAULT_FROM_EMAIL="hello@signalor.ai")
class ResendTransportTests(TestCase):
    @patch.dict("os.environ", {"RESEND_API_KEY": "re_test"})
    @patch("urllib.request.urlopen", return_value=_Resp())
    def test_posts_the_message_to_resend(self, urlopen):
        self.assertTrue(resend.send(TO, "Subject", html="<p>hi</p>", plain="hi"))

        request = urlopen.call_args[0][0]
        self.assertEqual(request.full_url, "https://api.resend.com/emails")
        self.assertEqual(request.headers["Authorization"], "Bearer re_test")

        body = _sent_body(urlopen)
        self.assertEqual(body["to"], [TO])
        self.assertEqual(body["subject"], "Subject")
        self.assertEqual(body["html"], "<p>hi</p>")
        self.assertEqual(body["text"], "hi")

    @patch.dict("os.environ", {"RESEND_API_KEY": ""})
    @patch("urllib.request.urlopen")
    def test_without_a_key_it_reports_failure_and_sends_nothing(self, urlopen):
        self.assertFalse(resend.send(TO, "Subject", plain="hi"))
        urlopen.assert_not_called()

    @patch.dict("os.environ", {"RESEND_API_KEY": "re_test"})
    @patch("urllib.request.urlopen")
    def test_an_http_error_is_reported_not_raised(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError(
            resend.ENDPOINT, 422, "Unprocessable", {}, None
        )
        # Every caller treats email as best-effort; a digest failure must not
        # fail the analysis that produced it.
        self.assertFalse(resend.send(TO, "Subject", plain="hi"))

    @patch.dict("os.environ", {"RESEND_API_KEY": "re_test"})
    @patch("urllib.request.urlopen")
    def test_an_empty_recipient_list_sends_nothing(self, urlopen):
        self.assertFalse(resend.send([], "Subject", plain="hi"))
        self.assertFalse(resend.send("", "Subject", plain="hi"))
        urlopen.assert_not_called()


@override_settings(
    EMAIL_BACKEND="core.email.resend.ResendEmailBackend",
    DEFAULT_FROM_EMAIL="hello@signalor.ai",
)
class DjangoMailGoesThroughResendTests(TestCase):
    """The point of the backend: existing call sites change nothing."""

    @patch.dict("os.environ", {"RESEND_API_KEY": "re_test"})
    @patch("urllib.request.urlopen", return_value=_Resp())
    def test_send_mail_routes_through_resend(self, urlopen):
        sent = send_mail(
            subject="Digest",
            message="plain body",
            from_email="hello@signalor.ai",
            recipient_list=[TO],
            html_message="<p>rich</p>",
        )
        self.assertEqual(sent, 1)
        body = _sent_body(urlopen)
        self.assertEqual(body["to"], [TO])
        self.assertEqual(body["html"], "<p>rich</p>")
        self.assertEqual(body["text"], "plain body")

    @patch.dict("os.environ", {"RESEND_API_KEY": "re_test"})
    @patch("urllib.request.urlopen", return_value=_Resp())
    def test_multipart_alternatives_split_into_html_and_text(self, urlopen):
        msg = EmailMultiAlternatives("Billing", "text version", "hello@signalor.ai", [TO])
        msg.attach_alternative("<b>html version</b>", "text/html")
        self.assertEqual(msg.send(), 1)
        body = _sent_body(urlopen)
        self.assertEqual(body["html"], "<b>html version</b>")
        self.assertEqual(body["text"], "text version")

    @patch.dict("os.environ", {"RESEND_API_KEY": "re_test"})
    @patch("urllib.request.urlopen", return_value=_Resp())
    def test_an_html_only_message_is_not_sent_as_plain_text(self, urlopen):
        # apps.drip sends EmailMessage with content_subtype="html"; posting that
        # markup as `text` would deliver visible tags to the recipient.
        msg = EmailMessage("Drip", "<h1>hi</h1>", "hello@signalor.ai", [TO])
        msg.content_subtype = "html"
        self.assertEqual(msg.send(), 1)
        body = _sent_body(urlopen)
        self.assertEqual(body["html"], "<h1>hi</h1>")
        self.assertNotIn("text", body)


@override_settings(DEFAULT_FROM_EMAIL="hello@signalor.ai")
class WelcomeAndWeeklyUseResendTests(TestCase):
    """The two emails that had their own SendGrid POST now share the transport."""

    @patch.dict("os.environ", {"RESEND_API_KEY": "re_test"})
    @patch("urllib.request.urlopen", return_value=_Resp())
    def test_welcome_email_goes_to_resend(self, urlopen):
        from apps.analyzer.email_utils import send_welcome_email

        self.assertTrue(send_welcome_email(TO, first_name="Ada", dashboard_slug="abc"))
        request = urlopen.call_args[0][0]
        self.assertEqual(request.full_url, "https://api.resend.com/emails")
        self.assertEqual(_sent_body(urlopen)["to"], [TO])
