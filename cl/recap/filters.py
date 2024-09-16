from cl.api.utils import (
    BASIC_TEXT_LOOKUPS,
    DATE_LOOKUPS,
    DATETIME_LOOKUPS,
    NoEmptyFilterSet,
)
from cl.recap.models import (
    EmailProcessingQueue,
    FjcIntegratedDatabase,
    PacerFetchQueue,
    ProcessingQueue,
)


class ProcessingQueueFilter(NoEmptyFilterSet):
    class Meta:
        model = ProcessingQueue
        fields = {
            "court": ["exact"],
            "docket": ["exact"],
            "pacer_case_id": ["exact", "in"],
            "status": ["exact", "in"],
            "upload_type": ["exact", "in"],
            "date_created": DATETIME_LOOKUPS,
        }


class EmailProcessingQueueFilter(NoEmptyFilterSet):
    class Meta:
        model = EmailProcessingQueue
        fields = {
            "status": ["exact", "in"],
            "court": ["exact"],
            "recap_documents": ["exact", "in"],
            "date_created": DATETIME_LOOKUPS,
        }


class PacerFetchQueueFilter(NoEmptyFilterSet):
    class Meta:
        model = PacerFetchQueue
        fields = {
            "status": ["exact", "in"],
            "request_type": ["exact"],
            "court": ["exact"],
            "docket": ["exact"],
            "pacer_case_id": ["exact", "in"],
            "docket_number": ["exact"],
            "recap_document": ["exact", "in"],
        }


class FjcIntegratedDatabaseFilter(NoEmptyFilterSet):
    class Meta:
        model = FjcIntegratedDatabase
        fields = {
            "dataset_source": ["exact", "in"],
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "circuit": ["exact"],
            "district": ["exact"],
            "origin": ["exact", "in"],
            "date_filed": DATE_LOOKUPS,
            "jurisdiction": ["exact", "in"],
            "title": BASIC_TEXT_LOOKUPS,
            "section": BASIC_TEXT_LOOKUPS,
            "subsection": BASIC_TEXT_LOOKUPS,
            "arbitration_at_filing": ["exact", "in"],
            "arbitration_at_termination": ["exact", "in"],
            "class_action": ["exact", "in"],
            "plaintiff": BASIC_TEXT_LOOKUPS,
            "defendant": BASIC_TEXT_LOOKUPS,
            "termination_class_action_status": ["exact", "in"],
            "procedural_progress": ["exact", "in"],
            "disposition": ["exact", "in"],
            "judgment": ["exact", "in"],
            "pro_se": ["exact", "in"],
        }
