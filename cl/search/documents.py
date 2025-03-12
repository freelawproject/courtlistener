from collections.abc import Callable
from datetime import datetime
from functools import partial
from typing import Any

from django.conf import settings
from django.http import QueryDict
from django.utils.html import escape, strip_tags
from django_elasticsearch_dsl import Document, fields
from elasticsearch_dsl import Document as DSLDocument

from cl.alerts.models import Alert
from cl.audio.models import Audio
from cl.corpus_importer.utils import is_bankruptcy_court
from cl.custom_filters.templatetags.extras import render_string_or_list
from cl.custom_filters.templatetags.text_filters import (
    best_case_name,
    html_decode,
)
from cl.lib.command_utils import logger
from cl.lib.elasticsearch_utils import (
    CSVSerializableDocumentMixin,
    build_es_base_query,
)
from cl.lib.fields import JoinField, PercolatorField
from cl.lib.search_index_utils import (
    get_parties_from_case_name,
    get_parties_from_case_name_bankr,
    null_map,
)
from cl.lib.utils import deepgetattr
from cl.people_db.models import (
    DATE_GRANULARITIES,
    Attorney,
    AttorneyOrganization,
    Person,
    Position,
)
from cl.search.constants import (
    PEOPLE_ES_HL_FIELDS,
    PEOPLE_ES_HL_KEYWORD_FIELDS,
    SEARCH_OPINION_CHILD_HL_FIELDS,
    SEARCH_OPINION_HL_FIELDS,
    SEARCH_ORAL_ARGUMENT_ES_HL_FIELDS,
    SEARCH_RECAP_CHILD_HL_FIELDS,
    SEARCH_RECAP_HL_FIELDS,
    o_type_index_map,
)
from cl.search.es_indices import (
    opinion_index,
    oral_arguments_index,
    oral_arguments_percolator_index,
    parenthetical_group_index,
    people_db_index,
    recap_index,
)
from cl.search.forms import SearchForm
from cl.search.models import (
    PRECEDENTIAL_STATUS,
    SOURCES,
    BankruptcyInformation,
    Citation,
    Docket,
    Opinion,
    OpinionCluster,
    ParentheticalGroup,
    RECAPDocument,
)


@parenthetical_group_index.document
class ParentheticalGroupDocument(CSVSerializableDocumentMixin, Document):
    author_id = fields.IntegerField(attr="opinion.author_id")
    caseName = fields.TextField(attr="opinion.cluster.case_name")
    citeCount = fields.IntegerField(attr="opinion.cluster.citation_count")
    citation = fields.ListField(
        fields.KeywordField(),
    )
    cites = fields.ListField(
        fields.IntegerField(),
    )
    cluster_id = fields.IntegerField(attr="opinion.cluster_id")
    court_id = fields.KeywordField(attr="opinion.cluster.docket.court.pk")
    dateFiled = fields.DateField(attr="opinion.cluster.date_filed")
    describing_opinion_cluster_id = fields.KeywordField(
        attr="representative.describing_opinion.cluster.id"
    )
    describing_opinion_cluster_slug = fields.KeywordField(
        attr="representative.describing_opinion.cluster.slug"
    )
    docket_id = fields.IntegerField(attr="opinion.cluster.docket_id")
    docketNumber = fields.TextField(
        attr="opinion.cluster.docket.docket_number",
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                attr="opinion.cluster.docket.docket_number",
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
                term_vector="with_positions_offsets",
            ),
        },
        search_analyzer="search_analyzer",
    )
    judge = fields.TextField(
        attr="opinion.cluster.judges",
    )
    lexisCite = fields.ListField(
        fields.KeywordField(),
    )
    neutralCite = fields.ListField(
        fields.KeywordField(),
    )
    opinion_cluster_slug = fields.KeywordField(attr="opinion.cluster.slug")
    opinion_extracted_by_ocr = fields.BooleanField(
        attr="opinion.extracted_by_ocr"
    )
    panel_ids = fields.ListField(
        fields.IntegerField(),
    )
    representative_score = fields.KeywordField(attr="representative.score")
    representative_text = fields.TextField(
        attr="representative.text",
    )
    status = fields.KeywordField()
    suitNature = fields.TextField(
        attr="opinion.cluster.nature_of_suit",
    )

    class Django:
        model = ParentheticalGroup
        fields = ["score"]
        ignore_signals = True

    @classmethod
    def get_csv_headers(cls) -> list[str]:
        return [
            "author_id",
            "citation",
            "cite_count",
            "cites",
            "cluster_id",
            "docket_id",
            "court_id",
            "docket_number",
            "case_name",
            "date_filed",
            "describing_opinion_cluster_id",
            "describing_opinion_cluster_slug",
            "judge",
            "lexis_cite",
            "neutral_cite",
            "opinion_cluster_slug",
            "opinion_extracted_by_ocr",
            "panel_ids",
            "representative_score",
            "representative_text",
            "status",
            "suit_nature",
        ]

    @classmethod
    def get_csv_transformations(cls) -> dict[str, Callable[..., Any]]:
        hl_fields = ["representative_text", "docketNumber"]
        transformations = {
            key: lambda x: render_string_or_list(x) for key in hl_fields
        }
        return transformations

    def prepare_citation(self, instance):
        return [str(cite) for cite in instance.opinion.cluster.citations.all()]

    def prepare_cites(self, instance):
        return list(
            instance.opinion.opinions_cited.all().values_list("id", flat=True)
        )

    def prepare_lexisCite(self, instance):
        try:
            return str(
                instance.opinion.cluster.citations.filter(type=Citation.LEXIS)[
                    0
                ]
            )
        except IndexError:
            pass

    def prepare_neutralCite(self, instance):
        try:
            return str(
                instance.opinion.cluster.citations.filter(
                    type=Citation.NEUTRAL
                )[0]
            )
        except IndexError:
            pass

    def prepare_panel_ids(self, instance):
        return list(
            instance.opinion.cluster.panel.all().values_list("id", flat=True)
        )

    def prepare_status(self, instance):
        return instance.opinion.cluster.precedential_status


class AudioDocumentBase(Document):
    absolute_url = fields.KeywordField(index=False)
    caseName = fields.TextField(
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
                term_vector="with_positions_offsets",
            ),
        },
        search_analyzer="search_analyzer",
    )
    case_name_full = fields.TextField(
        attr="case_name_full",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="case_name_full",
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    court = fields.TextField(
        attr="docket.court.full_name",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="docket.court.full_name",
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    court_exact = fields.KeywordField(attr="docket.court.pk", index=False)
    court_id = fields.KeywordField(attr="docket.court.pk")
    court_id_text = fields.TextField(
        attr="docket.court.pk",
        analyzer="text_en_splitting_cl",
        search_analyzer="search_analyzer",
    )
    court_citation_string = fields.TextField(
        attr="docket.court.citation_string",
        analyzer="text_en_splitting_cl",
        search_analyzer="search_analyzer",
        term_vector="with_positions_offsets",
    )
    docket_id = fields.IntegerField(attr="docket.pk")
    dateArgued = fields.DateField(attr="docket.date_argued")
    dateReargued = fields.DateField(attr="docket.date_reargued")
    dateReargumentDenied = fields.DateField(
        attr="docket.date_reargument_denied"
    )
    dateArgued_text = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    dateReargued_text = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    dateReargumentDenied_text = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    docketNumber = fields.TextField(
        attr="docket.docket_number",
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                attr="docket.docket_number",
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
                term_vector="with_positions_offsets",
            ),
        },
        search_analyzer="search_analyzer",
    )
    docket_slug = fields.KeywordField(attr="docket.slug", index=False)
    duration = fields.IntegerField(attr="duration", index=False)
    download_url = fields.KeywordField(attr="download_url", index=False)
    file_size_mp3 = fields.IntegerField(index=False)
    id = fields.IntegerField(attr="pk")
    judge = fields.TextField(
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
                term_vector="with_positions_offsets",
            ),
        },
        search_analyzer="search_analyzer",
    )
    local_path = fields.KeywordField(index=False)
    pacer_case_id = fields.KeywordField(attr="docket.pacer_case_id")
    panel_ids = fields.ListField(
        fields.IntegerField(),
    )
    sha1 = fields.TextField(attr="sha1")
    source = fields.KeywordField(attr="source", index=False)
    text = fields.TextField(
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
                term_vector="with_positions_offsets",
            ),
        },
        search_analyzer="search_analyzer",
    )
    timestamp = fields.DateField()
    date_created = fields.DateField(attr="date_created")


