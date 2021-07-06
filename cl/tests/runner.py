import logging
import os
import sys
import warnings
from unittest import TestLoader

from django.test.runner import DiscoverRunner

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
                f"{testCaseClass.__module__}.{testCaseClass.__name__} does not"
                + " inherit from an cl.tests.cases TestCase class. Be sure to "
                "use those test case classes for your tests.",
                file=sys.stderr,
            )
            sys.exit(1)
        return super().loadTestsFromTestCase(testCaseClass)


class TestRunner(DiscoverRunner):
    test_loader = OurCasesTestLoader()

    def __init__(self, *args, enable_logging, exclude_tags=None, **kwargs):
        on_ci = os.environ.get("GITHUB_ACTIONS", "") == "true"

        # Exclude certain tests unless somebody is using the exclude_tags
        # argument explicitly or we are on CI.
        if exclude_tags is None and not on_ci:
            exclude_tags = ["selenium", "slow"]
        super().__init__(*args, exclude_tags=exclude_tags, **kwargs)
        self.enable_logging = enable_logging

    @classmethod
    def add_arguments(self, parser):
        # Only log things if the --enable-logging flag is provided.
        parser.add_argument(
            "--enable-logging",
            action="store_true",
            default=False,
            help="Actually edit the database",
        )
        super().add_arguments(parser)

        # Modify parallel option to default to number of CPU cores
        # Find the action as already created in super(), and change its
        # 'default' (1) to its 'const' (the number of CPU cores)
        parallel_action = next(
            a for a in parser._optionals._actions if a.dest == "parallel"
        )
        parallel_action.default = parallel_action.const

    def setup_databases(self, **kwargs):
        # Force to always delete the database if it exists
        interactive = self.interactive
        self.interactive = False
        try:
            return super().setup_databases(**kwargs)
        finally:
            self.interactive = interactive

    def run_tests(self, *args, **kwargs):
        # Show all warnings once, especially to show DeprecationWarning
        # messages which Python ignores by default
        warnings.simplefilter("default")

        # Disable logs for small performance boost.
        if not self.enable_logging:
            logging.disable()

        return super().run_tests(*args, **kwargs)
