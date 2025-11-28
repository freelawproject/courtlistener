from django.contrib.auth.models import User
from rest_framework.viewsets import ModelViewSet

from cl.api.utils import EmailProcessingQueueAPIUsers, LoggingMixin
from cl.recap.api_serializers import ProcessingQueueSerializer
from cl.recap.filters import ProcessingQueueFilter
from cl.recap.models import EmailProcessingQueue
from cl.scrapers.tasks import process_scotus_email


class ScraperSCOTUSEmailEndpoint(LoggingMixin, ModelViewSet):
    permission_classes = (EmailProcessingQueueAPIUsers,)
    queryset = EmailProcessingQueue.objects.all().order_by("-id")
    serializer_class = ProcessingQueueSerializer
    filterset_class = ProcessingQueueFilter
    ordering_fields = ("id", "date_created", "date_modified")
    ordering = "-id"
    cursor_ordering_fields = ["id", "date_created", "date_modified"]

    def get_message_id_from_request_data(self):
        return self.request.data.get("mail", {}).get("message_id")

    def get_destination_emails_from_request_data(self):
        return self.request.data.get("receipt", {}).get("recipients")

    def perform_create(self, serializer):
        scotus_email_user = User.objects.get(username="scotus-email")
        epq = serializer.save(
            message_id=self.get_message_id_from_request_data(),
            destination_emails=self.get_destination_emails_from_request_data(),
            uploader=scotus_email_user,
        )
        process_scotus_email.delay(epq.id)
        return epq
