from django_elasticsearch_dsl import Document, fields
from django_elasticsearch_dsl.registries import registry

from cl.search.models import Parenthetical


@registry.register_document
class ParentheticalDocument(Document):
    describing_opinion_url = fields.KeywordField(
        attr="describing_opinion.get_absolute_url"
    )
    describing_opinion_id = fields.IntegerField(attr="describing_opinion_id")
    describing_opinion_type = fields.KeywordField(
        attr="describing_opinion.type"
    )
    describing_opinion_autor_id = fields.IntegerField(
        attr="describing_opinion.author_id"
    )
    describing_opinion_extracted_by_ocr = fields.BooleanField(
        attr="describing_opinion.extracted_by_ocr"
    )
    describing_opinion_cluster_id = fields.IntegerField(
        attr="describing_opinion.cluster_id"
    )
    describing_opinion_cluster_date_filed = fields.DateField(
        attr="describing_opinion.cluster.date_filed"
    )
    describing_opinion_cluster_docket_id = fields.IntegerField(
        attr="describing_opinion.cluster.docket_id"
    )
    describing_opinion_cluster_docket_court_id = fields.KeywordField(
        attr="describing_opinion.cluster.docket.court.pk"
    )
    describing_opinion_cluster_docket_number = fields.KeywordField(
        attr="describing_opinion.cluster.docket.docket_number"
    )

    described_opinion_url = fields.KeywordField(
        attr="described_opinion.get_absolute_url"
    )
    described_opinion_id = fields.IntegerField(attr="described_opinion_id")
    described_opinion_type = fields.KeywordField(attr="described_opinion.type")
    described_opinion_autor_id = fields.IntegerField(
        attr="described_opinion.author_id"
    )
    described_opinion_extracted_by_ocr = fields.BooleanField(
        attr="described_opinion.extracted_by_ocr"
    )
    described_opinion_cluster_id = fields.IntegerField(
        attr="described_opinion.cluster_id"
    )
    described_opinion_cluster_date_filed = fields.DateField(
        attr="described_opinion.cluster.date_filed"
    )
    described_opinion_cluster_docket_id = fields.IntegerField(
        attr="described_opinion.cluster.docket_id"
    )
    described_opinion_cluster_docket_court_id = fields.KeywordField(
        attr="described_opinion.cluster.docket.court.pk"
    )
    described_opinion_cluster_docket_number = fields.KeywordField(
        attr="described_opinion.cluster.docket.docket_number"
    )

    group_id = fields.IntegerField(attr="group_id")

    class Index:
        # Name of Elasticsearch index
        name = "parenthetical"
        settings = {"number_of_shards": 1, "number_of_replicas": 0}

    class Django:
        model = Parenthetical
        fields = [
            "text",
            "score",
        ]
