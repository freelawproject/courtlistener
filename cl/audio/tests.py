from unittest import mock

from django.urls import reverse
from lxml import etree

from cl.audio.factories import AudioWithParentsFactory
from cl.lib.test_helpers import SitemapTest
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.models import SEARCH_TYPES
from cl.tests.cases import ESIndexTestCase, TestCase
from cl.tests.fixtures import ONE_SECOND_MP3_BYTES, SMALL_WAV_BYTES


class PodcastTest(ESIndexTestCase, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.court_1 = CourtFactory(
            id="ca9",
            full_name="Court of Appeals for the Ninth Circuit",
            jurisdiction="F",
            citation_string="Appeals. CA9.",
        )
        cls.court_2 = CourtFactory(
            id="ca8",
            full_name="Court of Appeals for the Eighth Circuit",
            jurisdiction="F",
            citation_string="Appeals. CA8.",
        )
        with mock.patch(
            "cl.search.tasks.abort_es_audio_indexing",
            side_effect=lambda x, y, z: False,
        ):
            cls.audio = AudioWithParentsFactory.create(
                docket=DocketFactory(court=cls.court_1),
                local_path_mp3__data=ONE_SECOND_MP3_BYTES,
                local_path_original_file__data=ONE_SECOND_MP3_BYTES,
                duration=1,
            )
            AudioWithParentsFactory.create(
                docket=cls.audio.docket,
                local_path_mp3__data=SMALL_WAV_BYTES,
                local_path_original_file__data=SMALL_WAV_BYTES,
                duration=0,
            )
            AudioWithParentsFactory.create(
                docket=DocketFactory(court=cls.court_2),
                local_path_mp3__data=SMALL_WAV_BYTES,
                local_path_original_file__data=SMALL_WAV_BYTES,
                duration=5,
            )

    def test_do_jurisdiction_podcasts_have_good_content(self) -> None:
        """Can we simply load a jurisdiction podcast page?"""

        # Test jurisdiction_podcast for a court.
        response = self.client.get(
            reverse(
                "jurisdiction_podcast",
                kwargs={"court": self.court_1.id},
            )
        )
        self.assertEqual(
            200,
            response.status_code,
            msg="Did not get 200 OK status code for podcasts.",
        )
        xml_tree = etree.fromstring(response.content)
        node_tests = (
            ("//channel/title", 1),
            ("//channel/link", 1),
            ("//channel/description", 1),
            ("//channel/item", 2),
            ("//channel/item/title", 2),
            ("//channel/item/enclosure/@url", 2),
        )
        for test, count in node_tests:
            node_count = len(xml_tree.xpath(test))  # type: ignore
            self.assertEqual(
                node_count,
                count,
                msg="Did not find %s node(s) with XPath query: %s. "
                "Instead found: %s" % (count, test, node_count),
            )

        # Test all_jurisdictions_podcast
        response = self.client.get(
            reverse(
                "all_jurisdictions_podcast",
            )
        )
        self.assertEqual(
            200,
            response.status_code,
            msg="Did not get 200 OK status code for podcasts.",
        )
        xml_tree = etree.fromstring(response.content)
        node_tests = (
            ("//channel/title", 1),
            ("//channel/link", 1),
            ("//channel/description", 1),
            ("//channel/item", 3),
            ("//channel/item/title", 3),
            ("//channel/item/enclosure/@url", 3),
        )
        for test, count in node_tests:
            node_count = len(xml_tree.xpath(test))  # type: ignore
            self.assertEqual(
                node_count,
                count,
                msg="Did not find %s node(s) with XPath query: %s. "
                "Instead found: %s" % (count, test, node_count),
            )

    def test_do_search_podcasts_have_content(self) -> None:
        """Can we make a search podcast?

        Search podcasts are a subclass of the Jurisdiction podcasts, so a
        simple test is all that's needed here.
        """
        response = self.client.get(
            reverse("search_podcast", args=["search"]),
            {
                "q": f"court_id:{self.audio.docket.court.pk}",
                "type": SEARCH_TYPES.ORAL_ARGUMENT,
            },
        )
        self.assertEqual(
            200, response.status_code, msg="Did not get a 200 OK status code."
        )
        xml_tree = etree.fromstring(response.content)
        node_count = len(xml_tree.xpath("//channel/item"))  # type: ignore

        expected_item_count = 2
        self.assertEqual(
            node_count,
            expected_item_count,
            msg="Did not get {expected} node(s) during search podcast "
            "generation. Instead found: {actual}".format(
                expected=expected_item_count, actual=node_count
            ),
        )


class AudioSitemapTest(SitemapTest):
    @classmethod
    def setUpTestData(cls) -> None:
        AudioWithParentsFactory.create(
            local_path_mp3__data=ONE_SECOND_MP3_BYTES,
            local_path_original_file__data=ONE_SECOND_MP3_BYTES,
            duration=1,
            blocked=True,
        )
        AudioWithParentsFactory.create(
            local_path_mp3__data=ONE_SECOND_MP3_BYTES,
            local_path_original_file__data=ONE_SECOND_MP3_BYTES,
            duration=1,
            blocked=False,
        )

    def setUp(self) -> None:
        self.expected_item_count = 1
        self.sitemap_url = reverse(
            "sitemaps", kwargs={"section": SEARCH_TYPES.ORAL_ARGUMENT}
        )

    def test_does_the_sitemap_have_content(self) -> None:
        super().assert_sitemap_has_content()
