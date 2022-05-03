from django_elasticsearch_dsl import Document, fields
from django_elasticsearch_dsl.registries import registry

from .models import Opinion, Parenthetical, ParentheticalGroup


@registry.register_document
class ParentheticalDocument(Document):
    describing_opinion = fields.ObjectField(
        properties={
            "author_str": fields.TextField(),
            "per_curiam": fields.BooleanField(),
            "joined_by_str": fields.TextField(),
            "type": fields.TextField(),
            "sha1": fields.TextField(),
            "page_count": fields.IntegerField(),
            "download_url": fields.TextField(),
            "local_path": fields.FileField(),
            "plain_text": fields.TextField(),
            "html": fields.TextField(),
            "html_lawbox": fields.TextField(),
            "html_columbia": fields.TextField(),
            "html_anon_2020": fields.TextField(),
            "xml_harvard": fields.TextField(),
            "html_with_citations": fields.TextField(),
            "extracted_by_ocr": fields.BooleanField(),
        }
    )

    described_opinion = fields.ObjectField(
        properties={
            "author_str": fields.TextField(),
            "per_curiam": fields.BooleanField(),
            "joined_by_str": fields.TextField(),
            "type": fields.TextField(),
            "sha1": fields.TextField(),
            "page_count": fields.IntegerField(),
            "download_url": fields.TextField(),
            "local_path": fields.FileField(),
            "plain_text": fields.TextField(),
            "html": fields.TextField(),
            "html_lawbox": fields.TextField(),
            "html_columbia": fields.TextField(),
            "html_anon_2020": fields.TextField(),
            "xml_harvard": fields.TextField(),
            "html_with_citations": fields.TextField(),
            "extracted_by_ocr": fields.BooleanField(),
        }
    )

    group = fields.ObjectField(
        properties={
            "score": fields.FloatField(),
            "size": fields.IntegerField(),
        }
    )
    #
    class Index:
        name = "parentheticals"

        settings = {"number_of_shards": 1, "number_of_replicas": 0}

    class Django:
        model = Parenthetical

        fields = [
            "text",
            "score",
        ]

        # related_models = [ParentheticalGroup, Opinion]

    def get_queryset(self):
        return (
            super(ParentheticalDocument, self)
            .get_queryset()
            .select_related("opinion", "parenthetical_group")
        )

    # [mln] Need to play with queries in console to better understand relationships. Coule be that I need to define Manager model.
    def get_instances_from_related(self, related_instance):
        if isinstance(related_instance, Opinion):
            return related_instance.objects.all()
        elif isinstance(related_instance, ParentheticalGroup):
            return related_instance.objects.all()


#
#     class Meta:
#         model = Parenthetical
#         fields = []
