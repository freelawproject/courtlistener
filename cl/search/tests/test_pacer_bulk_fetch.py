from datetime import timedelta
from unittest.mock import MagicMock, patch

import time_machine
from django.core.cache import cache as django_cache
from django.core.management import call_command
from django.utils import timezone

from cl.recap.factories import PacerFetchQueueFactory
from cl.recap.models import PROCESSING_STATUS, PacerFetchQueue
from cl.search.factories import (
    CourtFactory,
    DocketEntryFactory,
    DocketFactory,
    RECAPDocumentFactory,
)
from cl.search.management.commands.pacer_bulk_fetch import (
    Command,
    append_value_in_cache,
)
from cl.search.models import RECAPDocument
from cl.tests.cases import TestCase
from cl.tests.utils import MockResponse
from cl.users.factories import UserFactory


def _clean_cache_keys(keys):
    for key in keys:
        django_cache.delete(key)


@patch(
    "cl.search.management.commands.pacer_bulk_fetch.Command.should_skip",
    return_value=False,
)
@patch(
    "cl.search.management.commands.pacer_bulk_fetch.Command.docs_to_process_cache_key",
    return_value="pacer_bulk_fetch.test_page_count_filtering.docs_to_process",
)
@patch(
    "cl.search.management.commands.pacer_bulk_fetch.Command.timed_out_docs_cache_key",
    return_value="pacer_bulk_fetch.test_page_count_filtering.timed_out_docs",
)
@patch("cl.search.management.commands.pacer_bulk_fetch.time.sleep")
@patch(
    "cl.search.management.commands.pacer_bulk_fetch.get_or_cache_pacer_cookies"
)
@patch(
    "cl.search.management.commands.pacer_bulk_fetch.fetch_pacer_doc_by_rd_and_mark_fq_completed.si"
)
class BulkFetchPacerDocsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory()
        cls.courts = []
        for i in range(5):
            court = CourtFactory(id=f"ca{i}", jurisdiction="F")
            cls.courts.append(court)

        cls.dockets = []
        for court in cls.courts:
            docket = DocketFactory(court=court)
            cls.dockets.append(docket)

        # Docket entries by court index
        cls.docket_entries = {
            0: [DocketEntryFactory(docket=cls.dockets[0]) for _ in range(15)],
            1: [DocketEntryFactory(docket=cls.dockets[1]) for _ in range(8)],
            2: [DocketEntryFactory(docket=cls.dockets[2]) for _ in range(12)],
            3: [DocketEntryFactory(docket=cls.dockets[3]) for _ in range(7)],
            4: [DocketEntryFactory(docket=cls.dockets[4]) for _ in range(5)],
        }

        # Create RECAP docs in DB (no real caching)
        cls.docs = []
        # Court 0: Many large docs
        for i in range(15):
            cls.docs.append(
                RECAPDocumentFactory(
                    docket_entry=cls.docket_entries[0][i],
                    pacer_doc_id=f"0_{i}",
                    is_available=False,
                    page_count=1000 + i,
                )
            )

        # Court 1: Mix of pages
        page_counts = [5, 10, 50, 100, 500, 1000, 2000, 5000]
        for i, pages in enumerate(page_counts):
            cls.docs.append(
                RECAPDocumentFactory(
                    docket_entry=cls.docket_entries[1][i],
                    pacer_doc_id=f"1_{i}",
                    is_available=False,
                    page_count=pages,
                )
            )

        # Court 2: Only small docs (1-10 pages)
        for i in range(12):
            cls.docs.append(
                RECAPDocumentFactory(
                    docket_entry=cls.docket_entries[2][i],
                    pacer_doc_id=f"2_{i}",
                    is_available=False,
                    page_count=i + 1,
                )
            )

        # Court 3: Only medium docs (100-500 pages)
        for i in range(7):
            cls.docs.append(
                RECAPDocumentFactory(
                    docket_entry=cls.docket_entries[3][i],
                    pacer_doc_id=f"3_{i}",
                    is_available=False,
                    page_count=100 + (i * 25),
                )
            )

        # Court 4: No docs matching typical filters (all 11-49 pages)
        for i in range(5):
            cls.docs.append(
                RECAPDocumentFactory(
                    docket_entry=cls.docket_entries[4][i],
                    pacer_doc_id=f"4_{i}",
                    is_available=False,
                    page_count=11 + (i * 3),
                )
            )

    def tearDown(self):
        _clean_cache_keys(
            [
                "pacer_bulk_fetch.test_page_count_filtering.docs_to_process",
                "pacer_bulk_fetch.test_page_count_filtering.timed_out_docs",
            ]
        )

    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.append_value_in_cache",
        wraps=append_value_in_cache,
    )
    def test_page_count_filtering(
        self,
        mock_append_value_in_cache,
        mock_fetch_pacer_doc_by_rd,
        mock_pacer_cookies,
        mock_sleep,
        mock_timed_out_cache_key,
        mock_fetched_cache_key,
        mock_should_skip,
    ):
        """
        Test that documents are filtered correctly based on page count.
        """
        call_command(
            "pacer_bulk_fetch",
            testing=True,
            min_page_count=1000,
            stage="fetch",
            username=self.user.username,
        )

        # Verify that we only tried to fetch docs with >= 1000 pages
        expected_docs = [
            d for d in self.docs if d.page_count >= 1000 and not d.is_available
        ]
        self.assertEqual(
            mock_fetch_pacer_doc_by_rd.call_count,
            len(expected_docs),
            f"expected {len(expected_docs)} calls (1)",
        )

        self.assertTrue(mock_append_value_in_cache.called)

    def test_skip_available_documents(
        self,
        mock_fetch_pacer_doc_by_rd,
        mock_pacer_cookies,
        mock_sleep,
        mock_timed_out_cache_key,
        mock_fetched_cache_key,
        mock_should_skip,
    ):
        """
        Test that documents already available in CL are skipped
        (i.e., not enqueued).
        """

        # Make some documents available
        docs_available_in_cl = []
        for court_idx in range(5):
            court_docs = [
                d
                for d in self.docs
                if d.docket_entry.docket.court_id == f"ca{court_idx}"
            ]
            docs_available_in_cl.extend(
                court_docs[:2]
            )  # first 2 docs from each court

        RECAPDocument.objects.filter(
            pk__in=[d.pk for d in docs_available_in_cl]
        ).update(is_available=True)

        call_command(
            "pacer_bulk_fetch",
            min_page_count=0,
            testing=True,
            stage="fetch",
            username=self.user.username,
        )

        # Check how many docs were actually fetched
        expected_unavailable = [
            d
            for d in self.docs
            if d.pk not in [ad.pk for ad in docs_available_in_cl]
        ]
        self.assertEqual(
            mock_fetch_pacer_doc_by_rd.call_count, len(expected_unavailable)
        )

        # None of the available docs should be in the calls
        called_args = [
            args[0] for args, _ in mock_fetch_pacer_doc_by_rd.call_args_list
        ]
        for doc in docs_available_in_cl:
            with self.subTest(doc=doc):
                self.assertNotIn(doc.pk, called_args)

    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.extract_recap_pdf.si"
    )
    def test_fetch_queue_processing(
        self,
        mock_extract_recap_pdf,
        mock_fetch_pacer_doc_by_rd,
        mock_pacer_cookies,
        mock_sleep,
        mock_timed_out_cache_key,
        mock_fetched_cache_key,
        mock_should_skip,
    ):
        """
        Test that fetch queues are processed correctly (processing stage).
        """
        successful_fqs = []
        for doc in self.docs[:3]:
            fq = PacerFetchQueueFactory(
                recap_document=doc,
                status=PROCESSING_STATUS.SUCCESSFUL,
                user_id=self.user.pk,
            )
            doc.filepath_local = "/fake/path.pdf"
            doc.is_available = True
            doc.ocr_status = None
            doc.save()
            successful_fqs.append((doc.pk, fq.pk))

        django_cache.set(mock_fetched_cache_key.return_value, successful_fqs)

        call_command(
            "pacer_bulk_fetch",
            testing=True,
            stage="process",
            username=self.user.username,
        )

        # For each FQ, we expect an OCR extract call and a "mark successful" call
        self.assertEqual(
            mock_extract_recap_pdf.call_count,
            len(successful_fqs),
            "extract_recap_pdf",
        )


