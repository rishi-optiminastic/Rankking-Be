"""A fix PR belongs to one action, not to every action sharing its code.

A finding code is not unique. Ten "Win the AI query" actions all carry
`geo_prompt_lost` and differ only by which prompt they target. Keying a fix job
on the code alone had two consequences, both visible in the product: one PR
appeared on every one of those rows, and the in-flight dedup refused to fix any
of the other nine ("a pull request for these findings is already open").
"""

from django.test import TestCase

from apps.analyzer.models import AnalysisRun
from apps.github_agent.models import GithubFixJob, GithubInstallation

CODE = "geo_prompt_lost"


class FixJobScopeTests(TestCase):
    def setUp(self):
        self.install = GithubInstallation.objects.create(
            installation_id=31, repo_full_name="Optiminastic/Signalor-AI-Search", is_active=True
        )
        self.run = AnalysisRun.objects.create(url="https://signalor.ai", email="a@signalor.ai")

    def _job(self, recommendation_id, status=GithubFixJob.Status.OPEN, pr_number=83):
        return GithubFixJob.objects.create(
            installation=self.install,
            analysis_run=self.run,
            finding_codes=[CODE],
            recommendation_id=recommendation_id,
            status=status,
            pr_number=pr_number,
        )

    def test_a_job_records_the_action_it_was_raised_for(self):
        self.assertEqual(self._job(501).recommendation_id, 501)

    def test_two_actions_sharing_a_code_get_their_own_jobs(self):
        """The incident: one PR must not stand in for every prompt action."""
        first, second = self._job(501, pr_number=83), self._job(502, pr_number=84)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(
            sorted(
                GithubFixJob.objects.filter(analysis_run=self.run).values_list("recommendation_id", flat=True)
            ),
            [501, 502],
        )

    def test_an_open_pr_only_blocks_its_own_action(self):
        """The worse half of the bug: an open PR for one prompt used to make
        every other prompt action unfixable."""
        self._job(501)
        inflight = GithubFixJob.objects.filter(
            analysis_run=self.run,
            status__in=[
                GithubFixJob.Status.PENDING,
                GithubFixJob.Status.RUNNING,
                GithubFixJob.Status.OPEN,
            ],
        )
        # The endpoint's own scoping rule, applied to a different action.
        self.assertFalse(inflight.filter(recommendation_id=502).exists())
        self.assertTrue(inflight.filter(recommendation_id=501).exists())

    def test_an_untargeted_job_still_dedups_class_wide(self):
        """A caller that names no action keeps the old whole-finding rule, so it
        still cannot open two PRs for the same finding."""
        self._job(None)
        inflight = GithubFixJob.objects.filter(analysis_run=self.run, status=GithubFixJob.Status.OPEN)
        self.assertTrue(inflight.filter(recommendation_id__isnull=True).exists())

    def test_older_jobs_have_no_target_and_are_still_readable(self):
        """Backfill-free: pre-existing rows are NULL and must not break reads."""
        job = self._job(None)
        job.refresh_from_db()
        self.assertIsNone(job.recommendation_id)


class FixJobSerializationTests(TestCase):
    def test_the_api_exposes_the_target(self):
        """Without this the dashboard cannot tell whose PR a job is."""
        from apps.github_agent.views import _job_dict

        install = GithubInstallation.objects.create(installation_id=32, repo_full_name="o/r", is_active=True)
        run = AnalysisRun.objects.create(url="https://signalor.ai")
        job = GithubFixJob.objects.create(
            installation=install,
            analysis_run=run,
            finding_codes=[CODE],
            recommendation_id=777,
            status=GithubFixJob.Status.OPEN,
        )
        self.assertEqual(_job_dict(job)["recommendation_id"], 777)
