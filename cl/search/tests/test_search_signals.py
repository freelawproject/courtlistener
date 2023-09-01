from dataclasses import dataclass
from typing import List
from unittest.mock import Mock, patch

from django.db.models.signals import post_save

from cl.search.factories import (
    DocketEntryWithParentsFactory,
    RECAPDocumentFactory,
)
from cl.search.models import RECAPDocument
from cl.search.signals import handle_recap_doc_change
from cl.tests.cases import SimpleTestCase


# Test that event hits the receiver function
class RECAPDocumentSignalTests(SimpleTestCase):
    def setUp(self):
        post_save.disconnect(handle_recap_doc_change, sender=RECAPDocument)
        self.mock_receiver = Mock()
        post_save.connect(self.mock_receiver, sender=RECAPDocument)

    def test_recapdoc_save_emit_signal(self):
        recap_doc = RECAPDocumentFactory.create(
            plain_text="In Fisher v. SD Protection Inc., 948 F.3d 593 (2d Cir. 2020), the Second Circuit held that in the context of settlement of FLSA and NYLL cases, which must be approved by the trial court in accordance with Cheeks v. Freeport Pancake House, Inc., 796 F.3d 199 (2d Cir. 2015), the district court abused its discretion in limiting the amount of recoverable fees to a percentage of the recovery by the successful plaintiffs. But also: sdjnfdsjnk. Fisher, 948 F.3d at 597.",
            ocr_status=RECAPDocument.OCR_UNNECESSARY,
            docket_entry=DocketEntryWithParentsFactory(),
        )

        recap_doc.save(update_fields=["ocr_status", "plain_text"])
        self.assertTrue(self.mock_receiver.called)


@dataclass
class ReceiverTestCase:
    update_fields: List[str]
    ocr_status: RECAPDocument.OCR_STATUSES
    expect_enqueue: bool


class RECAPDocumentReceiverTests(SimpleTestCase):
    def test_receiver_enqueues_task(self):
        test_cases: List[ReceiverTestCase] = [
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
                update_fields=["tags"],
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
                        docket_entry=DocketEntryWithParentsFactory(),
                    )

                    recap_doc.save(update_fields=test_case.update_fields)

                    if test_case.expect_enqueue:
                        mock_apply.assert_called_once_with(
                            args=([recap_doc.pk])
                        )
                    else:
                        mock_apply.assert_not_called()
