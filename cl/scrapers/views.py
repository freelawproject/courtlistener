from django.contrib.auth.models import User
from rest_framework.viewsets import ModelViewSet

from cl.api.utils import EmailProcessingQueueAPIUsers, LoggingMixin
from cl.recap.api_serializers import EmailProcessingQueueSerializer
from cl.recap.filters import EmailProcessingQueueFilter
from cl.recap.models import EmailProcessingQueue


class TexasEmailEndpoint(LoggingMixin, ModelViewSet):
    permission_classes = (EmailProcessingQueueAPIUsers,)
    queryset = EmailProcessingQueue.objects.all().order_by("-id")
    serializer_class = EmailProcessingQueueSerializer
    filterset_class = EmailProcessingQueueFilter
    ordering_fields = ("id", "date_created", "date_modified")
    ordering = "-id"
    cursor_ordering_fields = ["id", "date_created", "date_modified"]

    def get_message_id_from_request_data(self):
        return self.request.data.get("mail", {}).get("message_id")

    def get_destination_emails_from_request_data(self):
        return self.request.data.get("receipt", {}).get("recipients")

    def perform_create(self, serializer):
        # TODO Update once parser is complete
        texas_email_user = User.objects.get(username="recap-email")
        epq = serializer.save(
            message_id=self.get_message_id_from_request_data(),
            destination_emails=self.get_destination_emails_from_request_data(),
            uploader=texas_email_user,
            # source=EmailSources.TEXAS
        )
        # process_texas_email.delay(epq.id)
        return epq
