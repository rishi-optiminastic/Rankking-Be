"""Every queued task name is actually reachable on a worker.

This exists because of a real production failure (Sentry SIGNALOR-K /
SIGNALOR-J). ``workers/analysis/tasks.py`` imported its models relatively —
``from .models import AnalysisRun`` — which resolves to ``workers.analysis.models``,
a module that has never existed. The import sits INSIDE the task body, so
nothing failed at deploy or at worker boot: every analysis run was accepted onto
the queue, then died with ModuleNotFoundError the moment a worker touched it.
The dashboard just showed runs that never finished.

Nothing in the suite caught it. The task bodies are only executed by a Celery
worker, which no test starts, and the dispatcher deliberately sends by NAME
(core/queue/dispatch) so not even the publisher imports them.

Two properties are pinned here:

1. Every worker task module imports cleanly, executing its module-level code.
2. Every name the app dispatches is registered on the app that owns its broker —
   a task published to a name no worker registers is silently never run.
"""

import importlib

from django.test import SimpleTestCase

# Modules Celery is told to import (config/celery.py and config/celery_rabbit.py
# `conf.imports`). Workers live outside apps/, so autodiscovery cannot see them
# and these are the only thing that binds them to a worker.
WORKER_TASK_MODULES = [
    "workers.analysis.tasks",
    "workers.crawling.tasks",
]

# task name -> the celery app expected to own it.
EXPECTED_TASKS = {
    "analyzer.run_analysis": "analysis",
    "analyzer.run_scheduled_analysis": "analysis",
    "analyzer.run_outreach_benchmark": "analysis",
    "analyzer.run_sitemap_audit": "default",
}


class WorkerTaskImportTests(SimpleTestCase):
    def test_every_worker_task_module_imports(self):
        """A bad import here means the task dies on the worker, not at deploy."""
        for name in WORKER_TASK_MODULES:
            with self.subTest(module=name):
                importlib.import_module(name)

    def test_task_bodies_have_no_unresolvable_imports(self):
        """The original bug hid in a function-level import, so compile isn't enough.

        Imports inside a task body are not executed until the task runs. Resolve
        each one here so a module that has never existed fails in CI instead of
        on a worker, mid-run.
        """
        import ast
        import pathlib

        for module_name in WORKER_TASK_MODULES:
            module = importlib.import_module(module_name)
            source = pathlib.Path(module.__file__).read_text()
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or not node.module:
                    continue
                # Resolve relative imports against the module's own package.
                target = node.module
                if node.level:
                    package = module_name.rsplit(".", node.level)[0]
                    target = f"{package}.{node.module}" if package else node.module
                with self.subTest(module=module_name, imports=target):
                    importlib.import_module(target)

    def test_every_dispatched_task_name_is_registered_on_its_broker(self):
        """A name no worker registers is a job that queues and never runs."""
        from config.celery import app as default_app
        from config.celery_rabbit import analysis_app

        for module_name in WORKER_TASK_MODULES:
            importlib.import_module(module_name)

        apps = {"analysis": analysis_app, "default": default_app}
        for task_name, broker in EXPECTED_TASKS.items():
            with self.subTest(task=task_name, broker=broker):
                self.assertIn(task_name, apps[broker].tasks)
