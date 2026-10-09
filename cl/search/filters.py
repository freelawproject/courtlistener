import rest_framework_filters as filters
from django.db.models import QuerySet

from cl.api.utils import (
    BASIC_TEXT_LOOKUPS,
    DATE_LOOKUPS,
    DATETIME_LOOKUPS,
    INTEGER_LOOKUPS,
    NoEmptyFilterSet,
)
from cl.audio.models import Audio
from cl.people_db.models import Party, Person
from cl.search.cluster_sources import ClusterSources
from cl.search.models import (
    Citation,
    Court,
    Docket,
    DocketEntry,
    Opinion,
    OpinionCluster,
    OpinionsCited,
    RECAPDocument,
    SCOTUSDocketEntry,
    ScotusDocketMetadata,
    SCOTUSDocument,
    Tag,
)


class CourtFilter(NoEmptyFilterSet):
    dockets = filters.RelatedFilter(
        "cl.search.filters.DocketFilter", queryset=Docket.objects.all()
    )
    jurisdiction = filters.MultipleChoiceFilter(choices=Court.JURISDICTIONS)
    parent_court = filters.CharFilter(
        field_name="parent_court__id",
        lookup_expr="exact",
    )

    class Meta:
        model = Court
        fields = {
            "id": ["exact"],
            "date_modified": DATETIME_LOOKUPS,
            "in_use": ["exact"],
            "has_opinion_scraper": ["exact"],
            "has_oral_argument_scraper": ["exact"],
            "position": INTEGER_LOOKUPS,
            "start_date": DATE_LOOKUPS,
            "end_date": DATE_LOOKUPS,
            "short_name": BASIC_TEXT_LOOKUPS,
            "full_name": BASIC_TEXT_LOOKUPS,
            "citation_string": BASIC_TEXT_LOOKUPS,
        }


class TagFilter(NoEmptyFilterSet):
    class Meta:
        model = Tag
        fields = {
            "id": ["exact"],
            "name": ["exact"],
        }


class DocketFilter(NoEmptyFilterSet):
    court = filters.RelatedFilter(CourtFilter, queryset=Court.objects.all())
    clusters = filters.RelatedFilter(
        "cl.search.filters.OpinionClusterFilter",
        queryset=OpinionCluster.objects.all(),
    )
    docket_entries = filters.RelatedFilter(
        "cl.search.filters.DocketEntryFilter",
        queryset=DocketEntry.objects.all(),
    )
    audio_files = filters.RelatedFilter(
        "cl.audio.filters.AudioFilter", queryset=Audio.objects.all()
    )
    assigned_to = filters.RelatedFilter(
        "cl.people_db.filters.PersonFilter", queryset=Person.objects.all()
    )
    referred_to = filters.RelatedFilter(
        "cl.people_db.filters.PersonFilter", queryset=Person.objects.all()
    )
    parties = filters.RelatedFilter(
        "cl.people_db.filters.PartyFilter",
        queryset=Party.objects.all(),
        distinct=True,
    )
    tags = filters.RelatedFilter(TagFilter, queryset=Tag.objects.all())

    class Meta:
        model = Docket
        fields = {
            "id": INTEGER_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "date_filed": DATE_LOOKUPS,
            "date_terminated": DATE_LOOKUPS,
            "date_last_filing": DATE_LOOKUPS,
            "docket_number": ["exact"],
            "docket_number_core": ["exact", "startswith"],
            "nature_of_suit": BASIC_TEXT_LOOKUPS,
            "pacer_case_id": ["exact"],
            "source": ["exact", "in"],
            "date_blocked": DATE_LOOKUPS,
            "blocked": ["exact"],
        }


class OpinionFilter(NoEmptyFilterSet):
    # Cannot to reference to opinions_cited here, due to it being a self join,
    # which is not supported (possibly for good reasons?)
    cluster = filters.RelatedFilter(
        "cl.search.filters.OpinionClusterFilter",
        queryset=OpinionCluster.objects.all(),
    )
    author = filters.RelatedFilter(
        "cl.people_db.filters.PersonFilter", queryset=Person.objects.all()
    )
    joined_by = filters.RelatedFilter(
        "cl.people_db.filters.PersonFilter", queryset=Person.objects.all()
    )
    type = filters.MultipleChoiceFilter(choices=Opinion.OPINION_TYPES)

    class Meta:
        model = Opinion
        fields = {
            "id": INTEGER_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "sha1": ["exact"],
            "extracted_by_ocr": ["exact"],
            "per_curiam": ["exact"],
        }


class CitationFilter(NoEmptyFilterSet):
    class Meta:
        model = Citation
        fields = {
            "volume": ["exact"],
            "reporter": ["exact"],
            "page": ["exact"],
            "type": ["exact"],
        }


class OpinionClusterFilter(NoEmptyFilterSet):
    docket = filters.RelatedFilter(DocketFilter, queryset=Docket.objects.all())
    panel = filters.RelatedFilter(
        "cl.people_db.filters.PersonFilter", queryset=Person.objects.all()
    )
    non_participating_judges = filters.RelatedFilter(
        "cl.people_db.filters.PersonFilter", queryset=Person.objects.all()
    )
    sub_opinions = filters.RelatedFilter(
        OpinionFilter, queryset=Opinion.objects.all()
    )
    source = filters.MultipleChoiceFilter(choices=ClusterSources.NAMES)
    citations = filters.RelatedFilter(
        CitationFilter, queryset=Citation.objects.all()
    )

    class Meta:
        model = OpinionCluster
        fields = {
            "id": INTEGER_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "date_filed": DATE_LOOKUPS,
            "scdb_id": ["exact"],
            "scdb_decision_direction": ["exact"],
            "scdb_votes_majority": INTEGER_LOOKUPS,
            "scdb_votes_minority": INTEGER_LOOKUPS,
            "citation_count": INTEGER_LOOKUPS,
            "precedential_status": ["exact"],
            "date_blocked": DATE_LOOKUPS,
            "blocked": ["exact"],
        }


