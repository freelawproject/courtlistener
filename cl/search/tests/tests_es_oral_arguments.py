import datetime
import math
from unittest import mock

import time_machine
from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now
from elasticsearch_dsl import connections
from lxml import html
from waffle.testutils import override_flag

from cl.alerts.models import Alert
from cl.alerts.utils import percolate_document
from cl.audio.factories import AudioFactory
from cl.audio.models import Audio
from cl.lib.elasticsearch_utils import (
    build_es_base_query,
    build_es_main_query,
    fetch_es_results,
)
from cl.lib.test_helpers import (
    AudioESTestCase,
    audio_v3_fields,
    audio_v4_fields,
    skip_if_common_tests_skipped,
    v4_meta_keys,
)
from cl.search.documents import AudioDocument, AudioPercolator
from cl.search.factories import CourtFactory, DocketFactory, PersonFactory
from cl.search.models import SEARCH_TYPES, Docket
from cl.search.tasks import es_save_document, update_es_document
from cl.tests.cases import (
    CountESTasksTestCase,
    ESIndexTestCase,
    TestCase,
    TransactionTestCase,
    V4SearchAPIAssertions,
)


class OASearchAPICommonTests(AudioESTestCase):
    version_api = "v3"
    skip_common_tests = True

    async def _test_api_results_count(
        self, params, expected_count, field_name
    ):
        """Get the result count in a API query response"""
        r = await self.async_client.get(
            reverse("search-list", kwargs={"version": "v3"}), params
        )
        got = len(r.data["results"])
        self.assertEqual(
            got,
            expected_count,
            msg="Did not get the right number of search results in API with %s "
            "filter applied.\n"
            "Expected: %s\n"
            "     Got: %s\n\n"
            "Params were: %s" % (field_name, expected_count, got, params),
        )
        return r

    @skip_if_common_tests_skipped
    async def test_oa_results_basic(self) -> None:
        # API
        r = await self._test_api_results_count(
            {"type": SEARCH_TYPES.ORAL_ARGUMENT}, 5, "match_all"
        )
        self.assertIn("Jose", r.content.decode())

    @skip_if_common_tests_skipped
    async def test_oa_results_date_argued_ordering(self) -> None:
        # Order by dateArgued desc
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "dateArgued desc",
        }
        # API
        r = await self._test_api_results_count(search_params, 5, "match_all")
        self.assertTrue(
            r.content.decode().index("SEC") < r.content.decode().index("Jose"),
            msg="'SEC' should come BEFORE 'Jose' when order_by desc.",
        )

        # Order by dateArgued asc
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "dateArgued asc",
        }
        # API
        r = await self._test_api_results_count(search_params, 5, "match_all")
        self.assertTrue(
            r.content.decode().index("Jose") < r.content.decode().index("SEC"),
            msg="'Jose' should come AFTER 'SEC' when order_by asc.",
        )

    @skip_if_common_tests_skipped
    async def test_oa_results_relevance_ordering(self) -> None:
        # Relevance order, single word match.
        search_params = {
            "q": "Loretta",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # API
        r = await self._test_api_results_count(
            search_params, 3, "Query String"
        )
        self.assertTrue(
            r.content.decode().index("Jose")
            > r.content.decode().index("Hong Liu"),
            msg="'Jose' should come AFTER 'Hong Liu' when order_by relevance.",
        )

    @skip_if_common_tests_skipped
    async def test_oa_results_search_in_text(self) -> None:
        # Text query search by docket number
        search_params = {
            "q": f"{self.docket_3.docket_number}",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # API
        r = await self._test_api_results_count(
            search_params, 2, "docket_number"
        )
        self.assertTrue(
            r.content.decode().index("Lorem")
            < r.content.decode().index("Yang"),
            msg="'Lorem' should come BEFORE 'Yang' when order_by relevance.",
        )

    @skip_if_common_tests_skipped
    async def test_oa_case_name_filtering(self) -> None:
        """Filter by case_name"""
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "case_name": "jose",
        }
        # API
        r = await self._test_api_results_count(search_params, 1, "case_name")

    @skip_if_common_tests_skipped
    async def test_oa_docket_number_filtering(self) -> None:
        """Filter by docket number"""
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "docket_number": f"{self.docket_1.docket_number}",
        }
        # API
        r = await self._test_api_results_count(
            search_params, 1, "docket_number"
        )
        self.assertIn("SEC", r.content.decode())

    @skip_if_common_tests_skipped
    async def test_oa_jurisdiction_filtering(self) -> None:
        """Filter by court"""
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "court": f"{self.docket_3.court_id}",
        }
        # API
        r = await self._test_api_results_count(search_params, 2, "court")

    @skip_if_common_tests_skipped
    async def test_oa_date_argued_filtering(self) -> None:
        """Filter by date_argued"""
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "argued_after": "2015-08-16",
        }
        # API
        r = await self._test_api_results_count(
            search_params, 1, "argued_after"
        )
        self.assertIn(
            "SEC v. Frank J. Information, WikiLeaks",
            r.content.decode(),
            msg="Did not get the expected oral argument.",
        )

    @skip_if_common_tests_skipped
    async def test_oa_combine_search_and_filtering(self) -> None:
        """Test combine text query and filtering"""
        # Text query filtered by case_name
        search_params = {
            "q": "Loretta",
            "case_name": "Hong Liu",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }

        # API
        r = await self._test_api_results_count(
            search_params, 2, "case_name + query"
        )

        # Text query filtered by case_name and judge
        search_params = {
            "q": "Loretta",
            "case_name": "Hong Liu",
            "judge": "John Smith",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        # API
        r = await self._test_api_results_count(
            search_params, 1, "case_name + judge + query"
        )

        # Text query filtered by argued_after. Notice that out of two audios
        # argued_after 2015-08-15, only one is selected by the query string,
        # which only matches one of them. Thus, this query tests that
        # minimum_should_match = 1 is properly added when combining a query
        # string with a filter.
        search_params = {
            "q": "Frank",
            "argued_after": "2015-08-15",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        # API
        r = await self._test_api_results_count(
            search_params, 1, "case_name + judge + query"
        )

    @skip_if_common_tests_skipped
    async def test_oa_advanced_search_and_query(self) -> None:
        # AND query
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "Loretta AND judge:John Smith",
        }

        # API
        r = await self._test_api_results_count(
            search_params, 1, "advance query string"
        )
        self.assertIn("Hong Liu Lorem v. Lynch", r.content.decode())
        self.assertIn("John Smith", r.content.decode())

    @skip_if_common_tests_skipped
    async def test_oa_results_relevance_ordering_elastic(self) -> None:
        # Relevance order, two words match.
        search_params = {
            "q": "Lynch Loretta",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # API
        r = await self._test_api_results_count(
            search_params, 3, "relevance sorting"
        )
        self.assertTrue(
            r.content.decode().index("Hong Liu Lorem")
            < r.content.decode().index("Hong Liu Yang")
            < r.content.decode().index("Jose"),
            msg="'Hong Liu Lorem' should come BEFORE 'Hong Liu Yang' and 'Jose' when order_by relevance.",
        )

        # Relevance order, two words match, reverse order.
        search_params = {
            "q": "Loretta Lynch",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # API
        r = await self._test_api_results_count(
            search_params, 3, "relevance sorting"
        )
        self.assertTrue(
            r.content.decode().index("Jose")
            > r.content.decode().index("Hong Liu Lorem")
            < r.content.decode().index("Hong Liu Yang"),
            msg="'Jose' should come AFTER 'Hong Liu Lorem' and 'Hong Liu Yang' when order_by relevance.",
        )

    @skip_if_common_tests_skipped
    async def test_emojis_searchable(self) -> None:
        # Are emojis are searchable?
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "⚖️",
        }
        # API
        r = await self._test_api_results_count(
            search_params, 1, "emoji searchable"
        )
        self.assertIn("Wallace", r.content.decode())


@override_flag("oa-es-activate", active=True)
class OAV3SearchAPITests(
    OASearchAPICommonTests, ESIndexTestCase, TestCase, V4SearchAPIAssertions
):
    version_api = "v3"
    skip_common_tests = False

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.rebuild_index("audio.Audio")
        cls.rebuild_index("alerts.Alert")

    async def test_search_transcript(self) -> None:
        """Test search transcript."""

        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "This is the best transcript",
        }
        # API
        r = await self._test_api_results_count(
            search_params, 1, "match transcript"
        )
        # Transcript highlights
        self.assertIn(
            "<mark>This is the best transcript</mark>", r.content.decode()
        )

    @mock.patch(
        "cl.lib.es_signal_processor.allow_es_audio_indexing",
        side_effect=lambda x, y: True,
    )
    def test_oa_results_pagination(self, mock_abort_audio) -> None:
        created_audios = []
        audios_to_create = 20
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            for _ in range(audios_to_create):
                audio = AudioFactory.create(
                    docket_id=self.audio_3.docket.pk,
                )
                created_audios.append(audio)

        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        # API
        r = async_to_sync(self._test_api_results_count)(
            search_params, 20, "api pagination"
        )
        self.assertEqual(25, r.data["count"])
        self.assertIn("page=2", r.data["next"])

        # Test next page.
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "page": 2,
        }
        r = async_to_sync(self._test_api_results_count)(
            search_params, 5, "api pagination"
        )
        self.assertEqual(25, r.data["count"])
        self.assertEqual(None, r.data["next"])

        # Remove Audio objects to avoid affecting other tests.
        for created_audio in created_audios:
            created_audio.delete()

    async def test_oa_random_ordering(self) -> None:
        """Can the Oral Arguments results be ordered randomly?

        This test is difficult since we can't check that things actually get
        ordered randomly, but we can at least make sure the query succeeds.
        """
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "Hong Liu",
            "order_by": "random_123 desc",
        }
        # API
        r = await self._test_api_results_count(
            search_params, 2, "random sorting"
        )

    async def test_oa_results_highlights(self) -> None:
        """Confirm snippet is properly highlighted."""
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "This is the best transcript",
        }
        # API
        r = await self._test_api_results_count(search_params, 1, "HL snippet")
        self.assertIn(
            "<mark>This is the best transcript</mark>",
            r.data["results"][0]["snippet"],
            msg="Snippet HL doesn't match.",
        )

    @override_settings(NO_MATCH_HL_SIZE=50)
    def test_results_api_fields(self) -> None:
        """Confirm fields in V3 ES Oral Arguments Search API results."""
        mock_date = now()
        print("Mock date", mock_date)
        with time_machine.travel(
            mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            audio_1 = AudioFactory.create(
                case_name="United States v. Lee ",
                case_name_full="a_random_title",
                docket_id=self.docket_1.pk,
                duration=420,
                judges="John American",
                local_path_original_file="test/audio/ander_v._leo.mp3",
                local_path_mp3=self.filepath_local,
                source="C",
                blocked=False,
                sha1="a49ada009774496ac01fb49818837e2296705c97",
                stt_status=Audio.STT_COMPLETE,
                stt_transcript=self.json_transcript,
            )
            audio_1.panel.add(self.author)
            audio_1.processing_complete = True
            audio_1.save(
                update_fields=[
                    "duration",
                    "local_path_mp3",
                    "processing_complete",
                ]
            )

            docket = DocketFactory.create(
                docket_number="",
                court_id=self.court_1.pk,
                date_argued=datetime.date(2015, 8, 16),
                source=Docket.DEFAULT,
                pacer_case_id="",
            )
            empty_fields_audio = AudioFactory(
                docket=docket,
                duration=653,
                source="",
                case_name="",
                download_url="",
                local_path_mp3=None,
            )
            empty_fields_audio.processing_complete = True
            empty_fields_audio.save(
                update_fields=[
                    "duration",
                    "local_path_mp3",
                    "processing_complete",
                ]
            )

        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"id:{audio_1.pk}",
        }
        # API
        r = async_to_sync(self._test_api_results_count)(
            search_params, 1, "API fields"
        )
        keys_count = len(r.data["results"][0])
        self.assertEqual(
            keys_count,
            len(audio_v3_fields),
            msg="Document fields count didn't match.",
        )
        content_to_compare = {
            "result": audio_1,
            "snippet": "This is the best transcript. Nunc egestas sem sed libero",
            "V4": False,
        }
        async_to_sync(self._test_api_fields_content)(
            r, content_to_compare, audio_v3_fields, None, None
        )

        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"id:{empty_fields_audio.pk}",
        }
        # API
        r = async_to_sync(self._test_api_results_count)(
            search_params, 1, "Empty API fields"
        )
        keys_count = len(r.data["results"][0])
        self.assertEqual(
            keys_count,
            len(audio_v3_fields),
            msg="Document fields count didn't match.",
        )
        content_to_compare = {
            "result": empty_fields_audio,
            "V4": False,
        }
        async_to_sync(self._test_api_fields_content)(
            r, content_to_compare, audio_v3_fields, None, None
        )
        audio_1.delete()
        empty_fields_audio.delete()


