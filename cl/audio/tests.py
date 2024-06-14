import datetime
import os
from math import ceil
from unittest import mock

import openai
from django.urls import reverse
from factory.django import FileField
from lxml import etree

from cl.audio.factories import AudioFactory, AudioWithParentsFactory
from cl.audio.management.commands.transcribe import (
    audio_can_be_processed_by_open_ai_api,
    transcribe_from_open_ai_api,
)
from cl.audio.models import Audio, AudioTranscriptionMetadata
from cl.lib.test_helpers import SitemapTest
from cl.search.factories import CourtFactory, DocketFactory
from cl.search.models import SEARCH_TYPES
from cl.tests.cases import ESIndexTestCase, TestCase
from cl.tests.fixtures import ONE_SECOND_MP3_BYTES, SMALL_WAV_BYTES
from cl.tests.utils import MockResponse


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


class TranscriptionTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.court_1 = CourtFactory(
            id="ca9",
            full_name="Court of Appeals for the Ninth Circuit",
            jurisdiction="F",
            citation_string="Appeals. CA9.",
        )

        cls.audio_without_local_path_mp3 = AudioFactory.create(
            docket=DocketFactory(
                court=cls.court_1, date_argued=datetime.date(2014, 8, 16)
            ),
            local_path_mp3=None,
            duration=1,
            stt_status=Audio.STT_NEEDED,
        )
        cls.audio_bigger_than_limit_duration = AudioFactory.create(
            docket=DocketFactory(
                court=cls.court_1, date_argued=datetime.date(2014, 8, 15)
            ),
            local_path_mp3=FileField(data=b"\x10" * 26_000_000),
            duration=4000,
            stt_status=Audio.STT_NEEDED,
        )
        cls.audio_1 = AudioFactory.create(
            docket=DocketFactory(
                court=cls.court_1, date_argued=datetime.date(2014, 8, 14)
            ),
            duration=2000,
            stt_status=Audio.STT_NEEDED,
        )
        cls.audio_to_be_retried = AudioFactory.create(
            docket=DocketFactory(
                court=cls.court_1, date_argued=datetime.date(2014, 8, 13)
            ),
            duration=1000,
            stt_status=Audio.STT_FAILED,
        )

        cls.open_ai_api_returned_dict = {
            "text": "Good morning, Camille Fenton, Federal Defenders, on behalf of Mr. Campos.",
            "task": "transcribe",
            "language": "english",
            "duration": 6.15,
            "segments": [
                {
                    "id": 0,
                    "end": 6.159999847412109,
                    "seek": 0,
                    "text": "Good morning, Camille Fenton, Federal Defenders, on behalf of Mr. Campos.",
                    "start": 1.5399999618530273,
                    "tokens": [
                        50364,
                        2205,
                        2446,
                        11,
                        6886,
                        3409,
                        479,
                        317,
                        266,
                        11,
                        12380,
                        9548,
                        16292,
                        11,
                        322,
                        9490,
                        295,
                        2221,
                        13,
                        9189,
                        329,
                        13,
                        50652,
                    ],
                    "avg_logprob": -0.2830151319503784,
                    "temperature": 0.0,
                    "no_speech_prob": 0.02627764642238617,
                    "compression_ratio": 1.4403291940689087,
                },
            ],
            "words": [
                {
                    "end": 2.059999942779541,
                    "word": "Good",
                    "start": 1.5399999618530273,
                },
                {
                    "end": 2.299999952316284,
                    "word": "morning",
                    "start": 2.059999942779541,
                },
                {
                    "end": 2.6600000858306885,
                    "word": "Camille",
                    "start": 2.4200000762939453,
                },
                {
                    "end": 2.9800000190734863,
                    "word": "Fenton",
                    "start": 2.6600000858306885,
                },
                {
                    "end": 3.380000114440918,
                    "word": "Federal",
                    "start": 3.140000104904175,
                },
                {
                    "end": 3.759999990463257,
                    "word": "Defenders",
                    "start": 3.380000114440918,
                },
                {
                    "end": 4.159999847412109,
                    "word": "on",
                    "start": 3.9000000953674316,
                },
                {
                    "end": 4.380000114440918,
                    "word": "behalf",
                    "start": 4.159999847412109,
                },
                {
                    "end": 4.539999961853027,
                    "word": "of",
                    "start": 4.380000114440918,
                },
                {
                    "end": 4.800000190734863,
                    "word": "Mr",
                    "start": 4.539999961853027,
                },
                {
                    "end": 5.320000171661377,
                    "word": "Campos",
                    "start": 5.059999942779541,
                },
            ],
        }

        class OpenAITranscription:
            def to_dict(self):
                return cls.open_ai_api_returned_dict

        cls.OpenAITranscriptionClass = OpenAITranscription

    def test_audio_file_validation(self) -> None:
        """Can we validate audio files existance and size for OpenAI API use?"""
        self.assertFalse(
            audio_can_be_processed_by_open_ai_api(
                self.audio_without_local_path_mp3,
            ),
            "Audio object without local_path_mp3 passed as valid",
        )
        self.assertFalse(
            audio_can_be_processed_by_open_ai_api(
                self.audio_bigger_than_limit_duration
            ),
            "Longer than allowed audio file passed as valid",
        )

        self.assertTrue(
            audio_can_be_processed_by_open_ai_api(self.audio_1),
            "Valid audio file was skipped",
        )
        self.assertTrue(
            audio_can_be_processed_by_open_ai_api(self.audio_to_be_retried),
            "Valid audio file was skipped",
        )

    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "123"}, clear=True)
    def test_successful_api_call(self) -> None:
        """Is Audio object updated and AudioTranscriptMetadata created correctly?"""
        audio = self.audio_1

        with mock.patch(
            "openai.resources.audio.transcriptions.Transcriptions.create"
        ) as patched_transcription:
            patched_transcription.return_value = (
                self.OpenAITranscriptionClass()
            )
            transcribe_from_open_ai_api(audio_pk=audio.pk)

        audio.refresh_from_db()
        self.assertEqual(
            audio.stt_status,
            Audio.STT_COMPLETE,
            "Audio.stt_status is not Audio.STT_COMPLETED",
        )
        self.assertEqual(
            audio.stt_source,
            Audio.STT_OPENAI_WHISPER,
            "Audio.stt_source is not Audio.STT_OPENAI_WHISPER",
        )

        transcription = self.open_ai_api_returned_dict
        self.assertEqual(
            audio.duration,
            ceil(transcription["duration"]),
            "Audio.duration was not updated",
        )
        self.assertEqual(
            audio.stt_transcript,
            transcription["text"],
            "Audio.stt_transcript was not updated",
        )
        queryset = AudioTranscriptionMetadata.objects.filter(audio=audio)
        self.assertTrue(
            queryset.exists(),
            "AudioTranscriptionMetadata was not created",
        )
        metadata = queryset[0]
        self.assertEqual(
            metadata.metadata["words"][0]["word"],
            transcription["words"][0]["word"],
            "AudioTranscriptionMetadata[words][0] not as expected",
        )
        self.assertEqual(
            metadata.metadata["segments"][0]["text"],
            transcription["segments"][0]["text"],
            "AudioTranscriptionMetadata[segments][0] not as expected",
        )

    @mock.patch.dict(os.environ, {"OPENAI_API_KEY": "123"}, clear=True)
    def test_failure_status_update(self) -> None:
        """Is Audio.stt_status updated correctly on failure?"""
        audio = self.audio_1

        with mock.patch(
            "openai.resources.audio.transcriptions.Transcriptions.create"
        ) as patched_transcription:
            mock_response = MockResponse(422, content="")
            setattr(mock_response, "request", {})
            setattr(mock_response, "headers", {"x-request-id": "1"})
            patched_transcription.side_effect = (
                openai.UnprocessableEntityError(
                    message="Test OpenAI API UnprocessableEntityError",
                    response=mock_response,
                    body="",
                )
            )
            transcribe_from_open_ai_api(audio_pk=audio.pk)

        audio.refresh_from_db()
        self.assertEqual(
            audio.stt_status,
            Audio.STT_FAILED,
            "Audio.stt_status is not Audio.STT_FAILED",
        )
