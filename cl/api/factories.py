from factory import SubFactory
from factory.django import DjangoModelFactory

from cl.api.models import Webhook
from cl.users.factories import UserFactory


class WebhookFactory(DjangoModelFactory):
    class Meta:
        model = Webhook

    user = SubFactory(UserFactory)
