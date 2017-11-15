from rest_framework_filters import FilterSet

from cl.recap.models import ProcessingQueue


class ProcessingQueueFilter(FilterSet):
    class Meta:
        model = ProcessingQueue
        fields = {
            'status': ['exact', 'in'],
            'upload_type': ['exact', 'in'],
        }
