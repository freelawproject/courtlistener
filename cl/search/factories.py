import logging
import string

from django.db.utils import IntegrityError
from factory import (
    DictFactory,
    Faker,
    Iterator,
    LazyAttribute,
    LazyFunction,
    List,
    RelatedFactory,
    SelfAttribute,
    SubFactory,
    post_generation,
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
                logger.info("Unexpected exp=%s, type(exp)=%s", exp, type(exp))
                kwargs["position"] = Faker(
                    "pyfloat", positive=True, right_digits=4, left_digits=3
                ).evaluate(None, None, {"locale": None})
                count = count + 1
                if count > 3:
                    raise (exp)


class DocketFactory(DjangoModelFactory):
    class Meta:
        model = Docket
        skip_postgeneration_save = True

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
    date_argued = Faker("date_object")
    view_count = 0

    """
    This hook is necessary to make this factory compatible with the
    `make_dev_command` by delegating the file creation to the hook, we prevent
    the model from trying to use our storage settings when the field is not
    explicitly requested
    """

    @post_generation
    def filepath_local(self, create, extracted, **kwargs):
        """Attaches a stub file to an instance of this factory."""
        if extracted:
            self.filepath_local = extracted
        elif kwargs:
            # Factory Boy uses the `evaluate` method of each field to calculate
            # values for object creation. The FileField class only requires the
            # extra dictionary to create the stub django file.
            #
            # Learn more about FactoryBoy's `FileField` class:
            # https://github.com/FactoryBoy/factory_boy/blob/ac49fb40ec424276c3cd3ca0925ba99a626f05f7/factory/django.py#L249
            self.filepath_local = FileField().evaluate(None, None, kwargs)

        if create:
            # Use a Docket queryset to persist filepath_local instead of calling
            # save(), which can trigger duplicate post_save signals, potentially
            # causing issues in certain testing scenarios.
            Docket.objects.filter(pk=self.pk).update(
                filepath_local=self.filepath_local
            )


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


class OpinionClusterWithChildrenFactory(OpinionClusterFactory):
    sub_opinions = RelatedFactory(
        OpinionWithChildrenFactory,
        factory_related_name="cluster",
    )


class OpinionClusterWithParentsFactory(OpinionClusterFactory):
    """Make an OpinionCluster with Docket parents"""

    docket = SubFactory(
        DocketFactory,
        case_name=SelfAttribute("..case_name"),
        case_name_full=SelfAttribute("..case_name_full"),
        case_name_short=SelfAttribute("..case_name_short"),
    )


class OpinionClusterWithChildrenAndParentsFactory(
    OpinionClusterWithChildrenFactory, OpinionClusterWithParentsFactory
):
    precedential_status = PRECEDENTIAL_STATUS.PUBLISHED  # Always precedential


class OpinionClusterWithMultipleOpinionsFactory(
    OpinionClusterWithParentsFactory
):
    """Make an OpinionCluster with Docket parent and multiple opinions"""

    class Meta:
        skip_postgeneration_save = True

    sub_opinions = RelatedFactoryVariableList(
        factory=OpinionWithChildrenFactory,
        factory_related_name="cluster",
        size=3,  # by default create 3 opinions
    )
    precedential_status = PRECEDENTIAL_STATUS.PUBLISHED


class CitationWithParentsFactory(DjangoModelFactory):
    class Meta:
        model = Citation

    volume = Faker("random_int", min=1, max=100)
    reporter = "U.S."
    page = Faker("random_int", min=1, max=100)
    type = 1
    cluster = SubFactory(OpinionClusterWithChildrenAndParentsFactory)


class DocketEntryFactory(DjangoModelFactory):
    class Meta:
        model = DocketEntry

    description = Faker("text", max_nb_chars=750)
    docket = SubFactory(DocketFactory)


class RECAPDocumentFactory(DjangoModelFactory):
    class Meta:
        model = RECAPDocument

    description = Faker("text", max_nb_chars=750)
    docket_entry = SubFactory(DocketEntryFactory)
    document_type = RECAPDocument.PACER_DOCUMENT
    pacer_doc_id = Faker("pyint", min_value=100_000, max_value=400_000)


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


class DocketEntryReuseParentsFactory(DocketEntryFactory):
    """Make a DocketEntry using existing Dockets as parents"""

    docket = Iterator(Docket.objects.all())


class DocketWithChildrenFactory(DocketFactory):
    clusters = RelatedFactory(
        OpinionClusterWithChildrenFactory,
        factory_related_name="docket",
    )


class OpinionsCitedWithParentsFactory(DjangoModelFactory):
    """Make a OpinionCited with Opinion parents"""

    class Meta:
        model = OpinionsCited

    citing_opinion = SubFactory(OpinionFactory)
    cited_opinion = SubFactory(OpinionFactory)


class BankruptcyInformationFactory(DjangoModelFactory):
    class Meta:
        model = BankruptcyInformation

    chapter = Faker("random_id_string")
    trustee_str = Faker("name_female")


class OpinionsCitedByRECAPDocumentFactory(DjangoModelFactory):
    """Make a OpinionsCitedByRECAPDocument with parents"""

    class Meta:
        model = OpinionsCitedByRECAPDocument

    citing_document = SubFactory(RECAPDocumentFactory)
    cited_opinion = SubFactory(OpinionFactory)


class EmbeddingDataFactory(DictFactory):
    chunk_number = Faker("pyint", min_value=0, max_value=100)
    chunk = Faker("text", max_nb_chars=500)
    embedding = LazyFunction(
        lambda: [0.036101438105106354 for _ in range(768)]
    )


class EmbeddingsDataFactory(DictFactory):
    id = Faker("pyint", min_value=1, max_value=100)
    embeddings = List([SubFactory(EmbeddingDataFactory)])
