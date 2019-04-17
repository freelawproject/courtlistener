from rest_framework_filters import FilterSet

from cl.api.utils import DATETIME_LOOKUPS, BASIC_TEXT_LOOKUPS
from cl.recap.models import ProcessingQueue, FjcIntegratedDatabase


class ProcessingQueueFilter(FilterSet):
    class Meta:
        model = ProcessingQueue
        fields = {
            'court': ['exact'],
            'pacer_case_id': ['exact', 'in'],
            'status': ['exact', 'in'],
            'upload_type': ['exact', 'in'],
        }


class FjcIntegratedDatabaseFilter(FilterSet):
    class Meta:
        model = FjcIntegratedDatabase
        fields = {
            'dataset_source': ['exact', 'in'],
            'date_created': DATETIME_LOOKUPS,
            'date_modified': DATETIME_LOOKUPS,
            'circuit': ['exact'],
            'district': ['exact'],
            'origin': ['exact', 'in'],
            'date_filed': DATETIME_LOOKUPS,
            'jurisdiction': ['exact', 'in'],
            'title': BASIC_TEXT_LOOKUPS,
            'section': BASIC_TEXT_LOOKUPS,
            'subsection': BASIC_TEXT_LOOKUPS,
            'arbitration_at_filing': ['exact', 'in'],
            'arbitration_at_termination': ['exact', 'in'],
            'class_action': ['exact', 'in'],
            'plaintiff': BASIC_TEXT_LOOKUPS,
            'defendant': BASIC_TEXT_LOOKUPS,
            'termination_class_action_status': ['exact', 'in'],
            'procedural_progress': ['exact', 'in'],
            'disposition': ['exact', 'in'],
            'judgment': ['exact', 'in'],
            'pro_se': ['exact', 'in'],
        }
