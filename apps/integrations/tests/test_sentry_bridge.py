"""The Sentry -> GitHub issue bridge.

The contract that matters most is the signature. This endpoint is
unauthenticated by necessity (Sentry cannot log in) and reachable by anyone who
finds the URL, so an unsigned request must never reach the GitHub client.
"""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.github_agent.models import GithubInstallation

SECRET = "test-sentry-secret"
REPO = "Optiminastic/Signalor-BE"
URL = "/api/integrations/sentry/webhook/"

PAYLOAD = {
    "action": "created",
    "data": {
        "issue": {
            "id": "123",
            "shortId": "SIGNALOR-9",
            "title": "ValueError: onboarding org 11 not found",
            "culprit": "/api/github/callback/",
            "level": "error",
            "firstSeen": "2026-08-08T09:00:00Z",
            "permalink": "https://optiminastic.sentry.io/issues/123/",
            "metadata": {"value": "onboarding org 11 not found in this environment"},
        },
        "project": {"slug": "signalor"},
    },
}


def _signed(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@override_settings(SENTRY_WEBHOOK_SECRET=SECRET, SENTRY_GITHUB_REPO=REPO)
class SentryWebhookTests(TestCase):
    def setUp(self):
        GithubInstallation.objects.create(installation_id=4242, repo_full_name=REPO, is_active=True)
        self.body = json.dumps(PAYLOAD).encode()

    def _post(self, body=None, signature=None, resource="issue"):
        body = self.body if body is None else body
        headers = {"sentry-hook-resource": resource}
        if signature is not None:
            headers["sentry-hook-signature"] = signature
        return self.client.post(URL, body, content_type="application/json", headers=headers)

    def _client_mock(self, existing=None, html_url="https://github.com/o/r/issues/7"):
        client = MagicMock()
        client.search_issues.return_value = existing or []
        client.create_issue.return_value = {"html_url": html_url}
        return client

    def test_a_signed_new_issue_is_filed_on_github(self):
        client = self._client_mock()
        with patch("apps.integrations.github.client.GithubClient", return_value=client):
            resp = self._post(signature=_signed(self.body))

        self.assertEqual(resp.status_code, 200, resp.content)
        client.create_issue.assert_called_once()
        title = client.create_issue.call_args.args[0]
        self.assertIn("SIGNALOR-9", title)
        self.assertIn("ValueError", title)

    def test_an_unsigned_request_is_refused_and_touches_nothing(self):
        with patch("apps.integrations.github.client.GithubClient") as gh:
            resp = self._post(signature=None)

        self.assertEqual(resp.status_code, 403)
        gh.assert_not_called()

    def test_a_wrong_signature_is_refused(self):
        with patch("apps.integrations.github.client.GithubClient") as gh:
            resp = self._post(signature=_signed(self.body, "not-the-secret"))

        self.assertEqual(resp.status_code, 403)
        gh.assert_not_called()

    def test_a_tampered_body_no_longer_matches_its_signature(self):
        good = _signed(self.body)
        tampered = json.dumps({**PAYLOAD, "action": "resolved"}).encode()
        with patch("apps.integrations.github.client.GithubClient") as gh:
            resp = self._post(body=tampered, signature=good)

        self.assertEqual(resp.status_code, 403)
        gh.assert_not_called()

    @override_settings(SENTRY_WEBHOOK_SECRET="")
    def test_no_configured_secret_disables_the_endpoint(self):
        """The safe default: a URL anyone can find must not accept everything."""
        with patch("apps.integrations.github.client.GithubClient") as gh:
            resp = self._post(signature=_signed(self.body))

        self.assertEqual(resp.status_code, 403)
        gh.assert_not_called()

    def test_an_already_filed_issue_is_not_filed_twice(self):
        """Sentry retries what it thinks failed; a retry must not duplicate."""
        existing = [
            {
                "html_url": "https://github.com/o/r/issues/3",
                "title": "[SIGNALOR-9] ValueError: onboarding org 11 not found",
            }
        ]
        client = self._client_mock(existing=existing)
        with patch("apps.integrations.github.client.GithubClient", return_value=client):
            resp = self._post(signature=_signed(self.body))

        self.assertEqual(resp.status_code, 200)
        client.create_issue.assert_not_called()
        self.assertEqual(resp.json()["github_issue"], existing[0]["html_url"])

    def test_a_loose_search_hit_does_not_swallow_the_alert(self):
        """GitHub search tokenises loosely, so a hit is a candidate, not a match.

        Accepting one blindly would drop the real alert and hand back an
        unrelated issue's URL.
        """
        unrelated = [
            {"html_url": "https://github.com/o/r/issues/99", "title": "Refactor the SIGNALOR parser"}
        ]
        client = self._client_mock(existing=unrelated)
        with patch("apps.integrations.github.client.GithubClient", return_value=client):
            resp = self._post(signature=_signed(self.body))

        self.assertEqual(resp.status_code, 200)
        client.create_issue.assert_called_once()
        self.assertNotEqual(resp.json()["github_issue"], unrelated[0]["html_url"])

    def test_other_sentry_hooks_are_acknowledged_and_ignored(self):
        body = json.dumps({"action": "created", "data": {}}).encode()
        with patch("apps.integrations.github.client.GithubClient") as gh:
            resp = self._post(body=body, signature=_signed(body), resource="installation")

        self.assertEqual(resp.status_code, 202)
        gh.assert_not_called()

    def test_a_github_failure_is_absorbed_rather_than_retried_into_duplicates(self):
        client = self._client_mock()
        client.create_issue.side_effect = ValueError("create_issue failed (HTTP 403)")
        with patch("apps.integrations.github.client.GithubClient", return_value=client):
            resp = self._post(signature=_signed(self.body))

        self.assertEqual(resp.status_code, 202)

    def test_no_matching_installation_is_logged_not_crashed(self):
        GithubInstallation.objects.all().delete()
        resp = self._post(signature=_signed(self.body))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {})
