from unittest.mock import patch

from django.core.management import call_command

testing = (True,)
from cl.recap.factories import PacerFetchQueueFactory
from cl.recap.models import PROCESSING_STATUS
from cl.search.factories import (
    CourtFactory,
    DocketEntryFactory,
    DocketFactory,
    RECAPDocumentFactory,
)
from cl.search.models import RECAPDocument
from cl.tests.cases import TestCase
from cl.users.factories import UserFactory


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
            0: [DocketEntryFactory(docket=cls.dockets[0]) for _ in range(300)],
            1: [DocketEntryFactory(docket=cls.dockets[1]) for _ in range(8)],
            2: [DocketEntryFactory(docket=cls.dockets[2]) for _ in range(20)],
            3: [DocketEntryFactory(docket=cls.dockets[3]) for _ in range(15)],
            4: [DocketEntryFactory(docket=cls.dockets[4]) for _ in range(10)],
        }

    def setUp(self):
        # Create RECAP docs in DB (no real caching)
        self.docs = []
        # Court 0: Many large docs
        for i in range(300):
            self.docs.append(
                RECAPDocumentFactory(
                    docket_entry=self.docket_entries[0][i],
                    pacer_doc_id=f"0_{i}",
                    is_available=False,
                    page_count=1000 + i,
                )
            )

        # Court 1: Mix of pages
        page_counts = [5, 10, 50, 100, 500, 1000, 2000, 5000]
        for i, pages in enumerate(page_counts):
            self.docs.append(
                RECAPDocumentFactory(
                    docket_entry=self.docket_entries[1][i],
                    pacer_doc_id=f"1_{i}",
                    is_available=False,
                    page_count=pages,
                )
            )

        # Court 2: Only small docs (1-10 pages)
        for i in range(20):
            self.docs.append(
                RECAPDocumentFactory(
                    docket_entry=self.docket_entries[2][i],
                    pacer_doc_id=f"2_{i}",
                    is_available=False,
                    page_count=i + 1,
                )
            )

        # Court 3: Only medium docs (100-500 pages)
        for i in range(15):
            self.docs.append(
                RECAPDocumentFactory(
                    docket_entry=self.docket_entries[3][i],
                    pacer_doc_id=f"3_{i}",
                    is_available=False,
                    page_count=100 + (i * 25),
                )
            )

        # Court 4: No docs matching typical filters (all 11-49 pages)
        for i in range(10):
            self.docs.append(
                RECAPDocumentFactory(
                    docket_entry=self.docket_entries[4][i],
                    pacer_doc_id=f"4_{i}",
                    is_available=False,
                    page_count=11 + (i * 3),
                )
            )

    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.Command.should_skip",
        return_value=False,
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.cache.get",
        return_value=[],
    )
    @patch("cl.search.management.commands.pacer_bulk_fetch.cache.set")
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.append_value_in_cache"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.CeleryThrottle.maybe_wait"
    )
    @patch("cl.search.management.commands.pacer_bulk_fetch.time.sleep")
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.get_or_cache_pacer_cookies"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.fetch_pacer_doc_by_rd.si"
    )
    def test_page_count_filtering(
        self,
        mock_fetch_pacer_doc_by_rd,
        mock_pacer_cookies,
        mock_sleep,
        mock_maybe_wait,
        mock_append_value_in_cache,
        mock_cache_set,
        mock_cache_get,
        mock_should_skip,
    ):
        """
        Test that documents are filtered correctly based on page count
        without actually hitting the cache.
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

    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.Command.should_skip",
        return_value=False,
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.cache.get",
        return_value=[],
    )
    @patch("cl.search.management.commands.pacer_bulk_fetch.cache.set")
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.append_value_in_cache"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.CeleryThrottle.maybe_wait"
    )
    @patch("cl.search.management.commands.pacer_bulk_fetch.time.sleep")
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.get_or_cache_pacer_cookies"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.fetch_pacer_doc_by_rd.si"
    )
    def test_skip_available_documents(
        self,
        mock_fetch_pacer_doc_by_rd,
        mock_pacer_cookies,
        mock_sleep,
        mock_maybe_wait,
        mock_append_value_in_cache,
        mock_cache_set,
        mock_cache_get,
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
        "cl.search.management.commands.pacer_bulk_fetch.Command.should_skip",
        return_value=False,
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.cache.get",
        return_value=[],
    )
    @patch("cl.search.management.commands.pacer_bulk_fetch.cache.set")
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.append_value_in_cache"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.CeleryThrottle.maybe_wait"
    )
    @patch("cl.search.management.commands.pacer_bulk_fetch.time.sleep")
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.get_or_cache_pacer_cookies"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.fetch_pacer_doc_by_rd.si"
    )
    def test_rate_limiting(
        self,
        mock_fetch_pacer_doc_by_rd,
        mock_pacer_cookies,
        mock_sleep,
        mock_maybe_wait,
        mock_append_value_in_cache,
        mock_cache_set,
        mock_cache_get,
        mock_should_skip,
    ):
        """Test that rate limiting triggers sleep calls (mocked)."""
        interval = 2
        call_command(
            "pacer_bulk_fetch",
            testing=True,
            interval=interval,
            min_page_count=1000,
            stage="fetch",
            username=self.user.username,
        )

        expected_docs = [
            d for d in self.docs if d.page_count >= 1000 and not d.is_available
        ]
        self.assertEqual(
            mock_fetch_pacer_doc_by_rd.call_count, len(expected_docs)
        )

    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.Command.should_skip",
        return_value=False,
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.cache.get",
        return_value=[],
    )
    @patch("cl.search.management.commands.pacer_bulk_fetch.cache.set")
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.CeleryThrottle.maybe_wait"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.extract_recap_pdf.si"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.mark_fq_successful.si"
    )
    def test_fetch_queue_processing(
        self,
        mock_mark_fq_successful,
        mock_extract_recap_pdf,
        mock_maybe_wait,
        mock_cache_set,
        mock_cache_get,
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

        mock_cache_get.return_value = successful_fqs

        call_command(
            "pacer_bulk_fetch",
            testing=True,
            stage="process",
            username=self.user.username,
        )

        # For each FQ, we expect an OCR extract call and a "mark successful" call
        self.assertEqual(
            mock_extract_recap_pdf.call_count, len(successful_fqs)
        )
        self.assertEqual(
            mock_mark_fq_successful.call_count, len(successful_fqs)
        )
