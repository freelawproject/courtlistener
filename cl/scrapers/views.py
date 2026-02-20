from attr import dataclass
from django.contrib.auth.models import User
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.relations import PrimaryKeyRelatedField
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer
from rest_framework.viewsets import ModelViewSet

from cl.api.utils import EmailProcessingQueueAPIUsers, LoggingMixin
from cl.celery_init import app
from cl.recap.filters import EmailProcessingQueueFilter
from cl.recap.models import EmailProcessingQueue
from cl.search.models import Court


@dataclass
class EmailProcessingTask:
    task: app.Task
    source: int


STATE_SITE_TASK_MAP: dict[str, dict[str, EmailProcessingTask]] = {
    "tx": {
        # TODO Update once parser is complete
        # "tames": EmailProcessingTask(task=process_texas_email, source=EmailSources.TEXAS)
    }
}


class StateEmailProcessingQueueSerializer(ModelSerializer):
    uploader = serializers.HiddenField(
        default=serializers.CurrentUserDefault(),
    )
    court: PrimaryKeyRelatedField[Court] = serializers.PrimaryKeyRelatedField(
        queryset=Court.state_courts.all(),
        html_cutoff=500,  # Show all values in HTML view.
        required=True,
    )
    mail = serializers.JSONField(write_only=True)
    receipt = serializers.JSONField(write_only=True)

    class Meta:
        model = EmailProcessingQueue
        fields = "__all__"
        read_only_fields = (
            "error_message",
            "status",
        )

    def validate(self, attrs):
        court_id = attrs["court"].pk
        mail = attrs["mail"]
        receipt = attrs["receipt"]

        all_court_ids = Court.state_courts.all()
        if not all_court_ids.filter(pk=court_id).exists():
            raise ValidationError(f"{court_id} is not a state court ID.")

        for attr_name in [
            "message_id",
            "timestamp",
            "source",
            "destination",
            "headers",
        ]:
            if (
                mail.get(attr_name) is None
                or mail.get(attr_name) == "undefined"
            ):
                raise ValidationError(
                    f"The JSON value at key 'mail' should include '{attr_name}'."
                )

        for attr_name in ["timestamp", "recipients"]:
            if (
                receipt.get(attr_name) is None
                or receipt.get(attr_name) == "undefined"
            ):
                raise ValidationError(
                    f"The JSON value at key 'receipt' should include '{attr_name}'."
                )

        return attrs

    def create(self, validated_data):
        validated_data.pop("mail", None)
        validated_data.pop("receipt", None)
        return super().create(validated_data)


class StateEmailEndpoint(LoggingMixin, ModelViewSet):
    permission_classes = (EmailProcessingQueueAPIUsers,)
    queryset = EmailProcessingQueue.objects.all().order_by("-id")
    serializer_class = StateEmailProcessingQueueSerializer
    filterset_class = EmailProcessingQueueFilter
    ordering_fields = ("id", "date_created", "date_modified")
    ordering = "-id"
    cursor_ordering_fields = ["id", "date_created", "date_modified"]

    def get_message_id_from_request_data(self):
        return self.request.data.get("mail", {}).get("message_id")

    def get_destination_emails_from_request_data(self):
        return self.request.data.get("receipt", {}).get("recipients")

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def create(self, request, *args, **kwargs):
        state = kwargs["state"]
        site = kwargs["site"]
        if (
            not state
            or not site
            or state not in STATE_SITE_TASK_MAP
            or site not in STATE_SITE_TASK_MAP[state]
        ):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer, state=state, site=site)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def perform_create(self, serializer, **kwargs):
        state = kwargs["state"]
        site = kwargs["site"]
        texas_email_user = User.objects.get(username="recap-email")
        epq = serializer.save(
            message_id=self.get_message_id_from_request_data(),
            destination_emails=self.get_destination_emails_from_request_data(),
            uploader=texas_email_user,
            source=STATE_SITE_TASK_MAP[state][site].source,
        )
        STATE_SITE_TASK_MAP[state][site].task.delay(epq.id)
        return epq
