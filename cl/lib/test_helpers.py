import os

import scorched
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.test.utils import override_settings
from lxml import etree

from cl.search.models import Court


@override_settings(
    SOLR_OPINION_URL=settings.SOLR_OPINION_TEST_URL,
    SOLR_AUDIO_URL=settings.SOLR_AUDIO_TEST_URL,
    SOLR_PEOPLE_URL=settings.SOLR_PEOPLE_TEST_URL,
    SOLR_RECAP_URL=settings.SOLR_RECAP_TEST_URL,
    SOLR_URLS=settings.SOLR_TEST_URLS,
)
class EmptySolrTestCase(TestCase):
    """Sets up an empty Solr index for tests that need to set up data manually.

    Other Solr test classes subclass this one, adding additional content or
    features.
    """

    def setUp(self) -> None:
        # Set up testing cores in Solr and swap them in
        self.core_name_opinion = settings.SOLR_OPINION_TEST_CORE_NAME
        self.core_name_audio = settings.SOLR_AUDIO_TEST_CORE_NAME
        self.core_name_people = settings.SOLR_PEOPLE_TEST_CORE_NAME
        self.core_name_recap = settings.SOLR_RECAP_TEST_CORE_NAME

        self.si_opinion = scorched.SolrInterface(
            settings.SOLR_OPINION_URL, mode="rw"
        )
        self.si_audio = scorched.SolrInterface(
            settings.SOLR_AUDIO_URL, mode="rw"
        )
        self.si_people = scorched.SolrInterface(
            settings.SOLR_PEOPLE_URL, mode="rw"
        )
        self.si_recap = scorched.SolrInterface(
            settings.SOLR_RECAP_URL, mode="rw"
        )
        self.all_sis = [
            self.si_opinion,
            self.si_audio,
            self.si_people,
            self.si_recap,
        ]

    def tearDown(self) -> None:
        for si in self.all_sis:
            si.delete_all()
            si.commit()
            si.conn.http_connection.close()


class SolrTestCase(EmptySolrTestCase):
    """A standard Solr test case with content included in the database,  but not
    yet indexed into the database.
    """

    fixtures = [
        "test_court.json",
        "judge_judy.json",
        "test_objects_search.json",
        "test_objects_audio.json",
        "authtest_data.json",
    ]

    def setUp(self) -> None:
        # Set up some handy variables
        super(SolrTestCase, self).setUp()

        self.court = Court.objects.get(pk="test")
        self.expected_num_results_opinion = 6
        self.expected_num_results_audio = 2


class IndexedSolrTestCase(SolrTestCase):
    """Similar to the SolrTestCase, but the data is indexed in Solr"""

    def setUp(self):
        super(IndexedSolrTestCase, self).setUp()
        cores = {
            "audio.Audio": self.core_name_audio,
            "search.Opinion": self.core_name_opinion,
            "people_db.Person": self.core_name_people,
        }
        for obj_type, core_name in cores.items():
            args = [
                "--type",
                obj_type,
                "--solr-url",
                "%s/solr/%s" % (settings.SOLR_HOST, core_name),
                "--update",
                "--everything",
                "--do-commit",
                "--noinput",
            ]
            call_command("cl_update_index", *args)


class SitemapTest(TestCase):
    def __init__(self, *args, **kwargs) -> None:
        super(SitemapTest, self).__init__(*args, **kwargs)
        self.item_qs = None
        self.sitemap_url = None

    def assert_sitemap_has_content(self) -> None:
        """Does content get into the sitemap?"""
        response = self.client.get(self.sitemap_url)
        self.assertEqual(
            200, response.status_code, msg="Did not get a 200 OK status code."
        )
        xml_tree = etree.fromstring(response.content)
        node_count = len(
            xml_tree.xpath(
                "//s:url",
                namespaces={
                    "s": "http://www.sitemaps.org/schemas/sitemap/0.9"
                },
            )
        )
        expected_item_count = self.item_qs.count()
        self.assertEqual(
            node_count,
            expected_item_count,
            msg="Did not get the right number of items in the sitemap.\n"
            "\tCounted:\t%s\n"
            "\tExpected:\t%s" % (node_count, expected_item_count),
        )
