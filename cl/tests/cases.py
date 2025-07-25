from django import test
from django.contrib.staticfiles import testing
from django.core.management import call_command
from django_elasticsearch_dsl.registries import registry
from lxml import etree, html
from rest_framework.test import APITestCase as DRFTestCase

from cl.lib.redis_utils import get_redis_interface

from .mixins import RestartRateLimitMixin


class TestCase(
    RestartRateLimitMixin,
    test.TestCase,
):
    pass


class TransactionTestCase(
    RestartRateLimitMixin,
    test.TransactionTestCase,
):
    pass


class LiveServerTestCase(
    RestartRateLimitMixin,
    test.LiveServerTestCase,
):
    pass


class StaticLiveServerTestCase(
    RestartRateLimitMixin,
    testing.StaticLiveServerTestCase,
):
    pass


class APITestCase(
    RestartRateLimitMixin,
    DRFTestCase,
):
    pass


@test.override_settings(
    ELASTICSEARCH_DSL_AUTO_REFRESH=True,
    ELASTICSEARCH_DISABLED=False,
)
class ESIndexTransactionTestCase(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        _index_suffixe = cls.__name__.lower()
        for index in registry.get_indices():
            index._name += f"-{_index_suffixe}"
            index.create(ignore=400)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        for index in registry.get_indices():
            index.delete(ignore=[404, 400])
            index._name = index._name.split("-")[0]
        super().tearDownClass()

    def tearDown(self) -> None:
        self.restart_celery_throttle_key()
        super().tearDown()

    @classmethod
    def rebuild_index(cls, model):
        """Create and populate the Elasticsearch index and mapping"""
        call_command("search_index", "--rebuild", "-f", "--models", model)

    @classmethod
    def create_index(cls, model):
        """Create the elasticsearch index."""
        call_command("search_index", "--create", "-f", "--models", model)

    @classmethod
    def delete_index(cls, model):
        """Delete the elasticsearch index."""
        call_command("search_index", "--delete", "-f", "--models", model)

    @classmethod
    def restart_celery_throttle_key(cls):
        r = get_redis_interface("CACHE")
        keys = r.keys("celery_throttle:*")
        if keys:
            r.delete(*keys)
        keys = r.keys("celery_throttle:*")

    def assert_es_feed_content(self, node_tests, response, namespaces):
        """Common assertion that checks the presence of specified nodes in an
        ES feed test.

        :param node_tests: A list of tuples, each containing an XPath query
        string and the expected count of nodes.
        :param response: The HTTP response that contains XML content.
        :param namespaces: A dictionary of XML namespaces required to parse
        the XPath expressions.
        :return: A lxml etree object parsed from the response content.
        """
        xml_tree = etree.fromstring(response.content)
        for test_content, count in node_tests:
            with self.subTest(test_content=test_content):
                node_count = len(
                    xml_tree.xpath(test_content, namespaces=namespaces)
                )  # type: ignore
                self.assertEqual(
                    node_count,
                    count,
                    msg=f"Did not find {count} node(s) with XPath query: {test_content}. "
                    f"Instead found: {node_count}",
                )

        return xml_tree

    @staticmethod
    def _get_frontend_counts_text(r):
        """Extract and clean frontend counts text from the response content."""
        tree = html.fromstring(r.content.decode())
        counts_h2_element = tree.xpath('//h2[@id="result-count"]')[0]
        counts_text = " ".join(counts_h2_element.xpath(".//text()"))
        counts_text = counts_text.replace("&nbsp;", " ")
        counts_text = counts_text.split()
        return " ".join(counts_text)


class ESIndexTestCase(ESIndexTransactionTestCase, TestCase):
    pass
