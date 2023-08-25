from datetime import datetime

from django.http import QueryDict
from django.template import loader
from django_elasticsearch_dsl import Document, fields

from cl.alerts.models import Alert
from cl.audio.models import Audio
from cl.lib.command_utils import logger
from cl.lib.elasticsearch_utils import build_es_base_query
from cl.lib.fields import PercolatorField
from cl.lib.search_index_utils import null_map
from cl.lib.utils import deepgetattr
from cl.search.es_indices import (
    oral_arguments_index,
    oral_arguments_percolator_index,
    parenthetical_group_index,
)
from cl.search.forms import SearchForm
from cl.search.models import Citation, ParentheticalGroup


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
        search_form = SearchForm(qd)
        if not search_form.is_valid():
            logger.warning(
                f"The query {qd} associated with Alert ID {instance.pk} is "
                f"invalid and was not indexed."
            )
            return None

        cd = search_form.cleaned_data
        search_query = AudioDocument.search()
        query = build_es_base_query(search_query, cd)
        return query.to_dict()["query"]