@oral_arguments_index.document
class AudioDocument(CSVSerializableDocumentMixin, AudioDocumentBase):
    class Django:
        model = Audio
        ignore_signals = True

    @classmethod
    def get_csv_headers(cls) -> list[str]:
        return [
            "id",
            "court_id",
            "court_citation_string",
            "docket_id",
            "docket_number",
            "docket_slug",
            "case_name",
            "case_name_full",
            "pacer_case_id",
            "judge",
            "local_path",
            "absolute_url",
            "duration",
            "file_size_mp3",
            "download_url",
            "panel_ids",
            "sha1",
            "source",
            "text",
            "date_argued",
            "date_argued_text",
            "date_reargued",
            "date_reargued_text",
            "date_reargument_denied",
            "date_reargument_denied_text",
            "date_created",
        ]

    @classmethod
    def get_csv_transformations(cls) -> dict[str, Callable[..., Any]]:
        transformations = {
            key: lambda x: render_string_or_list(x)
            for key in SEARCH_ORAL_ARGUMENT_ES_HL_FIELDS.keys()
        }
        transformations["absolute_url"] = (
            lambda x: f"https://www.courtlistener.com{x}"
        )
        transformations["local_path"] = lambda x: (
            f"https://storage.courtlistener.com/{x}" if x else ""
        )
        transformations["source"] = lambda x: dict(SOURCES.NAMES).get(x, x)
        return transformations

    def prepare_absolute_url(self, instance):
        return instance.get_absolute_url()

    def prepare_caseName(self, instance):
        return best_case_name(instance)

    def prepare_panel_ids(self, instance):
        return list(instance.panel.all().values_list("id", flat=True))

    def prepare_file_size_mp3(self, instance):
        if instance.local_path_mp3:
            if not instance.local_path_mp3.storage.exists(
                instance.local_path_mp3.name
            ):
                logger.warning(
                    f"The file {instance.local_path_mp3.name} associated with "
                    f"Audio ID {instance.pk} not found in S3. "
                )
                return None
            return deepgetattr(instance, "local_path_mp3.size", None)

    def prepare_local_path(self, instance):
        if instance.local_path_mp3:
            if not instance.local_path_mp3.storage.exists(
                instance.local_path_mp3.name
            ):
                logger.warning(
                    f"The file {instance.local_path_mp3.name} associated with "
                    f"Audio ID {instance.pk} not found in S3. "
                )
                return None
            return deepgetattr(instance, "local_path_mp3.name", None)

    def prepare_judge(self, instance):
        if instance.judges:
            return instance.judges
        return ""

    def prepare_text(self, instance):
        if instance.stt_status == Audio.STT_COMPLETE:
            return instance.transcript
        return ""

    def prepare_dateArgued_text(self, instance):
        if instance.docket.date_argued:
            return instance.docket.date_argued.strftime("%-d %B %Y")

    def prepare_dateReargued_text(self, instance):
        if instance.docket.date_reargued:
            return instance.docket.date_reargued.strftime("%-d %B %Y")

    def prepare_dateReargumentDenied_text(self, instance):
        if instance.docket.date_reargument_denied:
            return instance.docket.date_reargument_denied.strftime("%-d %B %Y")

    def prepare_timestamp(self, instance):
        return datetime.utcnow()


@oral_arguments_percolator_index.document
class AudioPercolator(AudioDocumentBase):
    rate = fields.KeywordField(attr="rate")
    percolator_query = PercolatorField()

    class Django:
        model = Alert
        ignore_signals = True

    def prepare_timestamp(self, instance):
        return datetime.utcnow()

    def prepare_percolator_query(self, instance):
        qd = QueryDict(instance.query.encode(), mutable=True)
        if "order_by" in qd:
            # sorting key is not required in percolator queries. Adding it
            # generates a custom function score for decay relevance, which breaks
            # percolator queries.
            del qd["order_by"]
        search_form = SearchForm(qd)
        if not search_form.is_valid():
            logger.warning(
                f"The query {qd} associated with Alert ID {instance.pk} is "
                "invalid and was not indexed."
            )
            return None

        cd = search_form.cleaned_data
        search_query = AudioDocument.search()
        es_queries = build_es_base_query(search_query, cd)
        return es_queries.search_query.to_dict()["query"]


class ES_CHILD_ID:
    """Returns an ID for its use in ES child documents"""

    def __init__(self, instance_id: int):
        self.instance_id = instance_id

    @property
    def POSITION(self) -> str:
        return f"po_{self.instance_id}"

    @property
    def RECAP(self) -> str:
        return f"rd_{self.instance_id}"

    @property
    def OPINION(self) -> str:
        return f"o_{self.instance_id}"


