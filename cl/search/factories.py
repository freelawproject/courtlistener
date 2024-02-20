import logging
import string

from django.db.utils import IntegrityError
from factory import (
    Faker,
    Iterator,
    LazyAttribute,
    RelatedFactory,
    SelfAttribute,
    SubFactory,
)
from factory.django import DjangoModelFactory, FileField
from factory.fuzzy import FuzzyChoice, FuzzyText
from juriscraper.lib.string_utils import CaseNameTweaker

from cl.lib.factories import RelatedFactoryVariableList
from cl.people_db.factories import PersonFactory
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    SOURCES,
    BankruptcyInformation,
    Citation,
    Court,
    Docket,
    DocketEntry,
    Opinion,
    OpinionCluster,
    OpinionsCited,
    OpinionsCitedByRECAPDocument,
    Parenthetical,
    ParentheticalGroup,
    RECAPDocument,
)
from cl.tests.providers import LegalProvider

logger = logging.getLogger(__name__)

Faker.add_provider(LegalProvider)

cnt = CaseNameTweaker()


class CourtFactory(DjangoModelFactory):
    class Meta:
        model = Court
        django_get_or_create = ("id",)

    id = FuzzyText(length=4, chars=string.ascii_lowercase, suffix="d")
    position = Faker("pyfloat", positive=True, right_digits=4, left_digits=3)
    short_name = Faker("court_name")
    full_name = Faker("court_name")
    url = Faker("url")
    jurisdiction = FuzzyChoice(Court.JURISDICTIONS, getter=lambda c: c[0])
    in_use = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        count = 1
        while True:
            try:
                obj = model_class(*args, **kwargs)
                obj.save()
                return obj
            except IntegrityError as exp:
                logger.info(f"Unexpected {exp=}, {type(exp)=}")
                kwargs["position"] = Faker(
                    "pyfloat", positive=True, right_digits=4, left_digits=3
                ).evaluate(None, None, {"locale": None})
                count = count + 1
                if count > 3:
                    raise (exp)


class ParentheticalFactory(DjangoModelFactory):
    class Meta:
        model = Parenthetical

    describing_opinion = SelfAttribute("described_opinion")
    text = Faker("sentence")
    score = Faker("pyfloat", min_value=0, max_value=1, right_digits=4)


class ParentheticalGroupFactory(DjangoModelFactory):
    class Meta:
        model = ParentheticalGroup

    score = Faker("pyfloat", min_value=0, max_value=1, right_digits=4)
    size = Faker("random_int", min=1, max=100)


class ParentheticalWithParentsFactory(ParentheticalFactory):
    describing_opinion = SubFactory(
        "cl.search.factories.OpinionWithParentsFactory",
    )
    described_opinion = SelfAttribute("describing_opinion")


class OpinionFactory(DjangoModelFactory):
    class Meta:
        model = Opinion

    author = SubFactory(PersonFactory)
    author_str = LazyAttribute(
        lambda self: self.author.name_full if self.author else ""
    )
    type = FuzzyChoice(Opinion.OPINION_TYPES, getter=lambda c: c[0])
    sha1 = Faker("sha1")
    plain_text = Faker("text", max_nb_chars=2000)


class OpinionWithChildrenFactory(OpinionFactory):
    parentheticals = RelatedFactory(
        ParentheticalFactory,
        factory_related_name="described_opinion",
    )


class CitationWithParentsFactory(DjangoModelFactory):
    class Meta:
        model = Citation

    volume = Faker("random_int", min=1, max=100)
    reporter = "U.S."
    page = Faker("random_int", min=1, max=100)
    type = 1
    cluster = SubFactory(
        "cl.search.factories.OpinionClusterFactoryWithChildrenAndParents",
    )


