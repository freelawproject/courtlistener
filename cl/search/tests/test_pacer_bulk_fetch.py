import random
from unittest.mock import patch

from cl.recap.models import PacerFetchQueue
from cl.search.factories import (
    CourtFactory,
    DocketEntryFactory,
    DocketFactory,
    RECAPDocumentFactory,
)
from cl.search.management.commands.pacer_bulk_fetch import Command
from cl.search.models import Docket, RECAPDocument
from cl.tests.cases import TestCase
from cl.users.factories import UserFactory


class BulkFetchPacerDocsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory()

        cls.courts = [CourtFactory() for _ in range(6)]

        dockets_per_court = 15
        entries_per_docket = 8

        page_count_ranges = [
            (1000, 2000),
            (500, 999),
            (100, 499),
            (1, 99),
        ]
        cls.big_page_count = 1000
        cls.big_docs_count = 0

        for court in cls.courts:
            [DocketFactory(court=court) for _ in range(dockets_per_court)]

        for docket in Docket.objects.all():
            docket_entries = [
                DocketEntryFactory(docket=docket)
                for _ in range(entries_per_docket)
            ]

            for de in docket_entries:
                min_pages, max_pages = random.choice(page_count_ranges)
                page_count = random.randint(min_pages, max_pages)
                cls.big_docs_count += 1 if page_count >= 1000 else 0
                RECAPDocumentFactory(
                    docket_entry=de,
                    page_count=page_count,
                    is_available=False,
                )

    def setUp(self):
        self.command = Command()
        self.big_docs_created = RECAPDocument.objects.filter(
            page_count__gte=self.big_page_count,
            is_available=False,
            pacer_doc_id__isnull=False,
        )
        self.assertEqual(self.big_docs_count, self.big_docs_created.count())

    @patch("time.sleep")
    @patch("cl.search.management.commands.pacer_bulk_fetch.do_pacer_fetch")
    def test_document_filtering(
        self,
        mock_fetch,
        mock_sleep,
    ):
        """Test document filtering according to command arguments passed."""
        self.command.handle(
            min_page_count=self.big_page_count,
            request_interval=1.0,
            username=self.user.username,
            testing=True,
        )

        self.assertEqual(
            mock_fetch.call_count,
            self.big_docs_count,
            f"Expected {self.big_docs_count} documents to be processed",
        )

        fetch_queues = PacerFetchQueue.objects.all()
        self.assertEqual(
            fetch_queues.count(),
            self.big_docs_count,
            f"Expected {self.big_docs_count} fetch queues",
        )

        enqueued_doc_ids = [fq.recap_document_id for fq in fetch_queues]
        big_doc_ids = self.big_docs_created.values_list("id", flat=True)
        self.assertSetEqual(set(enqueued_doc_ids), set(big_doc_ids))

    @patch("time.sleep")
    @patch("cl.search.management.commands.pacer_bulk_fetch.do_pacer_fetch")
    def test_rate_limiting(self, mock_fetch, mock_sleep):
        """Test rate limiting."""
        interval = 2.0
        self.command.handle(
            min_page_count=1000,
            request_interval=interval,
            username=self.user.username,
            testing=True,
        )

        self.assertEqual(
            mock_sleep.call_count,
            mock_fetch.call_count - 1,
            "Sleep should be called between each fetch",
        )

        for call in mock_sleep.call_args_list:
            self.assertEqual(
                call.args[0],
                interval,
                f"Expected sleep interval of {interval} seconds",
            )

    @patch("time.sleep")
    @patch("cl.search.management.commands.pacer_bulk_fetch.do_pacer_fetch")
    def test_error_handling(self, mock_fetch, mock_sleep):
        """Test that errors are handled gracefully"""
        mock_fetch.side_effect = Exception("PACER API error")

        self.command.handle(
            min_page_count=1000,
            request_interval=1.0,
            username=self.user.username,
            testing=True,
        )

        self.assertEqual(
            PacerFetchQueue.objects.count(),
            self.big_docs_count,
        )

    @patch("time.sleep")
    @patch("cl.search.management.commands.pacer_bulk_fetch.do_pacer_fetch")
    def test_round_robin(self, mock_fetch, mock_sleep):
        """
        Verify that each call to 'execute_round' never processes the same court
        more than once.
        """
        calls_per_round = []
        original_execute_round = self.command.execute_round

        def track_rounds_side_effect(remaining_courts, options, is_last_round):
            """
            Compares the mock_fetch calls before and after calling execute_round,
            then saves new calls that occurred during this round.
            """
            start_index = len(mock_fetch.call_args_list)
            updated_remaining = original_execute_round(
                remaining_courts, options, is_last_round
            )
            end_index = len(mock_fetch.call_args_list)
            current_round_calls = mock_fetch.call_args_list[
                start_index:end_index
            ]
            calls_per_round.append(current_round_calls)

            return updated_remaining

        with patch.object(
            Command, "execute_round", side_effect=track_rounds_side_effect
        ):
            # Run command with patched execute_round to save do_pacer_fetch
            # calls in each round
            self.command.handle(
                min_page_count=1000,
                request_interval=1.0,
                username=self.user.username,
                testing=True,
            )

        for round_index, round_calls in enumerate(calls_per_round, start=1):
            court_ids_this_round = []

            for call in round_calls:
                fetch_queue_obj = call.args[0]
                court_id = (
                    fetch_queue_obj.recap_document.docket_entry.docket.court_id
                )
                court_ids_this_round.append(court_id)

            self.assertEqual(
                len(court_ids_this_round),
                len(set(court_ids_this_round)),
                f"Round {round_index} had duplicate courts: {court_ids_this_round}",
            )
