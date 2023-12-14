from factory import Faker, SubFactory
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice

from cl.donate.models import PROVIDERS, Donation, NeonWebhookEvents
from cl.users.factories import UserWithChildProfileFactory


class DonationFactory(DjangoModelFactory):
    class Meta:
        model = Donation

    donor = SubFactory(UserWithChildProfileFactory)
    amount = Faker(
        "pydecimal",
        positive=True,
        right_digits=2,
        min_value=5,
        max_value=100_000,
    )
    payment_id = Faker("uuid4")
    payment_provider = FuzzyChoice(PROVIDERS.NAMES, getter=lambda c: c[0])
    status = FuzzyChoice(Donation.PAYMENT_STATUSES, getter=lambda c: c[0])
    send_annual_reminder = Faker("bool")


class NeonWebhookEventFactory(DjangoModelFactory):
    class Meta:
        model = NeonWebhookEvents

    trigger = FuzzyChoice(NeonWebhookEvents.TYPES, getter=lambda c: c[0])
