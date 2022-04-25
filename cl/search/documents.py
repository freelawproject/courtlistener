from django_elasticsearch_dsl import Document, fields
from django_elasticsearch_dsl.registries import registry
from .models import Parenthetical, Opinion, ParentheticalGroup

@registry.register_document
class ParentheticalDocument(Document):
    group = fields.ObjectField(properties={
        'score': fields.FloatField(),
        'size': fields.IntegerField(),
    })

    class Index:
        name = 'parentheticals'
        settings = {'number_of_shards': 1,
                    'number_of_replicas': 0}

    class Django:
        model = Parenthetical

        fields = [
            'text',
            'score',
        ]

        related_models = [ParentheticalGroup]

    class Meta:
        model = Parenthetical
        fields = []
