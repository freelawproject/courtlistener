import logging
import sys
import warnings
from typing import Any
from unittest import TestCase as UnitTestCase
from unittest import TestLoader

from django.test import SimpleTestCase
from django.test.runner import DiscoverRunner
from override_storage import override_storage
from xmlrunner import XMLTestRunner
from xmlrunner.result import _TestInfo, _XMLTestResult

from cl.tests.cases import (
    APITestCase,
    LiveServerTestCase,
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


class DurationAwareTestInfo(_TestInfo):
    """A ``_TestInfo`` that prefers the runner-measured test duration."""

    def test_finished(self) -> None:
        """Finalize timing, overriding xmlrunner's with the measured value."""
        super().test_finished()
        if (elapsed := self.test_result.duration) is not None:
            self.elapsed_time = elapsed


class DurationAwareXMLTestResult(_XMLTestResult):
    """An ``_XMLTestResult`` that writes real per-test times to the XML."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.infoclass = DurationAwareTestInfo
        self.duration: float | None = None

    def addDuration(self, test: UnitTestCase, elapsed: float) -> None:
        """Stash the measured duration of the test that just ran.

        ``addDuration()`` always arrives before the matching ``stopTest()``,
        which is what makes a single slot enough to hold it.
        """
        super().addDuration(test, elapsed)
        self.duration = elapsed

    def stopTest(self, test: UnitTestCase) -> None:
        """Finalize the test, then drop its duration."""
        super().stopTest(test)
        self.duration = None


class TestRunner(DiscoverRunner):
    test_loader = OurCasesTestLoader()

    def __init__(self, *args, enable_logging, xml_output=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.enable_logging = enable_logging
        self.xml_output = xml_output
        if xml_output:
            # Shadow DiscoverRunner.test_runner for this instance only, so
            # run_suite() builds an XMLTestRunner. Leaving the class attribute
            # alone keeps the default text runner for everyone else.
            self.test_runner = XMLTestRunner

    @classmethod
    def add_arguments(cls, parser):
        # Only log things if the --enable-logging flag is provided.
        parser.add_argument(
            "--enable-logging",
            action="store_true",
            default=False,
            help="Display all log lines",
        )
        parser.add_argument(
            "--xml-output",
            default=None,
            help="Directory to write JUnit XML test results to",
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

    def get_test_runner_kwargs(self) -> dict[str, Any]:
        """Build the kwargs for the test runner.

        Adds XMLTestRunner's ``output`` directory and the result class that
        gives the report real per-test times when ``--xml-output`` was passed;
        otherwise returns Django's defaults untouched.

        ``--debug-sql`` and ``--pdb`` pick their own result class, which
        cannot write XML. Those win, so combining either with ``--xml-output``
        fails loudly rather than quietly producing untimed reports.
        """
        kwargs = super().get_test_runner_kwargs()
        if self.xml_output:
            kwargs["output"] = self.xml_output
            if kwargs.get("resultclass") is None:
                kwargs["resultclass"] = DurationAwareXMLTestResult
        return kwargs

    def setup_databases(self, **kwargs):
        # Force to always delete the database if it exists
        interactive = self.interactive
        self.interactive = False
        try:
            return super().setup_databases(**kwargs)
        finally:
            self.interactive = interactive

    @override_storage()
    def run_tests(self, *args, **kwargs):
        # Show all warnings once, especially to show DeprecationWarning
        # messages which Python ignores by default
        warnings.simplefilter("default")

        # Disable logs for small performance boost.
        if not self.enable_logging:
            logging.disable()

        return super().run_tests(*args, **kwargs)
