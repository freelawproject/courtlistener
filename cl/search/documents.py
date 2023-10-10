from datetime import datetime

from django.http import QueryDict
from django.template import loader
from django_elasticsearch_dsl import Document, fields

from cl.alerts.models import Alert
from cl.audio.models import Audio
from cl.custom_filters.templatetags.text_filters import best_case_name
from cl.lib.command_utils import logger
from cl.lib.elasticsearch_utils import build_es_base_query
from cl.lib.fields import JoinField, PercolatorField
from cl.lib.search_index_utils import null_map
from cl.lib.utils import deepgetattr
from cl.people_db.models import Person, Position
from cl.search.es_indices import (
    oral_arguments_index,
    oral_arguments_percolator_index,
    parenthetical_group_index,
    people_db_index,
    recap_index,
)
from cl.search.forms import SearchForm
from cl.search.models import (
    Citation,
    Docket,
    ParentheticalGroup,
    RECAPDocument,
)


@parenthetical_group_index.document
class ParentheticalGroupDocument(Document):
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
    docketNumber = fields.KeywordField(
        attr="opinion.cluster.docket.docket_number"
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

    def prepare_citation(self, instance):
        return [str(cite) for cite in instance.opinion.cluster.citations.all()]

    def prepare_cites(self, instance):
        return [o.pk for o in instance.opinion.opinions_cited.all()]

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
        return [judge.pk for judge in instance.opinion.cluster.panel.all()]

    def prepare_status(self, instance):
        return instance.opinion.cluster.get_precedential_status_display()


class AudioDocumentBase(Document):
    absolute_url = fields.KeywordField(attr="get_absolute_url", index=False)
    caseName = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(analyzer="english_exact"),
        },
        search_analyzer="search_analyzer",
    )
    case_name_full = fields.TextField(
        attr="case_name_full",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="case_name_full", analyzer="english_exact"
            ),
        },
        search_analyzer="search_analyzer",
    )
    court = fields.TextField(
        attr="docket.court.full_name",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="docket.court.full_name", analyzer="english_exact"
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
            "exact": fields.TextField(analyzer="english_exact"),
        },
        search_analyzer="search_analyzer",
    )
    dateReargued_text = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(analyzer="english_exact"),
        },
        search_analyzer="search_analyzer",
    )
    dateReargumentDenied_text = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(analyzer="english_exact"),
        },
        search_analyzer="search_analyzer",
    )
    docketNumber = fields.TextField(
        attr="docket.docket_number",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="docket.docket_number", analyzer="english_exact"
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
        attr="judges",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(attr="judges", analyzer="english_exact"),
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
        fields={
            "exact": fields.TextField(analyzer="english_exact"),
        },
        search_analyzer="search_analyzer",
    )
    timestamp = fields.DateField()