class PersonBaseDocument(Document):
    id = fields.IntegerField(attr="pk")
    alias_ids = fields.ListField(
        fields.IntegerField(multi=True),
    )
    races = fields.ListField(
        fields.KeywordField(multi=True),
    )
    political_affiliation_id = fields.ListField(
        fields.KeywordField(multi=True),
    )
    fjc_id = fields.TextField()
    name = fields.TextField(
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
                term_vector="with_positions_offsets",
            ),
        },
        search_analyzer="search_analyzer",
    )
    gender = fields.TextField()
    religion = fields.TextField()
    alias = fields.ListField(
        fields.TextField(
            analyzer="text_en_splitting_cl",
            fields={
                "exact": fields.TextField(
                    analyzer="english_exact",
                    search_analyzer="search_analyzer_exact",
                ),
            },
            search_analyzer="search_analyzer",
            multi=True,
        )
    )
    dob = fields.DateField(attr="date_dob")
    dod = fields.DateField(attr="date_dod")
    dob_city = fields.TextField(
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
                term_vector="with_positions_offsets",
            ),
        },
        search_analyzer="search_analyzer",
    )
    dob_state = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    dob_state_id = fields.KeywordField(attr="dob_state")
    political_affiliation = fields.ListField(
        fields.TextField(
            analyzer="text_en_splitting_cl",
            term_vector="with_positions_offsets",
            fields={
                "exact": fields.TextField(
                    analyzer="english_exact",
                    search_analyzer="search_analyzer_exact",
                    term_vector="with_positions_offsets",
                ),
            },
            search_analyzer="search_analyzer",
            multi=True,
        )
    )
    aba_rating = fields.ListField(
        fields.TextField(
            analyzer="text_en_splitting_cl",
            fields={
                "exact": fields.TextField(
                    analyzer="english_exact",
                    search_analyzer="search_analyzer_exact",
                ),
            },
            search_analyzer="search_analyzer",
            multi=True,
        )
    )
    school = fields.ListField(
        fields.TextField(
            analyzer="text_en_splitting_cl",
            term_vector="with_positions_offsets",
            fields={
                "exact": fields.TextField(
                    analyzer="english_exact",
                    search_analyzer="search_analyzer_exact",
                    term_vector="with_positions_offsets",
                ),
            },
            search_analyzer="search_analyzer",
            multi=True,
        )
    )
    person_child = JoinField(relations={"person": ["position"]})
    timestamp = fields.DateField()
    date_created = fields.DateField(attr="date_created")

    class Django:
        model = Person
        ignore_signals = True

    def prepare_timestamp(self, instance):
        return datetime.utcnow()

    def prepare_name(self, instance):
        return instance.name_full

    def prepare_religion(self, instance):
        return instance.religion

    def prepare_gender(self, instance):
        return instance.get_gender_display()

    def prepare_dob_city(self, instance):
        return instance.dob_city

    def prepare_fjc_id(self, instance):
        return str(instance.fjc_id)

    def prepare_political_affiliation(self, instance):
        return [
            pa.get_political_party_display()
            for pa in instance.political_affiliations.all()
            if pa
        ]

    def prepare_dob_state(self, instance):
        return instance.get_dob_state_display()

    def prepare_alias(self, instance):
        return [r.name_full for r in instance.aliases.all()]

    def prepare_aba_rating(self, instance):
        return [
            r.get_rating_display() for r in instance.aba_ratings.all() if r
        ]

    def prepare_school(self, instance):
        return [e.school.name for e in instance.educations.all()]

    def prepare_races(self, instance):
        return [r.get_race_display() for r in instance.race.all()]

    def prepare_alias_ids(self, instance):
        return [alias.pk for alias in instance.aliases.all()]

    def prepare_political_affiliation_id(self, instance):
        return [
            pa.political_party
            for pa in instance.political_affiliations.all()
            if pa
        ]


