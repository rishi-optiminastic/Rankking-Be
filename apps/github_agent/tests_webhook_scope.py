"""The pull_request webhook must act on exactly one customer's job.

PR numbers are per-repository, so matching an incoming event on the number alone
crossed tenants: merging #7 in one customer's repo flipped a different
customer's #7 to MERGED and fired a re-crawl against their run. Identity here is
(installation, pr_number) — never the number by itself.
"""

from unittest.mock import patch

from django.test import TestCase

from apps.analyzer.models import AnalysisRun
from apps.github_agent.models import GithubFixJob, GithubInstallation
from apps.github_agent.services.webhook import handle_event

MINE = "Optiminastic/Signalor-AI-Search"
THEIRS = "SomeoneElse/their-app"
PR = 7


def _payload(action, repo, installation_id, merged=False, state="closed"):
    return {
        "action": action,
        "pull_request": {"number": PR, "merged": merged, "state": state},
        "repository": {"full_name": repo},
        "installation": {"id": installation_id},
    }


class WebhookScopeTests(TestCase):
    def setUp(self):
        self.mine = GithubInstallation.objects.create(installation_id=11, repo_full_name=MINE, is_active=True)
        self.theirs = GithubInstallation.objects.create(
            installation_id=22, repo_full_name=THEIRS, is_active=True
        )
        self.my_run = AnalysisRun.objects.create(url="https://signalor.ai")
        self.their_run = AnalysisRun.objects.create(url="https://elsewhere.com")

        self.my_job = GithubFixJob.objects.create(
            analysis_run=self.my_run,
            installation=self.mine,
            status=GithubFixJob.Status.OPEN,
            pr_number=PR,
        )
        # Same PR number, different customer — the collision that caused the bug.
        self.their_job = GithubFixJob.objects.create(
            analysis_run=self.their_run,
            installation=self.theirs,
            status=GithubFixJob.Status.OPEN,
            pr_number=PR,
        )

    def _statuses(self):
        self.my_job.refresh_from_db()
        self.their_job.refresh_from_db()
        return self.my_job.status, self.their_job.status

    def test_a_merge_touches_only_the_repo_it_came_from(self):
        with patch("apps.github_agent.services.webhook._trigger_recrawl"):
            handle_event("pull_request", _payload("closed", MINE, 11, merged=True))
        mine, theirs = self._statuses()
        self.assertEqual(mine, GithubFixJob.Status.MERGED)
        self.assertEqual(theirs, GithubFixJob.Status.OPEN, "another tenant's job must not move")

    def test_the_other_tenant_s_merge_does_not_touch_mine(self):
        with patch("apps.github_agent.services.webhook._trigger_recrawl"):
            handle_event("pull_request", _payload("closed", THEIRS, 22, merged=True))
        mine, theirs = self._statuses()
        self.assertEqual(mine, GithubFixJob.Status.OPEN)
        self.assertEqual(theirs, GithubFixJob.Status.MERGED)

    def test_a_recrawl_only_fires_for_the_owning_run(self):
        with patch("apps.github_agent.services.webhook._trigger_recrawl") as recrawl:
            handle_event("pull_request", _payload("closed", MINE, 11, merged=True))
        recrawl.assert_called_once()
        self.assertEqual(recrawl.call_args.args[0].pk, self.my_job.pk)

    def test_an_event_with_no_installation_or_repo_is_ignored(self):
        """Unattributable: acting would mean guessing whose PR it is."""
        payload = {"action": "closed", "pull_request": {"number": PR, "merged": True}}
        with patch("apps.github_agent.services.webhook._trigger_recrawl") as recrawl:
            handle_event("pull_request", payload)
        mine, theirs = self._statuses()
        self.assertEqual((mine, theirs), (GithubFixJob.Status.OPEN, GithubFixJob.Status.OPEN))
        recrawl.assert_not_called()

    def test_repo_name_alone_still_scopes_when_installation_id_is_absent(self):
        payload = _payload("closed", MINE, None, merged=True)
        payload.pop("installation")
        with patch("apps.github_agent.services.webhook._trigger_recrawl"):
            handle_event("pull_request", payload)
        mine, theirs = self._statuses()
        self.assertEqual(mine, GithubFixJob.Status.MERGED)
        self.assertEqual(theirs, GithubFixJob.Status.OPEN)

    def test_a_close_without_merge_is_recorded_as_closed(self):
        handle_event("pull_request", _payload("closed", MINE, 11, merged=False))
        self.assertEqual(self._statuses()[0], GithubFixJob.Status.CLOSED)

    def test_reopening_a_closed_pr_returns_it_to_open(self):
        """Otherwise it strands on CLOSED, which nothing ever revisits."""
        self.my_job.status = GithubFixJob.Status.CLOSED
        self.my_job.save(update_fields=["status"])
        handle_event("pull_request", _payload("reopened", MINE, 11, state="open"))
        self.assertEqual(self._statuses()[0], GithubFixJob.Status.OPEN)

    def test_reopening_never_downgrades_a_merged_job(self):
        self.my_job.status = GithubFixJob.Status.MERGED
        self.my_job.save(update_fields=["status"])
        handle_event("pull_request", _payload("reopened", MINE, 11, state="open"))
        self.assertEqual(self._statuses()[0], GithubFixJob.Status.MERGED)
