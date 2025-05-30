import uuid
from http import HTTPStatus

import pghistory
from django.contrib.auth.models import User
from django.core.validators import URLValidator
from django.db import models

from cl.lib.models import AbstractDateTimeModel


class WebhookEventType(models.IntegerChoices):
    DOCKET_ALERT = 1, "Docket Alert"
    SEARCH_ALERT = 2, "Search Alert"
    RECAP_FETCH = 3, "Recap Fetch"
    OLD_DOCKET_ALERTS_REPORT = 4, "Old Docket Alerts Report"


class WebhookVersions(models.IntegerChoices):
    v1 = 1, "v1"
    v2 = 2, "v2"


HttpStatusCodes = models.IntegerChoices(  # type: ignore
    "HttpStatusCodes",
    [(s.name, s.value) for s in HTTPStatus],  # type: ignore[arg-type]
)


@pghistory.track(
    pghistory.UpdateEvent(
        condition=pghistory.AnyChange(exclude_auto=True), row=pghistory.Old
    ),
    pghistory.DeleteEvent(),
    model_name="WebhookHistoryEvent",
)
class Webhook(AbstractDateTimeModel):
    user = models.ForeignKey[User, User](
        User,
        help_text="The user that has provisioned the webhook.",
        related_name="webhooks",
        on_delete=models.CASCADE,
    )
    event_type: models.IntegerField = models.IntegerField(
        help_text="The event type that triggers the webhook.",
        choices=WebhookEventType.choices,
    )
    url: models.URLField = models.URLField(
        help_text="The URL that receives a POST request from the webhook.",
        max_length=2000,
        validators=[URLValidator(schemes=["https"])],
    )
    enabled: models.BooleanField = models.BooleanField(
        help_text="An on/off switch for the webhook.", default=False
    )
    version: models.IntegerField = models.IntegerField(
        help_text="The specific version of the webhook provisioned.",
        choices=WebhookVersions.choices,
        default=WebhookVersions.v1,
    )
    failure_count: models.IntegerField = models.IntegerField(
        help_text="The number of failures (400+ status) responses the webhook "
        "has received.",
        default=0,
    )

    def __str__(self) -> str:
        return f"<Webhook:{self.pk} V{self.version} for event type '{self.get_event_type_display()}'>"


class WEBHOOK_EVENT_STATUS:
    """WebhookEvent Status Types"""

    IN_PROGRESS = 0
    ENQUEUED_RETRY = 1
    SUCCESSFUL = 2
    FAILED = 3
    ENDPOINT_DISABLED = 4
    STATUS = (
        (IN_PROGRESS, "Delivery in progress"),
        (ENQUEUED_RETRY, "Enqueued for retry"),
        (SUCCESSFUL, "Delivered successfully"),
        (FAILED, "Failed"),
        (ENDPOINT_DISABLED, "Endpoint disabled"),
    )


class WebhookEvent(AbstractDateTimeModel):
    webhook = models.ForeignKey[Webhook, Webhook](
        Webhook,
        help_text="The Webhook this event is associated with.",
        related_name="webhook_events",
        on_delete=models.CASCADE,
    )
    event_id: models.UUIDField = models.UUIDField(
        help_text="Unique event identifier",
        default=uuid.uuid4,
        editable=False,
    )
    event_status: models.SmallIntegerField = models.SmallIntegerField(
        help_text="The webhook event status.",
        default=WEBHOOK_EVENT_STATUS.IN_PROGRESS,
        choices=WEBHOOK_EVENT_STATUS.STATUS,
    )
    content: models.JSONField = models.JSONField(
        help_text="The content of the outgoing body in the POST request.",
        blank=True,
        null=True,
    )
    next_retry_date: models.DateTimeField = models.DateTimeField(
        help_text="The scheduled datetime to retry the webhook event.",
        blank=True,
        null=True,
    )
    error_message: models.TextField = models.TextField(
        help_text="The error raised by a failed POST request.",
        blank=True,
    )
    response: models.TextField = models.TextField(
        help_text="The response received from the POST request.",
        blank=True,
    )
    retry_counter: models.SmallIntegerField = models.SmallIntegerField(
        help_text="The retry counter for the exponential backoff event.",
        default=0,
    )
    status_code: models.SmallIntegerField = models.SmallIntegerField(
        help_text="The HTTP status code received from the POST request.",
        choices=HttpStatusCodes.choices,  # type: ignore[attr-defined]
        blank=True,
        null=True,
    )
    debug: models.BooleanField = models.BooleanField(
        help_text="Enabled if this is a test event for debugging purposes.",
        default=False,
    )

    class Meta:
        indexes = [
            models.Index(fields=["next_retry_date", "event_status"]),
        ]

    def __str__(self) -> str:
        return f"Webhook Event: {self.event_id}"

    @property
    def event_type(self):
        return self.webhook.event_type
