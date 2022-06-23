from cl.search.models import (
    OpinionCluster,
    Parenthetical,
    Opinion,
    ParentheticalGroup,
)
from django_elasticsearch_dsl import Document, fields
from django_elasticsearch_dsl.registries import registry


@registry.register_document
class ParentheticalDocument(Document):
    describing_opinion_id = fields.IntegerField(attr="describing_opinion_id")
    describing_opinion_type = fields.TextField(attr="describing_opinion.type")
    describing_opinion_autor_id = fields.IntegerField(
        attr="describing_opinion.author_id")
    describing_opinion_cluster_id = fields.IntegerField(
        attr="describing_opinion.cluster_id")
    describing_opinion_cluster_docket_id = fields.IntegerField(
        attr="describing_opinion.cluster.docket_id")
    describing_opinion_cluster_docket_date_filed = fields.DateField(
        attr="describing_opinion.cluster.date_filed")
    describing_opinion_cluster_docket_court_id= fields.TextField(
        attr="describing_opinion.cluster.docket.court.pk")

    described_opinion_id = fields.IntegerField(attr="described_opinion_id")
    described_opinion_type = fields.TextField(attr="described_opinion.type")
    described_opinion_autor_id = fields.IntegerField(
        attr="described_opinion.author_id")
    described_opinion_cluster_id = fields.IntegerField(
        attr="described_opinion.cluster_id")
    described_opinion_cluster_docket_id = fields.IntegerField(
        attr="described_opinion.cluster.docket_id")
    described_opinion_cluster_docket_date_filed = fields.DateField(
        attr="described_opinion.cluster.date_filed")
    described_opinion_cluster_docket_court_id = fields.TextField(
        attr="described_opinion.cluster.docket.court.pk")

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
