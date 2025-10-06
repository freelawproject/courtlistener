from django.utils.timezone import now
from factory import Faker, SubFactory
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice

from cl.api.models import (
    WEBHOOK_EVENT_STATUS,
    Webhook,
    WebhookEvent,
    WebhookEventType,
)
from cl.users.factories import UserFactory


class WebhookFactory(DjangoModelFactory):
    class Meta:
        model = Webhook

    event_type = WebhookEventType.DOCKET_ALERT
    user = SubFactory(UserFactory)
    url = Faker("url")
    enabled = Faker("boolean")


class WebhookEventFactory(DjangoModelFactory):
    class Meta:
        model = WebhookEvent

    next_retry_date = now()
    event_status = FuzzyChoice(
        WEBHOOK_EVENT_STATUS.STATUS, getter=lambda c: c[0]
    )


class WebhookEventWithParentsFactory(WebhookEventFactory):
    """Make a WebhookEvent with a parent Webhook"""

    webhook = SubFactory(WebhookFactory)
