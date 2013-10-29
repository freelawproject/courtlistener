from tastypie import fields
from tastypie.authentication import BasicAuthentication
from tastypie.resources import ModelResource
from tastypie.throttle import CacheThrottle
from alert.search.models import Citation, Court, Document


class CitationResource(ModelResource):
    class Meta:
        queryset = Citation.objects.all()
        excludes = ['slug', ]
        authentication = BasicAuthentication()
        throttle = CacheThrottle(throttle_at=500)  # 500 / hour


class CourtResource(ModelResource):
    class Meta:
        queryset = Court.objects.exclude(jurisdiction='T')
        authentication = BasicAuthentication()
        throttle = CacheThrottle(throttle_at=500)  # 500 / hour


class DocumentResource(ModelResource):
    citation = fields.ForeignKey(CitationResource, 'citation')
    court = fields.ForeignKey(CourtResource, 'court')
    cases_cited = fields.ManyToManyField(CitationResource, 'cases_cited')

    class Meta:
        queryset = Document.objects.all()
        resource_name = 'opinion'
        excludes = ['is_stub_document',]
        authentication = BasicAuthentication()
        throttle = CacheThrottle(throttle_at=500)  # 500 / hour
