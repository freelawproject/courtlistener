from factory import Faker, SubFactory
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice

from cl.alerts.models import Alert, DocketAlert
from cl.search.factories import DocketParentMixin
from cl.users.factories import UserFactory


class DocketAlertFactory(DjangoModelFactory):
    class Meta:
        model = DocketAlert

    user = SubFactory(UserFactory)
    secret_key = Faker(
        "password",
        length=40,
        special_chars=False,
        upper_case=False,
    )


class DocketAlertWithParentsFactory(DocketAlertFactory, DocketParentMixin):
    """Make an alert on a particular docket"""

    pass


class AlertFactory(DjangoModelFactory):
    class Meta:
        model = Alert

    name = Faker("text", max_nb_chars=75)
    user = SubFactory(UserFactory)
    secret_key = Faker(
        "password",
        length=40,
        special_chars=False,
        upper_case=False,
    )
    rate = FuzzyChoice(Alert.FREQUENCY, getter=lambda c: c[0])
