import logging
import sys
import warnings
from unittest import TestLoader

from django.test import SimpleTestCase
from django.test.runner import DiscoverRunner
from override_storage import override_storage

from cl.tests.cases import (
    APITestCase,
    LiveServerTestCase,
    StaticLiveServerTestCase,
    TestCase,
    TransactionTestCase,
)


def restore_migration_seed_data() -> None:
    """Re-create the data-migration seed if a reused ``--keepdb`` database had
    it flushed away by a prior run's ``TransactionTestCase``/selenium classes.

    The seed consists of the courts loaded by
    ``cl/search/migrations/0002_load_initial_data.py`` and the ``recap`` /
    ``recap-email`` system users created by
    ``cl/users/migrations/0002_load_initial_data.py``. This is idempotent: on a
    freshly-built database the seed is already present and nothing changes.
    """
    from django.apps import apps as global_apps
    from django.contrib.auth.models import User
    from django.core.management import call_command

    from cl.lib.migration_utils import make_new_user
    from cl.search.models import Court

    # loaddata upserts by primary key, so reloading the same truncated fixture
    # the migration uses restores the seed courts with their exact fields.
    if not Court.objects.filter(pk="scotus").exists():
        call_command("loaddata", "court_data_truncated", verbosity=0)

    seed_users = (
        ("recap", "recap@free.law", ["has_recap_upload_access"]),
        (
            "recap-email",
            "recap-email@free.law",
            ["has_recap_email_upload_access"],
        ),
    )
    for username, email, permission_codenames in seed_users:
        if not User.objects.filter(username=username).exists():
            make_new_user(
                global_apps, None, username, email, permission_codenames
            )


def reset_elasticsearch_state() -> None:
    """Reset Elasticsearch so a test run does not inherit index state left in
    the shared cluster by a previous run.

    Elasticsearch is external to the database, so neither ``--keepdb`` nor the
    test-database teardown clears it. Across runs this lets stale documents,
    percolator queries, and leftover per-class indices accumulate, which makes
    some ES tests pass or fail depending on what an earlier run (or a crashed
    ``setUpClass``) left behind. Recreating every registered index empty and
    dropping leftover per-class indices gives each run an identical clean slate.
    """
    from django_elasticsearch_dsl.registries import registry
    from elasticsearch.dsl import connections

    client = connections.get_connection()

    base_names = []
    for index in registry.get_indices():
        # Undo any in-process index-name mutation left by a partial prior run
        # (ESIndexTestCase appends a "-<classname>" suffix and resets it in
        # tearDownClass; a crashed setUpClass can leave it appended).
        index._name = index._name.split("-")[0]
        base_names.append(index._name)

    # Drop leftover per-class test indices ("<base>-<classname>...").
    for base in base_names:
        try:
            leftovers = list(
                client.indices.get(
                    index=f"{base}-*", ignore_unavailable=True
                ).keys()
            )
        except Exception:
            leftovers = []
        for name in leftovers:
            client.options(ignore_status=[400, 404]).indices.delete(index=name)

    # Recreate each base index empty so accumulated docs/percolator queries are
    # cleared.
    for index in registry.get_indices():
        index.delete(ignore=[404, 400])
        index.create(ignore=[400])


class OurCasesTestLoader(TestLoader):
    allowed_test_case_classes = (
        SimpleTestCase,
        TestCase,
        TransactionTestCase,
        LiveServerTestCase,
        StaticLiveServerTestCase,
        APITestCase,
    )

    def loadTestsFromTestCase(self, testCaseClass):
        if not issubclass(testCaseClass, self.allowed_test_case_classes):
            print(
                f"{testCaseClass.__module__}.{testCaseClass.__name__} does"
                " not inherit from an cl.tests.cases TestCase class. Be"
                " sure to use those test case classes for your tests.",
                file=sys.stderr,
            )
            sys.exit(1)
        return super().loadTestsFromTestCase(testCaseClass)


class TestRunner(DiscoverRunner):
    test_loader = OurCasesTestLoader()

    def __init__(self, *args, enable_logging, **kwargs):
        super().__init__(*args, **kwargs)
        self.enable_logging = enable_logging

    @classmethod
    def add_arguments(cls, parser):
        # Only log things if the --enable-logging flag is provided.
        parser.add_argument(
            "--enable-logging",
            action="store_true",
            default=False,
            help="Display all log lines",
        )
        super().add_arguments(parser)

        # Modify parallel option to default to number of CPU cores
        # Find the action as already created in super(), and change its
        # 'default' (1) to its 'const' (the number of CPU cores)
        parallel_action = next(
            a for a in parser._optionals._actions if a.dest == "parallel"
        )
        parallel_action.default = parallel_action.const

        # Default buffering on, to hide output
        # This is disabled due to Django bug #36491.
        # See PR #5888 for more details.
        # parser.set_defaults(buffer=True)

    def setup_databases(self, **kwargs):
        # Force to always delete the database if it exists
        interactive = self.interactive
        self.interactive = False
        try:
            result = super().setup_databases(**kwargs)
        finally:
            self.interactive = interactive
        # TransactionTestCase/selenium classes flush (truncate) the database
        # between tests, which also deletes data loaded by data migrations
        # (the seed courts in search/0002 and the recap/recap-email system
        # users in users/0002). When the database is reused with --keepdb, the
        # previous run's trailing flushes leave it without that seed data, so
        # the next run's tests fail with Court/User DoesNotExist. Restore the
        # migration seed here so a run does not depend on the state left behind
        # by a prior run. This is idempotent: on a freshly-built database the
        # seed is already present and nothing changes.
        restore_migration_seed_data()
        reset_elasticsearch_state()
        return result

    @override_storage()
    def run_tests(self, *args, **kwargs):
        # Show all warnings once, especially to show DeprecationWarning
        # messages which Python ignores by default
        warnings.simplefilter("default")

        # Disable logs for small performance boost.
        if not self.enable_logging:
            logging.disable()

        return super().run_tests(*args, **kwargs)