@people_db_index.document
class PositionDocument(PersonBaseDocument):
    court = fields.TextField(
        attr="court.short_name",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="court.short_name",
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    court_full_name = fields.TextField(
        attr="court.full_name",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="court.full_name",
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    court_exact = fields.TextField(
        attr="court.pk",
        analyzer="text_en_splitting_cl",
        fields={"raw": fields.KeywordField(attr="court.pk")},
        search_analyzer="search_analyzer",
    )
    court_citation_string = fields.TextField(
        attr="court.citation_string",
        analyzer="text_en_splitting_cl",
        search_analyzer="search_analyzer",
    )
    organization_name = fields.TextField(attr="organization_name")
    job_title = fields.TextField(
        attr="job_title",
        analyzer="text_en_splitting_cl",
        search_analyzer="search_analyzer",
    )
    position_type = fields.TextField(
        analyzer="text_en_splitting_cl",
        search_analyzer="search_analyzer",
        fields={"raw": fields.KeywordField()},
    )
    appointer = fields.TextField(
        attr="appointer.person.name_full_reverse",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="appointer.person.name_full_reverse",
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    supervisor = fields.TextField(
        attr="supervisor.name_full_reverse",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="supervisor.name_full_reverse",
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    predecessor = fields.TextField(
        attr="predecessor.name_full_reverse",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="predecessor.name_full_reverse",
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    date_nominated = fields.DateField(attr="date_nominated")
    date_elected = fields.DateField(attr="date_elected")
    date_recess_appointment = fields.DateField(attr="date_recess_appointment")
    date_referred_to_judicial_committee = fields.DateField(
        attr="date_referred_to_judicial_committee"
    )
    date_judicial_committee_action = fields.DateField(
        attr="date_judicial_committee_action"
    )
    date_hearing = fields.DateField(attr="date_hearing")
    date_confirmation = fields.DateField(attr="date_confirmation")
    date_start = fields.DateField(attr="date_start")
    date_granularity_start = fields.KeywordField(attr="date_granularity_start")
    date_retirement = fields.DateField(attr="date_retirement")
    date_termination = fields.DateField(attr="date_termination")
    date_granularity_termination = fields.KeywordField(
        attr="date_granularity_termination"
    )
    judicial_committee_action = fields.TextField(
        analyzer="text_en_splitting_cl",
        search_analyzer="search_analyzer",
        fields={"raw": fields.KeywordField()},
    )

    nomination_process = fields.TextField(
        analyzer="text_en_splitting_cl",
        search_analyzer="search_analyzer",
        fields={"raw": fields.KeywordField()},
    )
    selection_method = fields.TextField(
        analyzer="text_en_splitting_cl",
        search_analyzer="search_analyzer",
        fields={"raw": fields.KeywordField()},
    )
    selection_method_id = fields.KeywordField(attr="how_selected")

    termination_reason = fields.TextField(
        analyzer="text_en_splitting_cl",
        search_analyzer="search_analyzer",
        fields={"raw": fields.KeywordField()},
    )

    class Django:
        model = Position
        ignore_signals = True

    def prepare_position_type(self, instance):
        return instance.get_position_type_display()

    def prepare_judicial_committee_action(self, instance):
        return instance.get_judicial_committee_action_display()

    def prepare_nomination_process(self, instance):
        return instance.get_nomination_process_display()

    def prepare_selection_method(self, instance):
        return instance.get_how_selected_display()

    def prepare_termination_reason(self, instance):
        return instance.get_termination_reason_display()

    def prepare_person_child(self, instance):
        parent_id = getattr(instance.person, "pk", None)
        return {"name": "position", "parent": parent_id}

    def prepare_name(self, instance):
        return instance.person.name_full

    def prepare_religion(self, instance):
        return instance.person.religion

    def prepare_dob_city(self, instance):
        return instance.person.dob_city

    def prepare_gender(self, instance):
        return instance.person.get_gender_display()

    def prepare_fjc_id(self, instance):
        return str(instance.person.fjc_id)

    def prepare_dob_state(self, instance):
        return instance.person.get_dob_state_display()

    def prepare_id(self, instance):
        return instance.person.pk

    def prepare_dob_state_id(self, instance):
        return instance.person.dob_state

    def prepare_dob(self, instance):
        return instance.person.date_dob

    def prepare_dod(self, instance):
        return instance.person.date_dod

    def prepare_political_affiliation(self, instance):
        return [
            pa.get_political_party_display()
            for pa in instance.person.political_affiliations.all()
            if pa
        ]

    def prepare_alias(self, instance):
        return [r.name_full for r in instance.person.aliases.all()]

    def prepare_aba_rating(self, instance):
        return [
            r.get_rating_display()
            for r in instance.person.aba_ratings.all()
            if r
        ]

    def prepare_school(self, instance):
        return [e.school.name for e in instance.person.educations.all()]

    def prepare_races(self, instance):
        return [r.get_race_display() for r in instance.person.race.all()]

    def prepare_alias_ids(self, instance):
        return [alias.pk for alias in instance.person.aliases.all()]

    def prepare_political_affiliation_id(self, instance):
        return [
            pa.political_party
            for pa in instance.person.political_affiliations.all()
            if pa
        ]


@people_db_index.document
class PersonDocument(CSVSerializableDocumentMixin, PersonBaseDocument):
    name_reverse = fields.KeywordField(
        attr="name_full_reverse",
    )
    date_granularity_dob = fields.KeywordField(attr="date_granularity_dob")
    date_granularity_dod = fields.KeywordField(attr="date_granularity_dod")
    absolute_url = fields.KeywordField()

    @classmethod
    def get_csv_headers(cls) -> list[str]:
        return [
            "id",
            "name",
            "name_reverse",
            "court",
            "absolute_url",
            "gender",
            "religion",
            "alias",
            "races",
            "political_affiliation",
            "selection_method",
            "fjc_id",
            "dob",
            "dob_city",
            "dob_state",
            "dob_state_id",
            "date_granularity_dob",
            "dod",
            "date_granularity_dod",
            "aba_rating",
            "school",
            "appointer",
            "supervisor",
            "predecessor",
            "date_created",
        ]

    @classmethod
    def get_csv_transformations(cls) -> dict[str, Callable[..., Any]]:
        list_fields = [
            "races",
            "aba_rating",
            "alias",
            "selection_method",
            "appointer",
            "supervisor",
            "predecessor",
            "court",
        ]
        hl_fields = (
            list(PEOPLE_ES_HL_FIELDS.keys()) + PEOPLE_ES_HL_KEYWORD_FIELDS
        )
        transformations = {
            key: lambda x: render_string_or_list(x)
            for key in (hl_fields + list_fields)
        }

        # Adds tranformation for relative URL and compute human-readable values
        transformations["absolute_url"] = (
            lambda x: f"https://www.courtlistener.com{x}"
        )
        transformations["religion"] = lambda x: dict(Person.RELIGIONS).get(
            x, x
        )
        transformations["date_granularity_dob"] = lambda x: dict(
            DATE_GRANULARITIES
        ).get(x, x)
        transformations["date_granularity_dod"] = lambda x: dict(
            DATE_GRANULARITIES
        ).get(x, x)
        return transformations

    def prepare_person_child(self, instance):
        return "person"

    def prepare_absolute_url(self, instance):
        return instance.get_absolute_url()


# RECAP
class RECAPBaseDocument(Document):
    docket_child = JoinField(relations={"docket": ["recap_document"]})
    timestamp = fields.DateField()

    # Docket Fields
    docket_id = fields.IntegerField(attr="pk")
    caseName = fields.TextField(
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
                term_vector="with_positions_offsets",
            ),
        },
        search_analyzer="search_analyzer",
    )
    case_name_full = fields.TextField(
        attr="case_name_full",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="case_name_full",
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    docketNumber = fields.TextField(
        attr="docket_number",
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                attr="docket_number",
                analyzer="english_exact",
                term_vector="with_positions_offsets",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    suitNature = fields.TextField(
        attr="nature_of_suit",
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                attr="nature_of_suit",
                analyzer="english_exact",
                term_vector="with_positions_offsets",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    cause = fields.TextField(
        attr="cause",
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                attr="cause",
                analyzer="english_exact",
                term_vector="with_positions_offsets",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    juryDemand = fields.TextField(
        attr="jury_demand",
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                attr="jury_demand",
                analyzer="english_exact",
                term_vector="with_positions_offsets",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    jurisdictionType = fields.TextField(
        attr="jurisdiction_type",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="jurisdiction_type",
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    dateArgued = fields.DateField(attr="date_argued")
    dateFiled = fields.DateField(attr="date_filed")
    dateTerminated = fields.DateField(attr="date_terminated")
    assignedTo = fields.TextField(
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                term_vector="with_positions_offsets",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    assigned_to_id = fields.KeywordField(attr="assigned_to.pk")
    referredTo = fields.TextField(
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                term_vector="with_positions_offsets",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    referred_to_id = fields.KeywordField(attr="referred_to.pk")
    court = fields.TextField(
        attr="court.full_name",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="court.full_name",
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    court_id = fields.TextField(
        attr="court.pk",
        analyzer="text_en_splitting_cl",
        fields={"raw": fields.KeywordField(attr="court.pk")},
        search_analyzer="search_analyzer",
    )
    court_citation_string = fields.TextField(
        attr="court.citation_string",
        analyzer="text_en_splitting_cl",
        search_analyzer="search_analyzer",
        term_vector="with_positions_offsets",
    )
    chapter = fields.TextField(
        analyzer="text_en_splitting_cl",
        search_analyzer="search_analyzer",
    )
    trustee_str = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    date_created = fields.DateField(attr="date_created")
    pacer_case_id = fields.KeywordField(attr="pacer_case_id")

    class Django:
        model = Docket
        ignore_signals = True

    def prepare_timestamp(self, instance):
        return datetime.utcnow()


class ESRECAPBaseDocument(DSLDocument):
    id = fields.IntegerField(attr="pk")
    docket_entry_id = fields.IntegerField(attr="docket_entry.pk")
    description = fields.TextField(
        attr="docket_entry.description",
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                attr="docket_entry.description",
                term_vector="with_positions_offsets",
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    entry_number = fields.LongField(attr="docket_entry.entry_number")
    entry_date_filed = fields.DateField(attr="docket_entry.date_filed")
    short_description = fields.TextField(
        attr="description",
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                attr="description",
                analyzer="english_exact",
                term_vector="with_positions_offsets",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    document_type = fields.TextField(
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                term_vector="with_positions_offsets",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    document_number = fields.LongField()
    pacer_doc_id = fields.KeywordField(attr="pacer_doc_id")
    plain_text = fields.TextField(
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                term_vector="with_positions_offsets",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    attachment_number = fields.IntegerField(attr="attachment_number")
    is_available = fields.BooleanField(attr="is_available")
    page_count = fields.IntegerField(attr="page_count")
    filepath_local = fields.KeywordField(index=False)
    absolute_url = fields.KeywordField(index=False)
    cites = fields.ListField(
        fields.IntegerField(multi=True),
    )


@recap_index.document
class ESRECAPDocument(
    CSVSerializableDocumentMixin, RECAPBaseDocument, ESRECAPBaseDocument
):

    class Django:
        model = RECAPDocument
        ignore_signals = True

    @classmethod
    def get_csv_headers(cls) -> list[str]:
        return [
            "docket_entry_description",
            "docket_entry_number",
            "docket_entry_date_filed",
            "rd_absolute_url",
            "pacer_doc_id",
            "document_type",
            "rd_description",
            "rd_is_available",
            "rd_page_count",
            "rd_filepath_local",
            "rd_plain_text",
            "cites",
        ]

    @classmethod
    def get_csv_transformations(cls) -> dict[str, Callable[..., Any]]:
        transformations = {
            key: partial(
                lambda key, val: render_string_or_list(
                    val.get(key) if isinstance(val, dict) else val
                ),
                key,
            )
            for key in SEARCH_RECAP_CHILD_HL_FIELDS.keys()
        }

        # Add a transformation for relative URLs.
        transformations["rd_filepath_local"] = lambda x: (
            f"https://storage.courtlistener.com/{x['filepath_local']}"
            if x.get("filepath_local")
            else ""
        )
        transformations["rd_absolute_url"] = lambda x: (
            f"https://www.courtlistener.com{x['absolute_url']}"
            if x.get("absolute_url")
            else ""
        )

        # Define a mapping of new CSV column names to the corresponding source
        # keys in the data. This allows renaming specific fields for the CSV
        # output.
        new_keys_mapping = {
            "docket_entry_description": "description",
            "docket_entry_number": "entry_number",
            "docket_entry_date_filed": "entry_date_filed",
            "rd_id": "id",
            "rd_description": "short_description",
            "rd_document_number": "document_number",
            "rd_attachment_number": "attachment_number",
            "rd_is_available": "is_available",
            "rd_page_count": "page_count",
            "rd_plain_text": "plain_text",
        }
        # Add transformations to rename fields. Each transformation extracts
        # the value from the source key in the input data.
        for new_key, source in new_keys_mapping.items():
            transformations[new_key] = partial(
                lambda origin_key, document: document.get(origin_key, ""),
                source,
            )
        return transformations

    def prepare_document_number(self, instance):
        return instance.document_number or None

    def prepare_document_type(self, instance):
        return instance.get_document_type_display()

    def prepare_filepath_local(self, instance):
        if instance.filepath_local:
            return instance.filepath_local.name

    def prepare_absolute_url(self, instance):
        return instance.get_absolute_url()

    def prepare_docket_child(self, instance):
        parent_id = getattr(instance.docket_entry.docket, "pk", None)
        return {"name": "recap_document", "parent": parent_id}

    def prepare_caseName(self, instance):
        return best_case_name(instance.docket_entry.docket)

    def prepare_assignedTo(self, instance):
        if instance.docket_entry.docket.assigned_to:
            return instance.docket_entry.docket.assigned_to.name_full
        elif instance.docket_entry.docket.assigned_to_str:
            return instance.docket_entry.docket.assigned_to_str

    def prepare_referredTo(self, instance):
        if instance.docket_entry.docket.referred_to:
            return instance.docket_entry.docket.referred_to.name_full
        elif instance.docket_entry.docket.referred_to_str:
            return instance.docket_entry.docket.referred_to_str

    def prepare_docket_id(self, instance):
        return instance.docket_entry.docket.pk

    def prepare_case_name_full(self, instance):
        return instance.docket_entry.docket.case_name_full

    def prepare_docketNumber(self, instance):
        return instance.docket_entry.docket.docket_number

    def prepare_suitNature(self, instance):
        return instance.docket_entry.docket.nature_of_suit

    def prepare_cause(self, instance):
        return instance.docket_entry.docket.cause

    def prepare_juryDemand(self, instance):
        return instance.docket_entry.docket.jury_demand

    def prepare_jurisdictionType(self, instance):
        return instance.docket_entry.docket.jurisdiction_type

    def prepare_dateArgued(self, instance):
        return instance.docket_entry.docket.date_argued

    def prepare_dateFiled(self, instance):
        return instance.docket_entry.docket.date_filed

    def prepare_dateTerminated(self, instance):
        return instance.docket_entry.docket.date_terminated

    def prepare_assigned_to_id(self, instance):
        if instance.docket_entry.docket.assigned_to:
            return instance.docket_entry.docket.assigned_to.pk

    def prepare_referred_to_id(self, instance):
        if instance.docket_entry.docket.referred_to:
            return instance.docket_entry.docket.referred_to.pk

    def prepare_court(self, instance):
        return instance.docket_entry.docket.court.full_name

    def prepare_court_id(self, instance):
        return instance.docket_entry.docket.court.pk

    def prepare_court_citation_string(self, instance):
        return instance.docket_entry.docket.court.citation_string

    def prepare_chapter(self, instance):
        if hasattr(instance.docket_entry.docket, "bankruptcy_information"):
            return instance.docket_entry.docket.bankruptcy_information.chapter

    def prepare_trustee_str(self, instance):
        if hasattr(instance.docket_entry.docket, "bankruptcy_information"):
            return (
                instance.docket_entry.docket.bankruptcy_information.trustee_str
            )

    def prepare_plain_text(self, instance):
        return escape(instance.plain_text.translate(null_map))

    def prepare_cites(self, instance):
        return list(
            instance.cited_opinions.all().values_list(
                "cited_opinion_id", flat=True
            )
        )

    def prepare_pacer_case_id(self, instance):
        return instance.docket_entry.docket.pacer_case_id


class DocketBaseDocument(DSLDocument):
    docket_slug = fields.KeywordField(attr="slug", index=False)
    docket_absolute_url = fields.KeywordField(index=False)
    court_exact = fields.KeywordField(attr="court.pk", index=False)

    # Parties
    party_id = fields.ListField(fields.IntegerField(multi=True))
    party = fields.ListField(
        fields.TextField(
            analyzer="text_en_splitting_cl",
            fields={
                "exact": fields.TextField(
                    analyzer="english_exact",
                    search_analyzer="search_analyzer_exact",
                ),
            },
            search_analyzer="search_analyzer",
            multi=True,
        )
    )
    attorney_id = fields.ListField(fields.IntegerField(multi=True))
    attorney = fields.ListField(
        fields.TextField(
            analyzer="text_en_splitting_cl",
            fields={
                "exact": fields.TextField(
                    analyzer="english_exact",
                    search_analyzer="search_analyzer_exact",
                ),
            },
            search_analyzer="search_analyzer",
            multi=True,
        )
    )
    firm_id = fields.ListField(fields.IntegerField(multi=True))
    firm = fields.ListField(
        fields.TextField(
            analyzer="text_en_splitting_cl",
            fields={
                "exact": fields.TextField(
                    analyzer="english_exact",
                    search_analyzer="search_analyzer_exact",
                ),
            },
            search_analyzer="search_analyzer",
            multi=True,
        )
    )


@recap_index.document
class DocketDocument(
    CSVSerializableDocumentMixin, DocketBaseDocument, RECAPBaseDocument
):

    @classmethod
    def get_csv_headers(cls) -> list[str]:
        return [
            "docket_id",
            "docket_entry_id",
            "rd_id",
            "docket_number",
            "rd_document_number",
            "rd_attachment_number",
            "docket_slug",
            "docket_absolute_url",
            "court_id",
            "court",
            "court_citation_string",
            "pacer_case_id",
            "case_name",
            "case_name_full",
            "suit_nature",
            "cause",
            "jury_demand",
            "jurisdiction_type",
            "date_argued",
            "date_filed",
            "date_terminated",
            "assigned_to",
            "assigned_to_id",
            "referred_to",
            "referred_to_id",
            "chapter",
            "trustee_str",
            "party_id",
            "party",
            "attorney_id",
            "attorney",
            "firm_id",
            "firm",
        ]

    @classmethod
    def get_csv_transformations(cls) -> dict[str, Callable[..., Any]]:
        list_fields = ["party", "attorney", "firm"]
        hl_fields = list(SEARCH_RECAP_HL_FIELDS.keys())
        transformations = {
            key: lambda x: render_string_or_list(x)
            for key in (hl_fields + list_fields)
        }
        # Add a transformation for relative URLs.
        transformations["docket_absolute_url"] = (
            lambda x: f"https://www.courtlistener.com{x}"
        )
        return transformations

    def prepare_caseName(self, instance):
        return best_case_name(instance)

    def prepare_assignedTo(self, instance):
        if instance.assigned_to:
            return instance.assigned_to.name_full
        elif instance.assigned_to_str:
            return instance.assigned_to_str

    def prepare_referredTo(self, instance):
        if instance.referred_to:
            return instance.referred_to.name_full
        elif instance.referred_to_str:
            return instance.referred_to_str

    def prepare_chapter(self, instance):
        if BankruptcyInformation.objects.filter(docket=instance).exists():
            return instance.bankruptcy_information.chapter

    def prepare_trustee_str(self, instance):
        if BankruptcyInformation.objects.filter(docket=instance).exists():
            return instance.bankruptcy_information.trustee_str

    def prepare_docket_child(self, instance):
        return "docket"

    def prepare_docket_absolute_url(self, instance):
        return instance.get_absolute_url()

    def prepare_parties(self, instance):
        out = {
            "party_id": set(),
            "party": set(),
            "attorney_id": set(),
            "attorney": set(),
            "firm_id": set(),
            "firm": set(),
        }

        # Extract only required parties values.
        party_values = instance.parties.values_list("pk", "name")
        for pk, name in party_values.iterator():
            out["party_id"].add(pk)
            out["party"].add(name)

        if not out["party"]:
            # Get party from docket case_name if no normalized parties are
            # available.
            party_from_case_name = (
                get_parties_from_case_name_bankr(instance.case_name)
                if is_bankruptcy_court(instance.court_id)
                else get_parties_from_case_name(instance.case_name)
            )
            out["party"] = party_from_case_name if party_from_case_name else []

        # Extract only required attorney values.
        atty_values = (
            Attorney.objects.filter(roles__docket=instance)
            .distinct()
            .values_list("pk", "name")
        )
        for pk, name in atty_values.iterator():
            out["attorney_id"].add(pk)
            out["attorney"].add(name)

        # Extract only required firm values.
        firms_values = (
            AttorneyOrganization.objects.filter(
                attorney_organization_associations__docket=instance
            )
            .distinct()
            .values_list("pk", "name")
        )
        for pk, name in firms_values.iterator():
            out["firm_id"].add(pk)
            out["firm"].add(name)

        return out

    def prepare(self, instance):
        data = super().prepare(instance)
        parties_prepared = self.prepare_parties(instance)
        data["party_id"] = list(parties_prepared["party_id"])
        data["party"] = list(parties_prepared["party"])
        data["attorney_id"] = list(parties_prepared["attorney_id"])
        data["attorney"] = list(parties_prepared["attorney"])
        data["firm_id"] = list(parties_prepared["firm_id"])
        data["firm"] = list(parties_prepared["firm"])
        return data


# Opinions
class OpinionBaseDocument(Document):
    absolute_url = fields.KeywordField(index=False)
    cluster_id = fields.IntegerField(
        attr="pk", fields={"raw": fields.KeywordField(attr="pk")}
    )
    docket_id = fields.IntegerField(
        attr="docket.pk", fields={"raw": fields.KeywordField(attr="docket.pk")}
    )
    docketNumber = fields.TextField(
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
                term_vector="with_positions_offsets",
            ),
        },
        search_analyzer="search_analyzer",
    )
    caseName = fields.TextField(
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
                term_vector="with_positions_offsets",
            ),
        },
        search_analyzer="search_analyzer",
    )
    caseNameFull = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    dateFiled = fields.DateField()
    dateArgued = fields.DateField()
    dateReargued = fields.DateField()
    dateReargumentDenied = fields.DateField()
    court_id = fields.TextField(
        analyzer="text_en_splitting_cl",
        search_analyzer="search_analyzer",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
            "raw": fields.KeywordField(),
        },
    )
    court = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    court_citation_string = fields.TextField(
        attr="docket.court.citation_string",
        analyzer="text_en_splitting_cl",
        search_analyzer="search_analyzer",
        term_vector="with_positions_offsets",
    )
    judge = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    panel_names = fields.ListField(
        fields.TextField(
            analyzer="text_en_splitting_cl",
            search_analyzer="search_analyzer",
            multi=True,
        ),
    )
    attorney = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    suitNature = fields.TextField(
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
                term_vector="with_positions_offsets",
            ),
        },
        search_analyzer="search_analyzer",
    )
    citation = fields.ListField(
        fields.TextField(
            analyzer="text_en_splitting_cl",
            term_vector="with_positions_offsets",
            fields={
                "exact": fields.TextField(
                    analyzer="english_exact",
                    search_analyzer="search_analyzer_exact",
                    term_vector="with_positions_offsets",
                    multi=True,
                ),
            },
            search_analyzer="search_analyzer",
            multi=True,
        )
    )
    status = fields.TextField(
        analyzer="text_en_splitting_cl",
        search_analyzer="search_analyzer",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
            "raw": fields.KeywordField(),
        },
    )
    procedural_history = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    posture = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    syllabus = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    scdb_id = fields.KeywordField(attr="scdb_id")
    sibling_ids = fields.ListField(
        fields.IntegerField(multi=True),
    )
    panel_ids = fields.ListField(
        fields.IntegerField(multi=True),
    )
    neutralCite = fields.TextField(
        analyzer="text_en_splitting_cl",
        search_analyzer="search_analyzer",
    )
    lexisCite = fields.TextField(
        analyzer="text_en_splitting_cl",
        search_analyzer="search_analyzer",
    )
    citeCount = fields.IntegerField(attr="citation_count")
    cluster_child = JoinField(relations={"opinion_cluster": ["opinion"]})
    timestamp = fields.DateField()
    date_created = fields.DateField(attr="date_created")

    class Django:
        model = OpinionCluster
        ignore_signals = True

    def prepare_absolute_url(self, instance):
        return instance.get_absolute_url()

    def prepare_docketNumber(self, instance):
        return instance.docket.docket_number

    def prepare_caseName(self, instance):
        return best_case_name(instance)

    def prepare_caseNameFull(self, instance):
        return instance.case_name_full

    def prepare_court_id(self, instance):
        return instance.docket.court.pk

    def prepare_court(self, instance):
        return instance.docket.court.full_name

    def prepare_court_citation_string(self, instance):
        return instance.docket.court.citation_string

    def prepare_judge(self, instance):
        return instance.judges

    def prepare_panel_names(self, instance):
        return [judge.name_full for judge in instance.panel.all()]

    def prepare_citation(self, instance):
        return [str(cite) for cite in instance.citations.all()]

    def prepare_attorney(self, instance):
        return instance.attorneys

    def prepare_suitNature(self, instance):
        return instance.nature_of_suit

    def prepare_status(self, instance):
        return instance.precedential_status

    def prepare_procedural_history(self, instance):
        return instance.procedural_history

    def prepare_posture(self, instance):
        return instance.posture

    def prepare_syllabus(self, instance):
        return instance.syllabus

    def prepare_sibling_ids(self, instance):
        return list(instance.sub_opinions.all().values_list("id", flat=True))

    def prepare_panel_ids(self, instance):
        return list(instance.panel.all().values_list("id", flat=True))

    def prepare_dateFiled(self, instance):
        if instance.date_filed is None:
            return

        if isinstance(instance.date_filed, str):
            datetime_object = datetime.strptime(
                instance.date_filed, "%Y-%m-%d"
            )
            return datetime_object

        return instance.date_filed

    def prepare_dateArgued(self, instance):
        if instance.docket.date_argued is None:
            return

        if isinstance(instance.docket.date_argued, str):
            datetime_object = datetime.strptime(
                instance.docket.date_argued, "%Y-%m-%d"
            )
            return datetime_object

        return instance.docket.date_argued

    def prepare_dateReargued(self, instance):
        if instance.docket.date_reargued is None:
            return

        if isinstance(instance.docket.date_reargued, str):
            datetime_object = datetime.strptime(
                instance.docket.date_reargued, "%Y-%m-%d"
            )
            return datetime_object

        return instance.docket.date_reargued

    def prepare_dateReargumentDenied(self, instance):
        if instance.docket.date_reargument_denied is None:
            return

        if isinstance(instance.docket.date_reargument_denied, str):
            datetime_object = datetime.strptime(
                instance.docket.date_reargument_denied, "%Y-%m-%d"
            )
            return datetime_object

        return instance.docket.date_reargument_denied

    def prepare_neutralCite(self, instance):
        neutral_citations = instance.citations.filter(type=Citation.NEUTRAL)
        if neutral_citations.count():
            return str(neutral_citations[0])
        return ""

    def prepare_lexisCite(self, instance):
        lexis_citations = instance.citations.filter(type=Citation.LEXIS)
        if lexis_citations.count():
            return str(lexis_citations[0])
        return ""

    def prepare_timestamp(self, instance):
        return datetime.utcnow()


@opinion_index.document
class OpinionDocument(CSVSerializableDocumentMixin, OpinionBaseDocument):
    id = fields.IntegerField(
        attr="pk",
        fields={
            "raw": fields.KeywordField(attr="pk"),
        },
    )
    author_id = fields.IntegerField()
    type = fields.KeywordField()
    per_curiam = fields.BooleanField(attr="per_curiam")
    type_text = fields.TextField(index=False)
    download_url = fields.KeywordField(attr="download_url", index=False)
    local_path = fields.KeywordField(index=False)
    text = fields.TextField(
        analyzer="text_en_splitting_cl",
        term_vector="with_positions_offsets",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
                term_vector="with_positions_offsets",
            ),
        },
        search_analyzer="search_analyzer",
    )
    sha1 = fields.TextField(attr="sha1", index=False)
    cites = fields.ListField(
        fields.IntegerField(multi=True),
    )
    joined_by_ids = fields.ListField(
        fields.IntegerField(multi=True),
    )
    ordering_key = fields.IntegerField(attr="ordering_key")

    class Django:
        model = Opinion
        ignore_signals = True

    @classmethod
    def get_csv_headers(cls) -> list[str]:
        return [
            "author_id",
            "type",
            "per_curiam",
            "type_text",
            "download_url",
            "local_path",
            "text",
            "sha1",
            "cites",
            "joined_by_ids",
            "date_created",
        ]

    @classmethod
    def get_csv_transformations(cls) -> dict[str, Callable[..., Any]]:
        transformations = {
            key: lambda x: render_string_or_list(x)
            for key in SEARCH_OPINION_CHILD_HL_FIELDS.keys()
        }
        # Add a transformation for relative URLs.
        transformations["local_path"] = lambda x: (
            f"https://storage.courtlistener.com/{x}" if x else ""
        )
        return transformations

    def prepare_absolute_url(self, instance):
        return instance.cluster.get_absolute_url()

    def prepare_author_id(self, instance):
        return getattr(instance.author, "pk", None)

    def prepare_type_text(self, instance):
        return instance.get_type_display()

    def prepare_type(self, instance):
        return o_type_index_map.get(instance.type)

    def prepare_local_path(self, instance):
        if instance.local_path:
            return instance.local_path.name

    def prepare_cites(self, instance):
        return list(
            instance.cited_opinions.all().values_list(
                "cited_opinion_id", flat=True
            )
        )

    def prepare_joined_by_ids(self, instance):
        return list(instance.joined_by.all().values_list("id", flat=True))

    def prepare_text(self, instance):
        if instance.html_columbia:
            return html_decode(
                strip_tags(instance.html_columbia.translate(null_map))
            )
        elif instance.html_lawbox:
            return html_decode(
                strip_tags(instance.html_lawbox.translate(null_map))
            )
        elif instance.xml_harvard:
            return html_decode(
                strip_tags(instance.xml_harvard.translate(null_map))
            )
        elif instance.html_anon_2020:
            return html_decode(
                strip_tags(instance.html_anon_2020.translate(null_map))
            )
        elif instance.html:
            return html_decode(strip_tags(instance.html.translate(null_map)))
        else:
            return escape(instance.plain_text.translate(null_map))

    def prepare_cluster_id(self, instance):
        return instance.cluster.pk

    def prepare_docket_id(self, instance):
        return instance.cluster.docket.pk

    def prepare_scdb_id(self, instance):
        return instance.cluster.scdb_id

    def prepare_sibling_ids(self, instance):
        return list(
            instance.cluster.sub_opinions.all().values_list("id", flat=True)
        )

    def prepare_panel_ids(self, instance):
        return list(instance.cluster.panel.all().values_list("id", flat=True))

    def prepare_dateFiled(self, instance):
        if instance.cluster.date_filed is None:
            return

        if isinstance(instance.cluster.date_filed, str):
            datetime_object = datetime.strptime(
                instance.cluster.date_filed, "%Y-%m-%d"
            )
            return datetime_object

        return instance.cluster.date_filed

    def prepare_dateArgued(self, instance):
        if instance.cluster.docket.date_argued is None:
            return

        if isinstance(instance.cluster.docket.date_argued, str):
            datetime_object = datetime.strptime(
                instance.cluster.docket.date_argued, "%Y-%m-%d"
            )
            return datetime_object

        return instance.cluster.docket.date_argued

    def prepare_dateReargued(self, instance):
        if instance.cluster.docket.date_reargued is None:
            return

        if isinstance(instance.cluster.docket.date_reargued, str):
            datetime_object = datetime.strptime(
                instance.cluster.docket.date_reargued, "%Y-%m-%d"
            )
            return datetime_object

        return instance.cluster.docket.date_reargued

    def prepare_dateReargumentDenied(self, instance):
        if instance.cluster.docket.date_reargument_denied is None:
            return

        if isinstance(instance.cluster.docket.date_reargument_denied, str):
            datetime_object = datetime.strptime(
                instance.cluster.docket.date_reargument_denied, "%Y-%m-%d"
            )
            return datetime_object

        return instance.cluster.docket.date_reargument_denied

    def prepare_neutralCite(self, instance):
        neutral_citations = instance.cluster.citations.filter(
            type=Citation.NEUTRAL
        )
        if neutral_citations.count():
            return str(neutral_citations[0])
        return ""

    def prepare_lexisCite(self, instance):
        lexis_citations = instance.cluster.citations.filter(
            type=Citation.LEXIS
        )
        if lexis_citations.count():
            return str(lexis_citations[0])
        return ""

    def prepare_citeCount(self, instance):
        return instance.cluster.citation_count

    def prepare_docketNumber(self, instance):
        return instance.cluster.docket.docket_number

    def prepare_caseName(self, instance):
        return best_case_name(instance.cluster)

    def prepare_caseNameFull(self, instance):
        return instance.cluster.case_name_full

    def prepare_court_id(self, instance):
        return instance.cluster.docket.court.pk

    def prepare_court(self, instance):
        return instance.cluster.docket.court.full_name

    def prepare_court_citation_string(self, instance):
        return instance.cluster.docket.court.citation_string

    def prepare_judge(self, instance):
        return instance.cluster.judges

    def prepare_panel_names(self, instance):
        return [judge.name_full for judge in instance.cluster.panel.all()]

    def prepare_citation(self, instance):
        return [str(cite) for cite in instance.cluster.citations.all()]

    def prepare_attorney(self, instance):
        return instance.cluster.attorneys

    def prepare_suitNature(self, instance):
        return instance.cluster.nature_of_suit

    def prepare_status(self, instance):
        return instance.cluster.precedential_status

    def prepare_procedural_history(self, instance):
        return instance.cluster.procedural_history

    def prepare_posture(self, instance):
        return instance.cluster.posture

    def prepare_syllabus(self, instance):
        return instance.cluster.syllabus

    def prepare_cluster_child(self, instance):
        parent_id = getattr(instance.cluster, "pk", None)
        return {"name": "opinion", "parent": parent_id}


@opinion_index.document
class OpinionClusterDocument(
    CSVSerializableDocumentMixin, OpinionBaseDocument
):
    court_exact = fields.KeywordField(attr="docket.court_id")
    non_participating_judge_ids = fields.ListField(
        fields.IntegerField(multi=True),
    )
    source = fields.TextField(
        attr="source",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                analyzer="english_exact",
                search_analyzer="search_analyzer_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )

    @classmethod
    def get_csv_headers(cls) -> list[str]:
        return [
            "id",
            "cluster_id",
            "court_id",
            "court",
            "court_citation_string",
            "docket_id",
            "docket_number",
            "case_name",
            "case_name_full",
            "source",
            "absolute_url",
            "date_filed",
            "date_argued",
            "date_reargued",
            "date_reargument_denied",
            "judge",
            "non_participating_judge_ids",
            "panel_names",
            "attorney",
            "suit_nature",
            "citation",
            "status",
            "procedural_history",
            "posture",
            "syllabus",
            "scdb_id",
            "sibling_ids",
            "panel_ids",
            "neutral_cite",
            "lexis_cite",
            "cite_count",
        ]

    @classmethod
    def get_csv_transformations(cls) -> dict[str, Callable[..., Any]]:
        list_fields = ["panel_names", "citation"]
        hl_fields = list(SEARCH_OPINION_HL_FIELDS.keys())
        transformations = {
            key: lambda x: render_string_or_list(x)
            for key in (hl_fields + list_fields)
        }

        # Add a transformation for relative URL
        transformations["absolute_url"] = (
            lambda x: f"https://www.courtlistener.com{x}"
        )

        # Add a transformation to compute Human-readable values
        transformations["source"] = lambda x: dict(SOURCES.NAMES).get(x, x)
        transformations["status"] = lambda x: dict(
            PRECEDENTIAL_STATUS.NAMES
        ).get(x, x)
        return transformations

    def prepare_non_participating_judge_ids(self, instance):
        return list(
            instance.non_participating_judges.all().values_list(
                "id", flat=True
            )
        )

    def prepare_cluster_child(self, instance):
        return "opinion_cluster"


class RECAPSweepDocument(DocketDocument, ESRECAPDocument):
    class Index:
        name = "recap_sweep"
        settings = {
            "number_of_shards": settings.ELASTICSEARCH_RECAP_NUMBER_OF_SHARDS,
            "number_of_replicas": settings.ELASTICSEARCH_RECAP_NUMBER_OF_REPLICAS,
            "analysis": settings.ELASTICSEARCH_DSL["analysis"],
        }


class ESRECAPSweepDocument(ESRECAPBaseDocument):

    class Index:
        name = "recap_document_sweep"
        settings = {
            "number_of_shards": settings.ELASTICSEARCH_RECAP_NUMBER_OF_SHARDS,
            "number_of_replicas": settings.ELASTICSEARCH_RECAP_NUMBER_OF_REPLICAS,
            "analysis": settings.ELASTICSEARCH_DSL["analysis"],
        }


class ESRECAPDocumentPlain(ESRECAPDocument):
    docket_absolute_url = fields.KeywordField(index=False)

    # Parties
    party_id = fields.ListField(fields.IntegerField(multi=True))
    party = fields.ListField(
        fields.TextField(
            analyzer="text_en_splitting_cl",
            fields={
                "exact": fields.TextField(
                    analyzer="english_exact",
                    search_analyzer="search_analyzer_exact",
                ),
            },
            search_analyzer="search_analyzer",
            multi=True,
        )
    )
    attorney_id = fields.ListField(fields.IntegerField(multi=True))
    attorney = fields.ListField(
        fields.TextField(
            analyzer="text_en_splitting_cl",
            fields={
                "exact": fields.TextField(
                    analyzer="english_exact",
                    search_analyzer="search_analyzer_exact",
                ),
            },
            search_analyzer="search_analyzer",
            multi=True,
        )
    )
    firm_id = fields.ListField(fields.IntegerField(multi=True))
    firm = fields.ListField(
        fields.TextField(
            analyzer="text_en_splitting_cl",
            fields={
                "exact": fields.TextField(
                    analyzer="english_exact",
                    search_analyzer="search_analyzer_exact",
                ),
            },
            search_analyzer="search_analyzer",
            multi=True,
        )
    )

    def prepare_parties(self, instance):
        out = {
            "party_id": set(),
            "party": set(),
            "attorney_id": set(),
            "attorney": set(),
            "firm_id": set(),
            "firm": set(),
        }

        # Extract only required parties values.
        party_values = instance.docket_entry.docket.parties.values_list(
            "pk", "name"
        )
        for pk, name in party_values.iterator():
            out["party_id"].add(pk)
            out["party"].add(name)

        # Extract only required attorney values.
        atty_values = (
            Attorney.objects.filter(roles__docket=instance.docket_entry.docket)
            .distinct()
            .values_list("pk", "name")
        )
        for pk, name in atty_values.iterator():
            out["attorney_id"].add(pk)
            out["attorney"].add(name)

        # Extract only required firm values.
        firms_values = (
            AttorneyOrganization.objects.filter(
                attorney_organization_associations__docket=instance.docket_entry.docket
            )
            .distinct()
            .values_list("pk", "name")
        )
        for pk, name in firms_values.iterator():
            out["firm_id"].add(pk)
            out["firm"].add(name)

        return out

    def prepare_docket_absolute_url(self, instance):
        return instance.docket_entry.docket.get_absolute_url()

    def prepare(self, instance):
        data = super().prepare(instance)
        parties_prepared = self.prepare_parties(instance)
        data["party_id"] = list(parties_prepared["party_id"])
        data["party"] = list(parties_prepared["party"])
        data["attorney_id"] = list(parties_prepared["attorney_id"])
        data["attorney"] = list(parties_prepared["attorney"])
        data["firm_id"] = list(parties_prepared["firm_id"])
        data["firm"] = list(parties_prepared["firm"])
        return data


class RECAPPercolator(DocketDocument, ESRECAPDocument):
    rate = fields.KeywordField(attr="rate")
    percolator_query = PercolatorField()

    class Index:
        name = "recap_percolator"
        settings = {
            "number_of_shards": settings.ELASTICSEARCH_RECAP_ALERTS_NUMBER_OF_SHARDS,
            "number_of_replicas": settings.ELASTICSEARCH_RECAP_ALERTS_NUMBER_OF_REPLICAS,
            "analysis": settings.ELASTICSEARCH_DSL["analysis"],
        }

    def prepare_timestamp(self, instance):
        return datetime.utcnow()

    def prepare_percolator_query(self, instance):
        from cl.alerts.utils import build_plain_percolator_query

        qd = QueryDict(instance.query.encode(), mutable=True)
        # For RECAP percolator queries, we use build_plain_percolator_query to
        # build the query. It does not add a custom function_score, so there is
        # no need to remove the order_by sorting key as it is ignored.
        search_form = SearchForm(qd)
        if not search_form.is_valid():
            logger.warning(
                f"The query {qd} associated with Alert ID {instance.pk} is "
                "invalid and was not indexed."
            )
            return None

        cd = search_form.cleaned_data
        query = build_plain_percolator_query(cd)
        return query.to_dict()
