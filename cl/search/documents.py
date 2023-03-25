from django.conf import settings
from django_elasticsearch_dsl import Document, Index, fields

from cl.search.models import Parenthetical

# Define parenthetical elasticsearch index
parenthetical_index = Index("parenthetical")
parenthetical_index.settings(
    number_of_shards=settings.ELASTICSEARCH_NUMBER_OF_SHARDS,
    number_of_replicas=settings.ELASTICSEARCH_NUMBER_OF_REPLICAS,
)


@parenthetical_index.document
class ParentheticalDocument(Document):
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
    describing_opinion_cluster_slug = fields.KeywordField(
        attr="describing_opinion.cluster.slug"
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
    described_opinion_cluster_slug = fields.KeywordField(
        attr="described_opinion.cluster.slug"
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
    described_opinion_cluster_precedential_status = fields.KeywordField(
        attr="described_opinion.cluster.precedential_status"
    )

    group_id = fields.IntegerField(attr="group_id")

    class Django:
        model = Parenthetical
        fields = [
            "text",
            "score",
        ]
