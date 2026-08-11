"""Read-time reconciliation of a fix job's PR state.

The webhook is the fast path but a single point of failure: an unconfigured or
undelivered ``pull_request`` hook left a merged PR reading "PR Open" forever.
"""

from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.analyzer.models import AnalysisRun
from apps.github_agent.models import GithubFixJob, GithubInstallation
from apps.github_agent.services.pr_sync import reconcile

REPO = "Optiminastic/Signalor-AI-Search"


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class PrSyncTests(TestCase):
    def setUp(self):
        cache.clear()
        self.run = AnalysisRun.objects.create(url="https://signalor.ai")
        self.install = GithubInstallation.objects.create(
            installation_id=99, repo_full_name=REPO, is_active=True
        )

    def _job(self, status=GithubFixJob.Status.OPEN, pr_number=75):
        return GithubFixJob.objects.create(
            analysis_run=self.run, installation=self.install, status=status, pr_number=pr_number
        )

    def _client(self, pr):
        client = MagicMock()
        client.get_pull_request.return_value = pr
        return client

    def test_a_merged_pr_flips_the_job_to_merged(self):
        job = self._job()
        with patch(
            "apps.integrations.github.client.GithubClient",
            return_value=self._client({"state": "closed", "merged_at": "2026-08-10T13:15:00Z"}),
        ):
            reconcile([job])

        job.refresh_from_db()
        self.assertEqual(job.status, GithubFixJob.Status.MERGED)

    def test_a_pr_closed_without_merge_flips_to_closed(self):
        job = self._job()
        with patch(
            "apps.integrations.github.client.GithubClient",
            return_value=self._client({"state": "closed", "merged_at": None}),
        ):
            reconcile([job])

        job.refresh_from_db()
        self.assertEqual(job.status, GithubFixJob.Status.CLOSED)

    def test_a_still_open_pr_is_left_alone(self):
        job = self._job()
        with patch(
            "apps.integrations.github.client.GithubClient",
            return_value=self._client({"state": "open", "merged_at": None}),
        ):
            reconcile([job])

        job.refresh_from_db()
        self.assertEqual(job.status, GithubFixJob.Status.OPEN)

    def test_already_terminal_jobs_are_never_re_checked(self):
        job = self._job(status=GithubFixJob.Status.MERGED)
        with patch("apps.integrations.github.client.GithubClient") as gh:
            reconcile([job])
        gh.assert_not_called()

    def test_the_same_job_is_not_polled_twice_inside_the_ttl(self):
        job = self._job()
        client = self._client({"state": "open", "merged_at": None})
        with patch("apps.integrations.github.client.GithubClient", return_value=client):
            reconcile([job])
            reconcile([job])

        self.assertEqual(client.get_pull_request.call_count, 1)

    def test_a_github_failure_leaves_the_stored_status_intact(self):
        """A hiccup must degrade to the stored value, never break the poll."""
        job = self._job()
        client = MagicMock()
        client.get_pull_request.side_effect = RuntimeError("GitHub is down")
        with patch("apps.integrations.github.client.GithubClient", return_value=client):
            reconcile([job])

        job.refresh_from_db()
        self.assertEqual(job.status, GithubFixJob.Status.OPEN)
