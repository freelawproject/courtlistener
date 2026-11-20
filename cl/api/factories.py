"""Factories for API throttles, webhooks, and webhook events."""

from django.utils.timezone import now
from factory import Faker, SubFactory
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice

from cl.api.models import (
    WEBHOOK_EVENT_STATUS,
    APIThrottle,
    ThrottleType,
    Webhook,
    WebhookEvent,
    WebhookEventType,
)
from cl.users.factories import UserFactory


class APIThrottleFactory(DjangoModelFactory):
    """Make a manual, unblocked API throttle for a new user."""

    class Meta:
        model = APIThrottle

    user = SubFactory(UserFactory)
    throttle_type = ThrottleType.API
    blocked = False
    rate = "100/hour"
    source = APIThrottle.Source.MANUAL
    notes = Faker("sentence")


class WebhookFactory(DjangoModelFactory):
    """Make a docket alert webhook for a new user."""

    class Meta:
        model = Webhook

    event_type = WebhookEventType.DOCKET_ALERT
    user = SubFactory(UserFactory)
    url = Faker("url")
    enabled = Faker("boolean")


class WebhookEventFactory(DjangoModelFactory):
    """Make a webhook event with a random status, without a webhook."""

    class Meta:
        model = WebhookEvent

    next_retry_date = now()
    event_status = FuzzyChoice(
        WEBHOOK_EVENT_STATUS.STATUS, getter=lambda c: c[0]
    )


class WebhookEventWithParentsFactory(WebhookEventFactory):
    """Make a WebhookEvent with a parent Webhook."""

    webhook = SubFactory(WebhookFactory)
