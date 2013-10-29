from tastypie import fields
from tastypie.authentication import BasicAuthentication, SessionAuthentication, MultiAuthentication
from tastypie.constants import ALL
from tastypie.resources import ModelResource
from tastypie.throttle import CacheThrottle
from alert.search.models import Citation, Court, Document

good_time_filters = ('exact', 'gte', 'gt', 'lte', 'lt', 'range',
                     'year', 'month', 'day', 'hour', 'minute', 'second',)
good_date_filters = good_time_filters[:-3]
numerical_filters = ('exact', 'gte', 'gt', 'lte', 'lt', 'range',)


class ModelResourceWithFieldsFilter(ModelResource):
    def full_dehydrate(self, bundle, *args, **kwargs):
        bundle = super(ModelResourceWithFieldsFilter, self).full_dehydrate(bundle, *args, **kwargs)
        fields = bundle.request.GET.get("fields", "")
        if fields:
            fields = fields.split(",")
            new_data = {}
            for k in fields:
                if k in bundle.data:
                    new_data[k] = bundle.data[k]
            bundle.data = new_data
        return bundle

class CourtResource(ModelResourceWithFieldsFilter):
    class Meta:
        authentication = MultiAuthentication(BasicAuthentication(), SessionAuthentication())
        throttle = CacheThrottle(throttle_at=1000)
        resource_name = 'jurisdiction'
        queryset = Court.objects.exclude(jurisdiction='T')
        max_limit = 20
        filtering = {
            'id': ('exact',),
            'date_modified': good_time_filters,
            'in_use': ALL,
            'position': numerical_filters,
            'short_name': ALL,
            'full_name': ALL,
            'URL': ALL,
            'start_date': good_date_filters,
            'end_date': good_date_filters,
            'jurisdictions': ALL,
        }
        ordering = ['date_modified', 'start_date', 'end_date', 'position', 'jurisdiction']


class CitationResource(ModelResourceWithFieldsFilter):
    class Meta:
        authentication = MultiAuthentication(BasicAuthentication(), SessionAuthentication())
        throttle = CacheThrottle(throttle_at=1000)
        queryset = Citation.objects.all()
        max_limit = 20
        excludes = ['slug', ]


class DocumentResource(ModelResourceWithFieldsFilter):
    citation = fields.ForeignKey(CitationResource, 'citation')
    court = fields.ForeignKey(CourtResource, 'court')
    cases_cited = fields.ManyToManyField(CitationResource, 'cases_cited', use_in='detail')
    html = fields.CharField(attribute='html', use_in='detail', null=True)
    html_lawbox = fields.CharField(attribute='html_lawbox', use_in='detail', null=True)
    html_with_citations = fields.CharField(attribute='html_with_citations', use_in='detail', null=True)
    plaintext = fields.CharField(attribute='plaintext', use_in='detail', null=True)

    class Meta:
        authentication = MultiAuthentication(BasicAuthentication(), SessionAuthentication())
        throttle = CacheThrottle(throttle_at=1000)
        resource_name = 'opinion'
        queryset = Document.objects.all().select_related('court__pk', 'citation__pk', 'citation__slug')
        max_limit = 20
        include_absolute_url = True
        excludes = ['is_stub_document',]
        filtering = {
            'id': ('exact',),
            'time_retrieved': good_time_filters,
            'date_modified': good_time_filters,
            'date_filed': good_date_filters,
            'sha1': ('exact',),
            'court': ('exact',),
            'citation': numerical_filters,
            'citation_count': numerical_filters,
            'precedential_status': ('exact', 'in'),
            'date_blocked': good_date_filters,
            'blocked': ALL,
            'extracted_by_ocr': ALL,
        }
        ordering = ['time_retrieved', 'date_modified', 'date_filed', 'pagerank', 'date_blocked']