class OpinionWithParentsFactory(OpinionFactory):
    cluster = SubFactory(
        "cl.search.factories.OpinionClusterWithParentsFactory",
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
    source = FuzzyChoice(SOURCES.NAMES, getter=lambda c: c[0])
    precedential_status = FuzzyChoice(
        PRECEDENTIAL_STATUS.NAMES, getter=lambda c: c[0]
    )


class OpinionClusterFactoryWithChildren(OpinionClusterFactory):
    sub_opinions = RelatedFactory(
        OpinionWithChildrenFactory,
        factory_related_name="cluster",
    )


class DocketParentMixin(DjangoModelFactory):
    docket = SubFactory(
        "cl.search.factories.DocketFactory",
        # Set the case names on the docket to the ones on this object
        # if it has them. Else generate the case name values.
        case_name=LazyAttribute(
            lambda self: getattr(
                self.factory_parent,
                "case_name",
                Faker("case_name").evaluate(None, None, {"locale": None}),
            )
        ),
        case_name_short=LazyAttribute(
            lambda self: getattr(
                self.factory_parent,
                "case_name_short",
                cnt.make_case_name_short(self.case_name),
            )
        ),
        case_name_full=LazyAttribute(
            lambda self: getattr(
                self.factory_parent,
                "case_name_full",
                Faker("case_name", full=True).evaluate(
                    None, None, {"locale": None}
                ),
            )
        ),
    )


class OpinionClusterFactoryWithChildrenAndParents(
    OpinionClusterFactory, DocketParentMixin
):
    sub_opinions = RelatedFactory(
        OpinionWithChildrenFactory,
        factory_related_name="cluster",
    )
    precedential_status = PRECEDENTIAL_STATUS.PUBLISHED  # Always precedential


class OpinionClusterWithParentsFactory(
    OpinionClusterFactory,
    DocketParentMixin,
):
    """Make an OpinionCluster with Docket parents"""

    pass


class RECAPDocumentFactory(DjangoModelFactory):
    class Meta:
        model = RECAPDocument

    description = Faker("text", max_nb_chars=750)
    document_type = RECAPDocument.PACER_DOCUMENT
    pacer_doc_id = Faker("pyint", min_value=100_000, max_value=400_000)


class DocketEntryFactory(DjangoModelFactory):
    class Meta:
        model = DocketEntry

    description = Faker("text", max_nb_chars=750)


class DocketReuseParentMixin(DjangoModelFactory):
    docket = Iterator(Docket.objects.all())


class DocketEntryForDocketFactory(DjangoModelFactory):
    class Meta:
        model = DocketEntry

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override default docket"""
        docket_id = kwargs.pop("parent_id", None)
        if not docket_id:
            return None
        kwargs["docket_id"] = docket_id
        manager = cls._get_manager(model_class)
        return manager.create(*args, **kwargs)

    description = Faker("text", max_nb_chars=750)


class DocketEntryWithParentsFactory(
    DocketEntryFactory,
    DocketParentMixin,
):
    """Make a DocketEntry with Docket parents"""

    pass


class DocketEntryReuseParentsFactory(
    DocketEntryFactory,
    DocketReuseParentMixin,
):
    """Make a DocketEntry using existing Dockets as parents"""

    pass


class DocketFactory(DjangoModelFactory):
    class Meta:
        model = Docket

    source = FuzzyChoice(Docket.SOURCE_CHOICES, getter=lambda c: c[0])
    court = SubFactory(CourtFactory)
    appeal_from = SubFactory(CourtFactory)
    case_name_short = LazyAttribute(
        lambda self: cnt.make_case_name_short(self.case_name)
    )
    case_name = Faker("case_name")
    case_name_full = Faker("case_name", full=True)
    pacer_case_id = Faker("pyint", min_value=100_000, max_value=400_000)
    docket_number = Faker("federal_district_docket_number")
    slug = Faker("slug")
    filepath_local = FileField(filename=None)
    date_argued = Faker("date_object")


class DocketWithChildrenFactory(DocketFactory):
    clusters = RelatedFactory(
        OpinionClusterFactoryWithChildren,
        factory_related_name="docket",
    )


class OpinionClusterFactoryMultipleOpinions(
    OpinionClusterFactory, DocketParentMixin
):
    """Make an OpinionCluster with Docket parent and multiple opinions"""

    sub_opinions = RelatedFactoryVariableList(
        factory=OpinionWithChildrenFactory,
        factory_related_name="cluster",
        size=3,  # by default create 3 opinions
    )
    precedential_status = ("Published", "Precedential")


class OpinionsCitedWithParentsFactory(DjangoModelFactory):
    """Make a OpinionCited with Opinion parents"""

    class Meta:
        model = OpinionsCited

    citing_opinion = SubFactory(
        "cl.search.factories.OpinionFactory",
    )
    cited_opinion = SubFactory(
        "cl.search.factories.OpinionFactory",
    )


class BankruptcyInformationFactory(DjangoModelFactory):
    class Meta:
        model = BankruptcyInformation

    chapter = Faker("random_id_string")
    trustee_str = Faker("name_female")


class OpinionsCitedByRECAPDocumentFactory(DjangoModelFactory):
    """Make a OpinionsCitedByRECAPDocument with parents"""

    class Meta:
        model = OpinionsCitedByRECAPDocument

    citing_document = SubFactory(
        "cl.search.factories.RECAPDocumentFactory",
    )
    cited_opinion = SubFactory(
        "cl.search.factories.OpinionFactory",
    )