class OAV4SearchAPITests(
    OASearchAPICommonTests, ESIndexTestCase, TestCase, V4SearchAPIAssertions
):
    version_api = "v4"
    skip_common_tests = False

    @classmethod
    def setUpTestData(cls):
        cls.mock_date = now().replace(day=15, hour=0)
        with time_machine.travel(cls.mock_date, tick=False):
            cls.rebuild_index("alerts.Alert")
            super().setUpTestData()
            cls.rebuild_index("audio.Audio")
            cls.rebuild_index("alerts.Alert")

    async def _test_api_results_count(
        self, params, expected_count, field_name
    ):
        """Get the result count in a API query response"""
        r = await self.async_client.get(
            reverse("search-list", kwargs={"version": "v4"}), params
        )
        got = len(r.data["results"])
        self.assertEqual(
            got,
            expected_count,
            msg="Did not get the right number of search results in API with %s "
            "filter applied.\n"
            "Expected: %s\n"
            "     Got: %s\n\n"
            "Params were: %s" % (field_name, expected_count, got, params),
        )
        return r

    @override_settings(NO_MATCH_HL_SIZE=50)
    async def test_results_api_fields(self) -> None:
        """Confirm fields in V4 Oral Arguments Search API results."""
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"id:{self.audio_1.pk}",
        }
        # API
        r = await self._test_api_results_count(search_params, 1, "API fields")
        keys_count = len(r.data["results"][0])
        self.assertEqual(
            keys_count,
            len(audio_v4_fields),
            msg="Document fields count didn't match.",
        )
        content_to_compare = {
            "result": self.audio_1,
            "snippet": "This is the best transcript. Nunc egestas sem sed",
            "V4": True,
        }
        await self._test_api_fields_content(
            r,
            content_to_compare,
            audio_v4_fields,
            None,
            v4_meta_keys,
        )

    def test_results_api_empty_fields(self) -> None:
        """Confirm  empty fields values in V4 OA Search API results."""

        mock_date = now().replace(day=15, hour=0)
        with time_machine.travel(
            mock_date, tick=False
        ), self.captureOnCommitCallbacks(execute=True):
            docket = DocketFactory.create(
                docket_number="",
                court_id=self.court_1.pk,
                date_argued=datetime.date(2015, 8, 16),
                source=Docket.DEFAULT,
                pacer_case_id="",
            )
            empty_fields_audio = AudioFactory(
                docket=docket,
                duration=653,
                source="",
                case_name="",
                download_url="",
                local_path_mp3=None,
            )
            empty_fields_audio.processing_complete = True
            empty_fields_audio.save(
                update_fields=[
                    "duration",
                    "local_path_mp3",
                    "processing_complete",
                ]
            )

        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"id:{empty_fields_audio.pk}",
        }
        # API
        r = async_to_sync(self._test_api_results_count)(
            search_params, 1, "API fields"
        )
        keys_count = len(r.data["results"][0])
        self.assertEqual(
            keys_count,
            len(audio_v4_fields),
            msg="Document fields count didn't match.",
        )
        content_to_compare = {"result": empty_fields_audio, "V4": True}
        async_to_sync(self._test_api_fields_content)(
            r,
            content_to_compare,
            audio_v4_fields,
            None,
            v4_meta_keys,
        )

    @override_settings(NO_MATCH_HL_SIZE=50)
    async def test_results_api_highlighted_fields(self) -> None:
        """Confirm highlighted fields in V4 OA Search API results."""
        # API HL disabled.
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"id:{self.audio_1.pk} court_citation_string:Cal text:best",
            "case_name": "Information",
            "judge": "Mary",
            "docket_number": "1:21-bk-1234",
        }
        # OA Search type HL disabled.
        r = await self._test_api_results_count(search_params, 1, "API fields")
        content_to_compare = {
            "result": self.audio_1,
            "snippet": "This is the best transcript. Nunc egestas sem sed",
            "V4": True,
        }
        await self._test_api_fields_content(
            r,
            content_to_compare,
            audio_v4_fields,
            None,
            v4_meta_keys,
        )
        # OA Search type HL enabled.
        search_params["highlight"] = True
        r = await self._test_api_results_count(search_params, 1, "API fields")
        content_to_compare = {
            "result": self.audio_1,
            "caseName": "SEC v. Frank J. <mark>Information</mark>, WikiLeaks",
            "judge": "<mark>Mary</mark> Deposit Learning rd Administrative procedures act",
            "docketNumber": "<mark>1:21-bk-1234</mark>",
            "court_citation_string": "Bankr. C.D. <mark>Cal</mark>.",
            "snippet": "This is the <mark>best</mark> transcript. Nunc egestas sem sed libero feugiat, at interdum quam viverra. Pellentesque",
            "V4": True,
        }
        await self._test_api_fields_content(
            r,
            content_to_compare,
            audio_v4_fields,
            None,
            v4_meta_keys,
        )

    @override_settings(SEARCH_API_PAGE_SIZE=3)
    def test_opinion_results_cursor_api_pagination(self) -> None:
        """Test cursor pagination for V4 OA Search API."""

        created_audios = []
        audios_to_create = 4

        docket = DocketFactory.create(
            docket_number="12-23232",
            court_id=self.court_1.pk,
            date_argued=datetime.date(2024, 8, 16),
            source=Docket.DEFAULT,
            pacer_case_id="323232",
        )
        docket_date_argued_none = DocketFactory.create(
            docket_number="12-43562",
            court_id=self.court_1.pk,
            date_argued=None,
            source=Docket.DEFAULT,
            pacer_case_id="545462",
        )
        audio = AudioFactory(
            docket=docket,
            duration=653,
            case_name="Audio test",
        )
        created_audios.append(audio)
        for _ in range(audios_to_create):
            audio_2 = AudioFactory(
                docket=docket_date_argued_none,
                duration=653,
                case_name="Audio test 2",
                local_path_mp3=None,
                local_path_original_file=None,
            )
            created_audios.append(audio_2)

        with self.captureOnCommitCallbacks(execute=True):
            for audio_created in created_audios:
                audio_created.processing_complete = True
                audio_created.save(
                    update_fields=[
                        "duration",
                        "local_path_mp3",
                        "processing_complete",
                    ]
                )

        total_audios = Audio.objects.all().count()

        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
            "highlight": False,
        }

        tests = [
            {
                "results": 3,
                "count_exact": total_audios,
                "next": True,
                "previous": False,
            },
            {
                "results": 3,
                "count_exact": total_audios,
                "next": True,
                "previous": True,
            },
            {
                "results": 3,
                "count_exact": total_audios,
                "next": True,
                "previous": True,
            },
            {
                "results": 1,
                "count_exact": total_audios,
                "next": False,
                "previous": True,
            },
        ]

        order_types = [
            "score desc",
            "dateArgued desc",
            "dateArgued asc",
        ]
        for order_type in order_types:
            # Test forward pagination.
            next_page = None
            all_document_ids = []
            ids_per_page = []
            current_page = None
            with self.subTest(order_type=order_type, msg="Sorting order."):
                search_params["order_by"] = order_type
                for test in tests:
                    with self.subTest(test=test, msg="forward pagination"):
                        if not next_page:
                            r = self.client.get(
                                reverse(
                                    "search-list", kwargs={"version": "v4"}
                                ),
                                search_params,
                            )
                        else:
                            r = self.client.get(next_page)
                        # Test page variables.
                        next_page, _, current_page = self._test_page_variables(
                            r, test, current_page, search_params["type"]
                        )
                        ids_in_page = set()
                        for result in r.data["results"]:
                            all_document_ids.append(result["id"])
                            ids_in_page.add(result["id"])
                        ids_per_page.append(ids_in_page)

            # Confirm all the documents were shown when paginating forwards.
            self.assertEqual(
                len(all_document_ids),
                total_audios,
                msg="Wrong number of Audios.",
            )

        # Test backward pagination.
        tests_backward = tests.copy()
        tests_backward.reverse()
        previous_page = None
        all_ids_prev = []
        for test in tests_backward:
            with self.subTest(test=test, msg="backward pagination"):
                if not previous_page:
                    r = self.client.get(current_page)
                else:
                    r = self.client.get(previous_page)

                # Test page variables.
                _, previous_page, current_page = self._test_page_variables(
                    r, test, current_page, search_params["type"]
                )
                ids_in_page_got = set()
                for result in r.data["results"]:
                    all_ids_prev.append(result["id"])
                    ids_in_page_got.add(result["id"])
                current_page_ids_prev = ids_per_page.pop()
                # Check if IDs obtained with forward pagination match
                # the IDs obtained when paginating backwards.
                self.assertEqual(
                    current_page_ids_prev,
                    ids_in_page_got,
                    msg="Wrong audios in page.",
                )

        # Confirm all the documents were shown when paginating backwards.
        self.assertEqual(
            len(all_ids_prev),
            total_audios,
            msg="Wrong number of audios.",
        )

        # Remove Audio objects to avoid affecting other tests.
        for created_audio in created_audios:
            created_audio.delete()

    def test_audio_specific_sorting_keys(self) -> None:
        """Test if the dateArgued sorting keys work properly in
        the V4 OA Search API."""

        docket_date_argued_none = DocketFactory.create(
            docket_number="12-43562",
            court_id=self.court_1.pk,
            date_argued=None,
            source=Docket.DEFAULT,
            pacer_case_id="545462",
        )
        audio_none = AudioFactory(
            docket=docket_date_argued_none,
            duration=653,
            case_name="Audio test",
            local_path_mp3=None,
            local_path_original_file=None,
        )

        with self.captureOnCommitCallbacks(execute=True):
            audio_none.processing_complete = True
            audio_none.save(
                update_fields=[
                    "duration",
                    "local_path_mp3",
                    "processing_complete",
                ]
            )

        # Query string, order by name_reverse asc
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "dateArgued asc",
            "highlight": False,
        }

        params_date_argued_desc = search_params.copy()
        params_date_argued_desc["order_by"] = "dateArgued desc"

        base_test_cases = [
            {
                "name": "Query order by dateArgued asc",
                "search_params": search_params,
                "expected_results": 6,
                "expected_order": [
                    self.audio_5.pk,  # 2013, 8, 14
                    self.audio_4.pk,  # 2015, 8, 14 id: 4
                    self.audio_3.pk,  # 2015, 8, 14 id: 3
                    self.audio_2.pk,  # 2015, 8, 15
                    self.audio_1.pk,  # 2015, 8, 16
                    audio_none.pk,  # None
                ],
            },
            {
                "name": "Query order by dateArgued desc",
                "search_params": params_date_argued_desc,
                "expected_results": 6,
                "expected_order": [
                    self.audio_1.pk,  # 2015, 8, 16
                    self.audio_2.pk,  # 2015, 8, 15
                    self.audio_4.pk,  # 2015, 8, 14 id: 4
                    self.audio_3.pk,  # 2015, 8, 14 id: 3
                    self.audio_5.pk,  # 2013, 8, 14
                    audio_none.pk,  # None
                ],
            },
        ]

        # Extend test cases to include a Query string and a Match all query.
        test_cases = [
            {
                **test_param,
                "search_params": {**test_param["search_params"], **query_type},
            }
            for test_param in base_test_cases
            for query_type in [{"q": "*"}, {}]
        ]

        for test in test_cases:
            self._test_results_ordering(test, "id")

        audio_none.delete()

    def test_audio_cursor_api_pagination_count(self) -> None:
        """Test cursor pagination count for V4 OA Search API."""

        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
            "highlight": False,
        }
        total_audios = Audio.objects.all().count()
        ## Get count from cardinality.
        with override_settings(
            ELASTICSEARCH_MAX_RESULT_COUNT=total_audios - 1
        ):
            # OralArgument Search request, count Audios.
            r = self.client.get(
                reverse("search-list", kwargs={"version": "v4"}), search_params
            )
            self.assertEqual(
                r.data["count"],
                total_audios,
                msg="Results cardinality count didn't match.",
            )

        ## Get count from main query.
        with override_settings(
            ELASTICSEARCH_MAX_RESULT_COUNT=total_audios + 1
        ):
            # Oral Argument Search request, count Audios.
            r = self.client.get(
                reverse("search-list", kwargs={"version": "v4"}), search_params
            )
            self.assertEqual(
                r.data["count"],
                total_audios,
                msg="Results main query count didn't match.",
            )


