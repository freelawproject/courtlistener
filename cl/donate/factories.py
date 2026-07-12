import factory
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice

from cl.donate.models import (
    MembershipPaymentStatus,
    NeonMembership,
    NeonMembershipLevel,
    NeonWebhookEvent,
)
from cl.users.factories import UserFactory


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


class NeonMembershipFactory(DjangoModelFactory):
    class Meta:
        model = NeonMembership

    user = factory.SubFactory(UserFactory)
    level = NeonMembershipLevel.TIER_1
    payment_status = MembershipPaymentStatus.SUCCEEDED
