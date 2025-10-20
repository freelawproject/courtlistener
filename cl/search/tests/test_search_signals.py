from dataclasses import dataclass
from unittest.mock import Mock, patch

from django.db.models.signals import post_save
from django.test import override_settings

from cl.lib.redis_utils import get_redis_interface
from cl.search.factories import (
    CourtFactory,
    DocketEntryFactory,
    DocketFactory,
    RECAPDocumentFactory,
)
from cl.search.models import Docket, RECAPDocument
from cl.search.signals import handle_recap_doc_change
from cl.tests.cases import TestCase


# Test that event hits the receiver function
class RECAPDocumentSignalTests(TestCase):
    def setUp(self):
        post_save.disconnect(handle_recap_doc_change, sender=RECAPDocument)
        self.mock_receiver = Mock()
        post_save.connect(self.mock_receiver, sender=RECAPDocument)

    def test_recapdoc_save_emit_signal(self):
        recap_doc = RECAPDocumentFactory.create(
            plain_text="In Fisher v. SD Protection Inc., 948 F.3d 593 (2d Cir. 2020), the Second Circuit held that in the context of settlement of FLSA and NYLL cases, which must be approved by the trial court in accordance with Cheeks v. Freeport Pancake House, Inc., 796 F.3d 199 (2d Cir. 2015), the district court abused its discretion in limiting the amount of recoverable fees to a percentage of the recovery by the successful plaintiffs. But also: sdjnfdsjnk. Fisher, 948 F.3d at 597.",
            ocr_status=RECAPDocument.OCR_UNNECESSARY,
            docket_entry=DocketEntryFactory(),
        )

        recap_doc.save(update_fields=["ocr_status", "plain_text"])
        self.assertTrue(self.mock_receiver.called)


@dataclass
class ReceiverTestCase:
    update_fields: list[str] | None
    ocr_status: RECAPDocument.OCR_STATUSES
    expect_enqueue: bool


class RECAPDocumentReceiverTests(TestCase):
    def test_receiver_enqueues_task(self):
        test_cases: list[ReceiverTestCase] = [
            ReceiverTestCase(
                update_fields=["plain_text", "ocr_status"],
                ocr_status=RECAPDocument.OCR_UNNECESSARY,
                expect_enqueue=True,
            ),  # test that task is enq'd when the relevant fields are updated and ocr_status qualifies
            ReceiverTestCase(
                update_fields=["plain_text"],
                ocr_status=RECAPDocument.OCR_FAILED,
                expect_enqueue=False,  # test that task is not enq'd when the ocr_status does not qualify
            ),
            ReceiverTestCase(
                update_fields=None,
                ocr_status=RECAPDocument.OCR_COMPLETE,
                expect_enqueue=False,  # test that task is not enq'd when no update_fields even if ocr_status qualifies
            ),
            ReceiverTestCase(
                update_fields=["document_type"],
                ocr_status=RECAPDocument.OCR_COMPLETE,
                expect_enqueue=False,  # test that task is not enq'd when no relevant update_fields
            ),
        ]

        for test_case in test_cases:
            with self.subTest(test_case=test_case):
                with patch(
                    "cl.citations.tasks.find_citations_and_parantheticals_for_recap_documents.apply_async"
                ) as mock_apply:
                    recap_doc = RECAPDocumentFactory.create(
                        plain_text='"During the whole of his trip down town and return[,] Cornish had been ill, the journey being marked by frequent interruptions necessitated by the condition of his stomach and bowels. People v. Molineux, 168 NY 264, 275-276 (N.Y. 1901)."',
                        ocr_status=test_case.ocr_status,
                        docket_entry=DocketEntryFactory(),
                    )

                    recap_doc.save(update_fields=test_case.update_fields)

                    if test_case.expect_enqueue:
                        mock_apply.assert_called_once_with(
                            args=([recap_doc.pk],)
                        )
                    else:
                        mock_apply.assert_not_called()