class OASearchTestElasticSearch(ESIndexTestCase, AudioESTestCase, TestCase):
    """Oral argument search tests for Elasticsearch"""

    @classmethod
    def setUpTestData(cls):
        cls.rebuild_index("alerts.Alert")
        super().setUpTestData()
        cls.rebuild_index("audio.Audio")
        cls.rebuild_index("alerts.Alert")

    @classmethod
    def delete_documents_from_index(cls, index_alias, queries):
        es_conn = connections.get_connection()
        for query_id in queries:
            es_conn.delete(index=index_alias, id=query_id)

    @classmethod
    def tearDownClass(cls):
        Audio.objects.all().delete()
        super().tearDownClass()

    @staticmethod
    def get_article_count(r):
        """Get the article count in a query response"""
        return len(html.fromstring(r.content.decode()).xpath("//article"))

    @staticmethod
    def get_results_count(r):
        """Get the result count in a API query response"""
        return len(r.data["results"])

    @staticmethod
    def confirm_query_matched(response, query_id) -> bool:
        """Confirm if a percolator query matched."""

        matched = False
        for hit in response:
            if hit.meta.id == query_id:
                matched = True
        return matched

    @staticmethod
    def save_percolator_query(cd):
        search_query = AudioDocument.search()
        query, _ = build_es_base_query(search_query, cd)
        query_dict = query.to_dict()["query"]
        percolator_query = AudioPercolator(
            percolator_query=query_dict, rate=Alert.REAL_TIME
        )
        percolator_query.save(refresh=True)

        return percolator_query.meta.id

    @staticmethod
    def prepare_document(document):
        audio_doc = AudioDocument()
        return audio_doc.prepare(document)

    def test_oa_results_basic(self) -> None:
        # Frontend
        r = self.client.get(
            reverse("show_results"), {"type": SEARCH_TYPES.ORAL_ARGUMENT}
        )
        self.assertIn("Jose", r.content.decode())

    def test_oa_results_date_argued_ordering(self) -> None:
        # Order by dateArgued desc
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "dateArgued desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        self.assertTrue(
            r.content.decode().index("SEC") < r.content.decode().index("Jose"),
            msg="'SEC' should come BEFORE 'Jose' when order_by desc.",
        )

        # Order by dateArgued asc
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "dateArgued asc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        self.assertTrue(
            r.content.decode().index("Jose") < r.content.decode().index("SEC"),
            msg="'Jose' should come AFTER 'SEC' when order_by asc.",
        )

    def test_oa_results_relevance_ordering(self) -> None:
        # Relevance order, single word match.
        search_params = {
            "q": "Loretta",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 3
        self.assertEqual(actual, expected)
        self.assertTrue(
            r.content.decode().index("Jose")
            > r.content.decode().index("Hong Liu"),
            msg="'Jose' should come AFTER 'Hong Liu' when order_by relevance.",
        )

    def test_oa_results_search_match_phrase(self) -> None:
        # Search by phrase that only matches one result.
        search_params = {
            "q": "Hong Liu Lorem",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)

    def test_oa_results_search_in_text(self) -> None:
        # Text query search by docket number
        search_params = {
            "q": f"{self.audio_3.docket.docket_number}",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertTrue(
            r.content.decode().index("Lorem")
            < r.content.decode().index("Yang"),
            msg="'Lorem' should come BEFORE 'Yang' when order_by relevance.",
        )

        # Text query combine case name and docket name.
        search_params = {
            "q": f"Lorem {self.audio_3.docket.docket_number}",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)

        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)

        # Text query search by Court in text.
        search_params = {
            "q": f"{self.audio_3.docket.court.pk}",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)

        # Text query search by sha1 in text.
        search_params = {
            "q": self.audio_1.sha1,
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)

    def test_oa_results_highlights(self) -> None:
        # Case name highlights
        r = self.client.get(
            reverse("show_results"),
            {
                "q": "Hong Liu Yang",
                "type": SEARCH_TYPES.ORAL_ARGUMENT,
                "order_by": "score desc",
            },
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("<mark>Hong Liu Yang</mark>", r.content.decode())

        # Docket number highlights
        r = self.client.get(
            reverse("show_results"),
            {
                "q": f"{self.audio_2.docket.docket_number}",
                "type": SEARCH_TYPES.ORAL_ARGUMENT,
                "order_by": "score desc",
            },
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn(
            f"<mark>{self.audio_2.docket.docket_number}</mark>",
            r.content.decode(),
        )

        # Judge highlights
        r = self.client.get(
            reverse("show_results"),
            {
                "q": "John Smith",
                "type": SEARCH_TYPES.ORAL_ARGUMENT,
                "order_by": "score desc",
            },
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("<mark>John Smith</mark>", r.content.decode())
        self.assertEqual(
            r.content.decode().count("<mark>John Smith</mark>"), 1
        )

        # Court citation string highlights
        r = self.client.get(
            reverse("show_results"),
            {
                "q": "Freedom of Inform Wikileaks (Bankr. C.D. Cal. 2013)",
                "type": SEARCH_TYPES.ORAL_ARGUMENT,
                "order_by": "score desc",
            },
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn(
            "<mark>Bankr.&nbsp;C.D.&nbsp;Cal</mark>", r.content.decode()
        )
        self.assertEqual(
            r.content.decode().count("<mark>Bankr.&nbsp;C.D.&nbsp;Cal</mark>"),
            1,
        )

    def test_oa_case_name_filtering(self) -> None:
        """Filter by case_name"""
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "case_name": "jose",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "case name. Expected %s, but got %s." % (expected, actual),
        )

    def test_oa_docket_number_filtering(self) -> None:
        """Filter by docket number"""
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "docket_number": f"{self.audio_1.docket.docket_number}",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "docket number. Expected %s, but got %s." % (expected, actual),
        )
        self.assertIn("SEC", r.content.decode())

    def test_oa_jurisdiction_filtering(self) -> None:
        """Filter by court"""
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "court": f"{self.audio_3.docket.court.pk}",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "jurisdiction. Expected %s, but got %s." % (expected, actual),
        )

    def test_oa_date_argued_filtering(self) -> None:
        """Filter by date_argued"""
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "argued_after": "2015-08-16",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        self.assertNotIn(
            "an error",
            r.content.decode(),
            msg="Got an error when doing a Date Argued filter.",
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "argued_after. Expected %s, but got %s." % (actual, expected),
        )
        self.assertIn(
            "SEC v. Frank J. Information, WikiLeaks",
            r.content.decode(),
            msg="Did not get the expected oral argument.",
        )

    def test_oa_combine_search_and_filtering(self) -> None:
        """Test combine text query and filtering"""
        # Text query
        search_params = {
            "q": "Loretta",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 3
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "case name. Expected %s, but got %s." % (expected, actual),
        )

        # Text query filtered by case_name
        search_params = {
            "q": "Loretta",
            "case_name": "Hong Liu",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "case name. Expected %s, but got %s." % (expected, actual),
        )

        # Text query filtered by case_name and judge
        search_params = {
            "q": "Loretta",
            "case_name": "Hong Liu",
            "judge": "John Smith",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "case name. Expected %s, but got %s." % (expected, actual),
        )

        # Text query filtered by argued_after. Notice that out of two audios
        # argued_after 2015-08-15, only one is selected by the query string,
        # which only matches one of them. Thus, this query tests that
        # minimum_should_match = 1 is properly added when combining a query
        # string with a filter.
        search_params = {
            "q": "Frank",
            "argued_after": "2015-08-15",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        # Frontend
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(
            actual,
            expected,
            msg="Did not get expected number of results when filtering by "
            "case name. Expected %s, but got %s." % (expected, actual),
        )

    def test_oa_advanced_search_not_query(self) -> None:
        """Test advanced search queries"""
        # NOT query
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "Loretta NOT (Hong Liu)",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Jose A.", r.content.decode())

    def test_oa_advanced_search_and_query(self) -> None:
        # AND query
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "Loretta AND judge:John Smith",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Hong Liu Lorem v. Lynch", r.content.decode())
        self.assertIn("John Smith", r.content.decode())

    def test_oa_advanced_search_or_and_query(self) -> None:
        # Grouped "OR" query and "AND" query
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "(Loretta OR SEC) AND Jose",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("<mark>Jose</mark>", r.content.decode())

    def test_oa_advanced_search_by_field(self) -> None:
        # Query by docket_id advanced field
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"docket_id:{self.audio_1.docket.pk}",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("SEC v. Frank", r.content.decode())

        # Query by id advanced field
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"id:{self.audio_4.pk}",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Hong Liu Lorem", r.content.decode())

        # Query by court_id advanced field
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"court_id:{self.audio_3.docket.court_id}",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("Hong Liu Yang v. Lynch-Loretta E", r.content.decode())
        self.assertIn("Hong Liu Lorem v. Lynch-Loretta E.", r.content.decode())

        # Query by panel_ids advanced field
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"id:{self.audio_4.pk} AND panel_ids:{self.author.pk}",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Hong Liu Lorem v. Lynch-Loretta E.", r.content.decode())

        # Query by dateArgued advanced field
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "dateArgued:[2015-08-15T00:00:00Z TO 2015-08-17T00:00:00Z]",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("SEC", r.content.decode())
        self.assertIn("Jose", r.content.decode())

        # Query by pacer_case_id advanced field
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"pacer_case_id:{self.audio_5.docket.pacer_case_id}",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Wikileaks", r.content.decode())

    def test_oa_advanced_search_by_field_and_keyword(self) -> None:
        # Query by advanced field and refine by keyword.
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"docket_id:{self.audio_3.docket.pk} Lorem",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Lorem", r.content.decode())

    def test_oa_random_ordering(self) -> None:
        """Can the Oral Arguments results be ordered randomly?

        This test is difficult since we can't check that things actually get
        ordered randomly, but we can at least make sure the query succeeds.
        """
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "Hong Liu",
            "order_by": "random_123 desc",
        }
        # Frontend
        r = self.client.get(reverse("show_results"), search_params)
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertNotIn("an error", r.content.decode())

    def test_last_oral_arguments_home_page(self) -> None:
        """Test last oral arguments in home page"""
        cache.delete("homepage-data-oa-es")
        r = self.client.get(
            reverse("show_results"),
        )
        self.assertIn("Latest Oral Arguments", r.content.decode())
        self.assertIn(
            "SEC v. Frank J. Information, WikiLeaks", r.content.decode()
        )
        self.assertIn(
            "Jose A. Dominguez v. Loretta E. Lynch", r.content.decode()
        )
        self.assertIn("Hong Liu Yang v. Lynch-Loretta E.", r.content.decode())
        self.assertIn("Hong Liu Lorem v. Lynch-Loretta E.", r.content.decode())

    def test_oa_advanced_search_combine_fields(self) -> None:
        # Query by two advanced fields, caseName and docketNumber
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": f"caseName:Loretta AND docketNumber:({self.audio_2.docket.docket_number})",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Jose", r.content.decode())

    def test_oa_search_by_no_exact_docket_number(self) -> None:
        # Query a not exact docket number: 19-5734 -> 19 5734
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": 'docketNumber:"19 5734"',
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Jose", r.content.decode())

        # Avoid error parsing the docket number: 19-5734 -> 19:5734.
        search_params["q"] = "docketNumber:19:5734"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Jose", r.content.decode())

    def test_oa_results_relevance_ordering_elastic(self) -> None:
        # Relevance order, two words match.
        search_params = {
            "q": "Lynch Loretta",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 3
        self.assertEqual(actual, expected)
        self.assertTrue(
            r.content.decode().index("Hong Liu Lorem")
            < r.content.decode().index("Hong Liu Yang")
            < r.content.decode().index("Jose"),
            msg="'Hong Liu Lorem' should come BEFORE 'Hong Liu Yang' and 'Jose' when order_by relevance.",
        )

        # Relevance order, two words match, reverse order.
        search_params = {
            "q": "Loretta Lynch",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 3
        self.assertEqual(actual, expected)
        self.assertTrue(
            r.content.decode().index("Jose")
            > r.content.decode().index("Hong Liu Lorem")
            < r.content.decode().index("Hong Liu Yang"),
            msg="'Jose' should come AFTER 'Hong Liu Lorem' and 'Hong Liu Yang' when order_by relevance.",
        )

        # Relevance order, hyphenated compound word.
        search_params = {
            "q": "Lynch-Loretta E.",
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "order_by": "score desc",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 3
        self.assertEqual(actual, expected)
        self.assertTrue(
            r.content.decode().index("Hong Liu Lorem")
            < r.content.decode().index("Hong Liu Yang")
            < r.content.decode().index("Jose"),
            msg="'Hong Liu Lorem' should come BEFORE 'Hong Liu Yang' and 'Jose' when order_by relevance.",
        )

    @mock.patch(
        "cl.lib.es_signal_processor.allow_es_audio_indexing",
        side_effect=lambda x, y: True,
    )
    def test_oa_results_pagination(self, mock_abort_audio) -> None:
        created_audios = []
        audios_to_create = 20
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            for _ in range(audios_to_create):
                audio = AudioFactory.create(
                    docket_id=self.audio_3.docket.pk,
                )
                created_audios.append(audio)

        # Confirm that fetch_es_results works properly with different sorting
        # types, returning sequential results for each requested page.
        page_size = 5
        total_audios = Audio.objects.all().count()
        total_pages = int(total_audios / page_size) + 1
        order_types = [
            "score desc",
            "dateArgued desc",
            "dateArgued asc",
            "random_123 asc",
        ]
        for order in order_types:
            ids_in_results = []
            for page in range(total_pages):
                cd = {
                    "type": SEARCH_TYPES.ORAL_ARGUMENT,
                    "order_by": order,
                }
                search_query = AudioDocument.search()
                s, child_docs_query, *_ = build_es_main_query(search_query, cd)
                hits, *_ = fetch_es_results(
                    cd,
                    s,
                    child_docs_query,
                    page=page + 1,
                    rows_per_page=page_size,
                )
                for result in hits.hits:
                    ids_in_results.append(result.id)
            self.assertEqual(len(ids_in_results), total_audios)

        # Test pagination requests.
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
        }
        # Frontend
        results_per_page = settings.SEARCH_PAGE_SIZE
        total_results = 25
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = results_per_page
        expected_page = math.ceil(total_results / results_per_page)
        self.assertEqual(actual, expected)
        self.assertIn(f"{total_results} Results", r.content.decode())
        self.assertIn(f"1 of {expected_page:,}", r.content.decode())

        # Test next page.
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "page": expected_page,
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 5
        self.assertEqual(actual, expected)
        self.assertIn(f"{total_results} Results", r.content.decode())
        self.assertIn(
            f"{expected_page} of {expected_page:,}", r.content.decode()
        )

        # Remove Audio objects to avoid affecting other tests.
        for created_audio in created_audios:
            created_audio.delete()

    def test_oa_synonym_search(self) -> None:
        # Query using a synonym
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "Freedom of Info",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("<mark>Freedom of Inform</mark>", r.content.decode())

        # Top abbreviations in legal documents
        # Single term posttraumatic
        search_params["q"] = "posttraumatic stress disorder"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        # When using FVH, if the abbreviation term is indexed, then performing
        # a search using the whole term does not highlight the abbreviation.
        self.assertNotIn("<mark>ptsd</mark>", r.content.decode())

        # Split terms post traumatic
        search_params["q"] = "post traumatic stress disorder"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        # When using FVH, if the abbreviation term is indexed, then performing
        # a search using the whole term does not highlight the abbreviation.
        self.assertNotIn("<mark>ptsd</mark>", r.content.decode())

        # Search acronym "apa"
        search_params["q"] = "apa"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        # Note that if the whole term is indexed and a search is performed
        # using the abbreviation term, the whole term is properly highlighted.
        self.assertIn("<mark>apa</mark>", r.content.decode())
        self.assertIn(
            "<mark>Administrative procedures act</mark>", r.content.decode()
        )

        # Search by "Administrative procedures act"
        search_params["q"] = "Administrative procedures act"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("<mark>Administrative</mark>", r.content.decode())
        self.assertIn("<mark>procedures</mark>", r.content.decode())
        self.assertIn("<mark>act</mark>", r.content.decode())
        # When using FVH, if the abbreviation term is indexed, then performing
        # a search using the whole term does not highlight the abbreviation.
        self.assertNotIn("<mark>apa</mark>", r.content.decode())

        # Search by "Administrative" shouldn't return results for "apa" but for
        # "Administrative" and "Administrative procedures act".
        search_params["q"] = "Administrative"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("Hong Liu Yang", r.content.decode())
        self.assertIn("procedures act", r.content.decode())

        # Single word one-way synonyms.
        # mag => mag,magazine,magistrate
        search_params["q"] = "mag"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 3
        self.assertEqual(actual, expected)
        self.assertIn("<mark>mag</mark>", r.content.decode())
        self.assertIn("<mark>magazine</mark>", r.content.decode())
        self.assertIn("<mark>magistrate</mark>", r.content.decode())

        # Searching "magazine" only returns results containing "magazine"
        search_params["q"] = "magazine"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("<mark>magazine</mark>", r.content.decode())

    def test_oa_stopwords_search(self) -> None:
        # Query using a stopword, indexed content doesn't contain the stop word
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "judge:Wallace and Friedland",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Jose", r.content.decode())

        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "judge:Wallace to Friedland",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Freedom", r.content.decode())

        # Special stopwords are not found.
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "xx-xxxx",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 0
        self.assertEqual(actual, expected)

    def test_phrase_queries_with_stop_words(self) -> None:
        # Do phrase queries with stop words return results properly?
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": 'caseName:"Freedom of Inform"',
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("<mark>Freedom of Inform</mark>", r.content.decode())

    def test_character_case_queries(self) -> None:
        # Do character case queries works properly?
        # Queries like WikiLeaks and wikileaks or GraphQL and GraphqL, should
        # return the same results in both cases.
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "WikiLeaks",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("SEC", r.content.decode())
        self.assertIn("Freedom", r.content.decode())

        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "wikileaks",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("SEC", r.content.decode())
        self.assertIn("Freedom", r.content.decode())

    def test_emojis_searchable(self) -> None:
        # Are emojis are searchable?
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "⚖️",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Wallace", r.content.decode())
        # Is the emoji highlighted?
        self.assertIn("<mark>⚖️</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>⚖️</mark>"), 1)

    def test_docket_number_proximity_query(self) -> None:
        """Test docket_number proximity query, so that docket numbers like
        1:21-cv-1234-ABC can be matched by queries like: 21-1234
        """

        # Query 1234-21, no results should be returned due to phrased search.
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "1234-21",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 0
        self.assertEqual(actual, expected)

        # Query 21-1234, return results for 1:21-bk-1234 and 1:21-cv-1234-ABC
        # Frontend
        search_params["q"] = "21-1234"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("Freedom", r.content.decode())
        self.assertIn("SEC", r.content.decode())

        # Query 1:21-cv-1234
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "1:21-cv-1234",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Wikileaks", r.content.decode())

        # Query 1:21-cv-1234-ABC
        # Frontend
        search_params["q"] = "1:21-cv-1234-ABC"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Wikileaks", r.content.decode())

        # Query 1:21-bk-1234
        # Frontend
        search_params["q"] = "1:21-bk-1234"
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("SEC", r.content.decode())

        # docket_number filter: 21-1234, return results for 1:21-bk-1234
        # and 1:21-cv-1234-ABC
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "docket_number": "21-1234",
        }
        # Frontend
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("SEC", r.content.decode())
        self.assertIn("Freedom", r.content.decode())
        self.assertIn("SEC", r.content.decode())

    def test_docket_number_suffixes_query(self) -> None:
        """Test docket_number with suffixes can be found."""

        # Indexed: 1:21-bk-1234 -> Search: 1:21-bk-1234-ABC
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "1:21-bk-1234-ABC",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("SEC", r.content.decode())

        # Other kind of formats can still be searched -> ASBCA No. 59126
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "ASBCA No. 59126",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("Hong Liu", r.content.decode())

    def test_stemming_disable_search(self) -> None:
        """Test docket_number with suffixes can be found."""

        # Normal search with stemming 'Information', results for:
        # Hong Liu Yang (Joseph Information Deposition)
        # SEC v. Frank J. Information... (Mary Deposit)
        # Freedom of Inform... (Wallace to Friedland ⚖️ Deposit)
        # Frontend
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "Information deposition",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 3
        self.assertEqual(actual, expected)
        self.assertIn("SEC v. Frank J.", r.content.decode())
        self.assertIn("Freedom of", r.content.decode())
        self.assertIn("Hong Liu Yang", r.content.decode())

        # Exact search '"Information" deposition', results for:
        # Hong Liu Yang (Joseph Information Deposition)
        # SEC v. Frank J. Information... (Mary Deposit)
        # Frontend
        search_params["q"] = '"Information" deposition'
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("SEC v. Frank J.", r.content.decode())
        self.assertIn("Hong Liu Yang", r.content.decode())
        self.assertEqual(
            r.content.decode().count("<mark>Information</mark>"), 2
        )
        self.assertEqual(r.content.decode().count("<mark>Deposit</mark>"), 1)
        self.assertEqual(
            r.content.decode().count("<mark>Deposition</mark>"), 1
        )

        # Exact search '"Information" "deposit"', results for:
        # SEC v. Frank J. Information... (Mary Deposit)
        # Frontend
        search_params["q"] = '"Information" "deposit"'
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("SEC v. Frank J.", r.content.decode())

        # Exact search '"Inform" "deposit"', results for:
        # Freedom of Inform... (Wallace to Friedland ⚖️ Deposit)
        # Frontend
        search_params["q"] = '"Inform" "deposit"'
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("Freedom of", r.content.decode())
        self.assertIn("<mark>Inform</mark>", r.content.decode())
        self.assertEqual(r.content.decode().count("<mark>Inform</mark>"), 1)
        self.assertEqual(r.content.decode().count("<mark>Deposit</mark>"), 1)

    def test_exact_and_synonyms_query(self) -> None:
        """Test exact and synonyms in the same query."""

        # Search for 'learn road' should return results for 'learn of rd' and
        # 'learning rd'.
        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "learn road",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 2
        self.assertEqual(actual, expected)
        self.assertIn("<mark>Learn</mark>", r.content.decode())
        self.assertIn("<mark>Learning rd</mark>", r.content.decode())

        # Search for '"learning" road' should return only a result for
        # 'Learning rd'
        search_params["q"] = '"learning" road'
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        self.assertIn("<mark>Learning</mark>", r.content.decode())
        self.assertIn("<mark>rd</mark>", r.content.decode())

        # A phrase search for '"learn road"' should execute an exact and phrase
        # search simultaneously. It shouldn't return any results,
        # given that the indexed string is 'Learn of rd'.
        search_params["q"] = '"learn road"'
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 0
        self.assertEqual(actual, expected)

    def test_percolator(self) -> None:
        """Test if a variety of documents triggers a percolator query."""
        oral_argument_index_alias = AudioDocument._index._name
        created_queries_ids = []
        # Add queries to percolator.
        cd = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "Loretta",
            "order_by": "score desc",
        }
        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        response = percolate_document(
            str(self.audio_2.pk), oral_argument_index_alias
        )
        expected_queries = 1
        self.assertEqual(len(response), expected_queries)
        self.assertEqual(self.confirm_query_matched(response, query_id), True)

        cd = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "case_name": "jose",
            "q": "",
            "order_by": "score desc",
        }

        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        response = percolate_document(
            str(self.audio_2.pk), oral_argument_index_alias
        )
        expected_queries = 2
        self.assertEqual(len(response), expected_queries)
        self.assertEqual(self.confirm_query_matched(response, query_id), True)

        cd = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "docket_number": "1:21-bk-1234",
            "q": "",
            "order_by": "score desc",
        }
        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        response = percolate_document(
            str(self.audio_1.pk), oral_argument_index_alias
        )
        expected_queries = 1
        self.assertEqual(len(response), expected_queries)
        self.assertEqual(self.confirm_query_matched(response, query_id), True)

        cd = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "docket_number": "1:21-cv-1234-ABC",
            "court": "cabc",
            "q": "",
            "order_by": "score desc",
        }

        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        response = percolate_document(
            str(self.audio_5.pk), oral_argument_index_alias
        )
        expected_queries = 1
        self.assertEqual(len(response), expected_queries)
        self.assertEqual(self.confirm_query_matched(response, query_id), True)

        cd = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "docket_number": "1:21-bk-1234",
            "court": "cabc",
            "argued_after": datetime.date(2015, 8, 16),
            "q": "",
            "order_by": "score desc",
        }

        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        response = percolate_document(
            str(self.audio_1.pk), oral_argument_index_alias
        )
        expected_queries = 2
        self.assertEqual(len(response), expected_queries)
        self.assertEqual(self.confirm_query_matched(response, query_id), True)

        cd = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "docket_number": "19-5734",
            "court": "cabc",
            "argued_after": datetime.date(2015, 8, 15),
            "q": "Loretta NOT (Hong Liu)",
            "order_by": "score desc",
        }
        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        response = percolate_document(
            str(self.audio_2.pk), oral_argument_index_alias
        )
        expected_queries = 3
        self.assertEqual(len(response), expected_queries)
        self.assertEqual(self.confirm_query_matched(response, query_id), True)

        cd = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "court": "nyed",
            "argued_after": datetime.date(2015, 8, 14),
            "q": "caseName:Loretta AND docketNumber:(ASBCA No. 59126)",
            "order_by": "score desc",
        }

        query_id = self.save_percolator_query(cd)
        created_queries_ids.append(query_id)
        response = percolate_document(
            str(self.audio_4.pk), oral_argument_index_alias
        )
        expected_queries = 2
        self.assertEqual(len(response), expected_queries)
        self.assertEqual(self.confirm_query_matched(response, query_id), True)

        self.delete_documents_from_index(
            AudioPercolator._index._name, created_queries_ids
        )

    def test_search_transcript(self) -> None:
        """Test search transcript."""

        search_params = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "This is the best transcript",
        }
        r = self.client.get(
            reverse("show_results"),
            search_params,
        )
        actual = self.get_article_count(r)
        expected = 1
        self.assertEqual(actual, expected)
        # Transcript highlights
        self.assertIn(
            "<mark>This is the best transcript</mark>", r.content.decode()
        )


