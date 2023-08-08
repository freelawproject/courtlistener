from django.utils.timezone import now
from factory import Faker, LazyFunction, RelatedFactory
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice
from localflavor.us.us_states import STATE_CHOICES

from cl.people_db.models import (
    FEMALE,
    SUFFIXES,
    ABARating,
    Education,
    Person,
    PoliticalAffiliation,
    Position,
    Race,
    School,
    Source,
)
from cl.tests.providers import LegalProvider

Faker.add_provider(LegalProvider)


class PersonFactory(DjangoModelFactory):
    class Meta:
        model = Person

    date_completed = LazyFunction(now)
    name_first = Faker("name_female")
    name_last = Faker("last_name")
    name_suffix = FuzzyChoice(SUFFIXES, getter=lambda c: c[0])
    dob_city = Faker("city")
    dob_state = FuzzyChoice(STATE_CHOICES, getter=lambda c: c[0])
    gender = FEMALE
    slug = Faker("slug")


class PositionFactory(DjangoModelFactory):
    class Meta:
        model = Position

    position_type = Position.JUDGE


class PersonWithChildrenFactory(PersonFactory):
    positions = RelatedFactory(
        PositionFactory,
        factory_related_name="person",
    )


class RaceFactory(DjangoModelFactory):
    class Meta:
        model = Race

    race = FuzzyChoice(Race.RACES, getter=lambda c: c[0])


class SchoolFactory(DjangoModelFactory):
    class Meta:
        model = School

    ein = Faker("random_int", min=10000, max=100000)


class EducationFactory(DjangoModelFactory):
    class Meta:
        model = Education

    degree_level = FuzzyChoice(Education.DEGREE_LEVELS, getter=lambda c: c[0])


class PoliticalAffiliationFactory(DjangoModelFactory):
    class Meta:
        model = PoliticalAffiliation

    political_party = FuzzyChoice(
        PoliticalAffiliation.POLITICAL_PARTIES, getter=lambda c: c[0]
    )
    source = FuzzyChoice(
        PoliticalAffiliation.POLITICAL_AFFILIATION_SOURCE,
        getter=lambda c: c[0],
    )


class ABARatingFactory(DjangoModelFactory):
    class Meta:
        model = ABARating

    rating = FuzzyChoice(ABARating.ABA_RATINGS, getter=lambda c: c[0])
