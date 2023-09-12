from django.utils.timezone import now
from factory import (
    Faker,
    LazyFunction,
    RelatedFactory,
    SubFactory,
    post_generation,
)
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice
from localflavor.us.us_states import STATE_CHOICES

from cl.people_db.models import (
    FEMALE,
    SUFFIXES,
    ABARating,
    Attorney,
    AttorneyOrganization,
    AttorneyOrganizationAssociation,
    Education,
    Party,
    PartyType,
    Person,
    PoliticalAffiliation,
    Position,
    Race,
    Role,
    School,
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


class AttorneyOrganizationFactory(DjangoModelFactory):
    class Meta:
        model = AttorneyOrganization

    name = Faker("company")
    address1 = Faker("address")
    city = Faker("city")
    state = FuzzyChoice(STATE_CHOICES, getter=lambda c: c[0])


class AttorneyOrganizationAssociationFactory(DjangoModelFactory):
    class Meta:
        model = AttorneyOrganizationAssociation


class AttorneyFactory(DjangoModelFactory):
    class Meta:
        model = Attorney

    name = Faker("name")
    docket = None

    @post_generation
    def docket(self, create, extracted, **kwargs):
        if not create:
            return
        self.docket = extracted

    @post_generation
    def organizations(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for organization in extracted:
                # Use the passed-in organizations
                AttorneyOrganizationAssociationFactory(
                    attorney=self,
                    attorney_organization=organization,
                    docket=self.docket,
                )
        else:
            # Create only one default organization
            AttorneyOrganizationAssociationFactory(
                attorney=self,
                attorney_organization=AttorneyOrganizationFactory(),
                docket=self.docket,
            )


class RoleFactory(DjangoModelFactory):
    class Meta:
        model = Role


class PartyFactory(DjangoModelFactory):
    class Meta:
        model = Party

    name = Faker("name")
    docket = None

    @post_generation
    def docket(self, create, extracted, **kwargs):
        """Override default docket"""
        if not create:
            return
        self.docket = extracted

    @post_generation
    def attorneys(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            # Use the passed-in attorneys
            for attorney in extracted:
                RoleFactory(party=self, attorney=attorney, docket=self.docket)
        else:
            # Create 1 default attorney
            RoleFactory(
                party=self,
                attorney=AttorneyFactory(docket=self.docket),
                docket=self.docket,
            )


class PartyTypeFactory(DjangoModelFactory):
    class Meta:
        model = PartyType

    name = Faker("name")
    party = SubFactory(PartyFactory)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override default docket"""

        docket = kwargs.pop("docket", None)
        if not docket:
            return None
        kwargs["docket"] = docket
        manager = cls._get_manager(model_class)
        return manager.create(*args, **kwargs)
