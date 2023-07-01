from datetime import datetime

from django.conf import settings
from django.template import loader
from django_elasticsearch_dsl import Document, Index, fields
from elasticsearch_dsl import Join, Percolator

from cl.alerts.models import Alert
from cl.audio.models import Audio
from cl.lib.search_index_utils import null_map
from cl.lib.utils import deepgetattr
from cl.people_db.models import Education, Person, Position
from cl.search.models import Citation, ParentheticalGroup

# Define parenthetical elasticsearch index
parenthetical_group_index = Index("parenthetical_group")
parenthetical_group_index.settings(
    number_of_shards=settings.ELASTICSEARCH_NUMBER_OF_SHARDS,
    number_of_replicas=settings.ELASTICSEARCH_NUMBER_OF_REPLICAS,
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
    dateArgued = fields.DateField(attr="opinion.cluster.docket.date_argued")
    dateFiled = fields.DateField(attr="opinion.cluster.date_filed")
    dateReargued = fields.DateField(
        attr="opinion.cluster.docket.date_reargued"
    )
    dateReargumentDenied = fields.DateField(
        attr="opinion.cluster.docket.date_reargument_denied"
    )
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
    joined_by_ids = fields.ListField(
        fields.IntegerField(),
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
    scdb_id = fields.KeywordField(attr="opinion.cluster.scdb_id")
    status = fields.KeywordField()
    suitNature = fields.TextField(
        attr="opinion.cluster.nature_of_suit",
    )

    class Django:
        model = ParentheticalGroup
        fields = ["score"]

    def prepare_citation(self, instance):
        return [str(cite) for cite in instance.opinion.cluster.citations.all()]

    def prepare_cites(self, instance):
        return [o.pk for o in instance.opinion.opinions_cited.all()]

    def prepare_joined_by_ids(self, instance):
        return [judge.pk for judge in instance.opinion.joined_by.all()]

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
    absolute_url = fields.KeywordField(attr="get_absolute_url")
    caseName = fields.TextField(
        attr="case_name",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="case_name", analyzer="english_exact"
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
    court_exact = fields.KeywordField(attr="docket.court.pk")
    court_id = fields.KeywordField(attr="docket.court.pk")
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
    docket_slug = fields.KeywordField(attr="docket.slug")
    duration = fields.IntegerField(attr="duration")
    download_url = fields.KeywordField(attr="download_url")
    file_size_mp3 = fields.IntegerField()
    id = fields.IntegerField(attr="pk")
    judge = fields.TextField(
        attr="judges",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(attr="judges", analyzer="english_exact"),
        },
        search_analyzer="search_analyzer",
    )
    local_path = fields.KeywordField()
    pacer_case_id = fields.KeywordField(attr="docket.pacer_case_id")
    panel_ids = fields.ListField(
        fields.IntegerField(),
    )
    sha1 = fields.KeywordField(attr="sha1")
    source = fields.KeywordField(attr="source")
    text = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(analyzer="english_exact"),
        },
        search_analyzer="search_analyzer",
    )
    timestamp = fields.DateField()


# Define oral arguments elasticsearch index
oral_arguments_index = Index("oral_arguments")
oral_arguments_index.settings(
    number_of_shards=settings.ELASTICSEARCH_NUMBER_OF_SHARDS,
    number_of_replicas=settings.ELASTICSEARCH_NUMBER_OF_REPLICAS,
    analysis=settings.ELASTICSEARCH_DSL["analysis"],
)


@oral_arguments_index.document
class AudioDocument(AudioDocumentBase):
    class Django:
        model = Audio
        ignore_signals = True

    def prepare_panel_ids(self, instance):
        return [judge.pk for judge in instance.panel.all()]

    def prepare_file_size_mp3(self, instance):
        if instance.local_path_mp3:
            return deepgetattr(instance, "local_path_mp3.size", None)

    def prepare_local_path(self, instance):
        if instance.local_path_mp3:
            return deepgetattr(instance, "local_path_mp3.name", None)

    def prepare_text(self, instance):
        text_template = loader.get_template("indexes/audio_text.txt")
        return text_template.render({"item": instance}).translate(null_map)

    def prepare_timestamp(self, instance):
        return datetime.utcnow()


# Define oral arguments elasticsearch index
oral_arguments_percolator_index = Index("oral_arguments_percolator")
oral_arguments_percolator_index.settings(
    number_of_shards=settings.ELASTICSEARCH_NUMBER_OF_SHARDS,
    number_of_replicas=settings.ELASTICSEARCH_NUMBER_OF_REPLICAS,
    analysis=settings.ELASTICSEARCH_DSL["analysis"],
)


