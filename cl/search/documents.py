from datetime import datetime

from django.conf import settings
from django.http import QueryDict
from django.template import loader
from django_elasticsearch_dsl import Document, Index, fields
from elasticsearch_dsl import Percolator
from six import iteritems

from cl.alerts.models import Alert
from cl.audio.models import Audio
from cl.lib.elasticsearch_utils import build_es_main_query
from cl.lib.search_index_utils import null_map
from cl.lib.utils import deepgetattr
from cl.search.forms import SearchForm
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
            "exact": fields.TextField(attr="judges", analyzer="english_exact"),
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

    def _prepare_action(self, object_instance, action):
        data = self.prepare(object_instance) if action != "delete" else None
        # Store the data for this instance
        self._instance_data = data
        return {
            "_op_type": action,
            "_index": self._index._name,
            "_id": self.generate_id(object_instance),
            "_source": data,
        }


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

    def prepare_rate(self, instance):
        return instance.rate

    def prepare_percolator_query(self, instance):
        # Make a dict from the query string.
        qd = QueryDict(instance.query.encode(), mutable=True)
        cd = {}
        search_form = SearchForm(qd)
        if search_form.is_valid():
            cd = search_form.cleaned_data
        search_query = AudioDocument.search()
        (
            query,
            total_query_results,
            top_hits_limit,
        ) = build_es_main_query(search_query, cd)
        query_dict = query.to_dict()["query"]
        return query_dict

    def init_prepare(self):
        """Custom prepare method to achieve indexing a non-DEDField and only
        populate alert fields."""

        fields_to_index = ["percolator_query", "rate"]
        index_fields = getattr(self, "_fields", {})
        fields = []
        for name, field in iteritems(index_fields):
            prep_func = getattr(self, f"prepare_{name}", None)
            if name in fields_to_index:
                fields.append((name, field, prep_func))
        return fields
