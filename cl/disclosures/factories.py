from factory import Faker
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyInteger

from cl.disclosures.models import (
    Debt,
    FinancialDisclosure,
    Gift,
    Investment,
    NonInvestmentIncome,
    Position,
    Reimbursement,
    SpouseIncome,
)


class InvestmentFactory(DjangoModelFactory):
    class Meta:
        model = Investment

    page_number = FuzzyInteger(50)
    description = Faker("sentence")


class GiftFactory(DjangoModelFactory):
    class Meta:
        model = Gift

    description = Faker("sentence")
    source = Faker("sentence")


class ReimbursementFactory(DjangoModelFactory):
    class Meta:
        model = Reimbursement

    location = Faker("city")
    purpose = Faker("sentence")


class DebtFactory(DjangoModelFactory):
    class Meta:
        model = Debt


class NonInvestmentIncomeFactory(DjangoModelFactory):
    class Meta:
        model = NonInvestmentIncome


class SpousalIncomeFactory(DjangoModelFactory):
    class Meta:
        model = SpouseIncome


class FinancialDisclosurePositionFactory(DjangoModelFactory):
    class Meta:
        model = Position


class FinancialDisclosureFactory(DjangoModelFactory):
    class Meta:
        model = FinancialDisclosure

    year = Faker("year")
    page_count = FuzzyInteger(50)
    sha1 = Faker("sha1")
