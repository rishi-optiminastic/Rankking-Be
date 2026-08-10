"""The public outreach-benchmark endpoints.

The contract that matters most is the gate. This endpoint has no login by
design, and every successful POST spends LLM credits, so "unset key" and "wrong
key" must both refuse — otherwise finding the URL is the same as finding the
budget.
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.analyzer.models import AnalysisRun, PromptResult, PromptTrack
from apps.analyzer.services import outreach_benchmark as ob

KEY = "test-outreach-key"
_TASK = "apps.analyzer.views.outreach.queue"


@override_settings(OUTREACH_BENCHMARK_KEY=KEY)
class OutreachCreateGateTests(TestCase):
    def _post(self, payload, key=KEY):
        headers = {"x-outreach-key": key} if key is not None else {}
        return self.client.post(
            "/api/analyzer/outreach/", payload, content_type="application/json", headers=headers
        )

    def test_valid_key_starts_a_benchmark_run(self):
        with patch("core.queue.is_eager", return_value=False), patch("core.queue.send") as send:
            resp = self._post({"url": "https://example.com"})

        self.assertEqual(resp.status_code, 201, resp.content)
        run = AnalysisRun.objects.get(slug=resp.json()["slug"])
        self.assertEqual(run.run_type, AnalysisRun.RunType.OUTREACH)
        self.assertEqual(run.status, AnalysisRun.Status.PENDING)
        send.assert_called_once()

    def test_missing_key_is_refused_and_spends_nothing(self):
        with patch("core.queue.send") as send:
            resp = self._post({"url": "https://example.com"}, key=None)

        self.assertEqual(resp.status_code, 403)
        self.assertFalse(AnalysisRun.objects.exists())
        send.assert_not_called()

    def test_wrong_key_is_refused(self):
        resp = self._post({"url": "https://example.com"}, key="nope")
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(AnalysisRun.objects.exists())

    @override_settings(OUTREACH_BENCHMARK_KEY="")
    def test_unset_key_disables_generation_entirely(self):
        """The safe default: an environment that never opted in cannot be billed."""
        resp = self._post({"url": "https://example.com"}, key="")
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(AnalysisRun.objects.exists())

    def test_bare_domain_gets_a_scheme(self):
        with patch("core.queue.is_eager", return_value=False), patch("core.queue.send"):
            resp = self._post({"url": "acme.com"})

        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(AnalysisRun.objects.get().url, "https://acme.com")

    def test_private_address_is_rejected_by_the_ssrf_guard(self):
        resp = self._post({"url": "http://169.254.169.254/latest/meta-data/"})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(AnalysisRun.objects.exists())

    def test_missing_url_is_a_400(self):
        self.assertEqual(self._post({}).status_code, 400)

    def test_pinned_prompts_are_stored_for_the_run(self):
        with patch("core.queue.is_eager", return_value=False), patch("core.queue.send"):
            self._post({"url": "https://acme.com", "prompts": ["best MGA platforms", "  "]})

        self.assertEqual(AnalysisRun.objects.get().onboarding_prompts, ["best MGA platforms"])


@override_settings(OUTREACH_BENCHMARK_KEY=KEY, OUTREACH_REUSE_HOURS=24)
class OutreachReuseTests(TestCase):
    """A finished benchmark is served back instead of buying an identical one.

    Each generation spends ~18 search-enabled answer-engine calls, and the
    endpoint is hand-driven, so a re-run of the same domain used to pay full
    price for a report that cannot have changed.
    """

    def _post(self, payload):
        return self.client.post(
            "/api/analyzer/outreach/",
            payload,
            content_type="application/json",
            headers={"x-outreach-key": KEY},
        )

    def _finished(self, url="https://acme.com", report=None):
        return AnalysisRun.objects.create(
            url=url,
            run_type=AnalysisRun.RunType.OUTREACH,
            status=AnalysisRun.Status.COMPLETE,
            outreach_report=({"prompts": [{"prompt": "best MGA platforms"}]} if report is None else report),
        )

    def test_recent_benchmark_is_reused_and_spends_nothing(self):
        done = self._finished()
        with patch("core.queue.is_eager", return_value=False), patch("core.queue.send") as send:
            resp = self._post({"url": "https://acme.com"})

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["slug"], done.slug)
        send.assert_not_called()
        self.assertEqual(AnalysisRun.objects.count(), 1)

    def test_reuse_matches_on_host_not_the_raw_string(self):
        done = self._finished("https://www.acme.com")
        with patch("core.queue.is_eager", return_value=False), patch("core.queue.send"):
            resp = self._post({"url": "acme.com"})

        self.assertEqual(resp.json()["slug"], done.slug)

    def test_force_bypasses_reuse(self):
        self._finished()
        with patch("core.queue.is_eager", return_value=False), patch("core.queue.send") as send:
            resp = self._post({"url": "https://acme.com", "force": True})

        self.assertEqual(resp.status_code, 201, resp.content)
        send.assert_called_once()
        self.assertEqual(AnalysisRun.objects.count(), 2)

    def test_pinned_prompts_ask_a_different_question_so_never_reuse(self):
        self._finished()
        with patch("core.queue.is_eager", return_value=False), patch("core.queue.send"):
            resp = self._post({"url": "https://acme.com", "prompts": ["best MGA platforms"]})

        self.assertEqual(resp.status_code, 201, resp.content)

    def test_a_pinned_prompt_report_is_never_served_to_an_unpinned_request(self):
        """It answers a narrower question than the caller asked."""
        pinned = self._finished()
        AnalysisRun.objects.filter(pk=pinned.pk).update(onboarding_prompts=["a narrow question"])

        with patch("core.queue.is_eager", return_value=False), patch("core.queue.send"):
            resp = self._post({"url": "https://acme.com"})

        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertNotEqual(resp.json()["slug"], pinned.slug)

    def test_a_different_domain_is_not_reused(self):
        self._finished("https://acme.com")
        with patch("core.queue.is_eager", return_value=False), patch("core.queue.send"):
            resp = self._post({"url": "https://other.com"})

        self.assertEqual(resp.status_code, 201, resp.content)

    def test_an_empty_report_is_never_reused(self):
        # The credit-exhaustion case: "complete" but nothing usable in it.
        self._finished(report={})
        with patch("core.queue.is_eager", return_value=False), patch("core.queue.send"):
            resp = self._post({"url": "https://acme.com"})

        self.assertEqual(resp.status_code, 201, resp.content)

    @override_settings(OUTREACH_REUSE_HOURS=0)
    def test_zero_window_disables_reuse(self):
        self._finished()
        with patch("core.queue.is_eager", return_value=False), patch("core.queue.send"):
            resp = self._post({"url": "https://acme.com"})

        self.assertEqual(resp.status_code, 201, resp.content)

    def test_a_benchmark_older_than_the_window_is_regenerated(self):
        done = self._finished()
        AnalysisRun.objects.filter(pk=done.pk).update(created_at=timezone.now() - timedelta(hours=25))
        with patch("core.queue.is_eager", return_value=False), patch("core.queue.send"):
            resp = self._post({"url": "https://acme.com"})

        self.assertEqual(resp.status_code, 201, resp.content)


@override_settings(
    # config.settings.test uses DummyCache so DRF throttle buckets cannot leak
    # between tests. A cache test needs a cache that actually stores, so this
    # class opts into an in-process one; setUp clears it per test.
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class AnswerEngineCacheTests(TestCase):
    """An identical buyer question is not bought twice.

    The engines are asked the question alone — the brand is matched against the
    reply, never sent — so the same question yields the same answer for every
    prospect. The cache must therefore change cost, never a number in the report.
    """

    ANSWER = {
        "gpt": {"text": "Try acme.com and rival.com", "citations": ["https://rival.com"], "model": "m"},
        "claude": {"text": "Try acme.com", "citations": [], "model": "m"},
    }
    ENGINES = ["chatgpt", "claude"]

    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def _fire(self, brand="Acme", url="https://acme.com"):
        from apps.analyzer.pipeline import prompt_tracker as pt

        return pt.fire_prompt_across_engines(
            "best MGA platforms", brand, url, runs=1, allowed_engines=self.ENGINES, cache_ttl=600
        )

    def test_second_identical_question_is_served_from_cache(self):
        from apps.analyzer.pipeline import prompt_tracker as pt

        with patch("core.llm.client.ask_answer_engines", return_value=self.ANSWER) as ask:
            first = self._fire()
            second = self._fire()

        ask.assert_called_once()  # paid for once, answered twice
        self.assertEqual([r["response_text"] for r in first], [r["response_text"] for r in second])

    def test_a_different_brand_reuses_the_answer_but_matches_itself(self):
        """The saving is cross-prospect, and each brand is still scored on its own."""
        from apps.analyzer.pipeline import prompt_tracker as pt

        with patch("core.llm.client.ask_answer_engines", return_value=self.ANSWER) as ask:
            acme = self._fire("Acme", "https://acme.com")
            rival = self._fire("Rival", "https://rival.com")

        ask.assert_called_once()
        self.assertTrue(any(r["brand_mentioned"] for r in acme))
        self.assertTrue(any(r["brand_mentioned"] for r in rival))

    def test_an_incomplete_answer_set_is_never_cached(self):
        """One transient engine failure must not read as "not cited" for a day."""
        from apps.analyzer.pipeline import prompt_tracker as pt

        partial = {**self.ANSWER, "claude": {"text": "", "citations": [], "model": "m"}}
        with patch("core.llm.client.ask_answer_engines", return_value=partial) as ask:
            self._fire()
            self._fire()

        self.assertEqual(ask.call_count, 2)

    def test_flipping_an_engines_search_mode_invalidates_its_answers(self):
        """Native vs Exa is a different retrieval path, so it is a different answer."""
        from apps.analyzer.pipeline import prompt_tracker as pt

        before = pt._answer_bundle_key("best MGA platforms", ["gpt", "claude"])
        with patch.dict(
            "core.llm.client.ANSWER_ENGINES",
            {"claude": {"model": "anthropic/claude-haiku-4.5", "search": "exa"}},
        ):
            after = pt._answer_bundle_key("best MGA platforms", ["gpt", "claude"])

        self.assertNotEqual(before, after)

    def test_a_multi_run_measurement_is_never_served_from_cache(self):
        """runs > 1 samples the engine repeatedly; a cache would collapse them."""
        from apps.analyzer.pipeline import prompt_tracker as pt

        with patch("core.llm.client.ask_answer_engines", return_value=self.ANSWER) as ask:
            for _ in range(2):
                pt.fire_prompt_across_engines(
                    "best MGA platforms",
                    "Acme",
                    "https://acme.com",
                    runs=2,
                    allowed_engines=self.ENGINES,
                    cache_ttl=600,
                )

        self.assertEqual(ask.call_count, 4)

    def test_ttl_zero_disables_the_cache(self):
        from apps.analyzer.pipeline import prompt_tracker as pt

        with patch("core.llm.client.ask_answer_engines", return_value=self.ANSWER) as ask:
            for _ in range(2):
                pt.fire_prompt_across_engines(
                    "best MGA platforms",
                    "Acme",
                    "https://acme.com",
                    runs=1,
                    allowed_engines=self.ENGINES,
                    cache_ttl=0,
                )

        self.assertEqual(ask.call_count, 2)


class OutreachSpendAccountingTests(TestCase):
    """A finished benchmark records what it spent.

    It previously recorded nothing: ``llm_cost_usd`` stayed 0.0 on every outreach
    run, so the spend never reached ``services.llm_spend`` and the budget fuse was
    blind to the one endpoint that spends LLM credits without a login.
    """

    LOGS = [
        {"model": "anthropic/claude-haiku-4.5", "purpose": "engine", "usage": {"cost": 0.0231}},
        {"model": "openai/gpt-4.1-mini", "purpose": "engine", "usage": {"cost": 0.0143}},
    ]

    def test_spend_is_recorded_through_the_real_log_collector(self):
        """No mocking of get_collected_logs — that is what hid the original bug.

        ``_log_call`` drops everything while the collector is unarmed, so a
        version that never calls ``start_log_collection()`` writes an empty
        ``llm_logs`` and records $0 while still passing a mocked test.
        """
        from core.llm import client as llm

        run = AnalysisRun.objects.create(url="https://acme.com", run_type=AnalysisRun.RunType.OUTREACH)
        crawl = SimpleNamespace(ok=True, url=run.url, soup=None, text="", error="")

        def _spend_one(*_a, **_kw):
            llm._log_call(
                model="anthropic/claude-haiku-4.5",
                purpose="engine",
                prompt="best MGA platforms",
                response="...",
                status="success",
                duration_ms=10,
                usage={"cost": 0.0231},
            )

        with (
            patch("apps.analyzer.pipeline.crawler.crawl_site", return_value=(crawl, {}, {})),
            patch.object(ob, "_brand_and_industry", return_value=("Acme", "insurance")),
            patch.object(ob, "_prompts_for", return_value=["best MGA platforms"]),
            patch.object(ob, "_measure", side_effect=_spend_one),
            patch.object(
                ob,
                "_findings",
                return_value={"prompts_measured": 1, "prompts_total": 1, "prompts_lost": 0},
            ),
            patch.object(ob, "_opportunities", return_value=[]),
        ):
            ob.run_outreach_benchmark(run.id)

        run.refresh_from_db()
        self.assertEqual(run.status, AnalysisRun.Status.COMPLETE)
        self.assertAlmostEqual(run.llm_cost_usd, 0.0231, places=4)

    def test_spend_is_recorded_even_when_the_benchmark_fails(self):
        """Measurement spends the money; a later crash must not erase the bill."""
        from core.llm import client as llm

        run = AnalysisRun.objects.create(url="https://acme.com", run_type=AnalysisRun.RunType.OUTREACH)
        crawl = SimpleNamespace(ok=True, url=run.url, soup=None, text="", error="")

        def _spend_then_die(*_a, **_kw):
            llm._log_call(
                model="anthropic/claude-haiku-4.5",
                purpose="engine",
                prompt="best MGA platforms",
                response="...",
                status="success",
                duration_ms=10,
                usage={"cost": 0.0143},
            )
            raise RuntimeError("engine exploded after billing")

        with (
            patch("apps.analyzer.pipeline.crawler.crawl_site", return_value=(crawl, {}, {})),
            patch.object(ob, "_brand_and_industry", return_value=("Acme", "insurance")),
            patch.object(ob, "_prompts_for", return_value=["best MGA platforms"]),
            patch.object(ob, "_measure", side_effect=_spend_then_die),
        ):
            ob.run_outreach_benchmark(run.id)

        run.refresh_from_db()
        self.assertEqual(run.status, AnalysisRun.Status.FAILED)
        self.assertAlmostEqual(run.llm_cost_usd, 0.0143, places=4)

    def test_completed_benchmark_records_its_llm_spend(self):
        run = AnalysisRun.objects.create(url="https://acme.com", run_type=AnalysisRun.RunType.OUTREACH)
        crawl = SimpleNamespace(ok=True, url=run.url, soup=None, text="", error="")

        with (
            patch("apps.analyzer.pipeline.crawler.crawl_site", return_value=(crawl, {}, {})),
            patch.object(ob, "_brand_and_industry", return_value=("Acme", "insurance")),
            patch.object(ob, "_prompts_for", return_value=["best MGA platforms"]),
            patch.object(ob, "_measure"),
            patch.object(
                ob,
                "_findings",
                return_value={"prompts_measured": 1, "prompts_total": 1, "prompts_lost": 0},
            ),
            patch.object(ob, "_opportunities", return_value=[]),
            patch("core.llm.client.get_collected_logs", return_value=self.LOGS),
        ):
            ob.run_outreach_benchmark(run.id)

        run.refresh_from_db()
        self.assertEqual(run.status, AnalysisRun.Status.COMPLETE)
        self.assertAlmostEqual(run.llm_cost_usd, 0.0374, places=4)
        self.assertEqual(len(run.llm_logs), 2)


class OutreachDetailTests(TestCase):
    def setUp(self):
        self.run = AnalysisRun.objects.create(
            url="https://acme.com",
            run_type=AnalysisRun.RunType.OUTREACH,
            status=AnalysisRun.Status.COMPLETE,
            progress=100,
            outreach_report={"prompts_total": 6, "opportunities": ["Do the thing."]},
        )

    def test_report_is_readable_without_a_key(self):
        """Reads stay open so a finished benchmark can be sent to the prospect."""
        resp = self.client.get(f"/api/analyzer/outreach/{self.run.slug}/")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["report"]["opportunities"], ["Do the thing."])

    def test_unknown_slug_is_404(self):
        self.assertEqual(self.client.get("/api/analyzer/outreach/nope/").status_code, 404)

    def test_non_outreach_run_is_not_exposed_here(self):
        other = AnalysisRun.objects.create(
            url="https://private.com", run_type=AnalysisRun.RunType.SINGLE_PAGE
        )
        self.assertEqual(self.client.get(f"/api/analyzer/outreach/{other.slug}/").status_code, 404)


class FindingsRollupTests(TestCase):
    """The numbers the email quotes, derived only from what was persisted."""

    def setUp(self):
        self.run = AnalysisRun.objects.create(url="https://acme.com", run_type=AnalysisRun.RunType.OUTREACH)

    def _track(self, text, engine_answers):
        track = PromptTrack.objects.create(analysis_run=self.run, prompt_text=text)
        for engine, (answered, mentioned) in engine_answers.items():
            PromptResult.objects.create(
                prompt_track=track,
                engine=engine,
                response_text="an answer" if answered else "",
                brand_mentioned=mentioned,
            )
        return track

    def test_lost_prompts_exclude_unmeasured_ones(self):
        """An engine failure must never be counted as a lost prompt."""
        self._track("won", {PromptResult.Engine.CHATGPT: (True, True)})
        self._track("lost", {PromptResult.Engine.CHATGPT: (True, False)})
        self._track("errored", {PromptResult.Engine.CHATGPT: (False, False)})

        findings = ob._findings(self.run)

        self.assertEqual(findings["prompts_total"], 3)
        self.assertEqual(findings["prompts_measured"], 2)
        self.assertEqual(findings["prompts_lost"], 1)

    def test_brand_and_industry_resolve_against_the_real_helpers(self):
        """Regression: these are imported lazily inside the function, so a wrong
        module path is invisible until a run is already crawling. It shipped once
        and failed live at 5% with an ImportError."""
        from bs4 import BeautifulSoup

        crawl = SimpleNamespace(
            soup=BeautifulSoup("<html><head><title>Acme Insurance</title></head></html>", "html.parser"),
            text="Acme sells policy administration software.",
            url="https://acme.com",
        )

        brand, industry = ob._brand_and_industry(crawl, self.run)

        self.assertTrue(brand)
        self.assertIsInstance(industry, str)

    def test_opportunities_are_skipped_when_nothing_was_measured(self):
        """No measurement means no grounded advice, so it must not invent any."""
        self._track("errored", {PromptResult.Engine.CHATGPT: (False, False)})

        findings = ob._findings(self.run)

        self.assertEqual(ob._opportunities("Acme", "saas", findings), [])
