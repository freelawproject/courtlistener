import json
from io import StringIO

from django.contrib.auth.models import User
from django.core.files import File
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.viewsets import ModelViewSet

from cl.api.utils import (
    BigPagination,
    EmailProcessingQueueAPIUsers,
    LoggingMixin,
    RECAPUploaders,
    RECAPUsersReadOnly,
)
from cl.recap.api_serializers import (
    EmailProcessingQueueSerializer,
    FjcIntegratedDatabaseSerializer,
    PacerDocIdLookUpSerializer,
    PacerFetchQueueSerializer,
    ProcessingQueueSerializer,
)
from cl.recap.filters import (
    FjcIntegratedDatabaseFilter,
    PacerFetchQueueFilter,
    ProcessingQueueFilter,
)
from cl.recap.models import (
    EmailProcessingQueue,
    FjcIntegratedDatabase,
    PacerFetchQueue,
    ProcessingQueue,
)
from cl.recap.tasks import do_pacer_fetch, process_recap_upload
from cl.search.filters import RECAPDocumentFilter
from cl.search.models import RECAPDocument


class PacerProcessingQueueViewSet(LoggingMixin, ModelViewSet):
    permission_classes = (RECAPUploaders,)
    queryset = ProcessingQueue.objects.all().order_by("-id")
    serializer_class = ProcessingQueueSerializer
    filterset_class = ProcessingQueueFilter
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
    )

    def perform_create(self, serializer):
        pq = serializer.save(uploader=self.request.user)
        process_recap_upload(pq)


class EmailProcessingQueueViewSet(LoggingMixin, ModelViewSet):
    permission_classes = (EmailProcessingQueueAPIUsers,)
    queryset = EmailProcessingQueue.objects.all().order_by("-id")
    serializer_class = EmailProcessingQueueSerializer

    def get_stream_for_mail_and_receipt(self, mail, receipt) -> StringIO:
        payload = {"mail": mail, "receipt": receipt}
        stream: StringIO = StringIO()
        stream.write(json.dumps(payload))
        return stream

    def perform_create(self, serializer):
        filepath_stream = self.get_stream_for_mail_and_receipt(
            self.request.data["mail"], self.request.data["receipt"]
        )
        recap_email_user = User.objects.get(username="recap-email")
        epq = serializer.save(
            filepath=File(filepath_stream), uploader=recap_email_user
        )
        return epq


class PacerFetchRequestViewSet(LoggingMixin, ModelViewSet):
    queryset = PacerFetchQueue.objects.all().order_by("-id")
    serializer_class = PacerFetchQueueSerializer
    filterset_class = PacerFetchQueueFilter
    permission_classes = (IsAuthenticatedOrReadOnly,)
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
        "date_completed",
    )

    def perform_create(self, serializer):
        fq = serializer.save(user=self.request.user)
        do_pacer_fetch(fq)


class PacerDocIdLookupViewSet(LoggingMixin, ModelViewSet):
    permission_classes = (RECAPUsersReadOnly,)
    queryset = (
        RECAPDocument.objects.filter(is_available=True)
        .only(
            "pk",
            "filepath_local",
            "pacer_doc_id",
            # Fields below needed for absolute_url, if we add that back.
            # 'document_number',
            # 'document_type',
            # 'docket_entry_id',
            # 'docket_entry__docket_id',
            # 'docket_entry__docket__slug',
        )
        .order_by("-id")
    )
    serializer_class = PacerDocIdLookUpSerializer
    filterset_class = RECAPDocumentFilter
    pagination_class = BigPagination

    def get_view_name(self):
        name = "RECAP lookup API"
        suffix = getattr(self, "suffix", None)
        if suffix:
            name += " " + suffix
        return name

    def list(self, request, *args, **kwargs):
        if not [p.startswith("pacer_doc_id") for p in request.GET.keys()]:
            # Not having this parameter causes bad performance. Abort.
            raise ValidationError("pacer_doc_id is a required filter.")
        return super(PacerDocIdLookupViewSet, self).list(
            request, *args, **kwargs
        )


class FjcIntegratedDatabaseViewSet(LoggingMixin, ModelViewSet):
    queryset = FjcIntegratedDatabase.objects.all().order_by("-id")
    serializer_class = FjcIntegratedDatabaseSerializer
    filterset_class = FjcIntegratedDatabaseFilter
    ordering_fields = (
        "id",
        "date_created",
        "date_modified",
        "date_filed",
    )
