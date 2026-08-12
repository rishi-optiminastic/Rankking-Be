"""Tracked prompts, and their history, must survive a re-analysis.

A tracked prompt is a measurement series: the same question asked run after run
so visibility can be compared over time. The pipeline used to create a brand-new
PromptTrack every run, so each re-analysis both changed the ten questions AND
started their history over — every prompt sat at 0% with no trend behind it.

The fix re-points the brand's existing rows at the new run (a move, not a copy),
so the primary key, the original created_at and every past PromptResult survive.
These tests pin that, and the plan-limit rule that goes with it: re-measuring
prompts you already own is never capped; the cap governs NEW prompts only.
"""

from django.test import TestCase
from django.utils import timezone

from apps.analyzer.models import AnalysisRun, PromptResult, PromptTrack
from apps.analyzer.tasks.analysis import _adopt_brand_prompts, _brand_runs

PROMPTS = [
    "How to audit my website's visibility in generative AI platforms?",
    "How can I ensure AI models accurately cite my website?",
    "Strategies to increase my brand's presence in AI-powered search?",
]


class AdoptionTests(TestCase):
    def setUp(self):
        self.old = AnalysisRun.objects.create(url="https://signalor.ai", email="a@signalor.ai")
        self.new = AnalysisRun.objects.create(url="https://signalor.ai", email="a@signalor.ai")

    def _track(self, run, text, **kw):
        return PromptTrack.objects.create(analysis_run=run, prompt_text=text, **kw)

    def test_a_re_analysis_adopts_the_brand_s_prompts(self):
        for text in PROMPTS:
            self._track(self.old, text)
        adopted = _adopt_brand_prompts(self.new, 10)
        self.assertEqual(sorted(t.prompt_text for t in adopted.values()), sorted(PROMPTS))

    def test_adoption_is_a_move_so_the_row_and_its_history_survive(self):
        """The heart of it: same primary key, same results, new run."""
        track = self._track(self.old, PROMPTS[0])
        PromptResult.objects.create(prompt_track=track, engine="chatgpt", brand_mentioned=True)
        original_pk, original_created = track.pk, track.created_at

        adopted = _adopt_brand_prompts(self.new, 10)
        moved = adopted[PROMPTS[0].lower()]

        self.assertEqual(moved.pk, original_pk)
        self.assertEqual(moved.created_at, original_created)
        moved.refresh_from_db()
        self.assertEqual(moved.analysis_run_id, self.new.pk)
        self.assertEqual(moved.results.count(), 1, "past results must survive the re-analysis")

    def test_no_duplicate_row_is_left_behind(self):
        """One question, one row — for ever. Duplicates split the history."""
        self._track(self.old, PROMPTS[0])
        _adopt_brand_prompts(self.new, 10)
        self.assertEqual(PromptTrack.objects.filter(prompt_text=PROMPTS[0]).count(), 1)

    def test_pre_existing_duplicates_collapse_to_one(self):
        """Rows the OLD behaviour already created must not all be adopted."""
        mid = AnalysisRun.objects.create(url="https://signalor.ai", email="a@signalor.ai")
        self._track(self.old, PROMPTS[0])
        self._track(mid, PROMPTS[0].upper())
        self.assertEqual(len(_adopt_brand_prompts(self.new, 10)), 1)

    def test_the_first_ever_analysis_adopts_nothing(self):
        self.assertEqual(_adopt_brand_prompts(self.old, 10), {})

    def test_a_deleted_prompt_is_not_resurrected(self):
        self._track(self.old, PROMPTS[0])
        self._track(self.old, PROMPTS[1], deleted_at=timezone.now())
        adopted = _adopt_brand_prompts(self.new, 10)
        self.assertEqual([t.prompt_text for t in adopted.values()], [PROMPTS[0]])

    def test_custom_prompts_the_user_added_survive(self):
        self._track(self.old, "my own question about pricing", is_custom=True)
        adopted = _adopt_brand_prompts(self.new, 10)
        self.assertIn("my own question about pricing", [t.prompt_text for t in adopted.values()])

    def test_another_brand_s_prompts_are_never_borrowed(self):
        other = AnalysisRun.objects.create(url="https://kaizan.ai", email="b@kaizan.ai")
        self._track(other, "a kaizan-only question")
        self._track(self.old, PROMPTS[0])
        adopted = _adopt_brand_prompts(self.new, 10)
        self.assertEqual([t.prompt_text for t in adopted.values()], [PROMPTS[0]])

    def test_the_limit_is_respected(self):
        for text in PROMPTS:
            self._track(self.old, text)
        self.assertEqual(len(_adopt_brand_prompts(self.new, 2)), 2)

    def test_it_stays_stable_and_keeps_accumulating_across_many_runs(self):
        """The user-visible promise, end to end."""
        for text in PROMPTS:
            track = self._track(self.old, text)
            PromptResult.objects.create(prompt_track=track, engine="chatgpt")

        expected = sorted(PROMPTS)
        for run_number in range(2, 5):
            nxt = AnalysisRun.objects.create(url="https://signalor.ai", email="a@signalor.ai")
            adopted = _adopt_brand_prompts(nxt, 10)
            self.assertEqual(sorted(t.prompt_text for t in adopted.values()), expected)
            for track in adopted.values():
                PromptResult.objects.create(prompt_track=track, engine="chatgpt")
            # History grows by one run's answers each time — it never resets.
            for track in adopted.values():
                self.assertEqual(track.results.count(), run_number)

        self.assertEqual(PromptTrack.objects.count(), len(PROMPTS))


class BrandScopeTests(TestCase):
    def test_outreach_benchmarks_are_never_a_source(self):
        """A prospect report's prompts must not join a customer's tracked set."""
        outreach = AnalysisRun.objects.create(
            url="https://signalor.ai",
            email="a@signalor.ai",
            run_type=AnalysisRun.RunType.OUTREACH,
        )
        PromptTrack.objects.create(analysis_run=outreach, prompt_text="a prospect question")
        run = AnalysisRun.objects.create(url="https://signalor.ai", email="a@signalor.ai")
        self.assertEqual(_adopt_brand_prompts(run, 10), {})

    def test_an_anonymous_run_has_no_brand_to_adopt_from(self):
        run = AnalysisRun.objects.create(url="https://signalor.ai", email="")
        self.assertIsNone(_brand_runs(run))

    def test_organization_scope_wins_over_email(self):
        from apps.organizations.models import Organization

        org = Organization.objects.create(name="Signalor", url="https://signalor.ai")
        old = AnalysisRun.objects.create(url="https://signalor.ai", email="a@signalor.ai", organization=org)
        PromptTrack.objects.create(analysis_run=old, prompt_text=PROMPTS[0])

        # A teammate re-running it keeps the same tracked set.
        new = AnalysisRun.objects.create(
            url="https://signalor.ai", email="teammate@signalor.ai", organization=org
        )
        adopted = _adopt_brand_prompts(new, 10)
        self.assertEqual([t.prompt_text for t in adopted.values()], [PROMPTS[0]])
