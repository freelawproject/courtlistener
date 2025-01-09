import random
from unittest.mock import MagicMock, patch

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

    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.CeleryThrottle.maybe_wait"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.build_pdf_retrieval_task_chain"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.get_or_cache_pacer_cookies"
    )
    def test_document_filtering(
        self,
        mock_pacer_cookies,
        mock_chain_builder,
        mock_throttle,
    ):
        """Test document filtering according to command arguments passed."""
        # Setup mock chain
        mock_chain = MagicMock()
        mock_chain_builder.return_value = mock_chain

        self.command.handle(
            min_page_count=self.big_page_count,
            request_interval=1.0,
            username=self.user.username,
            testing=True,
        )

        self.assertEqual(
            mock_chain.apply_async.call_count,
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

    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.CeleryThrottle.maybe_wait"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.build_pdf_retrieval_task_chain"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.get_or_cache_pacer_cookies"
    )
    def test_rate_limiting(
        self,
        mock_pacer_cookies,
        mock_chain_builder,
        mock_throttle,
    ):
        """Test rate limiting."""
        # Setup mock chain
        mock_chain = MagicMock()
        mock_chain_builder.return_value = mock_chain

        rate_limit = "10/m"
        self.command.handle(
            min_page_count=1000,
            rate_limit=rate_limit,
            username=self.user.username,
            testing=True,
        )

        # Verify the rate limit was passed correctly
        for call in mock_chain_builder.call_args_list:
            with self.subTest(call=call):
                _, kwargs = call
                self.assertEqual(
                    kwargs.get("rate_limit"),
                    rate_limit,
                    "Rate limit should be passed to chain builder",
                )

        self.assertEqual(
            mock_throttle.call_count,
            self.big_docs_count,
            "CeleryThrottle.maybe_wait should be called for each document",
        )

    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.CeleryThrottle.maybe_wait"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.build_pdf_retrieval_task_chain"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.get_or_cache_pacer_cookies"
    )
    def test_error_handling(
        self,
        mock_pacer_cookies,
        mock_chain_builder,
        mock_throttle,
    ):
        """Test that errors are handled gracefully"""
        mock_chain_builder.side_effect = Exception("Chain building error")

        self.command.handle(
            min_page_count=1000,
            username=self.user.username,
            testing=True,
        )

        self.assertEqual(
            PacerFetchQueue.objects.count(),
            self.big_docs_count,
            "PacerFetchQueue objects should still be created even if chain building fails",
        )

    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.CeleryThrottle.maybe_wait"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.build_pdf_retrieval_task_chain"
    )
    @patch(
        "cl.search.management.commands.pacer_bulk_fetch.get_or_cache_pacer_cookies"
    )
    def test_round_robin(
        self,
        mock_pacer_cookies,
        mock_chain_builder,
        mock_throttle,
    ):
        """
        Verify that each call to 'execute_round' never processes the same court
        more than once.
        """
        mock_chain = MagicMock()
        mock_chain_builder.return_value = mock_chain

        calls_per_round = []
        original_execute_round = self.command.execute_round

        def track_rounds_side_effect(remaining_courts, options, is_last_round):
            """
            Tracks PacerFetchQueue creation before and after calling execute_round
            to identify which courts were processed in each round.
            """
            start_count = PacerFetchQueue.objects.count()
            updated_remaining = original_execute_round(
                remaining_courts, options, is_last_round
            )
            end_count = PacerFetchQueue.objects.count()

            # Get the fetch queues created in this round
            current_round_queues = PacerFetchQueue.objects.order_by("pk")[
                start_count:end_count
            ]
            calls_per_round.append(current_round_queues)

            return updated_remaining

        with patch.object(
            Command, "execute_round", side_effect=track_rounds_side_effect
        ):
            self.command.handle(
                min_page_count=1000,
                request_interval=1.0,
                username=self.user.username,
                testing=True,
            )

        for round_index, round_queues in enumerate(calls_per_round, start=1):
            court_ids_this_round = []

            for queue in round_queues:
                court_id = queue.recap_document.docket_entry.docket.court_id
                court_ids_this_round.append(court_id)

            with self.subTest(
                court_ids_this_round=court_ids_this_round,
                round_index=round_index,
            ):
                self.assertEqual(
                    len(court_ids_this_round),
                    len(set(court_ids_this_round)),
                    f"Round {round_index} had duplicate courts: {court_ids_this_round}",
                )
