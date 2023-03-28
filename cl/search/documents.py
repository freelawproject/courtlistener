from django.conf import settings
from django_elasticsearch_dsl import Document, Index, fields

from cl.search.models import ParentheticalGroup

# Define parenthetical elasticsearch index
parenthetical_group_index = Index("parenthetical_group")
parenthetical_group_index.settings(
    number_of_shards=settings.ELASTICSEARCH_NUMBER_OF_SHARDS,
    number_of_replicas=settings.ELASTICSEARCH_NUMBER_OF_REPLICAS,
)


@parenthetical_group_index.document
class ParentheticalGroupDocument(Document):
    opinion_extracted_by_ocr = fields.BooleanField(
        attr="opinion.extracted_by_ocr"
    )
    opinion_cluster_case_name = fields.TextField(
        attr="opinion.cluster.case_name"
    )
    opinion_cluster_id = fields.IntegerField(attr="opinion.cluster_id")
    opinion_cluster_date_filed = fields.DateField(
        attr="opinion.cluster.date_filed"
    )
    docket_id = fields.IntegerField(attr="opinion.cluster.docket_id")
    opinion_cluster_docket_court_id = fields.KeywordField(
        attr="opinion.cluster.docket.court.pk"
    )
    opinion_cluster_docket_number = fields.KeywordField(
        attr="opinion.cluster.docket.docket_number"
    )
    opinion_cluster_slug = fields.KeywordField(attr="opinion.cluster.slug")

    representative_text = fields.TextField(
        attr="representative.text",
    )
    representative_score = fields.KeywordField(attr="representative.score")

    class Django:
        model = ParentheticalGroup
        fields = ["score"]
