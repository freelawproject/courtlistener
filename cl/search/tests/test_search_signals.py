from unittest.mock import Mock

from django.db.models.signals import post_save

from cl.search.factories import (
    DocketEntryWithParentsFactory,
    RECAPDocumentFactory,
)
from cl.search.models import RECAPDocument
from cl.search.signals import handle_recap_doc_change
from cl.tests.cases import SimpleTestCase


# Test that event hits the receiver function
class RECAPDocumentSignalsTests(SimpleTestCase):
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
