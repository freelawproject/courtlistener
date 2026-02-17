from factory import Faker, RelatedFactory, SubFactory, post_generation
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
from cl.people_db.factories import PersonFactory, PositionFactory
from cl.search.factories import CourtFactory


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


class PersonWithDisclosuresFactory(PersonFactory):
    """Creates a person (judge) with financial disclosures and investments."""

    positions = RelatedFactory(
        PositionFactory,
        factory_related_name="person",
        court=SubFactory(CourtFactory),
    )

    @post_generation
    def disclosures(self, create, extracted, **kwargs):
        if not create:
            return
        # Create two years of disclosures with investments
        for year in [2023, 2022]:
            disclosure = FinancialDisclosureFactory(
                person=self,
                year=year,
                has_been_extracted=True,
            )
            # Add some investments to each disclosure
            InvestmentFactory.create_batch(3, financial_disclosure=disclosure)
