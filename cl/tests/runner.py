import logging
import sys
import warnings
from unittest import TestLoader

from django.conf import settings
from django.test.runner import DiscoverRunner
from override_storage import override_storage

from cl.tests.cases import (
    APITestCase,
    LiveServerTestCase,
    SimpleTestCase,
    StaticLiveServerTestCase,
    TestCase,
    TransactionTestCase,
)


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

    def setup_databases(self, *args, **kwargs):
        # Force to always delete the database if it exists
        interactive = self.interactive
        self.interactive = False

        try:
            if self.keepdb:
                # --keepdb doesn't really work. See Django bug #25251:
                # https://code.djangoproject.com/ticket/25251. In addition to
                # TransactionTestCases, it appears TestCases can also delete
                # migration data. To resolve that, this modifies the test
                # runner to never run against the actual test database if we're
                # trying to keep it. Instead, always run against a clone that
                # gets destroyed at the end of testing.

                # Because we don't want to run through migrations twice,
                # we use the normal process to create the actual test database, then
                # manually clone it and the parallel clones.
                parallel = self.parallel
                self.parallel = 1
                old_config = super().setup_databases(*args, **kwargs)
                self.parallel = parallel
                # Create the clones ourselves
                for c in (x for x, y, z in old_config if z):
                    # Create test_database_clone and replace the real test database.
                    db_clone_name = c.settings_dict["NAME"] + "_clone"
                    with self.time_keeper.timed(f"  Cloning '{c.alias}'"):
                        c.creation.clone_test_db(
                            "clone", verbosity=self.verbosity
                        )
                    settings.DATABASES[c.alias]["NAME"] = db_clone_name
                    c.settings_dict["NAME"] = db_clone_name
                    # Create parallel clones.
                    if parallel > 1:
                        for index in range(1, self.parallel + 1):
                            with self.time_keeper.timed(
                                f"  Cloning '{c.alias}'"
                            ):
                                c.creation.clone_test_db(
                                    str(index), verbosity=self.verbosity
                                )
                return old_config
            else:
                return super().setup_databases(*args, **kwargs)
        finally:
            self.interactive = interactive

    def teardown_databases(self, *args, **kwargs):
        keepdb = self.keepdb
        # Always delete the cloned DBs.
        self.keepdb = False
        super().teardown_databases(*args, **kwargs)
        self.keebdb = keepdb

    @override_storage()
    def run_tests(self, *args, **kwargs):
        # Show all warnings once, especially to show DeprecationWarning
        # messages which Python ignores by default
        warnings.simplefilter("default")

        # Disable logs for small performance boost.
        if not self.enable_logging:
            logging.disable()

        return super().run_tests(*args, **kwargs)
