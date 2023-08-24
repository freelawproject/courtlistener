from datetime import datetime
from unittest import mock

from django.urls import reverse
from lxml import etree

from cl.audio.factories import AudioWithParentsFactory
from cl.audio.models import Audio
from cl.lib.test_helpers import IndexedSolrTestCase, SitemapTest
from cl.search.models import SEARCH_TYPES
from cl.tests.fixtures import ONE_SECOND_MP3_BYTES, SMALL_WAV_BYTES


class PodcastTest(IndexedSolrTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.audio = AudioWithParentsFactory.create(
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

    def test_do_jurisdiction_podcasts_have_good_content(self) -> None:
        """Can we simply load a jurisdiction podcast page?"""
        response = self.client.get(
            reverse(
                "jurisdiction_podcast",
                kwargs={"court": self.audio.docket.court.id},
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