@patch(
    "cl.search.management.commands.pacer_bulk_fetch.Command.docs_to_process_cache_key",
    return_value="pacer_bulk_fetch.test_identify_documents_filtering.docs_to_process",
)
@patch(
    "cl.search.management.commands.pacer_bulk_fetch.Command.timed_out_docs_cache_key",
    return_value="pacer_bulk_fetch.test_identify_documents_filtering.timed_out_docs",
)
class PacerBulkFetchUnitTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory()
        cls.court = CourtFactory(id="ca1", jurisdiction="F")
        cls.docket = DocketFactory(court=cls.court)
        cls.docket_entries = [
            DocketEntryFactory(docket=cls.docket) for _ in range(5)
        ]

    def setUp(self):
        self.command = Command()
        self.command.user = self.user
        self.command.options = {
            "testing": True,
            "min_page_count": 100,
            "max_page_count": 10_000,
        }
        self.command.interval = 2
        self.command.total_launched = 0
        self.command.throttle = MagicMock()

        self.docs = []
        for i, de in enumerate(self.docket_entries):
            doc = RECAPDocumentFactory(
                docket_entry=de,
                pacer_doc_id=f"1_{i}",
                is_available=False,
                page_count=100 + (i * 50),
            )
            self.docs.append(doc)

    def tearDown(self):
        _clean_cache_keys(
            [
                "pacer_bulk_fetch.test_page_count_filtering.docs_to_process",
                "pacer_bulk_fetch.test_page_count_filtering.timed_out_docs",
            ]
        )

    def test_identify_documents_filtering(
        self,
        mock_timed_out_cache_key,
        mock_fetched_cache_key,
    ):
        """Test that identify_documents correctly filters documents based on criteria"""
        self.command.options["min_page_count"] = 200
        self.command.options["max_page_count"] = 300

        self.command.identify_documents()

        # We should only get docs with page counts between 200-300
        expected_docs = [
            doc.id
            for doc in self.docs
            if 200 <= doc.page_count <= 300 and not doc.is_available
        ]
        actual_docs = [doc["id"] for doc in self.command.recap_documents]
        self.assertSetEqual(
            set(expected_docs),
            set(actual_docs),
            "Should only include docs matching page count criteria",
        )

    def test_identify_documents_cache_exclusion(
        self,
        mock_timed_out_cache_key,
        mock_fetched_cache_key,
    ):
        """Test that identify_documents excludes previously processed documents"""
        # Set up cache with some "previously processed" documents
        cache_key = mock_fetched_cache_key.return_value
        previously_processed = [(self.docs[0].pk, 1), (self.docs[1].pk, 2)]
        django_cache.set(cache_key, previously_processed)

        # But mark one as timed out, so it should be retried
        timed_out_key = mock_timed_out_cache_key.return_value
        timed_out = [(self.docs[1].pk, 2)]
        django_cache.set(timed_out_key, timed_out)

        self.command.identify_documents()

        excluded_docs = [self.docs[0].pk]
        actual_docs = [doc["id"] for doc in self.command.recap_documents]

        self.assertNotIn(
            excluded_docs[0],
            actual_docs,
            "Previously processed docs should be excluded",
        )
        self.assertIn(
            self.docs[1].pk, actual_docs, "Timed out docs should be included"
        )

    def test_should_skip_court_not_in_progress(
        self, mock_timed_out_cache_key, mock_fetched_cache_key
    ):
        """Test should_skip when court has no fetch in progress"""
        self.command.fetches_in_progress = {}

        result = self.command.should_skip("ca1")

        self.assertFalse(
            result, "Should not skip court with no fetch in progress"
        )

    def test_should_skip_with_time_conditions(
        self,
        mock_timed_out_cache_key,
        mock_fetched_cache_key,
    ):
        """Test should_skip under different time conditions"""
        test_cases = [
            {
                "name": "recent completion",
                "time_elapsed": 1,
                "expected_skip": True,
            },
            {
                "name": "enough time passed",
                "time_elapsed": self.command.interval + 1,
                "expected_skip": False,
            },
        ]

        current_time = timezone.now()
        for case in test_cases:
            with self.subTest(case=case["name"]):
                fq = PacerFetchQueueFactory(
                    recap_document=self.docs[0],
                    status=PROCESSING_STATUS.SUCCESSFUL,
                    date_completed=current_time,
                    user=self.user,
                )
                self.command.fetches_in_progress = {"ca1": (fq.pk, 0)}

                with time_machine.travel(
                    current_time + timedelta(seconds=case["time_elapsed"]),
                    tick=False,
                ):
                    result = self.command.should_skip("ca1")

                self.assertEqual(
                    result,
                    case["expected_skip"],
                    f"should_skip returned {result} for {case['name']}",
                )

    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.fetch_pacer_doc_by_rd_and_mark_fq_completed.si"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.Command.should_skip",
        return_value=False,
    )
    def test_fetch_next_doc_in_court(
        self,
        mock_should_skip,
        mock_fetch,
        mock_timed_out_cache_key,
        mock_fetched_cache_key,
    ):
        """
        Test fetch_next_doc_in_court removes a doc from the court and
        updates fetches_in_progress.
        """
        court_id = "ca1"

        self.command.recap_documents = [self.docs[0]]
        remaining_courts = {court_id: [{"id": self.docs[0].pk}]}
        original_count = len(remaining_courts[court_id])

        self.command.fetch_next_doc_in_court(court_id, remaining_courts)

        self.assertEqual(
            len(remaining_courts[court_id]),
            original_count - 1,
            "Document should be removed from remaining_courts",
        )

        fq_pk = PacerFetchQueue.objects.get(recap_document=self.docs[0]).pk
        mock_fetch.assert_called_once()
        self.assertEqual(
            self.command.fetches_in_progress[court_id][0],
            fq_pk,
        )

    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.fetch_pacer_doc_by_rd_and_mark_fq_completed.si"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.get_or_cache_pacer_cookies"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.Command.should_skip",
        return_value=False,
    )
    @patch("cl.search.management.commands.pacer_bulk_fetch.time.sleep")
    def test_fetch_docs_from_pacer_no_sleep(
        self,
        mock_sleep,
        mock_should_skip,
        mock_pacer_cookies,
        mock_fetch,
        mock_timed_out_cache_key,
        mock_fetched_cache_key,
    ):
        """Test fetch_docs_from_pacer when no delays are needed"""
        self.command.courts_with_docs = {
            "ca1": [{"id": doc.pk} for doc in self.docs[:2]]
        }

        self.command.fetch_docs_from_pacer()

        mock_sleep.assert_not_called()

        self.assertEqual(
            len(self.command.fetches_in_progress),
            0,
            "fetches_in_progress should be empty",
        )


