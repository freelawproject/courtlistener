import sys
from io import StringIO
from unittest import mock

from django import test
from django.contrib.staticfiles import testing
from django.core.management import call_command
from rest_framework.test import APITestCase

from cl.lib.redis_utils import make_redis_interface
from cl.search.es_indices import es_indices_registered


class OutputBlockerTestMixin:
    """Block the output of tests so that they run a bit faster.

    This is pulled from Speed Up Your Django Tests, Chapter, 4.9 "Prevent
    Output". In Django 3.2, this should be easier via a new --buffer argument.
    """

    def _callTestMethod(self, method):
        try:
            out = StringIO()
            err = StringIO()
            with mock.patch.object(sys, "stdout", new=out), mock.patch.object(
                sys, "stderr", new=err
            ):
                super()._callTestMethod(method)
        except Exception:
            print(out.getvalue(), end="")
            print(err.getvalue(), end="", file=sys.stderr)
            raise


class OneDatabaseMixin:
    """Only use one DB during tests

    If you have more than one DB in your settings, which we sometimes do,
    Django creates transactions for each DB and each test. This takes time.

    Since we don't have multi-DB features/tests, simply ensure that all our
    tests use only one DB, the default one.
    """

    databases = {"default"}


class RestartSentEmailQuotaMixin:
    """Restart sent email quota in redis."""

    @classmethod
    def restart_sent_email_quota(self):
        r = make_redis_interface("CACHE")
        keys = r.keys("email:*")

        if keys:
            r.delete(*keys)

    def tearDown(self):
        self.restart_sent_email_quota()
        super().tearDown()


class SimpleTestCase(
    OutputBlockerTestMixin,
    OneDatabaseMixin,
    test.SimpleTestCase,
):
    pass


class TestCase(
    OutputBlockerTestMixin,
    OneDatabaseMixin,
    test.TestCase,
):
    pass


class TransactionTestCase(
    OutputBlockerTestMixin,
    OneDatabaseMixin,
    test.TransactionTestCase,
):
    pass


class LiveServerTestCase(
    OutputBlockerTestMixin,
    OneDatabaseMixin,
    test.LiveServerTestCase,
):
    pass


class StaticLiveServerTestCase(
    OutputBlockerTestMixin,
    OneDatabaseMixin,
    testing.StaticLiveServerTestCase,
):
    pass


class APITestCase(
    OutputBlockerTestMixin,
    OneDatabaseMixin,
    APITestCase,
):
    pass


@test.override_settings(ELASTICSEARCH_DSL_AUTO_REFRESH=True)
class ESIndexTestCase(SimpleTestCase):
    """Common Django Elasticsearch DSL index commands, useful in testing."""

    @classmethod
    def setUpClass(cls):
        # Create a unique index name for all indices registered in es_indices.
        # So each test class get an isolated index from each other.
        for index_registered in es_indices_registered:
            index_registered._name = cls.__name__.lower()
        super().setUpClass()

    @classmethod
    def rebuild_index(self, model):
        """Create and populate the Elasticsearch index and mapping"""
        call_command("search_index", "--rebuild", "-f", "--models", model)

    @classmethod
    def create_index(self, model):
        """Create the elasticsearch index."""
        call_command("search_index", "--create", "-f", "--models", model)

    @classmethod
    def delete_index(self, model):
        """Delete the elasticsearch index."""
        call_command("search_index", "--delete", "-f", "--models", model)