class OralArgumentIndexingTest(
    CountESTasksTestCase, ESIndexTestCase, TransactionTestCase
):
    def setUp(self):
        self.court_1 = CourtFactory(
            id="cabc",
            full_name="Testing Supreme Court",
            jurisdiction="FB",
            citation_string="Bankr. C.D. Cal.",
        )
        self.docket = DocketFactory.create(
            court_id=self.court_1.pk, source=Docket.SCRAPER
        )
        self.docket_2 = DocketFactory.create(
            court_id=self.court_1.pk, source=Docket.SCRAPER
        )

        super().setUp()

    @mock.patch(
        "cl.lib.es_signal_processor.allow_es_audio_indexing",
        side_effect=lambda x, y: True,
    )
    def test_keep_in_sync_related_OA_objects(self, mock_abort_audio) -> None:
        """Test Audio documents are updated when related objects change."""

        docket_5 = DocketFactory.create(
            docket_number="1:22-bk-12345",
            court_id=self.court_1.pk,
            date_argued=datetime.date(2015, 8, 16),
            source=Docket.SCRAPER,
        )
        audio_6 = AudioFactory.create(
            case_name="Lorem Ipsum Dolor vs. USA",
            docket_id=docket_5.pk,
        )
        audio_7 = AudioFactory.create(
            case_name="Lorem Ipsum Dolor vs. IRS",
            docket_id=docket_5.pk,
        )
        cd = {
            "type": SEARCH_TYPES.ORAL_ARGUMENT,
            "q": "Lorem Ipsum Dolor vs. United States",
            "order_by": "score desc",
        }
        search_query = AudioDocument.search()
        s, *_ = build_es_main_query(search_query, cd)
        self.assertEqual(s.count(), 1)
        results = s.execute()
        self.assertEqual(results[0].caseName, "Lorem Ipsum Dolor vs. USA")
        self.assertEqual(results[0].docketNumber, "1:22-bk-12345")
        self.assertEqual(results[0].panel_ids, [])
        self.assertEqual(results[0].date_created, audio_6.date_created)

        # Update docket number and dateArgued
        docket_5.docket_number = "23-98765"
        docket_5.date_argued = datetime.date(2023, 5, 15)
        docket_5.date_reargued = datetime.date(2022, 5, 15)
        docket_5.date_reargument_denied = datetime.date(2021, 5, 15)
        docket_5.save()
        # Confirm docket number and dateArgued are updated in the index.
        s, *_ = build_es_main_query(search_query, cd)
        self.assertEqual(s.count(), 1)
        results = s.execute()
        self.assertEqual(results[0].caseName, "Lorem Ipsum Dolor vs. USA")
        self.assertEqual(results[0].docketNumber, "23-98765")
        self.assertIn("15 May 2023", results[0].dateArgued_text)
        self.assertIn("15 May 2022", results[0].dateReargued_text)
        self.assertIn("15 May 2021", results[0].dateReargumentDenied_text)
        self.assertEqual(
            results[0].dateArgued, datetime.datetime(2023, 5, 15, 0, 0)
        )

        # Trigger a ManyToMany insert.
        audio_7.refresh_from_db()
        author = PersonFactory.create()
        audio_7.panel.add(author)
        # Confirm ManyToMany field is updated in the index.
        cd["q"] = "Lorem Ipsum Dolor vs. IRS"
        s, *_ = build_es_main_query(search_query, cd)
        self.assertEqual(s.count(), 1)
        results = s.execute()
        self.assertEqual(results[0].caseName, "Lorem Ipsum Dolor vs. IRS")
        self.assertEqual(results[0].panel_ids, [author.pk])

        # Confirm duration is updated in the index after Audio is updated.
        audio_7.duration = 322
        audio_7.save()
        audio_7.refresh_from_db()
        s, *_ = build_es_main_query(search_query, cd)
        self.assertEqual(s.count(), 1)
        results = s.execute()
        self.assertEqual(results[0].caseName, "Lorem Ipsum Dolor vs. IRS")
        self.assertEqual(results[0].duration, audio_7.duration)

        # Delete parent docket.
        docket_5.delete()
        # Confirm that docket-related audio objects are removed from the
        # index.
        cd["q"] = "Lorem Ipsum Dolor"
        s, *_ = build_es_main_query(search_query, cd)
        self.assertEqual(s.count(), 0)

    def test_oa_indexing_and_tasks_count(self) -> None:
        """Confirm an Audio is properly indexed in ES with the right number of
        indexing tasks.
        """

        # When the Audio is created the file processing is not complete.
        # The Audio indexing is avoided.
        with mock.patch(
            "cl.lib.es_signal_processor.es_save_document.si",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                es_save_document, *args, **kwargs
            ),
        ):
            audio = AudioFactory.create(
                case_name="Lorem Ipsum Dolor vs. USA",
                docket_id=self.docket.pk,
            )
        # 0 es_save_document task calls for Audio creation, due to processing
        # is not complete.
        self.reset_and_assert_task_count(expected=0)
        self.assertFalse(AudioDocument.exists(id=audio.pk))

        # Index the document for first time when file processing is completed.
        with mock.patch(
            "cl.lib.es_signal_processor.es_save_document.si",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                es_save_document, *args, **kwargs
            ),
        ):
            audio.save(
                update_fields=[
                    "processing_complete",
                ]
            )
        # 1 es_save_document task calls for Audio after processing is complete
        self.reset_and_assert_task_count(expected=1)
        self.assertTrue(AudioDocument.exists(id=audio.pk))

        # Update an Audio without changes.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            audio.save()
        # update_es_document task shouldn't be called on save() without changes
        self.reset_and_assert_task_count(expected=0)

        # Update an Audio tracked field.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            audio.case_name = "Bank vs America"
            audio.save()
        # update_es_document task should be called 1 on tracked fields updates
        self.reset_and_assert_task_count(expected=1)
        a_doc = AudioDocument.get(id=audio.pk)
        self.assertEqual(a_doc.caseName, "Bank vs America")

        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            audio.docket = self.docket_2
            audio.save()
        # update_es_document task should be called 1 on tracked fields updates
        self.reset_and_assert_task_count(expected=1)
        a_doc = AudioDocument.get(id=audio.pk)
        self.assertEqual(a_doc.docket_id, self.docket_2.pk)

        # Confirm an Audio is indexed if it doesn't exist in the
        # index on a tracked field update.
        self.delete_index("audio.Audio")
        self.create_index("audio.Audio")

        self.assertFalse(AudioDocument.exists(id=audio.pk))
        # Audio creation on update.
        with mock.patch(
            "cl.lib.es_signal_processor.update_es_document.delay",
            side_effect=lambda *args, **kwargs: self.count_task_calls(
                update_es_document, *args, **kwargs
            ),
        ):
            audio.case_name = "Lorem Ipsum"
            audio.save()

        # update_es_document task should be called 1 on tracked fields update
        self.reset_and_assert_task_count(expected=1)
        a_doc = AudioDocument.get(id=audio.pk)
        self.assertEqual(a_doc.caseName, "Lorem Ipsum")

        audio.delete()
