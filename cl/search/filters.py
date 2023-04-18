import rest_framework_filters as filters

from cl.api.utils import (
    ALL_TEXT_LOOKUPS,
    DATE_LOOKUPS,
    DATETIME_LOOKUPS,
    INTEGER_LOOKUPS,
    NoEmptyFilterSet,
)
from cl.audio.models import Audio
from cl.people_db.models import Party, Person
from cl.search.models import (
    SOURCES,
    Citation,
    Court,
    Docket,
    DocketEntry,
    Opinion,
    OpinionCluster,
    OpinionsCited,
    RECAPDocument,
    Tag,
)


class CourtFilter(NoEmptyFilterSet):
    dockets = filters.RelatedFilter(
        "cl.search.filters.DocketFilter", queryset=Docket.objects.all()
    )
    jurisdiction = filters.MultipleChoiceFilter(choices=Court.JURISDICTIONS)

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
            "short_name": ALL_TEXT_LOOKUPS,
            "full_name": ALL_TEXT_LOOKUPS,
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
        "cl.people_db.filters.PartyFilter", queryset=Party.objects.all()
    )
    tags = filters.RelatedFilter(TagFilter, queryset=Tag.objects.all())

    class Meta:
        model = Docket
        fields = {
            "id": ["exact"],
            "date_modified": DATETIME_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "date_filed": DATE_LOOKUPS,
            "date_terminated": DATE_LOOKUPS,
            "date_last_filing": DATE_LOOKUPS,
            "docket_number": ["exact", "startswith"],
            "docket_number_core": ["exact", "startswith"],
            "nature_of_suit": ALL_TEXT_LOOKUPS,
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
    source = filters.MultipleChoiceFilter(choices=SOURCES.NAMES)
    citations = filters.RelatedFilter(
        CitationFilter, queryset=Citation.objects.all()
    )

    class Meta:
        model = OpinionCluster
        fields = {
            "id": ["exact"],
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
            "id": ["exact"],
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
            "id": ["exact"],
            "entry_number": INTEGER_LOOKUPS,
            "date_created": DATETIME_LOOKUPS,
            "date_modified": DATETIME_LOOKUPS,
            "date_filed": DATE_LOOKUPS,
        }


class RECAPDocumentFilter(NoEmptyFilterSet):
    docket_entry = filters.RelatedFilter(
        DocketEntryFilter, queryset=DocketEntry.objects.all()
    )
    tags = filters.RelatedFilter(TagFilter, queryset=Tag.objects.all())

    class Meta:
        model = RECAPDocument
        fields = {
            "id": ["exact"],
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
