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
    # Index nested fields
    # describing_opinion = fields.ObjectField(properties={
    #     "author_str": fields.TextField()
    # })
    #
    # group = fields.ObjectField(properties={
    #     "size": fields.IntegerField()
    # })

    # Index only ids
    describing_opinion = fields.IntegerField(attr="describing_opinion_id")
    described_opinion = fields.IntegerField(attr="described_opinion_id")
    group = fields.IntegerField(attr="group_id")

    class Index:
        # Name of Elasticsearch index
        name = "parenthetical"
        settings = {"number_of_shards": 1, "number_of_replicas": 0}

    class Django:
        model = Parenthetical
        fields = [
            # "describing_opinion",
            # "described_opinion",
            "text",
            "score",
        ]

    #     # Ensure Parenthetical will be re-saved when Opinion or ParentheticalGroup is updated
    #     related_models = [Opinion, ParentheticalGroup]
    #
    # def get_instances_from_related(self, related_instance):
    #     """If related_models is set, define how to retrieve the Car instance(s) from the related model.
    #     The related_models option should be used with caution because it can lead in the index
    #     to the updating of a lot of items.
    #     """
    #     if isinstance(related_instance, Opinion):
    #         return related_instance.opinion_set.all()
    #     elif isinstance(related_instance, Ad):
    #         return related_instance.car
