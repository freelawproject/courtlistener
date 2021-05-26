from http import HTTPStatus

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework.authtoken.models import Token

from cl.lib.models import AbstractDateTimeModel


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)


class WebhookEventType(models.IntegerChoices):
    RECAP_EMAIL = 1, "RECAP email received"
    ALERT = 2, "Alert triggered"


HttpStatusCodes = models.IntegerChoices(
    "HttpStatusCodes", [(s.name, s.value) for s in HTTPStatus]
)


class Webhook(AbstractDateTimeModel):
    user = models.ForeignKey(
        User,
        help_text="The user that has provisioned the webhook.",
        related_name="webhooks",
        on_delete=models.CASCADE,
    )
    event_type = models.IntegerField(
        help_text="The event type that triggers the webhook.",
        choices=WebhookEventType.choices,
    )
    url = models.URLField(
        help_text="The URL that receives a POST request from the webhook.",
        max_length=2000,
    )
    enabled = models.BooleanField(
        help_text="An on/off switch for the webhook.", default=False
    )
    version = models.IntegerField(
        help_text="The specific version of the webhook provisioned.", default=1
    )
    failure_count = models.IntegerField(
        help_text="The number of failures (400+ status) responses the webhook "
        "has received.",
        default=0,
    )

    def __str__(self) -> str:
        return f"<Webhook: {self.pk} for event type '{self.get_event_type_display()}'>"


class WebhookEvent(AbstractDateTimeModel):
    webhook = models.ForeignKey(
        Webhook,
        help_text="The Webhook this event is associated with.",
        related_name="webhook_events",
        on_delete=models.CASCADE,
    )
    status_code = models.IntegerField(
        help_text="The HTTP status code received when the webhook event was "
        "created.",
        choices=HttpStatusCodes.choices,
    )
    content = models.JSONField(
        help_text="The content of the outgoing body in the POST request."
    )
    response = models.TextField(
        help_text="The response received from the POST request."
    )

    @property
    def event_type(self):
        return self.webhook.event_type