@oral_arguments_index.document
class AudioDocument(AudioDocumentBase):
    class Django:
        model = Audio
        ignore_signals = True

    def prepare_caseName(self, instance):
        return best_case_name(instance)

    def prepare_panel_ids(self, instance):
        return [judge.pk for judge in instance.panel.all()]

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

    def prepare_text(self, instance):
        if instance.stt_status == Audio.STT_COMPLETE:
            return instance.transcript

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
    date_created = fields.DateField(attr="date_created")
    percolator_query = PercolatorField()

    class Django:
        model = Alert
        ignore_signals = True

    def prepare_timestamp(self, instance):
        return datetime.utcnow()

    def prepare_percolator_query(self, instance):
        qd = QueryDict(instance.query.encode(), mutable=True)
        search_form = SearchForm(qd)
        if not search_form.is_valid():
            logger.warning(
                f"The query {qd} associated with Alert ID {instance.pk} is "
                f"invalid and was not indexed."
            )
            return None

        cd = search_form.cleaned_data
        search_query = AudioDocument.search()
        query, _ = build_es_base_query(search_query, cd)
        return query.to_dict()["query"]


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
        fields={
            "exact": fields.TextField(analyzer="english_exact"),
        },
        search_analyzer="search_analyzer",
    )
    gender = fields.TextField()
    religion = fields.TextField()
    alias = fields.ListField(
        fields.TextField(
            analyzer="text_en_splitting_cl",
            fields={
                "exact": fields.TextField(analyzer="english_exact"),
            },
            search_analyzer="search_analyzer",
            multi=True,
        )
    )
    dob = fields.DateField(attr="date_dob")
    dod = fields.DateField(attr="date_dod")
    dob_city = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="person.dob_city", analyzer="english_exact"
            ),
        },
        search_analyzer="search_analyzer",
    )
    dob_state = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(analyzer="english_exact"),
        },
        search_analyzer="search_analyzer",
    )
    dob_state_id = fields.KeywordField(attr="dob_state")
    political_affiliation = fields.ListField(
        fields.TextField(
            analyzer="text_en_splitting_cl",
            fields={
                "exact": fields.TextField(analyzer="english_exact"),
            },
            search_analyzer="search_analyzer",
            multi=True,
        )
    )
    aba_rating = fields.ListField(
        fields.TextField(
            analyzer="text_en_splitting_cl",
            fields={
                "exact": fields.TextField(analyzer="english_exact"),
            },
            search_analyzer="search_analyzer",
            multi=True,
        )
    )
    school = fields.ListField(
        fields.TextField(
            analyzer="text_en_splitting_cl",
            fields={
                "exact": fields.TextField(analyzer="english_exact"),
            },
            search_analyzer="search_analyzer",
            multi=True,
        )
    )
    person_child = JoinField(relations={"person": ["position"]})
    timestamp = fields.DateField()

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
        ] or None

    def prepare_dob_state(self, instance):
        return instance.get_dob_state_display()

    def prepare_alias(self, instance):
        return [r.name_full for r in instance.aliases.all()] or None

    def prepare_aba_rating(self, instance):
        return [
            r.get_rating_display() for r in instance.aba_ratings.all() if r
        ] or None

    def prepare_school(self, instance):
        return [e.school.name for e in instance.educations.all()] or None

    def prepare_races(self, instance):
        return [r.get_race_display() for r in instance.race.all()] or None

    def prepare_alias_ids(self, instance):
        return [alias.pk for alias in instance.aliases.all()] or None

    def prepare_political_affiliation_id(self, instance):
        return [
            pa.political_party
            for pa in instance.political_affiliations.all()
            if pa
        ] or None


@people_db_index.document
class PositionDocument(PersonBaseDocument):
    court = fields.TextField(
        attr="court.short_name",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="court.short_name", analyzer="english_exact"
            ),
        },
        search_analyzer="search_analyzer",
    )
    court_full_name = fields.TextField(
        attr="court.full_name",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="court.full_name", analyzer="english_exact"
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
            ),
        },
        search_analyzer="search_analyzer",
    )
    supervisor = fields.TextField(
        attr="supervisor.name_full_reverse",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="supervisor.name_full_reverse", analyzer="english_exact"
            ),
        },
        search_analyzer="search_analyzer",
    )
    predecessor = fields.TextField(
        attr="predecessor.name_full_reverse",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="predecessor.name_full_reverse", analyzer="english_exact"
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
        ] or None

    def prepare_alias(self, instance):
        return [r.name_full for r in instance.person.aliases.all()] or None

    def prepare_aba_rating(self, instance):
        return [
            r.get_rating_display()
            for r in instance.person.aba_ratings.all()
            if r
        ] or None

    def prepare_school(self, instance):
        return [
            e.school.name for e in instance.person.educations.all()
        ] or None

    def prepare_races(self, instance):
        return [
            r.get_race_display() for r in instance.person.race.all()
        ] or None

    def prepare_alias_ids(self, instance):
        return [alias.pk for alias in instance.person.aliases.all()] or None

    def prepare_political_affiliation_id(self, instance):
        return [
            pa.political_party
            for pa in instance.person.political_affiliations.all()
            if pa
        ] or None


@people_db_index.document
class PersonDocument(PersonBaseDocument):
    name_reverse = fields.KeywordField(
        attr="name_full_reverse",
    )
    date_granularity_dob = fields.KeywordField(attr="date_granularity_dob")
    date_granularity_dod = fields.KeywordField(attr="date_granularity_dod")
    absolute_url = fields.KeywordField(attr="get_absolute_url")

    def prepare_person_child(self, instance):
        return "person"