@oral_arguments_percolator_index.document
class AudioPercolator(AudioDocumentBase):
    rate = fields.KeywordField(attr="rate")
    percolator_query = Percolator()

    class Django:
        model = Alert
        ignore_signals = True


# Define people elasticsearch index
people_db_index = Index("people_db_index")
people_db_index.settings(
    number_of_shards=settings.ELASTICSEARCH_NUMBER_OF_SHARDS,
    number_of_replicas=settings.ELASTICSEARCH_NUMBER_OF_REPLICAS,
    analysis=settings.ELASTICSEARCH_DSL["analysis"],
)


class PEOPLE_DOCS_TYPE_ID:
    """Returns an ID for its use in people_db_index child documents"""

    def __init__(self, instance_id: int):
        self.instance_id = instance_id

    @property
    def POSITION(self) -> str:
        return f"po_{self.instance_id}"

    @property
    def EDUCATION(self) -> str:
        return f"ed_{self.instance_id}"


@people_db_index.document
class PersonBaseDocument(Document):
    person_child = Join(relations={"person": ["position", "education"]})
    timestamp = fields.DateField()

    class Django:
        model = Person
        ignore_signals = True

    def prepare_timestamp(self, instance):
        return datetime.utcnow()


class EducationDocument(PersonBaseDocument):
    school = fields.TextField(
        attr="school.name",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="school.name", analyzer="english_exact"
            ),
        },
        search_analyzer="search_analyzer",
    )
    degree_level = fields.KeywordField(attr="degree_level")
    degree_detail = fields.TextField(
        attr="degree_detail",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="degree_detail", analyzer="english_exact"
            ),
        },
        search_analyzer="search_analyzer",
    )
    degree_year = fields.IntegerField(attr="degree_year")

    class Django:
        model = Education
        ignore_signals = True


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
    court_exact = fields.KeywordField(attr="court.pk")
    position_type = fields.KeywordField()
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
    judicial_committee_action = fields.KeywordField()
    nomination_process = fields.KeywordField()
    selection_method = fields.KeywordField()
    selection_method_id = fields.KeywordField(attr="how_selected")
    termination_reason = fields.KeywordField()
    text = fields.TextField(
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(analyzer="english_exact"),
        },
        search_analyzer="search_analyzer",
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

    def prepare_text(self, instance):
        text_template = loader.get_template("indexes/person_text.txt")
        return text_template.render({"item": instance}).translate(null_map)


class PersonDocument(PersonBaseDocument):
    id = fields.IntegerField(attr="pk")
    fjc_id = fields.IntegerField(attr="fjc_id")
    alias_ids = fields.ListField(
        fields.KeywordField(),
    )
    races = fields.ListField(
        fields.KeywordField(),
    )
    gender = fields.KeywordField()
    religion = fields.KeywordField(attr="religion")
    name = fields.TextField(
        attr="name_full",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="name_full", analyzer="english_exact"
            ),
        },
        search_analyzer="search_analyzer",
    )
    name_reverse = fields.TextField(
        attr="name_reverse",
        analyzer="text_en_splitting_cl",
        fields={
            "exact": fields.TextField(
                attr="name_reverse", analyzer="english_exact"
            ),
        },
        search_analyzer="search_analyzer",
    )

    date_granularity_dob = fields.KeywordField(attr="date_granularity_dob")
    date_granularity_dod = fields.KeywordField(attr="date_granularity_dod")
    dob_city = fields.KeywordField(attr="dob_city")
    dob_state = fields.KeywordField()
    dob_state_id = fields.KeywordField(attr="dob_state")
    absolute_url = fields.KeywordField(attr="get_absolute_url")
    dob = fields.DateField(attr="date_dob")
    dod = fields.DateField(attr="date_dod")
    political_affiliation = fields.ListField(
        fields.KeywordField(),
    )
    political_affiliation_id = fields.ListField(
        fields.KeywordField(),
    )
    aba_rating = fields.ListField(
        fields.KeywordField(),
    )

    def save(self, **kwargs):
        self.person_child = "person"
        return super().save(**kwargs)

    def prepare_races(self, instance):
        return [r.get_race_display() for r in instance.race.all()]

    def prepare_alias_ids(self, instance):
        return [alias.pk for alias in instance.aliases.all()]

    def prepare_gender(self, instance):
        return instance.get_gender_display()

    def prepare_dob_state(self, instance):
        return instance.get_dob_state_display()

    def prepare_political_affiliation(self, instance):
        return [
            pa.get_political_party_display()
            for pa in instance.political_affiliations.all()
            if pa
        ]

    def prepare_political_affiliation_id(self, instance):
        return [
            pa.political_party
            for pa in instance.political_affiliations.all()
            if pa
        ]

    def prepare_aba_rating(self, instance):
        return [
            r.get_rating_display() for r in instance.aba_ratings.all() if r
        ]
