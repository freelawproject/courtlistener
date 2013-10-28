from tastypie import fields
from tastypie.resources import ModelResource
from alert.search.models import Citation, Court, Document


class CitationResource(ModelResource):
    class Meta:
        queryset = Citation.objects.all()


class CourtResource(ModelResource):
    class Meta:
        queryset = Court.objects.exclude(jurisdiction='T')


class DocumentResource(ModelResource):
    citation = fields.ForeignKey(CitationResource, 'citation')
    court = fields.ForeignKey(CourtResource, 'court')

    class Meta:
        queryset = Document.objects.all()
        resource_name = 'opinion'