# RECAP
class DocketBaseDocument(Document):
    docket_child = JoinField(relations={"docket": ["recap_document"]})
    timestamp = fields.DateField()

    # Docket Fields
    docket_id = fields.IntegerField(attr="pk")
    caseName = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(analyzer="english_exact"),
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
            ),
        },
        search_analyzer="search_analyzer",
    )
    docketNumber = fields.TextField(
        attr="docket_number",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="docket_number",
                analyzer="english_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    suitNature = fields.TextField(
        attr="nature_of_suit",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="nature_of_suit",
                analyzer="english_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    cause = fields.TextField(
        attr="cause",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(attr="cause", analyzer="english_exact"),
        },
        search_analyzer="search_analyzer",
    )
    juryDemand = fields.TextField(
        attr="jury_demand",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="jury_demand",
                analyzer="english_exact",
            ),
        },
        search_analyzer="search_analyzer",
    )
    jurisdictionType = fields.TextField(
        attr="jurisdiction_type",
    )
    dateArgued = fields.DateField(attr="date_argued")
    dateFiled = fields.DateField(attr="date_filed")
    dateTerminated = fields.DateField(attr="date_terminated")
    assignedTo = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(analyzer="english_exact"),
        },
        search_analyzer="search_analyzer",
    )
    assigned_to_id = fields.KeywordField(attr="assigned_to.pk")
    referredTo = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(analyzer="english_exact"),
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
            ),
        },
        search_analyzer="search_analyzer",
    )

    class Django:
        model = Docket
        ignore_signals = True

    def prepare_timestamp(self, instance):
        return datetime.utcnow()


@recap_index.document
class ESRECAPDocument(DocketBaseDocument):
    id = fields.IntegerField(attr="pk")
    docket_entry_id = fields.IntegerField(attr="docket_entry.pk")
    description = fields.TextField(
        attr="docket_entry.description",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="docket_entry.description", analyzer="english_exact"
            ),
        },
        search_analyzer="search_analyzer",
    )
    entry_number = fields.IntegerField(attr="docket_entry.entry_number")
    entry_date_filed = fields.DateField(attr="docket_entry.date_filed")
    short_description = fields.TextField(
        attr="description",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="description", analyzer="english_exact"
            ),
        },
        search_analyzer="search_analyzer",
    )
    document_type = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(analyzer="english_exact"),
        },
        search_analyzer="search_analyzer",
    )
    document_number = fields.TextField(attr="document_number")
    pacer_doc_id = fields.KeywordField(attr="pacer_doc_id")
    plain_text = fields.TextField(
        attr="plain_text",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="plain_text", analyzer="english_exact"
            ),
        },
        search_analyzer="search_analyzer",
    )
    attachment_number = fields.IntegerField(attr="attachment_number")
    is_available = fields.BooleanField(attr="is_available")
    page_count = fields.IntegerField(attr="page_count")
    filepath_local = fields.KeywordField(index=False)
    absolute_url = fields.KeywordField(index=False)

    class Django:
        model = RECAPDocument
        ignore_signals = True

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


@recap_index.document
class DocketDocument(DocketBaseDocument):
    docket_slug = fields.KeywordField(attr="slug", index=False)
    docket_absolute_url = fields.KeywordField(index=False)
    court_exact = fields.KeywordField(attr="court.pk", index=False)

    # Parties
    party_id = fields.ListField(fields.IntegerField(multi=True))
    party = fields.ListField(
        fields.TextField(
            analyzer="text_en_splitting_cl",
            fields={
                "exact": fields.TextField(analyzer="english_exact"),
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
                "exact": fields.TextField(analyzer="english_exact"),
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
                "exact": fields.TextField(analyzer="english_exact"),
            },
            search_analyzer="search_analyzer",
            multi=True,
        )
    )

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
        if hasattr(instance, "bankruptcy_information"):
            return instance.bankruptcy_information.chapter

    def prepare_trustee_str(self, instance):
        if hasattr(instance, "bankruptcy_information"):
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
        for p in instance.prefetched_parties:
            out["party_id"].add(p.pk)
            out["party"].add(p.name)
            for a in p.attys_in_docket:
                out["attorney_id"].add(a.pk)
                out["attorney"].add(a.name)
                for f in a.firms_in_docket:
                    out["firm_id"].add(f.pk)
                    out["firm"].add(f.name)
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
