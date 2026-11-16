"""Factories for judges, parties, and attorneys."""

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
    """Make a female person with a random name, suffix, and birthplace."""

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
    """Make a judge position."""

    class Meta:
        model = Position

    position_type = Position.JUDGE


class PersonWithChildrenFactory(PersonFactory):
    """Make a person with a judge position."""

    positions = RelatedFactory(
        PositionFactory,
        factory_related_name="person",
    )


class RaceFactory(DjangoModelFactory):
    """Make a race with a random value."""

    class Meta:
        model = Race

    race = FuzzyChoice(Race.RACES, getter=lambda c: c[0])


class SchoolFactory(DjangoModelFactory):
    """Make a school with a random EIN."""

    class Meta:
        model = School

    ein = Faker("random_int", min=10000, max=100000)


class EducationFactory(DjangoModelFactory):
    """Make an education record with a random degree level."""

    class Meta:
        model = Education

    degree_level = FuzzyChoice(Education.DEGREE_LEVELS, getter=lambda c: c[0])


class PoliticalAffiliationFactory(DjangoModelFactory):
    """Make a political affiliation with a random party and source."""

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
    """Make an ABA rating with a random rating."""

    class Meta:
        model = ABARating

    rating = FuzzyChoice(ABARating.ABA_RATINGS, getter=lambda c: c[0])


class AttorneyOrganizationFactory(DjangoModelFactory):
    """Make an attorney organization with a random name and address."""

    class Meta:
        model = AttorneyOrganization

    name = Faker("company")
    address1 = Faker("address")
    city = Faker("city")
    state = FuzzyChoice(STATE_CHOICES, getter=lambda c: c[0])


class AttorneyOrganizationAssociationFactory(DjangoModelFactory):
    """Make an association between an attorney and an organization."""

    class Meta:
        model = AttorneyOrganizationAssociation


class AttorneyFactory(DjangoModelFactory):
    """Make an attorney with a random name, associated with organizations on a docket."""

    class Meta:
        model = Attorney

    name = Faker("name")

    @post_generation
    def docket(self, create, extracted, **kwargs):
        """Set the docket used for the attorney's organization associations."""
        if not create:
            return
        self.docket = extracted

    @post_generation
    def organizations(self, create, extracted, **kwargs):
        """Associate the attorney with the given organizations, or with one new organization.

        The associations are made on the attorney's docket. Nothing is made
        unless the attorney is being created.
        """
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
    """Make an attorney's role."""

    class Meta:
        model = Role


class PartyFactory(DjangoModelFactory):
    """Make a party with a random name, with attorneys on a docket."""

    class Meta:
        model = Party

    name = Faker("name")

    @post_generation
    def docket(self, create, extracted, **kwargs):
        """Override default docket."""
        if not create:
            return
        self.docket = extracted

    @post_generation
    def attorneys(self, create, extracted, **kwargs):
        """Give the party roles for the given attorneys, or for one new attorney.

        The roles are made on the party's docket. Nothing is made unless the
        party is being created.
        """
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
    """Make a party type with a new party.

    The party type itself is only created when a docket is given.
    """

    class Meta:
        model = PartyType

    name = Faker("name")
    party = SubFactory(PartyFactory)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override default docket."""
        docket = kwargs.pop("docket", None)
        if not docket:
            return None
        kwargs["docket"] = docket
        manager = cls._get_manager(model_class)
        return manager.create(*args, **kwargs)