class OpinionsCitedFilter(NoEmptyFilterSet):
    citing_opinion = filters.RelatedFilter(
        OpinionFilter, queryset=Opinion.objects.all()
    )
    cited_opinion = filters.RelatedFilter(
        OpinionFilter, queryset=Opinion.objects.all()
    )

    class Meta:
        model = OpinionsCited
        fields = {
            "id": INTEGER_LOOKUPS,
        }


class DocketEntryFilter(NoEmptyFilterSet):
    docket = filters.RelatedFilter(DocketFilter, queryset=Docket.objects.all())
    recap_documents = filters.RelatedFilter(
        "cl.search.filters.RECAPDocumentFilter",
        queryset=RECAPDocument.objects.all(),
    )
    tags = filters.RelatedFilter(TagFilter, queryset=Tag.objects.all())

    class Meta:
        model = DocketEntry
        fields = {
            "id": INTEGER_LOOKUPS,
            "entry_number": INTEGER_LOOKUPS + ["isnull"],
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "date_filed": DATE_LOOKUPS,
            "pacer_sequence_number": INTEGER_LOOKUPS + ["isnull"],
        }


class RECAPDocumentFilter(NoEmptyFilterSet):
    docket_entry = filters.RelatedFilter(
        DocketEntryFilter, queryset=DocketEntry.objects.all()
    )
    tags = filters.RelatedFilter(TagFilter, queryset=Tag.objects.all())

    class Meta:
        model = RECAPDocument
        fields = {
            "id": INTEGER_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "date_upload": DATETIME_LOOKUPS,
            "document_type": ["exact"],
            "document_number": ["exact", "gte", "gt", "lte", "lt"],
            # Parameter required in view.
            "pacer_doc_id": ["exact", "in"],
            "is_available": ["exact"],
            "sha1": ["exact"],
            "ocr_status": INTEGER_LOOKUPS,
            "is_free_on_pacer": ["exact"],
        }


class BaseSourceFilter(NoEmptyFilterSet):
    """Base filterset for models of a single docket source.

    django-filter doesn't merge Meta.fields through inheritance, so
    subclasses must spread their parent's fields into their own:
    fields = {**BaseSourceFilter.Meta.fields, ...}
    """

    class Meta:
        fields: dict[str, list[str]] = {
            "id": INTEGER_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
        }


class BaseSourceDocketEntryFilter(BaseSourceFilter):
    """Base filterset for the docket entries of a docket source.

    Sources whose date_filed is a DateTimeField must override its lookups:
    there, date_filed=2025-01-01 only matches entries filed at midnight.
    """

    docket = filters.RelatedFilter(DocketFilter, queryset=Docket.objects.all())

    class Meta(BaseSourceFilter.Meta):
        fields = {
            **BaseSourceFilter.Meta.fields,
            "date_filed": DATE_LOOKUPS,
        }


class BaseSourceDocumentFilter(BaseSourceFilter):
    """Base filterset for the documents of a docket source.

    Pairs with BaseSourceDocumentSerializer: the model's is_available property
    must read its filepath_local file field.
    """

    is_available = filters.BooleanFilter(method="filter_is_available")

    class Meta(BaseSourceFilter.Meta):
        fields = {
            **BaseSourceFilter.Meta.fields,
            "sha1": ["exact"],
            "ocr_status": INTEGER_LOOKUPS,
        }

    def filter_is_available(
        self, queryset: QuerySet, name: str, value: bool
    ) -> QuerySet:
        """Filter on whether the document has a file.

        is_available is a model property, not a column, so it can't be
        looked up directly.
        """
        if value:
            return queryset.exclude(filepath_local="")
        return queryset.filter(filepath_local="")


class ScotusDocketMetadataFilter(BaseSourceFilter):
    """Filters for SCOTUS docket metadata."""

    docket = filters.RelatedFilter(DocketFilter, queryset=Docket.objects.all())

    class Meta(BaseSourceFilter.Meta):
        model = ScotusDocketMetadata
        fields = {
            **BaseSourceFilter.Meta.fields,
            "capital_case": ["exact"],
            "date_discretionary_court_decision": DATE_LOOKUPS,
        }


class SCOTUSDocketEntryFilter(BaseSourceDocketEntryFilter):
    """Filters for SCOTUS docket entries."""

    scotus_documents = filters.RelatedFilter(
        "cl.search.filters.SCOTUSDocumentFilter",
        queryset=SCOTUSDocument.objects.all(),
        distinct=True,
    )

    class Meta(BaseSourceDocketEntryFilter.Meta):
        model = SCOTUSDocketEntry
        fields = {
            **BaseSourceDocketEntryFilter.Meta.fields,
            "entry_number": INTEGER_LOOKUPS + ["isnull"],
        }


class SCOTUSDocumentFilter(BaseSourceDocumentFilter):
    """Filters for SCOTUS documents."""

    docket_entry = filters.RelatedFilter(
        SCOTUSDocketEntryFilter, queryset=SCOTUSDocketEntry.objects.all()
    )

    class Meta(BaseSourceDocumentFilter.Meta):
        model = SCOTUSDocument
        fields = {
            **BaseSourceDocumentFilter.Meta.fields,
            "document_number": INTEGER_LOOKUPS + ["isnull"],
            "attachment_number": INTEGER_LOOKUPS + ["isnull"],
        }