@patch(
    "cl.search.management.commands.pacer_bulk_fetch.Command.docs_to_process_cache_key",
    return_value="pacer_bulk_fetch.test_page_count_filtering.docs_to_process",
)
@patch(
    "cl.search.management.commands.pacer_bulk_fetch.Command.timed_out_docs_cache_key",
    return_value="pacer_bulk_fetch.test_page_count_filtering.timed_out_docs",
)
@patch("cl.search.management.commands.pacer_bulk_fetch.time.sleep")
@patch("cl.recap.tasks.get_pacer_cookie_from_cache")
@patch(
    "cl.recap.tasks.is_pacer_court_accessible",
    side_effect=lambda a: True,
)
class BulkFetchPacerIntegrationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory()
        cls.courts = []
        court = CourtFactory(id="ca1", jurisdiction="F")
        cls.docket_1 = DocketFactory(court=court)
        cls.docket_2 = DocketFactory(court=court)
        cls.docket_3 = DocketFactory(court=court)

        de_1 = DocketEntryFactory(docket=cls.docket_1)
        de_2 = DocketEntryFactory(docket=cls.docket_2)
        de_3 = DocketEntryFactory(docket=cls.docket_2)

        # Create RECAP docs in DB (no real caching)
        des = [de_1, de_2]
        cls.rds_to_retrieve = []
        for i, de in enumerate(des):
            cls.rds_to_retrieve.append(
                RECAPDocumentFactory(
                    docket_entry=de,
                    pacer_doc_id=f"0{i}",
                    is_available=False,
                    page_count=1000 + i,
                )
            )

        RECAPDocumentFactory(
            docket_entry=de_3,
            pacer_doc_id=f"1234",
            is_available=False,
            page_count=100,
        )

    def tearDown(self):
        _clean_cache_keys(
            [
                "pacer_bulk_fetch.test_page_count_filtering.docs_to_process",
                "pacer_bulk_fetch.test_page_count_filtering.timed_out_docs",
            ]
        )

    @patch(
        "cl.recap.tasks.download_pacer_pdf_by_rd",
        side_effect=lambda z, x, c, v, b, de_seq_num: (
            MockResponse(
                200,
                b"binary content",
            ),
            "OK",
        ),
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.Command.enough_time_elapsed",
        return_value=True,
    )
    def test_pacer_bulk_fetch_integration(
        self,
        mock_enough_time_elapsed,
        mock_download_pacer_pdf_by_rd,
        mock_is_pacer_court_accessible,
        mock_pacer_cookies,
        mock_sleep,
        mock_timed_out_cache_key,
        mock_fetched_cache_key,
    ):
        """pacer_bulk_fetch command integration test"""

        all_rds = RECAPDocument.objects.all()
        self.assertEqual(
            set(
                status
                for status in all_rds.values_list("is_available", flat=True)
            ),
            {False},
        )
        call_command(
            "pacer_bulk_fetch",
            testing=True,
            min_page_count=1000,
            stage="fetch",
            username=self.user.username,
        )

        rds_purchased = RECAPDocument.objects.filter(is_available=True)
        self.assertEqual(rds_purchased.count(), 2)
        self.assertEqual(
            set(
                status
                for status in rds_purchased.values_list(
                    "is_available", flat=True
                )
            ),
            {True},
        )

    @patch(
        "cl.recap.tasks.download_pacer_pdf_by_rd",
        side_effect=lambda z, x, c, v, b, de_seq_num: (
            MockResponse(
                200,
                None,
            ),
            "OK",
        ),
    )
    def test_abort_fqs_after_retries(
        self,
        mock_download_pacer_pdf_by_rd,
        mock_is_pacer_court_accessible,
        mock_pacer_cookies,
        mock_sleep,
        mock_timed_out_cache_key,
        mock_fetched_cache_key,
    ):
        """pacer_bulk_fetch command integration log max retried docs"""

        all_rds = RECAPDocument.objects.all()
        self.assertEqual(
            set(
                status
                for status in all_rds.values_list("is_available", flat=True)
            ),
            {False},
        )
        call_command(
            "pacer_bulk_fetch",
            testing=True,
            min_page_count=1000,
            stage="fetch",
            username=self.user.username,
        )

        rds_purchased = RECAPDocument.objects.filter(is_available=True)
        self.assertEqual(rds_purchased.count(), 0)
        cached_timed_out = django_cache.get(
            mock_timed_out_cache_key.return_value, []
        )

        rds_timed_out = set(rd_fq_pair[0] for rd_fq_pair in cached_timed_out)
        self.assertEqual(rds_timed_out, {rd.pk for rd in self.rds_to_retrieve})
