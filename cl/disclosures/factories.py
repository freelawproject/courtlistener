from factory import Faker
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyInteger

from cl.disclosures.models import FinancialDisclosure, Investment, Position


class InvestmentFactory(DjangoModelFactory):
    class Meta:
        model = Investment

    page_number = FuzzyInteger(50)
    description = Faker("sentence")


class FinancialDisclosurePositionFactory(DjangoModelFactory):
    class Meta:
        model = Position


class FinancialDisclosureFactory(DjangoModelFactory):
    class Meta:
        model = FinancialDisclosure

    year = Faker("year")
    page_count = FuzzyInteger(50)
    sha1 = Faker("sha1")
