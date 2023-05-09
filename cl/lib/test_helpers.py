from typing import Sized, cast

import scorched
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.test.testcases import SerializeMixin
from django.test.utils import override_settings
from lxml import etree

from cl.audio.factories import AudioFactory
from cl.audio.models import Audio
from cl.people_db.factories import PersonFactory
from cl.people_db.models import Person
from cl.search.models import Court, Opinion
from cl.search.tasks import add_items_to_solr
from cl.tests.cases import TestCase
from cl.users.factories import UserProfileWithParentsFactory


class SerializeSolrTestMixin(SerializeMixin):
    lockfile = __file__


class SimpleUserDataMixin:
    @classmethod
    def setUpTestData(cls) -> None:
        UserProfileWithParentsFactory.create(
            user__username="pandora",
            user__password=make_password("password"),
        )
        super().setUpTestData()  # type: ignore


@override_settings(
    SOLR_OPINION_URL=settings.SOLR_OPINION_TEST_URL,
    SOLR_AUDIO_URL=settings.SOLR_AUDIO_TEST_URL,
    SOLR_PEOPLE_URL=settings.SOLR_PEOPLE_TEST_URL,
    SOLR_RECAP_URL=settings.SOLR_RECAP_TEST_URL,
    SOLR_URLS=settings.SOLR_TEST_URLS,
)
class EmptySolrTestCase(SerializeSolrTestMixin, TestCase):
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


class SolrTestCase(SimpleUserDataMixin, EmptySolrTestCase):
    """A standard Solr test case with content included in the database,  but not
    yet indexed into the database.
    """

    fixtures = [
        "test_court.json",
        "judge_judy.json",
        "test_objects_search.json",
    ]

    @classmethod
    def setUpTestData(cls):
        cls.author = PersonFactory.create()
        cls.audio_1 = AudioFactory.create(
            case_name="SEC v. Frank J. Custable, Jr.",
            docket_id=1,
            duration=420,
            judges="",
        )
        cls.audio_2 = AudioFactory.create(
            case_name="Jose A. Dominguez v. Loretta E. Lynch",
            docket_id=2,
            duration=837,
            judges="",
        )
        cls.audio_3 = AudioFactory.create(
            case_name="Hong Liu Yang v. Lynch-Loretta E.",
            docket_id=3,
            duration=653,
            judges="",
        )
        cls.audio_4 = AudioFactory.create(
            case_name="Hong Liu Lorem v. Lynch-Loretta E.",
            docket_id=3,
            duration=653,
            judges="John Smith",
        )
        cls.audio_4.panel.add(cls.author)

    def setUp(self) -> None:
        # Set up some handy variables
        super(SolrTestCase, self).setUp()

        self.court = Court.objects.get(pk="test")
        self.expected_num_results_opinion = 6
        self.expected_num_results_audio = 2


class IndexedElasticTestCase(SimpleUserDataMixin, TestCase):
    """A standard Solr test case with content included in the database,  but not
    yet indexed into the database.
    """

    fixtures = [
        "test_court.json",
        "judge_judy.json",
        "test_objects_search.json",
    ]

    @classmethod
    def setUpTestData(cls):
        cls.author = PersonFactory.create()
        cls.audio_1 = AudioFactory.create(
            case_name="SEC v. Frank J. Custable, Jr.",
            docket_id=1,
            duration=420,
            judges="",
        )
        cls.audio_2 = AudioFactory.create(
            case_name="Jose A. Dominguez v. Loretta E. Lynch",
            docket_id=2,
            duration=837,
            judges="",
        )
        cls.audio_3 = AudioFactory.create(
            case_name="Hong Liu Yang v. Lynch-Loretta E.",
            docket_id=3,
            duration=653,
            judges="",
        )
        cls.audio_4 = AudioFactory.create(
            case_name="Hong Liu Lorem v. Lynch-Loretta E.",
            docket_id=3,
            duration=653,
            judges="John Smith",
        )
        cls.audio_4.panel.add(cls.author)

    def rebuild_index(self):
        """
        Create and populate the Elasticsearch index and mapping
        """

        # -f rebuilds index without prompt for confirmation
        call_command("search_index", "--rebuild", "-f")

    def setUp(self) -> None:
        self.rebuild_index()


class IndexedSolrTestCase(SolrTestCase):
    """Similar to the SolrTestCase, but the data is indexed in Solr"""

    def setUp(self) -> None:
        super(IndexedSolrTestCase, self).setUp()
        obj_types = {
            "audio.Audio": Audio,
            "search.Opinion": Opinion,
            "people_db.Person": Person,
        }
        for obj_name, obj_type in obj_types.items():
            if obj_name == "people_db.Person":
                items = obj_type.objects.filter(is_alias_of=None)
                ids = [item.pk for item in items if item.is_judge]
            else:
                ids = obj_type.objects.all().values_list("pk", flat=True)
            add_items_to_solr(ids, obj_name, force_commit=True)


class SitemapTest(TestCase):
    sitemap_url: str
    expected_item_count: int

    def assert_sitemap_has_content(self) -> None:
        """Does content get into the sitemap?"""
        response = self.client.get(self.sitemap_url)
        self.assertEqual(
            200, response.status_code, msg="Did not get a 200 OK status code."
        )
        xml_tree = etree.fromstring(response.content)
        node_count = len(
            cast(
                Sized,
                xml_tree.xpath(
                    "//s:url",
                    namespaces={
                        "s": "http://www.sitemaps.org/schemas/sitemap/0.9"
                    },
                ),
            )
        )
        self.assertGreater(
            self.expected_item_count,
            0,
            msg="Didn't get any content in test case.",
        )
        self.assertEqual(
            node_count,
            self.expected_item_count,
            msg="Did not get the right number of items in the sitemap.\n"
            f"\tCounted:\t{node_count}\n"
            f"\tExpected:\t{self.expected_item_count}",
        )
