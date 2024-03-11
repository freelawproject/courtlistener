import datetime
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
            "cl.lib.es_signal_processor.allow_es_audio_indexing",
            side_effect=lambda x, y: True,
        ), cls.captureOnCommitCallbacks(execute=True):
            cls.audio = AudioWithParentsFactory.create(
                docket=DocketFactory(
                    court=cls.court_1, date_argued=datetime.date(2014, 8, 16)
                ),
                local_path_mp3__data=ONE_SECOND_MP3_BYTES,
                local_path_original_file__data=ONE_SECOND_MP3_BYTES,
                duration=1,
            )
            cls.audio_2 = AudioWithParentsFactory.create(
                docket=DocketFactory(
                    court=cls.court_1, date_argued=datetime.date(2016, 8, 17)
                ),
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

    async def test_do_jurisdiction_podcasts_have_good_content(self) -> None:
        """Can we simply load a jurisdiction podcast page?"""

        # Test jurisdiction_podcast for a court.
        response = await self.async_client.get(
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
        namespaces = {"atom": "http://www.w3.org/2005/Atom"}
        node_tests = (
            ("//channel/title", 1),
            ("//channel/link", 1),
            ("//channel/description", 1),
            ("//channel/item", 2),
            ("//channel/item/title", 2),
            ("//channel/item/enclosure/@url", 2),
        )
        xml_tree = self.assert_es_feed_content(
            node_tests, response, namespaces
        )

        # Confirm items are ordered by dateArgued desc
        pub_date_format = "%a, %d %b %Y %H:%M:%S %z"
        first_item_pub_date_str = str(
            xml_tree.xpath("//channel/item[1]/pubDate")[0].text  # type: ignore
        )
        second_item_pub_date_str = str(
            xml_tree.xpath("//channel/item[2]/pubDate")[0].text  # type: ignore
        )
        first_item_pub_date_dt = datetime.datetime.strptime(
            first_item_pub_date_str, pub_date_format
        )
        second_item_pub_date_dt = datetime.datetime.strptime(
            second_item_pub_date_str, pub_date_format
        )
        self.assertGreater(
            first_item_pub_date_dt,
            second_item_pub_date_dt,
            msg="The first item should be newer than the second item.",
        )

        # Test all_jurisdictions_podcast
        response = await self.async_client.get(
            reverse(
                "all_jurisdictions_podcast",
            )
        )
        self.assertEqual(
            200,
            response.status_code,
            msg="Did not get 200 OK status code for podcasts.",
        )
        namespaces = {"atom": "http://www.w3.org/2005/Atom"}
        node_tests = (
            ("//channel/title", 1),
            ("//channel/link", 1),
            ("//channel/description", 1),
            ("//channel/item", 3),
            ("//channel/item/title", 3),
            ("//channel/item/enclosure/@url", 3),
        )
        self.assert_es_feed_content(node_tests, response, namespaces)

    def test_do_search_podcasts_have_content(self) -> None:
        """Can we make a search podcast?

        Search podcasts are a subclass of the Jurisdiction podcasts, so a
        simple test is all that's needed here.
        """

        params = {
            "q": f"court_id:{self.audio.docket.court.pk}",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        response = self.client.get(
            reverse("search_podcast", args=["search"]),
            params,
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
        # pubDate key must be present in Audios with date_argued.
        pubdate_present = xml_tree.xpath(
            "count(//item[pubDate]) = count(//item)"
        )
        self.assertTrue(pubdate_present)

        # Confirm items are ordered by dateArgued desc
        pub_date_format = "%a, %d %b %Y %H:%M:%S %z"
        first_item_pub_date_str = str(
            xml_tree.xpath("//channel/item[1]/pubDate")[0].text  # type: ignore
        )
        second_item_pub_date_str = str(
            xml_tree.xpath("//channel/item[2]/pubDate")[0].text  # type: ignore
        )
        first_item_pub_date_dt = datetime.datetime.strptime(
            first_item_pub_date_str, pub_date_format
        )
        second_item_pub_date_dt = datetime.datetime.strptime(
            second_item_pub_date_str, pub_date_format
        )
        self.assertGreater(
            first_item_pub_date_dt,
            second_item_pub_date_dt,
            msg="The first item should be newer than the second item.",
        )

        # pubDate key must be omitted in Audios without date_argued.
        with self.captureOnCommitCallbacks(execute=True):
            self.audio.docket.date_argued = None
            self.audio.docket.save()
            self.audio_2.docket.date_argued = None
            self.audio_2.docket.save()
        response = self.client.get(
            reverse("search_podcast", args=["search"]),
            params,
        )
        self.assertEqual(
            200, response.status_code, msg="Did not get a 200 OK status code."
        )
        xml_tree = etree.fromstring(response.content)
        pubdate_not_present = xml_tree.xpath(
            "count(//item[not(pubDate)]) = count(//item)"
        )
        self.assertTrue(pubdate_not_present)

    def test_catch_es_errors(self) -> None:
        """Can we catch es errors and just render an empy podcast?"""

        # Bad syntax error.
        params = {
            "q": "Leave /:",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        response = self.client.get(
            reverse("search_podcast", args=["search"]),
            params,
        )
        self.assertEqual(
            400, response.status_code, msg="Did not get a 400 OK status code."
        )
        self.assertEqual(
            "Invalid search syntax. Please check your request and try again.",
            response.content.decode(),
        )

        # Unbalanced parentheses
        params = {
            "q": "(Leave ",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        response = self.client.get(
            reverse("search_podcast", args=["search"]),
            params,
        )
        self.assertEqual(
            400, response.status_code, msg="Did not get a 400 OK status code."
        )
        self.assertEqual(
            "Invalid search syntax. Please check your request and try again.",
            response.content.decode(),
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
