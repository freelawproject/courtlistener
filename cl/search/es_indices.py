from django.conf import settings
from django_elasticsearch_dsl import Index

# Define parenthetical elasticsearch index
parenthetical_group_index = Index("parenthetical_group")
parenthetical_group_index.settings(
    number_of_shards=settings.ELASTICSEARCH_NUMBER_OF_SHARDS,
    number_of_replicas=settings.ELASTICSEARCH_NUMBER_OF_REPLICAS,
)

# Register ES indices here. In order to create a unique name for each index for
# testing purposes.
es_indices_registered = [parenthetical_group_index]
