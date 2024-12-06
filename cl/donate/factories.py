import factory
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice

from cl.donate.models import NeonWebhookEvent


class NeonWebhookEventFactory(DjangoModelFactory):
    class Meta:
        model = NeonWebhookEvent

    trigger = FuzzyChoice(NeonWebhookEvent.TYPES, getter=lambda c: c[0])
    content = factory.Dict(
        {
            "eventTrigger": FuzzyChoice(
                NeonWebhookEvent.TYPES, getter=lambda c: c[0]
            ),
        }
    )
