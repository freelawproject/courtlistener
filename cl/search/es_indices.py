from django.conf import settings
from django_elasticsearch_dsl import Index

# Define parenthetical elasticsearch index
parenthetical_group_index = Index("parenthetical_group")
parenthetical_group_index.settings(
    number_of_shards=settings.ELASTICSEARCH_NUMBER_OF_SHARDS,
    number_of_replicas=settings.ELASTICSEARCH_NUMBER_OF_REPLICAS,
)

# Define oral arguments elasticsearch index
oral_arguments_index = Index("oral_arguments")
oral_arguments_index.settings(
    number_of_shards=settings.ELASTICSEARCH_OA_NUMBER_OF_SHARDS,
    number_of_replicas=settings.ELASTICSEARCH_OA_NUMBER_OF_REPLICAS,
    analysis=settings.ELASTICSEARCH_DSL["analysis"],
)


# Define oral arguments alerts elasticsearch index
oral_arguments_percolator_index = Index("oral_arguments_percolator")
oral_arguments_percolator_index.settings(
    number_of_shards=settings.ELASTICSEARCH_OA_ALERTS_NUMBER_OF_SHARDS,
    number_of_replicas=settings.ELASTICSEARCH_OA_ALERTS_NUMBER_OF_REPLICAS,
    analysis=settings.ELASTICSEARCH_DSL["analysis"],
)


# Define people elasticsearch index
people_db_index = Index("people_db_index")
people_db_index.settings(
    number_of_shards=settings.ELASTICSEARCH_PEOPLE_NUMBER_OF_SHARDS,
    number_of_replicas=settings.ELASTICSEARCH_PEOPLE_NUMBER_OF_REPLICAS,
    analysis=settings.ELASTICSEARCH_DSL["analysis"],
)


# Define RECAP elasticsearch index
recap_index = Index("recap")
recap_index.settings(
    number_of_shards=settings.ELASTICSEARCH_RECAP_NUMBER_OF_SHARDS,
    number_of_replicas=settings.ELASTICSEARCH_RECAP_NUMBER_OF_REPLICAS,
    analysis=settings.ELASTICSEARCH_DSL["analysis"],
    max_inner_result_window=500,
)