@override_settings(DOCKET_NUMBER_CLEANING_ENABLED=True)
class TestHandleDocketNumberRawCleaning(TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.court_canb = CourtFactory(id="canb", jurisdiction="FB")
        cls.court_scotus = CourtFactory(id="scotus", jurisdiction="F")

    def setUp(self) -> None:
        self.r = get_redis_interface("CACHE")
        key_to_clean = "docket_number_cleaning:llm_batch"
        key = self.r.keys(key_to_clean)
        if key:
            self.r.delete(*key)

    def test_docket_number_cleaning_triggered_with_cleaning(self):
        docket = DocketFactory(
            court=self.court_scotus,
            docket_number_raw="12-1234-ag",
            source=Docket.DEFAULT,
        )
        self.assertEqual(
            docket.docket_number, "12-1234-AG", "Docket number doesn't match"
        )
        self.assertEqual(
            self.r.scard("docket_number_cleaning:llm_batch"),
            0,
            "Redis cache count doesn't match",
        )
        self.assertEqual(
            self.r.smembers("docket_number_cleaning:llm_batch"),
            set(),
            "Redis cache set doesn't match",
        )

        docket.docket_number_raw = "12--1234-ag"
        docket.save(update_fields=["docket_number_raw"])
        self.assertEqual(
            docket.docket_number, "12-1234-AG", "Docket number doesn't match"
        )
        self.assertEqual(
            self.r.scard("docket_number_cleaning:llm_batch"),
            0,
            "Redis cache count doesn't match",
        )
        self.assertEqual(
            self.r.smembers("docket_number_cleaning:llm_batch"),
            set(),
            "Redis cache set doesn't match",
        )

    def test_docket_number_cleaning_not_triggered_for_recap_source(self):
        docket = DocketFactory.create(
            court=self.court_scotus,
            docket_number_raw="Docket 12--1234-ag",
            docket_number="Docket 12--1234-ag",
            source=Docket.RECAP,
        )
        self.assertEqual(
            docket.docket_number,
            "Docket 12--1234-ag",
            "Docket number doesn't match",
        )
        self.assertEqual(
            self.r.scard("docket_number_cleaning:llm_batch"),
            0,
            "Redis cache count doesn't match",
        )
        self.assertEqual(
            self.r.smembers("docket_number_cleaning:llm_batch"),
            set(),
            "Redis cache set doesn't match",
        )

    def test_docket_number_cleaning_triggered_without_cleaning(self):
        docket = DocketFactory(
            court=self.court_canb,
            docket_number_raw="12-1234",
            source=Docket.DEFAULT,
        )
        self.assertEqual(
            docket.docket_number,
            "12-1234",
            "Docket number doesn't match",
        )
        self.assertEqual(
            self.r.scard("docket_number_cleaning:llm_batch"),
            0,
            "Redis cache count doesn't match",
        )
        self.assertEqual(
            self.r.smembers("docket_number_cleaning:llm_batch"),
            set(),
            "Redis cache set doesn't match",
        )

        docket.court = self.court_scotus
        docket.docket_number_raw = "Docket Nos. 12-1234-ag, 1235_"
        docket.save(update_fields=["court", "docket_number_raw"])
        self.assertEqual(
            docket.docket_number,
            "Docket Nos. 12-1234-ag, 1235_",
            "Docket number doesn't match",
        )
        self.assertEqual(
            self.r.scard("docket_number_cleaning:llm_batch"),
            1,
            "Redis cache count doesn't match",
        )
        self.assertEqual(
            self.r.smembers("docket_number_cleaning:llm_batch"),
            set([str(docket.id)]),
            "Redis cache set doesn't match",
        )

    def test_docket_number_cleaning_triggered_without_cleaning_multiples(self):
        docket_1 = DocketFactory(
            court=self.court_scotus,
            docket_number_raw="Docket Nos. 12-1234-ag, 1235",
            source=Docket.DEFAULT,
        )
        docket_2 = DocketFactory(
            court=self.court_scotus,
            docket_number_raw="Docket Nos. 12-1234-ag, 1235_",
            source=Docket.DEFAULT,
        )
        self.assertEqual(
            docket_1.docket_number,
            "Docket Nos. 12-1234-ag, 1235",
            "Docket number doesn't match",
        )
        self.assertEqual(
            docket_2.docket_number,
            "Docket Nos. 12-1234-ag, 1235_",
            "Docket number doesn't match",
        )
        self.assertEqual(
            self.r.scard("docket_number_cleaning:llm_batch"),
            2,
            "Redis cache count doesn't match",
        )
        self.assertEqual(
            self.r.smembers("docket_number_cleaning:llm_batch"),
            set([str(docket_1.id), str(docket_2.id)]),
            "Redis cache set doesn't match",
        )
