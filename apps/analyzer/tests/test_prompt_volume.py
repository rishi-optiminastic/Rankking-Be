"""Search-volume enrichment for tracked prompts.

Two things carry real risk here and are what these tests pin: the cost controls
(a term must never be bought twice inside the TTL) and the null-vs-zero
distinction the dashboard depends on to tell "not looked up" from "nobody
searches this".
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.analyzer.models import AnalysisRun, PromptTrack
from apps.analyzer.services.prompt_volume import VOLUME_TTL, backfill_run_volumes
from apps.integrations.services.dataforseo import (
    DataForSEOError,
    fetch_search_volume,
    is_volume_eligible,
)

SERVICE = "apps.analyzer.services.prompt_volume.fetch_search_volume"


class EligibilityTests(TestCase):
    """Google Ads rejects long terms, so they must be filtered before the call."""

    def test_a_short_prompt_is_eligible(self):
        self.assertTrue(is_volume_eligible("best crm for startups"))

    def test_a_prompt_over_80_characters_is_rejected(self):
        self.assertFalse(is_volume_eligible("a" * 81))

    def test_a_prompt_over_ten_words_is_rejected(self):
        # 11 short words: under the character cap, over the word cap.
        self.assertFalse(is_volume_eligible(" ".join(["ab"] * 11)))

    def test_blank_is_rejected(self):
        self.assertFalse(is_volume_eligible("   "))


class FetchSearchVolumeTests(TestCase):
    def test_ineligible_terms_are_never_sent(self):
        with patch("apps.integrations.services.dataforseo._post") as post:
            out = fetch_search_volume(["a" * 200])
        post.assert_not_called()
        self.assertEqual(out, {})

    def test_it_parses_rows_from_the_result_list(self):
        body = {
            "tasks": [
                {"result": [{"keyword": "best crm", "search_volume": 4400}]},
            ]
        }
        with patch("apps.integrations.services.dataforseo._post", return_value=body):
            out = fetch_search_volume(["Best CRM"])
        # Normalized to lowercase so callers can match on the prompt text.
        self.assertEqual(out, {"best crm": 4400})

    def test_a_null_search_volume_reads_as_zero(self):
        body = {"tasks": [{"result": [{"keyword": "best crm", "search_volume": None}]}]}
        with patch("apps.integrations.services.dataforseo._post", return_value=body):
            out = fetch_search_volume(["best crm"])
        self.assertEqual(out["best crm"], 0)


class BackfillTests(TestCase):
    def setUp(self):
        self.run = AnalysisRun.objects.create(url="https://acme.com", email="a@acme.com")

    def _prompt(self, text, run=None, **kw):
        return PromptTrack.objects.create(analysis_run=run or self.run, prompt_text=text, **kw)

    def test_it_stores_the_fetched_volume(self):
        self._prompt("best crm")
        with patch(SERVICE, return_value={"best crm": 4400}) as fetch:
            updated = backfill_run_volumes(self.run.id)
        self.assertEqual(updated, 1)
        fetch.assert_called_once()
        self.assertEqual(PromptTrack.objects.get().search_volume, 4400)

    def test_an_eligible_term_with_no_data_is_a_real_zero(self):
        """Google answering "nothing" is a measurement, not a missing value."""
        self._prompt("best crm")
        with patch(SERVICE, return_value={}):
            backfill_run_volumes(self.run.id)
        prompt = PromptTrack.objects.get()
        self.assertEqual(prompt.search_volume, 0)
        self.assertIsNotNone(prompt.search_volume_checked_at)

    def test_an_ineligible_term_stays_null_but_is_marked_checked(self):
        """Never asked, so no number — but it must not be retried every run."""
        self._prompt("a" * 200)
        with patch(SERVICE, return_value={}):
            backfill_run_volumes(self.run.id)
        prompt = PromptTrack.objects.get()
        self.assertIsNone(prompt.search_volume)
        self.assertIsNotNone(prompt.search_volume_checked_at)

    def test_a_recently_checked_prompt_is_not_re_fetched(self):
        self._prompt("best crm", search_volume=4400, search_volume_checked_at=timezone.now())
        with patch(SERVICE) as fetch:
            updated = backfill_run_volumes(self.run.id)
        self.assertEqual(updated, 0)
        fetch.assert_not_called()

    def test_a_stale_prompt_is_re_fetched(self):
        self._prompt(
            "best crm",
            search_volume=4400,
            search_volume_checked_at=timezone.now() - VOLUME_TTL - timedelta(days=1),
        )
        with patch(SERVICE, return_value={"best crm": 5000}) as fetch:
            backfill_run_volumes(self.run.id)
        fetch.assert_called_once()
        self.assertEqual(PromptTrack.objects.get().search_volume, 5000)

    def test_a_term_priced_on_another_run_is_reused_not_rebought(self):
        """The cost control: the same prompt across brands must bill once."""
        other = AnalysisRun.objects.create(url="https://other.com", email="b@other.com")
        self._prompt(
            "best crm",
            run=other,
            search_volume=4400,
            search_volume_checked_at=timezone.now(),
        )
        self._prompt("best crm")

        with patch(SERVICE) as fetch:
            backfill_run_volumes(self.run.id)

        fetch.assert_not_called()
        mine = PromptTrack.objects.get(analysis_run=self.run)
        self.assertEqual(mine.search_volume, 4400)

    def test_an_upstream_failure_leaves_the_run_intact(self):
        """Enrichment must degrade, never raise into the analysis that owns it."""
        self._prompt("best crm")
        with patch(SERVICE, side_effect=DataForSEOError("402 out of credits")):
            updated = backfill_run_volumes(self.run.id)
        self.assertEqual(updated, 0)

    def test_an_outage_is_not_recorded_as_zero_demand(self):
        """An unanswered lookup is missing data, not a measurement of nothing.

        Writing 0 here would be indistinguishable from a term Google really has
        no volume for, and the row would never be retried.
        """
        self._prompt("best crm")
        with patch(SERVICE, side_effect=DataForSEOError("402 out of credits")):
            backfill_run_volumes(self.run.id)

        prompt = PromptTrack.objects.get()
        self.assertIsNone(prompt.search_volume)
        self.assertIsNone(prompt.search_volume_checked_at)

        # ...and the next run, with the endpoint healthy again, fills it in.
        with patch(SERVICE, return_value={"best crm": 4400}):
            backfill_run_volumes(self.run.id)
        self.assertEqual(PromptTrack.objects.get().search_volume, 4400)

    def test_deleted_prompts_are_skipped(self):
        self._prompt("best crm", deleted_at=timezone.now())
        with patch(SERVICE) as fetch:
            updated = backfill_run_volumes(self.run.id)
        self.assertEqual(updated, 0)
        fetch.assert_not_called()
