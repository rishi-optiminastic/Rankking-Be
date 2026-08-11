"""An engine that never answered is not a measured miss.

``fire_prompt_across_engines`` persists a row for an engine that returned
nothing (API error, timeout, exhausted credits) with ``response_text=""`` and
``brand_mentioned=False``. Counting those made an engine OUTAGE render as a
confident "0% share of voice" — a fabricated finding. These pin the rule.
"""

from django.test import TestCase

from apps.analyzer.models import AnalysisRun, PromptResult, PromptTrack


class UnansweredEnginesTests(TestCase):
    def setUp(self):
        self.run = AnalysisRun.objects.create(url="https://acme.com", email="o@acme.com")
        self.track = PromptTrack.objects.create(analysis_run=self.run, prompt_text="best MGA platforms")

    def _result(self, engine: str, *, text: str, mentioned: bool):
        return PromptResult.objects.create(
            prompt_track=self.track,
            engine=engine,
            response_text=text,
            brand_mentioned=mentioned,
        )

    def _sov(self) -> dict:
        resp = self.client.get(f"/api/analyzer/runs/s/{self.run.slug}/share-of-voice/")
        self.assertEqual(resp.status_code, 200, resp.content)
        return {row["engine"]: row for row in resp.json()}

    def test_an_engine_that_never_answered_is_not_counted_as_a_miss(self):
        """The whole point: an outage must not read as 0% visibility."""
        self._result("chatgpt", text="", mentioned=False)

        row = self._sov()["chatgpt"]
        self.assertEqual(row["total"], 0)
        self.assertEqual(row["sov_pct"], 0.0)

    def test_a_real_miss_still_counts_against_share_of_voice(self):
        """An engine that answered without naming the brand IS a measured miss."""
        self._result("chatgpt", text="Try rival.com instead", mentioned=False)

        row = self._sov()["chatgpt"]
        self.assertEqual(row["total"], 1)
        self.assertEqual(row["sov_pct"], 0.0)

    def test_failures_do_not_dilute_a_real_score(self):
        """One answer naming the brand + one outage is 100%, not 50%."""
        self._result("chatgpt", text="acme.com is the best option", mentioned=True)
        self._result("chatgpt", text="", mentioned=False)

        row = self._sov()["chatgpt"]
        self.assertEqual(row["total"], 1)
        self.assertEqual(row["mentioned"], 1)
        self.assertEqual(row["sov_pct"], 100.0)

    def test_the_recommendation_summary_applies_the_same_rule(self):
        self._result("chatgpt", text="acme.com is great", mentioned=True)
        self._result("gemini", text="", mentioned=False)

        resp = self.client.get(f"/api/analyzer/runs/s/{self.run.slug}/ai-recommendation-summary/")
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["mention_pct"], 100.0)
