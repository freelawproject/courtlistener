from rest_framework.viewsets import ModelViewSet

from cl.api.utils import RECAPUploaders, LoggingMixin, RECAPUsersReadOnly, \
    BigPagination
from cl.recap.api_serializers import ProcessingQueueSerializer, \
    PacerDocIdLookUpSerializer, FjcIntegratedDatabaseSerializer
from cl.recap.filters import ProcessingQueueFilter, FjcIntegratedDatabaseFilter
from cl.recap.models import ProcessingQueue, FjcIntegratedDatabase
from cl.recap.tasks import process_recap_upload
from cl.search.filters import RECAPDocumentFilter
from cl.search.models import RECAPDocument


class PacerProcessingQueueViewSet(LoggingMixin, ModelViewSet):
    permission_classes = (RECAPUploaders,)
    queryset = ProcessingQueue.objects.all().order_by('-id')
    serializer_class = ProcessingQueueSerializer
    filter_class = ProcessingQueueFilter
    ordering_fields = (
        'date_created', 'date_modified',
    )

    def perform_create(self, serializer):
        pq = serializer.save(uploader=self.request.user)
        process_recap_upload(pq)


class PacerDocIdLookupViewSet(LoggingMixin, ModelViewSet):
    permission_classes = (RECAPUsersReadOnly,)
    queryset = RECAPDocument.objects.filter(
        is_available=True,
    ).only(
        'pk',
        'filepath_local',
        'pacer_doc_id',
        # Fields below needed for absolute_url, if we add that back.
        # 'document_number',
        # 'document_type',
        # 'docket_entry_id',
        # 'docket_entry__docket_id',
        # 'docket_entry__docket__slug',
    ).order_by('-id')
    serializer_class = PacerDocIdLookUpSerializer
    filter_class = RECAPDocumentFilter
    pagination_class = BigPagination

    def get_view_name(self):
        name = "RECAP lookup API"
        suffix = getattr(self, 'suffix', None)
        if suffix:
            name += ' ' + suffix
        return name


class FjcIntegratedDatabaseViewSet(LoggingMixin, ModelViewSet):
    queryset = FjcIntegratedDatabase.objects.all().order_by('-id')
    serializer_class = FjcIntegratedDatabaseSerializer
    filter_class = FjcIntegratedDatabaseFilter
    ordering_fields = (
        'date_created', 'date_modified', 'date_filed',

    )
