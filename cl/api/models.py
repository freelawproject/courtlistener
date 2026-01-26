import re
import uuid
from http import HTTPStatus

import pghistory
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models

from cl.lib.models import AbstractDateTimeModel

# Pattern: digits, slash, then valid time unit (s/m/h/d or full words)
RATE_PATTERN = re.compile(r"^\d+/(s|m|h|d|sec|min|second|minute|hour|day)$")


class ThrottleType(models.IntegerChoices):
    API = 1, "API"
    CITATION_LOOKUP = 2, "Citation Lookup"


@pghistory.track()
class APIThrottle(AbstractDateTimeModel):
    """Override rate limits or block specific users for API endpoints."""

    user: models.ForeignKey[User, User] = models.ForeignKey(
        User,
        help_text="The user whose throttle rate is being overridden.",
        related_name="api_throttles",
        on_delete=models.CASCADE,
    )
    throttle_type: models.SmallIntegerField = models.SmallIntegerField(
        help_text="The type of throttle being overridden.",
        choices=ThrottleType.choices,
    )
    blocked: models.BooleanField = models.BooleanField(
        help_text="If True, the user is blocked from making requests. "
        "Takes precedence over rate.",
        default=False,
    )
    rate: models.CharField = models.CharField(
        help_text="The rate limit (e.g., '100/hour', '1000/day'). "
        "Required if not blocked.",
        max_length=20,
        blank=True,
    )
    notes: models.TextField = models.TextField(
        help_text="Admin notes about why this override exists.",
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "throttle_type"],
                name="unique_user_throttle_type",
            ),
        ]

    def __str__(self) -> str:
        throttle_type = self.get_throttle_type_display()
        if self.blocked:
            return f"{self.user.username} blocked ({throttle_type})"
        return f"{self.user.username} at {self.rate} ({throttle_type})"

    def clean(self) -> None:
        super().clean()
        if not self.blocked and not self.rate:
            raise ValidationError(
                {"rate": "Rate is required when user is not blocked."}
            )
        if self.rate and not RATE_PATTERN.match(self.rate):
            raise ValidationError(
                {
                    "rate": f"Invalid rate format: {self.rate}. "
                    "Use format like '100/hour', '1000/day', '60/min'."
                }
            )


class WebhookEventType(models.IntegerChoices):
    DOCKET_ALERT = 1, "Docket Alert"
    SEARCH_ALERT = 2, "Search Alert"
    RECAP_FETCH = 3, "Recap Fetch"
    OLD_DOCKET_ALERTS_REPORT = 4, "Old Docket Alerts Report"
    PRAY_AND_PAY = 5, "Pray And Pay Alert"


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
        choices=WebhookEventType,
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
        choices=WebhookVersions,
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
