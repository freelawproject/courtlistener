from factory import (
    Faker,
    Iterator,
    LazyAttribute,
    RelatedFactory,
    SelfAttribute,
    SubFactory,
)
from factory.django import DjangoModelFactory
from factory.fuzzy import FuzzyChoice
from juriscraper.lib.string_utils import CaseNameTweaker

from cl.people_db.factories import PersonFactory
from cl.recap.factories import FjcIntegratedDatabaseFactory
from cl.search.models import (
    DOCUMENT_STATUSES,
    SOURCES,
    Court,
    Docket,
    Opinion,
    OpinionCluster,
    Parenthetical,
)
from cl.tests.providers import LegalProvider

Faker.add_provider(LegalProvider)

cnt = CaseNameTweaker()


class CourtFactory(DjangoModelFactory):
    class Meta:
        model = Court

    id = Faker("random_id")
    position = Faker("pyfloat", positive=True, right_digits=2, left_digits=3)
    short_name = Faker("court_name")
    url = Faker("url")
    jurisdiction = FuzzyChoice(Court.JURISDICTIONS, getter=lambda c: c[0])
    in_use = True


class ParentheticalFactory(DjangoModelFactory):
    class Meta:
        model = Parenthetical

    describing_opinion = SelfAttribute("described_opinion")
    text = Faker("sentence")
    score = Faker("pyfloat", min_value=0, max_value=1, right_digits=4)


class ParentheticalFactoryWithParents(ParentheticalFactory):
    describing_opinion = SubFactory(
        "cl.search.factories.OpinionFactoryWithParents",
    )
    described_opinion = SelfAttribute("describing_opinion")


class OpinionFactory(DjangoModelFactory):
    class Meta:
        model = Opinion

    author = SubFactory(PersonFactory)
    author_str = LazyAttribute(lambda self: self.author.name_full)
    type = FuzzyChoice(Opinion.OPINION_TYPES, getter=lambda c: c[0])
    sha1 = Faker("sha1")
    plain_text = Faker("text", max_nb_chars=2000)


class OpinionFactoryWithChildren(OpinionFactory):

    parentheticals = RelatedFactory(
        ParentheticalFactory,
        factory_related_name="described_opinion",
    )


class OpinionFactoryWithParents(OpinionFactory):
    cluster = SubFactory(
        "cl.search.factories.OpinionClusterFactoryWithParents",
    )


class OpinionClusterFactory(DjangoModelFactory):
    class Meta:
        model = OpinionCluster

    case_name_short = LazyAttribute(
        lambda self: cnt.make_case_name_short(self.case_name)
    )
    case_name = Faker("case_name")
    case_name_full = Faker("case_name", full=True)
    date_filed = Faker("date")
    slug = Faker("slug")
    source = FuzzyChoice(SOURCES, getter=lambda c: c[0])
    precedential_status = FuzzyChoice(DOCUMENT_STATUSES, getter=lambda c: c[0])


class OpinionClusterFactoryWithChildren(OpinionClusterFactory):
    sub_opinions = RelatedFactory(
        OpinionFactoryWithChildren,
        factory_related_name="cluster",
    )


class OpinionClusterFactoryWithParents(OpinionClusterFactory):
    docket = SubFactory(
        "cl.search.factories.DocketFactory",
        # Set the case names on the docket to the ones on this object
        case_name=LazyAttribute(lambda self: self.factory_parent.case_name),
        case_name_short=LazyAttribute(
            lambda self: self.factory_parent.case_name_short
        ),
        case_name_full=LazyAttribute(
            lambda self: self.factory_parent.case_name_full
        ),
    )


class DocketFactory(DjangoModelFactory):
    class Meta:
        model = Docket

    idb_data = SubFactory(FjcIntegratedDatabaseFactory)
    source = FuzzyChoice(Docket.SOURCE_CHOICES, getter=lambda c: c[0])
    court = Iterator(Court.objects.all())
    appeal_from = Iterator(Court.objects.all())
    case_name_short = LazyAttribute(
        lambda self: cnt.make_case_name_short(self.case_name)
    )
    case_name = Faker("case_name")
    case_name_full = Faker("case_name", full=True)
    pacer_case_id = Faker("pyint", min_value=100_000, max_value=400_000)
    docket_number = Faker("federal_district_docket_number")
    slug = Faker("slug")


class DocketFactoryWithChildren(DocketFactory):
    clusters = RelatedFactory(
        OpinionClusterFactoryWithChildren,
        factory_related_name="docket",
    )
